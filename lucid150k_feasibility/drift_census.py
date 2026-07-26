"""
Unconditional drift census on NQ RTH.

The trigger census returned gross EV ~= 0 on all 240 combinations: at 1-second
resolution the price is a martingale and every bracket just pays the 4-tick
cost. Before abandoning price-only information entirely, this asks the simplest
possible remaining question, with no trigger at all:

    entering LONG (or SHORT) at a fixed time of day, every day, with a fixed
    bracket - is there any window of the session with a real directional drift?

If the whole map is flat, then no amount of timing logic built on OHLCV alone
can fund the account, and the search has to move to information that is not in
the bar (order flow, book, cross-instrument state).

One trade per day per cell, DEV only, 4-tick cost, stop wins intrabar ties.
"""

import json
import time

import numpy as np

from progress import track

CACHE = "nq_1s_cache.npz"
COST_TICKS = 4
DEV_START, DEV_END = "2022-04-25", "2023-12-31"

BUCKET_MIN = 15                                   # entry every 15 minutes
S_GRID = [20, 30, 40, 60]
RR_GRID = [1.0, 2.0]


def trade(close, high, low, i, direction, s, rr):
    entry = close[i]
    tgt = int(round(s * rr))
    if direction > 0:
        sl_hit = low[i + 1:] <= entry - s
        tp_hit = high[i + 1:] >= entry + tgt
    else:
        sl_hit = high[i + 1:] >= entry + s
        tp_hit = low[i + 1:] <= entry - tgt
    j_sl = int(np.argmax(sl_hit)) if sl_hit.any() else 10**9
    j_tp = int(np.argmax(tp_hit)) if tp_hit.any() else 10**9
    if j_sl == 10**9 and j_tp == 10**9:
        return int(direction * (close[-1] - entry)) - COST_TICKS
    return (-s - COST_TICKS) if j_sl <= j_tp else (tgt - COST_TICKS)


def main():
    t0 = time.time()
    z = np.load(CACHE, allow_pickle=True)
    days = z["days"].astype(str)
    offsets = z["offsets"]
    close, high, low = z["close"], z["high"], z["low"]

    idx = np.flatnonzero((days >= DEV_START) & (days <= DEV_END))
    sessions = []
    for i in idx:
        a, b = offsets[i], offsets[i + 1]
        sessions.append((days[i], close[a:b], high[a:b], low[a:b]))
    print(f"DEV sessions: {len(sessions)}")

    # entry offsets in seconds from each session's own first bar (DST-safe)
    entry_offsets = list(range(0, 6 * 3600 + 1, BUCKET_MIN * 60))
    cells = [(off, d, s, rr) for off in entry_offsets
             for d in (1, -1) for s in S_GRID for rr in RR_GRID]
    print(f"cells: {len(cells)}  (entry windows: {len(entry_offsets)})\n")

    rows = []
    for off, direction, s, rr in track(cells, label="drift census"):
        pnls = []
        for day, c_, h_, l_ in sessions:
            if off + 60 >= len(c_):
                continue
            pnls.append(trade(c_, h_, l_, off, direction, s, rr))
        if len(pnls) < 100:
            continue
        arr = np.array(pnls, dtype=float)
        wins = arr > 0
        gl = -arr[arr < 0].sum()
        rows.append(dict(
            entry_min=off // 60, dir="LONG" if direction > 0 else "SHORT",
            S=s, RR=rr, n=len(arr),
            wr=round(float(wins.mean()), 4),
            ev_ticks=round(float(arr.mean()), 3),
            ev_gross=round(float(arr.mean()) + COST_TICKS, 3),
            pf=round(float(arr[arr > 0].sum() / gl), 3) if gl > 0 else None,
            t_stat=round(float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), 2),
        ))

    with open("DRIFT_CENSUS_DEV.json", "w") as fh:
        json.dump(rows, fh, indent=1)

    rows.sort(key=lambda r: -r["ev_ticks"])
    print(f"\ncells: {len(rows)}   positive net EV: "
          f"{sum(1 for r in rows if r['ev_ticks'] > 0)}   "
          f"EV >= +6t: {sum(1 for r in rows if r['ev_ticks'] >= 6)}   "
          f"[{time.time()-t0:.1f}s]")

    print("\n--- top 15 by net EV ---")
    print(f"{'entry(min)':>10} {'dir':>6} {'S':>3} {'RR':>4} {'n':>4} {'WR':>6} "
          f"{'EVnet':>7} {'EVgross':>8} {'PF':>6} {'t':>6}")
    for r in rows[:15]:
        print(f"{r['entry_min']:>10} {r['dir']:>6} {r['S']:>3} {r['RR']:>4.1f} "
              f"{r['n']:>4} {r['wr']:>6.3f} {r['ev_ticks']:>7.2f} "
              f"{r['ev_gross']:>8.2f} {str(r['pf']):>6} {r['t_stat']:>6.2f}")

    gross = np.array([r["ev_gross"] for r in rows])
    print(f"\ngross EV across all cells: mean {gross.mean():+.2f} "
          f"p5 {np.percentile(gross,5):+.2f} median {np.median(gross):+.2f} "
          f"p95 {np.percentile(gross,95):+.2f}")
    ts = np.array([abs(r["t_stat"]) for r in rows])
    print(f"|t| > 2 in {int((ts > 2).sum())}/{len(ts)} cells "
          f"({100*(ts>2).mean():.1f}%; ~5% expected under the null)")
    print(f"total elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
