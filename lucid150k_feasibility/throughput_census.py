"""
Throughput census on NQ RTH 1-second bars.

Doc 060 established the real requirement: >=2 trades/day at >= +6 ticks of net
EV, with R:R >= 1:1. Thirteen hand-crafted single-shot hypotheses have failed,
so instead of proposing a fourteenth this script measures the whole surface of a
simple parameterized trigger family and asks a falsifiable question:

    does ANY corner of this surface reach the throughput the account needs?

A negative answer over the full grid is a real result: it says the mechanism
family cannot fund the evaluation, no matter how the thresholds are tuned.

Trigger family (causal, no look-ahead):
    at second t, move = close[t] - close[t-W] in ticks
    if |move| >= K, take a position at close[t]
        CONT -> in the direction of the move
        FADE -> against it
    bracket: stop S ticks, target S * RR ticks
    one position at a time; no new entry until the previous trade exits
    entries stop at 15:30 NY, anything open is closed at the session's last bar

Costs: 4 ticks per round turn, charged to every trade.
Stop is evaluated before target whenever a single 1-second bar spans both.

Era policy: this pass reads DEV only (2022-04-25 .. 2023-12-31). The 2024
pseudo-validation and the 2025-2026 stress stay closed until a candidate is
frozen.
"""

import itertools
import json
import time

import numpy as np

from progress import track

CACHE = "nq_1s_cache.npz"
COST_TICKS = 4
DEV_START, DEV_END = "2022-04-25", "2023-12-31"
LAST_ENTRY_SEC_OFFSET = 6 * 3600          # no new entries after 6h into the session

W_GRID = [30, 60, 180, 300]               # lookback seconds
K_GRID = [10, 15, 20, 30, 40]             # trigger size in ticks
S_GRID = [20, 30, 40]                     # stop in ticks
RR_GRID = [1.0, 2.0]
DIR_GRID = ["CONT", "FADE"]


def simulate_day(close, high, low, sec, w, k, s, rr, is_cont):
    """Return list of (net_ticks, is_win) for one session."""
    n = len(close)
    if n <= w + 10:
        return []
    move = np.empty(n, dtype=np.int32)
    move[:w] = 0
    move[w:] = close[w:] - close[:-w]
    fire = np.abs(move) >= k
    last_entry = sec[0] + LAST_ENTRY_SEC_OFFSET

    target_ticks = int(round(s * rr))
    out = []
    i = w
    while i < n - 1:
        if not fire[i] or sec[i] > last_entry:
            i += 1
            continue
        direction = np.sign(move[i])
        if not is_cont:
            direction = -direction
        if direction == 0:
            i += 1
            continue

        entry = close[i]
        if direction > 0:
            tp, sl = entry + target_ticks, entry - s
            hit_sl = low[i + 1:] <= sl
            hit_tp = high[i + 1:] >= tp
        else:
            tp, sl = entry - target_ticks, entry + s
            hit_sl = high[i + 1:] >= sl
            hit_tp = low[i + 1:] <= tp

        j_sl = int(np.argmax(hit_sl)) if hit_sl.any() else 10**9
        j_tp = int(np.argmax(hit_tp)) if hit_tp.any() else 10**9

        if j_sl == 10**9 and j_tp == 10**9:
            # closed at the last bar of the session
            pnl = int(direction * (close[-1] - entry)) - COST_TICKS
            out.append((pnl, pnl > 0))
            break
        # stop wins ties inside the same 1-second bar
        if j_sl <= j_tp:
            out.append((-s - COST_TICKS, False))
            i = i + 1 + j_sl
        else:
            out.append((target_ticks - COST_TICKS, True))
            i = i + 1 + j_tp
        i += 1
    return out


def main():
    t0 = time.time()
    z = np.load(CACHE, allow_pickle=True)
    days = z["days"].astype(str)
    offsets = z["offsets"]
    close, high, low, sec = z["close"], z["high"], z["low"], z["sec"]

    mask = (days >= DEV_START) & (days <= DEV_END)
    idx = np.flatnonzero(mask)
    print(f"cache: {len(days)} days total, DEV subset: {len(idx)} days "
          f"[{days[idx[0]]} .. {days[idx[-1]]}]")

    # slice DEV days once
    dev = []
    for i in idx:
        a, b = offsets[i], offsets[i + 1]
        dev.append((days[i], close[a:b], high[a:b], low[a:b], sec[a:b]))

    combos = list(itertools.product(W_GRID, K_GRID, S_GRID, RR_GRID, DIR_GRID))
    print(f"combos: {len(combos)}   trade sims: {len(combos) * len(dev):,}\n")

    results = []
    for w, k, s, rr, d in track(combos, label="throughput census"):
        is_cont = d == "CONT"
        pnls, wins, per_year = [], 0, {}
        for day, c_, h_, l_, sc_ in dev:
            trades = simulate_day(c_, h_, l_, sc_, w, k, s, rr, is_cont)
            if not trades:
                continue
            yr = day[:4]
            acc = per_year.setdefault(yr, [0, 0.0])
            for pnl, win in trades:
                pnls.append(pnl)
                wins += int(win)
                acc[0] += 1
                acc[1] += pnl
        n = len(pnls)
        if n == 0:
            continue
        arr = np.array(pnls, dtype=np.float64)
        gross_win = arr[arr > 0].sum()
        gross_loss = -arr[arr < 0].sum()
        results.append(dict(
            W=w, K=k, S=s, RR=rr, dir=d,
            n=n,
            trades_per_day=round(n / len(dev), 3),
            wr=round(wins / n, 4),
            ev_ticks=round(float(arr.mean()), 3),
            pf=round(float(gross_win / gross_loss), 3) if gross_loss > 0 else None,
            ticks_per_session=round(float(arr.sum() / len(dev)), 3),
            years={y: dict(n=v[0], ev=round(v[1] / v[0], 3)) for y, v in per_year.items()},
        ))

    with open("CENSUS_DEV_RESULT.json", "w") as fh:
        json.dump(dict(params=dict(cost_ticks=COST_TICKS, dev=[DEV_START, DEV_END],
                                   days=len(dev)), rows=results), fh, indent=1)

    ok = [r for r in results if r["trades_per_day"] >= 2.0 and r["ev_ticks"] >= 6.0]
    print(f"\ncombos with data: {len(results)}   meeting DEV throughput bar "
          f"(>=2 tr/day AND >= +6 ticks EV): {len(ok)}   [{time.time()-t0:.1f}s]")

    print("\n--- top 20 by ticks/session ---")
    print(f"{'W':>4} {'K':>3} {'S':>3} {'RR':>4} {'dir':>5} {'n':>6} {'tr/day':>7} "
          f"{'WR':>6} {'EVt':>7} {'PF':>6} {'t/sess':>7}")
    for r in sorted(results, key=lambda r: -r["ticks_per_session"])[:20]:
        print(f"{r['W']:>4} {r['K']:>3} {r['S']:>3} {r['RR']:>4.1f} {r['dir']:>5} "
              f"{r['n']:>6} {r['trades_per_day']:>7.2f} {r['wr']:>6.3f} "
              f"{r['ev_ticks']:>7.2f} {str(r['pf']):>6} {r['ticks_per_session']:>7.2f}")

    evs = np.array([r["ev_ticks"] for r in results])
    print(f"\nsurface EV distribution (ticks/trade): min {evs.min():.2f} "
          f"p25 {np.percentile(evs,25):.2f} median {np.median(evs):.2f} "
          f"p75 {np.percentile(evs,75):.2f} p95 {np.percentile(evs,95):.2f} "
          f"max {evs.max():.2f}")
    print(f"total elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
