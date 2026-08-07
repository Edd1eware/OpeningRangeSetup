"""G1 runner: single evaluation of the binary expansion hypothesis.

Hypothesis 2 of the declared budget of 5 over the frozen F3 matrix. The join is
the same one F5 performed, with the resolved classes collapsed onto EXPANSION
versus NO_EXPANSION. Direction is discarded and cannot re-enter.

Subcommands:

    freeze  hash the G1 code and preregistration before the run
    run     perform the single evaluation and write the verdict
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time as wall_time
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from run_pre_lb_precursor_f5 import (  # noqa: E402
    LABELS_PATH,
    MATRIX_DIR,
    OUTPUT_FREEZE_PATH,
    ProgressReporter,
    load_config,
    matched_sample,
    sha256_file,
    telegram,
    verify_output_freeze,
    write_json,
    CONFIG_PATH,
    PRIMARY,
    EXECUTABLE_SECONDARIES,
)
from src.pre_lb_f5_discovery import (  # noqa: E402
    BENJAMINI_HOCHBERG_Q_MAX,
    BOOTSTRAP_REPETITIONS,
    BOOTSTRAP_SEED,
    FOLDS,
    PERMUTATION_REPETITIONS,
    PERMUTATION_SEED,
    ProcessFail,
    benjamini_hochberg,
    model_feature_sets,
    primary_gates,
    stack_folds,
)
from src.pre_lb_g1_expansion import (  # noqa: E402
    DIRECTIONAL_CLASSES,
    EXPANSION_CLASSES,
    balanced_binary_log_loss,
    binary_class_presence,
    binary_delta,
    binary_fold_deltas,
    binary_permutation_test,
    binary_session_bootstrap,
    collapse_to_expansion,
    expansion_base_rate,
    out_of_fold_binary,
)

PREREGISTRATION_PATH = (
    ROOT / "config" / "preregistration" / "PRE_LB_G1_EXPANSION_PREREGISTRATION.md"
)
G1_FREEZE_PATH = (
    ROOT / "config" / "preregistration" / "PRE_LB_G1_FREEZE_MANIFEST.json"
)
OUTPUT = ROOT / "artifacts" / "pre_lb_g1_expansion"

G1_FREEZE_FILES = (
    "src/pre_lb_g1_expansion.py",
    "run_pre_lb_g1_expansion.py",
    "tests/test_pre_lb_g1_expansion.py",
    "config/preregistration/PRE_LB_G1_EXPANSION_PREREGISTRATION.md",
)

HYPOTHESIS_NUMBER = 2
HYPOTHESIS_BUDGET = 5


def verify_g1_freeze() -> dict:
    if not G1_FREEZE_PATH.is_file():
        raise RuntimeError("G1 freeze manifest missing; run the freeze subcommand")
    manifest = json.loads(G1_FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, meta in manifest["files"].items():
        if sha256_file(ROOT / relative) != meta["sha256"].upper():
            raise RuntimeError(f"G1 frozen file changed: {relative}")
    return manifest


def freeze_g1(gemini_verdict: str) -> dict:
    payload = {
        "audit_id": "PRE_LB_G1_FREEZE_V1",
        "status": "BEFORE_SINGLE_G1_EVALUATION",
        "hypothesis_number": HYPOTHESIS_NUMBER,
        "hypothesis_budget": HYPOTHESIS_BUDGET,
        "f3_output_freeze_sha256": sha256_file(OUTPUT_FREEZE_PATH),
        "gemini_preregistration": "GEMINI_G1_PREREGISTRATION: PASS",
        "gemini_code_review": gemini_verdict,
        "target": "EXPANSION = CONTINUATION OR REVERSAL",
        "metric": "BALANCED_BINARY_LOG_LOSS",
        "files": {
            relative: {
                "bytes": (ROOT / relative).stat().st_size,
                "sha256": sha256_file(ROOT / relative),
            }
            for relative in G1_FREEZE_FILES
        },
        "python": platform.python_version(),
    }
    write_json(G1_FREEZE_PATH, payload)
    return payload


def load_expansion_frame(matrix: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Join the frozen labels once and collapse them onto the binary target."""

    labels = pd.read_parquet(LABELS_PATH, columns=["lb_id", "regime"])
    joined = matrix.merge(labels, on="lb_id", how="inner", validate="one_to_one")
    resolved = joined[
        joined["regime"].isin(list(DIRECTIONAL_CLASSES) + [EXPANSION_CLASSES[0]])
    ].copy()
    audit = {
        "matrix_rows": int(len(matrix)),
        "label_rows": int(len(labels)),
        "joined_rows": int(len(joined)),
        "unmatched_matrix_rows": int(len(matrix) - len(joined)),
        "abstained_rows": int(len(joined) - len(resolved)),
        "resolved_rows": int(len(resolved)),
        "expansion_rows": int(resolved["regime"].isin(DIRECTIONAL_CLASSES).sum()),
        "no_expansion_rows": int(
            (resolved["regime"] == EXPANSION_CLASSES[0]).sum()
        ),
    }
    audit["expansion_base_rate"] = audit["expansion_rows"] / max(
        audit["resolved_rows"], 1
    )
    return resolved, audit


def evaluate(
    frame: pd.DataFrame,
    baseline_features: Sequence[str],
    augmented_features: Sequence[str],
    session_order: Sequence[str],
    progress: ProgressReporter,
    stage: str,
) -> dict:
    truth = collapse_to_expansion(frame["regime"].tolist())
    sessions = frame["session_date"].astype(str).to_numpy()
    event_ticks = frame["source_second_ticks"].to_numpy()
    baseline_matrix = frame.loc[:, list(baseline_features)].to_numpy(dtype=np.float64)
    augmented_matrix = frame.loc[:, list(augmented_features)].to_numpy(
        dtype=np.float64
    )

    presence = binary_class_presence(truth, sessions, session_order)
    if presence["process_fail"]:
        return {"status": "PROCESS_FAIL", "presence": presence}

    baseline_folds = out_of_fold_binary(
        baseline_matrix, truth, sessions, session_order
    )
    augmented_folds = out_of_fold_binary(
        augmented_matrix, truth, sessions, session_order
    )
    delta = binary_delta(baseline_folds, augmented_folds)
    fold_deltas = binary_fold_deltas(baseline_folds, augmented_folds)
    progress.advance(1, f"{stage}: folds")

    rows, baseline_probabilities, scored_truth = stack_folds(baseline_folds)
    _, augmented_probabilities, _ = stack_folds(augmented_folds)
    scored_sessions = sessions[rows]
    scored_direction = frame["direction"].to_numpy()[rows]

    bootstrap = binary_session_bootstrap(
        baseline_probabilities,
        augmented_probabilities,
        scored_truth,
        scored_sessions,
        BOOTSTRAP_REPETITIONS,
        BOOTSTRAP_SEED,
    )
    progress.advance(1, f"{stage}: bootstrap")

    side_deltas: dict[str, float | None] = {}
    for label, mask in (
        ("BUY", scored_direction > 0),
        ("SELL", scored_direction < 0),
    ):
        try:
            side_deltas[label] = balanced_binary_log_loss(
                baseline_probabilities[mask], scored_truth[mask]
            ) - balanced_binary_log_loss(
                augmented_probabilities[mask], scored_truth[mask]
            )
        except ProcessFail:
            side_deltas[label] = None

    step = max(PERMUTATION_REPETITIONS // 20, 1)

    def report(done: int, total: int) -> None:
        if done % step == 0:
            progress.advance(1, f"{stage}: permutacion {done}/{total}")

    permutation = binary_permutation_test(
        baseline_matrix,
        augmented_matrix,
        truth,
        sessions,
        event_ticks,
        session_order,
        delta,
        PERMUTATION_REPETITIONS,
        PERMUTATION_SEED,
        progress=report,
    )

    return {
        "status": "OK",
        "rows": int(len(frame)),
        "scored_rows": int(rows.shape[0]),
        "sessions": int(len(set(sessions.tolist()))),
        "expansion_base_rate": expansion_base_rate(truth),
        "delta": float(delta),
        "fold_deltas": {int(k): float(v) for k, v in fold_deltas.items()},
        "bootstrap": bootstrap,
        "buy_delta": side_deltas["BUY"],
        "sell_delta": side_deltas["SELL"],
        "permutation": permutation,
    }


def run(telegram_enabled: bool) -> dict:
    started = wall_time.perf_counter()
    verify_output_freeze()
    g1_freeze = verify_g1_freeze()
    sets = model_feature_sets(load_config(CONFIG_PATH)["feature_catalog"])

    matrix = pd.read_parquet(MATRIX_DIR / "feature_matrix.parquet")
    session_order = sorted(matrix["session_date"].astype(str).unique().tolist())
    if len(session_order) != FOLDS[-1]["test"][1]:
        raise ProcessFail("eligible session count does not match the frozen folds")
    resolved, join_audit = load_expansion_frame(matrix)

    telegram(
        (
            "VT PRE-LB | G1 INICIO\n\n"
            f"Target binario EXPANSION. Base rate "
            f"{join_audit['expansion_base_rate']:.4f}\n"
            f"Resueltas {join_audit['resolved_rows']}, "
            f"sesiones {len(session_order)}\n"
            f"Hipotesis {HYPOTHESIS_NUMBER} de {HYPOTHESIS_BUDGET}"
        ),
        telegram_enabled,
    )

    progress = ProgressReporter(22 * (1 + len(EXECUTABLE_SECONDARIES)), telegram_enabled)

    primary_result = evaluate(
        matched_sample(
            resolved,
            PRIMARY["support"],
            list(sets[PRIMARY["baseline"]]) + list(sets[PRIMARY["augmented"]]),
        ),
        sets[PRIMARY["baseline"]],
        sets[PRIMARY["augmented"]],
        session_order,
        progress,
        "primary",
    )

    secondary_results = []
    for spec in EXECUTABLE_SECONDARIES:
        outcome = evaluate(
            matched_sample(
                resolved,
                spec["support"],
                list(sets[spec["baseline"]]) + list(sets[spec["augmented"]]),
            ),
            sets[spec["baseline"]],
            sets[spec["augmented"]],
            session_order,
            progress,
            spec["name"],
        )
        outcome["name"] = spec["name"]
        secondary_results.append(outcome)

    ok_secondaries = [item for item in secondary_results if item["status"] == "OK"]
    rejected = benjamini_hochberg(
        [item["permutation"]["p_value"] for item in ok_secondaries]
    )
    for outcome, flag in zip(ok_secondaries, rejected):
        outcome["benjamini_hochberg_rejected"] = bool(flag)

    if primary_result["status"] != "OK":
        verdict = {"terminal_verdict": "PROCESS_FAIL", "all_primary_gates_pass": False}
    else:
        gates = primary_gates(
            primary_result["delta"],
            primary_result["bootstrap"],
            primary_result["permutation"],
            primary_result["fold_deltas"],
            primary_result["buy_delta"]
            if primary_result["buy_delta"] is not None
            else -1.0,
            primary_result["sell_delta"]
            if primary_result["sell_delta"] is not None
            else -1.0,
        )
        gates["terminal_verdict"] = (
            "DISCOVERY_ONLY_SIGNAL_EXPANSION"
            if gates["all_primary_gates_pass"]
            else "NO_EXPANSION_SIGNAL_CLOSE_G1"
        )
        verdict = gates

    result = {
        "audit_id": "PRE_LB_G1_EXPANSION_V1",
        "status": "G1_COMPLETE_PENDING_JOINT_REVIEW",
        "hypothesis_number": HYPOTHESIS_NUMBER,
        "hypothesis_budget": HYPOTHESIS_BUDGET,
        "target": "EXPANSION = CONTINUATION OR REVERSAL",
        "metric": "BALANCED_BINARY_LOG_LOSS",
        "f3_output_freeze_sha256": sha256_file(OUTPUT_FREEZE_PATH),
        "g1_freeze_sha256": sha256_file(G1_FREEZE_PATH),
        "gemini_preregistration": g1_freeze.get("gemini_preregistration"),
        "gemini_code_review": g1_freeze.get("gemini_code_review"),
        "join_audit": join_audit,
        "sessions_used": len(session_order),
        "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
        "permutation_repetitions": PERMUTATION_REPETITIONS,
        "benjamini_hochberg_q_max": BENJAMINI_HOCHBERG_Q_MAX,
        "primary": primary_result,
        "secondaries": secondary_results,
        "verdict": verdict,
        "era_blind_replication_required_if_pass": True,
        "sample_era": "2022_DEPTH_PRESENT",
        "validation_opened": False,
        "holdout_opened": False,
        "parent_v3_status": "REGIME_V3_TARGET_DISCOVERY_FAIL",
        "f5_direction_status": "NO_DISCOVERY_SIGNAL_CLOSE_LINE",
        "runtime_seconds": round(wall_time.perf_counter() - started, 1),
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT / "result.json", result)
    write_json(
        OUTPUT / "manifest.json",
        {
            "result.json": {
                "bytes": (OUTPUT / "result.json").stat().st_size,
                "sha256": sha256_file(OUTPUT / "result.json"),
            }
        },
    )

    telegram(
        (
            "VT PRE-LB | G1 COMPLETO\n\n"
            f"Delta {primary_result.get('delta')}\n"
            f"Veredicto {verdict['terminal_verdict']}\n\n"
            "Un PASS no autoriza operar, solo replicacion era-blind."
        ),
        telegram_enabled,
    )
    return result


def main() -> None:
    import warnings

    warnings.filterwarnings(
        "ignore", message="'penalty' was deprecated", category=FutureWarning
    )
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser("freeze")
    freeze_parser.add_argument("--gemini-verdict", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--telegram", action="store_true")
    args = parser.parse_args()

    if args.command == "freeze":
        print(json.dumps(freeze_g1(args.gemini_verdict), indent=2))
        return
    print(json.dumps(run(telegram_enabled=args.telegram), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
