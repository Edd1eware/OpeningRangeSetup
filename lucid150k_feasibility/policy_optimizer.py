"""
Optimal sizing policy under the LucidPro 150K rule set, given the measured edge.

Everything measured in docs 060 and 061 says the directional edge available in
this data is statistically zero. That does not make the evaluation a coin flip
with fixed odds, because the rule set itself is asymmetric:

    floor = min(peak_EOD - 4500, +100)

The floor trails the peak until the peak reaches +4,600, and from then on it is
pinned at +100 forever. So the account has two regimes:

    phase 1  equity below +4,600: a 4,500 trailing stop is chasing you
    phase 2  equity above +4,600: you may give back everything down to +100

Phase 2 is enormously safer than phase 1. That asymmetry is structural, it comes
from the firm's rules rather than from the market, and it means the size policy
that maximises P(pass) is not the one that maximises expected profit.

This sweeps size policies of the form:

    contracts = clip( floor( (equity - floor) * f / risk_per_contract ), 1, 10 )

with a separate fraction f1 while in phase 1 and f2 in phase 2, over a range of
per-trade edges expressed in ticks, so the answer degrades gracefully if a small
real edge is ever found.
"""

import itertools
import json
import time

import numpy as np

from progress import track

TICK_VALUE = 5.00
COST_TICKS = 4.0
TARGET = 9_000.0
MLL = 4_500.0
FLOOR_LOCK = 100.0
DLL_BUFFER = 2_200.0
SESSIONS = 63
MAX_CONTRACTS = 10
N_PATHS = 20_000
SEED = 20260726

STOP = 60                      # ticks
RR = 2.0
EDGE_GRID = [-2.0, 0.0, 2.0, 4.0, 8.0]        # net ticks per trade
F1_GRID = [0.15, 0.25, 0.35, 0.50, 0.75, 1.00]
F2_GRID = [0.05, 0.10, 0.20, 0.35, 0.50]
TRADES_PER_DAY = 2


def wr_for_edge(edge):
    """Win rate that produces the requested net EV at the fixed bracket."""
    return (edge + STOP + COST_TICKS) / (STOP * (RR + 1))


def run(edge, f1, f2, rng):
    wr = wr_for_edge(edge)
    win_t = STOP * RR - COST_TICKS
    loss_t = -(STOP + COST_TICKS)
    risk_per_contract = (STOP + COST_TICKS) * TICK_VALUE

    equity = np.zeros(N_PATHS)
    peak = np.zeros(N_PATHS)
    alive = np.ones(N_PATHS, dtype=bool)
    passed = np.zeros(N_PATHS, dtype=bool)
    breached = np.zeros(N_PATHS, dtype=bool)
    day_passed = np.full(N_PATHS, SESSIONS + 1, dtype=np.int32)

    for day in range(1, SESSIONS + 1):
        if not alive.any():
            break
        floor = np.minimum(peak - MLL, FLOOR_LOCK)
        day_pnl = np.zeros(N_PATHS)

        for _ in range(TRADES_PER_DAY):
            room = np.maximum(equity - floor, 0.0)
            frac = np.where(peak >= MLL + FLOOR_LOCK, f2, f1)
            size = np.floor(room * frac / risk_per_contract)
            size = np.clip(size, 1, MAX_CONTRACTS)

            active = alive & (day_pnl > -DLL_BUFFER)
            if not active.any():
                break
            win = rng.random(N_PATHS) < wr
            pnl = np.where(win, win_t, loss_t) * TICK_VALUE * size
            equity = np.where(active, equity + pnl, equity)
            day_pnl = np.where(active, day_pnl + pnl, day_pnl)

            hit = active & (equity <= floor)
            breached |= hit
            alive &= ~hit

        won = alive & (equity >= TARGET) & ~passed
        passed |= won
        day_passed = np.where(won, day, day_passed)
        alive &= ~won
        peak = np.maximum(peak, equity)

    med = float(np.median(day_passed[passed])) if passed.any() else float("nan")
    return passed.mean(), breached.mean(), med


def main():
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    combos = list(itertools.product(EDGE_GRID, F1_GRID, F2_GRID))
    rows = []
    for edge, f1, f2 in track(combos, label="policy sweep"):
        p_pass, p_breach, med = run(edge, f1, f2, rng)
        rows.append(dict(edge_ticks=edge, f1=f1, f2=f2,
                         p_pass=round(float(p_pass), 4),
                         p_breach=round(float(p_breach), 4),
                         median_days=med))

    with open("POLICY_RESULT.json", "w") as fh:
        json.dump(dict(params=dict(stop=STOP, rr=RR, cost=COST_TICKS,
                                   trades_per_day=TRADES_PER_DAY,
                                   n_paths=N_PATHS, seed=SEED), rows=rows), fh, indent=1)

    print(f"\nbracket: stop {STOP}t / target {int(STOP*RR)}t, {TRADES_PER_DAY} trades/day, "
          f"{N_PATHS:,} paths\n")
    print("--- best policy per edge level ---")
    print(f"{'edge(t)':>8} {'WR':>6} {'f1':>5} {'f2':>5} {'P(pass)':>8} "
          f"{'P(breach)':>10} {'medDays':>8}")
    for edge in EDGE_GRID:
        sub = [r for r in rows if r["edge_ticks"] == edge]
        best = max(sub, key=lambda r: r["p_pass"])
        print(f"{edge:>8.1f} {wr_for_edge(edge):>6.3f} {best['f1']:>5.2f} {best['f2']:>5.2f} "
              f"{best['p_pass']:>8.4f} {best['p_breach']:>10.4f} {best['median_days']:>8.0f}")

    print("\n--- zero-edge surface: P(pass) by (f1, f2) ---")
    print(f"{'f1\\f2':>7} " + " ".join(f"{f2:>7.2f}" for f2 in F2_GRID))
    for f1 in F1_GRID:
        cells = []
        for f2 in F2_GRID:
            r = next(r for r in rows if r["edge_ticks"] == 0.0
                     and r["f1"] == f1 and r["f2"] == f2)
            cells.append(f"{r['p_pass']:>7.3f}")
        print(f"{f1:>7.2f} " + " ".join(cells))

    print(f"\ntotal elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
