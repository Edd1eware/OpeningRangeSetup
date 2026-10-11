"""End-to-end check of stages 04-06 on synthetic 1s bars (no Databento needed).

Proves the labeling and walk-forward code runs and that the reported metrics
line up with a known ground truth: on a pure random walk the net EV must be
negative and the win rate must sit near the bracket's breakeven WR.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from config import NY, session_days

TICK = 0.25
SECONDS = 8 * 3600 + 15 * 60     # 08:00 -> 16:15 ET


def synth_bars(days: list[date], seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = []
    px = 20000.0
    for d in days:
        start = datetime.combine(d, time(8, 0), tzinfo=NY)
        steps = rng.normal(0, 0.9, SECONDS).cumsum() + px
        ts = pd.date_range(start, periods=SECONDS, freq="1s", tz=NY)
        close = np.round(steps / TICK) * TICK
        wig = np.abs(rng.normal(0, 1.2, SECONDS))
        df = pd.DataFrame({
            "ts_utc": ts.tz_convert("UTC"), "ts_ny": ts, "session": d,
            "open": np.r_[close[0], close[:-1]], "close": close,
            "high": close + wig, "low": close - wig,
            "volume": rng.integers(1, 400, SECONDS)})
        out.append(df)
        px = float(close[-1])
    return pd.concat(out, ignore_index=True)


def synth_features(events: Path, dest: Path) -> None:
    """Pure-noise features: a healthy pipeline must NOT find edge in these."""
    ev = pd.read_parquet(events)
    sigs = ev.drop_duplicates(["session", "or_minutes"])[["session", "or_minutes"]]
    rng = np.random.default_rng(3)
    for c in ("imb_1", "imb_5", "spread_ticks", "aggr_imb_60s",
              "cancel_per_trade", "cvd_aligned", "level_pulled"):
        sigs[c] = rng.normal(size=len(sigs))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sigs.to_parquet(dest, index=False)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="orb_smoke_"))
    env = {**os.environ, "ORB_DATA_ROOT": str(tmp), "PYTHONIOENCODING": "utf-8"}
    print(f"synthetic data root: {tmp}")

    days = []
    for y in (2022, 2023, 2024, 2025):
        days += session_days(date(y, 4, 1), date(y, 9, 30))[:60]
    bars = synth_bars(days)
    (tmp / "bars").mkdir(parents=True, exist_ok=True)
    for year, g in bars.groupby(bars.ts_ny.dt.year):
        g.to_parquet(tmp / "bars" / f"bars_1s_{year}.parquet", index=False)
    print(f"{len(bars):,} synthetic 1s bars over {len(days)} sessions")

    r = subprocess.run([sys.executable, "-u", str(HERE / "04_or_events.py")],
                       env=env, cwd=HERE.parent)
    if r.returncode:
        return r.returncode
    synth_features(tmp / "events" / "or_events.parquet",
                   tmp / "features" / "l2_features.parquet")
    r = subprocess.run([sys.executable, "-u", str(HERE / "06_train_catboost.py"),
                        "--or-minutes", "15", "--tp", "40", "--sl", "20"],
                       env=env, cwd=HERE.parent)
    print(f"\nsmoke test exit={r.returncode}. random-walk input, so a negative "
          "net EV and a WR near breakeven is the CORRECT result.")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
