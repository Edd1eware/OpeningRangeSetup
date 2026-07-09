#!/usr/bin/env python3
"""Gates del loop de investigación LVN (2026-07-08).

Gates congelados por el usuario ANTES de mirar resultados multi-temporada:
  WR minimo 50% | PF minimo 2.0 | RR 1:1 (bracket simétrico) | trades/mes minimo 4

Uso:
  python evaluate_lvn_gates.py --events "outputs\\lvn_or_strategy_replay\\*_csv\\LVN_Events.csv"

Reporta tabla año × métrica (estándar de reporte de backtest del usuario) por bracket y por
cohorte de interacción (ACCEPTANCE/REJECTION). Comisión asumida: 1 tick NQ por trade
(~$4-5 round-turn vs $5/tick). Breakeven bruto para 1:1 = 50% WR.

Decisión del loop: si ALGÚN bracket (o cohorte) pasa todos los gates en el agregado Y no
depende de un solo año gordo, se lanza la temporada DST del año anterior. NUNCA borra ni
sobrescribe Excels (solo lee).
"""
from __future__ import annotations

import argparse
import glob
import math
import sys

import pandas as pd

COMMISSION_TICKS = 1.0
GATE_WR = 50.0
GATE_PF = 2.0
GATE_TRADES_PER_MONTH = 4.0
BRACKETS = (20, 40, 60, 80)


def load_events(patterns: list[str]) -> pd.DataFrame:
    paths = sorted({path for pattern in patterns for path in glob.glob(pattern, recursive=True)})
    if not paths:
        raise FileNotFoundError(f"Sin LVN_Events.csv en: {patterns}")
    frames = [pd.read_csv(path) for path in paths]
    events = pd.concat(frames, ignore_index=True)
    events = events.drop_duplicates(subset=["event_id"], keep="last")
    events["date"] = pd.to_datetime(events["date"])
    events["year"] = events["date"].dt.year
    events["month"] = events["date"].dt.to_period("M")
    print(f"Archivos: {len(paths)} | eventos únicos: {len(events)} | "
          f"rango: {events['date'].min():%Y-%m-%d} -> {events['date'].max():%Y-%m-%d}\n")
    return events


def bracket_table(events: pd.DataFrame, target: int, label: str) -> tuple[pd.DataFrame, dict[str, float]]:
    column = f"tp_sl_{target}_{target}_result"
    result = events[column].astype(str)
    resolved = events.loc[result.isin(["TP", "SL"])].copy()
    resolved["win"] = (resolved[column] == "TP").astype(int)
    rows = []
    span_months = events["month"].nunique()

    def metrics(cohort: pd.DataFrame, months: int) -> dict[str, float]:
        n = len(cohort)
        wins = int(cohort["win"].sum())
        losses = n - wins
        wr = 100.0 * wins / n if n else math.nan
        pf = wins / losses if losses else math.inf if wins else math.nan
        ev_gross = (wins * target - losses * target) / n if n else math.nan
        ev_net = ev_gross - COMMISSION_TICKS if n else math.nan
        return {
            "trades": n,
            "trades/mes": n / months if months else math.nan,
            "WR%": wr,
            "R:R": 1.0,
            "PF": pf,
            "EV_bruto_t": ev_gross,
            "EV_neto_t": ev_net,
        }

    for year, cohort in resolved.groupby("year"):
        year_months = events.loc[events["year"] == year, "month"].nunique()
        rows.append({"year": str(year), **metrics(cohort, year_months)})
    total = metrics(resolved, span_months)
    rows.append({"year": "TOTAL", **total})
    table = pd.DataFrame(rows)
    passes = {
        "WR": total["WR%"] >= GATE_WR,
        "PF": total["PF"] >= GATE_PF,
        "trades/mes": total["trades/mes"] >= GATE_TRADES_PER_MONTH,
    }
    verdict = "PASS" if all(passes.values()) else "FAIL"
    print(f"== {label} bracket {target}/{target} (breakeven 50%) -> {verdict} "
          f"[WR {'OK' if passes['WR'] else 'X'} | PF {'OK' if passes['PF'] else 'X'} | "
          f"freq {'OK' if passes['trades/mes'] else 'X'}]")
    print(table.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print()
    return table, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", nargs="+", required=True, help="Globs de LVN_Events.csv")
    parser.add_argument("--cohorts", action="store_true", default=True, help="Además por lvn_interaction")
    args = parser.parse_args()
    events = load_events(args.events)

    any_pass = False
    for target in BRACKETS:
        _, total = bracket_table(events, target, "GLOBAL")
        if (total["WR%"] >= GATE_WR and total["PF"] >= GATE_PF
                and total["trades/mes"] >= GATE_TRADES_PER_MONTH):
            any_pass = True

    if args.cohorts and "lvn_interaction" in events.columns:
        for interaction in ("ACCEPTANCE", "REJECTION"):
            cohort = events.loc[events["lvn_interaction"] == interaction]
            if cohort.empty:
                continue
            for target in BRACKETS:
                _, total = bracket_table(cohort, target, interaction)
                if (total["WR%"] >= GATE_WR and total["PF"] >= GATE_PF
                        and total["trades/mes"] >= GATE_TRADES_PER_MONTH):
                    any_pass = True

    print("DECISION LOOP:", "ALGUN SEGMENTO PASA GATES -> lanzar temporada DST del año anterior"
          if any_pass else "NADA PASA GATES TODAVIA -> revisar cohortes/ADN antes de escalar")
    return 0 if any_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
