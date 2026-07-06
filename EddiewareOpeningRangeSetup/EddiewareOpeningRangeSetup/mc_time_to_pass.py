# -*- coding: utf-8 -*-
"""How long to pass Lucid at a given WR, R:R 1:1 (60/60), contract caps enforced.

Trades are Bernoulli at win-rate WR: gross win +60t, gross loss -60t, minus 2t
round-trip commission -> net win +58t, net loss -62t. $5/tick. 4 trades/month.
Trailing drawdown modelled on the closed-trade equity peak (Lucid also trails
intraday open PnL, so real bust risk is a bit HIGHER than shown).

Caps: 100k -> max 6 contracts, 150k -> max 10 contracts.
Reports, per size: P(pass eventually), P(pass within 3mo / 6mo), P(bust),
and the median trades & months to pass among successful runs.
"""

from __future__ import annotations

import numpy as np

TICK_USD = 5.0
WIN_T, LOSS_T = 58.0, -62.0          # net of 2t commission on a 60/60 bracket
TRADES_PER_MONTH = 4.0
MAX_TRADES = 400                     # ~100 months cap for the sim
N_SIMS = 40000
RNG = np.random.default_rng(7)

ACCOUNTS = {  # name: (target$, trailingDD$, maxContracts)
    "100k": (6000.0, 3000.0, 6),
    "150k": (9000.0, 4500.0, 10),
}


def run(wr, size, target, dd):
    """One eval attempt -> ('pass'|'bust'|'timeout', n_trades_used)."""
    eq = peak = 0.0
    for k in range(1, MAX_TRADES + 1):
        win = RNG.random() < wr
        eq += (WIN_T if win else LOSS_T) * size * TICK_USD
        peak = max(peak, eq)
        if peak - eq >= dd:
            return "bust", k
        if eq >= target:
            return "pass", k
    return "timeout", MAX_TRADES


def summarize(wr):
    print(f"\n{'='*66}\nWR = {wr*100:.1f}%   (R:R 1:1, 60/60, {TRADES_PER_MONTH:.0f} trades/mo, "
          f"EV/trade = {wr*WIN_T+(1-wr)*LOSS_T:+.1f}t)\n{'='*66}")
    for acc, (target, dd, cap) in ACCOUNTS.items():
        print(f"\n  Lucid {acc}: target +${target:.0f}, trailing DD ${dd:.0f}, MAX {cap} ct")
        print(f"  {'size':>4} {'pass%':>6} {'<=3mo':>6} {'<=6mo':>6} {'bust%':>6} "
              f"{'medTrades':>9} {'medMonths':>9}")
        for size in range(1, cap + 1):
            outs = np.empty(N_SIMS, dtype=object)
            ks = np.empty(N_SIMS)
            for i in range(N_SIMS):
                o, k = run(wr, size, target, dd)
                outs[i] = o; ks[i] = k
            passed = outs == "pass"
            p_pass = passed.mean() * 100
            kp = ks[passed]
            in3 = ((passed) & (ks <= 3 * TRADES_PER_MONTH)).mean() * 100
            in6 = ((passed) & (ks <= 6 * TRADES_PER_MONTH)).mean() * 100
            bust = (outs == "bust").mean() * 100
            med_tr = np.median(kp) if kp.size else float("nan")
            med_mo = med_tr / TRADES_PER_MONTH if kp.size else float("nan")
            print(f"  {size:>4} {p_pass:>5.1f}% {in3:>5.1f}% {in6:>5.1f}% {bust:>5.1f}% "
                  f"{med_tr:>9.0f} {med_mo:>9.1f}")


if __name__ == "__main__":
    summarize(0.594)   # best year (2025) — optimistic
    summarize(0.520)   # mild edge
    summarize(0.480)   # 4-year average — realistic
