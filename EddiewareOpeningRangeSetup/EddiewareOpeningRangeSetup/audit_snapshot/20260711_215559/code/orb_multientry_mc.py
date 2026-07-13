# -*- coding: utf-8 -*-
"""Raise frequency with the SAME thesis: take every upward cross of OR-high.

Instead of one first-breakout per day we arm a long on each upward pierce of the
09:30 OR high (first break, re-entries after price falls back inside, and
failed-down -> reversal-up). Same anti-absorption filter (drop top-tercile
vol_per_tick over the prior 30s), same trailing 40/20/40. After a trade exits we
re-arm only once price has traded back below OR-high, so entries are distinct.

Then per-year table + the Lucid pass-rate Monte Carlo on the richer stream.
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
COMMISSION_TICKS = 2.0
OR_START, OR_END, SCAN_START = "13:30:00", "13:31:00", "13:31:00"
SL, ACT, DIST = 40, 20, 40
MAX_ENTRIES_DAY = 4

DBN_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn_2")
OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")


def load_session(date):
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    return db.DBNStore.from_file(hits[0]).to_df()[["open", "high", "low", "close", "volume"]].sort_index()


def trail_exit(bars, start_i, entry):
    """Simulate a long from bar start_i; return (net_ticks, exit_i)."""
    stop = entry - SL * TICK
    best = entry
    activated = False
    hs = bars["high"].to_numpy(); ls = bars["low"].to_numpy(); cs = bars["close"].to_numpy()
    for i in range(start_i, len(bars)):
        if ls[i] <= stop:
            return (stop - entry) / TICK, i
        best = max(best, hs[i])
        if not activated and (best - entry) / TICK >= ACT:
            activated = True
        if activated:
            stop = max(stop, best - DIST * TICK)
    return (cs[-1] - entry) / TICK, len(bars) - 1


def day_entries(df):
    day = df.index[0].strftime("%Y-%m-%d")
    orw = df.between_time(OR_START, OR_END, inclusive="left")
    if orw.empty:
        return []
    or_high = float(orw["high"].max())
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")].reset_index()
    hs = post["high"].to_numpy(); ls = post["low"].to_numpy()
    vol = post["volume"].to_numpy(); clo = post["close"].to_numpy(); opn = post["open"].to_numpy()
    entries = []
    armed = True  # can enter when price is below or_high and then crosses up
    i = 0
    n = len(post)
    while i < n and len(entries) < MAX_ENTRIES_DAY:
        if armed and hs[i] > or_high:
            # entry at OR high on this upward cross
            entry = or_high
            # causal vol_per_tick over prior 30s
            lo = max(0, i - 30)
            w_vol = vol[lo:i].sum()
            w_rng = max((hs[lo:i].max() - ls[lo:i].min()) / TICK, 1.0) if i > lo else 1.0
            vpt = w_vol / w_rng
            net, xi = trail_exit(post, i, entry)
            entries.append({"date": day, "vpt": vpt, "net": net})
            # re-arm only after price returns below or_high
            armed = False
            i = xi + 1
        else:
            if not armed and hs[i] < or_high:  # back inside -> can arm again
                armed = True
            i += 1
    return entries


def main():
    dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    rows = []
    for d in track(dates, label="multi-entry ORB"):
        try:
            df = load_session(d)
            if df is None or df.empty:
                continue
            rows.extend(day_entries(df))
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {d}: {exc}")
    r = pd.DataFrame(rows)
    r["year"] = pd.to_datetime(r["date"]).dt.year
    vhi = r["vpt"].quantile(2/3)
    r_f = r[r["vpt"] <= vhi].copy()   # anti-absorption filter
    r.to_csv(OUT_DIR / "orb_multientry.csv", index=False)

    def year_table(sub, title):
        print(f"\n=== {title} ===")
        print(f"{'year':>6} {'n':>4} {'t/mo':>5} {'WR%':>6} {'EVnet':>7} {'PF':>6}")
        for y in sorted(sub["year"].unique()) + ["ALL"]:
            g = sub if y == "ALL" else sub[sub.year == y]
            v = g["net"].to_numpy()
            wins = v[v > 0].sum(); loss = -v[v < 0].sum()
            mo = pd.to_datetime(g["date"]).dt.to_period("M").nunique()
            print(f"{str(y):>6} {len(v):>4} {len(v)/max(mo,1):>5.1f} {(v>0).mean()*100:>5.1f}% "
                  f"{v.mean()-COMMISSION_TICKS:>7.1f} {wins/loss if loss else float('inf'):>6.2f}")

    year_table(r, "ALL upward crosses (no filter)")
    year_table(r_f, "ALL crosses + anti-absorption filter")

    total_mo = pd.to_datetime(r_f["date"]).dt.to_period("M").nunique()
    fmo = len(r_f) / total_mo
    print(f"\nFiltered frequency = {fmo:.1f} trades/mo (was 6.3 single-entry)")

    # ---- Monte Carlo pass rate on filtered stream ----
    series = r_f.sort_values("date")["net"].to_numpy() - COMMISSION_TICKS
    RNG = np.random.default_rng(11); BLOCK = 8; NS = 20000

    def block_boot(n):
        out = []
        while len(out) < n:
            i = RNG.integers(0, len(series))
            out.extend(series[i:i + BLOCK])
        return np.asarray(out[:n]) * TICK_USD

    def sim(n_trades, size, target, dd):
        seq = block_boot(n_trades) * size
        eq = peak = 0.0
        for x in seq:
            eq += x; peak = max(peak, eq)
            if peak - eq >= dd:
                return 0
            if eq >= target:
                return 1
        return 0

    n_trades = int(round(fmo * 3))
    print(f"\n=== Lucid MC (multi-entry, {n_trades} trades/3mo) ===")
    for acc, (target, dd) in {"100k": (6000, 3000), "150k": (9000, 4500)}.items():
        best = (0, -1)
        for size in range(1, 16):
            pp = np.mean([sim(n_trades, size, target, dd) for _ in range(NS)]) * 100
            if pp > best[1]:
                best = (size, pp)
        print(f"  {acc}: best size {best[0]} ct -> P(pass 3mo) = {best[1]:.1f}%")


if __name__ == "__main__":
    main()
