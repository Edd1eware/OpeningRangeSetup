"""DST-correct development reconstruction for LUCID150K-SNIPER-V3."""

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
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V3.md"
PREREG_SHA = "915ec4c4365a49fd4575effa20066ad6b94fbff6c85caeda5a1db16d94725eb2"

TICK = 0.25
COST_TICKS = 4.0
STOP_TICKS = 55.0
TARGET_TICKS = 120.0
DEV_START = "2022-04-25"
DEV_END = "2026-06-30"


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
    entry: float,
    trailing: bool,
) -> dict:
    forward = nq.loc[(nq.index >= entry_time) & (nq.index <= exit_cutoff)]
    if forward.empty:
        raise ValueError("No bars after entry")
    stop = entry - STOP_TICKS * TICK
    target = entry + TARGET_TICKS * TICK
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
        mae = min(mae, (low - entry) / TICK)
        if low <= stop:
            gross = (stop - entry) / TICK
            return outcome(gross, mae, "STOP", activated)
        if high >= target:
            return outcome(TARGET_TICKS, mae, "TARGET", activated)
        if trailing:
            best = max(best, high)
            if (best - entry) / TICK >= STOP_TICKS:
                activated = True
                break_even = entry + COST_TICKS * TICK
                trail = best - STOP_TICKS * TICK
                stop = max(stop, break_even, trail)

    gross = (close - entry) / TICK
    return outcome(gross, mae, "EOD", activated)


def outcome(
    gross_ticks: float,
    mae_ticks: float,
    reason: str,
    activated: bool,
) -> dict:
    net = gross_ticks - COST_TICKS
    return {
        "gross_ticks": gross_ticks,
        "net_ticks": net,
        "net_R": net / STOP_TICKS,
        "mae_ticks": mae_ticks,
        "exit_reason": reason,
        "trailing_activated": activated,
    }


def process_date(date: str) -> tuple[dict | None, str | None]:
    try:
        nq = common.load_session(common.NQ_ROOT, date)
        if nq is None:
            return None, None
        or_start = common.local_ts(date, "09:30:00")
        or_end = common.local_ts(date, "09:31:00")
        entry_cutoff = common.local_ts(date, "10:00:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        opening = common.opening_range(nq, or_start, or_end)
        if opening is None:
            return None, None
        or_high, or_low = opening
        post = nq.loc[
            (nq.index >= or_end) & (nq.index <= entry_cutoff)
        ]
        if post.empty:
            return None, None

        up = post["high"].to_numpy(float) >= or_high + TICK
        down = post["low"].to_numpy(float) <= or_low - TICK
        up_positions = np.flatnonzero(up)
        down_positions = np.flatnonzero(down)
        first_up = int(up_positions[0]) if up_positions.size else None
        first_down = int(down_positions[0]) if down_positions.size else None
        if first_up is None:
            return None, None
        if first_down is not None and first_down <= first_up:
            return None, None
        if bool(up[first_up] and down[first_up]):
            return None, None

        entry_time = post.index[first_up]
        entry = or_high + TICK
        trail = simulate(nq, entry_time, exit_cutoff, entry, True)
        fixed = simulate(nq, entry_time, exit_cutoff, entry, False)
        return {
            "family": "FIRST_UP_ORB_120_55_TRAIL",
            "date": date,
            "year": int(date[:4]),
            "half": f"{date[:4]}-H{1 if int(date[5:7]) <= 6 else 2}",
            "entry_utc": entry_time.isoformat(),
            "entry": entry,
            "risk_ticks": STOP_TICKS,
            **trail,
            "fixed_net_ticks": fixed["net_ticks"],
            "fixed_net_R": fixed["net_R"],
            "fixed_exit_reason": fixed["exit_reason"],
        }, None
    except Exception as exc:  # noqa: BLE001
        return None, repr(exc)


def inclusive_months(start: str, end: str) -> int:
    first = pd.Period(start[:7], freq="M")
    last = pd.Period(end[:7], freq="M")
    return int(last.ordinal - first.ordinal + 1)


def positive_half_concentration(frame: pd.DataFrame) -> float | None:
    pnl = frame.groupby("half")["net_R"].sum()
    positive = pnl[pnl > 0]
    if positive.empty:
        return None
    return float(positive.max() / positive.sum())


def main() -> int:
    if sha256_file(PREREG) != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    OUT.mkdir(exist_ok=True)
    dates = sorted(
        path.name for path in common.NQ_ROOT.iterdir()
        if path.is_dir() and DEV_START <= path.name <= DEV_END
    )
    rows: list[dict] = []
    errors: list[dict] = []
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
            try:
                row, error = future.result()
                if row is not None:
                    rows.append(row)
                if error is not None:
                    errors.append({"date": date, "error": error})
            except Exception as exc:  # noqa: BLE001
                errors.append({"date": date, "error": repr(exc)})
            if complete % 100 == 0 or complete == len(dates):
                print(
                    f"[{complete:4d}/{len(dates)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )

    trades = pd.DataFrame(rows).sort_values("date")
    trades.to_csv(OUT / "DEV_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )

    trail = common.metrics(trades)
    fixed = common.metrics(trades, "fixed_net_R")
    months = inclusive_months(DEV_START, DEV_END)
    frequency = len(trades) / months
    concentration = positive_half_concentration(trades)
    difference = trail["ev_R"] - fixed["ev_R"]
    gates = {
        "D1_n_ge_200": bool(trail["n"] >= 200),
        "D2_frequency_ge_6_per_month": bool(frequency >= 6.0),
        "D3_ev_gt_008R": bool(trail["ev_R"] > 0.08),
        "D4_pf_gt_120": bool(
            trail["pf"] is not None and trail["pf"] > 1.20
        ),
        "D5_positive_years_ge_3": bool(trail["positive_years"] >= 3),
        "D6_positive_halves_ge_65pct": bool(
            trail["positive_halves_pct"] >= 65.0
        ),
        "D7_max_positive_half_share_le_50pct": bool(
            concentration is not None and concentration <= 0.50
        ),
        "D8_trailing_minus_fixed_ge_minus003R": bool(difference >= -0.03),
    }
    passed = all(gates.values())
    result = {
        "study": "LUCID150K-SNIPER-V3",
        "prereg_sha256": PREREG_SHA,
        "dates_scanned": len(dates),
        "errors": len(errors),
        "TRAILING": trail,
        "FIXED_120_55_DIAGNOSTIC": fixed,
        "trades_per_calendar_month": round(frequency, 4),
        "max_positive_half_pnl_share": (
            round(concentration, 5) if concentration is not None else None
        ),
        "trailing_minus_fixed_EV_R": round(difference, 5),
        "gates": gates,
        "PASS_DEV_SEEN": passed,
        "AUTHORIZE_HOLDOUT_DOWNLOAD": passed,
        "VERDICT_STAGE": (
            "PASS_TO_ONE_SHOT_HOLDOUT" if passed else "FAIL_NO_DOWNLOAD"
        ),
    }
    (OUT / "DEV_RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
