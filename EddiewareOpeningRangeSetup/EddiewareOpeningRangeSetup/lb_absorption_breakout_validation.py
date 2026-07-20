"""Freeze and evaluate the one-shot Liquidity Burst A-vs-B validation.

The model is learned only from the frozen 2022-2024 discovery manifest.  The
validation command never refits, recalibrates, selects features, or changes a
threshold after reading 2025-2026 outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)

import absorption_breakout_research as ab_research
import causal_regime_baseline_research as regime_research


FAMILY_A = "A_TRUE_ABSORPTION"
FAMILY_B = "B_CLEAN_BREAKOUT"
FAMILY_C = "C_MIXED_PATH"
RANDOM_SEED = 20260720
BOOTSTRAPS = 5000
PERMUTATIONS = 10000
CLASSIFICATION_THRESHOLD = 0.50

# Only the pre-registered, minimal causal baseline is deployed in the frozen
# package.  MBO and the 12 MBP/tape additions are excluded because the pilot
# showed no incremental value and they are not needed to replay the hypothesis.
FEATURES = list(regime_research.CORE_BASELINE_FEATURES)

REGIME_RULES = {
    "VWAP_FAR": {
        "feature": "Directional_VWAP_Distance_Ticks_AtEntry",
        "transform": "absolute",
        "operator": ">",
    },
    "RV60_HIGH": {
        "feature": "Realized_Volatility_60s_Ticks",
        "transform": "identity",
        "operator": ">",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def freeze_package(project: Path, package: Path) -> dict[str, object]:
    """Fit once on the 70 frozen discovery rows and seal the artifact."""
    project = project.resolve()
    package = package.resolve()
    if package.exists():
        raise FileExistsError(f"Frozen package already exists: {package}")

    frame, source_audit = regime_research.load_discovery(project)
    if len(frame) != 70 or frame["BurstId"].nunique() != 70:
        raise ValueError("Freeze requires exactly 70 unique discovery events")
    if not frame["year"].between(2022, 2024).all():
        raise ValueError("A 2025-2026 row reached the freeze dataset")
    if frame["family"].isin([FAMILY_A, FAMILY_B]).sum() != len(frame):
        raise ValueError("Freeze dataset contains a non-A/B family")

    model = regime_research.make_model()
    target = frame["family"].eq(FAMILY_A).astype(int)
    model.fit(frame[FEATURES], target)

    thresholds = {
        "VWAP_FAR": float(frame["Directional_VWAP_Distance_Ticks_AtEntry"].abs().median()),
        "RV60_HIGH": float(frame["Realized_Volatility_60s_Ticks"].median()),
    }

    package.mkdir(parents=True, exist_ok=False)
    model_path = package / "frozen_core_baseline.joblib"
    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "target_positive": FAMILY_A,
            "classification_threshold": CLASSIFICATION_THRESHOLD,
        },
        model_path,
        compress=3,
    )

    discovery_source = project / "outputs" / "causal_regime_baseline_20260720_r1" / "discovery_only_2022_2024.csv"
    oof_source = project / "outputs" / "causal_regime_baseline_20260720_r1" / "baseline_loyo_predictions.csv"
    label_source = project / "absorption_breakout_research.py"
    frozen_rows = frame[["BurstId", "fecha", "year", "family", "burst_side", *FEATURES]].copy()
    frozen_rows.to_csv(package / "frozen_training_rows_2022_2024.csv", index=False)

    spec = {
        "schema_version": "lb-a-vs-b-frozen-validation-2026-07-20-r1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "objective": (
            "After Liquidity Burst detection, classify at the original causal decision callback "
            "whether the path will be true absorption A or clean breakout B."
        ),
        "prediction_cutoff": "feature_timestamp_utc (same callback as original entry decision)",
        "outcome_positive": FAMILY_A,
        "outcome_negative": FAMILY_B,
        "mixed_policy": "C_MIXED_PATH is abstention and is excluded from A/B metrics",
        "other_exit_policy": "D_OTHER_EXIT is reported and excluded from A/B metrics",
        "model": "median imputer + standard scaler + logistic regression C=0.2 class_weight=balanced",
        "features": FEATURES,
        "classification_threshold": CLASSIFICATION_THRESHOLD,
        "regime_rules": {
            name: {**rule, "threshold": thresholds[name]}
            for name, rule in REGIME_RULES.items()
        },
        "regime_selection_policy": (
            "Only VWAP_FAR and RV60_HIGH are retained because both were candidates or stable "
            "under the pre-registered existing and minimal baseline representations. They are "
            "validation strata, not live filters."
        ),
        "primary_validation_gate": {
            "minimum_A": 10,
            "minimum_B": 10,
            "auc_global_min": 0.65,
            "permutation_p_max": 0.05,
            "bootstrap_auc_lower_95_min": 0.50,
            "eligible_year_auc_min": 0.55,
            "eligible_side_auc_min": 0.55,
            "eligible_subgroup_minimum_each_class": 3,
        },
        "regime_support_gate": {
            "coverage_pct_min": 35.0,
            "minimum_A": 8,
            "minimum_B": 8,
            "auc_min": 0.70,
            "auc_improvement_vs_complement_min": 0.10,
            "eligible_year_auc_min": 0.55,
            "eligible_side_auc_min": 0.55,
            "eligible_subgroup_minimum_each_class": 3,
        },
        "training": {
            **source_audit,
            "allowed_years": [2022, 2023, 2024],
            "validation_years_opened": [],
            "model_sha256": sha256_file(model_path),
            "frozen_rows_sha256": sha256_file(package / "frozen_training_rows_2022_2024.csv"),
            "discovery_source_sha256": sha256_file(discovery_source),
            "oof_source_sha256": sha256_file(oof_source),
            "label_source_sha256": sha256_file(label_source),
        },
        "excluded_from_predictors": [
            "burst_response_events 1s/3s/5s",
            "MAE/MFE/result/exit/future fields",
            "MBO",
            "12 MBP/tape incremental features",
        ],
        "trading_logic_changed": False,
        "model_path": str(model_path),
    }
    spec_path = package / "frozen_spec.json"
    _json_write(spec_path, spec)
    return spec


def load_package(package: Path) -> tuple[dict[str, object], dict[str, object]]:
    package = package.resolve()
    spec_path = package / "frozen_spec.json"
    model_path = package / "frozen_core_baseline.joblib"
    if not spec_path.exists() or not model_path.exists():
        raise FileNotFoundError(f"Incomplete frozen package: {package}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    expected_hash = spec["training"]["model_sha256"]
    actual_hash = sha256_file(model_path)
    if actual_hash != expected_hash:
        raise ValueError("Frozen model SHA256 does not match its sealed specification")
    bundle = joblib.load(model_path)
    if list(bundle.get("features", [])) != list(spec.get("features", [])):
        raise ValueError("Feature order differs between model and frozen specification")
    return spec, bundle


def _rule_mask(frame: pd.DataFrame, rule: dict[str, object]) -> pd.Series:
    values = pd.to_numeric(frame[str(rule["feature"])], errors="coerce")
    if rule["transform"] == "absolute":
        values = values.abs()
    if rule["operator"] != ">":
        raise ValueError(f"Unsupported frozen operator: {rule['operator']}")
    return values.gt(float(rule["threshold"]))


def _auc(target: pd.Series, probability: pd.Series) -> float:
    return float(roc_auc_score(target, probability)) if target.nunique() == 2 else np.nan


def _metric_row(group: pd.DataFrame, subgroup: str) -> dict[str, object]:
    target = group["target"].astype(int)
    probability = group["probability_A"].astype(float)
    predicted = group["predicted_A"].astype(int)
    n_a = int(target.sum())
    n_b = int((1 - target).sum())
    if target.nunique() == 2:
        tn, fp, fn, tp = confusion_matrix(target, predicted, labels=[0, 1]).ravel()
        sensitivity = tp / (tp + fn) if tp + fn else np.nan
        specificity = tn / (tn + fp) if tn + fp else np.nan
        balanced = float(balanced_accuracy_score(target, predicted))
        brier = float(brier_score_loss(target, probability))
    else:
        sensitivity = specificity = balanced = brier = np.nan
    return {
        "subgroup": subgroup,
        "n": len(group),
        "n_A": n_a,
        "n_B": n_b,
        "coverage_pct": np.nan,
        "roc_auc": _auc(target, probability),
        "balanced_accuracy_at_0_5": balanced,
        "sensitivity_absorption_A": sensitivity,
        "specificity_breakout_B": specificity,
        "brier_score": brier,
    }


def _permutation_p(frame: pd.DataFrame) -> float:
    if frame["target"].nunique() != 2:
        return np.nan
    observed = _auc(frame["target"], frame["probability_A"])
    rng = np.random.default_rng(RANDOM_SEED + 10)
    exceed = 0
    for _ in range(PERMUTATIONS):
        shuffled = frame["target"].copy()
        for _, indexes in frame.groupby("year").groups.items():
            shuffled.loc[indexes] = rng.permutation(shuffled.loc[indexes].to_numpy())
        exceed += _auc(shuffled, frame["probability_A"]) >= observed
    return float((1 + exceed) / (1 + PERMUTATIONS))


def _bootstrap_auc(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    rng = np.random.default_rng(RANDOM_SEED + 11)
    groups = [np.asarray(indexes) for indexes in frame.groupby(["year", "target"]).groups.values()]
    rows = []
    for iteration in range(BOOTSTRAPS):
        indexes = np.concatenate([rng.choice(group, size=len(group), replace=True) for group in groups])
        sample = frame.loc[indexes]
        rows.append({"iteration": iteration, "roc_auc": _auc(sample["target"], sample["probability_A"])})
    distribution = pd.DataFrame(rows)
    return distribution, {
        "iterations": BOOTSTRAPS,
        "median": float(distribution["roc_auc"].median()),
        "lower_95": float(distribution["roc_auc"].quantile(0.025)),
        "upper_95": float(distribution["roc_auc"].quantile(0.975)),
    }


def _primary_gate(metrics: pd.DataFrame, p_value: float, bootstrap: dict[str, float], spec: dict[str, object]) -> tuple[pd.DataFrame, bool]:
    gate = spec["primary_validation_gate"]
    table = metrics.set_index("subgroup")
    overall = table.loc["ALL_AB"]
    checks: list[tuple[str, float, str, float, bool]] = [
        ("MINIMUM_A", float(overall.n_A), ">=", float(gate["minimum_A"]), overall.n_A >= gate["minimum_A"]),
        ("MINIMUM_B", float(overall.n_B), ">=", float(gate["minimum_B"]), overall.n_B >= gate["minimum_B"]),
        ("GLOBAL_AUC", float(overall.roc_auc), ">=", float(gate["auc_global_min"]), overall.roc_auc >= gate["auc_global_min"]),
        ("PERMUTATION_P", float(p_value), "<=", float(gate["permutation_p_max"]), p_value <= gate["permutation_p_max"]),
        ("BOOTSTRAP_LOWER_95", float(bootstrap["lower_95"]), ">=", float(gate["bootstrap_auc_lower_95_min"]), bootstrap["lower_95"] >= gate["bootstrap_auc_lower_95_min"]),
    ]
    eligible_min = int(gate["eligible_subgroup_minimum_each_class"])
    for row in metrics.loc[metrics["subgroup"].str.startswith(("YEAR_", "BURST_SIDE_"))].itertuples(index=False):
        if row.n_A < eligible_min or row.n_B < eligible_min:
            continue
        threshold = gate["eligible_year_auc_min"] if row.subgroup.startswith("YEAR_") else gate["eligible_side_auc_min"]
        checks.append((f"{row.subgroup}_AUC", float(row.roc_auc), ">=", float(threshold), row.roc_auc >= threshold))
    result = pd.DataFrame(checks, columns=["criterion", "observed", "operator", "threshold", "passed"])
    return result, bool(result["passed"].all())


def _regime_gate(ledger: pd.DataFrame, metrics: pd.DataFrame, spec: dict[str, object]) -> pd.DataFrame:
    gate = spec["regime_support_gate"]
    table = metrics.set_index("subgroup")
    rows = []
    for name in spec["regime_rules"]:
        subgroup = f"REGIME_{name}"
        complement = f"COMPLEMENT_{name}"
        row = table.loc[subgroup]
        comp = table.loc[complement]
        conditions = {
            "coverage": row.coverage_pct >= gate["coverage_pct_min"],
            "minimum_A": row.n_A >= gate["minimum_A"],
            "minimum_B": row.n_B >= gate["minimum_B"],
            "auc": row.roc_auc >= gate["auc_min"],
            "delta": row.roc_auc - comp.roc_auc >= gate["auc_improvement_vs_complement_min"],
        }
        mask = ledger[f"regime_{name}"].astype(bool)
        segment = ledger.loc[mask]
        eligible_min = int(gate["eligible_subgroup_minimum_each_class"])
        subgroup_aucs = []
        for _, child in segment.groupby("year"):
            if child["target"].sum() >= eligible_min and (1 - child["target"]).sum() >= eligible_min:
                subgroup_aucs.append(_auc(child["target"], child["probability_A"]))
        for _, child in segment.groupby("BurstSide"):
            if child["target"].sum() >= eligible_min and (1 - child["target"]).sum() >= eligible_min:
                subgroup_aucs.append(_auc(child["target"], child["probability_A"]))
        conditions["eligible_subgroups"] = bool(subgroup_aucs) and min(subgroup_aucs) >= min(
            gate["eligible_year_auc_min"], gate["eligible_side_auc_min"]
        )
        rows.append({
            "regime": name,
            "coverage_pct": row.coverage_pct,
            "n_A": int(row.n_A),
            "n_B": int(row.n_B),
            "roc_auc": row.roc_auc,
            "complement_auc": comp.roc_auc,
            "auc_improvement_vs_complement": row.roc_auc - comp.roc_auc,
            "eligible_subgroup_min_auc": min(subgroup_aucs) if subgroup_aucs else np.nan,
            **{f"passed_{key}": bool(value) for key, value in conditions.items()},
            "supported": bool(all(conditions.values())),
        })
    return pd.DataFrame(rows)


def _plots(output: Path, ledger: pd.DataFrame, metrics: pd.DataFrame, bootstrap: pd.DataFrame) -> list[Path]:
    folder = output / "visualizations"
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    plt.figure(figsize=(8, 6))
    for family, color in ((FAMILY_A, "#2ca25f"), (FAMILY_B, "#de2d26")):
        values = ledger.loc[ledger["family"].eq(family), "probability_A"]
        if not values.empty:
            plt.hist(values, bins=min(15, max(5, len(values) // 2)), alpha=0.55, density=True, label=family, color=color)
    plt.axvline(CLASSIFICATION_THRESHOLD, color="black", linestyle="--", linewidth=1)
    plt.xlabel("Probabilidad congelada de absorción A")
    plt.ylabel("Densidad")
    plt.title("Separación ciega A vs B — DST 2025–2026")
    plt.legend()
    plt.tight_layout()
    path = folder / "probability_distribution_A_vs_B.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(path)

    if ledger["target"].nunique() == 2:
        fpr, tpr, _ = roc_curve(ledger["target"], ledger["probability_A"])
        auc_value = _auc(ledger["target"], ledger["probability_A"])
        plt.figure(figsize=(6.5, 6.5))
        plt.plot(fpr, tpr, color="#2b8cbe", linewidth=2, label=f"AUC={auc_value:.3f}")
        plt.plot([0, 1], [0, 1], "k--", linewidth=1)
        plt.xlabel("False positive rate")
        plt.ylabel("True positive rate")
        plt.title("ROC holdout temporal congelado")
        plt.legend(loc="lower right")
        plt.tight_layout()
        path = folder / "roc_holdout_2025_2026.png"
        plt.savefig(path, dpi=160)
        plt.close()
        paths.append(path)

    chart = metrics.loc[metrics["subgroup"].isin(["ALL_AB", "YEAR_2025", "YEAR_2026", "BURST_SIDE_BUY", "BURST_SIDE_SELL", "REGIME_VWAP_FAR", "REGIME_RV60_HIGH"])].copy()
    plt.figure(figsize=(10, 6))
    plt.bar(chart["subgroup"], chart["roc_auc"], color="#756bb1")
    plt.axhline(0.5, color="black", linestyle="--", linewidth=1)
    plt.axhline(0.7, color="#31a354", linestyle=":", linewidth=1)
    plt.ylim(0, 1)
    plt.ylabel("ROC AUC")
    plt.title("Estabilidad del clasificador congelado")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    path = folder / "auc_stability_holdout.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(path)

    plt.figure(figsize=(8, 5))
    plt.hist(bootstrap["roc_auc"].dropna(), bins=35, color="#2b8cbe", alpha=0.85)
    plt.axvline(0.5, color="black", linestyle="--", linewidth=1)
    plt.xlabel("AUC bootstrap estratificado")
    plt.ylabel("Frecuencia")
    plt.title("Incertidumbre del AUC holdout")
    plt.tight_layout()
    path = folder / "auc_bootstrap_holdout.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(path)
    return paths


def validate(package: Path, results: Path, output: Path) -> dict[str, object]:
    """Apply the sealed package once to the isolated 2025-2026 capture."""
    spec, bundle = load_package(package)
    if output.exists():
        raise FileExistsError(f"Validation output already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)

    dataset, source_audit = ab_research.build_dataset(results)
    if dataset.empty:
        raise ValueError("Validation capture has no joinable Liquidity Burst trades")
    dataset["year"] = pd.to_datetime(dataset["fecha"], errors="raise").dt.year
    outside = dataset.loc[~dataset["year"].isin([2025, 2026])]
    if not outside.empty:
        raise ValueError(f"Isolated validation capture contains years outside 2025-2026: {sorted(outside.year.unique())}")

    dataset["detector_publish_timestamp"] = pd.to_datetime(
        dataset.get("Detector_Publish_Timestamp_UTC"), utc=True, errors="coerce"
    )
    dataset["publish_before_prediction"] = dataset["detector_publish_timestamp"].le(dataset["prediction_timestamp"])
    dataset["prediction_not_after_entry"] = dataset["prediction_timestamp"].le(dataset["entry_timestamp_utc_parsed"])
    if not dataset["causal_row_flag"].all():
        raise ValueError("A non-causal row reached the blind validation")
    if not dataset["publish_before_prediction"].all():
        raise ValueError("A prediction precedes the detector's actual publication")
    if not dataset["prediction_not_after_entry"].all():
        raise ValueError("A prediction timestamp is after entry")

    for feature in spec["features"]:
        if feature not in dataset:
            raise ValueError(f"Frozen feature missing from validation capture: {feature}")
        dataset[feature] = pd.to_numeric(dataset[feature], errors="coerce")

    dataset["probability_A"] = bundle["model"].predict_proba(dataset[spec["features"]])[:, 1]
    dataset["predicted_A"] = dataset["probability_A"].ge(spec["classification_threshold"]).astype(int)
    dataset["prediction_label"] = np.where(dataset["predicted_A"].eq(1), FAMILY_A, FAMILY_B)
    dataset["target"] = dataset["family"].eq(FAMILY_A).astype(int)
    for name, rule in spec["regime_rules"].items():
        dataset[f"regime_{name}"] = _rule_mask(dataset, rule)

    ab = dataset.loc[dataset["family"].isin([FAMILY_A, FAMILY_B])].copy().reset_index(drop=True)
    if ab.empty:
        raise ValueError("No strict A/B outcomes exist in the validation capture")

    metric_rows = [_metric_row(ab, "ALL_AB")]
    for year, group in ab.groupby("year"):
        metric_rows.append(_metric_row(group, f"YEAR_{year}"))
    for side, group in ab.groupby("BurstSide"):
        metric_rows.append(_metric_row(group, f"BURST_SIDE_{str(side).upper()}"))
    for name in spec["regime_rules"]:
        mask = ab[f"regime_{name}"].astype(bool)
        inside = _metric_row(ab.loc[mask], f"REGIME_{name}")
        outside_row = _metric_row(ab.loc[~mask], f"COMPLEMENT_{name}")
        inside["coverage_pct"] = 100 * int(mask.sum()) / len(ab)
        outside_row["coverage_pct"] = 100 * int((~mask).sum()) / len(ab)
        metric_rows.extend([inside, outside_row])
    metrics = pd.DataFrame(metric_rows)

    p_value = _permutation_p(ab)
    bootstrap_distribution, bootstrap_summary = _bootstrap_auc(ab)
    primary_gate, primary_pass = _primary_gate(metrics, p_value, bootstrap_summary, spec)
    regime_gate = _regime_gate(ab, metrics, spec)
    supported_regimes = regime_gate.loc[regime_gate["supported"], "regime"].tolist()
    conclusion = "SUPPORTED" if primary_pass or supported_regimes else "NOT_SUPPORTED"

    ledger_columns = [
        "fecha", "BurstId", "prediction_timestamp", "detector_publish_timestamp",
        "entry_timestamp_utc_parsed", "ExecutionSide", "BurstSide", "family", "family_reason",
        "probability_A", "predicted_A", "prediction_label", *[f"regime_{name}" for name in spec["regime_rules"]],
        "causal_row_flag", "publish_before_prediction", "prediction_not_after_entry", *spec["features"],
    ]
    dataset[ledger_columns].to_csv(output / "validation_event_ledger.csv", index=False)
    metrics.to_csv(output / "validation_metrics.csv", index=False)
    primary_gate.to_csv(output / "primary_validation_gate.csv", index=False)
    regime_gate.to_csv(output / "regime_validation_gate.csv", index=False)
    bootstrap_distribution.to_csv(output / "validation_bootstrap_distribution.csv", index=False)
    source_audit.to_csv(output / "source_dataset_audit.csv", index=False)
    plots = _plots(output, ab, metrics, bootstrap_distribution)

    family_counts = dataset["family"].value_counts().sort_index().to_dict()
    overall = metrics.set_index("subgroup").loc["ALL_AB"]
    report_lines = [
        "# Validación temporal ciega — Liquidity Burst: absorción A vs breakout B",
        "",
        f"Conclusión congelada: **{conclusion}**.",
        "",
        "## Objetivo y cutoff",
        "",
        "El detector identifica el Liquidity Burst. El clasificador estima A vs B en `feature_timestamp_utc`, "
        "el mismo callback causal de la decisión original, después de la publicación real del detector y sin esperar 1/3/5 s.",
        "",
        "- Modelo/variables/umbrales congelados con 70 eventos de 2022–2024.",
        "- Reentrenamientos o ajustes usando 2025–2026: **0**.",
        "- MBO y MBP incremental: excluidos.",
        "- C mixto: abstención; no se fuerza a A/B.",
        "- La lógica operativa no fue modificada.",
        "",
        "## Muestra",
        "",
        f"- Eventos unidos: {len(dataset)}.",
        f"- A/B estrictos: {len(ab)} ({int(overall.n_A)} A, {int(overall.n_B)} B).",
        f"- Familias: `{json.dumps(family_counts, ensure_ascii=False)}`.",
        "",
        "## Resultado principal",
        "",
        f"- AUC: {overall.roc_auc:.3f}.",
        f"- Balanced accuracy @0.5: {overall.balanced_accuracy_at_0_5:.3f}.",
        f"- Sensibilidad absorción A: {overall.sensitivity_absorption_A:.3f}.",
        f"- Especificidad breakout B: {overall.specificity_breakout_B:.3f}.",
        f"- p permutación temporal: {p_value:.4f}.",
        f"- Bootstrap 95% AUC: [{bootstrap_summary['lower_95']:.3f}, {bootstrap_summary['upper_95']:.3f}].",
        "",
        "## Regímenes congelados",
        "",
        "| Régimen | Cobertura | A/B | AUC | Complemento | Delta | Soportado |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in regime_gate.itertuples(index=False):
        report_lines.append(
            f"| {row.regime} | {row.coverage_pct:.1f}% | {row.n_A}/{row.n_B} | "
            f"{row.roc_auc:.3f} | {row.complement_auc:.3f} | "
            f"{row.auc_improvement_vs_complement:+.3f} | {int(row.supported)} |"
        )
    report_lines.extend([
        "",
        "## Interpretación permitida",
        "",
        "`SUPPORTED` significa que el baseline causal o al menos uno de los dos contextos congelados sobrevivió "
        "fuera de muestra. No autoriza por sí solo un filtro operativo; primero se revisan cobertura, errores y C mixtos.",
        "`NOT_SUPPORTED` detiene esta línea: no se reajusta el modelo sobre 2025–2026.",
    ])
    report = "\n".join(report_lines) + "\n"
    (output / "final_validation_report.md").write_text(report, encoding="utf-8")

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "package": str(package.resolve()),
        "package_model_sha256": spec["training"]["model_sha256"],
        "results": str(results.resolve()),
        "output": str(output.resolve()),
        "rows": len(dataset),
        "families": family_counts,
        "primary_gate_passed": primary_pass,
        "supported_regimes": supported_regimes,
        "conclusion": conclusion,
        "validation_years": sorted(int(value) for value in dataset["year"].unique()),
        "model_refit_count": 0,
        "threshold_changes": 0,
        "trading_logic_changed": False,
        "plots": [str(path) for path in plots],
    }
    _json_write(output / "validation_manifest.json", manifest)
    return {"manifest": manifest, "report": report, "plots": plots}


def send_validation_to_telegram(results: Path, validation: dict[str, object]) -> bool:
    from telegram_run_summary_after_sync import send_photo, send_text

    manifest = validation["manifest"]
    header = (
        "LIQUIDITY BURST | VALIDACION CIEGA A vs B\n"
        f"Conclusion: {manifest['conclusion']}\n"
        f"Eventos: {manifest['rows']} | Familias: {manifest['families']}\n"
        f"Regimenes soportados: {manifest['supported_regimes'] or 'ninguno'}\n"
        "Modelo/umbrales congelados en 2022-2024; 0 reentrenamientos con 2025-2026."
    )
    ok = send_text(str(results), header)
    paragraphs = validation["report"].split("\n\n")
    chunk = ""
    chunks = []
    for paragraph in paragraphs:
        candidate = paragraph if not chunk else chunk + "\n\n" + paragraph
        if len(candidate) <= 3500:
            chunk = candidate
        else:
            if chunk:
                chunks.append(chunk)
            chunk = paragraph
    if chunk:
        chunks.append(chunk)
    for index, text in enumerate(chunks, 1):
        ok = send_text(str(results), f"[{index}/{len(chunks)}] {text}") and ok
    for path in validation["plots"]:
        ok = send_photo(str(results), str(path), "LB A vs B | holdout temporal") and ok
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--package", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze", action="store_true")
    action.add_argument("--validate", action="store_true")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--telegram", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.freeze:
        print(json.dumps(freeze_package(args.project, args.package), indent=2, default=str))
        return 0
    if args.results is None or args.output is None:
        raise SystemExit("--validate requires --results and --output")
    result = validate(args.package, args.results, args.output)
    print(json.dumps(result["manifest"], indent=2, default=str))
    if args.telegram and not send_validation_to_telegram(args.results, result):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
