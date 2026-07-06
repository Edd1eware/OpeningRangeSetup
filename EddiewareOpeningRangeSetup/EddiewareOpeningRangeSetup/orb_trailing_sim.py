# -*- coding: utf-8 -*-
"""ORB with trailing-stop management, evaluated per year (no overfit).

Entry: first 09:30-OR breakout (UP pierces OR high, DOWN pierces OR low),
entry at the OR level. Management = trailing stop, defined by three params:

  sl   : initial stop distance (ticks) from entry
  act  : activation - once MFE >= act ticks, trailing engages
  dist : trailing distance (ticks) behind the best favourable price

Bar-by-bar rule (conservative, no intrabar look-ahead):
  1) with the stop carried from the previous bar, if this bar's adverse
     extreme reaches it -> exit at the stop;
  2) else update the best favourable price, activate/ratchet the trail.
Session end -> exit at close. Realized P&L is signed ticks (favourable +).

We grid several trailing families plus a fixed 60/60 baseline and print the
year x metric table (project backtest standard). $5/tick (NQ).
"""

from __future__ import annotations

import glob
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from progress import track

TICK = 0.25
TICK_USD = 5.0
OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
COMMISSION_TICKS = 2.0

# (name, sl, act, dist);  dist=None -> fixed bracket TP=sl_as_tp (baseline)
TRAILS = [
    ("trail_50_20_40", 50, 20, 40),   # ATRAPADOS family
    ("trail_50_30_50", 50, 30, 50),
    ("trail_50_20_30", 50, 20, 30),
    ("trail_40_20_40", 40, 20, 40),
    ("trail_30_20_30", 30, 20, 30),
    ("trail_60_30_50", 60, 30, 50),
]
FIXED = [("fixed_60_60", 60, 60), ("fixed_60_30", 60, 30)]

DBN_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
)
OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")


def load_session(date: str):
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    return db.DBNStore.from_file(hits[0]).to_df()[["open", "high", "low", "close", "volume"]].sort_index()


def find_breakout(df: pd.DataFrame):
    day = df.index[0].strftime("%Y-%m-%d")
    orw = df.between_time(OR_START, OR_END, inclusive="left")
    if orw.empty:
        return None
    or_high, or_low = float(orw["high"].max()), float(orw["low"].min())
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")]
    if post.empty:
        return None
    up = post.index[post["high"] > or_high]
    dn = post.index[post["low"] < or_low]
    t_up = up[0] if len(up) else None
    t_dn = dn[0] if len(dn) else None
    if t_up is None and t_dn is None:
        return None
    if t_dn is None or (t_up is not None and t_up <= t_dn):
        return "UP", or_high, 1, post.loc[post.index >= t_up]
    return "DOWN", or_low, -1, post.loc[post.index >= t_dn]


def trail_pnl(fwd, entry, sign, sl, act, dist):
    stop = entry - sign * sl * TICK
    best = entry
    activated = False
    close = entry
    highs = fwd["high"].to_numpy()
    lows = fwd["low"].to_numpy()
    closes = fwd["close"].to_numpy()
    for h, l, c in zip(highs, lows, closes):
        close = c
        # 1) stop carried from prior bar
        if sign == 1 and l <= stop:
            return (stop - entry) / TICK
        if sign == -1 and h >= stop:
            return (entry - stop) / TICK
        # 2) update best & trail for next bar
        best = max(best, h) if sign == 1 else min(best, l)
        mfe = (best - entry) / TICK * sign
        if not activated and mfe >= act:
            activated = True
        if activated:
            new_stop = best - sign * dist * TICK
            stop = max(stop, new_stop) if sign == 1 else min(stop, new_stop)
    return (close - entry) / TICK * sign


def fixed_pnl(fwd, entry, sign, tp, sl):
    if sign == 1:
        tpp, slp = entry + tp * TICK, entry - sl * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            if l <= slp:
                return -sl
            if h >= tpp:
                return tp
    else:
        tpp, slp = entry - tp * TICK, entry + sl * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            if h >= slp:
                return -sl
            if l <= tpp:
                return tp
    return (fwd["close"].iloc[-1] - entry) / TICK * sign


def main():
    dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    rows = []
    for d in track(dates, label="ORB trailing sim"):
        try:
            df = load_session(d)
            if df is None or df.empty:
                continue
            bo = find_breakout(df)
            if bo is None:
                continue
            direction, entry, sign, fwd = bo
            rec = {"date": d, "direction": direction}
            for name, sl, act, dist in TRAILS:
                rec[name] = trail_pnl(fwd, entry, sign, sl, act, dist)
            for name, tp, sl in FIXED:
                rec[name] = fixed_pnl(fwd, entry, sign, tp, sl)
            rows.append(rec)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {d}: {exc}")

    out = pd.DataFrame(rows)
    out["year"] = pd.to_datetime(out["date"]).dt.year
    out.to_csv(OUT_DIR / "orb_trailing_pnl.csv", index=False)
    cols = [c for c, *_ in TRAILS] + [c for c, *_ in FIXED]
    print(f"\nEvents: {len(out)}  ($5/tick, commission {COMMISSION_TICKS}t)\n")

    for col in cols:
        print(f"=== {col} ===")
        print(f"{'year':>6} {'n':>5} {'t/mo':>5} {'WR%':>6} {'EVgr':>7} {'EVnet':>7} {'PF':>6} {'maxDD$':>8}")
        for y, g in out.groupby("year"):
            _row(g, col, str(y))
        _row(out, col, "TOTAL")
        print()


def _row(g, col, label):
    p = g[col].to_numpy()
    n = len(p)
    wins = p[p > 0].sum()
    losses = -p[p < 0].sum()
    wr = (p > 0).mean() * 100
    ev = p.mean()
    evnet = ev - COMMISSION_TICKS
    pf = wins / losses if losses else float("inf")
    # equity max drawdown in $ (1 contract), net of commission
    eq = np.cumsum((p - COMMISSION_TICKS) * TICK_USD)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq).max() if n else 0.0
    months = pd.to_datetime(g["date"]).dt.to_period("M").nunique()
    print(f"{label:>6} {n:>5} {n/max(months,1):>5.1f} {wr:>5.1f}% {ev:>7.1f} {evnet:>7.1f} {pf:>6.2f} {dd:>8.0f}")


if __name__ == "__main__":
    main()
