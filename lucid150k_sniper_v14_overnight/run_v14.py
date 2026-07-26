"""Overnight inventory correction test for LUCID150K V14."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
V1_ROOT = BASE.parent / "lucid150k_sniper_v1"
sys.path.insert(0, str(V1_ROOT))
import run_dev as common  # noqa: E402

OUT = BASE / "output"
BULK = BASE / "nq_es_1m_20220424_20260630.dbn.zst"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V14.md"
PREREG_SHA = "7648ea736b5369a738a2cfe921c932be7896d7f54cbe224f2dccff5ad1a23613"
FAMILY = "OVERNIGHT_INVENTORY_CORRECTION"
SEED = 0x2F9A19E5436C8DB7
BOOTSTRAPS = 10_000
DEGRADED_DATES = {"2025-09-17", "2025-09-24", "2025-11-28"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def previous_close(root: Path, date: str) -> float | None:
    frame = common.load_session(root, date)
    if frame is None or frame.empty:
        return None
    return float(frame.iloc[-1]["close"])


def process_date(
    date: str,
    previous_date: str,
    context: dict,
) -> tuple[dict | None, str | None, str]:
    try:
        if date in DEGRADED_DATES:
            return None, None, "degraded_data"
        nq = common.load_session(common.NQ_ROOT, date)
        if nq is None:
            return None, None, "missing_nq"
        nq_anchor = previous_close(common.NQ_ROOT, previous_date)
        es_anchor = previous_close(common.ES_ROOT, previous_date)
        if nq_anchor is None or es_anchor is None:
            return None, None, "missing_anchor"
        nq_closes = np.asarray(context["nq_closes"], dtype=float)
        es_closes = np.asarray(context["es_closes"], dtype=float)
        if nq_closes.size == 0 or es_closes.size == 0:
            return None, None, "missing_overnight"
        nq_fraction = float(np.mean(nq_closes > nq_anchor))
        es_fraction = float(np.mean(es_closes > es_anchor))
        nq_last = float(nq_closes[-1])
        es_last = float(es_closes[-1])
        long_inventory = (
            nq_fraction >= 0.75
            and es_fraction >= 0.65
            and nq_last > nq_anchor
            and es_last > es_anchor
        )
        short_inventory = (
            nq_fraction <= 0.25
            and es_fraction <= 0.35
            and nq_last < nq_anchor
            and es_last < es_anchor
        )
        if not long_inventory and not short_inventory:
            return None, None, "no_concentrated_inventory"
        inventory_sign = 1 if long_inventory else -1

        cash_start = common.local_ts(date, "09:30:00")
        cash_end = common.local_ts(date, "09:35:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        cash = nq.loc[(nq.index >= cash_start) & (nq.index < cash_end)]
        if cash.empty:
            return None, None, "missing_cash5"
        cash_open = float(cash.iloc[0]["open"])
        cash_close = float(cash.iloc[-1]["close"])
        moved_against_inventory = (
            cash_close < cash_open
            if inventory_sign == 1
            else cash_close > cash_open
        )
        closer_to_anchor = abs(cash_close - nq_anchor) < abs(
            cash_open - nq_anchor
        )
        if not moved_against_inventory or not closer_to_anchor:
            return None, None, "no_cash_correction"

        following = nq.loc[(nq.index > cash_end) & (nq.index <= exit_cutoff)]
        if following.empty:
            return None, None, "no_entry_bar"
        sign = -inventory_sign
        entry_time = following.index[0]
        entry = float(following.iloc[0]["open"]) + sign * common.TICK
        extreme = (
            float(cash["high"].max())
            if sign == -1
            else float(cash["low"].min())
        )
        stop = (
            extreme + 4 * common.TICK
            if sign == -1
            else extreme - 4 * common.TICK
        )
        risk = sign * (entry - stop) / common.TICK
        if risk < common.MIN_R:
            risk = common.MIN_R
        if risk > common.MAX_R:
            return None, None, "risk_gt_80"
        row = common.trade_record(
            FAMILY,
            date,
            nq,
            entry_time,
            exit_cutoff,
            sign,
            entry,
            risk,
        )
        row.update(
            {
                "previous_date": previous_date,
                "nq_anchor": nq_anchor,
                "es_anchor": es_anchor,
                "nq_inventory_fraction": nq_fraction,
                "es_inventory_fraction": es_fraction,
                "nq_overnight_last": nq_last,
                "es_overnight_last": es_last,
                "cash5_open": cash_open,
                "cash5_close": cash_close,
                "cash5_high": float(cash["high"].max()),
                "cash5_low": float(cash["low"].min()),
            }
        )
        return row, None, "trade"
    except Exception as exc:  # noqa: BLE001
        return None, repr(exc), "error"


def bootstrap_ci(values: np.ndarray) -> list[float]:
    rng = np.random.default_rng(SEED)
    means = np.empty(BOOTSTRAPS, dtype=float)
    for index in range(BOOTSTRAPS):
        means[index] = rng.choice(values, size=values.size, replace=True).mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return [round(float(low), 5), round(float(high), 5)]


def overnight_contexts(frame: pd.DataFrame, dates: list[str]) -> dict[str, dict]:
    contexts = {}
    for index, date in enumerate(dates, start=1):
        current = pd.Timestamp(date, tz=common.NY)
        start = current - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
        end = current + pd.Timedelta(hours=9, minutes=30)
        start_utc = start.tz_convert(common.UTC)
        end_utc = end.tz_convert(common.UTC)
        window = frame.loc[(frame.index >= start_utc) & (frame.index < end_utc)]
        nq = window.loc[window["symbol"] == "NQ.c.0", "close"]
        es = window.loc[window["symbol"] == "ES.c.0", "close"]
        contexts[date] = {
            "nq_closes": nq.to_numpy(float),
            "es_closes": es.to_numpy(float),
        }
        if index % 250 == 0:
            print(f"contexts [{index}/{len(dates)}]", flush=True)
    return contexts


def main() -> int:
    if sha256_file(PREREG) != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    if not BULK.exists():
        raise SystemExit("Bulk overnight data is missing")
    OUT.mkdir(exist_ok=True)
    print("loading bulk overnight data", flush=True)
    bulk = db.DBNStore.from_file(BULK).to_df()
    bulk = bulk[["close", "symbol"]].sort_index()
    dates = sorted(
        set(
            path.name
            for path in common.NQ_ROOT.iterdir()
            if path.is_dir()
        )
        & set(
            path.name
            for path in common.ES_ROOT.iterdir()
            if path.is_dir()
        )
    )
    dates = [date for date in dates if "2022-04-25" <= date <= "2026-06-30"]
    contexts = overnight_contexts(bulk, dates)
    rows: list[dict] = []
    errors: list[dict] = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(
                process_date,
                date,
                dates[index - 1],
                contexts[date],
            ): date
            for index, date in enumerate(dates)
            if index > 0
        }
        complete = 0
        for future in concurrent.futures.as_completed(pending):
            complete += 1
            row, error, disposition = future.result()
            dispositions[disposition] = dispositions.get(disposition, 0) + 1
            if row is not None:
                rows.append(row)
            if error is not None:
                errors.append({"date": pending[future], "error": error})
            if complete % 100 == 0 or complete == len(pending):
                print(
                    f"[{complete:4d}/{len(pending)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )
    trades = pd.DataFrame(rows)
    if not trades.empty:
        trades = trades.sort_values("date")
    trades.to_csv(OUT / "ALL_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )
    dev = trades[
        (trades["date"] >= "2022-04-25")
        & (trades["date"] <= "2023-12-31")
    ]
    pseudo = trades[
        (trades["date"] >= "2024-01-01")
        & (trades["date"] <= "2024-12-31")
    ]
    stress = trades[
        (trades["date"] >= "2025-01-01")
        & (trades["date"] <= "2026-06-30")
    ]
    trail = common.metrics(dev)
    fixed = common.metrics(dev, "fixed_net_R")
    frequency = trail.get("n", 0) / 21.0
    difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
    gates = {
        "D1_n_ge_50": bool(trail.get("n", 0) >= 50),
        "D2_frequency_ge_2": bool(frequency >= 2.0),
        "D3_ev_gt_012R": bool(trail.get("ev_R", -999) > 0.12),
        "D4_pf_gt_135": bool(
            trail.get("pf") is not None and trail["pf"] > 1.35
        ),
        "D5_two_positive_years": bool(trail.get("positive_years", 0) == 2),
        "D6_positive_halves_ge_75pct": bool(
            trail.get("positive_halves_pct", 0) >= 75.0
        ),
        "D7_trailing_minus_fixed_ge_minus005R": bool(
            difference >= -0.05
        ),
    }
    dev_pass = all(gates.values())
    pseudo_result = None
    authorize_holdout = False
    if dev_pass:
        metrics = common.metrics(pseudo)
        ci = bootstrap_ci(pseudo["net_R"].to_numpy(float))
        pseudo_gates = {
            "V1_n_ge_25": bool(metrics.get("n", 0) >= 25),
            "V2_ev_gt_0": bool(metrics.get("ev_R", -999) > 0),
            "V3_pf_gt_115": bool(
                metrics.get("pf") is not None and metrics["pf"] > 1.15
            ),
            "V4_ci_low_gt_minus008R": bool(ci[0] > -0.08),
        }
        authorize_holdout = all(pseudo_gates.values())
        pseudo_result = {
            "metrics": metrics,
            "bootstrap_EV_R_CI95": ci,
            "gates": pseudo_gates,
            "PASS": authorize_holdout,
        }
    result = {
        "study": "LUCID150K-SNIPER-V14-OVERNIGHT-INVENTORY",
        "prereg_sha256": PREREG_SHA,
        "bulk_data_bytes": BULK.stat().st_size,
        "dates_scanned": len(dates),
        "degraded_dates_excluded": sorted(DEGRADED_DATES),
        "errors": len(errors),
        "dispositions": dispositions,
        "DEV": {
            "TRAILING": trail,
            "FIXED_1R_DIAGNOSTIC": fixed,
            "trades_per_month": round(frequency, 4),
            "trailing_minus_fixed_EV_R": round(difference, 5),
            "gates": gates,
            "PASS": dev_pass,
        },
        "PSEUDO_VAL_2024": pseudo_result,
        "STRESS_SEEN_2025_2026": common.metrics(stress),
        "AUTHORIZE_HOLDOUT_DOWNLOAD": authorize_holdout,
        "VERDICT_STAGE": (
            "PASS_TO_HOLDOUT" if authorize_holdout else "FAIL_NO_DOWNLOAD"
        ),
    }
    (OUT / "RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
