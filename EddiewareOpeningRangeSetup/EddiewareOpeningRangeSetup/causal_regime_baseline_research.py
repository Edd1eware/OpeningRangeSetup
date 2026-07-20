"""Discovery-only causal regime segmentation and baseline stability research.

The analysis is intentionally restricted to the frozen 2022-2024 discovery
manifest. Regime thresholds are learned inside each leave-one-year-out fold.
No 2025-2026 outcome is selected or emitted.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


RANDOM_SEED = 20260720
MODEL_PERMUTATIONS = 2000
REGIME_PERMUTATIONS = 5000
BOOTSTRAPS = 5000
FAMILY_A = "A_TRUE_ABSORPTION"
FAMILY_B = "B_CLEAN_BREAKOUT"

CORE_BASELINE_FEATURES = [
    "Profile_Local_Maxima_Count",
    "Previous_Delta_AtEntry",
    "Pre_Approach_Pause_Seconds",
    "Prior_Closed_ATR3_Ticks_AtEntry",
    "Prior_Closed_ATR5_Ticks_AtEntry",
    "Flow_3_5_DirectionalNetDelta",
    "Flow_3_5_GrossAggressive",
    "BuySellRatio",
    "Directional_VWAP_Distance_Ticks_AtEntry",
    "Signal_To_Entry_Latency_Milliseconds",
]

MBP_TAPE_FEATURES = [
    "burst_w1_add_to_aggressive",
    "burst_w1_refill_to_remove",
    "burst_w1_depth_balance",
    "burst_w1_recovery_from_min",
    "burst_w1_refill_latency_ms",
    "burst_w1_aggressive_volume",
    "reference_w3_add_to_aggressive",
    "reference_w3_refill_to_remove",
    "reference_w3_depth_balance",
    "reference_w3_recovery_from_min",
    "reference_w3_refill_latency_ms",
    "reference_w3_aggressive_volume",
]


@dataclass(frozen=True)
class RegimeSpec:
    name: str
    column: str
    low_label: str
    high_label: str
    absolute: bool = False


REGIMES = (
    RegimeSpec("ATR5", "Prior_Closed_ATR5_Ticks_AtEntry", "LOW", "HIGH"),
    RegimeSpec("OR_WIDTH", "OR_WidthTicks", "NARROW", "WIDE"),
    RegimeSpec("REALIZED_VOL_60S", "Realized_Volatility_60s_Ticks", "LOW", "HIGH"),
    RegimeSpec("PATH_EFFICIENCY", "PreBurst_Path_Efficiency_10s", "ROTATIONAL", "DIRECTIONAL"),
    RegimeSpec("FLOW_INTENSITY", "Flow_3_5_GrossAggressive", "LOW", "HIGH"),
    RegimeSpec("VWAP_DISTANCE_ABS", "Directional_VWAP_Distance_Ticks_AtEntry", "NEAR", "FAR", absolute=True),
    RegimeSpec("PROFILE_CONCENTRATION", "Profile_Concentration", "DISPERSED", "CONCENTRATED"),
)


def auc_or_nan(target: pd.Series, probability: pd.Series) -> float:
    return float(roc_auc_score(target, probability)) if target.nunique() == 2 else np.nan


def bh_adjust(values: pd.Series) -> pd.Series:
    valid = values.dropna().sort_values()
    result = pd.Series(np.nan, index=values.index, dtype=float)
    if valid.empty:
        return result
    raw = valid.to_numpy() * len(valid) / np.arange(1, len(valid) + 1)
    result.loc[valid.index] = np.minimum.accumulate(raw[::-1])[::-1].clip(max=1)
    return result


def make_model() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(
            C=0.2,
            class_weight="balanced",
            solver="liblinear",
            max_iter=3000,
            random_state=RANDOM_SEED,
        ),
    )


def usable_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    usable = []
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().sum() >= 3 and values.dropna().nunique() >= 2:
            usable.append(column)
    if not usable:
        raise ValueError("No usable predictors in temporal training fold")
    return usable


def load_discovery(project: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    manifest_path = project / "contexto_features_atas" / "DATABENTO_MBO_PILOTO_DISCOVERY_AB_20260720.csv"
    engineered_path = project / "outputs" / "absorption_breakout_research_20260720_085139" / "engineered_features.csv"
    mbp_path = project / "outputs" / "preentry_liquidity_features_20260720_preentry_r2" / "preentry_mbp_feature_ledger.csv"

    manifest = pd.read_csv(manifest_path)
    if len(manifest) != 70 or manifest["BurstId"].nunique() != 70:
        raise ValueError("Frozen discovery manifest must contain 70 unique events")
    if not manifest["split"].eq("discovery").all():
        raise ValueError("Non-discovery row found in frozen manifest")
    manifest["year"] = pd.to_datetime(manifest["fecha"], errors="raise").dt.year
    if not manifest["year"].between(2022, 2024).all():
        raise ValueError("Frozen discovery manifest contains a date outside 2022-2024")

    selected_ids = set(manifest["BurstId"])
    engineered_all = pd.read_csv(engineered_path)
    engineered = engineered_all.loc[engineered_all["BurstId"].isin(selected_ids)].copy()
    mbp_all = pd.read_csv(mbp_path)
    mbp = mbp_all.loc[mbp_all["BurstId"].isin(selected_ids)].copy()
    if len(engineered) != 70 or len(mbp) != 70:
        raise ValueError("Discovery selection did not join 70/70 source rows")

    manifest_columns = ["BurstId", "fecha", "split", "family_label_only"]
    frame = manifest[manifest_columns].merge(
        engineered.drop(columns=["fecha", "split", "family"], errors="ignore"),
        on="BurstId",
        how="left",
        validate="one_to_one",
    )
    mbp_columns = ["BurstId", "burst_side", *[name for name in MBP_TAPE_FEATURES if name in mbp.columns]]
    frame = frame.merge(mbp[mbp_columns], on="BurstId", how="left", validate="one_to_one")
    frame = frame.rename(columns={"family_label_only": "family"})
    frame["year"] = pd.to_datetime(frame["fecha"]).dt.year
    frame["target"] = frame["family"].eq(FAMILY_A).astype(int)
    if not frame["family"].isin([FAMILY_A, FAMILY_B]).all():
        raise ValueError("Discovery view contains a non-A/B family")
    if frame["BurstId"].duplicated().any():
        raise ValueError("Duplicate BurstId after discovery joins")

    required = set(CORE_BASELINE_FEATURES)
    required.update(spec.column for spec in REGIMES)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required discovery columns: {sorted(missing)}")
    audit = {
        "manifest_rows": len(manifest),
        "analysis_rows": len(frame),
        "analysis_year_min": int(frame["year"].min()),
        "analysis_year_max": int(frame["year"].max()),
        "rows_2025_2026_selected": int(frame["year"].ge(2025).sum()),
        "families": frame["family"].value_counts().sort_index().to_dict(),
        "years": frame["year"].value_counts().sort_index().to_dict(),
        "directions": frame["burst_side"].value_counts().sort_index().to_dict(),
        "source_2025_2026_labels_used": False,
    }
    return frame.sort_values(["fecha", "BurstId"]).reset_index(drop=True), audit


def regime_values(frame: pd.DataFrame, spec: RegimeSpec) -> pd.Series:
    values = pd.to_numeric(frame[spec.column], errors="coerce")
    return values.abs() if spec.absolute else values


def assign_regimes_from_training(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[dict[str, pd.Series], list[dict[str, object]]]:
    assignments = {}
    thresholds = []
    for spec in REGIMES:
        threshold = float(regime_values(train, spec).median())
        test_values = regime_values(test, spec)
        assignments[spec.name] = pd.Series(
            np.where(test_values.le(threshold), spec.low_label, spec.high_label),
            index=test.index,
        )
        thresholds.append({
            "test_year": int(test["year"].iloc[0]),
            "regime_axis": spec.name,
            "source_feature": spec.column,
            "absolute_transform": spec.absolute,
            "training_threshold": threshold,
            "training_years": ",".join(str(value) for value in sorted(train["year"].unique())),
        })
    return assignments, thresholds


def loyo_predictions(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    target: pd.Series | None = None,
    collect_details: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    y = frame["target"] if target is None else pd.Series(target.to_numpy(), index=frame.index)
    prediction_rows = []
    threshold_rows = []
    coefficient_rows = []
    for year in sorted(frame["year"].unique()):
        train_mask = frame["year"].ne(year)
        test_mask = frame["year"].eq(year)
        train = frame.loc[train_mask]
        test = frame.loc[test_mask]
        selected = usable_columns(train, columns)
        model = make_model()
        model.fit(train[selected], y.loc[train_mask])
        probabilities = model.predict_proba(test[selected])[:, 1]
        assignments, thresholds = assign_regimes_from_training(train, test)
        if collect_details:
            threshold_rows.extend(thresholds)
            coefficients = model.named_steps["logisticregression"].coef_[0]
            coefficient_rows.extend(
                {"test_year": int(year), "feature": feature, "coefficient": float(coefficient)}
                for feature, coefficient in zip(selected, coefficients, strict=True)
            )
        for position, (index, probability) in enumerate(zip(test.index, probabilities, strict=True)):
            row = {
                "row_index": int(index),
                "BurstId": frame.loc[index, "BurstId"],
                "fecha": frame.loc[index, "fecha"],
                "year": int(year),
                "burst_side": frame.loc[index, "burst_side"],
                "family": frame.loc[index, "family"],
                "target": int(y.loc[index]),
                "probability": float(probability),
                "feature_count": len(selected),
            }
            for spec in REGIMES:
                row[f"regime_{spec.name}"] = assignments[spec.name].iloc[position]
            prediction_rows.append(row)
    return pd.DataFrame(prediction_rows).sort_values("row_index"), pd.DataFrame(threshold_rows), pd.DataFrame(coefficient_rows)


def performance_rows(predictions: pd.DataFrame, feature_set: str) -> list[dict[str, object]]:
    rows = [{
        "feature_set": feature_set,
        "subgroup": "ALL",
        "n": len(predictions),
        "n_A": int(predictions["target"].sum()),
        "n_B": int((1 - predictions["target"]).sum()),
        "roc_auc": auc_or_nan(predictions["target"], predictions["probability"]),
    }]
    for year, group in predictions.groupby("year"):
        rows.append({
            "feature_set": feature_set,
            "subgroup": f"YEAR_{year}",
            "n": len(group),
            "n_A": int(group["target"].sum()),
            "n_B": int((1 - group["target"]).sum()),
            "roc_auc": auc_or_nan(group["target"], group["probability"]),
        })
    for side, group in predictions.groupby("burst_side"):
        rows.append({
            "feature_set": feature_set,
            "subgroup": f"SIDE_{side}",
            "n": len(group),
            "n_A": int(group["target"].sum()),
            "n_B": int((1 - group["target"]).sum()),
            "roc_auc": auc_or_nan(group["target"], group["probability"]),
        })
    return rows


def evaluate_models(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, list[str]]]:
    sets = {
        "CORE_BASELINE": [name for name in CORE_BASELINE_FEATURES if name in frame.columns],
        "EXISTING_CAUSAL": [name for name in CORE_BASELINE_FEATURES + MBP_TAPE_FEATURES if name in frame.columns],
    }
    predictions = []
    metrics = []
    primary_thresholds = pd.DataFrame()
    primary_coefficients = pd.DataFrame()
    for name, columns in sets.items():
        pred, thresholds, coefficients = loyo_predictions(
            frame,
            columns,
            collect_details=name == "EXISTING_CAUSAL",
        )
        pred["feature_set"] = name
        predictions.append(pred)
        metrics.extend(performance_rows(pred, name))
        if name == "EXISTING_CAUSAL":
            primary_thresholds = thresholds
            primary_coefficients = coefficients
    return pd.DataFrame(metrics), pd.concat(predictions, ignore_index=True), primary_thresholds, primary_coefficients, sets


def coefficient_stability(coefficients: pd.DataFrame) -> pd.DataFrame:
    pivot = coefficients.pivot(index="feature", columns="test_year", values="coefficient")
    for year in (2022, 2023, 2024):
        if year not in pivot:
            pivot[year] = np.nan
    pivot = pivot[[2022, 2023, 2024]].rename(columns=lambda year: f"coef_fold_{year}")
    result = pivot.reset_index()
    coef_columns = [f"coef_fold_{year}" for year in (2022, 2023, 2024)]
    result["median_abs_coefficient"] = result[coef_columns].abs().median(axis=1)
    signs = np.sign(result[coef_columns])
    result["same_sign_all_folds"] = (
        signs.notna().all(axis=1)
        & signs.ne(0).all(axis=1)
        & signs.nunique(axis=1).eq(1)
    ).astype(int)
    return result.sort_values(["same_sign_all_folds", "median_abs_coefficient"], ascending=[False, False]).reset_index(drop=True)


def model_permutation_tests(
    frame: pd.DataFrame,
    sets: dict[str, list[str]],
    metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    observed = metrics.loc[metrics["subgroup"].eq("ALL")].set_index("feature_set")["roc_auc"]
    observed_delta = float(observed["EXISTING_CAUSAL"] - observed["CORE_BASELINE"])
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for iteration in range(MODEL_PERMUTATIONS):
        permuted = frame["target"].copy()
        for _, indexes in frame.groupby("year").groups.items():
            permuted.loc[indexes] = rng.permutation(permuted.loc[indexes].to_numpy())
        aucs = {}
        for name, columns in sets.items():
            pred, _, _ = loyo_predictions(frame, columns, target=permuted)
            aucs[name] = auc_or_nan(pred["target"], pred["probability"])
        rows.append({
            "iteration": iteration,
            "auc_CORE_BASELINE": aucs["CORE_BASELINE"],
            "auc_EXISTING_CAUSAL": aucs["EXISTING_CAUSAL"],
            "delta_EXISTING_minus_CORE": aucs["EXISTING_CAUSAL"] - aucs["CORE_BASELINE"],
        })
    distribution = pd.DataFrame(rows)
    summary = pd.DataFrame([
        {
            "test": "CORE_BASELINE_AUC",
            "observed": float(observed["CORE_BASELINE"]),
            "p_permutation": float((1 + distribution["auc_CORE_BASELINE"].ge(observed["CORE_BASELINE"]).sum()) / (MODEL_PERMUTATIONS + 1)),
        },
        {
            "test": "EXISTING_CAUSAL_AUC",
            "observed": float(observed["EXISTING_CAUSAL"]),
            "p_permutation": float((1 + distribution["auc_EXISTING_CAUSAL"].ge(observed["EXISTING_CAUSAL"]).sum()) / (MODEL_PERMUTATIONS + 1)),
        },
        {
            "test": "DELTA_EXISTING_MINUS_CORE",
            "observed": observed_delta,
            "p_permutation": float((1 + distribution["delta_EXISTING_minus_CORE"].ge(observed_delta).sum()) / (MODEL_PERMUTATIONS + 1)),
        },
    ])
    return summary, distribution


def stratified_bootstrap_auc(predictions: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    rng = np.random.default_rng(RANDOM_SEED + 1)
    groups = list(predictions.groupby(["year", "target"]).groups.values())
    values = []
    for iteration in range(BOOTSTRAPS):
        indexes = np.concatenate([rng.choice(np.asarray(group), size=len(group), replace=True) for group in groups])
        sample = predictions.loc[indexes]
        values.append({"iteration": iteration, "roc_auc": auc_or_nan(sample["target"], sample["probability"])})
    distribution = pd.DataFrame(values)
    summary = {
        "bootstrap_iterations": BOOTSTRAPS,
        "auc_median": float(distribution["roc_auc"].median()),
        "auc_ci_lower_95": float(distribution["roc_auc"].quantile(0.025)),
        "auc_ci_upper_95": float(distribution["roc_auc"].quantile(0.975)),
    }
    return distribution, summary


def regime_performance(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for spec in REGIMES:
        column = f"regime_{spec.name}"
        for segment, group in predictions.groupby(column):
            complement = predictions.loc[predictions[column].ne(segment)]
            year_aucs = {}
            eligible_year_aucs = []
            for year, year_group in group.groupby("year"):
                eligible = year_group["target"].sum() >= 2 and (1 - year_group["target"]).sum() >= 2
                value = auc_or_nan(year_group["target"], year_group["probability"]) if eligible else np.nan
                year_aucs[f"auc_year_{year}"] = value
                year_aucs[f"eligible_year_{year}"] = int(eligible)
                if eligible:
                    eligible_year_aucs.append(value)
            side_aucs = {}
            side_eligible = []
            for side in ("BUY", "SELL"):
                side_group = group.loc[group["burst_side"].eq(side)]
                eligible = side_group["target"].sum() >= 2 and (1 - side_group["target"]).sum() >= 2
                value = auc_or_nan(side_group["target"], side_group["probability"]) if eligible else np.nan
                side_aucs[f"auc_side_{side}"] = value
                side_aucs[f"eligible_side_{side}"] = int(eligible)
                side_eligible.append(eligible)
            rows.append({
                "regime_axis": spec.name,
                "segment": segment,
                "n": len(group),
                "coverage_pct": 100 * len(group) / len(predictions),
                "n_A": int(group["target"].sum()),
                "n_B": int((1 - group["target"]).sum()),
                "roc_auc": auc_or_nan(group["target"], group["probability"]),
                "complement_auc": auc_or_nan(complement["target"], complement["probability"]),
                "auc_improvement_vs_complement": auc_or_nan(group["target"], group["probability"]) - auc_or_nan(complement["target"], complement["probability"]),
                "eligible_year_count": len(eligible_year_aucs),
                "years_auc_at_least_0_60": sum(value >= 0.60 for value in eligible_year_aucs),
                "minimum_eligible_year_auc": min(eligible_year_aucs) if eligible_year_aucs else np.nan,
                "both_sides_eligible": int(all(side_eligible)),
                **year_aucs,
                **side_aucs,
            })
    result = pd.DataFrame(rows)

    rng = np.random.default_rng(RANDOM_SEED + 2)
    permuted_targets = []
    for _ in range(REGIME_PERMUTATIONS):
        target = predictions["target"].copy()
        for _, indexes in predictions.groupby("year").groups.items():
            target.loc[indexes] = rng.permutation(target.loc[indexes].to_numpy())
        permuted_targets.append(target.to_numpy())
    permuted_matrix = np.asarray(permuted_targets)

    p_values = []
    for row in result.itertuples(index=False):
        mask = predictions[f"regime_{row.regime_axis}"].eq(row.segment).to_numpy()
        probability = predictions.loc[mask, "probability"].reset_index(drop=True)
        observed = float(row.roc_auc)
        exceed = 0
        valid = 0
        for permuted in permuted_matrix[:, mask]:
            target = pd.Series(permuted)
            if target.nunique() != 2:
                continue
            valid += 1
            exceed += auc_or_nan(target, probability) >= observed
        p_values.append((1 + exceed) / (1 + valid) if valid else np.nan)
    result["p_permutation_oof_fixed"] = p_values
    result["q_bh"] = bh_adjust(result["p_permutation_oof_fixed"])
    result["candidate_regime"] = (
        result["coverage_pct"].ge(35)
        & result["n_A"].ge(8)
        & result["n_B"].ge(8)
        & result["roc_auc"].ge(0.70)
        & result["auc_improvement_vs_complement"].ge(0.10)
        & result["q_bh"].le(0.10)
        & result["eligible_year_count"].ge(2)
        & result["years_auc_at_least_0_60"].ge(2)
        & result["minimum_eligible_year_auc"].ge(0.45)
        & result["both_sides_eligible"].eq(1)
        & result["auc_side_BUY"].ge(0.55)
        & result["auc_side_SELL"].ge(0.55)
    ).astype(int)
    return result.sort_values(["candidate_regime", "roc_auc"], ascending=[False, False]).reset_index(drop=True)


def global_stability_gate(metrics: pd.DataFrame, permutations: pd.DataFrame, bootstrap: dict[str, float]) -> tuple[pd.DataFrame, bool]:
    table = metrics.loc[metrics["feature_set"].eq("EXISTING_CAUSAL")].set_index("subgroup")["roc_auc"]
    p_value = float(permutations.loc[permutations["test"].eq("EXISTING_CAUSAL_AUC"), "p_permutation"].iloc[0])
    checks = [
        ("OVERALL_AUC_AT_LEAST_0_65", float(table["ALL"]), 0.65, table["ALL"] >= 0.65),
        ("PERMUTATION_P_AT_MOST_0_05", p_value, 0.05, p_value <= 0.05),
        ("YEAR_2022_AUC_AT_LEAST_0_55", float(table["YEAR_2022"]), 0.55, table["YEAR_2022"] >= 0.55),
        ("YEAR_2023_AUC_AT_LEAST_0_55", float(table["YEAR_2023"]), 0.55, table["YEAR_2023"] >= 0.55),
        ("YEAR_2024_AUC_AT_LEAST_0_55", float(table["YEAR_2024"]), 0.55, table["YEAR_2024"] >= 0.55),
        ("BUY_AUC_AT_LEAST_0_55", float(table["SIDE_BUY"]), 0.55, table["SIDE_BUY"] >= 0.55),
        ("SELL_AUC_AT_LEAST_0_55", float(table["SIDE_SELL"]), 0.55, table["SIDE_SELL"] >= 0.55),
        ("BOOTSTRAP_CI_LOWER_AT_LEAST_0_50", bootstrap["auc_ci_lower_95"], 0.50, bootstrap["auc_ci_lower_95"] >= 0.50),
    ]
    frame = pd.DataFrame(checks, columns=["criterion", "observed", "threshold", "passed"])
    return frame, bool(frame["passed"].all())


def create_plots(
    output: Path,
    metrics: pd.DataFrame,
    regimes: pd.DataFrame,
    coefficients: pd.DataFrame,
    bootstrap_distribution: pd.DataFrame,
) -> list[str]:
    folder = output / "visualizations"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []

    pivot = metrics.pivot(index="subgroup", columns="feature_set", values="roc_auc")
    order = ["ALL", "YEAR_2022", "YEAR_2023", "YEAR_2024", "SIDE_BUY", "SIDE_SELL"]
    ax = pivot.loc[order].plot(kind="bar", figsize=(11, 6), ylim=(0, 1), color=["#636363", "#2c7fb8"])
    ax.axhline(0.5, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("ROC AUC LOYO")
    ax.set_title("Estabilidad temporal del baseline causal — discovery 2022–2024")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    path = folder / "baseline_loyo_stability.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(str(path))

    plt.figure(figsize=(10, 7))
    colors = np.where(regimes["candidate_regime"].eq(1), "#31a354", "#756bb1")
    plt.scatter(regimes["coverage_pct"], regimes["roc_auc"], s=70, c=colors, alpha=0.85)
    for row in regimes.itertuples(index=False):
        plt.annotate(f"{row.regime_axis}:{row.segment}", (row.coverage_pct, row.roc_auc), fontsize=7, xytext=(3, 3), textcoords="offset points")
    plt.axhline(0.70, color="black", linestyle="--", linewidth=1)
    plt.axvline(35, color="black", linestyle=":", linewidth=1)
    plt.xlabel("Cobertura de operaciones (%)")
    plt.ylabel("AUC OOF dentro del segmento")
    plt.title("Regímenes causales: fuerza vs cobertura")
    plt.tight_layout()
    path = folder / "regime_auc_vs_coverage.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(str(path))

    top = coefficients.sort_values("median_abs_coefficient", ascending=False).head(15).set_index("feature")
    matrix = top[[f"coef_fold_{year}" for year in (2022, 2023, 2024)]].to_numpy()
    limit = np.nanmax(np.abs(matrix)) or 1.0
    plt.figure(figsize=(8, 8))
    image = plt.imshow(matrix, aspect="auto", cmap="coolwarm", vmin=-limit, vmax=limit)
    plt.yticks(range(len(top)), top.index, fontsize=8)
    plt.xticks(range(3), ["test 2022", "test 2023", "test 2024"])
    plt.colorbar(image, label="Coeficiente estandarizado")
    plt.title("Estabilidad de coeficientes entre folds")
    plt.tight_layout()
    path = folder / "baseline_coefficient_stability.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(str(path))

    plt.figure(figsize=(9, 5))
    plt.hist(bootstrap_distribution["roc_auc"], bins=35, color="#2c7fb8", alpha=0.85)
    plt.axvline(0.5, color="black", linestyle="--")
    plt.xlabel("AUC bootstrap")
    plt.ylabel("Frecuencia")
    plt.title("Incertidumbre del AUC OOF — baseline causal")
    plt.tight_layout()
    path = folder / "baseline_auc_bootstrap.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(str(path))
    return paths


def write_report(
    output: Path,
    audit: dict[str, object],
    metrics: pd.DataFrame,
    permutations: pd.DataFrame,
    bootstrap: dict[str, float],
    global_gate: pd.DataFrame,
    global_stable: bool,
    regimes: pd.DataFrame,
    coefficients: pd.DataFrame,
) -> None:
    table = metrics.pivot(index="subgroup", columns="feature_set", values="roc_auc")
    candidates = regimes.loc[regimes["candidate_regime"].eq(1)]
    p_existing = permutations.loc[permutations["test"].eq("EXISTING_CAUSAL_AUC"), "p_permutation"].iloc[0]
    lines = [
        "# Segmentación causal de régimen y estabilidad del baseline",
        "",
        "## Aislamiento",
        "",
        f"- Eventos discovery: {audit['analysis_rows']}.",
        f"- Años utilizados: {audit['analysis_year_min']}–{audit['analysis_year_max']}.",
        "- Filas 2025–2026 utilizadas: **0**.",
        "- Validation/holdout abiertos por esta investigación: **0**.",
        "",
        "## Resultado global",
        "",
        f"Estabilidad global del baseline causal: **{'PASÓ' if global_stable else 'NO PASÓ'}**.",
        f"Regímenes candidatos que pasan todos los criterios: **{len(candidates)}**.",
        "",
        f"- AUC OOF CORE_BASELINE: {table.loc['ALL', 'CORE_BASELINE']:.3f}.",
        f"- AUC OOF EXISTING_CAUSAL: {table.loc['ALL', 'EXISTING_CAUSAL']:.3f}.",
        f"- p de permutación EXISTING_CAUSAL: {p_existing:.4f}.",
        f"- Bootstrap 95%: [{bootstrap['auc_ci_lower_95']:.3f}, {bootstrap['auc_ci_upper_95']:.3f}].",
        "",
        "## Estabilidad por año y lado",
        "",
        "| Subgrupo | Core | Existing causal |",
        "| --- | ---: | ---: |",
    ]
    for subgroup in ["YEAR_2022", "YEAR_2023", "YEAR_2024", "SIDE_BUY", "SIDE_SELL"]:
        lines.append(f"| {subgroup} | {table.loc[subgroup, 'CORE_BASELINE']:.3f} | {table.loc[subgroup, 'EXISTING_CAUSAL']:.3f} |")
    lines.extend([
        "",
        "## Puerta global congelada",
        "",
        "| Criterio | Observado | Umbral | Pasó |",
        "| --- | ---: | ---: | ---: |",
    ])
    for row in global_gate.itertuples(index=False):
        lines.append(f"| {row.criterion} | {row.observed:.4f} | {row.threshold:.4f} | {int(row.passed)} |")
    lines.extend([
        "",
        "## Regímenes con mayor AUC",
        "",
        "| Eje | Segmento | Cobertura | A/B | AUC | Complemento | q BH | Candidato |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in regimes.head(10).itertuples(index=False):
        lines.append(f"| {row.regime_axis} | {row.segment} | {row.coverage_pct:.1f}% | {row.n_A}/{row.n_B} | {row.roc_auc:.3f} | {row.complement_auc:.3f} | {row.q_bh:.3f} | {row.candidate_regime} |")
    stable_coefficients = coefficients.loc[coefficients["same_sign_all_folds"].eq(1)]
    lines.extend([
        "",
        "## Coeficientes",
        "",
        f"Features con signo idéntico en los tres folds: {len(stable_coefficients)}/{len(coefficients)}.",
        "",
        "## Interpretación",
        "",
        "- Los segmentos se evaluaron con predicciones fuera de año y umbrales de régimen aprendidos sin el año de prueba.",
        "- Un AUC alto aislado no basta: debe conservar cobertura, significancia, estabilidad anual y ambos lados.",
        "- Este análisis no modifica entradas, no estima WR/PF y no autoriza abrir 2025–2026.",
        "",
        f"Artefactos: `{output}`",
    ])
    (output / "final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(project: Path, output: Path) -> dict[str, object]:
    frame, audit = load_discovery(project)
    output.mkdir(parents=True, exist_ok=False)
    metrics, predictions, thresholds, raw_coefficients, sets = evaluate_models(frame)
    coefficients = coefficient_stability(raw_coefficients)
    permutation_summary, permutation_distribution = model_permutation_tests(frame, sets, metrics)
    primary_predictions = predictions.loc[predictions["feature_set"].eq("EXISTING_CAUSAL")].copy().reset_index(drop=True)
    bootstrap_distribution, bootstrap_summary = stratified_bootstrap_auc(primary_predictions)
    regimes = regime_performance(primary_predictions)
    gate, global_stable = global_stability_gate(metrics, permutation_summary, bootstrap_summary)
    plots = create_plots(output, metrics, regimes, coefficients, bootstrap_distribution)

    frame.to_csv(output / "discovery_only_2022_2024.csv", index=False)
    predictions.to_csv(output / "baseline_loyo_predictions.csv", index=False)
    metrics.to_csv(output / "baseline_loyo_metrics.csv", index=False)
    thresholds.to_csv(output / "regime_training_thresholds.csv", index=False)
    coefficients.to_csv(output / "baseline_coefficient_stability.csv", index=False)
    permutation_summary.to_csv(output / "model_permutation_tests.csv", index=False)
    permutation_distribution.to_csv(output / "model_permutation_distribution.csv", index=False)
    bootstrap_distribution.to_csv(output / "baseline_bootstrap_distribution.csv", index=False)
    regimes.to_csv(output / "regime_performance.csv", index=False)
    gate.to_csv(output / "global_stability_gate.csv", index=False)
    write_report(output, audit, metrics, permutation_summary, bootstrap_summary, gate, global_stable, regimes, coefficients)

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        **audit,
        "model_permutations": MODEL_PERMUTATIONS,
        "regime_permutations": REGIME_PERMUTATIONS,
        "bootstraps": BOOTSTRAPS,
        "bootstrap_summary": bootstrap_summary,
        "global_baseline_stable": global_stable,
        "candidate_regimes": regimes.loc[regimes["candidate_regime"].eq(1), ["regime_axis", "segment"]].to_dict("records"),
        "validation_dates_opened": 0,
        "atas_replay_launched": False,
        "new_data_purchased": False,
        "plots": plots,
        "output": str(output),
    }
    (output / "run_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.project, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
