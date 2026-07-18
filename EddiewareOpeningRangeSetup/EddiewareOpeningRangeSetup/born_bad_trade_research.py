"""Investigacion causal de trades que nacen mal (Grupo D).

Es un analizador observacional. No escribe archivos consumidos por ATAS, no
modifica entradas/salidas y usa MFE/MAE/resultado exclusivamente como etiquetas.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score
from sklearn.preprocessing import StandardScaler

import absorption_breakout_research as base


TELEGRAM_TITLE = "ANALISIS  FAMILIAS A, B, C, ETC.\nGRUPO D - TRADES QUE NACEN MAL"
RESULT_TICKS_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
OFFICIAL_CUTOFF_DATE = pd.Timestamp("2026-07-16")


DERIVED_FEATURES = [
    "seconds_from_open",
    "minute_from_open",
    "weekday_index",
    "month_index",
    "execution_side_sign",
    "or_position_fraction",
    "distance_nearest_or_edge_ticks",
    "distance_nearest_profile_reference_ticks",
    "vwap_poc_spread_ticks",
    "signed_velocity_decay_1_5",
    "signed_delta_decay_1_5",
    "execution_cvd_alignment",
]

RESPONSE_METRICS = [
    "Directional_Displacement_Ticks",
    "Response_MFE_Ticks",
    "Response_MAE_Ticks",
    "Acceptance_Dwell_Ratio",
    "Reclaim_Count",
    "Rejection_Speed_TPS",
    "Directional_Delta",
    "Response_Volume",
    "Effort_Result_Delta",
    "Effort_Result_Volume",
    "Momentum_Survival_Ratio",
    "Rotation_Index",
    "Local_Entropy",
    "Path_Efficiency",
    "Response_POC_Migration_Ticks",
]


def _physical_family(feature: str) -> str:
    name = feature.lower()
    if "clv" in name:
        return "CLV"
    if any(token in name for token in ("accept", "reclaim", "rejection", "retest", "dwell")):
        return "ACCEPTANCE_RECLAIM"
    if any(token in name for token in ("profile", "poc", "vah", "val", "hvn", "lvn", "vwap", "or_")):
        return "AUCTION_THEORY"
    if any(token in name for token in ("entropy", "rotation", "sequence", "path_efficiency")):
        return "TEMPORAL_SEQUENCE"
    if any(token in name for token in ("effort_result", "price_per", "impact_per", "absorption_pressure", "efficiency_score")):
        return "EFFORT_VS_RESULT"
    if any(token in name for token in ("persistence", "survival", "decay", "acceleration", "velocity")):
        return "PERSISTENCE_EXHAUSTION"
    if any(token in name for token in ("delta", "imbalance", "volume", "trade_size", "contracts")):
        return "FLOW_BURST_QUALITY"
    if any(token in name for token in ("second", "minute", "weekday", "month")):
        return "TIME_REGIME"
    return "OTHER_CAUSAL_CONTEXT"


def _report_flag(value: object) -> int:
    """Serializa flags estadisticos faltantes sin alterar el calculo."""
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return 0 if pd.isna(numeric) else int(numeric)


def _result_ticks(frame: pd.DataFrame) -> pd.Series:
    result = pd.Series(np.nan, index=frame.index, dtype=float)
    for column in ("Result_After_Slippage_Ticks", "result TP SL BE"):
        if column not in frame:
            continue
        parsed = frame[column].astype(str).str.extract(f"({RESULT_TICKS_PATTERN.pattern})", expand=False)
        result = result.fillna(pd.to_numeric(parsed, errors="coerce"))
    labels = frame.get("Result_Label", pd.Series("", index=frame.index)).astype(str).str.upper()
    result = result.mask(result.isna() & labels.eq("TP"), 1.0)
    result = result.mask(result.isna() & labels.eq("SL"), -1.0)
    result = result.mask(result.isna() & labels.eq("BE"), 0.0)
    return result


def _add_causal_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    timestamp = pd.to_datetime(frame["prediction_timestamp"], utc=True, errors="coerce")
    ny = timestamp.dt.tz_convert("America/New_York")
    frame["seconds_from_open"] = (
        (ny.dt.hour * 3600 + ny.dt.minute * 60 + ny.dt.second) - (9 * 3600 + 30 * 60)
    )
    frame["minute_from_open"] = frame["seconds_from_open"] / 60.0
    frame["weekday_index"] = ny.dt.weekday
    frame["month_index"] = ny.dt.month

    execution_side = frame.get("ExecutionSide", pd.Series("", index=frame.index)).astype(str).str.upper()
    frame["execution_side_sign"] = np.where(execution_side.eq("BUY"), 1.0, -1.0)
    frame["or_position_fraction"] = (
        pd.to_numeric(frame.get("Dist_OR_Low_Ticks"), errors="coerce") /
        pd.to_numeric(frame.get("OR_WidthTicks"), errors="coerce").abs().clip(lower=1)
    )
    frame["distance_nearest_or_edge_ticks"] = pd.concat(
        [
            pd.to_numeric(frame.get("Dist_OR_High_Ticks"), errors="coerce").abs(),
            pd.to_numeric(frame.get("Dist_OR_Low_Ticks"), errors="coerce").abs(),
        ],
        axis=1,
    ).min(axis=1)
    profile_columns = [
        "Dist_POC_Ticks", "Dist_VAH_Ticks", "Dist_VAL_Ticks",
        "Dist_HVN_Ticks", "Dist_LVN_Ticks",
    ]
    frame["distance_nearest_profile_reference_ticks"] = frame[profile_columns].apply(
        pd.to_numeric, errors="coerce"
    ).abs().min(axis=1)
    frame["vwap_poc_spread_ticks"] = (
        pd.to_numeric(frame.get("Dist_VWAP_Ticks"), errors="coerce") -
        pd.to_numeric(frame.get("Dist_POC_Ticks"), errors="coerce")
    ).abs()
    sign = frame["execution_side_sign"]
    frame["signed_velocity_decay_1_5"] = sign * (
        pd.to_numeric(frame.get("Velocity1s"), errors="coerce") -
        pd.to_numeric(frame.get("Velocity5s"), errors="coerce")
    )
    frame["signed_delta_decay_1_5"] = sign * (
        pd.to_numeric(frame.get("Delta1s"), errors="coerce") -
        pd.to_numeric(frame.get("Delta5s"), errors="coerce") / 5.0
    )
    cvd = pd.to_numeric(frame.get("Cumulative_Delta_AtEntry"), errors="coerce")
    frame["execution_cvd_alignment"] = sign * np.sign(cvd)
    return frame


def _classify(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["realized_ticks_for_label"] = _result_ticks(frame)
    frame["MFE_ticks"] = pd.to_numeric(frame.get("MFE_ticks"), errors="coerce")
    frame["MAE_ticks"] = pd.to_numeric(frame.get("MAE_ticks"), errors="coerce")
    result = frame.get("Result_Label", pd.Series("", index=frame.index)).astype(str).str.upper()
    winner = frame["realized_ticks_for_label"].gt(0) | result.eq("TP")
    loser = frame["realized_ticks_for_label"].lt(0) | result.eq("SL")

    frame["born_bad_group"] = "EXCLUDED_OTHER_EXIT"
    frame["born_bad_reason"] = "BE/time/otra salida; no entra en A/B/C/D"
    frame.loc[winner, "born_bad_group"] = "A_WINNER"
    frame.loc[winner, "born_bad_reason"] = "Resultado realizado positivo"
    frame.loc[loser & frame["MFE_ticks"].gt(30), "born_bad_group"] = "B_LOSER_MFE_GT_30"
    frame.loc[loser & frame["MFE_ticks"].gt(30), "born_bad_reason"] = "Perdedor con MFE > 30 ticks"
    normal = loser & frame["MFE_ticks"].gt(2) & frame["MFE_ticks"].le(30)
    frame.loc[normal, "born_bad_group"] = "C_LOSER_MFE_3_TO_30"
    frame.loc[normal, "born_bad_reason"] = "Perdedor con 2 < MFE <= 30 ticks"
    born_bad = loser & frame["MFE_ticks"].le(2)
    frame.loc[born_bad, "born_bad_group"] = "D_BORN_BAD_MFE_LE_2"
    frame.loc[born_bad, "born_bad_reason"] = "Perdedor con MFE <= 2 ticks"
    return frame


def _comparison_dataset(dataset: pd.DataFrame, comparator: str) -> pd.DataFrame:
    if comparator == "A":
        keep = dataset["born_bad_group"].isin(["D_BORN_BAD_MFE_LE_2", "A_WINNER"])
        compared = dataset.loc[keep].copy()
        compared["family"] = np.where(
            compared["born_bad_group"].eq("D_BORN_BAD_MFE_LE_2"),
            "A_TRUE_ABSORPTION",
            "B_CLEAN_BREAKOUT",
        )
    else:
        keep = dataset["born_bad_group"].isin(
            ["A_WINNER", "B_LOSER_MFE_GT_30", "C_LOSER_MFE_3_TO_30", "D_BORN_BAD_MFE_LE_2"]
        )
        compared = dataset.loc[keep].copy()
        compared["family"] = np.where(
            compared["born_bad_group"].eq("D_BORN_BAD_MFE_LE_2"),
            "A_TRUE_ABSORPTION",
            "B_CLEAN_BREAKOUT",
        )
    return compared


def _run_comparison(dataset: pd.DataFrame, comparator: str) -> dict[str, pd.DataFrame]:
    compared = _comparison_dataset(dataset, comparator)
    if compared.empty or compared["family"].nunique() < 2:
        empty = pd.DataFrame()
        return {"dataset": compared, "statistics": empty, "importance": empty,
                "validation": empty, "models": empty, "ranking": empty}
    statistics = base._statistical_tests(compared)
    importance, validation, models = base._model_and_rankings(compared, statistics)
    ranking = base._rankings(statistics, importance, validation)
    return {
        "dataset": compared,
        "statistics": statistics,
        "importance": importance,
        "validation": validation,
        "models": models,
        "ranking": ranking,
    }


def _usable_features(dataset: pd.DataFrame, requested: list[str]) -> list[str]:
    usable: list[str] = []
    for feature in requested:
        if feature not in dataset:
            continue
        values = pd.to_numeric(dataset[feature], errors="coerce")
        if values.notna().sum() >= 5 and values.nunique(dropna=True) >= 2:
            usable.append(feature)
    return usable


def _clv_audit(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = [
        "Directional_CLV_AtEntry",
        "Causal_Entry_High_AtEntry",
        "Causal_Entry_Low_AtEntry",
        "Causal_Entry_Observation_Count_AtEntry",
        "Causal_Entry_First_Timestamp_UTC",
        "Causal_Entry_Last_Timestamp_UTC",
        "Causal_Entry_Source_AtEntry",
        "CLV_Causality_Status_AtEntry",
    ]
    missing = [column for column in required if column not in dataset]
    if missing:
        return pd.DataFrame([{
            "decision": "REJECT_UNAUDITABLE",
            "reason": "missing columns: " + ", ".join(missing),
        }]), pd.DataFrame()

    frame = dataset.copy()
    high = pd.to_numeric(frame["Causal_Entry_High_AtEntry"], errors="coerce")
    low = pd.to_numeric(frame["Causal_Entry_Low_AtEntry"], errors="coerce")
    entry = pd.to_numeric(frame["Entry_price"], errors="coerce")
    observed = pd.to_numeric(frame["Directional_CLV_AtEntry"], errors="coerce")
    side = frame["ExecutionSide"].astype(str).str.upper().map({"BUY": 1.0, "SELL": -1.0})
    spread = high - low
    expected = side * ((2.0 * entry - high - low) / spread.where(spread.gt(0)))
    expected = expected.clip(-1.0, 1.0)
    prediction = pd.to_datetime(frame["prediction_timestamp"], utc=True, errors="coerce")
    first = pd.to_datetime(frame["Causal_Entry_First_Timestamp_UTC"], utc=True, errors="coerce")
    last = pd.to_datetime(frame["Causal_Entry_Last_Timestamp_UTC"], utc=True, errors="coerce")
    source_ok = frame["Causal_Entry_Source_AtEntry"].astype(str).str.startswith("MARKET_TRADE_EVENTS")
    status_ok = frame["CLV_Causality_Status_AtEntry"].astype(str).eq("CAUSAL_EVENT_RANGE")
    observations_ok = pd.to_numeric(
        frame["Causal_Entry_Observation_Count_AtEntry"], errors="coerce"
    ).ge(2)
    timestamp_ok = first.notna() & last.notna() & prediction.notna() & first.le(last) & last.le(prediction)
    formula_error = (observed - expected).abs()
    formula_ok = observed.notna() & expected.notna() & formula_error.le(1e-9)
    row_ok = source_ok & status_ok & observations_ok & timestamp_ok & formula_ok

    detail = pd.DataFrame({
        "fecha": frame.get("fecha"),
        "BurstId": frame.get("BurstId"),
        "prediction_timestamp": prediction,
        "causal_first_timestamp": first,
        "causal_last_timestamp": last,
        "source": frame["Causal_Entry_Source_AtEntry"],
        "status": frame["CLV_Causality_Status_AtEntry"],
        "observed_clv": observed,
        "recomputed_clv": expected,
        "absolute_formula_error": formula_error,
        "timestamp_ok": timestamp_ok.astype(int),
        "source_ok": source_ok.astype(int),
        "observation_count_ok": observations_ok.astype(int),
        "formula_ok": formula_ok.astype(int),
        "causal_row_ok": row_ok.astype(int),
        "decision": np.where(row_ok, "ACCEPT_CAUSAL", "EXCLUDE_FROM_MODELS"),
    })

    comparison_columns = [
        "Delta1s", "Delta3s", "Delta5s", "DeltaChangeZScore",
        "Velocity1s", "Velocity3s", "Velocity5s",
        "Buy_Imbalance_Count_AtEntry", "Sell_Imbalance_Count_AtEntry",
        "PreEntry_Directional_Delta_Share3_AtEntry",
    ]
    correlations: list[dict[str, object]] = []
    accepted = frame.loc[row_ok].copy()
    for feature in comparison_columns:
        if feature not in accepted:
            continue
        pair = accepted[["Directional_CLV_AtEntry", feature]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair) < 5 or pair[feature].nunique() < 2:
            continue
        correlations.append({
            "feature": feature,
            "physical_family": _physical_family(feature),
            "n": len(pair),
            "pearson_with_causal_clv": pair.corr(method="pearson").iloc[0, 1],
            "spearman_with_causal_clv": pair.corr(method="spearman").iloc[0, 1],
        })
    return detail, pd.DataFrame(correlations)


def _independence_analysis(
    dataset: pd.DataFrame,
    features: list[str],
) -> dict[str, pd.DataFrame]:
    causal = dataset.loc[dataset["causal_row_flag"]].copy()
    features = _usable_features(causal, features)
    if len(features) < 2:
        empty = pd.DataFrame()
        return {name: empty for name in (
            "correlations", "clusters", "pca_loadings", "pca_variance",
            "vif", "mutual_information", "family_independence",
        )}

    numeric = causal[features].apply(pd.to_numeric, errors="coerce")
    spearman = numeric.corr(method="spearman").fillna(0.0)
    pearson = numeric.corr(method="pearson").fillna(0.0)
    correlation_rows: list[dict[str, object]] = []
    mi_rows: list[dict[str, object]] = []
    imputed = SimpleImputer(strategy="median").fit_transform(numeric)
    for i, feature_a in enumerate(features):
        for j in range(i + 1, len(features)):
            feature_b = features[j]
            rho = float(spearman.iloc[i, j])
            r = float(pearson.iloc[i, j])
            correlation_rows.append({
                "feature_a": feature_a,
                "family_a": _physical_family(feature_a),
                "feature_b": feature_b,
                "family_b": _physical_family(feature_b),
                "spearman": rho,
                "pearson": r,
                "abs_spearman": abs(rho),
                "redundant_ge_0_90": int(abs(rho) >= 0.90 or abs(r) >= 0.90),
            })
            mi_ab = mutual_info_regression(
                imputed[:, [i]], imputed[:, j], random_state=base.RANDOM_SEED
            )[0]
            mi_ba = mutual_info_regression(
                imputed[:, [j]], imputed[:, i], random_state=base.RANDOM_SEED
            )[0]
            mi_rows.append({
                "feature_a": feature_a,
                "feature_b": feature_b,
                "mutual_information_symmetric": float((mi_ab + mi_ba) / 2.0),
            })

    distance = (1.0 - spearman.abs().clip(0.0, 1.0)).to_numpy(copy=True)
    np.fill_diagonal(distance, 0.0)
    hierarchy = linkage(squareform(distance, checks=False), method="average")
    labels = fcluster(hierarchy, t=0.35, criterion="distance")
    clusters = pd.DataFrame({
        "feature": features,
        "physical_family": [_physical_family(feature) for feature in features],
        "correlation_cluster_abs_spearman_ge_0_65": labels,
    }).sort_values(["correlation_cluster_abs_spearman_ge_0_65", "feature"])

    scaled = StandardScaler().fit_transform(imputed)
    n_components = min(10, scaled.shape[0], scaled.shape[1])
    pca = base.PCA(n_components=n_components, random_state=base.RANDOM_SEED).fit(scaled)
    pca_variance = pd.DataFrame({
        "component": [f"PC{i + 1}" for i in range(n_components)],
        "explained_variance_ratio": pca.explained_variance_ratio_,
        "cumulative_explained_variance": np.cumsum(pca.explained_variance_ratio_),
    })
    pca_loadings = pd.DataFrame(
        pca.components_.T,
        index=features,
        columns=[f"PC{i + 1}" for i in range(n_components)],
    ).reset_index(names="feature")
    pca_loadings.insert(1, "physical_family", pca_loadings["feature"].map(_physical_family))

    vif_rows: list[dict[str, object]] = []
    matrix_rank = int(np.linalg.matrix_rank(scaled))
    for index, feature in enumerate(features):
        target = scaled[:, index]
        predictors = np.delete(scaled, index, axis=1)
        design = np.column_stack([np.ones(len(predictors)), predictors])
        coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
        residual = target - design @ coefficients
        denominator = float(np.sum((target - target.mean()) ** 2))
        r_squared = 1.0 - float(np.sum(residual ** 2)) / denominator if denominator > 0 else np.nan
        vif = np.inf if pd.notna(r_squared) and r_squared >= 1.0 - 1e-12 else 1.0 / (1.0 - r_squared)
        vif_rows.append({
            "feature": feature,
            "physical_family": _physical_family(feature),
            "vif": vif,
            "r_squared_against_other_features": r_squared,
            "design_matrix_rank": matrix_rank,
            "rank_deficient": int(matrix_rank < scaled.shape[1]),
        })

    family_rows: list[dict[str, object]] = []
    correlation_frame = pd.DataFrame(correlation_rows)
    for (family_a, family_b), group in correlation_frame.groupby(["family_a", "family_b"]):
        family_rows.append({
            "family_a": family_a,
            "family_b": family_b,
            "pairs": len(group),
            "median_abs_spearman": group["abs_spearman"].median(),
            "p90_abs_spearman": group["abs_spearman"].quantile(0.90),
            "redundant_pairs_ge_0_90": int(group["redundant_ge_0_90"].sum()),
        })

    discovery = causal.loc[causal["split"].eq("discovery")].copy()
    if not discovery.empty:
        discovery_x = SimpleImputer(strategy="median").fit_transform(
            discovery[features].apply(pd.to_numeric, errors="coerce")
        )
        discovery_y = discovery["born_bad_group"].eq("D_BORN_BAD_MFE_LE_2").astype(int)
        if discovery_y.nunique() == 2:
            label_mi = mutual_info_classif(
                discovery_x, discovery_y, random_state=base.RANDOM_SEED
            )
            for feature, value in zip(features, label_mi):
                mi_rows.append({
                    "feature_a": feature,
                    "feature_b": "D_LABEL_DISCOVERY_ONLY",
                    "mutual_information_symmetric": float(value),
                })

    return {
        "correlations": correlation_frame.sort_values("abs_spearman", ascending=False),
        "clusters": clusters,
        "pca_loadings": pca_loadings,
        "pca_variance": pca_variance,
        "vif": pd.DataFrame(vif_rows).sort_values("vif", ascending=False),
        "mutual_information": pd.DataFrame(mi_rows).sort_values(
            "mutual_information_symmetric", ascending=False
        ),
        "family_independence": pd.DataFrame(family_rows).sort_values(
            "median_abs_spearman", ascending=False
        ),
    }


def _temporal_validation(
    dataset: pd.DataFrame,
    features: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    annual_rows: list[dict[str, object]] = []
    walk_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    features = _usable_features(dataset, features)
    years = sorted(pd.to_datetime(dataset["prediction_timestamp"], utc=True).dt.year.dropna().unique())

    for comparator in ("A", "REST"):
        compared = _comparison_dataset(dataset, comparator)
        compared["year"] = pd.to_datetime(compared["prediction_timestamp"], utc=True).dt.year
        compared["is_d"] = compared["born_bad_group"].eq("D_BORN_BAD_MFE_LE_2")
        for feature in features:
            directions: list[float] = []
            for year in years:
                yearly = compared.loc[compared["year"].eq(year)]
                d_values = pd.to_numeric(yearly.loc[yearly["is_d"], feature], errors="coerce").dropna().to_numpy()
                other_values = pd.to_numeric(yearly.loc[~yearly["is_d"], feature], errors="coerce").dropna().to_numpy()
                direction = np.sign(np.median(d_values) - np.median(other_values)) if len(d_values) and len(other_values) else np.nan
                if pd.notna(direction) and direction != 0:
                    directions.append(float(direction))
                annual_rows.append({
                    "comparison": f"D_vs_{comparator}",
                    "year": int(year),
                    "feature": feature,
                    "physical_family": _physical_family(feature),
                    "n_D": len(d_values),
                    "n_other": len(other_values),
                    "median_D": np.median(d_values) if len(d_values) else np.nan,
                    "median_other": np.median(other_values) if len(other_values) else np.nan,
                    "direction_D_minus_other": direction,
                    "cliffs_delta_D_minus_other": base._cliffs_delta(d_values, other_values),
                })

            valid_fold_scores: list[float] = []
            fold_directions: list[float] = []
            for test_year in years[1:]:
                train = compared.loc[compared["year"].lt(test_year)]
                test = compared.loc[compared["year"].eq(test_year)]
                train_d = pd.to_numeric(train.loc[train["is_d"], feature], errors="coerce").dropna()
                train_other = pd.to_numeric(train.loc[~train["is_d"], feature], errors="coerce").dropna()
                test_values = pd.to_numeric(test[feature], errors="coerce")
                valid_test = test_values.notna()
                y_test = test.loc[valid_test, "is_d"].astype(int)
                status = "INSUFFICIENT_SAMPLE"
                score = np.nan
                threshold = np.nan
                direction = np.nan
                if len(train_d) >= 4 and len(train_other) >= 4 and y_test.nunique() == 2:
                    direction = np.sign(train_d.median() - train_other.median())
                    threshold = float((train_d.median() + train_other.median()) / 2.0)
                    if direction != 0:
                        predicts_d = test_values.loc[valid_test].ge(threshold) if direction > 0 else test_values.loc[valid_test].le(threshold)
                        score = balanced_accuracy_score(y_test, predicts_d.astype(int))
                        status = "OK"
                        valid_fold_scores.append(float(score))
                        fold_directions.append(float(direction))
                walk_rows.append({
                    "comparison": f"D_vs_{comparator}",
                    "feature": feature,
                    "physical_family": _physical_family(feature),
                    "train_years": f"{min(years)}-{int(test_year) - 1}" if years else "",
                    "test_year": int(test_year),
                    "is_latest_year_oos": int(test_year == max(years)),
                    "n_train_D": len(train_d),
                    "n_train_other": len(train_other),
                    "n_test": int(valid_test.sum()),
                    "threshold_train_only": threshold,
                    "direction_train_only": direction,
                    "balanced_accuracy_oos": score,
                    "status": status,
                })

            nonzero_annual = [value for value in directions if value != 0]
            direction_stable = len(nonzero_annual) >= 3 and len(set(nonzero_annual)) == 1
            wf_direction_stable = len(fold_directions) >= 2 and len(set(fold_directions)) == 1
            latest = [row for row in walk_rows if row["comparison"] == f"D_vs_{comparator}" and row["feature"] == feature and row["is_latest_year_oos"]]
            latest_score = latest[-1]["balanced_accuracy_oos"] if latest else np.nan
            summary_rows.append({
                "comparison": f"D_vs_{comparator}",
                "feature": feature,
                "physical_family": _physical_family(feature),
                "years_with_nonzero_effect": len(nonzero_annual),
                "annual_direction_stable_min_3_years": int(direction_stable),
                "valid_walk_forward_folds": len(valid_fold_scores),
                "median_walk_forward_balanced_accuracy": np.median(valid_fold_scores) if valid_fold_scores else np.nan,
                "walk_forward_direction_stable": int(wf_direction_stable),
                "latest_year_oos_balanced_accuracy": latest_score,
                "passes_confirmation_gate": int(
                    direction_stable and
                    wf_direction_stable and
                    len(valid_fold_scores) >= 2 and
                    np.median(valid_fold_scores) > 0.50 and
                    pd.notna(latest_score) and latest_score > 0.50
                ),
            })

    return (
        pd.DataFrame(annual_rows),
        pd.DataFrame(walk_rows),
        pd.DataFrame(summary_rows).sort_values(
            ["passes_confirmation_gate", "median_walk_forward_balanced_accuracy"],
            ascending=[False, False],
        ),
    )


def _post_burst_response_analysis(
    results_folder: Path,
    dataset: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    path = results_folder / "burst_response_events.csv"
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame([{
            "status": "NO_RESPONSE_FILE",
            "model_eligibility": "POST_BURST_ONLY",
        }])
    responses = pd.read_csv(path, low_memory=False)
    if "Detector_VERSION" in responses:
        responses = responses.loc[
            responses["Detector_VERSION"].astype(str).eq(base.EXPECTED_BURST_VERSION)
        ].copy()
    responses["Response_Available_Timestamp_UTC"] = pd.to_datetime(
        responses["Response_Available_Timestamp_UTC"], utc=True, errors="coerce"
    )
    responses["Burst_Timestamp_UTC"] = pd.to_datetime(
        responses["Burst_Timestamp_UTC"], utc=True, errors="coerce"
    )
    responses["Burst_Feature_Available_Timestamp_UTC"] = pd.to_datetime(
        responses["Burst_Feature_Available_Timestamp_UTC"], utc=True, errors="coerce"
    )
    available = responses.get(
        "AvailableBeforeEntry", pd.Series(1, index=responses.index)
    )
    eligibility = responses.get(
        "Model_Eligibility", pd.Series("", index=responses.index)
    )
    eligibility_ok = available.astype(str).eq("0") & eligibility.astype(str).eq(
        "POST_BURST_ONLY"
    )
    expected_available = responses["Burst_Feature_Available_Timestamp_UTC"] + pd.to_timedelta(
        pd.to_numeric(responses["Response_Horizon_Seconds"], errors="coerce"), unit="s"
    )
    time_ok = responses["Response_Available_Timestamp_UTC"].eq(expected_available)
    audit = pd.DataFrame([{
        "status": "OK" if eligibility_ok.all() and time_ok.all() else "CAUSAL_CONTRACT_VIOLATION",
        "rows": len(responses),
        "post_burst_only_rows": int(eligibility_ok.sum()),
        "timestamp_order_ok_rows": int(time_ok.sum()),
        "used_as_preentry_predictor": 0,
        "model_eligibility": "POST_BURST_ONLY",
    }])
    labels = dataset[["BurstId", "born_bad_group", "fecha"]].drop_duplicates("BurstId", keep="last")
    merged = responses.merge(labels, on="BurstId", how="inner", validate="many_to_one")
    for metric in RESPONSE_METRICS:
        if metric in merged:
            merged[metric] = pd.to_numeric(merged[metric], errors="coerce")
    stats_rows: list[dict[str, object]] = []
    for (horizon, group_name), group in merged.groupby(["Response_Horizon_Seconds", "born_bad_group"]):
        for metric in RESPONSE_METRICS:
            if metric not in group:
                continue
            values = group[metric].dropna()
            stats_rows.append({
                "response_horizon_seconds": horizon,
                "born_bad_group": group_name,
                "metric": metric,
                "n": len(values),
                "mean": values.mean() if len(values) else np.nan,
                "median": values.median() if len(values) else np.nan,
                "std": values.std(ddof=1) if len(values) > 1 else np.nan,
                "p25": values.quantile(0.25) if len(values) else np.nan,
                "p75": values.quantile(0.75) if len(values) else np.nan,
                "model_eligibility": "POST_BURST_ONLY",
            })
    return merged, pd.DataFrame(stats_rows), audit


def _feature_proposals() -> pd.DataFrame:
    rows = [
        ("seconds_from_open", "(entry_ny - 09:30 NY).total_seconds", "Régimen temporal de apertura", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("or_position_fraction", "(price-OR_low)/max(OR_width,1 tick)", "Entrada extendida o dentro del balance", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("execution_cvd_alignment", "side_sign*sign(session_CVD_at_entry)", "Conflicto con agresión acumulada", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("velocity_decay_1_5", "side_sign*(velocity_1s-velocity_5s)", "Impulso que se extingue al disparar", "HIGH", "EASY", "MEDIUM", "AVAILABLE_NOW"),
        ("delta_decay_1_5", "side_sign*(delta_1s-delta_5s/5)", "Agresión instantánea sin persistencia", "HIGH", "EASY", "MEDIUM", "AVAILABLE_NOW"),
        ("nearest_profile_reference", "min(|dPOC|,|dVAH|,|dVAL|,|dHVN|,|dLVN|)", "Choque inmediato contra liquidez estructural", "HIGH", "EASY", "LOW", "AVAILABLE_NOW"),
        ("prior_atr_ticks", "ATR_N de barras cerradas antes de entry", "Normaliza SL/OR por volatilidad", "HIGH", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("overnight_range_ticks", "(ON_high-ON_low)/tick hasta 09:29:59", "Compresión/expansión previa", "HIGH", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("opening_gap_atr", "(RTH_open-prior_settle)/prior_ATR", "Inventario overnight y repricing", "HIGH", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("vwap_slope_ticks_per_min", "OLS slope VWAP causal en últimos N minutos", "Dirección/curvatura del valor negociado", "HIGH", "MEDIUM", "MEDIUM", "ADD_EXPORTER_NEXT"),
        ("poc_migration_ticks_per_min", "(POC_now-POC_Nmin_ago)/(N*min*tick)", "Migración del valor contra la entrada", "HIGH", "HARD", "MEDIUM", "ADD_EXPORTER_NEXT"),
        ("profile_shape_moments", "skew,kurtosis,modes de volumen por precio causal", "P/b/D/B/doble distribución sin etiqueta subjetiva", "MEDIUM", "HARD", "MEDIUM", "ADD_EXPORTER_LATER"),
        ("acceptance_dwell_ratio", "time_inside_level_band/window_before_entry", "Acceptance frente a rechazo instantáneo", "HIGH", "HARD", "MEDIUM", "ADD_EXPORTER_NEXT"),
        ("level_retest_count", "count(cross/retest causal de OR/VA/POC)", "Nivel debilitado por pruebas repetidas", "MEDIUM", "MEDIUM", "LOW", "ADD_EXPORTER_NEXT"),
        ("refill_after_sweep_ratio", "added_size/consumed_size antes de entry", "Absorción real frente a vacío de liquidez", "HIGH", "HARD", "HIGH", "REQUIRES_REPLAYABLE_BOOK"),
        ("book_imbalance_multilevel", "sum_bid_depth_L/sum_ask_depth_L", "Asimetría de profundidad preentrada", "MEDIUM", "HARD", "HIGH", "REQUIRES_REPLAYABLE_BOOK"),
    ]
    return pd.DataFrame(rows, columns=[
        "feature", "formula", "market_mechanism", "expected_impact",
        "implementation", "overfit_risk", "recommendation",
    ])


def _plots(dataset: pd.DataFrame, comparisons: dict[str, dict[str, pd.DataFrame]], output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    counts = dataset["born_bad_group"].value_counts()
    fig, ax = plt.subplots(figsize=(10, 5))
    counts.plot(kind="bar", ax=ax, color="#2563eb")
    ax.set_title("Familias de trades")
    ax.set_ylabel("Trades")
    fig.tight_layout()
    path = output / "group_counts.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    for label, comparison in comparisons.items():
        ranking = comparison["ranking"]
        if ranking.empty:
            continue
        top = ranking.head(10).iloc[::-1]
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(top["feature"], top["evidence_score"], color="#dc2626")
        ax.set_title(f"Grupo D vs {label}: evidencia preentrada")
        ax.set_xlabel("Evidence score")
        fig.tight_layout()
        path = output / f"ranking_D_vs_{label}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


def _report(
    dataset: pd.DataFrame,
    comparisons: dict[str, dict[str, pd.DataFrame]],
    proposals: pd.DataFrame,
    clv_audit: pd.DataFrame,
    clv_correlations: pd.DataFrame,
    independence: dict[str, pd.DataFrame],
    temporal_summary: pd.DataFrame,
    response_audit: pd.DataFrame,
    response_statistics: pd.DataFrame,
    output: Path,
) -> str:
    counts = dataset["born_bad_group"].value_counts().to_dict()
    causal = dataset.loc[dataset["causal_row_flag"]]
    years = sorted(pd.to_datetime(dataset["prediction_timestamp"], utc=True).dt.year.dropna().unique())
    confirmed = temporal_summary.loc[
        temporal_summary.get("passes_confirmation_gate", pd.Series(dtype=int)).eq(1)
    ] if not temporal_summary.empty else pd.DataFrame()
    clv_ok = int(clv_audit.get("causal_row_ok", pd.Series(dtype=int)).sum()) if not clv_audit.empty else 0
    clv_total = len(clv_audit) if "causal_row_ok" in clv_audit else 0
    lines = [
        "# Investigación cuantitativa — Trades que nacen mal",
        "",
        "## Resultado principal",
        "",
    ]
    robust_union: list[str] = []
    for comparison in comparisons.values():
        ranking = comparison["ranking"]
        if not ranking.empty:
            robust_union.extend(ranking.loc[ranking["robust_candidate"].eq(1), "feature"].tolist())
    robust_union = list(dict.fromkeys(robust_union))
    if robust_union:
        lines.append(
            "Las siguientes variables preentrada superaron el criterio estadístico pre-registrado: "
            + ", ".join(robust_union[:10])
            + ". Esto demuestra separación observacional, no autoriza todavía un filtro."
        )
    else:
        lines.append(
            "Ninguna variable disponible superó simultáneamente significancia corregida, tamaño de efecto "
            "y estabilidad cronológica. La hipótesis no queda demostrada con el dataset actual y no se "
            "autoriza modificar la estrategia."
        )
    lines.extend([
        "",
        "## Definición congelada",
        "",
        "- A: trade ganador (resultado realizado positivo).",
        "- B: trade perdedor con MFE > 30 ticks.",
        "- C: trade perdedor con 2 < MFE <= 30 ticks.",
        "- D: trade perdedor con MFE <= 2 ticks.",
        "- MFE, MAE, duración y resultado son etiquetas posteriores; nunca entran como features.",
        "",
        "## Muestra",
        "",
        f"- Filas Liquidity Burst unidas: {len(dataset)}.",
        f"- Filas causales válidas: {int(causal.shape[0])}.",
        f"- Grupo A: {counts.get('A_WINNER', 0)}.",
        f"- Grupo B: {counts.get('B_LOSER_MFE_GT_30', 0)}.",
        f"- Grupo C: {counts.get('C_LOSER_MFE_3_TO_30', 0)}.",
        f"- Grupo D: {counts.get('D_BORN_BAD_MFE_LE_2', 0)}.",
        "- Split cronológico congelado: 60% discovery, 20% validation, 20% holdout.",
        f"- Años observados: {', '.join(str(int(year)) for year in years) if years else 'sin datos'}.",
        "- Esta corrida es confirmación multi-año; ningún resultado aislado autoriza filtros.",
    ])
    for label, title in (("A", "Grupo D vs Grupo A"), ("REST", "Grupo D vs todos los demás")):
        ranking = comparisons[label]["ranking"]
        lines.extend(["", f"## {title}", "", "| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |", "|---|---:|---:|---:|---:|---:|"])
        if ranking.empty:
            lines.append("| Muestra insuficiente | | | | | |")
        else:
            for _, row in ranking.head(12).iterrows():
                lines.append(
                    f"| {row['feature']} | {row.get('permutation_q_bh', np.nan):.4f} | "
                    f"{row.get('abs_cliffs_delta', np.nan):.3f} | {row.get('overlap_coefficient', np.nan):.3f} | "
                    f"{_report_flag(row.get('direction_stable_discovery_validation_holdout', 0))} | "
                    f"{_report_flag(row.get('robust_candidate', 0))} |"
                )
    lines.extend([
        "",
        "## Auditoría de Directional CLV",
        "",
        "- Fórmula: `side_sign * (2*entry-causal_high-causal_low)/(causal_high-causal_low)`.",
        "- El rango causal se construye exclusivamente con trades cuyo timestamp es <= señal; el OHLC de ATAS queda como auditoría y no entra al modelo.",
        f"- Filas CLV que reprodujeron fórmula, fuente y orden temporal: {clv_ok}/{clv_total}.",
        "- Las filas con rango causal insuficiente o cualquier discrepancia se excluyen, no se rellenan.",
        "",
        "| Variable | Pearson con CLV | Spearman con CLV | n |",
        "|---|---:|---:|---:|",
    ])
    if clv_correlations.empty:
        lines.append("| Sin muestra causal suficiente | | | 0 |")
    else:
        for _, row in clv_correlations.reindex(
            clv_correlations["spearman_with_causal_clv"].abs().sort_values(ascending=False).index
        ).head(10).iterrows():
            lines.append(
                f"| {row['feature']} | {row['pearson_with_causal_clv']:.3f} | "
                f"{row['spearman_with_causal_clv']:.3f} | {int(row['n'])} |"
            )

    pca_variance = independence.get("pca_variance", pd.DataFrame())
    clusters = independence.get("clusters", pd.DataFrame())
    correlations = independence.get("correlations", pd.DataFrame())
    redundant = int(correlations.get("redundant_ge_0_90", pd.Series(dtype=int)).sum()) if not correlations.empty else 0
    lines.extend([
        "",
        "## Independencia entre familias",
        "",
        f"- Features numéricas auditables: {clusters['feature'].nunique() if not clusters.empty else 0}.",
        f"- Clusters por |Spearman| >= 0.65: {clusters['correlation_cluster_abs_spearman_ge_0_65'].nunique() if not clusters.empty else 0}.",
        f"- Pares redundantes con correlación >= 0.90: {redundant}.",
        f"- Componentes PCA para explicar 80%: {int((pca_variance['cumulative_explained_variance'] < 0.80).sum() + 1) if not pca_variance.empty else 0}.",
        "- Correlación, clustering, PCA, VIF y mutual information se exportan completos; cuentan fenómenos, no thresholds de trading.",
        "",
        "## Estabilidad multi-año, Walk Forward y OOS",
        "",
        f"- Features que pasan el gate confirmatorio completo: {len(confirmed)}.",
        "- Gate: mismo signo en >=3 años, dirección estable en >=2 folds walk-forward, balanced accuracy mediana >0.50 y último año OOS >0.50.",
        "",
        "| Comparación | Feature | Años estables | Folds WF | BA WF mediana | BA último año OOS | Gate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    if temporal_summary.empty:
        lines.append("| Sin muestra suficiente | | | | | | 0 |")
    else:
        for _, row in temporal_summary.head(15).iterrows():
            lines.append(
                f"| {row['comparison']} | {row['feature']} | "
                f"{int(row['annual_direction_stable_min_3_years'])} | {int(row['valid_walk_forward_folds'])} | "
                f"{row['median_walk_forward_balanced_accuracy']:.3f} | "
                f"{row['latest_year_oos_balanced_accuracy']:.3f} | {int(row['passes_confirmation_gate'])} |"
            )

    response_status = response_audit.iloc[0].get("status", "NO_DATA") if not response_audit.empty else "NO_DATA"
    lines.extend([
        "",
        "## Respuesta posterior al burst",
        "",
        f"- Auditoría: {response_status}.",
        f"- Filas descriptivas por horizonte/familia/métrica: {len(response_statistics)}.",
        "- Estas métricas responden qué ocurrió 1s/3s/5s después del burst; están marcadas `POST_BURST_ONLY` y jamás se usan para decidir la entrada del mismo trade.",
        "- Sirven para generar hipótesis de dinámica de respuesta, no para presentar rendimiento preentrada.",
    ])
    lines.extend([
        "",
        "## Variables nuevas recomendadas para Build Alpha",
        "",
        "| Feature | Impacto | Implementación | Overfit | Estado | Mecanismo |",
        "|---|---|---|---|---|---|",
    ])
    for _, row in proposals.iterrows():
        lines.append(
            f"| {row['feature']} | {row['expected_impact']} | {row['implementation']} | "
            f"{row['overfit_risk']} | {row['recommendation']} | {row['market_mechanism']} |"
        )
    lines.extend([
        "",
        "## Orden mínimo de instrumentación siguiente",
        "",
        "1. ATR previo, overnight range y gap normalizado.",
        "2. Pendiente causal de VWAP y migración de POC/Value Area.",
        "3. Acceptance dwell ratio y número de retests de OR/VA/POC.",
        "4. Momentos matemáticos del perfil (skew, kurtosis y multimodalidad).",
        "5. Refill/book/icebergs sólo si Historia X10 entrega un stream reproducible; si no, se rechazan.",
        "",
        "## Salvaguardas",
        "",
        "- No se optimizaron parámetros, thresholds, TP, SL, trailing ni gestión.",
        "- No se creó ningún filtro de entrada.",
        "- No se usó información posterior a la entrada como predictor.",
        "- Las respuestas post-burst se analizaron sólo como outcomes descriptivos separados.",
        "- Ninguna ausencia de order book se rellenó o simuló.",
        "- Una feature sólo se considerará confirmada si conserva estabilidad anual, walk-forward y OOS; si falla, se rechaza.",
        "",
        f"Artefactos: `{output}`",
    ])
    return "\n".join(lines) + "\n"


def run_analysis(results_folder: Path, output_folder: Path | None = None) -> dict[str, object]:
    results_folder = Path(results_folder)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_folder is None:
        output_folder = Path(__file__).resolve().parent / "outputs" / f"born_bad_trade_research_{stamp}"
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    dataset, audit = base.build_dataset(results_folder)
    if dataset.empty:
        raise RuntimeError("No hay dataset causal Liquidity Burst suficiente.")
    replay_dates = pd.to_datetime(dataset.get("fecha"), errors="coerce")
    dataset = dataset.loc[replay_dates.le(OFFICIAL_CUTOFF_DATE)].copy()
    if dataset.empty:
        raise RuntimeError("No hay dataset causal anterior o igual al cutoff oficial.")
    dataset = _classify(_add_causal_features(dataset))

    original_names = list(base.FEATURE_NAMES)
    base.FEATURE_NAMES[:] = list(dict.fromkeys(original_names + DERIVED_FEATURES))
    try:
        comparisons = {
            "A": _run_comparison(dataset, "A"),
            "REST": _run_comparison(dataset, "REST"),
        }
    finally:
        base.FEATURE_NAMES[:] = original_names

    research_features = list(dict.fromkeys(original_names + DERIVED_FEATURES))
    clv_audit, clv_correlations = _clv_audit(dataset)
    independence = _independence_analysis(dataset, research_features)
    annual_stability, walk_forward, temporal_summary = _temporal_validation(
        dataset, research_features
    )
    response_rows, response_statistics, response_audit = _post_burst_response_analysis(
        results_folder, dataset
    )
    proposals = _feature_proposals()
    visuals = _plots(dataset, comparisons, output_folder / "visualizations")
    report = _report(
        dataset,
        comparisons,
        proposals,
        clv_audit,
        clv_correlations,
        independence,
        temporal_summary,
        response_audit,
        response_statistics,
        output_folder,
    )

    identity = [
        "fecha", "prediction_timestamp", "burst_event_timestamp", "burst_timestamp", "split", "born_bad_group", "born_bad_reason",
        "Result_Label", "realized_ticks_for_label", "MFE_ticks", "MAE_ticks",
        "Trade_Duration", "Entry_price", "ExecutionSide", "canonical_source_file",
        "causal_row_flag",
    ]
    feature_columns = [c for c in original_names + DERIVED_FEATURES if c in dataset]
    dataset[[c for c in identity + feature_columns if c in dataset]].to_csv(
        output_folder / "grouped_trades.csv", index=False
    )
    audit.to_csv(output_folder / "dataset_audit.csv", index=False)
    proposals.to_csv(output_folder / "new_feature_proposals.csv", index=False)
    clv_audit.to_csv(output_folder / "directional_clv_causality_audit.csv", index=False)
    clv_correlations.to_csv(output_folder / "directional_clv_correlations.csv", index=False)
    annual_stability.to_csv(output_folder / "annual_feature_stability.csv", index=False)
    walk_forward.to_csv(output_folder / "walk_forward_feature_validation.csv", index=False)
    temporal_summary.to_csv(output_folder / "temporal_confirmation_gate.csv", index=False)
    response_rows.to_csv(output_folder / "post_burst_response_rows.csv", index=False)
    response_statistics.to_csv(output_folder / "post_burst_response_statistics.csv", index=False)
    response_audit.to_csv(output_folder / "post_burst_response_audit.csv", index=False)
    for name, frame in independence.items():
        frame.to_csv(output_folder / f"feature_{name}.csv", index=False)
    for label, comparison in comparisons.items():
        suffix = "D_vs_A" if label == "A" else "D_vs_all_others"
        for name in ("statistics", "importance", "validation", "models", "ranking"):
            comparison[name].to_csv(output_folder / f"{name}_{suffix}.csv", index=False)
    (output_folder / "final_report.md").write_text(report, encoding="utf-8")

    context = Path(__file__).resolve().parent / "contexto_features_atas"
    context.mkdir(parents=True, exist_ok=True)
    context_report = context / f"INVESTIGACION_TRADES_NACEN_MAL_{stamp}.md"
    shutil.copy2(output_folder / "final_report.md", context_report)

    counts = dataset["born_bad_group"].value_counts().to_dict()
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "Historia X10 únicamente",
        "replay_x1": "DESHABILITADO",
        "official_cutoff_date": OFFICIAL_CUTOFF_DATE.date().isoformat(),
        "rows": len(dataset),
        "groups": counts,
        "output_folder": str(output_folder),
        "context_report": str(context_report),
        "trading_logic_changed": False,
        "filters_created": False,
        "post_burst_features_used_as_predictors": False,
        "temporal_confirmation_candidates": int(
            temporal_summary.get("passes_confirmation_gate", pd.Series(dtype=int)).sum()
        ),
        "holdout_opened_once": True,
    }
    (output_folder / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (results_folder / "latest_born_bad_trade_research.txt").write_text(str(output_folder), encoding="utf-8")
    return {"report": report, "manifest": manifest, "visuals": visuals, "output_folder": output_folder}


def send_to_telegram(results_folder: Path, analysis: dict[str, object]) -> bool:
    from telegram_run_summary_after_sync import send_photo, send_text

    completed_timer = "\nTimer etapa: 00:00 (completada)"
    ok = send_text(str(results_folder), TELEGRAM_TITLE + completed_timer)
    for index, chunk in enumerate(base._telegram_chunks(str(analysis["report"])), start=1):
        ok = send_text(str(results_folder), f"[{index}] {chunk}{completed_timer}") and ok
    for path in analysis["visuals"]:
        ok = send_photo(
            str(results_folder), str(path), TELEGRAM_TITLE + completed_timer
        ) and ok
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-folder", type=Path, required=True)
    parser.add_argument("--output-folder", type=Path, default=None)
    parser.add_argument("--telegram", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis = run_analysis(args.results_folder, args.output_folder)
    print(json.dumps(analysis["manifest"], indent=2, default=str))
    if args.telegram and not send_to_telegram(args.results_folder, analysis):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
