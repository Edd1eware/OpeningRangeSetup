"""Nonlinear Liquidity Burst diagnostics with temporal CatBoost validation.

This is a post-holdout research tool.  It may generate hypotheses, but it does
not turn the already-opened 2025-2026 sample into a new holdout and never writes
anything consumed by the trading strategy.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from scipy.stats import rankdata
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score

import absorption_breakout_research as ab_research
import causal_regime_baseline_research as regime_research


RANDOM_SEED = 20260720
FAMILY_A = ab_research.FAMILY_ABSORPTION
FAMILY_B = ab_research.FAMILY_CONTINUATION
CORE = list(regime_research.CORE_BASELINE_FEATURES)
FORBIDDEN = ("mfe", "mae", "result", "exit", "outcome", "future", "response")
SYSTEM_ARTIFACT_FEATURES = {
    "Detector_Publish_Delay_Milliseconds",
    "Signal_To_Entry_Latency_Milliseconds",
    "Detector_Publish_To_Entry_Latency_Milliseconds",
}


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


def load_data(project: Path, results: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    old = pd.read_csv(
        project / "outputs" / "causal_regime_baseline_20260720_r1" / "discovery_only_2022_2024.csv",
        low_memory=False,
    )
    new, new_audit = ab_research.build_dataset(results)
    old = old.loc[old["family"].isin([FAMILY_A, FAMILY_B])].copy()
    new = new.loc[new["family"].isin([FAMILY_A, FAMILY_B])].copy()
    old["year"] = pd.to_datetime(old["fecha"], errors="raise").dt.year
    new["year"] = pd.to_datetime(new["fecha"], errors="raise").dt.year
    old["era"] = "DISCOVERY_2022_2024"
    new["era"] = "OPENED_2025_2026"
    old["target"] = old["family"].eq(FAMILY_A).astype(int)
    new["target"] = new["family"].eq(FAMILY_A).astype(int)
    if len(old) != 70 or old["BurstId"].nunique() != 70:
        raise ValueError("Expected 70 unique frozen discovery A/B events")
    if not old["year"].between(2022, 2024).all():
        raise ValueError("Old discovery contains a year outside 2022-2024")
    if not new["year"].isin([2025, 2026]).all():
        raise ValueError("Latest capture contains a year outside 2025-2026")
    if not new["causal_row_flag"].all():
        raise ValueError("Latest capture contains a non-causal row")
    if set(old["BurstId"]).intersection(new["BurstId"]):
        raise ValueError("Old discovery and latest capture overlap by BurstId")
    audit = {
        "old_rows": len(old),
        "new_rows": len(new),
        "combined_rows": len(old) + len(new),
        "old_families": old["family"].value_counts().to_dict(),
        "new_families": new["family"].value_counts().to_dict(),
        "old_years": old["year"].value_counts().sort_index().to_dict(),
        "new_years": new["year"].value_counts().sort_index().to_dict(),
        "new_source_audit": new_audit.to_dict("records"),
        "new_holdout_reused_as_holdout": False,
        "purpose": "post-holdout hypothesis generation only",
    }
    return old.reset_index(drop=True), new.reset_index(drop=True), audit


def feature_universe(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    specs = {spec.name: spec for spec in ab_research.ALL_SPECS}
    rows = []
    for feature in ab_research.FEATURE_NAMES:
        if feature not in old or feature not in new:
            continue
        old_values = pd.to_numeric(old[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        new_values = pd.to_numeric(new[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        spec = specs[feature]
        forbidden = any(token in feature.lower() for token in FORBIDDEN)
        rows.append({
            "feature": feature,
            "source": spec.source,
            "formula": spec.formula,
            "units": spec.units,
            "interpretation": spec.interpretation,
            "window_start_seconds": spec.window_start_seconds,
            "window_end_seconds": spec.window_end_seconds,
            "mechanism_family": ab_research._mechanism_family(feature),
            "coverage_old_pct": 100 * old_values.notna().mean(),
            "coverage_new_pct": 100 * new_values.notna().mean(),
            "unique_old": old_values.nunique(dropna=True),
            "unique_new": new_values.nunique(dropna=True),
            "forbidden_name": forbidden,
            "system_artifact": feature in SYSTEM_ARTIFACT_FEATURES,
            "eligible": (
                not forbidden
                and feature not in SYSTEM_ARTIFACT_FEATURES
                and spec.window_end_seconds <= 0
                and old_values.notna().mean() >= 0.80
                and new_values.notna().mean() >= 0.80
                and old_values.nunique(dropna=True) >= 3
                and new_values.nunique(dropna=True) >= 3
            ),
        })
    result = pd.DataFrame(rows)
    if result["forbidden_name"].any():
        raise ValueError("A forbidden outcome-like feature exists in FEATURE_NAMES")
    return result.sort_values(["eligible", "mechanism_family", "feature"], ascending=[False, True, True]).reset_index(drop=True)


def clean_matrix(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    return frame[features].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def make_catboost(seed: int = RANDOM_SEED) -> CatBoostClassifier:
    return CatBoostClassifier(
        iterations=350,
        depth=2,
        learning_rate=0.025,
        l2_leaf_reg=25.0,
        random_strength=1.0,
        loss_function="Logloss",
        auto_class_weights="Balanced",
        random_seed=seed,
        verbose=False,
        allow_writing_files=False,
        thread_count=-1,
    )


def usable_in_training(train: pd.DataFrame, features: list[str]) -> list[str]:
    result = []
    for feature in features:
        values = pd.to_numeric(train[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if values.notna().sum() >= 8 and values.nunique(dropna=True) >= 2:
            result.append(feature)
    if not result:
        raise ValueError("No usable CatBoost features in temporal training split")
    return result


def subgroup_metrics(frame: pd.DataFrame, experiment: str, feature_set: str) -> list[dict[str, object]]:
    rows = []
    groups: list[tuple[str, pd.DataFrame]] = [("ALL", frame)]
    groups.extend((f"YEAR_{year}", group) for year, group in frame.groupby("year"))
    groups.extend((f"BURST_SIDE_{side}", group) for side, group in frame.groupby("BurstSide"))
    for subgroup, group in groups:
        prediction = group["probability_A"].ge(0.5).astype(int)
        if group["target"].nunique() == 2:
            tn, fp, fn, tp = confusion_matrix(group["target"], prediction, labels=[0, 1]).ravel()
            balanced = balanced_accuracy_score(group["target"], prediction)
            sensitivity = tp / (tp + fn) if tp + fn else np.nan
            specificity = tn / (tn + fp) if tn + fp else np.nan
        else:
            balanced = sensitivity = specificity = np.nan
        rows.append({
            "experiment": experiment,
            "feature_set": feature_set,
            "subgroup": subgroup,
            "n": len(group),
            "n_A": int(group["target"].sum()),
            "n_B": int((1 - group["target"]).sum()),
            "roc_auc": auc_or_nan(group["target"], group["probability_A"]),
            "balanced_accuracy": balanced,
            "sensitivity_A": sensitivity,
            "specificity_B": specificity,
        })
    return rows


def stratified_permutation_auc_p(
    target: pd.Series,
    score: pd.Series,
    strata: pd.Series,
    observed: float,
    iterations: int,
    seed: int,
) -> float:
    """One-sided AUC permutation p-value, vectorized within temporal strata."""
    if iterations <= 0 or not np.isfinite(observed):
        return np.nan
    valid = target.notna() & score.notna() & strata.notna()
    y = target.loc[valid].astype(int).to_numpy()
    ranks = rankdata(score.loc[valid].to_numpy(dtype=float))
    groups = strata.loc[valid].reset_index(drop=True)
    n_positive = int(y.sum())
    n_negative = int(len(y) - n_positive)
    if not n_positive or not n_negative:
        return np.nan
    rng = np.random.default_rng(seed)
    permuted = np.empty((iterations, len(y)), dtype=np.int8)
    for _, indexes in groups.groupby(groups).groups.items():
        positions = np.asarray(list(indexes), dtype=int)
        values = y[positions]
        random_keys = rng.random((iterations, len(positions)))
        orders = np.argsort(random_keys, axis=1)
        permuted[:, positions] = values[orders]
    aucs = (
        permuted @ ranks - n_positive * (n_positive + 1) / 2.0
    ) / (n_positive * n_negative)
    return float((1 + np.count_nonzero(aucs >= observed)) / (1 + iterations))


def fixed_prediction_permutation_p(frame: pd.DataFrame, iterations: int = 5000) -> float:
    observed = auc_or_nan(frame["target"], frame["probability_A"])
    return stratified_permutation_auc_p(
        frame["target"],
        frame["probability_A"],
        frame["year"],
        observed,
        iterations,
        RANDOM_SEED + 31,
    )


def fit_experiment(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    experiment: str,
    feature_set: str,
    permutation_iterations: int = 5000,
) -> tuple[pd.DataFrame, pd.DataFrame, CatBoostClassifier, list[str]]:
    selected = usable_in_training(train, features)
    model = make_catboost()
    model.fit(clean_matrix(train, selected), train["target"])
    result = test[["BurstId", "fecha", "year", "BurstSide", "ExecutionSide", "family", "target", "era"]].copy()
    result["probability_A"] = model.predict_proba(clean_matrix(test, selected))[:, 1]
    result["experiment"] = experiment
    result["feature_set"] = feature_set
    result["feature_count"] = len(selected)
    metrics = pd.DataFrame(subgroup_metrics(result, experiment, feature_set))
    overall_p = fixed_prediction_permutation_p(result, iterations=permutation_iterations)
    metrics.loc[metrics["subgroup"].eq("ALL"), "p_permutation_fixed_oos"] = overall_p
    return result, metrics, model, selected


def shap_rows(
    model: CatBoostClassifier,
    selected: list[str],
    test: pd.DataFrame,
    experiment: str,
    feature_set: str,
) -> pd.DataFrame:
    matrix = clean_matrix(test, selected)
    values = model.get_feature_importance(Pool(matrix, feature_names=selected), type="ShapValues")[:, :-1]
    rows = []
    for index, feature in enumerate(selected):
        raw = matrix[feature]
        shap = pd.Series(values[:, index], index=test.index)
        valid = raw.notna() & shap.notna()
        corr = raw.loc[valid].corr(shap.loc[valid], method="spearman") if valid.sum() >= 5 else np.nan
        a = shap.loc[test["target"].eq(1)].median()
        b = shap.loc[test["target"].eq(0)].median()
        rows.append({
            "experiment": experiment,
            "feature_set": feature_set,
            "feature": feature,
            "mechanism_family": ab_research._mechanism_family(feature),
            "mean_abs_shap_oos": float(np.mean(np.abs(values[:, index]))),
            "spearman_value_vs_shap_oos": corr,
            "median_shap_A_minus_B_oos": float(a - b),
            "coverage_oos_pct": 100 * raw.notna().mean(),
        })
    result = pd.DataFrame(rows)
    result["importance_rank"] = result["mean_abs_shap_oos"].rank(method="min", ascending=False).astype(int)
    return result.sort_values("importance_rank").reset_index(drop=True)


def univariate_stability(old: pd.DataFrame, new: pd.DataFrame, features: list[str], permutations: int = 5000) -> pd.DataFrame:
    rows = []
    for feature in features:
        old_values = pd.to_numeric(old[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        new_values = pd.to_numeric(new[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        direction = np.sign(old_values.loc[old.target.eq(1)].median() - old_values.loc[old.target.eq(0)].median())
        if direction == 0 or not np.isfinite(direction):
            continue
        def oriented_auc(frame: pd.DataFrame, values: pd.Series) -> float:
            mask = values.notna()
            return auc_or_nan(frame.loc[mask, "target"], direction * values.loc[mask])
        observed = oriented_auc(new, new_values)
        valid = new_values.notna()
        permutation_p = stratified_permutation_auc_p(
            new.loc[valid, "target"],
            direction * new_values.loc[valid],
            new.loc[valid, "year"],
            observed,
            permutations,
            RANDOM_SEED + 40,
        )
        subgroup = {}
        for year in (2025, 2026):
            mask = new["year"].eq(year)
            subgroup[f"auc_{year}"] = oriented_auc(new.loc[mask], new_values.loc[mask])
        for side in ("BUY", "SELL"):
            mask = new["BurstSide"].eq(side)
            subgroup[f"auc_{side}"] = oriented_auc(new.loc[mask], new_values.loc[mask])
        rows.append({
            "feature": feature,
            "mechanism_family": ab_research._mechanism_family(feature),
            "direction_from_old_A_minus_B": int(direction),
            "coverage_old_pct": 100 * old_values.notna().mean(),
            "coverage_new_pct": 100 * new_values.notna().mean(),
            "auc_old_oriented": oriented_auc(old, old_values),
            "auc_new_oriented": observed,
            "p_permutation_new_fixed_direction": permutation_p,
            **subgroup,
        })
    result = pd.DataFrame(rows)
    result["q_bh_new"] = bh_adjust(result["p_permutation_new_fixed_direction"])
    result["stable_univariate_candidate"] = (
        result["auc_old_oriented"].ge(0.58)
        & result["auc_new_oriented"].ge(0.60)
        & result["auc_2025"].ge(0.58)
        & result["auc_2026"].ge(0.58)
        & result["auc_BUY"].ge(0.55)
        & result["auc_SELL"].ge(0.55)
        & result["q_bh_new"].le(0.10)
    ).astype(int)
    return result.sort_values(["stable_univariate_candidate", "q_bh_new", "auc_new_oriented"], ascending=[False, True, False]).reset_index(drop=True)


def family_ablation(old: pd.DataFrame, new: pd.DataFrame, eligible: list[str]) -> pd.DataFrame:
    families = sorted({ab_research._mechanism_family(feature) for feature in eligible})
    rows = []
    for family in families:
        family_features = [feature for feature in eligible if ab_research._mechanism_family(feature) == family]
        without = [feature for feature in eligible if feature not in family_features]
        for mode, features in (("ONLY_FAMILY", family_features), ("WITHOUT_FAMILY", without)):
            prediction, metrics, _, selected = fit_experiment(
                old,
                new,
                features,
                "DISCOVERY_TO_NEW",
                f"{mode}:{family}",
                permutation_iterations=0,
            )
            overall = metrics.loc[metrics["subgroup"].eq("ALL")].iloc[0]
            rows.append({
                "family": family,
                "mode": mode,
                "feature_count": len(selected),
                "roc_auc_new": overall["roc_auc"],
                "balanced_accuracy_new": overall["balanced_accuracy"],
                "p_permutation_new": overall["p_permutation_fixed_oos"],
            })
    return pd.DataFrame(rows).sort_values(["mode", "roc_auc_new"], ascending=[True, False]).reset_index(drop=True)


def interactions(model: CatBoostClassifier, selected: list[str]) -> pd.DataFrame:
    try:
        raw = model.get_feature_importance(type="Interaction", prettified=True)
        if isinstance(raw, pd.DataFrame):
            result = raw.copy()
        else:
            result = pd.DataFrame(raw, columns=["first_index", "second_index", "interaction"])
        columns = {str(column).lower(): column for column in result.columns}
        first_col = next(column for key, column in columns.items() if "first" in key)
        second_col = next(column for key, column in columns.items() if "second" in key)
        value_col = next(column for key, column in columns.items() if "interaction" in key)
        result = result.rename(columns={first_col: "first_index", second_col: "second_index", value_col: "interaction_strength"})
        result["feature_1"] = result["first_index"].astype(int).map(lambda index: selected[index])
        result["feature_2"] = result["second_index"].astype(int).map(lambda index: selected[index])
        return result[["feature_1", "feature_2", "interaction_strength"]].head(30)
    except Exception as exc:
        return pd.DataFrame([{"feature_1": "ERROR", "feature_2": str(exc), "interaction_strength": np.nan}])


def bootstrap_auc_delta(predictions: pd.DataFrame, baseline: str, iterations: int = 5000) -> pd.DataFrame:
    pivot = predictions.pivot(index="BurstId", columns="feature_set", values="probability_A")
    identity = predictions.drop_duplicates("BurstId").set_index("BurstId")[["year", "target"]]
    frame = identity.join(pivot, how="inner")
    rng = np.random.default_rng(RANDOM_SEED + 50)
    groups = [np.asarray(indexes) for indexes in frame.groupby(["year", "target"]).groups.values()]
    rows = []
    baseline_auc = auc_or_nan(frame["target"], frame[baseline])
    for feature_set in [column for column in pivot.columns if column != baseline]:
        observed = auc_or_nan(frame["target"], frame[feature_set]) - baseline_auc
        values = []
        for _ in range(iterations):
            indexes = np.concatenate([rng.choice(group, size=len(group), replace=True) for group in groups])
            sample = frame.loc[indexes]
            values.append(auc_or_nan(sample["target"], sample[feature_set]) - auc_or_nan(sample["target"], sample[baseline]))
        rows.append({
            "feature_set": feature_set,
            "baseline": baseline,
            "observed_auc_delta": observed,
            "bootstrap_delta_lower_95": float(np.nanquantile(values, 0.025)),
            "bootstrap_delta_upper_95": float(np.nanquantile(values, 0.975)),
            "probability_delta_gt_zero": float(np.mean(np.asarray(values) > 0)),
        })
    return pd.DataFrame(rows)


def plots(output: Path, metrics: pd.DataFrame, shap: pd.DataFrame, univariate: pd.DataFrame) -> list[Path]:
    folder = output / "visualizations"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    primary = metrics.loc[(metrics["experiment"].eq("DISCOVERY_TO_NEW")) & metrics["subgroup"].eq("ALL")]
    plt.figure(figsize=(9, 5))
    plt.bar(primary["feature_set"], primary["roc_auc"], color="#2b8cbe")
    plt.axhline(0.5, color="black", linestyle="--")
    plt.ylim(0, 1)
    plt.ylabel("ROC AUC 2025–2026")
    plt.title("CatBoost temporal: discovery 2022–2024 → nueva corrida")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    path = folder / "catboost_temporal_auc.png"
    plt.savefig(path, dpi=160)
    plt.close(); paths.append(path)

    view = shap.loc[(shap["experiment"].eq("DISCOVERY_TO_NEW")) & shap["feature_set"].eq("ALL_CAUSAL")].nsmallest(20, "importance_rank").sort_values("mean_abs_shap_oos")
    plt.figure(figsize=(10, 8))
    plt.barh(view["feature"], view["mean_abs_shap_oos"], color="#756bb1")
    plt.xlabel("Mean |SHAP| fuera de muestra")
    plt.title("CatBoost: contribuciones dominantes en 2025–2026")
    plt.tight_layout()
    path = folder / "catboost_shap_oos_top20.png"
    plt.savefig(path, dpi=160)
    plt.close(); paths.append(path)

    plt.figure(figsize=(7, 7))
    colors = np.where(univariate["stable_univariate_candidate"].eq(1), "#31a354", "#969696")
    plt.scatter(univariate["auc_old_oriented"], univariate["auc_new_oriented"], c=colors, alpha=0.75)
    plt.axvline(0.5, color="black", linestyle="--", linewidth=1)
    plt.axhline(0.5, color="black", linestyle="--", linewidth=1)
    plt.xlabel("AUC univariado orientado 2022–2024")
    plt.ylabel("AUC univariado orientación congelada 2025–2026")
    plt.title("Estabilidad temporal de las features causales")
    plt.tight_layout()
    path = folder / "feature_temporal_stability.png"
    plt.savefig(path, dpi=160)
    plt.close(); paths.append(path)
    return paths


def write_report(
    output: Path,
    audit: dict[str, object],
    metrics: pd.DataFrame,
    delta: pd.DataFrame,
    univariate: pd.DataFrame,
    shap: pd.DataFrame,
    ablation: pd.DataFrame,
) -> str:
    primary = metrics.loc[(metrics["experiment"].eq("DISCOVERY_TO_NEW")) & metrics["subgroup"].eq("ALL")]
    strict_2026 = metrics.loc[(metrics["experiment"].eq("THROUGH_2025_TO_2026")) & metrics["subgroup"].eq("ALL")]
    candidates = univariate.loc[univariate["stable_univariate_candidate"].eq(1)]
    top_shap = shap.loc[(shap["experiment"].eq("DISCOVERY_TO_NEW")) & shap["feature_set"].eq("ALL_CAUSAL")].nsmallest(15, "importance_rank")
    lines = [
        "# Diagnóstico CatBoost — Liquidity Burst A vs B",
        "",
        "## Alcance",
        "",
        f"- Discovery 2022–2024: {audit['old_rows']} A/B.",
        f"- Corrida abierta 2025–2026: {audit['new_rows']} A/B.",
        "- Esta investigación es posterior a abrir el holdout. Sirve para generar hipótesis; no crea una nueva validación.",
        "- CatBoost usa profundidad 2, regularización L2 fuerte y parámetros fijos; no se optimiza contra 2025–2026.",
        "- Respuestas 1/3/5 s y campos de outcome no entran como predictores.",
        "",
        "## Desempeño temporal",
        "",
        "| Corte | Features | n | AUC | Balanced acc. | p permutación |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in pd.concat([primary, strict_2026]).itertuples(index=False):
        lines.append(f"| {row.experiment} | {row.feature_set} | {row.n} | {row.roc_auc:.3f} | {row.balanced_accuracy:.3f} | {row.p_permutation_fixed_oos:.4f} |")
    lines.extend([
        "",
        "## Incremento frente al core",
        "",
        "| Features | Delta AUC | Bootstrap 95% | P(delta>0) |",
        "| --- | ---: | ---: | ---: |",
    ])
    for row in delta.itertuples(index=False):
        lines.append(f"| {row.feature_set} | {row.observed_auc_delta:+.3f} | [{row.bootstrap_delta_lower_95:+.3f}, {row.bootstrap_delta_upper_95:+.3f}] | {row.probability_delta_gt_zero:.3f} |")
    lines.extend([
        "",
        "## Features univariadas estables",
        "",
        f"Candidatas que pasan todos los criterios: **{len(candidates)}**.",
        "",
        "| Feature | Familia | AUC old | AUC new | 2025 | 2026 | BUY | SELL | q |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in univariate.head(15).itertuples(index=False):
        lines.append(f"| {row.feature} | {row.mechanism_family} | {row.auc_old_oriented:.3f} | {row.auc_new_oriented:.3f} | {row.auc_2025:.3f} | {row.auc_2026:.3f} | {row.auc_BUY:.3f} | {row.auc_SELL:.3f} | {row.q_bh_new:.3f} |")
    lines.extend([
        "",
        "## SHAP fuera de muestra — ALL_CAUSAL",
        "",
        "| Rango | Feature | Familia | Mean abs SHAP | Corr(value, SHAP) | SHAP A-B |",
        "| ---: | --- | --- | ---: | ---: | ---: |",
    ])
    for row in top_shap.itertuples(index=False):
        lines.append(f"| {row.importance_rank} | {row.feature} | {row.mechanism_family} | {row.mean_abs_shap_oos:.4f} | {row.spearman_value_vs_shap_oos:.3f} | {row.median_shap_A_minus_B_oos:+.4f} |")
    lines.extend([
        "",
        "## Familias",
        "",
        "| Familia | Modo | Features | AUC new |",
        "| --- | --- | ---: | ---: |",
    ])
    for row in ablation.itertuples(index=False):
        lines.append(f"| {row.family} | {row.mode} | {row.feature_count} | {row.roc_auc_new:.3f} |")
    lines.extend([
        "",
        "## Regla de interpretación",
        "",
        "CatBoost sólo demuestra información nueva si ALL_CAUSAL o BURST_MECHANISM supera al CORE fuera de era con "
        "delta positivo, intervalo bootstrap que no cruce cero y estabilidad en 2025/2026 y BUY/SELL. SHAP por sí solo "
        "explica el modelo; no valida una feature.",
    ])
    report = "\n".join(lines) + "\n"
    (output / "catboost_diagnostic_report.md").write_text(report, encoding="utf-8")
    return report


def fable_packet(
    output: Path,
    report: str,
    interactions_frame: pd.DataFrame,
    universe: pd.DataFrame,
) -> None:
    eligible_dictionary = universe.loc[universe["eligible"], [
        "feature", "mechanism_family", "source", "formula", "units", "interpretation",
        "window_start_seconds", "window_end_seconds", "coverage_old_pct", "coverage_new_pct",
    ]]
    top_dictionary = eligible_dictionary.head(0)
    # Include every formula in a compact CSV-style block so Fable can reason
    # about measurement gaps rather than inventing aliases for existing fields.
    dictionary_text = eligible_dictionary.to_csv(index=False)
    interaction_text = interactions_frame.head(20).to_csv(index=False)
    prompt = f"""# Independent review request for Claude Fable

You are reviewing a causal microstructure study. Do not fit or claim a deployable model. The 2025-2026 holdout has already been opened and may only generate hypotheses.

Objective: after detecting a Liquidity Burst, at the original causal decision callback (no 1/3/5-second wait), distinguish true absorption A from clean breakout B. Mixed C is abstention.

Tasks:
1. Audit whether CatBoost found genuine incremental nonlinear information or only small-sample instability.
2. Explain the 2022-2024 to 2025-2026 sign reversal mechanistically.
3. Propose at most 8 genuinely new causal features, not aliases of fields already present. For each give exact formula, source, causal window, availability timestamp, expected A-vs-B direction, physical rationale, redundancy check, and falsification test.
4. Prioritize features that can anticipate at the callback. Do not use post-burst response, MAE/MFE/result, delayed confirmation, or MBO unless the evidence makes it indispensable.
5. Return a clear STOP/CONTINUE decision for feature engineering and name the minimum next experiment. Be skeptical of n=115 and of SHAP as validation.

## CatBoost report

{report}

## Top CatBoost interactions

{interaction_text}

## Existing causal feature dictionary (do not rename these as new)

{dictionary_text}
"""
    (output / "fable_review_packet.md").write_text(prompt, encoding="utf-8")


def run(project: Path, results: Path, output: Path, permutations: int = 5000, bootstraps: int = 5000) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)
    old, new, audit = load_data(project, results)
    universe = feature_universe(old, new)
    eligible = universe.loc[universe["eligible"], "feature"].tolist()
    burst_mechanism = [
        feature for feature in eligible
        if universe.set_index("feature").loc[feature, "source"] in {"burst_events", "engineered"}
    ]
    core = [feature for feature in CORE if feature in eligible or feature == "Signal_To_Entry_Latency_Milliseconds"]
    # The frozen core includes latency. Keep it only in the comparator to match
    # the failed model; candidate sets deliberately exclude system timing.
    core = [feature for feature in CORE if feature in old and feature in new]
    sets = {
        "CORE_FROZEN": core,
        "BURST_MECHANISM": burst_mechanism,
        "ALL_CAUSAL": eligible,
    }

    predictions = []
    metric_frames = []
    shap_frames = []
    primary_models = {}
    primary_selected = {}
    for name, features in sets.items():
        pred, metric, model, selected = fit_experiment(old, new, features, "DISCOVERY_TO_NEW", name)
        predictions.append(pred); metric_frames.append(metric)
        shap_frames.append(shap_rows(model, selected, new, "DISCOVERY_TO_NEW", name))
        primary_models[name] = model; primary_selected[name] = selected

        through_2025 = pd.concat([old, new.loc[new["year"].eq(2025)]], ignore_index=True)
        test_2026 = new.loc[new["year"].eq(2026)].copy()
        pred_26, metric_26, model_26, selected_26 = fit_experiment(
            through_2025, test_2026, features, "THROUGH_2025_TO_2026", name
        )
        predictions.append(pred_26); metric_frames.append(metric_26)
        shap_frames.append(shap_rows(model_26, selected_26, test_2026, "THROUGH_2025_TO_2026", name))

    prediction_frame = pd.concat(predictions, ignore_index=True)
    metrics = pd.concat(metric_frames, ignore_index=True)
    shap = pd.concat(shap_frames, ignore_index=True)
    primary_predictions = prediction_frame.loc[prediction_frame["experiment"].eq("DISCOVERY_TO_NEW")]
    delta = bootstrap_auc_delta(primary_predictions, "CORE_FROZEN", iterations=bootstraps)
    univariate = univariate_stability(old, new, eligible, permutations=permutations)
    ablation = family_ablation(old, new, eligible)
    interaction_frame = interactions(primary_models["ALL_CAUSAL"], primary_selected["ALL_CAUSAL"])

    combined = pd.concat([old, new], ignore_index=True, sort=False)
    combined[["BurstId", "fecha", "year", "era", "BurstSide", "ExecutionSide", "family", "target", *sorted(set(sum(sets.values(), [])))]].to_csv(
        output / "combined_causal_ab.csv", index=False
    )
    universe.to_csv(output / "feature_universe.csv", index=False)
    metrics.to_csv(output / "catboost_temporal_metrics.csv", index=False)
    prediction_frame.to_csv(output / "catboost_oos_predictions.csv", index=False)
    shap.to_csv(output / "catboost_shap_oos.csv", index=False)
    delta.to_csv(output / "catboost_incremental_bootstrap.csv", index=False)
    univariate.to_csv(output / "univariate_temporal_stability.csv", index=False)
    ablation.to_csv(output / "catboost_family_ablation.csv", index=False)
    interaction_frame.to_csv(output / "catboost_interactions.csv", index=False)

    shortlist = univariate.loc[univariate["stable_univariate_candidate"].eq(1)].copy()
    shortlist.to_csv(output / "candidate_feature_shortlist.csv", index=False)
    report = write_report(output, audit, metrics, delta, univariate, shap, ablation)
    fable_packet(output, report, interaction_frame, universe)
    plot_paths = plots(output, metrics, shap, univariate)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        **audit,
        "eligible_feature_count": len(eligible),
        "burst_mechanism_feature_count": len(burst_mechanism),
        "stable_univariate_candidates": shortlist["feature"].tolist(),
        "catboost_parameters_tuned_on_new": False,
        "new_sample_is_fresh_holdout": False,
        "trading_logic_changed": False,
        "atas_launched": False,
        "output": str(output.resolve()),
        "plots": [str(path) for path in plot_paths],
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--results", type=Path, default=Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--permutations", type=int, default=5000)
    parser.add_argument("--bootstraps", type=int, default=5000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(run(args.project, args.results, args.output, args.permutations, args.bootstraps), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
