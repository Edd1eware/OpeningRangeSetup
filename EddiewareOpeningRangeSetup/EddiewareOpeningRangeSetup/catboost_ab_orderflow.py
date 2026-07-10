#!/usr/bin/env python3
"""A/B order flow — evaluación SOLO POR EXTENSIÓN (decisión usuario 2026-07-10).

Pregunta: ¿el modelo B (estructural + flujo) rankea mejor que A (estructural) los eventos
por la EXTENSIÓN máxima que alcanzan (MFE en ticks, direccional al lado del evento)?

Sin brackets, sin WR, sin PF. Métricas de ranking OOF (GroupKFold por fecha):
  - Spearman score↔MFE (calidad global del ranking)
  - MFE mediana/media del top-40% del score vs base de todos los eventos
Umbrales de veredicto por grupo (congelados antes de correr con la muestra ampliada):
  MANTENER  : ΔMFE_med_top40 ≥ +10t y ΔSpearman ≥ +0.03 (vs A)
  MARGINAL  : ambas ≥ 0
  NO APORTA : lo demás
Eventos sin MFE direccional (UNRESOLVED/UNKNOWN) se excluyen CON conteo auditado.
"""
from __future__ import annotations

import argparse
import math

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold

from catboost_lvn_dna import CATEGORICAL_FEATURES, NUMERIC_FEATURES

FLOW_GROUPS = {
    "refill": ["zone_refill_count", "zone_refill_ratio", "zone_liq_added"],
    "velocidad": ["pre_vol_per_s", "pre_trades_per_s", "pre_ticks_per_s",
                  "zone_vol_per_s", "zone_trades_per_s", "zone_ticks_per_s", "flow_speed_ratio"],
    "agresion_delta": ["pre_buy_vol", "pre_sell_vol", "pre_delta", "pre_delta_per_s",
                       "zone_buy_vol", "zone_sell_vol", "zone_delta", "zone_delta_per_s"],
    "profundidad_liquidez": ["zone_resting_bid_mean", "zone_resting_ask_mean",
                             "zone_liq_removed", "zone_depth_levels_emptied"],
    "absorcion": ["pre_absorption_proxy", "zone_absorption_proxy"],
    "cancelacion": ["zone_cancel_proxy_ratio"],
}
TOP_PCT = 0.40


def oof_scores(frame: pd.DataFrame, features: list[str], categorical: list[str], target: np.ndarray) -> np.ndarray:
    scores = np.full(len(frame), np.nan)
    for train_idx, test_idx in GroupKFold(n_splits=5).split(frame, target, frame["date"].to_numpy()):
        model = CatBoostRegressor(iterations=300, depth=3, learning_rate=0.05, l2_leaf_reg=10,
                                  loss_function="RMSE", random_seed=7, verbose=0,
                                  allow_writing_files=False)
        model.fit(Pool(frame.iloc[train_idx][features], target[train_idx], cat_features=categorical))
        scores[test_idx] = model.predict(frame.iloc[test_idx][features])
    return scores


def evaluate(mfe: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    mask = ~np.isnan(scores)
    y, s = mfe[mask], scores[mask]
    rho = float(spearmanr(s, y).statistic) if len(y) > 10 else math.nan
    cut = np.quantile(s, 1 - TOP_PCT)
    top = y[s >= cut]
    return {
        "spearman": rho,
        "n_top": int(len(top)),
        "mfe_med_top": float(np.median(top)) if len(top) else math.nan,
        "mfe_mean_top": float(np.mean(top)) if len(top) else math.nan,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", required=True)
    args = parser.parse_args()
    data = pd.read_csv(args.merged)
    total = len(data)
    data["mfe_ticks"] = pd.to_numeric(data["mfe_ticks"], errors="coerce")
    data = data.dropna(subset=["mfe_ticks"]).reset_index(drop=True)
    print(f"eventos {total} | con MFE direccional {len(data)} | excluidos auditados {total - len(data)} "
          "(UNRESOLVED/UNKNOWN sin lado)")

    structural_numeric = [f for f in NUMERIC_FEATURES if f in data.columns]
    categorical = [f for f in CATEGORICAL_FEATURES if f in data.columns]
    for feature in categorical:
        data[feature] = data[feature].fillna("NA").astype(str)
    flow_all = [f for group in FLOW_GROUPS.values() for f in group if f in data.columns]
    for feature in structural_numeric + flow_all:
        data[feature] = pd.to_numeric(data[feature], errors="coerce")

    mfe = data["mfe_ticks"].to_numpy(dtype=float)
    target = np.log1p(np.clip(mfe, 0, None))
    base_med = float(np.median(mfe))
    print(f"MFE base (todos): med {base_med:.0f}t | media {mfe.mean():.0f}t")

    features_a = structural_numeric + categorical
    result_a = evaluate(mfe, oof_scores(data, features_a, categorical, target))
    result_b = evaluate(mfe, oof_scores(data, structural_numeric + flow_all + categorical, categorical, target))
    print(f"\nA estructural : Spearman {result_a['spearman']:+.3f} | MFE top{TOP_PCT:.0%} med {result_a['mfe_med_top']:.0f}t media {result_a['mfe_mean_top']:.0f}t (n={result_a['n_top']})")
    print(f"B +flujo      : Spearman {result_b['spearman']:+.3f} | MFE top{TOP_PCT:.0%} med {result_b['mfe_med_top']:.0f}t media {result_b['mfe_mean_top']:.0f}t (n={result_b['n_top']})")

    print("\n--- marginal por grupo (A+grupo vs A) ---")
    rows = []
    for group_name, group_features in FLOW_GROUPS.items():
        present = [f for f in group_features if f in data.columns]
        if not present:
            continue
        result_g = evaluate(mfe, oof_scores(data, structural_numeric + present + categorical, categorical, target))
        d_rho = result_g["spearman"] - result_a["spearman"]
        d_med = result_g["mfe_med_top"] - result_a["mfe_med_top"]
        verdict = ("MANTENER" if d_med >= 10 and d_rho >= 0.03
                   else "Marginal" if d_med >= 0 and d_rho >= 0 else "No aporta")
        print(f"  {group_name:22s} dSpearman {d_rho:+.3f} | dMFE_med_top {d_med:+.0f}t -> {verdict}")
        rows.append({"grupo": group_name, "dSpearman": d_rho, "dMFE_med_top40": d_med, "veredicto": verdict})
    pd.DataFrame(rows).to_csv("outputs/orderflow_ab_extension_table.csv", index=False)
    print("\ntabla -> outputs/orderflow_ab_extension_table.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
