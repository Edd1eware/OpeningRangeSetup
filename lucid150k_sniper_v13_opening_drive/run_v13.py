"""Opening-drive pullback and resumption test for LUCID150K V13."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
V1_ROOT = BASE.parent / "lucid150k_sniper_v1"
sys.path.insert(0, str(V1_ROOT))
import run_dev as common  # noqa: E402

OUT = BASE / "output"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V13.md"
PREREG_SHA = "1ff52e3f38b31392ac644067f5d29f626f98cfb4084305ba5ac3c303fd73771a"
FAMILY = "OPENING_DRIVE_PULLBACK_RESUMPTION"
SEED = 0xB3DAE74150A99D2C
BOOTSTRAPS = 10_000
RISK_TICKS = 40.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_date(date: str) -> tuple[dict | None, str | None, str]:
    try:
        nq = common.load_session(common.NQ_ROOT, date)
        if nq is None:
            return None, None, "missing_data"
        start = common.local_ts(date, "09:30:00")
        drive_end = common.local_ts(date, "09:45:00")
        entry_cutoff = common.local_ts(date, "10:45:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        drive = nq.loc[(nq.index >= start) & (nq.index < drive_end)]
        if drive.empty:
            return None, None, "missing_drive"

        drive_open = float(drive.iloc[0]["open"])
        drive_close = float(drive.iloc[-1]["close"])
        drive_high = float(drive["high"].max())
        drive_low = float(drive["low"].min())
        drive_range = drive_high - drive_low
        body = drive_close - drive_open
        if drive_range <= 0.0 or body == 0.0:
            return None, None, "not_directional"
        sign = 1 if body > 0.0 else -1
        efficiency = abs(body) / drive_range
        close_location = (drive_close - drive_low) / drive_range
        exterior = close_location >= 0.80 if sign == 1 else close_location <= 0.20
        if efficiency < 0.70 or not exterior:
            return None, None, "inefficient_drive"

        midpoint = drive_open + 0.50 * body
        resume_level = drive_open + 0.75 * body
        scan = nq.loc[(nq.index >= drive_end) & (nq.index <= entry_cutoff)]
        pulled_back = False
        trigger_time = None
        for timestamp, bar in scan.iterrows():
            invalidated = (
                float(bar["low"]) <= drive_open
                if sign == 1
                else float(bar["high"]) >= drive_open
            )
            if invalidated:
                return None, None, "retrace_to_open"
            if not pulled_back:
                pulled_back = (
                    float(bar["low"]) <= midpoint
                    if sign == 1
                    else float(bar["high"]) >= midpoint
                )
            resumed = (
                float(bar["close"]) >= resume_level
                if sign == 1
                else float(bar["close"]) <= resume_level
            )
            if pulled_back and resumed:
                trigger_time = timestamp
                break
        if not pulled_back:
            return None, None, "no_half_pullback"
        if trigger_time is None:
            return None, None, "no_resumption"

        following = nq.loc[
            (nq.index > trigger_time) & (nq.index <= entry_cutoff)
        ]
        if following.empty:
            return None, None, "no_entry_bar"
        entry_time = following.index[0]
        entry = float(following.iloc[0]["open"]) + sign * common.TICK
        row = common.trade_record(
            FAMILY,
            date,
            nq,
            entry_time,
            exit_cutoff,
            sign,
            entry,
            RISK_TICKS,
        )
        row.update(
            {
                "drive_open": drive_open,
                "drive_close": drive_close,
                "drive_high": drive_high,
                "drive_low": drive_low,
                "drive_efficiency": efficiency,
                "drive_close_location": close_location,
                "pullback_midpoint": midpoint,
                "resumption_level": resume_level,
                "trigger_utc": trigger_time.isoformat(),
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


def main() -> int:
    if sha256_file(PREREG) != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    OUT.mkdir(exist_ok=True)
    dates = sorted(
        path.name for path in common.NQ_ROOT.iterdir() if path.is_dir()
    )
    rows: list[dict] = []
    errors: list[dict] = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(process_date, date): date for date in dates
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
            if complete % 100 == 0 or complete == len(dates):
                print(
                    f"[{complete:4d}/{len(dates)}] trades={len(rows)} "
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
        "study": "LUCID150K-SNIPER-V13-OPENING-DRIVE",
        "prereg_sha256": PREREG_SHA,
        "dates_scanned": len(dates),
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
