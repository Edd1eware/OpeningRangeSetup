"""Five-minute OR acceptance + ES pullback test for V10."""

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
V4_ROOT = BASE.parent / "lucid150k_sniper_v4_breadth"
sys.path.insert(0, str(V1_ROOT))
sys.path.insert(0, str(V4_ROOT))
import run_dev as common  # noqa: E402
from run_v4 import PriorClose  # noqa: E402

OUT = BASE / "output"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V10.md"
PREREG_SHA = "7b882794f7cf0cf63da4e0e2f275a50d3e99ed938ac41237b1ca249fa259a72e"
FAMILY = "OR5_ACCEPTANCE_ES_PULLBACK"
STOP_TICKS = 40.0
TARGET_TICKS = 80.0
COST_TICKS = 4.0
SEED = 0xE2A7601D4CB895F3
BOOTSTRAPS = 10_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def simulate(
    nq: pd.DataFrame,
    entry_time: pd.Timestamp,
    exit_cutoff: pd.Timestamp,
    sign: int,
    entry: float,
    trailing: bool,
) -> dict:
    forward = nq.loc[(nq.index >= entry_time) & (nq.index <= exit_cutoff)]
    if forward.empty:
        raise ValueError("No bars after entry")
    stop = entry - sign * STOP_TICKS * common.TICK
    target = entry + sign * TARGET_TICKS * common.TICK
    best = entry
    mae = 0.0
    activated = False
    close = entry
    for high, low, bar_close in zip(
        forward["high"].to_numpy(float),
        forward["low"].to_numpy(float),
        forward["close"].to_numpy(float),
    ):
        close = bar_close
        adverse = (
            (low - entry) / common.TICK
            if sign == 1
            else (entry - high) / common.TICK
        )
        mae = min(mae, adverse)
        stop_hit = low <= stop if sign == 1 else high >= stop
        if stop_hit:
            gross = sign * (stop - entry) / common.TICK
            return outcome(gross, mae, "STOP", activated)
        target_hit = high >= target if sign == 1 else low <= target
        if target_hit:
            return outcome(TARGET_TICKS, mae, "TARGET", activated)
        if trailing:
            best = max(best, high) if sign == 1 else min(best, low)
            favorable = sign * (best - entry) / common.TICK
            if favorable >= STOP_TICKS:
                activated = True
                break_even = entry + sign * COST_TICKS * common.TICK
                trail = best - sign * STOP_TICKS * common.TICK
                stop = (
                    max(stop, break_even, trail)
                    if sign == 1
                    else min(stop, break_even, trail)
                )
    gross = sign * (close - entry) / common.TICK
    return outcome(gross, mae, "EOD", activated)


def outcome(
    gross: float,
    mae: float,
    reason: str,
    activated: bool,
) -> dict:
    net = gross - COST_TICKS
    return {
        "gross_ticks": gross,
        "net_ticks": net,
        "net_R": net / STOP_TICKS,
        "mae_ticks": mae,
        "exit_reason": reason,
        "trailing_activated": activated,
    }


def process_date(date: str) -> tuple[dict | None, str | None, str]:
    try:
        nq = common.load_session(common.NQ_ROOT, date)
        es = common.load_session(common.ES_ROOT, date)
        if nq is None or es is None:
            return None, None, "missing_data"
        or_start = common.local_ts(date, "09:30:00")
        or_end = common.local_ts(date, "09:35:00")
        accept_cutoff = common.local_ts(date, "10:15:00")
        entry_cutoff = common.local_ts(date, "10:30:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        nq_or = common.opening_range(nq, or_start, or_end)
        es_or = common.opening_range(es, or_start, or_end)
        if nq_or is None or es_or is None:
            return None, None, "missing_or"
        nq_high, nq_low = nq_or
        es_high, es_low = es_or
        es_lookup = PriorClose(es)
        scan = nq.loc[
            (nq.index >= or_end) & (nq.index <= accept_cutoff)
        ]
        previous_sign = 0
        count = 0
        previous_time = None
        accepted_sign = 0
        accepted_time = None
        for timestamp, bar in scan.iterrows():
            close = float(bar["close"])
            sign = (
                1 if close >= nq_high + common.TICK
                else -1 if close <= nq_low - common.TICK
                else 0
            )
            is_consecutive = (
                previous_time is not None
                and timestamp - previous_time == pd.Timedelta(seconds=1)
            )
            if sign != 0 and sign == previous_sign and is_consecutive:
                count += 1
            elif sign != 0:
                count = 1
            else:
                count = 0
            previous_sign = sign
            previous_time = timestamp
            if count < 3:
                continue
            es_close = es_lookup.before(timestamp)
            if es_close is None:
                return None, None, "missing_es_close"
            confirmed = (
                es_close >= es_high + common.TICK
                if sign == 1
                else es_close <= es_low - common.TICK
            )
            if not confirmed:
                return None, None, "first_acceptance_unconfirmed"
            accepted_sign = sign
            accepted_time = timestamp
            break
        if accepted_time is None:
            return None, None, "no_acceptance"

        deadline = min(
            accepted_time + pd.Timedelta(seconds=300),
            entry_cutoff,
        )
        window = nq.loc[
            (nq.index > accepted_time) & (nq.index <= deadline)
        ]
        retest_time = None
        for timestamp, bar in window.iterrows():
            close = float(bar["close"])
            invalid = (
                close <= nq_low - common.TICK
                if accepted_sign == 1
                else close >= nq_high + common.TICK
            )
            if invalid:
                return None, None, "opposite_close"
            defended = (
                float(bar["low"]) <= nq_high
                and close >= nq_high + common.TICK
                if accepted_sign == 1
                else float(bar["high"]) >= nq_low
                and close <= nq_low - common.TICK
            )
            if not defended:
                continue
            es_close = es_lookup.before(timestamp)
            confirmed = (
                es_close is not None
                and (
                    es_close >= es_high + common.TICK
                    if accepted_sign == 1
                    else es_close <= es_low - common.TICK
                )
            )
            if not confirmed:
                return None, None, "retest_es_unconfirmed"
            retest_time = timestamp
            break
        if retest_time is None:
            return None, None, "no_retest"
        following = nq.loc[
            (nq.index > retest_time) & (nq.index <= entry_cutoff)
        ]
        if following.empty:
            return None, None, "no_entry_bar"
        entry_time = following.index[0]
        entry = float(following.iloc[0]["open"]) + accepted_sign * common.TICK
        trail = simulate(
            nq, entry_time, exit_cutoff, accepted_sign, entry, True
        )
        fixed = simulate(
            nq, entry_time, exit_cutoff, accepted_sign, entry, False
        )
        row = {
            "family": FAMILY,
            "date": date,
            "year": int(date[:4]),
            "half": f"{date[:4]}-H{1 if int(date[5:7]) <= 6 else 2}",
            "side": "LONG" if accepted_sign == 1 else "SHORT",
            "entry_utc": entry_time.isoformat(),
            "entry": entry,
            "risk_ticks": STOP_TICKS,
            "acceptance_utc": accepted_time.isoformat(),
            "retest_utc": retest_time.isoformat(),
            **trail,
            "fixed_net_ticks": fixed["net_ticks"],
            "fixed_net_R": fixed["net_R"],
            "fixed_exit_reason": fixed["exit_reason"],
        }
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
        set(path.name for path in common.NQ_ROOT.iterdir() if path.is_dir())
        & set(path.name for path in common.ES_ROOT.iterdir() if path.is_dir())
    )
    rows = []
    errors = []
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
            date = pending[future]
            complete += 1
            row, error, disposition = future.result()
            dispositions[disposition] = dispositions.get(disposition, 0) + 1
            if row is not None:
                rows.append(row)
            if error is not None:
                errors.append({"date": date, "error": error})
            if complete % 100 == 0 or complete == len(dates):
                print(
                    f"[{complete:4d}/{len(dates)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )
    trades = pd.DataFrame(rows).sort_values("date")
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
        "D2_frequency_ge_25": bool(frequency >= 2.5),
        "D3_ev_gt_010R": bool(trail.get("ev_R", -999) > 0.10),
        "D4_pf_gt_130": bool(
            trail.get("pf") is not None and trail["pf"] > 1.30
        ),
        "D5_two_positive_years": bool(trail.get("positive_years", 0) == 2),
        "D6_positive_halves_ge_60pct": bool(
            trail.get("positive_halves_pct", 0) >= 60.0
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
            "V4_ci_low_gt_minus010R": bool(ci[0] > -0.10),
        }
        authorize_holdout = all(pseudo_gates.values())
        pseudo_result = {
            "metrics": metrics,
            "bootstrap_EV_R_CI95": ci,
            "gates": pseudo_gates,
            "PASS": authorize_holdout,
        }
    result = {
        "study": "LUCID150K-SNIPER-V10-OR5",
        "prereg_sha256": PREREG_SHA,
        "dates_scanned": len(dates),
        "errors": len(errors),
        "dispositions": dispositions,
        "DEV": {
            "TRAILING": trail,
            "FIXED_80_40_DIAGNOSTIC": fixed,
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
