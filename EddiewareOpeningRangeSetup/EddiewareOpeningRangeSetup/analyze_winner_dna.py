#!/usr/bin/env python3
"""ADN de winners — LVN retest (2026-07-09).

Compara distribuciones de features CAUSALES entre winners (TP) y losers (SL) por bracket y
cohorte de interacción, y propone filtros por percentiles de winners (retener ~85% de
winners, regla de calibración congelada en targets_lvn_volume_profile.md).

Solo LEE los CSV; nunca borra ni modifica Excels. Look-ahead permitido: fase exploración.

Uso:
  python analyze_winner_dna.py --events "outputs\\...\\LVN_Events.csv" --bracket 80
"""
from __future__ import annotations

import argparse
import glob
import math

import numpy as np
import pandas as pd

CAUSAL_FEATURES = [
    "lvn_depth", "lvn_width_ticks", "lvn_volume",
    "distance_to_context_poc_ticks", "distance_to_context_vah_ticks", "distance_to_context_val_ticks",
    "distance_to_minute_poc_ticks", "distance_to_open_ticks",
    "distance_to_vwap_ticks", "vwap_slope_ticks", "ema_slope_ticks", "realized_volatility",
    "approach_speed_ticks_per_second", "zone_speed_ticks_per_second", "deceleration_ratio",
    "seconds_touch_to_entry", "time_inside_lvn_zone_seconds", "seconds_from_0931",
    "retest_number", "distance_traveled_to_lvn_ticks", "prior_move_from_open_ticks",
    "lvn_retest_delta", "delta_touch_bar", "delta_change_touch_bar",
    "aggression_delta_per_second", "aggression_volume_per_second", "tape_speed_trades_per_second",
    "buy_imbalance_count", "sell_imbalance_count", "net_imbalance_count",
    "context_shape_confidence", "context_prob_D", "context_prob_P", "context_prob_b",
    "context_prob_trend_up", "context_prob_trend_down",
    "minute_shape_confidence",
]


def load_events(patterns: list[str]) -> pd.DataFrame:
    paths = sorted({p for pattern in patterns for p in glob.glob(pattern, recursive=True)})
    if not paths:
        raise FileNotFoundError(patterns)
    events = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    events = events.drop_duplicates(subset=["event_id"], keep="last")
    print(f"Eventos únicos: {len(events)} ({events['date'].min()} -> {events['date'].max()})\n")
    return events


def dna_table(events: pd.DataFrame, bracket: int, label: str) -> None:
    column = f"tp_sl_{bracket}_{bracket}_result"
    resolved = events.loc[events[column].isin(["TP", "SL"])].copy()
    winners = resolved.loc[resolved[column] == "TP"]
    losers = resolved.loc[resolved[column] == "SL"]
    if len(winners) < 5 or len(losers) < 5:
        print(f"== {label} {bracket}/{bracket}: n insuficiente (W={len(winners)}, L={len(losers)})\n")
        return
    print(f"== {label} {bracket}/{bracket} | winners {len(winners)} vs losers {len(losers)}")
    rows = []
    for feature in CAUSAL_FEATURES:
        if feature not in resolved.columns:
            continue
        w = pd.to_numeric(winners[feature], errors="coerce").dropna()
        l = pd.to_numeric(losers[feature], errors="coerce").dropna()
        if len(w) < 5 or len(l) < 5:
            continue
        w_med, l_med = float(w.median()), float(l.median())
        pooled_std = float(pd.concat([w, l]).std(ddof=0)) or math.nan
        separation = abs(w_med - l_med) / pooled_std if pooled_std and math.isfinite(pooled_std) else math.nan
        # Filtro candidato: banda percentil 7.5-92.5 de winners (retiene ~85%).
        lo, hi = float(w.quantile(0.075)), float(w.quantile(0.925))
        in_band_w = ((w >= lo) & (w <= hi)).mean()
        in_band_l = ((l >= lo) & (l <= hi)).mean()
        n_band = int(((pd.to_numeric(resolved[feature], errors="coerce") >= lo)
                      & (pd.to_numeric(resolved[feature], errors="coerce") <= hi)).sum())
        band_result = resolved.loc[
            (pd.to_numeric(resolved[feature], errors="coerce") >= lo)
            & (pd.to_numeric(resolved[feature], errors="coerce") <= hi), column]
        band_wr = 100.0 * (band_result == "TP").mean() if len(band_result) else math.nan
        rows.append({
            "feature": feature,
            "med_W": w_med,
            "med_L": l_med,
            "sep": separation,
            "band_lo": lo,
            "band_hi": hi,
            "W_ret%": 100 * in_band_w,
            "L_ret%": 100 * in_band_l,
            "WR_band%": band_wr,
            "n_band": n_band,
        })
    table = pd.DataFrame(rows).sort_values("sep", ascending=False)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", nargs="+", required=True)
    parser.add_argument("--bracket", type=int, nargs="*", default=[80, 40])
    args = parser.parse_args()
    events = load_events(args.events)
    for bracket in args.bracket:
        dna_table(events, bracket, "GLOBAL")
        for interaction in ("ACCEPTANCE", "REJECTION"):
            dna_table(events.loc[events["lvn_interaction"] == interaction], bracket, interaction)
    print("Nota: separación (sep) = |mediana_W - mediana_L| / std pooled. Bandas = percentiles "
          "7.5-92.5 de winners. WR_band = WR si solo se toman eventos dentro de la banda. "
          "Todo exploratorio (look-ahead OK); validación final requiere era-blind + forward.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
