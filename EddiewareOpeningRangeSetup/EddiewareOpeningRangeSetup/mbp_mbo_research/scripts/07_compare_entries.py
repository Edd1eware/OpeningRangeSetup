"""Entry mode x bracket comparison with the honest statistics attached.

The point of this table is to stop a good-looking cell from being believed. For
every cell it prints the net EV after costs, how far the WR sits from the 50%
breakeven of a 1:1 bracket, and a two-sided binomial p-value against that 50%.

It also prints the multiple-testing correction, because the grid tries
7 entry modes x 7 brackets = 49 cells: at p < 0.05 you expect ~2.5 cells to look
significant on pure noise. A cell only earns attention if it survives that.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA

EVENTS = DATA / "events" / "or_events.parquet"
COMMISSION_TICKS = 0.8      # ~$4 round turn on NQ at $5/tick
SLIPPAGE_TICKS = 1.0        # 1 tick of adverse fill, entry and exit combined
COST = COMMISSION_TICKS + SLIPPAGE_TICKS
MIN_N = 30


def net_breakeven_wr(bracket: int) -> float:
    """Win rate that merely pays the costs on a 1:1 bracket.

    Gross breakeven is 50%, but each trade pays COST ticks, so the real bar is
    0.5 + COST/(2*bracket). For a 40-tick bracket at 1.8 ticks of cost that is
    52.25%, not 50%. Reporting the gross figure as if it were the hurdle makes a
    losing strategy look like it is on the edge of working.
    """
    return 0.5 + COST / (2.0 * bracket)


def cell_stats(g: pd.DataFrame) -> dict:
    wins = g.ticks > 0
    n, k = len(g), int(wins.sum())
    gross_win = g.loc[wins, "ticks"].sum()
    gross_loss = -g.loc[~wins, "ticks"].sum()
    # two-sided binomial test against the 50% breakeven of a 1:1 bracket
    p = stats.binomtest(k, n, 0.5).pvalue if n else np.nan
    br = int(g.tp_ticks.iloc[0]) if n else 0
    be_net = net_breakeven_wr(br) if br else np.nan
    p_net = (stats.binomtest(k, n, be_net, alternative="greater").pvalue
             if n else np.nan)
    return {"trades": n,
            "WR %": round(100 * k / n, 1) if n else np.nan,
            "BE neto %": round(100 * be_net, 2) if n else np.nan,
            "p > BE neto": round(p_net, 4) if n else np.nan,
            "PF": round(gross_win / gross_loss, 2) if gross_loss else np.inf,
            "EV bruto": round(g.ticks.mean(), 2) if n else np.nan,
            "EV neto": round(g.ticks.mean() - COST, 2) if n else np.nan,
            "p vs 50%": round(p, 4) if n else np.nan,
            "n ok": "" if n >= MIN_N else f"<{MIN_N}"}


def main() -> int:
    if not EVENTS.exists():
        print(f"no events at {EVENTS}. run 04_or_events.py first.")
        return 1
    ev = pd.read_parquet(EVENTS)
    filled = ev[ev.filled & ev.ticks.notna()].copy()

    sessions = ev.session.nunique()
    months = pd.to_datetime(ev.session).dt.to_period("M").nunique()
    print(f"{sessions} sessions with a signal over {months} calendar month(s)")
    print(f"costs assumed: {COMMISSION_TICKS} ticks commission + "
          f"{SLIPPAGE_TICKS} ticks slippage = {COST} ticks/trade")
    print(f"breakeven WR for a 1:1 bracket = 50.0% exactly\n")

    rows = []
    for (mode, br), g in filled.groupby(["entry_mode", "tp_ticks"]):
        taken = ev[ev.entry_mode == mode].session.nunique()
        rows.append({"entry_mode": mode, "bracket": int(br),
                     "trades/mes": round(len(g) / months, 1),
                     "fill %": round(100 * g.session.nunique() / max(taken, 1), 1),
                     **cell_stats(g)})
    tab = pd.DataFrame(rows).sort_values(["entry_mode", "bracket"])

    pd.set_option("display.width", 220)
    print("=== entry mode x bracket (1:1, R:R = 1.0, BE WR = 50%) ===")
    print(tab.to_string(index=False))

    n_cells = len(tab)
    hits = tab[tab["p > BE neto"] < 0.05]
    expected = 0.05 * n_cells
    print(f"\n--- multiple testing ---")
    print(f"cells tested: {n_cells}  |  cells with p<0.05: {len(hits)}  |  "
          f"expected on pure noise: {expected:.1f}")
    bonf = 0.05 / n_cells
    survivors = tab[tab["p > BE neto"] < bonf]
    print(f"Bonferroni threshold: p < {bonf:.5f}  |  survivors: {len(survivors)}")
    if survivors.empty:
        print("  -> NO cell survives the correction. Everything in the table is "
              "within what a coin flip produces across this many tries.")
    else:
        print(survivors.to_string(index=False))

    thin = tab[tab["n ok"] != ""]
    if len(thin):
        print(f"\nWARNING: {len(thin)}/{n_cells} cells have n < {MIN_N}. "
              "A 1:1 bracket needs roughly 400 trades to separate a 55% WR "
              "from a 50% one at p<0.05.")

    out = DATA / "reports"
    out.mkdir(parents=True, exist_ok=True)
    tab.to_csv(out / "entry_mode_comparison.csv", index=False)
    print(f"\n-> {out/'entry_mode_comparison.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
