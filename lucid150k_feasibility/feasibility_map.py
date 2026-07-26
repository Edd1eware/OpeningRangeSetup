"""
Lucid 150K feasibility frontier.

Answers the question V1-V13 never asked: what does an edge have to LOOK LIKE
(win rate, stop size, frequency, contracts) to actually pass a LucidPro 150K
evaluation within 63 sessions?

Account rules (LucidPro Evaluation 150K):
    profit target      +$9,000  (evaluated on EOD balance)
    MLL floor          min(peak_EOD - 4500, +100)   -> locks at +100
    daily loss limit   $2,700   (soft; we stop the day at a buffer below it)
    max size           10 minis
    horizon            63 sessions (~3 months)

Trade model: fixed 1:1 gross bracket, stop = target = S ticks, round-turn cost
of COST_TICKS. NQ mini = $5.00 / tick.
"""

import json
import time
import numpy as np

from progress import track

# ---------------------------------------------------------------- parameters
TICK_VALUE = 5.00          # NQ mini, USD per tick
COST_TICKS = 4.0           # round-turn total cost assumption (Codex standard)
TARGET = 9_000.0
MLL = 4_500.0
FLOOR_LOCK = 100.0
DLL = 2_700.0
DLL_BUFFER = 2_200.0       # stop trading for the day at this loss
SESSIONS = 63
MAX_CONTRACTS = 10
N_PATHS = 5_000
SEED = 20260726

WR_GRID = [0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62, 0.65, 0.70]
STOP_GRID = [20, 30, 40, 60]           # ticks
FREQ_GRID = [0.5, 1.0, 2.0, 3.0]       # mean trades per session
CONTRACT_GRID = list(range(1, MAX_CONTRACTS + 1))

# preregistered acceptance thresholds (frozen BEFORE running)
GATE_P_PASS = 0.70
GATE_P_BREACH = 0.10


def simulate(wr, stop_ticks, freq, contracts, rng):
    """Monte Carlo of one strategy configuration. Returns (p_pass, p_breach, median_days)."""
    win_usd = (stop_ticks - COST_TICKS) * TICK_VALUE * contracts
    loss_usd = -(stop_ticks + COST_TICKS) * TICK_VALUE * contracts

    equity = np.zeros(N_PATHS)
    peak = np.zeros(N_PATHS)          # peak of EOD equity
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
        n_trades = rng.poisson(freq, N_PATHS)
        np.minimum(n_trades, max_trades, out=n_trades)

        for k in range(max_trades):
            active = alive & (n_trades > k) & (day_pnl > -DLL_BUFFER)
            if not active.any():
                break
            outcome = np.where(rng.random(N_PATHS) < wr, win_usd, loss_usd)
            equity = np.where(active, equity + outcome, equity)
            day_pnl = np.where(active, day_pnl + outcome, day_pnl)
            # intraday breach check against the floor set at start of day
            hit = active & (equity <= floor)
            breached |= hit
            alive &= ~hit

        # end of day: target evaluated on EOD balance, then peak updates
        won = alive & (equity >= TARGET) & ~passed
        passed |= won
        day_passed = np.where(won, day, day_passed)
        alive &= ~won
        peak = np.maximum(peak, equity)

    p_pass = passed.mean()
    p_breach = breached.mean()
    med_days = float(np.median(day_passed[passed])) if passed.any() else float("nan")
    return p_pass, p_breach, med_days


def main():
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    cells = [(w, s, f) for w in WR_GRID for s in STOP_GRID for f in FREQ_GRID]
    rows = []

    for wr, stop_ticks, freq in track(cells, label="feasibility grid"):
        ev_ticks = stop_ticks * (2 * wr - 1) - COST_TICKS
        best = None
        for c in CONTRACT_GRID:
            p_pass, p_breach, med_days = simulate(wr, stop_ticks, freq, c, rng)
            rec = dict(wr=wr, stop_ticks=stop_ticks, freq=freq, contracts=c,
                       ev_ticks_net=round(ev_ticks, 3),
                       ev_usd_trade=round(ev_ticks * TICK_VALUE * c, 2),
                       risk_usd_trade=round((stop_ticks + COST_TICKS) * TICK_VALUE * c, 2),
                       p_pass=round(float(p_pass), 4),
                       p_breach=round(float(p_breach), 4),
                       median_days=med_days)
            rows.append(rec)
            ok = p_pass >= GATE_P_PASS and p_breach <= GATE_P_BREACH
            if ok and (best is None or p_pass > best["p_pass"]):
                best = rec
        if best is not None:
            best["gate_pass"] = True

    out = dict(
        params=dict(tick_value=TICK_VALUE, cost_ticks=COST_TICKS, target=TARGET,
                    mll=MLL, floor_lock=FLOOR_LOCK, dll=DLL, dll_buffer=DLL_BUFFER,
                    sessions=SESSIONS, n_paths=N_PATHS, seed=SEED,
                    gate_p_pass=GATE_P_PASS, gate_p_breach=GATE_P_BREACH),
        rows=rows,
    )
    with open("FEASIBILITY_RESULT.json", "w") as fh:
        json.dump(out, fh, indent=1)

    viable = [r for r in rows if r["p_pass"] >= GATE_P_PASS and r["p_breach"] <= GATE_P_BREACH]
    viable.sort(key=lambda r: (r["wr"], r["ev_ticks_net"]))
    print(f"\ncells simulated: {len(rows)}   viable: {len(viable)}   [{time.time()-t0:.1f}s]")
    if viable:
        print("\n--- minimum viable configurations (lowest WR first) ---")
        print(f"{'WR':>5} {'stop':>5} {'tr/day':>7} {'ctr':>4} {'EVt':>7} {'EV$':>9} "
              f"{'risk$':>7} {'Ppass':>6} {'Pbreach':>8} {'medD':>5}")
        for r in viable[:25]:
            print(f"{r['wr']:>5.2f} {r['stop_ticks']:>5} {r['freq']:>7.1f} {r['contracts']:>4} "
                  f"{r['ev_ticks_net']:>7.2f} {r['ev_usd_trade']:>9.2f} {r['risk_usd_trade']:>7.0f} "
                  f"{r['p_pass']:>6.3f} {r['p_breach']:>8.3f} {r['median_days']:>5.0f}")
    else:
        print("NO viable configuration under the frozen gates.")
    print(f"\ntotal elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
