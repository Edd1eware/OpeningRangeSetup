"""Preregistered discovery analysis combining causal post-LB matrices and MBO.

The experiment is deliberately narrow:

* MBO predictors use only ``ts_event <= causal_cutoff``;
* matrix predictors use only ``t_burst <= event <= t_decision``;
* labels are joined by ``BurstId`` after both representations are built;
* feature families are frozen and evaluated with leave-one-year-out predictions.

The 100-session pilot is discovery-only.  It can authorize a sealed validation
purchase, but it cannot produce the definitive capability verdict by itself.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import lb_matrix_classification_research as matrix
import mbo_liquidity_burst_research as mbo


RANDOM_SEED = 20260722
PERMUTATIONS = 1000
BOOTSTRAPS = 1000
MODEL_C = 0.2
FAMILY_A = "A_TRUE_ABSORPTION"
FAMILY_B = "B_CLEAN_BREAKOUT"
FAMILY_C = "C_MIXED_PATH"
PRIMARY_FAMILY = "MATRIX_TRANSITIONS_SEQUENCES_PLUS_MBO_CORE"
MBO_CAPABILITY_VERDICT = "B_SIRVEN_PARCIALMENTE"
FINAL_NO = "NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO"

FAMILY_ORDER = (
    "MATRIX_TRANSITIONS",
    "MATRIX_SEQUENCES",
    "MATRIX_TRANSITIONS_SEQUENCES",
    "MBO_CORE",
    "MATRIX_TRANSITIONS_PLUS_MBO_CORE",
    "MATRIX_SEQUENCES_PLUS_MBO_CORE",
    PRIMARY_FAMILY,
)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False)


def _make_model() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(
            C=MODEL_C,
            class_weight="balanced",
            solver="liblinear",
            max_iter=3000,
            random_state=RANDOM_SEED,
        ),
    )


def _usable_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    usable: list[str] = []
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().sum() >= 3 and values.dropna().nunique() >= 2:
            usable.append(column)
    if not usable:
        raise ValueError("No usable predictors in LOYO training fold")
    return usable


def _loyo_predictions(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    target: pd.Series | None = None,
) -> pd.DataFrame:
    y = frame["target"].astype(int) if target is None else pd.Series(target.to_numpy(), index=frame.index)
    rows: list[dict[str, object]] = []
    for year in sorted(frame["year"].unique()):
        train = frame["year"].ne(year)
        test = frame["year"].eq(year)
        selected = _usable_columns(frame.loc[train], columns)
        if y.loc[train].nunique() < 2:
            raise ValueError(f"Training fold without both classes for test year {year}")
        model = _make_model()
        model.fit(frame.loc[train, selected], y.loc[train])
        probability = model.predict_proba(frame.loc[test, selected])[:, 1]
        for index, value in zip(frame.index[test], probability, strict=True):
            rows.append(
                {
                    "row_index": int(index),
                    "BurstId": frame.at[index, "BurstId"],
                    "fecha": frame.at[index, "fecha"],
                    "year": int(year),
                    "burst_side": frame.at[index, "burst_side"],
                    "family": frame.at[index, "family"],
                    "target": int(y.at[index]),
                    "probability_A": float(value),
                    "prediction": int(value >= 0.5),
                    "feature_count": len(selected),
                }
            )
    return pd.DataFrame(rows).sort_values("row_index").reset_index(drop=True)


def _metrics(predictions: pd.DataFrame) -> dict[str, float | int]:
    if predictions.empty or predictions["target"].nunique() < 2:
        return {
            "n": len(predictions),
            "n_A": int(predictions.get("target", pd.Series(dtype=int)).eq(1).sum()),
            "n_B": int(predictions.get("target", pd.Series(dtype=int)).eq(0).sum()),
            "balanced_accuracy": np.nan,
            "roc_auc_A_vs_B": np.nan,
            "sensitivity_A": np.nan,
            "specificity_B": np.nan,
        }
    y = predictions["target"].to_numpy(dtype=int)
    pred = predictions["prediction"].to_numpy(dtype=int)
    probability = predictions["probability_A"].to_numpy(dtype=float)
    return {
        "n": len(predictions),
        "n_A": int((y == 1).sum()),
        "n_B": int((y == 0).sum()),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "roc_auc_A_vs_B": float(roc_auc_score(y, probability)),
        "sensitivity_A": float(pred[y == 1].mean()),
        "specificity_B": float((pred[y == 0] == 0).mean()),
    }


def _bootstrap_ci(predictions: pd.DataFrame) -> tuple[float, float]:
    rng = np.random.default_rng(RANDOM_SEED)
    y = predictions["target"].to_numpy(dtype=int)
    pred = predictions["prediction"].to_numpy(dtype=int)
    groups = [np.flatnonzero(y == value) for value in (0, 1)]
    if any(len(group) == 0 for group in groups):
        return np.nan, np.nan
    values: list[float] = []
    for _ in range(BOOTSTRAPS):
        sampled = np.concatenate([rng.choice(group, len(group), replace=True) for group in groups])
        values.append(float(balanced_accuracy_score(y[sampled], pred[sampled])))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def _permutation_p_value(frame: pd.DataFrame, columns: list[str], observed: float) -> float:
    rng = np.random.default_rng(RANDOM_SEED)
    exceed = 0
    for _ in range(PERMUTATIONS):
        shuffled = frame["target"].copy()
        for indexes in frame.groupby("year").groups.values():
            shuffled.loc[indexes] = rng.permutation(shuffled.loc[indexes].to_numpy())
        permuted = _loyo_predictions(frame, columns, target=shuffled)
        score = float(_metrics(permuted)["balanced_accuracy"])
        exceed += int(score >= observed - 1e-12)
    return float((exceed + 1) / (PERMUTATIONS + 1))


def _build_matrix_predictors(
    results_folder: Path,
    manifest: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    timeline = matrix.load_timeline(results_folder)
    causal_audit, passed, post = matrix.audit_timeline(timeline)
    if not passed:
        raise RuntimeError("Matrix post-burst causal audit failed")
    states, sequences = matrix.build_macro_states(post)
    transitions = matrix.build_transition_events(post, states)
    occurrences = matrix._pattern_occurrences(states)  # label-free support mining

    ids = set(manifest["BurstId"].astype(str))
    transitions = transitions.loc[transitions["BurstId"].astype(str).isin(ids)].copy()
    occurrences = occurrences.loc[occurrences["BurstId"].astype(str).isin(ids)].copy()
    sequences = sequences.loc[sequences["BurstId"].astype(str).isin(ids)].copy()

    transition_presence = transitions[["BurstId", "transition"]].drop_duplicates()
    transition_rank = transition_presence["transition"].value_counts()
    selected_transitions = transition_rank.loc[transition_rank.ge(3)].head(6).index.tolist()

    sequence_presence = occurrences[["BurstId", "pattern"]].drop_duplicates()
    eligible_sequences = sequence_presence.loc[sequence_presence["pattern"].str.count(">").between(2, 3)]
    sequence_rank = eligible_sequences["pattern"].value_counts()
    selected_sequences = sequence_rank.loc[sequence_rank.ge(3)].head(6).index.tolist()

    predictors = manifest[["BurstId", "fecha", "split", "family_label_only"]].copy()
    for pattern in selected_transitions:
        present = set(transition_presence.loc[transition_presence["transition"].eq(pattern), "BurstId"])
        predictors[f"tr__{pattern}"] = predictors["BurstId"].isin(present).astype(int)
    for pattern in selected_sequences:
        present = set(sequence_presence.loc[sequence_presence["pattern"].eq(pattern), "BurstId"])
        predictors[f"sq__{pattern}"] = predictors["BurstId"].isin(present).astype(int)

    feature_manifest = pd.DataFrame(
        [
            {
                "feature_family": "MATRIX_TRANSITIONS",
                "feature": f"tr__{pattern}",
                "selection_rule": "top support >=3, labels unavailable",
                "support": int(transition_rank.get(pattern, 0)),
            }
            for pattern in selected_transitions
        ]
        + [
            {
                "feature_family": "MATRIX_SEQUENCES",
                "feature": f"sq__{pattern}",
                "selection_rule": "top support >=3, labels unavailable",
                "support": int(sequence_rank.get(pattern, 0)),
            }
            for pattern in selected_sequences
        ]
    )
    coverage = pd.DataFrame(
        [
            {
                "manifest_bursts": int(manifest["BurstId"].nunique()),
                "matrix_sequence_bursts": int(sequences["BurstId"].nunique()),
                "matrix_transition_bursts": int(transitions["BurstId"].nunique()),
                "selected_transitions": len(selected_transitions),
                "selected_sequences": len(selected_sequences),
            }
        ]
    )
    return predictors, feature_manifest, causal_audit, coverage


def _feature_sets(frame: pd.DataFrame) -> dict[str, list[str]]:
    transitions = [column for column in frame if column.startswith("tr__")]
    sequences = [column for column in frame if column.startswith("sq__")]
    mbo_core = [column for column in mbo.CORE_MBO_FEATURES if column in frame]
    if len(mbo_core) != len(mbo.CORE_MBO_FEATURES):
        missing = sorted(set(mbo.CORE_MBO_FEATURES) - set(mbo_core))
        raise ValueError(f"Missing frozen MBO features: {missing}")
    return {
        "MATRIX_TRANSITIONS": transitions,
        "MATRIX_SEQUENCES": sequences,
        "MATRIX_TRANSITIONS_SEQUENCES": transitions + sequences,
        "MBO_CORE": mbo_core,
        "MATRIX_TRANSITIONS_PLUS_MBO_CORE": transitions + mbo_core,
        "MATRIX_SEQUENCES_PLUS_MBO_CORE": sequences + mbo_core,
        PRIMARY_FAMILY: transitions + sequences + mbo_core,
    }


def _evaluate(
    clean: pd.DataFrame,
    feature_sets: dict[str, list[str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, object]] = []
    prediction_rows: list[pd.DataFrame] = []
    for family in FAMILY_ORDER:
        columns = feature_sets[family]
        predictions = _loyo_predictions(clean, columns)
        predictions["feature_family"] = family
        prediction_rows.append(predictions)
        overall = _metrics(predictions)
        ci_low, ci_high = _bootstrap_ci(predictions)
        permutation_p = _permutation_p_value(clean, columns, float(overall["balanced_accuracy"]))
        slice_values: dict[str, float] = {}
        for year, group in predictions.groupby("year"):
            slice_values[f"ba_year_{int(year)}"] = float(_metrics(group)["balanced_accuracy"])
        for side, group in predictions.groupby("burst_side"):
            slice_values[f"ba_side_{side}"] = float(_metrics(group)["balanced_accuracy"])
        stability_values = [
            value for key, value in slice_values.items()
            if key.startswith(("ba_year_", "ba_side_")) and math.isfinite(value)
        ]
        metric_rows.append(
            {
                "feature_family": family,
                "model": "logistic_C_0.2_balanced",
                "validation": "LOYO_2022_2023_2024",
                "feature_count": len(columns),
                **overall,
                "balanced_accuracy_ci_low": ci_low,
                "balanced_accuracy_ci_high": ci_high,
                "permutation_p_within_year": permutation_p,
                "minimum_year_side_balanced_accuracy": min(stability_values) if stability_values else np.nan,
                **slice_values,
            }
        )
    metrics = pd.DataFrame(metric_rows)
    best_single = float(
        metrics.loc[
            metrics["feature_family"].isin(
                ["MATRIX_TRANSITIONS", "MATRIX_SEQUENCES", "MATRIX_TRANSITIONS_SEQUENCES", "MBO_CORE"]
            ),
            "balanced_accuracy",
        ].max()
    )
    best_single_auc = float(
        metrics.loc[
            metrics["feature_family"].isin(
                ["MATRIX_TRANSITIONS", "MATRIX_SEQUENCES", "MATRIX_TRANSITIONS_SEQUENCES", "MBO_CORE"]
            ),
            "roc_auc_A_vs_B",
        ].max()
    )
    metrics["gain_vs_best_single_balanced_accuracy"] = metrics["balanced_accuracy"] - best_single
    metrics["gain_vs_best_single_auc"] = metrics["roc_auc_A_vs_B"] - best_single_auc
    metrics["discovery_gate_passed"] = (
        metrics["n"].ge(60)
        & metrics["balanced_accuracy"].ge(0.65)
        & metrics["roc_auc_A_vs_B"].ge(0.68)
        & metrics["sensitivity_A"].ge(0.60)
        & metrics["specificity_B"].ge(0.60)
        & metrics["balanced_accuracy_ci_low"].gt(0.55)
        & metrics["permutation_p_within_year"].le(0.05)
        & metrics["minimum_year_side_balanced_accuracy"].ge(0.55)
        & (
            metrics["gain_vs_best_single_balanced_accuracy"].ge(0.03)
            | metrics["gain_vs_best_single_auc"].ge(0.03)
        )
    )
    metrics["pilot_status"] = np.where(
        metrics["discovery_gate_passed"],
        "PROMETEDORA_DISCOVERY",
        "NO_SUPERA_PUERTA_DISCOVERY",
    )
    return metrics.sort_values(
        ["discovery_gate_passed", "balanced_accuracy", "roc_auc_A_vs_B"],
        ascending=[False, False, False],
    ).reset_index(drop=True), pd.concat(prediction_rows, ignore_index=True)


def _plot_metrics(metrics: pd.DataFrame, output: Path) -> str:
    ordered = metrics.sort_values("balanced_accuracy")
    labels = ordered["feature_family"].str.replace("MATRIX_", "M_").str.replace("_PLUS_", "+")
    y = np.arange(len(ordered))
    plt.figure(figsize=(12, 7))
    plt.barh(y - 0.18, ordered["balanced_accuracy"], height=0.34, label="Balanced accuracy LOYO")
    plt.barh(y + 0.18, ordered["roc_auc_A_vs_B"], height=0.34, label="ROC AUC LOYO")
    plt.axvline(0.5, color="black", linestyle="--", linewidth=1)
    plt.yticks(y, labels)
    plt.xlim(0, 1)
    plt.xlabel("Separación A vs B fuera de año")
    plt.title("Combinaciones causales MATRIX + MBO — discovery")
    plt.legend()
    plt.tight_layout()
    path = output / "matrix_mbo_combination_effectiveness.png"
    plt.savefig(path, dpi=170)
    plt.close()
    return str(path)


def _label_text(metrics: pd.DataFrame, capability: dict[str, float | int]) -> str:
    lines = [
        "ETIQUETA MATRIX+MBO | combinaciones mas efectivas",
        (
            f"MBO capability: B SIRVEN PARCIALMENTE | "
            f"censura izquierda {capability['left_censored_pct']:.2f}% | "
            f"snapshot {int(capability['snapshot_rows'])} | "
            f"eventos post-cutoff excluidos {int(capability['post_cutoff_rows_excluded'])}"
        ),
    ]
    for row in metrics.head(3).itertuples(index=False):
        lines.append(
            f"{row.feature_family}: n={row.n} | BA {row.balanced_accuracy:.3f} "
            f"[{row.balanced_accuracy_ci_low:.3f},{row.balanced_accuracy_ci_high:.3f}] | "
            f"AUC {row.roc_auc_A_vs_B:.3f} | sens A {row.sensitivity_A:.3f} | "
            f"esp B {row.specificity_B:.3f} | p_perm {row.permutation_p_within_year:.4f} | "
            f"min año/lado {row.minimum_year_side_balanced_accuracy:.3f} | {row.pilot_status}"
        )
    lines.append("Metricas LOYO discovery; no son WR ni PF y no sustituyen validacion sellada.")
    return "\n".join(lines)


def _annotate_feature_manifest(feature_manifest: pd.DataFrame) -> pd.DataFrame:
    feature_rows = feature_manifest.to_dict("records")
    feature_rows.extend(
        {
            "feature_family": "MBO_CORE",
            "feature": feature,
            "selection_rule": "frozen before pilot labels",
            "support": np.nan,
            "information_status": mbo.CORE_MBO_FEATURE_STATUS[feature][0],
            "limitation": mbo.CORE_MBO_FEATURE_STATUS[feature][1],
        }
        for feature in mbo.CORE_MBO_FEATURES
    )
    annotated = pd.DataFrame(feature_rows)
    annotated["information_status"] = annotated["information_status"].fillna(
        "EXPLICIT_DERIVED_MATRIX"
    )
    annotated["limitation"] = annotated["limitation"].fillna(
        "Observed only between t_burst and t_decision"
    )
    return annotated


def run_analysis(
    results_folder: Path | str,
    output_folder: Path | str,
    manifest_path: Path | str,
    mbo_dir: Path | str,
    mbp_ledger_path: Path | str,
) -> dict[str, object]:
    results = Path(results_folder)
    output = Path(output_folder)
    output.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(manifest_path)
    if len(manifest) != 100 or manifest["BurstId"].nunique() != 100:
        raise ValueError("The frozen pilot manifest must contain 100 unique BurstIds")
    if not manifest["split"].astype(str).eq("discovery").all():
        raise ValueError("Validation or holdout leaked into the discovery pilot")

    matrix_predictors, feature_manifest, causal_audit, coverage = _build_matrix_predictors(results, manifest)
    mbp_ledger = pd.read_csv(mbp_ledger_path, low_memory=False)
    mbo_ledger = mbo.extract_ledger(manifest, mbp_ledger, Path(mbo_dir))
    if not pd.to_numeric(mbo_ledger["mbo_causal_max_ok"], errors="coerce").eq(1).all():
        raise RuntimeError("At least one MBO file violates the causal cutoff")
    snapshot_rows = int(pd.to_numeric(mbo_ledger["mbo_snapshot_rows"], errors="coerce").fillna(0).sum())
    bad_book_rows = int(pd.to_numeric(mbo_ledger["mbo_bad_book_rows"], errors="coerce").fillna(0).sum())
    if snapshot_rows != 0:
        raise RuntimeError("MBO snapshot state changed; repeat capability audit before analysis")
    if bad_book_rows != 0:
        raise RuntimeError(f"MBO contains {bad_book_rows} F_MAYBE_BAD_BOOK rows")
    order_weights = pd.to_numeric(mbo_ledger["mbo_unique_order_ids"], errors="coerce").fillna(0)
    left_censored = pd.to_numeric(
        mbo_ledger["mbo_left_censored_order_share"], errors="coerce"
    ).fillna(0)
    capability = {
        "unique_orders": int(order_weights.sum()),
        "left_censored_pct": float(
            100.0 * (left_censored * order_weights).sum() / order_weights.sum()
        ),
        "snapshot_rows": snapshot_rows,
        "bad_book_rows": bad_book_rows,
        "ambiguous_cancel_fill_rows": int(
            pd.to_numeric(
                mbo_ledger["mbo_ambiguous_cancel_fill_rows"], errors="coerce"
            ).fillna(0).sum()
        ),
        "post_cutoff_rows_excluded": int(
            pd.to_numeric(
                mbo_ledger["mbo_post_cutoff_rows_excluded"], errors="coerce"
            ).fillna(0).sum()
        ),
    }
    joined = matrix_predictors.merge(
        mbo_ledger.drop(columns=["fecha", "split", "family"], errors="ignore"),
        on="BurstId",
        how="inner",
        validate="one_to_one",
    )
    joined = joined.rename(columns={"family_label_only": "family"})
    joined["year"] = pd.to_datetime(joined["fecha"]).dt.year.astype(int)
    joined["target"] = joined["family"].eq(FAMILY_A).astype(int)
    if len(joined) != 100:
        raise RuntimeError(f"Matrix/MBO join incomplete: {len(joined)}/100")
    clean = joined.loc[joined["family"].isin([FAMILY_A, FAMILY_B])].copy()
    if clean["year"].nunique() != 3 or len(clean) < 60:
        raise RuntimeError("Insufficient clean A/B discovery coverage for LOYO")

    feature_sets = _feature_sets(joined)
    metrics, predictions = _evaluate(clean, feature_sets)
    primary = metrics.loc[metrics["feature_family"].eq(PRIMARY_FAMILY)].iloc[0]
    pilot_promising = bool(primary["discovery_gate_passed"])
    plot_path = _plot_metrics(metrics, output)

    feature_manifest = _annotate_feature_manifest(feature_manifest)
    join_audit = pd.DataFrame(
        [
            {
                "manifest_rows": len(manifest),
                "matrix_predictor_rows": len(matrix_predictors),
                "mbo_ledger_rows": len(mbo_ledger),
                "joined_rows": len(joined),
                "clean_A_B_rows": len(clean),
                "family_A": int(joined["family"].eq(FAMILY_A).sum()),
                "family_B": int(joined["family"].eq(FAMILY_B).sum()),
                "family_C": int(joined["family"].eq(FAMILY_C).sum()),
                "post_cutoff_mbo_rows_excluded": int(
                    pd.to_numeric(mbo_ledger["mbo_post_cutoff_rows_excluded"], errors="coerce").fillna(0).sum()
                ),
                "mbo_causal_max_all_ok": int(
                    pd.to_numeric(mbo_ledger["mbo_causal_max_ok"], errors="coerce").eq(1).all()
                ),
                "sealed_validation_rows": 0,
                "sealed_holdout_rows": 0,
                "mbo_capability_verdict": MBO_CAPABILITY_VERDICT,
                "mbo_unique_orders": capability["unique_orders"],
                "mbo_left_censored_pct": capability["left_censored_pct"],
                "mbo_snapshot_rows": capability["snapshot_rows"],
                "mbo_bad_book_rows": capability["bad_book_rows"],
                "mbo_ambiguous_cancel_fill_rows": capability["ambiguous_cancel_fill_rows"],
            }
        ]
    )
    _write_csv(causal_audit, output / "matrix_postburst_causal_audit.csv")
    _write_csv(coverage, output / "matrix_coverage_audit.csv")
    _write_csv(join_audit, output / "matrix_mbo_join_audit.csv")
    _write_csv(feature_manifest, output / "frozen_feature_manifest.csv")
    _write_csv(mbo_ledger, output / "mbo_feature_ledger_100.csv")
    _write_csv(joined, output / "matrix_mbo_joined_dataset.csv")
    _write_csv(metrics, output / "matrix_mbo_combination_effectiveness.csv")
    _write_csv(predictions, output / "matrix_mbo_loyo_predictions.csv")

    label_text = _label_text(metrics, capability)
    (output / "telegram_matrix_mbo_label.txt").write_text(label_text + "\n", encoding="utf-8")
    report = [
        "# MATRIX + MBO CLASSIFICATION TEST — piloto discovery 100",
        "",
        f"Resultado primario: **{'PROMETEDORA_DISCOVERY' if pilot_promising else 'NO_SUPERA_PUERTA_DISCOVERY'}**.",
        "",
        "Veredicto de capacidad: **NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO**.",
        "",
        "La muestra no contiene validación ni holdout sellados. Incluso una señal discovery fuerte solo autoriza comprar/evaluar la siguiente etapa.",
        "",
        "## Capacidad de los datos MBO",
        "",
        f"- Veredicto previo: **{MBO_CAPABILITY_VERDICT}**.",
        f"- IDs de orden observados: {capability['unique_orders']:,}.",
        f"- Censura izquierda: {capability['left_censored_pct']:.2f}%.",
        f"- Snapshot inicial: {int(capability['snapshot_rows'])} registros.",
        f"- `F_MAYBE_BAD_BOOK`: {int(capability['bad_book_rows'])} registros.",
        f"- C/F con cantidad ambigua: {int(capability['ambiguous_cancel_fill_rows'])} eventos C.",
        f"- Eventos posteriores al timestamp nominal excluidos: {int(capability['post_cutoff_rows_excluded'])}.",
        "",
        "Los predictores MBO se interpretan según `frozen_feature_manifest.csv`: explícitos, inferidos o censurados. "
        "No se convierte una aproximación de cola, refill o cancel-replace en un hecho observado.",
        "",
        "## Combinaciones",
        "",
        "| combinación | n | BA LOYO | IC 95% | AUC | sensibilidad A | especificidad B | p permutación | mínimo año/lado | estado |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in metrics.itertuples(index=False):
        report.append(
            f"| {row.feature_family} | {row.n} | {row.balanced_accuracy:.3f} | "
            f"[{row.balanced_accuracy_ci_low:.3f}, {row.balanced_accuracy_ci_high:.3f}] | "
            f"{row.roc_auc_A_vs_B:.3f} | {row.sensitivity_A:.3f} | {row.specificity_B:.3f} | "
            f"{row.permutation_p_within_year:.4f} | {row.minimum_year_side_balanced_accuracy:.3f} | "
            f"{row.pilot_status} |"
        )
    report.extend(
        [
            "",
            "## Interpretación congelada",
            "",
            "Las métricas son predicciones fuera de año 2022/2023/2024. C no participa en el ajuste A/B. "
            "No se utilizaron MAE, MFE, TP, SL, resultado ni eventos posteriores a t_decision como predictores.",
            "",
            "El MBO carece de snapshot inicial en estas ventanas; por ello no se afirma posición inicial de cola. "
            "Las features de ciclo de vida se apoyan en órdenes cuya alta es observable dentro de la ventana.",
            "",
            "## Qué falta para afirmar capacidad",
            "",
            "- Validación temporal sellada que no haya intervenido en selección.",
            "- Snapshot inicial MBO para cola/estado completo, o limitar la afirmación a ciclos nacidos dentro de ventana.",
            "- Sincronización de DOM/tape y MBO desde un reloj/feed común si se pretende usar precedencia submilisegundo cruzada.",
        ]
    )
    report_path = output / "final_matrix_mbo_discovery_report.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    if pilot_promising:
        final_telegram_verdict = (
            f"{FINAL_NO}\n"
            "POR QUE: discovery es prometedor, pero no existe validacion temporal sellada y el "
            "MBO auditado tiene capacidad B parcial.\n"
            "ME FALTA: confirmar la separacion fuera de muestra; estado/cola inicial completos; "
            "y reloj comun MBO-DOM-tape para precedencia cruzada submilisegundo.\n"
            "NEXT STEPS: construir la muestra adicional hasta 04/04/2022 excluyendo feriados "
            "CME/EE. UU. y sesiones sin actividad NQ; descargar solo sus ventanas necesarias; "
            "ejecutar una unica validacion sellada. Solo si esa validacion pasa se podra enviar: "
            "SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO."
        )
    else:
        final_telegram_verdict = (
            f"{FINAL_NO}\n"
            "POR QUE: ninguna de las 7 combinaciones supero la puerta discovery. MBO_CORE quedo "
            "por debajo de azar y agregar MBO redujo BA y AUC frente a cada bloque MATRIX comparable.\n"
            "ME FALTA: una representacion causal pre-decision que sea estable por año y BUY/SELL. "
            "Los 12 predictores MBO actuales no aportan esa separacion.\n"
            "NEXT STEPS: NO descargar nuevas fechas MBO hasta 04/04/2022 porque la condicion "
            "prometedora no se cumplio. Cerrar esta representacion MBO; conservar los datos; "
            "solo reabrir MBO con snapshot/estado inicial completo y un nuevo piloto pequeño "
            "pre-registrado antes de comprar una muestra amplia."
        )

    manifest_out = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_pass": True,
        "discovery_only": True,
        "sealed_validation_rows": 0,
        "sealed_holdout_rows": 0,
        "rows": len(joined),
        "clean_A_B": len(clean),
        "primary_feature_family": PRIMARY_FAMILY,
        "primary_discovery_gate_passed": pilot_promising,
        "pilot_status": "PROMETEDORA_DISCOVERY" if pilot_promising else "NO_SUPERA_PUERTA_DISCOVERY",
        "mbo_data_capability": MBO_CAPABILITY_VERDICT,
        "mbo_capability_summary": capability,
        "capability_verdict": "NO_CAPABLE_WITHOUT_SEALED_VALIDATION",
        "conditional_mbo_download_triggered": pilot_promising,
        "final_telegram_verdict": final_telegram_verdict,
        "telegram_label": label_text,
        "visuals": [plot_path],
        "report": str(report_path),
        "output_folder": str(output),
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest_out, indent=2) + "\n", encoding="utf-8")
    return manifest_out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_folder", type=Path)
    parser.add_argument("output_folder", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("mbo_dir", type=Path)
    parser.add_argument("mbp_ledger", type=Path)
    args = parser.parse_args()
    result = run_analysis(
        args.results_folder,
        args.output_folder,
        args.manifest,
        args.mbo_dir,
        args.mbp_ledger,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
