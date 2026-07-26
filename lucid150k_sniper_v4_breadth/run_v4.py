"""Preregistered breadth confirmation test for LUCID150K-SNIPER-V4."""

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

MULTI_ROOT = BASE.parent / "lucid150k_multi_data" / "combined_early"
OUT = BASE / "output"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V4.md"
PREREG_SHA = "4674221355ddcebe513f2ef5c03b3256db2a4e4c0b5d32ab1c502a2a07d5a5e1"

TICKS = {"ES.c.0": 0.25, "YM.c.0": 1.0, "RTY.c.0": 0.10}
SEED = 0x72C18EF05A9346BD
BOOTSTRAPS = 10_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PriorClose:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.times = frame.index.asi8
        self.closes = frame["close"].to_numpy(float)

    def before(self, timestamp: pd.Timestamp) -> float | None:
        position = int(np.searchsorted(self.times, timestamp.value, side="left")) - 1
        return (
            float(self.closes[position])
            if position >= 0
            else None
        )


def load_multi(date: str) -> dict[str, pd.DataFrame] | None:
    path = MULTI_ROOT / date / "ohlcv-1s" / "ym_rty.dbn.zst"
    if not path.exists():
        return None
    frame = db.DBNStore.from_file(path).to_df()
    output = {}
    for symbol in ("YM.c.0", "RTY.c.0"):
        selected = frame.loc[
            frame["symbol"].eq(symbol),
            ["open", "high", "low", "close"],
        ].sort_index()
        if selected.empty:
            return None
        output[symbol] = selected
    return output


def first_nq_touch(
    nq: pd.DataFrame,
    opening: tuple[float, float],
    scan_start: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> tuple[pd.Timestamp, int] | None:
    or_high, or_low = opening
    post = nq.loc[(nq.index >= scan_start) & (nq.index <= cutoff)]
    if post.empty:
        return None
    up = post["high"].to_numpy(float) >= or_high + common.TICK
    down = post["low"].to_numpy(float) <= or_low - common.TICK
    up_positions = np.flatnonzero(up)
    down_positions = np.flatnonzero(down)
    first_up = int(up_positions[0]) if up_positions.size else None
    first_down = int(down_positions[0]) if down_positions.size else None
    if first_up is None and first_down is None:
        return None
    if first_up is not None and first_down is not None:
        if first_up == first_down:
            return None
        position = min(first_up, first_down)
        sign = 1 if first_up < first_down else -1
    elif first_up is not None:
        position, sign = first_up, 1
    else:
        position, sign = first_down, -1
    return post.index[position], sign


def process_date(date: str) -> tuple[dict | None, str | None, str]:
    try:
        multi = load_multi(date)
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
        touch = first_nq_touch(nq, nq_or, or_end, entry_cutoff)
        if touch is None:
            return None, None, "no_touch"
        timestamp, sign = touch
        confirms = {}
        closes = {}
        for symbol, frame in frames.items():
            close = PriorClose(frame).before(timestamp)
            if close is None:
                return None, None, "missing_prior_close"
            closes[symbol] = close
            or_high, or_low = openings[symbol]
            tick = TICKS[symbol]
            confirms[symbol] = (
                close >= or_high + tick
                if sign == 1
                else close <= or_low - tick
            )
        count = sum(confirms.values())
        if count < 2:
            return None, None, "breadth_lt_2"

        nq_high, nq_low = nq_or
        entry = (
            nq_high + common.TICK
            if sign == 1
            else nq_low - common.TICK
        )
        midpoint = (nq_high + nq_low) / 2.0
        risk = sign * (entry - midpoint) / common.TICK
        if not (common.MIN_R <= risk <= common.MAX_R):
            return None, None, "risk_outside"
        row = common.trade_record(
            "NQ_FIRST_BREAK_BREADTH_2OF3",
            date,
            nq,
            timestamp,
            exit_cutoff,
            sign,
            entry,
            risk,
        )
        row.update(
            {
                "breadth_count": count,
                "es_confirm": confirms["ES.c.0"],
                "ym_confirm": confirms["YM.c.0"],
                "rty_confirm": confirms["RTY.c.0"],
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
    nq_dates = {
        path.name for path in common.NQ_ROOT.iterdir() if path.is_dir()
    }
    es_dates = {
        path.name for path in common.ES_ROOT.iterdir() if path.is_dir()
    }
    multi_dates = {
        path.name for path in MULTI_ROOT.iterdir()
        if path.is_dir()
        and (path / "ohlcv-1s" / "ym_rty.dbn.zst").exists()
    }
    expected = sorted(nq_dates & es_dates)
    if set(expected) - multi_dates:
        missing = sorted(set(expected) - multi_dates)
        raise SystemExit(
            f"Multi-instrument coverage incomplete: {len(missing)} dates"
        )

    rows: list[dict] = []
    errors: list[dict] = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(process_date, date): date for date in expected
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
            if complete % 100 == 0 or complete == len(expected):
                print(
                    f"[{complete:4d}/{len(expected)}] trades={len(rows)} "
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
    difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
    dev_gates = {
        "D1_n_ge_40": bool(trail.get("n", 0) >= 40),
        "D2_ev_gt_008R": bool(trail.get("ev_R", -999) > 0.08),
        "D3_pf_gt_125": bool(
            trail.get("pf") is not None and trail["pf"] > 1.25
        ),
        "D4_two_positive_years": bool(trail.get("positive_years", 0) == 2),
        "D5_positive_halves_ge_60pct": bool(
            trail.get("positive_halves_pct", 0) >= 60.0
        ),
        "D6_trailing_minus_fixed_ge_minus005R": bool(
            difference >= -0.05
        ),
    }
    dev_pass = all(dev_gates.values())

    pseudo_result = None
    authorize_holdout = False
    if dev_pass:
        pseudo_metrics = common.metrics(pseudo)
        ci = bootstrap_ci(pseudo["net_R"].to_numpy(float))
        pseudo_gates = {
            "V1_n_ge_20": bool(pseudo_metrics.get("n", 0) >= 20),
            "V2_ev_gt_0": bool(pseudo_metrics.get("ev_R", -999) > 0),
            "V3_pf_gt_110": bool(
                pseudo_metrics.get("pf") is not None
                and pseudo_metrics["pf"] > 1.10
            ),
            "V4_ci_low_gt_minus010R": bool(ci[0] > -0.10),
        }
        authorize_holdout = all(pseudo_gates.values())
        pseudo_result = {
            "metrics": pseudo_metrics,
            "bootstrap_EV_R_CI95": ci,
            "gates": pseudo_gates,
            "PASS": authorize_holdout,
        }

    result = {
        "study": "LUCID150K-SNIPER-V4-BREADTH",
        "prereg_sha256": PREREG_SHA,
        "dates_scanned": len(expected),
        "errors": len(errors),
        "dispositions": dispositions,
        "DEV": {
            "TRAILING": trail,
            "FIXED_1R_DIAGNOSTIC": fixed,
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
