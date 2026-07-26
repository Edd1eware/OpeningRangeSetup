"""Preregistered normalized gap-and-go test for LUCID150K-SNIPER-V6."""

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
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V6.md"
PREREG_SHA = "2bb503fcf7bb25a60eb3e625e2a8e528821532fb381f0207706dec010124cf1a"
FAMILY = "NORMALIZED_GAP_AND_GO"
SEED = 0x61D4A8C3207FEB95
BOOTSTRAPS = 10_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_pair(
    previous_date: str,
    date: str,
) -> tuple[dict | None, str | None, str]:
    try:
        previous = common.load_session(common.NQ_ROOT, previous_date)
        current = common.load_session(common.NQ_ROOT, date)
        if previous is None or current is None:
            return None, None, "missing_data"

        prev_start = common.local_ts(previous_date, "09:30:00")
        prev_end = common.local_ts(previous_date, "16:00:00")
        prior = previous.loc[
            (previous.index >= prev_start) & (previous.index < prev_end)
        ]
        if prior.empty:
            return None, None, "missing_previous_rth"
        prev_close = float(prior["close"].iloc[-1])
        prev_range = float(prior["high"].max() - prior["low"].min())
        if prev_range <= 0:
            return None, None, "zero_previous_range"

        or_start = common.local_ts(date, "09:30:00")
        or_end = common.local_ts(date, "09:31:00")
        entry_cutoff = common.local_ts(date, "10:00:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        current_open_rows = current.loc[
            (current.index >= or_start) & (current.index < or_end)
        ]
        opening = common.opening_range(current, or_start, or_end)
        if current_open_rows.empty or opening is None:
            return None, None, "missing_current_or"
        current_open = float(current_open_rows["open"].iloc[0])
        gap = current_open - prev_close
        if abs(gap) < 0.25 * prev_range:
            return None, None, "gap_too_small"
        sign = 1 if gap > 0 else -1
        or_high, or_low = opening
        held_open = (
            or_low > prev_close if sign == 1 else or_high < prev_close
        )
        if not held_open:
            return None, None, "gap_not_held"

        post = current.loc[
            (current.index >= or_end) & (current.index <= entry_cutoff)
        ]
        if post.empty:
            return None, None, "missing_scan"
        up = post["high"].to_numpy(float) >= or_high + common.TICK
        down = post["low"].to_numpy(float) <= or_low - common.TICK
        up_positions = np.flatnonzero(up)
        down_positions = np.flatnonzero(down)
        first_up = int(up_positions[0]) if up_positions.size else None
        first_down = int(down_positions[0]) if down_positions.size else None
        wanted = first_up if sign == 1 else first_down
        opposite = first_down if sign == 1 else first_up
        if wanted is None:
            return None, None, "no_directional_touch"
        if opposite is not None and opposite <= wanted:
            return None, None, "opposite_first_or_ambiguous"

        entry_time = post.index[wanted]
        entry = (
            or_high + common.TICK
            if sign == 1
            else or_low - common.TICK
        )
        midpoint = (or_high + or_low) / 2.0
        risk = sign * (entry - midpoint) / common.TICK
        if not (common.MIN_R <= risk <= common.MAX_R):
            return None, None, "risk_outside"
        row = common.trade_record(
            FAMILY,
            date,
            current,
            entry_time,
            exit_cutoff,
            sign,
            entry,
            risk,
        )
        row.update(
            {
                "previous_date": previous_date,
                "prev_close": prev_close,
                "prev_range": prev_range,
                "current_open": current_open,
                "gap": gap,
                "gap_over_prev_range": gap / prev_range,
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


def inclusive_months(start: str, end: str) -> int:
    first = pd.Period(start[:7], freq="M")
    last = pd.Period(end[:7], freq="M")
    return int(last.ordinal - first.ordinal + 1)


def main() -> int:
    if sha256_file(PREREG) != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    OUT.mkdir(exist_ok=True)
    dates = sorted(
        path.name for path in common.NQ_ROOT.iterdir() if path.is_dir()
    )
    pairs = [
        (dates[index - 1], dates[index])
        for index in range(1, len(dates))
        if "2022-04-26" <= dates[index] <= "2026-06-30"
    ]
    rows: list[dict] = []
    errors: list[dict] = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(process_pair, previous, date): date
            for previous, date in pairs
        }
        complete = 0
        for future in concurrent.futures.as_completed(pending):
            date = pending[future]
            complete += 1
            try:
                row, error, disposition = future.result()
                dispositions[disposition] = dispositions.get(disposition, 0) + 1
                if row is not None:
                    rows.append(row)
                if error is not None:
                    errors.append({"date": date, "error": error})
            except Exception as exc:  # noqa: BLE001
                errors.append({"date": date, "error": repr(exc)})
            if complete % 100 == 0 or complete == len(pairs):
                print(
                    f"[{complete:4d}/{len(pairs)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )

    trades = pd.DataFrame(rows).sort_values("date")
    trades.to_csv(OUT / "ALL_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )
    dev = trades[
        (trades["date"] >= "2022-04-26")
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
    frequency = trail.get("n", 0) / inclusive_months(
        "2022-04-26", "2023-12-31"
    )
    difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
    dev_gates = {
        "D1_n_ge_40": bool(trail.get("n", 0) >= 40),
        "D2_frequency_ge_2_per_month": bool(frequency >= 2.0),
        "D3_ev_gt_015R": bool(trail.get("ev_R", -999) > 0.15),
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
    dev_pass = all(dev_gates.values())

    pseudo_result = None
    authorize_holdout = False
    if dev_pass:
        metrics = common.metrics(pseudo)
        ci = bootstrap_ci(pseudo["net_R"].to_numpy(float))
        gates = {
            "V1_n_ge_20": bool(metrics.get("n", 0) >= 20),
            "V2_ev_gt_0": bool(metrics.get("ev_R", -999) > 0),
            "V3_pf_gt_115": bool(
                metrics.get("pf") is not None and metrics["pf"] > 1.15
            ),
            "V4_ci_low_gt_minus010R": bool(ci[0] > -0.10),
        }
        authorize_holdout = all(gates.values())
        pseudo_result = {
            "metrics": metrics,
            "bootstrap_EV_R_CI95": ci,
            "gates": gates,
            "PASS": authorize_holdout,
        }

    result = {
        "study": "LUCID150K-SNIPER-V6-GAP",
        "prereg_sha256": PREREG_SHA,
        "pairs_scanned": len(pairs),
        "errors": len(errors),
        "dispositions": dispositions,
        "DEV": {
            "TRAILING": trail,
            "FIXED_1R_DIAGNOSTIC": fixed,
            "trades_per_calendar_month": round(frequency, 4),
            "trailing_minus_fixed_EV_R": round(difference, 5),
            "gates": dev_gates,
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
