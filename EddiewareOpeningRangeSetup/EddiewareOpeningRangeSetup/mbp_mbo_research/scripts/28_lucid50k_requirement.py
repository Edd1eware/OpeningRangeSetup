"""How much edge does the Lucid 50K evaluation actually require?

Script 19 answered this for the 100K. The 50K is NOT a scaled copy: its target
and drawdown are $3,000 / $2,000, a ratio of 1.5, against the 100K's
$6,000 / $3,000, a ratio of 2.0. A tighter ratio is HARDER, not easier, so the
100K numbers cannot be carried over.

This costs nothing to run and it is what decides whether any further Databento
spend is justified, because it converts "is there an edge" into the number that
actually matters: the win rate at which passing stops being a coin flip.

Rules as modelled (LucidFlex 50K)
---------------------------------
    profit target     +$3,000 -> balance $53,000
    trailing drawdown  $2,000, trailing on END-OF-DAY equity
    drawdown lock      once balance reaches $52,100 the floor fixes at $50,100
    consistency        no single day may exceed 50% of total profit
    daily loss limit   $1,200 (LucidPro only; modelled as a switch)

The trailing EOD drawdown is the rule a static-drawdown model gets wrong, and
it gets it wrong in the dangerous direction: once the account is up, the floor
has followed it, so giving back is fatal in a way a static floor is not. The
floor only moves at the close, but a breach INTRADAY still ends the account,
so both are enforced here.

What is NOT modelled, and all of it makes reality worse
-------------------------------------------------------
* Trades within a day are independent, which they are not.
* Fills are at the bracket. Real stop slippage is worse than the flat cost.
* No scaling plan, no inactivity rule, no news restriction.
* The consistency rule is checked only at the moment the target is reached.
So every number below is an OPTIMISTIC bound on the real pass probability.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from progress import track

NQ_TICK_USD = 5.0
MNQ_TICK_USD = 0.50
COST_TICKS = 1.8            # round trip, spread + commission, in ticks

START = 50_000.0
TARGET = 53_000.0
DD = 2_000.0
LOCK_AT = 52_100.0
LOCK_FLOOR = 50_100.0
CONSISTENCY = 0.50
MAX_DAYS = 120
N_SIM = 20_000
SEED = 20261013

GRID_K = (10, 20, 40, 60, 80, 100, 150)
GRID_WR = (0.50, 0.51, 0.52, 0.53, 0.55, 0.58)
GRID_TPD = (1, 2, 4)


def simulate(k_ticks: int, wr: float, trades_per_day: int, tick_usd: float,
             n_contracts: int, daily_loss_usd: float | None,
             n_sim: int, rng: np.random.Generator) -> dict:
    """Monte Carlo the evaluation day by day, all paths advanced in lockstep.

    One trade is +k or -k ticks before cost; cost is charged on every trade
    whatever the outcome. Equity is tracked INSIDE the day because the floor
    can be breached intraday even though it only MOVES at the close.
    """
    win_usd = k_ticks * tick_usd * n_contracts
    cost_usd = COST_TICKS * tick_usd * n_contracts

    bal = np.full(n_sim, START)
    floor = np.full(n_sim, START - DD)
    locked = np.zeros(n_sim, dtype=bool)
    best_day = np.zeros(n_sim)
    alive = np.ones(n_sim, dtype=bool)
    passed = np.zeros(n_sim, dtype=bool)
    blown = np.zeros(n_sim, dtype=bool)
    days_used = np.zeros(n_sim, dtype=int)
    consistency_blocks = 0

    for day in range(1, MAX_DAYS + 1):
        if not alive.any():
            break
        day_start = bal.copy()
        stopped_today = ~alive            # a dead path takes no more trades
        for _ in range(trades_per_day):
            win = rng.random(n_sim) < wr
            pnl = np.where(win, win_usd, -win_usd) - cost_usd
            take = alive & ~stopped_today
            bal = np.where(take, bal + pnl, bal)
            hit_floor = take & (bal <= floor)
            blown |= hit_floor
            alive &= ~hit_floor
            stopped_today |= hit_floor
            if daily_loss_usd is not None:
                stopped_today |= take & ((bal - day_start) <= -daily_loss_usd)

        best_day = np.where(alive, np.maximum(best_day, bal - day_start), best_day)

        # the floor trails on END-OF-DAY equity, and stops trailing for good
        # once the lock level has been touched
        reach_lock = alive & ~locked & (bal >= LOCK_AT)
        floor = np.where(reach_lock, LOCK_FLOOR, floor)
        locked |= reach_lock
        trail = alive & ~locked
        floor = np.where(trail, np.maximum(floor, bal - DD), floor)

        at_target = alive & (bal >= TARGET)
        ok = at_target & (best_day <= CONSISTENCY * (bal - START) + 1e-9)
        consistency_blocks += int((at_target & ~ok).sum())
        passed |= ok
        days_used = np.where(ok & (days_used == 0), day, days_used)
        alive &= ~ok                       # a passed path stops trading

    return dict(p_pass=float(passed.mean()),
                p_blown=float(blown.mean()),
                p_timeout=float(1 - passed.mean() - blown.mean()),
                consistency_blocks=consistency_blocks,
                median_days=float(np.median(days_used[passed])) if passed.any() else np.nan)


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows = []
    combos = [(k, wr, tpd) for k in GRID_K for wr in GRID_WR for tpd in GRID_TPD]
    for k, wr, tpd in track(combos, label="lucid50k MC"):
        # 1 NQ is the only size that keeps the stop inside the daily loss limit
        # for the larger brackets; micros are reported alongside because they
        # are how a 150-tick stop stays survivable on a $2,000 drawdown.
        for tag, tick_usd, n_ct, dll in (("NQ_x1", NQ_TICK_USD, 1, None),
                                         ("NQ_x1_pro", NQ_TICK_USD, 1, 1200.0),
                                         ("MNQ_x5", MNQ_TICK_USD, 5, None)):
            r = simulate(k, wr, tpd, tick_usd, n_ct, dll, N_SIM, rng)
            risk = k * tick_usd * n_ct
            rows.append(dict(size=tag, k_ticks=k, risk_usd=risk, wr=wr,
                             trades_per_day=tpd,
                             be_wr_net=(k + COST_TICKS) / (2 * k), **r))
    df = pd.DataFrame(rows)
    out = C.DATA / "reports" / "lucid50k_requirement.csv"
    df.to_csv(out, index=False)

    print("\n=== zero edge (WR 0.50): pass probability by stop size, 1 NQ ===")
    z = df[(df.wr == 0.50) & (df["size"] == "NQ_x1")]
    print(z.pivot_table(index="k_ticks", columns="trades_per_day",
                        values="p_pass").round(4).to_string())

    print("\n=== best configuration per win rate (1 NQ, no daily loss limit) ===")
    b = df[df["size"] == "NQ_x1"].sort_values("p_pass", ascending=False)
    print(b.groupby("wr").head(1)[
        ["wr", "k_ticks", "trades_per_day", "risk_usd", "be_wr_net",
         "p_pass", "p_blown", "p_timeout", "median_days"]
    ].sort_values("wr").round(4).to_string(index=False))

    print("\n=== same, LucidPro daily loss limit $1,200 ===")
    b = df[df["size"] == "NQ_x1_pro"].sort_values("p_pass", ascending=False)
    print(b.groupby("wr").head(1)[
        ["wr", "k_ticks", "trades_per_day", "risk_usd", "p_pass", "p_blown",
         "p_timeout", "median_days"]
    ].sort_values("wr").round(4).to_string(index=False))

    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
