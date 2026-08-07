from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from run_post_lb_regime import (  # noqa: E402
    REGIME_CONFIG_PATH,
    build_labels,
    distribution_table,
    stability_and_gates,
    transition_table,
)
from src.vt_core import load_config  # noqa: E402


AUDIT_ID = "POST_LB_REGIME_TARGET_AUDIT_INTEGRITY_V3"
OUTPUT = ROOT / "artifacts" / "post_lb_regime_audit_integrity_v3"
FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_AUDIT_INTEGRITY_V3_FREEZE_MANIFEST.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    raise TypeError(type(value).__name__)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            allow_nan=False,
            default=json_default,
        ),
        encoding="utf-8",
    )


def freeze() -> dict[str, object]:
    files = (
        REGIME_CONFIG_PATH,
        ROOT
        / "config"
        / "preregistration"
        / "POST_LB_REGIME_PREREGISTRATION.md",
        ROOT
        / "config"
        / "preregistration"
        / "AMENDMENT_003_CURRENT_QUOTE_VALIDITY.md",
        ROOT
        / "config"
        / "preregistration"
        / "AMENDMENT_003_PRE_FIX_MANIFEST.json",
        ROOT
        / "config"
        / "preregistration"
        / "CLAUDE_CODEX_CONSENSUS_DATA_INTEGRITY.md",
        ROOT / "artifacts" / "quote_state_smoke_audit" / "manifest.json",
        ROOT / "artifacts" / "data_coverage" / "manifest.json",
        Path(__file__).resolve(),
        ROOT / "run_post_lb_regime.py",
        ROOT / "src" / "post_lb_regime.py",
        ROOT / "src" / "efficiency_audit.py",
        ROOT / "tests" / "test_post_lb_regime.py",
        ROOT / "tests" / "test_efficiency_audit.py",
    )
    manifest = {
        "audit_id": AUDIT_ID,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BEFORE_CORRECTED_SMOKE_LABELS",
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        },
        "threshold_selection_hierarchy_unchanged": [
            8,
            12,
            4,
            16,
        ],
        "non_smoke_labels_opened": False,
        "features_opened": False,
        "models_opened": False,
    }
    write_json(FREEZE_PATH, manifest)
    return manifest


def verify_freeze() -> dict[str, object]:
    if not FREEZE_PATH.is_file():
        raise RuntimeError("freeze corrected audit before running")
    manifest = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        observed = sha256_file(ROOT / relative)
        if observed != expected["sha256"]:
            raise RuntimeError(f"frozen file changed: {relative}")
    return manifest


def run() -> dict[str, object]:
    frozen = verify_freeze()
    config = load_config(REGIME_CONFIG_PATH)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    labels, sensitivity, audits = build_labels(config)
    distributions = distribution_table(labels)
    transitions = transition_table(labels)
    reference_table, stability_table, gate_result = stability_and_gates(
        labels,
        sensitivity,
        audits,
        config,
    )
    gate_table = gate_result.pop("gate_table")
    selected = gate_result["selected_threshold_ticks"]
    result = {
        "audit_id": AUDIT_ID,
        "status": (
            "TECHNICAL_REGIME_TARGET_CANDIDATE"
            if selected is not None
            else "REGIME_TARGET_INVALID"
        ),
        "liquidity_bursts": int(audits["liquidity_bursts"].sum()),
        "valid_reference_bursts": int(
            audits["valid_reference_bursts"].sum()
        ),
        "invalid_current_quote_bursts": int(
            audits["liquidity_bursts"].sum()
            - audits["valid_reference_bursts"].sum()
        ),
        "primary_reference": config["primary_reference"],
        "primary_horizon_ms": int(config["primary_horizon_ms"]),
        "ambiguity_window_ms": int(config["ambiguity_window_ms"]),
        **gate_result,
        "selection_did_not_use_model_metrics": True,
        "non_smoke_labels_opened": False,
        "features_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "freeze_sha256": sha256_file(FREEZE_PATH),
        "input_freeze_status": frozen["status"],
    }
    labels.to_parquet(OUTPUT / "regime_labels.parquet", index=False)
    sensitivity.to_parquet(
        OUTPUT / "regime_sensitivity.parquet",
        index=False,
    )
    audits.to_csv(OUTPUT / "data_audit.csv", index=False)
    distributions.to_csv(
        OUTPUT / "regime_distribution.csv",
        index=False,
    )
    transitions.to_csv(
        OUTPUT / "regime_transition_matrix.csv",
        index=False,
    )
    reference_table.to_csv(
        OUTPUT / "reference_agreement.csv",
        index=False,
    )
    stability_table.to_csv(
        OUTPUT / "stability_audit.csv",
        index=False,
    )
    gate_table.to_csv(
        OUTPUT / "outcome_threshold_audit.csv",
        index=False,
    )
    distributions[
        distributions["dimension"].eq("ALL")
    ].to_csv(
        OUTPUT / "outcome_horizon_audit.csv",
        index=False,
    )
    write_json(OUTPUT / "result.json", result)
    artifact_names = (
        "regime_labels.parquet",
        "regime_sensitivity.parquet",
        "data_audit.csv",
        "regime_distribution.csv",
        "regime_transition_matrix.csv",
        "reference_agreement.csv",
        "stability_audit.csv",
        "outcome_threshold_audit.csv",
        "outcome_horizon_audit.csv",
        "result.json",
    )
    write_json(
        OUTPUT / "manifest.json",
        {
            name: sha256_file(OUTPUT / name)
            for name in artifact_names
        },
    )
    print(json.dumps(result, indent=2, allow_nan=False), flush=True)
    print(gate_table.to_json(orient="records"), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "run"))
    arguments = parser.parse_args()
    if arguments.command == "freeze":
        print(json.dumps(freeze(), indent=2))
        return 0
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
