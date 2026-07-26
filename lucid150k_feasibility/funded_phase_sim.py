"""
The evaluation and the funded account are two different games.

policy_optimizer.py showed the evaluation can be won by variance: with zero
edge and bold sizing, P(pass) is about 26% per attempt and the median winning
path takes two days. There is no minimum-trading-day rule, so nothing stops
that.

The funded account is not the same game. Two rules block the same trick:

  consistency   the largest single profitable day may not exceed 40% of total
                profit (LucidPro funded, post 2025-11-28)
  LucidScale    once above the initial trail balance the loss limit becomes 60%
                of the highest end-of-day profit and ratchets up only

Consistency forces profit to be spread across several days, which forces more
exposure, and LucidScale caps give-back at 40% of the peak. Together they mean
a zero-edge trader cannot reach a payout by being lucky once.

This simulates the funded phase to price that claim.

Rule sources are web documentation, not the firm's dashboard. Treat the exact
LucidScale conversion point as an assumption flagged below, and re-verify before
any capital decision.
"""

import itertools
import json

import numpy as np

from progress import track

TICK_VALUE = 5.00
COST_TICKS = 4.0
STOP = 60
RR = 2.0
MLL = 4_500.0
SCALE_FRAC = 0.60          # LucidScale: floor = 60% of peak EOD profit
CONSISTENCY = 0.40         # largest day <= 40% of total profit
MIN_PAYOUT = 1_000.0
MAX_CONTRACTS = 10
DLL_BUFFER = 2_200.0
TRADES_PER_DAY = 2
HORIZON = 126             # ~6 months of sessions
N_PATHS = 20_000
SEED = 20260726
READING = "soft"   # "strict" or "soft"

EDGE_GRID = [0.0, 2.0, 4.0, 8.0, 12.0]
FRAC_GRID = [0.05, 0.10, 0.20, 0.35]


def wr_for_edge(edge):
    return (edge + STOP + COST_TICKS) / (STOP * (RR + 1))


def run(edge, frac, rng):
    wr = wr_for_edge(edge)
    win_t = STOP * RR - COST_TICKS
    loss_t = -(STOP + COST_TICKS)
    risk_per_contract = (STOP + COST_TICKS) * TICK_VALUE

    equity = np.zeros(N_PATHS)
    peak = np.zeros(N_PATHS)
    max_day = np.zeros(N_PATHS)         # largest single profitable day
    alive = np.ones(N_PATHS, dtype=bool)
    eligible = np.zeros(N_PATHS, dtype=bool)
    day_elig = np.full(N_PATHS, HORIZON + 1, dtype=np.int32)

    for day in range(1, HORIZON + 1):
        if not alive.any():
            break
        # floor. The web docs say the loss limit converts to "60% of the highest
        # end-of-day profit" once the account closes above the initial trail
        # balance, but not where that balance sits. Two readings are simulated:
        #   strict  the 60% lock binds from the first profitable close
        #   soft    the MLL trails to breakeven first, and the 60% lock only
        #           binds once peak profit exceeds the MLL itself
        if READING == "strict":
            floor = np.where(peak > 0.0,
                             np.maximum(peak - MLL, SCALE_FRAC * peak),
                             peak - MLL)
        else:
            floor = np.where(peak > MLL,
                             SCALE_FRAC * peak,
                             np.minimum(peak - MLL, 0.0))
        day_pnl = np.zeros(N_PATHS)

        for _ in range(TRADES_PER_DAY):
            room = np.maximum(equity - floor, 0.0)
            size = np.clip(np.floor(room * frac / risk_per_contract), 1, MAX_CONTRACTS)
            active = alive & (day_pnl > -DLL_BUFFER)
            if not active.any():
                break
            pnl = np.where(rng.random(N_PATHS) < wr, win_t, loss_t) * TICK_VALUE * size
            equity = np.where(active, equity + pnl, equity)
            day_pnl = np.where(active, day_pnl + pnl, day_pnl)
            hit = active & (equity <= floor)
            alive &= ~hit

        max_day = np.maximum(max_day, np.where(alive, day_pnl, 0.0))
        peak = np.maximum(peak, equity)

        ok = (alive & ~eligible & (equity >= MIN_PAYOUT)
              & (max_day <= CONSISTENCY * np.maximum(equity, 1e-9)))
        eligible |= ok
        day_elig = np.where(ok, day, day_elig)

    return dict(p_eligible=float(eligible.mean()),
                p_dead=float(1 - alive.mean()),
                median_days=float(np.median(day_elig[eligible])) if eligible.any() else float("nan"))


def main():
    print(f"floor reading: {READING}")
    rng = np.random.default_rng(SEED)
    rows = []
    combos = list(itertools.product(EDGE_GRID, FRAC_GRID))
    for edge, frac in track(combos, label="funded phase"):
        r = run(edge, frac, rng)
        r.update(edge_ticks=edge, frac=frac)
        rows.append(r)

    with open("FUNDED_RESULT.json", "w") as fh:
        json.dump(rows, fh, indent=1)

    print(f"\nfunded phase: stop {STOP}/{int(STOP*RR)}, {TRADES_PER_DAY} trades/day, "
          f"horizon {HORIZON} sessions, consistency {CONSISTENCY:.0%}, "
          f"LucidScale floor {SCALE_FRAC:.0%} of peak\n")
    print(f"{'edge(t)':>8} {'frac':>6} {'P(payout ok)':>13} {'P(blown)':>9} {'medDays':>8}")
    for edge in EDGE_GRID:
        for frac in FRAC_GRID:
            r = next(x for x in rows if x["edge_ticks"] == edge and x["frac"] == frac)
            print(f"{edge:>8.1f} {frac:>6.2f} {r['p_eligible']:>13.4f} "
                  f"{r['p_dead']:>9.4f} {r['median_days']:>8.0f}")

    print("\n--- best fraction per edge ---")
    for edge in EDGE_GRID:
        sub = [x for x in rows if x["edge_ticks"] == edge]
        b = max(sub, key=lambda x: x["p_eligible"])
        print(f"edge {edge:>5.1f}t -> frac {b['frac']:.2f}  "
              f"P(payout) {b['p_eligible']:.3f}  P(blown) {b['p_dead']:.3f}")


if __name__ == "__main__":
    main()
