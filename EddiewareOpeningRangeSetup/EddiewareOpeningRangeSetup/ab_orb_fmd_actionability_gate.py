"""Run the preregistered early-actionability gate for A/B ORB NQ.

This gate does not train a classifier and does not use MBO predictors.  It asks
whether the already-defined terminal A/B families diverge during the first
post-decision second.  The purpose is to stop the program before further MBO
research when the target is not actionable early enough.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm


SEED = 20260724
N_BOOT = 10_000
N_PERM = 10_000
MDE_TICKS = 2.0
UTILITY_TICKS = 1.0
ALPHA = 0.05
POWER_TARGET = 0.80

FAMILY_A = "A_TRUE_ABSORPTION"
FAMILY_B = "B_CLEAN_BREAKOUT"
FAMILY_C = "C_MIXED_PATH"
PRIMARY_ENDPOINT = "Directional_Displacement_Ticks"
EXPECTED_PREREG_HASH = (
    "7820b1ac1f0115328b93572078e70cf92a14ebb155b9fce77adfb91fcad35311"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _effect(frame: pd.DataFrame, values: np.ndarray | None = None) -> float:
    observed = (
        pd.to_numeric(frame[PRIMARY_ENDPOINT], errors="coerce").to_numpy()
        if values is None
        else np.asarray(values, dtype=float)
    )
    labels = frame["family"].astype(str).to_numpy()
    a = observed[labels == FAMILY_A]
    b = observed[labels == FAMILY_B]
    if not len(a) or not len(b):
        return math.nan
    return float(np.mean(b) - np.mean(a))


def cluster_bootstrap(
    frame: pd.DataFrame,
    *,
    n_boot: int = N_BOOT,
    seed: int = SEED,
) -> np.ndarray:
    """Resample date blocks; one row/date today, future-safe for repeated events."""
    rng = np.random.default_rng(seed)
    blocks = [
        group.reset_index(drop=True)
        for _, group in frame.groupby("fecha", sort=True, dropna=False)
    ]
    if not blocks:
        return np.array([], dtype=float)
    results: list[float] = []
    for _ in range(n_boot):
        indexes = rng.integers(0, len(blocks), len(blocks))
        sampled = pd.concat([blocks[index] for index in indexes], ignore_index=True)
        value = _effect(sampled)
        if math.isfinite(value):
            results.append(value)
    return np.asarray(results, dtype=float)


def stratified_permutation(
    frame: pd.DataFrame,
    *,
    n_perm: int = N_PERM,
    seed: int = SEED + 1,
) -> np.ndarray:
    """Permute A/B labels only within year and burst side."""
    rng = np.random.default_rng(seed)
    labels = frame["family"].astype(str).to_numpy()
    values = pd.to_numeric(
        frame[PRIMARY_ENDPOINT], errors="coerce"
    ).to_numpy(dtype=float)
    groups = [
        np.asarray(indexes, dtype=int)
        for indexes in frame.groupby(
            ["year", "burst_side"], sort=True, dropna=False
        ).indices.values()
    ]
    output = np.empty(n_perm, dtype=float)
    for iteration in range(n_perm):
        shuffled = labels.copy()
        for indexes in groups:
            shuffled[indexes] = rng.permutation(shuffled[indexes])
        a = values[shuffled == FAMILY_A]
        b = values[shuffled == FAMILY_B]
        output[iteration] = (
            float(np.mean(b) - np.mean(a)) if len(a) and len(b) else math.nan
        )
    return output[np.isfinite(output)]


def power_normal(delta: float, standard_error: float) -> float:
    if not math.isfinite(standard_error) or standard_error <= 0:
        return 1.0 if delta > 0 else 0.0
    z = norm.ppf(1 - ALPHA / 2)
    signal = delta / standard_error
    return float(1 - norm.cdf(z - signal) + norm.cdf(-z - signal))


def classify_gate(
    effect: float,
    ci_low: float,
    ci_high: float,
    p_two_sided: float,
    power_at_mde: float,
) -> str:
    if (
        effect > 0
        and ci_low > UTILITY_TICKS
        and p_two_sided <= ALPHA
    ):
        return "PASS"
    if ci_high < 0:
        return "REFUTACION"
    if ci_low <= 0 <= ci_high:
        return (
            "NO_CONCLUYENTE"
            if power_at_mde < POWER_TARGET
            else "REFUTACION"
        )
    return "SENAL_SUBUMBRAL"


def load_gate_dataset(
    manifest_path: Path,
    response_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = pd.read_csv(manifest_path, low_memory=False)
    responses = pd.read_csv(response_path, low_memory=False)

    required_manifest = {
        "BurstId",
        "fecha",
        "year",
        "family_label_only",
        "burst_side",
        "strategy_decision_timestamp_utc",
    }
    required_response = {
        "BurstId",
        "Burst_Feature_Available_Timestamp_UTC",
        "Response_Available_Timestamp_UTC",
        "Response_Horizon_Seconds",
        "Directional_Displacement_Ticks",
        "Model_Eligibility",
    }
    missing_manifest = sorted(required_manifest - set(manifest.columns))
    missing_response = sorted(required_response - set(responses.columns))
    if missing_manifest or missing_response:
        raise RuntimeError(
            f"Missing columns manifest={missing_manifest}, response={missing_response}"
        )
    if manifest["BurstId"].duplicated().any():
        raise RuntimeError("Manifest contains duplicate BurstId")

    one_second_raw = responses.loc[
        pd.to_numeric(
            responses["Response_Horizon_Seconds"], errors="coerce"
        ).eq(1)
    ].copy()
    exact_duplicate_rows_removed = int(one_second_raw.duplicated().sum())
    one_second = one_second_raw.drop_duplicates().copy()
    if one_second["BurstId"].duplicated().any():
        duplicate_ids = sorted(
            one_second.loc[
                one_second["BurstId"].duplicated(keep=False), "BurstId"
            ]
            .astype(str)
            .unique()
            .tolist()
        )
        raise RuntimeError(
            "One-second response contains non-identical duplicate BurstId: "
            + ", ".join(duplicate_ids)
        )

    columns = [
        "BurstId",
        "Burst_Feature_Available_Timestamp_UTC",
        "Response_Available_Timestamp_UTC",
        "Response_Horizon_Seconds",
        "Directional_Displacement_Ticks",
        "Response_MFE_Ticks",
        "Response_MAE_Ticks",
        "Acceptance_Dwell_Ratio",
        "Level_Band_Dwell_Ratio",
        "Rejected_Side_Dwell_Ratio",
        "Reclaim_Count",
        "Momentum_Survival_Ratio",
        "Path_Efficiency",
        "Model_Eligibility",
    ]
    columns = [column for column in columns if column in one_second.columns]
    joined = manifest[
        [
            "BurstId",
            "fecha",
            "year",
            "family_label_only",
            "burst_side",
            "strategy_decision_timestamp_utc",
        ]
    ].merge(
        one_second[columns],
        on="BurstId",
        how="left",
        validate="one_to_one",
    )
    joined = joined.rename(columns={"family_label_only": "family"})

    joined["decision_utc"] = pd.to_datetime(
        joined["strategy_decision_timestamp_utc"],
        utc=True,
        errors="coerce",
        format="mixed",
    )
    joined["feature_available_utc"] = pd.to_datetime(
        joined["Burst_Feature_Available_Timestamp_UTC"],
        utc=True,
        errors="coerce",
        format="mixed",
    )
    joined["response_available_utc"] = pd.to_datetime(
        joined["Response_Available_Timestamp_UTC"],
        utc=True,
        errors="coerce",
        format="mixed",
    )
    joined["response_after_decision_ms"] = (
        joined["response_available_utc"] - joined["decision_utc"]
    ).dt.total_seconds() * 1000
    joined["response_window_ms"] = (
        joined["response_available_utc"] - joined["feature_available_utc"]
    ).dt.total_seconds() * 1000
    joined[PRIMARY_ENDPOINT] = pd.to_numeric(
        joined[PRIMARY_ENDPOINT], errors="coerce"
    )

    coverage = {
        "manifest_rows": int(len(manifest)),
        "response_h1_rows_raw": int(len(one_second_raw)),
        "response_h1_rows": int(len(one_second)),
        "exact_duplicate_rows_removed": exact_duplicate_rows_removed,
        "joined_rows": int(len(joined)),
        "missing_response": int(joined[PRIMARY_ENDPOINT].isna().sum()),
        "duplicate_dates": int(joined["fecha"].duplicated().sum()),
        "response_not_after_decision": int(
            joined["response_after_decision_ms"].le(0).sum()
        ),
        "response_window_outside_800_1200ms": int(
            (~joined["response_window_ms"].between(800, 1200)).sum()
        ),
        "not_post_burst_only": int(
            (
                ~joined["Model_Eligibility"]
                .astype(str)
                .eq("POST_BURST_ONLY")
            ).sum()
        ),
        "family_counts": joined["family"].value_counts(dropna=False).to_dict(),
    }
    integrity_pass = (
        coverage["manifest_rows"] == 100
        and coverage["joined_rows"] == 100
        and coverage["missing_response"] == 0
        and coverage["duplicate_dates"] == 0
        and coverage["response_not_after_decision"] == 0
        and coverage["response_window_outside_800_1200ms"] == 0
        and coverage["not_post_burst_only"] == 0
    )
    coverage["integrity_pass"] = bool(integrity_pass)
    return joined, coverage


def secondary_diagnostics(clean: pd.DataFrame) -> pd.DataFrame:
    candidates = [
        "Response_MFE_Ticks",
        "Response_MAE_Ticks",
        "Acceptance_Dwell_Ratio",
        "Level_Band_Dwell_Ratio",
        "Rejected_Side_Dwell_Ratio",
        "Reclaim_Count",
        "Momentum_Survival_Ratio",
        "Path_Efficiency",
    ]
    rows: list[dict[str, Any]] = []
    for column in candidates:
        if column not in clean.columns:
            continue
        values = pd.to_numeric(clean[column], errors="coerce")
        a = values.loc[clean["family"].eq(FAMILY_A)].dropna()
        b = values.loc[clean["family"].eq(FAMILY_B)].dropna()
        rows.append(
            {
                "metric": column,
                "n_A": int(len(a)),
                "n_B": int(len(b)),
                "mean_A": float(a.mean()) if len(a) else math.nan,
                "mean_B": float(b.mean()) if len(b) else math.nan,
                "difference_B_minus_A": (
                    float(b.mean() - a.mean()) if len(a) and len(b) else math.nan
                ),
                "status": "EXPLORATORY_NOT_GATE",
            }
        )
    return pd.DataFrame(rows)


def make_plot(
    clean: pd.DataFrame,
    bootstrap: np.ndarray,
    effect: float,
    ci_low: float,
    ci_high: float,
    gate: str,
    output_path: Path,
) -> None:
    a = pd.to_numeric(
        clean.loc[clean["family"].eq(FAMILY_A), PRIMARY_ENDPOINT],
        errors="coerce",
    ).dropna()
    b = pd.to_numeric(
        clean.loc[clean["family"].eq(FAMILY_B), PRIMARY_ENDPOINT],
        errors="coerce",
    ).dropna()
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    axes[0].boxplot(
        [a.to_numpy(), b.to_numpy()],
        labels=["A: reversión limpia", "B: continuación limpia"],
        patch_artist=True,
        boxprops={"facecolor": "#d9eaf7"},
        medianprops={"color": "#0f766e", "linewidth": 2},
    )
    axes[0].axhline(0, color="#475569", linewidth=1, linestyle="--")
    axes[0].set_ylabel("Desplazamiento direccional, ticks")
    axes[0].set_title("Primer segundo posterior a decisión")

    axes[1].hist(bootstrap, bins=40, color="#2563eb", alpha=0.75)
    axes[1].axvline(0, color="#475569", linewidth=1, linestyle="--")
    axes[1].axvline(UTILITY_TICKS, color="#dc2626", linewidth=1.5, linestyle=":")
    axes[1].axvline(effect, color="#0f766e", linewidth=2)
    axes[1].set_xlabel("Diferencia B − A, ticks")
    axes[1].set_title(
        f"Gate {gate}: {effect:+.2f} [{ci_low:+.2f}, {ci_high:+.2f}]"
    )
    figure.suptitle("Gate Cero de accionabilidad A/B — sin predictores MBO")
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def run(
    manifest_path: Path,
    response_path: Path,
    prereg_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    actual_hash = file_sha256(prereg_path)
    if actual_hash != EXPECTED_PREREG_HASH:
        raise RuntimeError(
            f"Preregister hash mismatch: {actual_hash} != {EXPECTED_PREREG_HASH}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    joined, coverage = load_gate_dataset(manifest_path, response_path)
    joined.to_csv(output_dir / "actionability_gate_dataset.csv", index=False)
    if not coverage["integrity_pass"]:
        result = {
            "gate": "INTEGRIDAD_FAIL",
            "coverage": coverage,
            "preregister_sha256": actual_hash,
        }
        (output_dir / "actionability_gate_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    clean = joined.loc[
        joined["family"].isin([FAMILY_A, FAMILY_B])
    ].copy().reset_index(drop=True)
    effect = _effect(clean)
    bootstrap = cluster_bootstrap(clean)
    if len(bootstrap) < int(N_BOOT * 0.99):
        raise RuntimeError("Too many invalid bootstrap replicates")
    ci_low, ci_high = np.percentile(bootstrap, [2.5, 97.5])
    standard_error = float(np.std(bootstrap, ddof=1))
    power_at_mde = power_normal(MDE_TICKS, standard_error)

    permutation = stratified_permutation(clean)
    if len(permutation) != N_PERM:
        raise RuntimeError("Invalid permutation count")
    p_two_sided = float(
        (1 + np.sum(np.abs(permutation) >= abs(effect))) / (len(permutation) + 1)
    )
    p_one_sided = float(
        (1 + np.sum(permutation >= effect)) / (len(permutation) + 1)
    )
    gate = classify_gate(
        effect,
        float(ci_low),
        float(ci_high),
        p_two_sided,
        power_at_mde,
    )

    a = clean.loc[clean["family"].eq(FAMILY_A), PRIMARY_ENDPOINT]
    b = clean.loc[clean["family"].eq(FAMILY_B), PRIMARY_ENDPOINT]
    result = {
        "gate": gate,
        "primary_endpoint": PRIMARY_ENDPOINT,
        "effect_definition": "mean_B_minus_mean_A",
        "effect_ticks": effect,
        "ci95_low_ticks": float(ci_low),
        "ci95_high_ticks": float(ci_high),
        "bootstrap_standard_error_ticks": standard_error,
        "permutation_p_two_sided": p_two_sided,
        "permutation_p_directional": p_one_sided,
        "power_at_mde_2_ticks": power_at_mde,
        "mde_ticks": MDE_TICKS,
        "utility_threshold_ticks": UTILITY_TICKS,
        "n_clean": int(len(clean)),
        "n_A": int(clean["family"].eq(FAMILY_A).sum()),
        "n_B": int(clean["family"].eq(FAMILY_B).sum()),
        "mean_A_ticks": float(pd.to_numeric(a, errors="coerce").mean()),
        "mean_B_ticks": float(pd.to_numeric(b, errors="coerce").mean()),
        "median_A_ticks": float(pd.to_numeric(a, errors="coerce").median()),
        "median_B_ticks": float(pd.to_numeric(b, errors="coerce").median()),
        "coverage": coverage,
        "preregister_sha256": actual_hash,
        "mbo_predictors_used": 0,
        "terminal_mfe_mae_tp_sl_pnl_used_in_endpoint": False,
        "response_used_as_predictor": False,
        "known_discovery_status": (
            "RETROSPECTIVE_REGISTERED_ANALYSIS_NOT_PROSPECTIVE_CONFIRMATION"
        ),
    }
    pd.DataFrame({"bootstrap_effect_B_minus_A_ticks": bootstrap}).to_csv(
        output_dir / "actionability_gate_bootstrap.csv", index=False
    )
    pd.DataFrame({"permuted_effect_B_minus_A_ticks": permutation}).to_csv(
        output_dir / "actionability_gate_permutation.csv", index=False
    )
    secondary = secondary_diagnostics(clean)
    secondary.to_csv(
        output_dir / "actionability_gate_secondary_exploratory.csv", index=False
    )
    (output_dir / "actionability_gate_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    make_plot(
        clean,
        bootstrap,
        effect,
        float(ci_low),
        float(ci_high),
        gate,
        output_dir / "actionability_gate.png",
    )

    action = {
        "PASS": "Pasar a ingeniería MBO sin etiquetas sobre las seis sesiones técnicas.",
        "NO_CONCLUYENTE": "No avanzar a MBO; dimensionar una muestra no selectiva.",
        "REFUTACION": "Detener esta taxonomía para una entrada temprana.",
        "SENAL_SUBUMBRAL": "No avanzar a MBO; confirmar primero en muestra no selectiva.",
    }[gate]
    report_lines = [
        "# GATE CERO DE ACCIONABILIDAD A/B",
        "",
        f"**Veredicto: {gate}**",
        "",
        "## Integridad",
        "",
        f"- Sesiones unidas: {coverage['joined_rows']}/100.",
        f"- Respuestas faltantes: {coverage['missing_response']}.",
        f"- Respuestas no posteriores a decisión: {coverage['response_not_after_decision']}.",
        f"- Ventanas fuera de 800–1200 ms: {coverage['response_window_outside_800_1200ms']}.",
        f"- A/B limpio: n={len(clean)}; A={len(a)}; B={len(b)}.",
        f"- SHA256 del diseño: `{actual_hash}`.",
        "",
        "## Endpoint primario",
        "",
        f"- Diferencia B−A: {effect:+.3f} ticks.",
        f"- IC95% bootstrap: [{ci_low:+.3f}, {ci_high:+.3f}].",
        f"- p permutación bilateral: {p_two_sided:.4f}.",
        f"- Potencia para MDE=2 ticks: {power_at_mde:.3f}.",
        f"- Media A: {float(a.mean()):+.3f}; media B: {float(b.mean()):+.3f}.",
        "",
        "## Decisión",
        "",
        action,
        "",
        "Las métricas secundarias son exploratorias y no modifican el Gate Cero.",
    ]
    (output_dir / "ACTIONABILITY_GATE_REPORT.md").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_RESOLVED_20260723.csv",
    )
    parser.add_argument(
        "--responses",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\trade_results_score\visual_tests"
            r"\04_run_replay_lb_matrix_mbo_pilot100_discovery_r1_runs"
            r"\observational\burst_response_events.csv"
        ),
    )
    parser.add_argument(
        "--preregister",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "PREREGISTRO_NUEVO_ENFOQUE_AB_FMD_V1_20260724.md",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "outputs" / "ab_fmd_actionability_gate_20260724_r1",
    )
    args = parser.parse_args()
    result = run(args.manifest, args.responses, args.preregister, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] != "INTEGRIDAD_FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
