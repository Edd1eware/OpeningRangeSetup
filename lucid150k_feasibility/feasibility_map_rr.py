"""
Lucid 150K feasibility frontier, extended over the reward:risk axis.

feasibility_map.py showed that at a fixed 1:1 bracket nothing below a 65% win
rate passes the evaluation. The user's constraint is R:R >= 1:1, not == 1:1,
so this run sweeps RR as well and reports, for every RR, the minimum win rate
that clears the frozen gates under the best integer sizing.

Same account rules and cost model as feasibility_map.py.
"""

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
N_PATHS = 5_000
SEED = 20260726

WR_GRID = [round(0.30 + 0.02 * i, 2) for i in range(21)]   # 0.30 .. 0.70
RR_GRID = [1.0, 1.5, 2.0, 2.5, 3.0]
STOP_GRID = [20, 30, 40, 60]
FREQ_GRID = [0.5, 1.0, 2.0, 3.0]

GATE_P_PASS = 0.70
GATE_P_BREACH = 0.10


def simulate(wr, rr, stop_ticks, freq, contracts, rng):
    win_usd = (stop_ticks * rr - COST_TICKS) * TICK_VALUE * contracts
    loss_usd = -(stop_ticks + COST_TICKS) * TICK_VALUE * contracts

    equity = np.zeros(N_PATHS)
    peak = np.zeros(N_PATHS)
    alive = np.ones(N_PATHS, dtype=bool)
    passed = np.zeros(N_PATHS, dtype=bool)
    breached = np.zeros(N_PATHS, dtype=bool)
    day_passed = np.full(N_PATHS, SESSIONS + 1, dtype=np.int32)

    max_trades = 6
    for day in range(1, SESSIONS + 1):
        if not alive.any():
            break
        floor = np.minimum(peak - MLL, FLOOR_LOCK)
        day_pnl = np.zeros(N_PATHS)
        n_trades = np.minimum(rng.poisson(freq, N_PATHS), max_trades)

        for k in range(max_trades):
            active = alive & (n_trades > k) & (day_pnl > -DLL_BUFFER)
            if not active.any():
                break
            outcome = np.where(rng.random(N_PATHS) < wr, win_usd, loss_usd)
            equity = np.where(active, equity + outcome, equity)
            day_pnl = np.where(active, day_pnl + outcome, day_pnl)
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
    cells = [(w, rr, s, f) for w in WR_GRID for rr in RR_GRID
             for s in STOP_GRID for f in FREQ_GRID]
    rows = []

    for wr, rr, stop_ticks, freq in track(cells, label="RR frontier"):
        ev_ticks = wr * (stop_ticks * rr - COST_TICKS) - (1 - wr) * (stop_ticks + COST_TICKS)
        if ev_ticks <= 0:
            continue                      # cannot pass anything with negative EV
        for c in range(1, MAX_CONTRACTS + 1):
            p_pass, p_breach, med = simulate(wr, rr, stop_ticks, freq, c, rng)
            if p_pass < 0.05:
                break                     # larger size only adds breach risk here
            rows.append(dict(wr=wr, rr=rr, stop_ticks=stop_ticks, freq=freq, contracts=c,
                             ev_ticks_net=round(ev_ticks, 3),
                             pf=round(wr * (stop_ticks * rr - COST_TICKS) /
                                      ((1 - wr) * (stop_ticks + COST_TICKS)), 3),
                             risk_usd_trade=round((stop_ticks + COST_TICKS) * TICK_VALUE * c, 2),
                             p_pass=round(float(p_pass), 4),
                             p_breach=round(float(p_breach), 4),
                             median_days=med))

    with open("FEASIBILITY_RR_RESULT.json", "w") as fh:
        json.dump(dict(params=dict(n_paths=N_PATHS, seed=SEED, cost_ticks=COST_TICKS,
                                   gate_p_pass=GATE_P_PASS, gate_p_breach=GATE_P_BREACH),
                       rows=rows), fh, indent=1)

    viable = [r for r in rows if r["p_pass"] >= GATE_P_PASS and r["p_breach"] <= GATE_P_BREACH]
    print(f"\ncells: {len(rows)}  viable: {len(viable)}  [{time.time()-t0:.1f}s]")

    print("\n--- MINIMUM WIN RATE REQUIRED, per (RR, trades/day) ---")
    print(f"{'RR':>5} {'tr/day':>7} {'minWR':>6} {'stop':>5} {'ctr':>4} {'PF':>6} "
          f"{'EVt':>7} {'risk$':>7} {'Ppass':>6} {'Pbrch':>6} {'medD':>5}")
    for rr in RR_GRID:
        for freq in FREQ_GRID:
            sub = [r for r in viable if r["rr"] == rr and r["freq"] == freq]
            if not sub:
                print(f"{rr:>5.1f} {freq:>7.1f} {'  none':>6}")
                continue
            best = min(sub, key=lambda r: (r["wr"], -r["p_pass"]))
            print(f"{rr:>5.1f} {freq:>7.1f} {best['wr']:>6.2f} {best['stop_ticks']:>5} "
                  f"{best['contracts']:>4} {best['pf']:>6.2f} {best['ev_ticks_net']:>7.2f} "
                  f"{best['risk_usd_trade']:>7.0f} {best['p_pass']:>6.3f} "
                  f"{best['p_breach']:>6.3f} {best['median_days']:>5.0f}")
    print(f"\ntotal elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
