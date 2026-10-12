"""Pre-registered hypothesis tests on the OR breakout, premarket context included.

The hypotheses below are FIXED IN CODE before any of them is run, and every one
of them is reported whether it works or not. That is the whole point: if you
look at twenty splits and publish the best, you have published noise. Here the
count of tests is known, so the Bonferroni threshold is honest.

Each hypothesis splits the same trades into two groups and asks whether the win
rate differs. The bracket is 1:1, so the reference is always 50%.
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
PM = DATA / "features" / "premarket_features.parquet"
OUT = DATA / "reports"
COST = 1.8

# (name, what it tests, a function returning the boolean group flag)
HYPOTHESES: list[tuple[str, str, "callable"]] = [
    ("beyond_VA",
     "el nivel roto esta mas alla del value area premarket",
     lambda d: d.lvl_beyond_va == 1),
    ("inside_VA",
     "el nivel roto esta dentro del value area premarket",
     lambda d: d.lvl_inside_va == 1),
    ("or_breaks_pm_range",
     "la vela OR rompio el extremo del rango premarket en la direccion",
     lambda d: pd.Series(np.where(d.side > 0, d.or_above_pm_high,
                                  d.or_below_pm_low), index=d.index) == 1),
    ("overnight_aligned",
     "la deriva nocturna va a favor de la ruptura",
     lambda d: d.gap_aligned > 0),
    ("or_wide",
     "la vela OR mide mas que la mediana",
     lambda d: d.or_range_ticks > d.or_range_ticks.median()),
    ("or_narrow_vs_h1",
     "la vela OR es chica respecto a la ultima hora premarket",
     lambda d: d.or_over_h1_range < d.or_over_h1_range.median()),
    ("vol_surge_high",
     "el volumen del minuto OR supera la mediana del surge",
     lambda d: d.or_vol_surge > d.or_vol_surge.median()),
    ("vwap_far",
     "el cierre que rompe esta lejos del VWAP de 09:30",
     lambda d: d.vwap_dist_ticks.abs() > d.vwap_dist_ticks.abs().median()),
    ("vwap_near",
     "el cierre que rompe esta cerca del VWAP de 09:30",
     lambda d: d.vwap_dist_ticks.abs() <= d.vwap_dist_ticks.abs().median()),
    ("body_strong",
     "el cuerpo de la vela que rompe ocupa mas del 70% del rango",
     lambda d: d.body_frac > 0.70),
    ("small_chase",
     "el cierre quedo a 20 ticks o menos del nivel",
     lambda d: d.break_ticks <= 20),
    ("early_minute",
     "la senal ocurrio en el minuto 09:31",
     lambda d: d.signal_minute_idx == 31),
    ("pm_close_high",
     "el premarket cerro en el tercio alto de su rango y la ruptura es long",
     lambda d: ((d.pm_close_pos > 0.667) & (d.side > 0))
               | ((d.pm_close_pos < 0.333) & (d.side < 0))),
    ("poc_behind",
     "el POC premarket quedo detras del nivel roto",
     lambda d: d.lvl_to_poc_ticks > 0),
]


def group_stats(g: pd.DataFrame) -> dict:
    n = len(g)
    if not n:
        return {"n": 0}
    k = int((g.ticks > 0).sum())
    return {"n": n, "WR %": round(100 * k / n, 1),
            "EV neto": round(g.ticks.mean() - COST, 2), "wins": k}


def main() -> int:
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--entry-mode", default="limit_level")
    ap.add_argument("--bracket", type=int, default=40)
    a = ap.parse_args()

    ev = pd.read_parquet(EVENTS)
    ev = ev[(ev.entry_mode == a.entry_mode) & (ev.tp_ticks == a.bracket)
            & ev.filled & ev.ticks.notna()]
    pm = pd.read_parquet(PM)
    d = ev.merge(pm, on="session", how="left")
    if "or_range_ticks" not in d.columns and "or_range_ticks_chk" in d.columns:
        d["or_range_ticks"] = d.or_range_ticks_chk

    print(f"entrada {a.entry_mode}, bracket 1:1 de {a.bracket} ticks")
    print(f"n = {len(d)} trades   WR global {100*(d.ticks>0).mean():.1f}%   "
          f"EV neto global {d.ticks.mean()-COST:+.2f} ticks")
    print(f"breakeven WR = 50.0%   hipotesis pre-registradas = {len(HYPOTHESES)}\n")

    rows = []
    for name, desc, fn in HYPOTHESES:
        try:
            flag = pd.Series(fn(d), index=d.index).fillna(False).astype(bool)
        except Exception as exc:
            rows.append({"hipotesis": name, "error": str(exc)[:40]})
            continue
        a_g, b_g = d[flag], d[~flag]
        sa, sb = group_stats(a_g), group_stats(b_g)
        if not sa["n"] or not sb["n"]:
            continue
        # two-sided test of "the two win rates are equal"
        table = [[sa["wins"], sa["n"] - sa["wins"]],
                 [sb["wins"], sb["n"] - sb["wins"]]]
        p_diff = stats.fisher_exact(table)[1]
        # and the group on its own against the 50% breakeven
        p_be = stats.binomtest(sa["wins"], sa["n"], 0.5).pvalue
        rows.append({"hipotesis": name,
                     "n si": sa["n"], "WR si": sa["WR %"], "EV si": sa["EV neto"],
                     "n no": sb["n"], "WR no": sb["WR %"], "EV no": sb["EV neto"],
                     "p dif": round(p_diff, 4), "p vs 50%": round(p_be, 4)})

    tab = pd.DataFrame(rows)
    pd.set_option("display.width", 230)
    print(tab.to_string(index=False))

    k = len(tab)
    bonf = 0.05 / k
    print(f"\numbral Bonferroni para {k} hipotesis: p < {bonf:.4f}")
    surv = tab[(tab["p dif"] < bonf) | (tab["p vs 50%"] < bonf)]
    if surv.empty:
        print("NINGUNA hipotesis sobrevive la correccion. Con esta n, cualquier")
        print("WR alto de la tabla es compatible con una moneda.")
        best = tab.loc[tab["p dif"].idxmin()]
        print(f"\nla mas cercana fue '{best.hipotesis}': p dif = {best['p dif']}, "
              f"necesitaria p < {bonf:.4f}")
    else:
        print(surv.to_string(index=False))
        print("ATENCION: sobrevivir aqui es condicion necesaria, no suficiente.")
        print("Falta validarla en datos que no se usaron para encontrarla.")

    nmin = tab["n si"].min() if "n si" in tab else 0
    if nmin < 30:
        print(f"\nAVISO: el grupo mas chico tiene n={nmin}. Grupos bajo 30 no pesan.")

    OUT.mkdir(parents=True, exist_ok=True)
    tab.to_csv(OUT / f"hypotheses_{a.entry_mode}_{a.bracket}t.csv", index=False)
    print(f"\n-> {OUT/f'hypotheses_{a.entry_mode}_{a.bracket}t.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
