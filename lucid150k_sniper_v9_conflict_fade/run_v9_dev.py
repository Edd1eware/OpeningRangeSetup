"""DEV gate for cross-market conflict plus NQ reclaim fade V9."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
V1_ROOT = BASE.parent / "lucid150k_sniper_v1"
V4_ROOT = BASE.parent / "lucid150k_sniper_v4_breadth"
sys.path.insert(0, str(V1_ROOT))
sys.path.insert(0, str(V4_ROOT))
import run_dev as common  # noqa: E402
import run_v4 as multi_common  # noqa: E402

OUT = BASE / "output"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V9.md"
PREREG_SHA = "ab7b9ad16491cea7dd49702d3d8b499739f4225f744fe9c872a307a18c005e4e"
FAMILY = "CROSS_CONFLICT_RECLAIM_FADE"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_date(date: str) -> tuple[dict | None, str | None, str]:
    try:
        multi = multi_common.load_multi(date)
        if multi is None:
            return None, None, "missing_multi"
        nq = common.load_session(common.NQ_ROOT, date)
        es = common.load_session(common.ES_ROOT, date)
        if nq is None or es is None:
            return None, None, "missing_nq_es"
        frames = {"ES.c.0": es, **multi}
        or_start = common.local_ts(date, "09:30:00")
        or_end = common.local_ts(date, "09:31:00")
        entry_cutoff = common.local_ts(date, "10:00:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        nq_or = common.opening_range(nq, or_start, or_end)
        openings = {
            symbol: common.opening_range(frame, or_start, or_end)
            for symbol, frame in frames.items()
        }
        if nq_or is None or any(value is None for value in openings.values()):
            return None, None, "missing_or"
        touch = multi_common.first_nq_touch(
            nq, nq_or, or_end, entry_cutoff
        )
        if touch is None:
            return None, None, "no_touch"
        touch_time, break_sign = touch
        opposite_count = 0
        states = {}
        for symbol, frame in frames.items():
            close = multi_common.PriorClose(frame).before(touch_time)
            if close is None:
                return None, None, "missing_prior_close"
            high, low = openings[symbol]
            tick = multi_common.TICKS[symbol]
            opposite = (
                close <= low - tick
                if break_sign == 1
                else close >= high + tick
            )
            states[symbol] = bool(opposite)
            opposite_count += bool(opposite)
        if opposite_count < 2:
            return None, None, "opposite_lt_2"

        nq_high, nq_low = nq_or
        deadline = min(
            touch_time + pd.Timedelta(seconds=15),
            entry_cutoff,
        )
        window = nq.loc[
            (nq.index >= touch_time) & (nq.index <= deadline)
        ]
        extreme = (
            float(window.iloc[0]["high"])
            if break_sign == 1
            else float(window.iloc[0]["low"])
        )
        reclaim_time = None
        for timestamp, bar in window.iterrows():
            extreme = (
                max(extreme, float(bar["high"]))
                if break_sign == 1
                else min(extreme, float(bar["low"]))
            )
            reclaimed = (
                float(bar["close"]) < nq_high
                if break_sign == 1
                else float(bar["close"]) > nq_low
            )
            if reclaimed:
                reclaim_time = timestamp
                break
        if reclaim_time is None:
            return None, None, "no_reclaim"

        following = nq.loc[
            (nq.index > reclaim_time) & (nq.index <= entry_cutoff)
        ]
        if following.empty:
            return None, None, "no_entry_bar"
        sign = -break_sign
        entry_time = following.index[0]
        entry = float(following.iloc[0]["open"]) + sign * common.TICK
        stop = (
            extreme + 2 * common.TICK
            if sign == -1
            else extreme - 2 * common.TICK
        )
        risk = sign * (entry - stop) / common.TICK
        if risk < common.MIN_R:
            risk = common.MIN_R
            stop = entry - sign * risk * common.TICK
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
                "opposite_count": opposite_count,
                "es_opposite": states["ES.c.0"],
                "ym_opposite": states["YM.c.0"],
                "rty_opposite": states["RTY.c.0"],
                "touch_utc": touch_time.isoformat(),
                "reclaim_utc": reclaim_time.isoformat(),
            }
        )
        return row, None, "trade"
    except Exception as exc:  # noqa: BLE001
        return None, repr(exc), "error"


def main() -> int:
    if sha256_file(PREREG) != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    OUT.mkdir(exist_ok=True)
    nq_dates = {
        path.name for path in common.NQ_ROOT.iterdir()
        if path.is_dir() and "2022-04-25" <= path.name <= "2023-12-31"
    }
    es_dates = {
        path.name for path in common.ES_ROOT.iterdir()
        if path.is_dir() and "2022-04-25" <= path.name <= "2023-12-31"
    }
    dates = sorted(nq_dates & es_dates)
    missing = [
        date for date in dates
        if not (
            multi_common.MULTI_ROOT
            / date
            / "ohlcv-1s"
            / "ym_rty.dbn.zst"
        ).exists()
    ]
    if missing:
        raise SystemExit(f"DEV multi coverage incomplete: {len(missing)}")

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

    trades = pd.DataFrame(rows)
    if not trades.empty:
        trades = trades.sort_values("date")
    trades.to_csv(OUT / "DEV_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )
    trail = common.metrics(trades)
    fixed = common.metrics(trades, "fixed_net_R")
    frequency = trail.get("n", 0) / 21.0
    difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
    gates = {
        "D1_n_ge_25": bool(trail.get("n", 0) >= 25),
        "D2_frequency_ge_12": bool(frequency >= 1.2),
        "D3_ev_gt_015R": bool(trail.get("ev_R", -999) > 0.15),
        "D4_pf_gt_140": bool(
            trail.get("pf") is not None and trail["pf"] > 1.40
        ),
        "D5_two_positive_years": bool(trail.get("positive_years", 0) == 2),
        "D6_positive_halves_ge_60pct": bool(
            trail.get("positive_halves_pct", 0) >= 60.0
        ),
        "D7_trailing_minus_fixed_ge_minus005R": bool(
            difference >= -0.05
        ),
    }
    result = {
        "study": "LUCID150K-SNIPER-V9-CONFLICT-FADE",
        "stage": "DEV",
        "prereg_sha256": PREREG_SHA,
        "dates_scanned": len(dates),
        "errors": len(errors),
        "dispositions": dispositions,
        "TRAILING": trail,
        "FIXED_1R_DIAGNOSTIC": fixed,
        "trades_per_month": round(frequency, 4),
        "trailing_minus_fixed_EV_R": round(difference, 5),
        "gates": gates,
        "PASS_DEV": all(gates.values()),
        "CONTINUE_PSEUDO": all(gates.values()),
    }
    (OUT / "DEV_RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
