"""How much edge does the Lucid 100K evaluation actually require?

This costs nothing to run and it is what decides whether any further Databento
spend is justified. The research so far asks "is there an edge". This asks the
complementary question: "how big would an edge have to be before it is worth
trying to pass with it", which turns out to invert one of the project's working
assumptions.

The assumption being tested
---------------------------
The project notes concluded that Lucid rewards a SMALL stop and HIGH frequency,
and that the trader's ~100 tick stop with 3.2 trades/month is the opposite of
what the evaluation wants. The frequency half is right. The small-stop half is
only right CONDITIONAL ON ALREADY HAVING AN EDGE, and that conditional matters
enormously, because the fixed round-trip cost c eats a fraction c/K of every
unit of risk. The smaller the stop, the larger the share of each bet that is
paid to the broker, so the net breakeven win rate rises as the stop shrinks:

    p_BE = (S + c) / (T + S)

With zero skill and a symmetric bracket, shrinking the stop does not keep the
pass probability flat; it collapses it. Under driftless gambler's ruin with
step +/-K, drift -c per trade, target +1200 ticks and drawdown -600 ticks:

    K = 20 ticks,  c = 1.8  ->  P(pass) ~ 0.002%
    K = 100 ticks, c = 1.8  ->  P(pass) ~ 26.4%

Same zero edge, same account rules, four orders of magnitude apart. A small
stop is a bet that the edge is real; a large stop is a bet that it is not.

The Lucid 100K rules as modelled
--------------------------------
    profit target        +$6,000       = +1,200 ticks at $5/tick, 1 contract
    max drawdown          $3,000       = 600 ticks, TRAILING on END-OF-DAY equity
    drawdown lock         once equity reaches $103,100 the floor fixes at
                          $100,100, i.e. it stops trailing
    consistency           no single day may be more than 50% of total profit,
                          which in practice forces at least two winning days

The trailing EOD drawdown is the rule that a static-drawdown model gets wrong,
and it gets it wrong in the DANGEROUS direction: once the account is up, the
floor has followed, so giving back is fatal in a way a static floor is not.
That is why this is a Monte Carlo over days rather than a closed form.

What is NOT modelled, and would make things worse
-------------------------------------------------
* No daily loss limit, no scaling plan, no inactivity rule.
* Costs are a flat c ticks per round trip, already charged to every trade.
* Trades inside a day are independent, which they are not.
* Fills are assumed at the bracket. Real slippage on the stop is worse.
So every number here is an OPTIMISTIC bound on the real pass probability.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from progress import track  # noqa: E402

TICK_USD = 5.0
START = 100_000.0
TARGET = 106_000.0           # +$6,000
DD = 3_000.0                 # trailing on end-of-day equity
LOCK_AT = 103_100.0          # above this the floor fixes
LOCK_FLOOR = 100_100.0
CONSISTENCY = 0.50           # no day may exceed 50% of total profit

MAX_DAYS = 120               # a practical patience limit for the evaluation
N_SIMS = 20_000
SEED = 20261012


def gamblers_ruin(k_ticks: float, cost: float, up: float, down: float) -> float:
    """Closed form P(hit +up before -down) for a +/-k step with a -cost drift.

    Used only for the zero-skill intuition in the docstring: the per-trade
    outcome is +k or -k with p chosen so the mean equals -cost.
    """
    p = (1.0 - cost / k_ticks) / 2.0
    q = 1.0 - p
    a = up / k_ticks
    b = down / k_ticks
    if abs(p - 0.5) < 1e-12:
        return b / (a + b)
    r = q / p
    # work in logs: r**90 overflows for small k
    log_r = np.log(r)
    num = 1.0 - np.exp(log_r * b)
    den = 1.0 - np.exp(log_r * (a + b))
    return float(num / den)


def simulate(wr: float, sl_t: float, tp_t: float, cost_t: float,
             trades_per_day: int, rng: np.random.Generator,
             n_sims: int = N_SIMS, max_days: int = MAX_DAYS,
             check_open: bool = True) -> dict:
    """Monte Carlo the evaluation under the full rule set.

    check_open controls the one bias Codex identified in the earlier version:
    it only tested CLOSED-trade equity, so a trade that dipped through the
    account floor while open and then recovered was counted as surviving. That
    biases the pass probability UP and the required edge DOWN.

    With check_open=True the worst open equity during a trade is bounded by
    `equity_before - (SL + cost)`, because the stop caps the loss. That bound is
    slightly pessimistic for a trade that never approaches its stop, so the two
    modes BRACKET the truth rather than guess inside it:
        check_open=False -> optimistic (the old, biased-up behaviour)
        check_open=True  -> conservative
    Both are reported, the same way ambiguous bar outcomes are bracketed
    elsewhere in this project instead of being invented.
    """
    win_usd = (tp_t - cost_t) * TICK_USD
    loss_usd = -(sl_t + cost_t) * TICK_USD
    worst_open_usd = (sl_t + cost_t) * TICK_USD   # max adverse excursion per trade

    passed = 0
    busted = 0
    days_to_pass: list[int] = []

    for _ in range(n_sims):
        equity = START
        floor = START - DD
        day_pnl: list[float] = []
        outcome = "timeout"

        for day in range(1, max_days + 1):
            # one day of trading
            wins = rng.random(trades_per_day) < wr
            steps = np.where(wins, win_usd, loss_usd)
            # walk the day so an intraday breach of the floor still kills
            path = equity + np.cumsum(steps)
            # equity BEFORE each trade, to bound its worst open excursion
            before = np.concatenate([[equity], path[:-1]])
            if check_open and (before - worst_open_usd).min() <= floor:
                outcome = "bust"
                break
            if path.min() <= floor:
                outcome = "bust"
                break
            equity = float(path[-1])
            day_pnl.append(float(steps.sum()))

            # trailing drawdown updates on END-OF-DAY equity only
            if equity >= LOCK_AT:
                floor = max(floor, LOCK_FLOOR)
            else:
                floor = max(floor, equity - DD)

            if equity >= TARGET:
                profit = equity - START
                best_day = max(day_pnl) if day_pnl else 0.0
                # consistency: the biggest day may not exceed 50% of profit.
                # if it does, the account must keep trading to dilute it, so
                # this is NOT a pass yet.
                if profit > 0 and best_day <= CONSISTENCY * profit:
                    outcome = "pass"
                    days_to_pass.append(day)
                    break
                # otherwise keep going; the target stays hit but unconfirmed

        if outcome == "pass":
            passed += 1
        elif outcome == "bust":
            busted += 1

    return dict(
        p_pass=passed / n_sims,
        p_bust=busted / n_sims,
        p_timeout=1.0 - (passed + busted) / n_sims,
        median_days=float(np.median(days_to_pass)) if days_to_pass else float("nan"),
    )


def main() -> None:
    rng = np.random.default_rng(SEED)

    print("=" * 88, flush=True)
    print("PARTE 1 - SOLO INTUICION: ruina de jugador con piso FIJO,", flush=True)
    print("target +1200 / DD -600 ticks. NO son las reglas de Lucid:", flush=True)
    print("el piso real es TRAILING EOD, no hay limite de tiempo en Flex, y", flush=True)
    print("sustituir +/-K con probabilidad ajustada NO preserva las", flush=True)
    print("probabilidades de primer paso. Los numeros validos estan en la Parte 2.",
          flush=True)
    print("", flush=True)
    print("| stop K | drag c/K | P(pasar) con WR justo 50% bruto |", flush=True)
    print("|---|---|---|", flush=True)
    zero_edge = []
    for k in (8, 12, 16, 20, 30, 50, 75, 100, 150):
        p = gamblers_ruin(k, 1.8, 1200, 600)
        print(f"| {k} ticks | {1.8 / k:.2%} | {p:.4%} |", flush=True)
    print("", flush=True)
    print("Las mismas celdas bajo el modelo REAL de piso trailing EOD,", flush=True)
    print("cero edge bruto (WR 50% antes de costos), 4 trades/dia:", flush=True)
    print("", flush=True)
    print("| stop K | P(pasar) equity cerrada | P(pasar) con equity abierta |",
          flush=True)
    print("|---|---|---|", flush=True)
    for k in (20, 40, 100, 150):
        a = simulate(0.50, k, k, 1.8, 4, rng, n_sims=4000, check_open=False)
        b = simulate(0.50, k, k, 1.8, 4, rng, n_sims=4000, check_open=True)
        print(f"| {k} | {a['p_pass']:.1%} | **{b['p_pass']:.1%}** |", flush=True)
    print("", flush=True)
    print("Mismo cero edge. El stop chico NO es neutral: el costo fijo se come", flush=True)
    print("una fraccion c/K de cada unidad de riesgo, y eso compone.", flush=True)

    # ---------------------------------------------------------------
    print("", flush=True)
    print("=" * 88, flush=True)
    print("PARTE 2 - Monte Carlo con las reglas completas de Lucid", flush=True)
    print(f"(DD trailing EOD, lock a ${LOCK_AT:,.0f}, consistencia 50%, "
          f"{MAX_DAYS} dias max, {N_SIMS:,} simulaciones)", flush=True)
    print("", flush=True)

    # bracket 1:1 at several stop sizes, swept over win rate
    configs = []
    for sl in (10, 20, 40, 100):
        for wr in (0.50, 0.52, 0.55, 0.58, 0.62, 0.68):
            configs.append(("1:1", sl, sl, wr))
    # 1:2, swept over win rate
    for sl in (10, 20, 40):
        for wr in (0.34, 0.38, 0.42, 0.46, 0.50):
            configs.append(("1:2", sl, sl * 2, wr))

    tpd = 4   # trades per day; frequency is varied separately below
    rows = []
    for rr, sl, tp, wr in track(configs, label="lucid sims"):
        be = (sl + 1.8) / (tp + sl)
        r = simulate(wr, sl, tp, 1.8, tpd, rng, n_sims=4000)
        ev_net = wr * (tp - 1.8) - (1 - wr) * (sl + 1.8)
        rows.append((rr, sl, tp, wr, be, ev_net, r))

    print(f"| R:R | SL | TP | WR | BE neto | EV neto ticks | P(pasar) | "
          f"P(quemar) | dias med |", flush=True)
    print("|---|---|---|---|---|---|---|---|---|", flush=True)
    for rr, sl, tp, wr, be, ev, r in rows:
        print(f"| {rr} | {sl} | {tp} | {wr:.0%} | {be:.1%} | {ev:+.2f} | "
              f"**{r['p_pass']:.1%}** | {r['p_bust']:.1%} | "
              f"{r['median_days']:.0f} |", flush=True)

    # ---------------------------------------------------------------
    print("", flush=True)
    print("=" * 88, flush=True)
    print("PARTE 3 - cuanto edge hace falta: EV neto minimo por trade", flush=True)
    print("para que P(pasar) supere 50%, por tamano de stop", flush=True)
    print("", flush=True)
    print("| SL=TP | WR necesario | EV neto ticks | P(pasar) | P(quemar) |", flush=True)
    print("|---|---|---|---|---|", flush=True)
    for sl in (10, 20, 40, 100):
        found = None
        for wr in np.arange(0.50, 0.86, 0.01):
            r = simulate(float(wr), sl, sl, 1.8, tpd, rng, n_sims=2000)
            if r["p_pass"] >= 0.50:
                ev = wr * (sl - 1.8) - (1 - wr) * (sl + 1.8)
                found = (wr, ev, r)
                break
        if found:
            wr, ev, r = found
            print(f"| {sl} | {wr:.0%} | {ev:+.2f} | {r['p_pass']:.1%} | "
                  f"{r['p_bust']:.1%} |", flush=True)
        else:
            print(f"| {sl} | >85% | — | nunca llega a 50% | — |", flush=True)

    # ---------------------------------------------------------------
    print("", flush=True)
    print("=" * 88, flush=True)
    print("PARTE 4 - frecuencia: con un edge FIJO y bueno, cuantos trades/dia",
          flush=True)
    print("", flush=True)
    print("| trades/dia | SL=TP 20, WR 58% | SL=TP 100, WR 54% |", flush=True)
    print("|---|---|---|", flush=True)
    for tpd_i in (1, 2, 4, 8, 16):
        a = simulate(0.58, 20, 20, 1.8, tpd_i, rng, n_sims=3000)
        b = simulate(0.54, 100, 100, 1.8, tpd_i, rng, n_sims=3000)
        print(f"| {tpd_i} | {a['p_pass']:.1%} pasa / {a['p_bust']:.1%} quema / "
              f"{a['median_days']:.0f}d | {b['p_pass']:.1%} pasa / "
              f"{b['p_bust']:.1%} quema / {b['median_days']:.0f}d |", flush=True)

    print("", flush=True)
    print("Nota: todo esto es una COTA OPTIMISTA. No modela slippage adicional en", flush=True)
    print("el stop, ni dependencia entre trades del mismo dia, ni limite diario.", flush=True)


if __name__ == "__main__":
    main()
