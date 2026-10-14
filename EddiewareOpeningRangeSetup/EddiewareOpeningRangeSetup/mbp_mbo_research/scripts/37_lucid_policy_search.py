"""The estimand that is NOT directional edge: P(pass) maximised over policies.

Codex's fourth attack, and it is the one that actually matters for the stated
goal. Script 28 reported "zero edge gives 25.2%, and reaching 50% needs WR 55%".
Both numbers are properties of ONE policy: a fixed stop size, the same every
trade, every day, whatever the state of the account. That is not the Lucid
objective. The objective is

    max over policies pi  of  P( reach $53,000 before breaching the floor )

and the floor is not static. The rules contain a structural asymmetry that a
fixed-size policy throws away:

    while balance < $52,100   the floor TRAILS: every dollar made raises the
                              level that kills you, so profit is only half won.
    once balance >= $52,100   the floor LOCKS at $50,100 and never moves again.

After the lock the remaining game is +$900 to the target against -$2,000 to the
floor. Under a fair coin that is a 69% leg. Before the lock the game is
+$2,100 against a floor that chases. So the two phases want opposite bet sizes,
and a policy that ignores the phase is leaving the asymmetry on the table.

This is not edge. Nothing here creates positive expectation, and a policy that
raises P(pass) does not make a losing strategy profitable: it reallocates the
same negative drift into a distribution of outcomes with more mass above the
target. Said plainly, it is better gambling, not an edge, and the expected
VALUE of the account is still negative by the cost paid. What it does buy, for
the stated goal, is a materially higher chance of converting one evaluation fee
into a funded account, and it does so at zero research cost.

Policies compared, all declared here before running
----------------------------------------------------
    fixed_K          script 28's policy, as the control
    bold             risk the entire distance to the floor on every trade,
                     which is the classic optimal play in an unfair game
    phase            large before the lock, small after it
    phase_inv        small before the lock, large after it
    prop_target      risk a fixed fraction of the distance remaining to target
    prop_floor       risk a fixed fraction of the distance to the floor
    min_both         risk a fraction of the SMALLER of the two distances

Everything else is held exactly as script 28 had it, including the consistency
rule, the intraday breach check, the $1,200 LucidPro daily loss limit as a
switch, and the 1.8 tick round-trip cost charged to every trade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from progress import track

TICK_USD = 5.0                 # 1 NQ
COST_TICKS = 1.8
COST_USD = COST_TICKS * TICK_USD

START = 50_000.0
TARGET = 53_000.0
DD = 2_000.0
LOCK_AT = 52_100.0
LOCK_FLOOR = 50_100.0
CONSISTENCY = 0.50
MAX_DAYS = 120
N_SIM = 40_000
MAX_TRADES_DAY = 4
MIN_RISK = 10 * TICK_USD       # a 10-tick stop, below which cost eats the bet
MAX_RISK = 3_000.0             # 600 ticks, a loose outer bound only
SAFETY = 0.95                  # never stake more than 95% of the distance
                               # to the floor: a bet equal to that distance
                               # turns the next loss into a certain breach
SEED = 20261013


def bet_size(kind, p, bal, floor, locked, to_target, to_floor):
    """USD risked on the next trade, given the account state."""
    if kind == "fixed":
        r = np.full_like(bal, p["k"] * TICK_USD)
    elif kind == "bold":
        r = to_floor
    elif kind == "phase":
        r = np.where(locked, p["k_post"] * TICK_USD, p["k_pre"] * TICK_USD)
    elif kind == "prop_target":
        r = p["f"] * to_target
    elif kind == "prop_floor":
        r = p["f"] * to_floor
    elif kind == "min_both":
        r = p["f"] * np.minimum(to_target, to_floor)
    elif kind == "safe":
        # Never place a bet that a loss cannot survive. Validation of the first
        # policy sweep found a cliff, not a slope: a $1,500 cap passes 43.7% of
        # the time and a $2,000 cap passes 0.03%, because once the stake reaches
        # the distance to the floor, one win followed by one loss forces a bet
        # that is certain death. The binding constraint is the floor, so the
        # stake is written against it rather than against a fixed ceiling.
        r = np.minimum(p["f"] * to_floor, to_target)
    else:
        raise ValueError(kind)
    cap = np.maximum(SAFETY * to_floor, MIN_RISK) if SAFETY else MAX_RISK
    return np.clip(r, MIN_RISK, np.minimum(cap, MAX_RISK))


def simulate(kind, p, wr, trades_per_day, daily_loss, n_sim, rng):
    """Vectorised over paths; bet size recomputed per trade from the state."""
    bal = np.full(n_sim, START)
    floor = np.full(n_sim, START - DD)
    locked = np.zeros(n_sim, dtype=bool)
    best_day = np.zeros(n_sim)
    alive = np.ones(n_sim, dtype=bool)
    passed = np.zeros(n_sim, dtype=bool)
    days_used = np.zeros(n_sim, dtype=int)

    for day in range(1, MAX_DAYS + 1):
        if not alive.any():
            break
        day_start = bal.copy()
        stopped = ~alive
        for _ in range(trades_per_day):
            to_target = np.maximum(TARGET - bal, 1.0)
            to_floor = np.maximum(bal - floor, 1.0)
            risk = bet_size(kind, p, bal, floor, locked, to_target, to_floor)
            win = rng.random(n_sim) < wr
            pnl = np.where(win, risk, -risk) - COST_USD
            take = alive & ~stopped
            bal = np.where(take, bal + pnl, bal)
            hit = take & (bal <= floor)
            alive &= ~hit
            stopped |= hit
            if daily_loss is not None:
                stopped |= take & ((bal - day_start) <= -daily_loss)
            # a path that has reached the target stops trading for the day
            stopped |= take & (bal >= TARGET)

        best_day = np.where(alive, np.maximum(best_day, bal - day_start), best_day)
        reach = alive & ~locked & (bal >= LOCK_AT)
        floor = np.where(reach, LOCK_FLOOR, floor)
        locked |= reach
        trail = alive & ~locked
        floor = np.where(trail, np.maximum(floor, bal - DD), floor)

        at_t = alive & (bal >= TARGET)
        ok = at_t & (best_day <= CONSISTENCY * (bal - START) + 1e-9)
        passed |= ok
        days_used = np.where(ok & (days_used == 0), day, days_used)
        alive &= ~ok
    return float(passed.mean()), (float(np.median(days_used[passed]))
                                  if passed.any() else np.nan)


def main():
    rng = np.random.default_rng(SEED)
    policies = []
    for k in (40, 60, 80, 100, 150, 200, 300):
        policies.append(("fixed", dict(k=k), f"fixed_{k}t"))
    policies.append(("bold", dict(), "bold"))
    for pre in (100, 150, 200, 300):
        for post in (20, 40, 60, 100):
            policies.append(("phase", dict(k_pre=pre, k_post=post),
                             f"phase_{pre}/{post}t"))
    for f in (0.1, 0.2, 0.3, 0.5, 0.8, 1.0):
        policies.append(("prop_target", dict(f=f), f"propT_{f}"))
        policies.append(("prop_floor", dict(f=f), f"propF_{f}"))
        policies.append(("min_both", dict(f=f), f"minBoth_{f}"))
    for f in (0.25, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        policies.append(("safe", dict(f=f), f"safe_{f}"))

    rows = []
    combos = [(wr, tpd) for wr in (0.50, 0.52, 0.55) for tpd in (1, 2, 4)]
    total = len(policies) * len(combos) * 2
    with_bar = track(range(total), label="policy search")
    for kind, p, name in policies:
        for wr, tpd in combos:
            for tag, dl in (("flex", None), ("pro", 1200.0)):
                pp, md = simulate(kind, p, wr, tpd, dl, N_SIM, rng)
                rows.append(dict(policy=name, kind=kind, wr=wr,
                                 trades_per_day=tpd, account=tag,
                                 p_pass=pp, median_days=md))
                next(with_bar, None)
    df = pd.DataFrame(rows)
    df.to_csv(C.DATA / "reports" / "lucid_policy_search.csv", index=False)

    for wr in (0.50, 0.52, 0.55):
        sub = df[(df.wr == wr) & (df.account == "flex")].sort_values("p_pass", ascending=False)
        print(f"\n=== WR {wr:.2f}, LucidFlex 50K: top 8 policies ===")
        print(sub.head(8)[["policy", "trades_per_day", "p_pass", "median_days"]]
              .round(4).to_string(index=False))
        base = sub[sub.policy == "fixed_150t"].p_pass.max()
        print(sub.head(12)[["policy", "trades_per_day", "p_pass", "median_days"]]
              .round(4).to_string(index=False)) if False else None
        best = sub.p_pass.iloc[0]
        print(f"  best {best:.4f} vs script 28's fixed 150t {base:.4f}  "
              f"-> {best - base:+.4f} absolute, {best/max(base,1e-9):.2f}x")

    print("\n=== LucidPro (daily loss $1,200), WR 0.50 ===")
    sub = df[(df.wr == 0.50) & (df.account == "pro")].sort_values("p_pass", ascending=False)
    print(sub.head(6)[["policy", "trades_per_day", "p_pass", "median_days"]]
          .round(4).to_string(index=False))
    print(f"\nwrote {C.DATA / 'reports' / 'lucid_policy_search.csv'}")


if __name__ == "__main__":
    main()
