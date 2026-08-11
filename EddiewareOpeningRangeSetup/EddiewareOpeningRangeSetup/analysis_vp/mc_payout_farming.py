"""Monte Carlo of Lucid $150k payout FARMING with the empirical daily P&L.

Objective (per user): pass -> extract max payouts -> if burned, repeat. Metric =
expected payouts / account and $ EV per account fee, NOT never-break.

Lucid $150k rules used:
  - profit target to pass    = $9,000
  - EOD trailing drawdown    = $4,500 (locks static at +$4,500 profit once passed)
  - min profitable days      = 5 before a payout
  - min payout               = $500
  - split                    = 100% first $10,000 lifetime, then 90/10
  - one-time account fee     = $370 (LucidPro 150k)

Model choices (documented; conservative where unsure):
  - day P&L bootstrapped i.i.d. from the empirical pool (daily_ticks_pool.npy).
    CAVEAT: ignores autocorrelation/regime; pool is 2025-partial (good stretch,
    excludes the weak 2023/24 that Lucid's DST-only window never sampled).
  - EOD-only drawdown check (matches Lucid).
  - funded farming: withdraw everything above the static floor whenever
    withdrawable >= $500 and >=5 profitable days accrued since last payout.
  - burned account -> pay fee, start a fresh one. Horizon = fixed trading days.

Usage:
    python -u mc_payout_farming.py                 # sweep 3..10 contracts
    python -u mc_payout_farming.py --contracts 6   # single size, verbose
"""

from __future__ import annotations

import argparse
import numpy as np

TICK_USD = 5.0          # NQ mini $/tick
TARGET = 9000.0
DD = 4500.0
FEE = 370.0
PAYOUT_MIN = 500.0
MIN_PROFIT_DAYS = 5
SPLIT_100_CAP = 10000.0  # first $10k lifetime at 100%, then 90%
SPLIT_AFTER = 0.90


def sim_one_horizon(days_pool, contracts, horizon, rng):
    """Simulate one trader over `horizon` trading days, farming payouts across
    however many accounts they burn. Returns (net_payout_usd, n_payouts, n_burns,
    passed_first)."""
    usd_per_tick = contracts * TICK_USD
    lifetime_gross = 0.0   # for the 100%/90% split
    net_payout = 0.0
    n_payouts = 0
    n_burns = 0
    passed_first = False
    fees_paid = FEE        # buy the first account

    # per-account state
    profit = 0.0
    peak = 0.0
    funded = False
    prof_days = 0

    samples = rng.integers(0, len(days_pool), size=horizon)
    for k in range(horizon):
        day = days_pool[samples[k]] * usd_per_tick
        profit += day
        if day > 0:
            prof_days += 1

        # EOD trailing floor
        if profit > peak:
            peak = profit
        floor = min(peak, TARGET) - DD   # locks at +4500 once peak>=target

        # burn?
        if profit <= floor:
            n_burns += 1
            fees_paid += FEE
            profit = 0.0; peak = 0.0; funded = False; prof_days = 0
            continue

        # pass?
        if not funded and profit >= TARGET:
            funded = True
            passed_first = True
            prof_days = 0   # start counting the funded cycle

        # farm payout
        if funded:
            withdrawable = profit - (TARGET - DD)   # keep the static floor (+4500)
            if withdrawable >= PAYOUT_MIN and prof_days >= MIN_PROFIT_DAYS:
                # apply lifetime split
                g = withdrawable
                at100 = max(0.0, min(g, SPLIT_100_CAP - lifetime_gross))
                at90 = g - at100
                take = at100 * 1.0 + at90 * SPLIT_AFTER
                lifetime_gross += g
                net_payout += take
                n_payouts += 1
                profit -= withdrawable   # withdraw down to the floor
                peak = profit
                prof_days = 0

    return net_payout - fees_paid, n_payouts, n_burns, passed_first, fees_paid


def run(days_pool, contracts, horizon, n_sims, rng):
    net = np.empty(n_sims); pays = np.empty(n_sims); burns = np.empty(n_sims)
    passed = np.empty(n_sims); fees = np.empty(n_sims)
    for i in range(n_sims):
        net[i], pays[i], burns[i], passed[i], fees[i] = sim_one_horizon(
            days_pool, contracts, horizon, rng)
    return net, pays, burns, passed, fees


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="daily_ticks_pool.npy")
    ap.add_argument("--contracts", type=int, default=None, help="single size (else sweep 3..10)")
    ap.add_argument("--horizon", type=int, default=252, help="trading days per trader")
    ap.add_argument("--sims", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    pool = np.load(args.pool)
    rng = np.random.default_rng(args.seed)
    print(f"Pool: {len(pool)} días | media {pool.mean():+.2f} t/día | std {pool.std():.1f} | "
          f"WR día {(pool>0).mean():.3f}")
    print(f"Reglas Lucid $150k: pass ${TARGET:.0f} | DD ${DD:.0f} EOD | fee ${FEE:.0f} | "
          f"min5díasProf | split 100%<${SPLIT_100_CAP:.0f} luego 90%")
    print(f"Horizonte {args.horizon} días (~1 año pace) | sims {args.sims:,}\n")

    sizes = [args.contracts] if args.contracts else [3, 4, 5, 6, 7, 8, 9, 10]
    hdr = ["cont", "$/día_ev", "P(pasar)", "payouts_med", "payouts_prom",
           "burns_prom", "$neto_prom", "$neto_P50", "$neto_P5", "P($neto>0)"]
    print(" | ".join(f"{h:>11}" for h in hdr))
    for c in sizes:
        net, pays, burns, passed, fees = run(pool, c, args.horizon, args.sims, rng)
        row = [
            c,
            f"{pool.mean()*c*TICK_USD:+.0f}",
            f"{passed.mean():.2f}",
            f"{np.median(pays):.0f}",
            f"{pays.mean():.1f}",
            f"{burns.mean():.1f}",
            f"{net.mean():+.0f}",
            f"{np.percentile(net,50):+.0f}",
            f"{np.percentile(net,5):+.0f}",
            f"{(net>0).mean():.2f}",
        ]
        print(" | ".join(f"{str(v):>11}" for v in row))

    print("\nCAVEAT: pool = 2025-parcial (tramo bueno, excluye 2023/24). Bootstrap i.i.d "
          "(ignora autocorrelación/régimen). Cifras PRELIMINARES hasta cerrar la corrida 246.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
