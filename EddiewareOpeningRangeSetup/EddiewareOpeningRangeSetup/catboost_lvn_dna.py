#!/usr/bin/env python3
"""CatBoost — ADN de ganadores LVN, multi-tamaño (2026-07-09).

Tarea (usuario): sacar el ADN de los ganadores SIN importar si son grandes o chicos.
Diseño: un modelo por cada tamaño de winner (bracket 20/40/60/80 1:1) + un regresor de la
extensión continua (MFE en ticks). El ADN final = ranking agregado de importancias entre
los 5 objetivos: una feature que separa winners chicos Y grandes es ADN robusto; una que
solo aparece en un bracket es ruido de tamaño.

Era-blind: entrena en años dev, valida en año val, y el holdout se toca UNA sola vez.
Features: whitelist CAUSAL explícita (nada del outcome entra al modelo).

Uso (banco completo):
  python catboost_lvn_dna.py --events "outputs/lvn_or_strategy_replay/*_csv/LVN_Events.csv" \
      --dev-years 2022 2023 2024 --val-year 2025 --holdout-year 2026
"""
from __future__ import annotations

import argparse
import glob

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor, Pool
from sklearn.metrics import roc_auc_score

NUMERIC_FEATURES = [
    # ubicación del LVN
    "distance_to_context_vah_ticks", "distance_to_context_poc_ticks", "distance_to_context_val_ticks",
    "distance_to_minute_poc_ticks", "distance_to_vwap_ticks", "distance_to_open_ticks",
    "distance_to_or_high_ticks", "distance_to_or_low_ticks", "distance_to_main_hvn_ticks",
    "open_to_ctx_poc_ticks", "open_to_ctx_vah_ticks", "open_to_ctx_val_ticks",
    # estructura del nodo
    "lvn_volume", "lvn_depth", "lvn_width_ticks",
    # forma del perfil (contexto y minuto)
    "ctx_skewness", "ctx_kurtosis_excess", "ctx_entropy", "ctx_profile_width_ticks",
    "ctx_value_area_width_ticks", "ctx_upper_volume_share", "ctx_lower_volume_share",
    "ctx_poc_position", "ctx_center_of_mass_position", "ctx_max_level_volume_share",
    "ctx_volume_slope", "ctx_total_volume", "ctx_delta",
    "ctx_distribution_count", "ctx_double_mode_separation", "ctx_double_valley_depth",
    "ctx_hvn_count", "ctx_lvn_count", "ctx_hvn_dominance",
    "min_skewness", "min_entropy", "min_total_volume", "min_delta", "minute_lvn_count",
    "context_prob_D", "context_prob_P", "context_prob_b", "context_prob_trend_up",
    "context_prob_trend_down", "context_shape_confidence", "minute_shape_confidence",
    # flujo/agresión PRE-ENTRADA (causal: ventana touch->confirmación).
    # EXCLUIDAS por leak las de episodio completo (aggression_*, tape_speed_*,
    # lvn_retest_*, time_inside_lvn_zone_seconds): pueden incluir flujo posterior
    # a la entrada (hallazgo 2026-07-09, AUC inflado a 0.89).
    "delta_touch_bar", "delta_change_touch_bar",
    "pre_entry_volume_per_second", "pre_entry_delta_per_second", "pre_entry_tape_speed",
    "pre_entry_lvn_delta", "pre_entry_lvn_volume",
    "approach_speed_ticks_per_second", "zone_speed_ticks_per_second", "deceleration_ratio",
    "distance_traveled_to_lvn_ticks", "prior_move_from_open_ticks",
    # temporal
    "seconds_from_0931", "seconds_touch_to_entry",
    "retest_number", "day_of_week",
    "vwap_slope_ticks", "ema_slope_ticks", "realized_volatility",
]
CATEGORICAL_FEATURES = ["lvn_interaction", "approach", "prior_movement_direction", "context_profile_shape"]
BRACKETS = (20, 40, 60, 80)


def model_params(kind: str) -> dict:
    base = dict(iterations=400, depth=3, learning_rate=0.05, l2_leaf_reg=10,
                random_seed=7, verbose=0, allow_writing_files=False)
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", nargs="+", required=True)
    parser.add_argument("--dev-years", type=int, nargs="+", required=True)
    parser.add_argument("--val-year", type=int, required=True)
    parser.add_argument("--holdout-year", type=int, default=None,
                        help="Solo pasar cuando se decida gastar la mirada única al holdout")
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()

    paths = sorted({p for pattern in args.events for p in glob.glob(pattern, recursive=True)})
    events = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    events = events.drop_duplicates(subset=["event_id"], keep="last").copy()
    events["year"] = pd.to_datetime(events["date"]).dt.year

    numeric = [f for f in NUMERIC_FEATURES if f in events.columns]
    categorical = [f for f in CATEGORICAL_FEATURES if f in events.columns]
    for feature in categorical:
        events[feature] = events[feature].fillna("NA").astype(str)
    for feature in numeric:
        events[feature] = pd.to_numeric(events[feature], errors="coerce")
    features = numeric + categorical
    print(f"eventos {len(events)} | features causales {len(features)} "
          f"({len(numeric)} numéricas + {len(categorical)} categóricas)")

    dev = events.loc[events["year"].isin(args.dev_years)]
    val = events.loc[events["year"] == args.val_year]
    print(f"dev {sorted(args.dev_years)}: {len(dev)} | val {args.val_year}: {len(val)}")

    importance_ranks: list[pd.Series] = []
    print(f"\n{'objetivo':>14} {'n_dev':>6} {'base%':>6} {'AUC/R2 val':>11}")
    for target in BRACKETS:
        column = f"tp_sl_{target}_{target}_result"
        dev_t = dev.loc[dev[column].isin(["TP", "SL"])]
        val_t = val.loc[val[column].isin(["TP", "SL"])]
        if len(dev_t) < 60 or val_t[column].nunique() < 2:
            print(f"win_{target:>9} {len(dev_t):6d}  -- n insuficiente, se omite")
            continue
        y_dev = (dev_t[column] == "TP").astype(int)
        model = CatBoostClassifier(loss_function="Logloss", **model_params("clf"))
        pool = Pool(dev_t[features], y_dev, cat_features=categorical)
        model.fit(pool)
        auc = roc_auc_score((val_t[column] == "TP").astype(int),
                            model.predict_proba(val_t[features])[:, 1])
        print(f"win_{target:>9} {len(dev_t):6d} {100 * y_dev.mean():6.1f} {auc:11.3f}")
        imp = pd.Series(model.get_feature_importance(pool), index=features)
        importance_ranks.append(imp.rank(pct=True))

    # Winner size-agnóstico: regresión de la extensión continua (todos los eventos).
    dev_r = dev.dropna(subset=["mfe_ticks"])
    val_r = val.dropna(subset=["mfe_ticks"])
    if len(dev_r) >= 60:
        reg = CatBoostRegressor(loss_function="RMSE", **model_params("reg"))
        pool = Pool(dev_r[features], np.log1p(dev_r["mfe_ticks"].clip(lower=0)), cat_features=categorical)
        reg.fit(pool)
        pred = reg.predict(val_r[features])
        y_true = np.log1p(val_r["mfe_ticks"].clip(lower=0))
        ss_res = float(((y_true - pred) ** 2).sum())
        ss_tot = float(((y_true - y_true.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
        print(f"{'mfe_log':>14} {len(dev_r):6d} {'':6} {r2:11.3f}")
        imp = pd.Series(reg.get_feature_importance(pool), index=features)
        importance_ranks.append(imp.rank(pct=True))

    if not importance_ranks:
        print("Sin modelos entrenables.")
        return 1
    adn = pd.concat(importance_ranks, axis=1).mean(axis=1).sort_values(ascending=False)
    print(f"\n=== ADN agregado (rank medio de importancia entre {len(importance_ranks)} objetivos) ===")
    print(adn.head(args.top).to_string(float_format=lambda v: f"{v:.3f}"))

    if args.holdout_year is not None:
        hold = events.loc[events["year"] == args.holdout_year]
        print(f"\n=== HOLDOUT {args.holdout_year} (mirada única) ===")
        for target in BRACKETS:
            column = f"tp_sl_{target}_{target}_result"
            dev_t = dev.loc[dev[column].isin(["TP", "SL"])]
            hold_t = hold.loc[hold[column].isin(["TP", "SL"])]
            if len(dev_t) < 60 or hold_t[column].nunique() < 2:
                continue
            model = CatBoostClassifier(loss_function="Logloss", **model_params("clf"))
            model.fit(Pool(dev_t[features], (dev_t[column] == "TP").astype(int), cat_features=categorical))
            auc = roc_auc_score((hold_t[column] == "TP").astype(int),
                                model.predict_proba(hold_t[features])[:, 1])
            print(f"win_{target}: AUC holdout {auc:.3f} (n={len(hold_t)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
