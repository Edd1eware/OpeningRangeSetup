"""F5 discovery runner for the pre-LB precursor line.

This is the single authorised join between the frozen outcome-blind feature
matrix and the V3 discovery labels. It runs once, writes its verdict, and does
not open validation or holdout under any outcome.

Subcommands:

    calibrate  time the frozen pipeline on synthetic labels, opens nothing
    freeze     hash the F5 code and config before the run
    run        perform the single join and evaluate the frozen protocol
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time as wall_time
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from telegram_run_summary_after_sync import send_persistent_text  # noqa: E402
from src.pre_lb_f5_discovery import (  # noqa: E402
    BENJAMINI_HOCHBERG_Q_MAX,
    BOOTSTRAP_REPETITIONS,
    FOLDS,
    PERMUTATION_REPETITIONS,
    RESOLVED_CLASSES,
    ProcessFail,
    benjamini_hochberg,
    delta_from_predictions,
    encode_truth,
    model_feature_sets,
    out_of_fold_predictions,
    per_fold_deltas,
    permutation_test,
    primary_gates,
    resolved_class_presence,
    session_bootstrap,
    stack_folds,
)

CONFIG_PATH = ROOT / "config" / "pre_lb_precursor_f2_config.json"
MAIN_CONFIG_PATH = ROOT / "config" / "discovery_config.json"
MATRIX_DIR = ROOT / "artifacts" / "pre_lb_precursor_f3"
LABELS_PATH = (
    ROOT / "artifacts" / "regime_discovery_target_v3" / "regime_discovery_labels.parquet"
)
OUTPUT_FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "PRE_LB_PRECURSOR_F3_OUTPUT_FREEZE_MANIFEST.json"
)
F5_FREEZE_PATH = (
    ROOT / "config" / "preregistration" / "PRE_LB_PRECURSOR_F5_FREEZE_MANIFEST.json"
)
OUTPUT = ROOT / "artifacts" / "pre_lb_precursor_f5"

F5_FREEZE_FILES = (
    "src/pre_lb_f5_discovery.py",
    "run_pre_lb_precursor_f5.py",
    "tests/test_pre_lb_f5_discovery.py",
)

PRIMARY = {
    "name": "PRIMARY_M_ALL_W1_MINUS_M0_BASE",
    "baseline": "M0_BASE",
    "augmented": "M_ALL_W1",
    "support": "COMBINED_W1_SUPPORT",
}

# The last three were unblocked by the substitution amendment resolved before
# any label was opened: GEMINI_F5_MODEL_SET_AMENDMENT: APPROVE_A.
EXECUTABLE_SECONDARIES = (
    {
        "name": "M_DOM_W1_MINUS_M0_BASE_MATCHED_DOM_W1_SUPPORT",
        "baseline": "M0_BASE",
        "augmented": "M_DOM_W1",
        "support": "DOM_W1_SUPPORT",
    },
    {
        "name": "M_PRF_MINUS_M0_BASE_MATCHED_PROFILE_F11_SUPPORT",
        "baseline": "M0_BASE",
        "augmented": "M_PRF",
        "support": "PROFILE_F11_SUPPORT",
    },
    {
        "name": "B_PRICE_PLUS_PRF_MINUS_B_PRICE_MATCHED_PROFILE_F11_SUPPORT",
        "baseline": "B_PRICE",
        "augmented": "B_PRICE_PLUS_PRF",
        "support": "PROFILE_F11_SUPPORT",
    },
    {
        "name": "M_ALL_W5_MINUS_M_ALL_W1_MATCHED_COMBINED_W5_SUPPORT",
        "baseline": "M_ALL_W1",
        "augmented": "M_ALL_W5",
        "support": "COMBINED_W5_SUPPORT",
    },
    {
        "name": "M_ALL_W30_MINUS_M_ALL_W5_MATCHED_COMBINED_W30_SUPPORT",
        "baseline": "M_ALL_W5",
        "augmented": "M_ALL_W30",
        "support": "COMBINED_W30_SUPPORT",
    },
)

BLOCKED_SECONDARIES: tuple[str, ...] = ()

MODEL_SET_AMENDMENT = "GEMINI_F5_MODEL_SET_AMENDMENT: APPROVE_A"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_json(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def telegram(message: str, enabled: bool) -> bool:
    if not enabled:
        return False
    main_config = load_config(MAIN_CONFIG_PATH)
    return bool(
        send_persistent_text(main_config["telegram_results_folder"], message)
    )


class ProgressReporter:
    """Emit a Telegram update at every 5% of total work."""

    def __init__(self, total_units: int, enabled: bool) -> None:
        self.total = max(int(total_units), 1)
        self.enabled = enabled
        self.done = 0
        self.last_bucket = 0
        self.started = wall_time.perf_counter()

    def advance(self, units: int = 1, stage: str = "") -> None:
        self.done += int(units)
        percent = min(100.0, 100.0 * self.done / self.total)
        bucket = int(percent // 5)
        if bucket <= self.last_bucket:
            return
        self.last_bucket = bucket
        elapsed = wall_time.perf_counter() - self.started
        remaining = elapsed / max(percent, 1e-9) * (100.0 - percent)
        print(
            json.dumps(
                {
                    "percent": round(percent, 1),
                    "stage": stage,
                    "elapsed_s": round(elapsed, 1),
                    "eta_s": round(remaining, 1),
                }
            ),
            flush=True,
        )
        telegram(
            (
                f"VT PRE-LB | F5 {percent:.0f}%\n\n"
                f"Etapa: {stage}\n"
                f"Transcurrido: {elapsed / 60:.1f} min\n"
                f"ETA restante: {remaining / 60:.1f} min\n\n"
                "Sin veredicto hasta el final."
            ),
            self.enabled,
        )


def verify_output_freeze() -> dict:
    """Confirm the frozen F3 artifacts are byte-identical to the joint PASS."""

    if not OUTPUT_FREEZE_PATH.is_file():
        raise RuntimeError("F3 output freeze manifest missing")
    manifest = json.loads(OUTPUT_FREEZE_PATH.read_text(encoding="utf-8"))
    for name, meta in manifest["files"].items():
        path = MATRIX_DIR / name
        if path.stat().st_size != meta["bytes"]:
            raise RuntimeError(f"frozen artifact size changed: {name}")
        if sha256_file(path) != meta["sha256"].upper():
            raise RuntimeError(f"frozen artifact hash changed: {name}")
    if manifest["joint_verdict"] != "F3_OUTPUT_AUDIT_JOINT_PASS":
        raise RuntimeError("F3 outputs lack the joint PASS")
    return manifest


def verify_f5_freeze() -> dict:
    if not F5_FREEZE_PATH.is_file():
        raise RuntimeError("F5 freeze manifest missing; run the freeze subcommand")
    manifest = json.loads(F5_FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, meta in manifest["files"].items():
        observed = sha256_file(ROOT / relative)
        if observed != meta["sha256"].upper():
            raise RuntimeError(f"F5 frozen file changed: {relative}")
    return manifest


def freeze_f5(gemini_verdict: str) -> dict:
    files = {}
    for relative in F5_FREEZE_FILES:
        path = ROOT / relative
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    payload = {
        "audit_id": "PRE_LB_PRECURSOR_F5_FREEZE_V1",
        "status": "BEFORE_SINGLE_DISCOVERY_JOIN",
        "f3_output_freeze_sha256": sha256_file(OUTPUT_FREEZE_PATH),
        "gemini_code_review": gemini_verdict,
        "model_set_amendment": MODEL_SET_AMENDMENT,
        "blocked_secondaries_pending_amendment": list(BLOCKED_SECONDARIES),
        "executable_secondaries": [item["name"] for item in EXECUTABLE_SECONDARIES],
        "files": files,
        "python": platform.python_version(),
    }
    write_json(F5_FREEZE_PATH, payload)
    return payload


def matched_sample(
    matrix: pd.DataFrame,
    support_column: str,
    feature_names: Sequence[str],
) -> pd.DataFrame:
    """Rows where the declared support holds and every used feature is finite."""

    rows = matrix[matrix[support_column].astype(bool)]
    used = rows.loc[:, list(feature_names)]
    complete = used.notna().all(axis=1)
    return rows[complete]


def evaluate_comparison(
    frame: pd.DataFrame,
    baseline_features: Sequence[str],
    augmented_features: Sequence[str],
    session_order: Sequence[str],
    with_permutation: bool,
    progress: ProgressReporter | None,
    stage: str,
) -> dict[str, object]:
    """Run one baseline vs augmented comparison end to end."""

    truth = encode_truth(frame["regime"].tolist())
    sessions = frame["session_date"].astype(str).to_numpy()
    event_ticks = frame["source_second_ticks"].to_numpy()
    baseline_matrix = frame.loc[:, list(baseline_features)].to_numpy(dtype=np.float64)
    augmented_matrix = frame.loc[:, list(augmented_features)].to_numpy(
        dtype=np.float64
    )

    presence = resolved_class_presence(truth, sessions, session_order)
    if presence["process_fail"]:
        return {"status": "PROCESS_FAIL", "presence": presence}

    baseline_folds = out_of_fold_predictions(
        baseline_matrix, truth, sessions, session_order
    )
    augmented_folds = out_of_fold_predictions(
        augmented_matrix, truth, sessions, session_order
    )
    delta = delta_from_predictions(baseline_folds, augmented_folds)
    fold_deltas = per_fold_deltas(baseline_folds, augmented_folds)
    if progress is not None:
        progress.advance(1, f"{stage}: folds")

    rows, baseline_probabilities, scored_truth = stack_folds(baseline_folds)
    _, augmented_probabilities, _ = stack_folds(augmented_folds)
    scored_sessions = sessions[rows]
    scored_direction = frame["direction"].to_numpy()[rows]

    bootstrap = session_bootstrap(
        baseline_probabilities,
        augmented_probabilities,
        scored_truth,
        scored_sessions,
    )
    if progress is not None:
        progress.advance(1, f"{stage}: bootstrap")

    side_deltas: dict[str, float | None] = {}
    for label, mask in (
        ("BUY", scored_direction > 0),
        ("SELL", scored_direction < 0),
    ):
        try:
            from src.pre_lb_f5_discovery import balanced_multiclass_log_loss

            side_deltas[label] = balanced_multiclass_log_loss(
                baseline_probabilities[mask], scored_truth[mask]
            ) - balanced_multiclass_log_loss(
                augmented_probabilities[mask], scored_truth[mask]
            )
        except ProcessFail:
            side_deltas[label] = None

    result: dict[str, object] = {
        "status": "OK",
        "rows": int(len(frame)),
        "scored_rows": int(rows.shape[0]),
        "sessions": int(len(set(sessions.tolist()))),
        "delta": float(delta),
        "fold_deltas": {int(k): float(v) for k, v in fold_deltas.items()},
        "bootstrap": bootstrap,
        "buy_delta": side_deltas["BUY"],
        "sell_delta": side_deltas["SELL"],
        "class_counts": {
            RESOLVED_CLASSES[index]: int((truth == index).sum())
            for index in range(len(RESOLVED_CLASSES))
        },
    }

    if with_permutation:
        step = max(PERMUTATION_REPETITIONS // 20, 1)

        def report(done: int, total: int) -> None:
            if progress is not None and done % step == 0:
                progress.advance(1, f"{stage}: permutacion {done}/{total}")

        result["permutation"] = permutation_test(
            baseline_matrix,
            augmented_matrix,
            truth,
            sessions,
            event_ticks,
            session_order,
            delta,
            progress=report,
        )
    return result


def load_joined_frame(matrix: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """Perform the single authorised join and drop the abstention class."""

    labels = pd.read_parquet(LABELS_PATH, columns=["lb_id", "regime"])
    joined = matrix.merge(labels, on="lb_id", how="inner", validate="one_to_one")
    resolved = joined[joined["regime"].isin(RESOLVED_CLASSES)].copy()
    audit = {
        "matrix_rows": int(len(matrix)),
        "label_rows": int(len(labels)),
        "joined_rows": int(len(joined)),
        "unmatched_matrix_rows": int(len(matrix) - len(joined)),
        "abstained_rows": int(len(joined) - len(resolved)),
        "resolved_rows": int(len(resolved)),
        "class_counts": {
            name: int((resolved["regime"] == name).sum()) for name in RESOLVED_CLASSES
        },
    }
    return resolved, audit


def run(telegram_enabled: bool) -> dict[str, object]:
    started = wall_time.perf_counter()
    output_freeze = verify_output_freeze()
    f5_freeze = verify_f5_freeze()
    config = load_config(CONFIG_PATH)
    families = config["feature_catalog"]
    sets = model_feature_sets(families)

    matrix = pd.read_parquet(MATRIX_DIR / "feature_matrix.parquet")
    # Fold positions come from the 104 eligible sessions of the frozen matrix,
    # never from the joined subset, so dropping abstained or unmatched rows can
    # never renumber a session into a different fold.
    session_order = sorted(matrix["session_date"].astype(str).unique().tolist())
    if len(session_order) != FOLDS[-1]["test"][1]:
        raise ProcessFail(
            f"expected {FOLDS[-1]['test'][1]} eligible sessions, "
            f"found {len(session_order)}"
        )
    resolved, join_audit = load_joined_frame(matrix)

    telegram(
        (
            "VT PRE-LB | F5 INICIO DEL UNICO JOIN\n\n"
            f"Filas matriz {join_audit['matrix_rows']}, "
            f"unidas {join_audit['joined_rows']}, "
            f"resueltas {join_audit['resolved_rows']}\n"
            f"Sesiones {len(session_order)}\n"
            f"Primary + {len(EXECUTABLE_SECONDARIES)} secundarios. "
            f"{MODEL_SET_AMENDMENT}"
        ),
        telegram_enabled,
    )

    # 1 folds + 1 bootstrap + 20 permutation ticks per comparison
    total_units = 22 * (1 + len(EXECUTABLE_SECONDARIES))
    progress = ProgressReporter(total_units, telegram_enabled)

    primary_frame = matched_sample(
        resolved,
        PRIMARY["support"],
        list(sets[PRIMARY["baseline"]]) + list(sets[PRIMARY["augmented"]]),
    )
    primary_result = evaluate_comparison(
        primary_frame,
        sets[PRIMARY["baseline"]],
        sets[PRIMARY["augmented"]],
        session_order,
        with_permutation=True,
        progress=progress,
        stage="primary",
    )

    secondary_results = []
    secondary_p_values = []
    for spec in EXECUTABLE_SECONDARIES:
        # Both sides of a comparison must be scorable on identical rows, so the
        # matched sample requires every feature of both models to be finite.
        frame = matched_sample(
            resolved,
            spec["support"],
            list(sets[spec["baseline"]]) + list(sets[spec["augmented"]]),
        )
        outcome = evaluate_comparison(
            frame,
            sets[spec["baseline"]],
            sets[spec["augmented"]],
            session_order,
            with_permutation=True,
            progress=progress,
            stage=spec["name"],
        )
        outcome["name"] = spec["name"]
        secondary_results.append(outcome)
        if outcome["status"] == "OK":
            secondary_p_values.append(outcome["permutation"]["p_value"])

    rejected = benjamini_hochberg(secondary_p_values)
    for outcome, flag in zip(
        [item for item in secondary_results if item["status"] == "OK"], rejected
    ):
        outcome["benjamini_hochberg_rejected"] = bool(flag)

    if primary_result["status"] != "OK":
        verdict = {
            "all_primary_gates_pass": False,
            "terminal_verdict": "PROCESS_FAIL",
            "gates": {},
        }
    else:
        verdict = primary_gates(
            primary_result["delta"],
            primary_result["bootstrap"],
            primary_result["permutation"],
            primary_result["fold_deltas"],
            primary_result["buy_delta"] if primary_result["buy_delta"] is not None else -1.0,
            primary_result["sell_delta"]
            if primary_result["sell_delta"] is not None
            else -1.0,
        )

    result = {
        "audit_id": "PRE_LB_PRECURSOR_F5_DISCOVERY_V1",
        "status": "F5_DISCOVERY_COMPLETE_PENDING_JOINT_REVIEW",
        "f3_output_freeze_sha256": sha256_file(OUTPUT_FREEZE_PATH),
        "f5_freeze_sha256": sha256_file(F5_FREEZE_PATH),
        "f3_joint_verdict": output_freeze["joint_verdict"],
        "gemini_code_review": f5_freeze.get("gemini_code_review"),
        "join_audit": join_audit,
        "sessions_used": len(session_order),
        "folds": [dict(item) for item in FOLDS],
        "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
        "permutation_repetitions": PERMUTATION_REPETITIONS,
        "benjamini_hochberg_q_max": BENJAMINI_HOCHBERG_Q_MAX,
        "model_set_amendment": MODEL_SET_AMENDMENT,
        "primary": primary_result,
        "secondaries": secondary_results,
        "blocked_secondaries_pending_amendment": list(BLOCKED_SECONDARIES),
        "verdict": verdict,
        "validation_opened": False,
        "holdout_opened": False,
        "parent_v3_status": "REGIME_V3_TARGET_DISCOVERY_FAIL",
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
            "VT PRE-LB | F5 COMPLETO\n\n"
            f"Delta primary {primary_result.get('delta')}\n"
            f"Veredicto {verdict['terminal_verdict']}\n\n"
            "Pendiente auditoria conjunta. No abre validation ni holdout."
        ),
        telegram_enabled,
    )
    return result


def calibrate(repetitions: int) -> dict[str, object]:
    """Time the frozen pipeline on synthetic labels. Opens no outcome."""

    verify_output_freeze()
    config = load_config(CONFIG_PATH)
    sets = model_feature_sets(config["feature_catalog"])
    matrix = pd.read_parquet(MATRIX_DIR / "feature_matrix.parquet")
    frame = matched_sample(matrix, PRIMARY["support"], sets[PRIMARY["augmented"]])
    sessions = frame["session_date"].astype(str).to_numpy()
    session_order = sorted(matrix["session_date"].astype(str).unique().tolist())
    generator = np.random.default_rng(0)
    synthetic = generator.integers(0, len(RESOLVED_CLASSES), size=len(frame))

    timings = []
    for _ in range(repetitions):
        start = wall_time.perf_counter()
        for name in (PRIMARY["baseline"], PRIMARY["augmented"]):
            out_of_fold_predictions(
                frame.loc[:, sets[name]].to_numpy(dtype=np.float64),
                synthetic,
                sessions,
                session_order,
            )
        timings.append(wall_time.perf_counter() - start)

    per_pair = float(np.median(timings))
    payload = {
        "matched_rows": int(len(frame)),
        "sessions": len(session_order),
        "seconds_per_model_pair": round(per_pair, 3),
        "estimated_primary_permutation_minutes": round(
            per_pair * PERMUTATION_REPETITIONS / 60.0, 1
        ),
        "estimated_total_minutes_three_comparisons": round(
            per_pair * PERMUTATION_REPETITIONS * 3 / 60.0, 1
        ),
        "labels_opened": False,
        "synthetic_labels_only": True,
    }
    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    # The preregistration fixes penalty="l2". scikit-learn 1.8 deprecates the
    # keyword in favour of l1_ratio while keeping identical behaviour, so the
    # explicit spelling is kept for fidelity and the notice is silenced.
    import warnings

    warnings.filterwarnings(
        "ignore",
        message="'penalty' was deprecated",
        category=FutureWarning,
    )
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    calibrate_parser = subparsers.add_parser("calibrate")
    calibrate_parser.add_argument("--repetitions", type=int, default=3)
    freeze_parser = subparsers.add_parser("freeze")
    freeze_parser.add_argument("--gemini-verdict", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--telegram", action="store_true")
    args = parser.parse_args()

    if args.command == "calibrate":
        calibrate(args.repetitions)
        return
    if args.command == "freeze":
        print(json.dumps(freeze_f5(args.gemini_verdict), indent=2))
        return
    print(json.dumps(run(telegram_enabled=args.telegram), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
