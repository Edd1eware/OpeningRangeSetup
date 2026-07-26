"""
Is the V14 preregistered gate even sufficient to pass the account?

V14 freezes: n>=50, frequency >=2.0 trades/MONTH, EV >+0.12R, PF >1.35,
target 2R, stop 40 ticks. This script takes a strategy that passes those gates
exactly at the threshold and asks what it does to a LucidPro 150K evaluation
over 63 sessions, at every legal size.

If the answer is "nothing", then V14 can succeed as science and still be
useless for the stated objective, and the gate is misaligned with the goal.
"""

import numpy as np

TICK_VALUE = 5.00
COST_TICKS = 4.0
TARGET = 9_000.0
MLL = 4_500.0
FLOOR_LOCK = 100.0
SESSIONS = 63
N_PATHS = 20_000
SEED = 20260726

# V14 gate-minimum strategy
STOP_TICKS = 40
RR = 2.0
FREQ_PER_MONTH = 2.0
TRADES_PER_SESSION = FREQ_PER_MONTH * 3 / SESSIONS      # 3 months of sessions
# PF 1.35 at 2R implies win rate 1.35 / (2 + 1.35)
WR = 1.35 / 3.35


def run(contracts, rng):
    win = (STOP_TICKS * RR - COST_TICKS) * TICK_VALUE * contracts
    loss = -(STOP_TICKS + COST_TICKS) * TICK_VALUE * contracts
    equity = np.zeros(N_PATHS)
    peak = np.zeros(N_PATHS)
    alive = np.ones(N_PATHS, dtype=bool)
    passed = np.zeros(N_PATHS, dtype=bool)
    breached = np.zeros(N_PATHS, dtype=bool)

    for _ in range(SESSIONS):
        floor = np.minimum(peak - MLL, FLOOR_LOCK)
        n = np.minimum(rng.poisson(TRADES_PER_SESSION, N_PATHS), 3)
        for k in range(3):
            active = alive & (n > k)
            if not active.any():
                continue
            out = np.where(rng.random(N_PATHS) < WR, win, loss)
            equity = np.where(active, equity + out, equity)
            hit = active & (equity <= floor)
            breached |= hit
            alive &= ~hit
        won = alive & (equity >= TARGET)
        passed |= won
        alive &= ~won
        peak = np.maximum(peak, equity)

    return passed.mean(), breached.mean(), equity


def main():
    rng = np.random.default_rng(SEED)
    expected_trades = TRADES_PER_SESSION * SESSIONS
    ev_r = WR * RR - (1 - WR)
    print(f"V14 gate-minimum strategy: WR={WR:.3f} RR={RR} stop={STOP_TICKS}t "
          f"PF=1.35 EV={ev_r:.3f}R")
    print(f"expected trades in {SESSIONS} sessions: {expected_trades:.1f}")
    print(f"expected gross R accumulated: {expected_trades * ev_r:.2f}R\n")
    print(f"{'ctr':>4} {'risk$/trade':>12} {'P(pass)':>8} {'P(breach)':>10} {'median $':>10}")
    for c in range(1, 11):
        p_pass, p_breach, eq = run(c, rng)
        risk = (STOP_TICKS + COST_TICKS) * TICK_VALUE * c
        print(f"{c:>4} {risk:>12.0f} {p_pass:>8.4f} {p_breach:>10.4f} {np.median(eq):>10.0f}")

    print("\nR needed to reach +$9,000 at a given per-trade risk:")
    for c in (1, 2, 3, 5, 10):
        risk = (STOP_TICKS + COST_TICKS) * TICK_VALUE * c
        print(f"  {c:>2} contracts -> risk ${risk:>5.0f}/trade -> need {TARGET / risk:>5.1f}R net")


if __name__ == "__main__":
    main()
