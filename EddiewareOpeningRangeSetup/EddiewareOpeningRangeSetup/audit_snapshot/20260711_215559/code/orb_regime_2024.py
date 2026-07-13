# -*- coding: utf-8 -*-
"""Characterise the ORB regime by year to explain why 2024 breaks the edge.

Per RTH session we measure:
  or_range   : 09:30 minute high-low (ticks)
  day_range  : session high-low (ticks)
  trend      : close - 09:30 open (signed ticks)
  trendiness : |trend| / day_range  (1=clean trend day, ~0=round-trip chop)
  bo_dir     : first OR breakout direction
  bo_success : did the first breakout reach +40t favourable before -40t?
Aggregated by year, plus the worst single days (candidate macro shocks).
"""

from __future__ import annotations

import glob
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from progress import track

TICK = 0.25
OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
DBN_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn_2")
OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")


def load(date):
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    return db.DBNStore.from_file(hits[0]).to_df()[["open", "high", "low", "close", "volume"]].sort_index()


def session_row(date):
    df = load(date)
    if df is None or df.empty:
        return None
    day = df.index[0].strftime("%Y-%m-%d")
    orw = df.between_time(OR_START, OR_END, inclusive="left")
    if orw.empty:
        return None
    oh, ol = float(orw["high"].max()), float(orw["low"].min())
    open0 = float(orw["open"].iloc[0])
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")]
    if post.empty:
        return None
    hi, lo, clo = float(df["high"].max()), float(df["low"].min()), float(df["close"].iloc[-1])
    day_range = (hi - lo) / TICK
    trend = (clo - open0) / TICK
    # first breakout + success (+40 before -40)
    up = post.index[post["high"] > oh]; dn = post.index[post["low"] < ol]
    tu = up[0] if len(up) else None; td = dn[0] if len(dn) else None
    bo_dir, success = "NONE", np.nan
    if tu is not None or td is not None:
        if td is None or (tu is not None and tu <= td):
            bo_dir, entry, sign = "UP", oh, 1
            fwd = post.loc[post.index >= tu]
        else:
            bo_dir, entry, sign = "DOWN", ol, -1
            fwd = post.loc[post.index >= td]
        success = 0
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            fav = (h - entry) / TICK if sign == 1 else (entry - l) / TICK
            adv = (entry - l) / TICK if sign == 1 else (h - entry) / TICK
            if adv >= 40:
                success = 0; break
            if fav >= 40:
                success = 1; break
    return {"date": day, "or_range": (oh - ol) / TICK, "day_range": day_range,
            "trend": trend, "abs_trend": abs(trend),
            "trendiness": abs(trend) / max(day_range, 1),
            "bo_dir": bo_dir, "bo_success": success,
            "day_pnl_proxy": trend}


def main():
    dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    rows = []
    for d in track(dates, label="regime scan"):
        try:
            r = session_row(d)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {d}: {exc}"); r = None
        if r:
            rows.append(r)
    df = pd.DataFrame(rows)
    df["year"] = pd.to_datetime(df["date"]).dt.year
    df.to_csv(OUT_DIR / "orb_regime_by_session.csv", index=False)

    print(f"\n{'year':>6} {'n':>4} {'orRng':>6} {'dayRng':>7} {'|trend|':>8} {'trendy':>7} "
          f"{'up%':>6} {'boSucc%':>8} {'trendUp%':>9}")
    for y, g in df.groupby("year"):
        b = g[g.bo_dir.isin(['UP', 'DOWN'])]
        print(f"{y:>6} {len(g):>4} {g.or_range.median():>6.0f} {g.day_range.median():>7.0f} "
              f"{g.abs_trend.median():>8.0f} {g.trendiness.median():>7.2f} "
              f"{(b.bo_dir=='UP').mean()*100:>5.1f}% {b.bo_success.mean()*100:>7.1f}% "
              f"{(g.trend>0).mean()*100:>8.1f}%")

    print("\nWorst 10 down-trend sessions (candidate macro shocks):")
    w = df.sort_values("trend").head(10)[["date", "trend", "day_range", "trendiness"]]
    for _, r in w.iterrows():
        print(f"  {r['date']}  trend={r['trend']:>7.0f}t  dayRange={r['day_range']:>5.0f}t  trendy={r['trendiness']:.2f}")

    print("\n2024 month-by-month breakout success (+40 before -40):")
    d24 = df[(df.year == 2024) & df.bo_dir.isin(['UP', 'DOWN'])].copy()
    d24["month"] = pd.to_datetime(d24["date"]).dt.strftime("%Y-%m")
    for m, g in d24.groupby("month"):
        print(f"  {m}  n={len(g):>2}  up%={ (g.bo_dir=='UP').mean()*100:>4.0f}  "
              f"boSucc%={g.bo_success.mean()*100:>4.0f}  medTrend={g.trend.median():>6.0f}t")


if __name__ == "__main__":
    main()
