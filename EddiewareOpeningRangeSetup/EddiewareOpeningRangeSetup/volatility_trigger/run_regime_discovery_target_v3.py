from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from telegram_run_summary_after_sync import send_persistent_text  # noqa: E402
from run_research import CONFIG_PATH, stage_dates  # noqa: E402
from run_regime_discovery_target import (  # noqa: E402
    process_session,
    target_gates,
)
from src.vt_core import load_config  # noqa: E402


TARGET_CONFIG_PATH = ROOT / "config" / "post_lb_regime_v3_config.json"
TARGET_FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_V3_FREEZE_MANIFEST.json"
)
RUN_FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "REGIME_DISCOVERY_TARGET_V3_RUN_FREEZE_MANIFEST.json"
)
COVERAGE_PATH = (
    ROOT
    / "artifacts"
    / "data_coverage"
    / "depth_coverage_manifest.csv"
)
OUTPUT = ROOT / "artifacts" / "regime_discovery_target_v3"
TECHNICAL_DATES = {
    "2022-08-01",
    "2022-08-02",
    "2022-08-03",
    "2022-08-04",
    "2022-08-05",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            allow_nan=False,
            default=lambda item: (
                int(item)
                if isinstance(item, np.integer)
                else float(item)
                if isinstance(item, np.floating)
                and math.isfinite(float(item))
                else None
            ),
        ),
        encoding="utf-8",
    )


def telegram(message: str, enabled: bool) -> bool:
    if not enabled:
        return False
    config = load_config(CONFIG_PATH)
    return send_persistent_text(
        config["telegram_results_folder"],
        message,
    )


def freeze() -> dict[str, object]:
    files = (
        TARGET_CONFIG_PATH,
        TARGET_FREEZE_PATH,
        COVERAGE_PATH,
        ROOT / "artifacts" / "data_coverage" / "manifest.json",
        ROOT
        / "artifacts"
        / "resolved_threshold_audit_v3"
        / "manifest.json",
        ROOT
        / "artifacts"
        / "post_lb_regime_audit_integrity_v3"
        / "manifest.json",
        ROOT
        / "config"
        / "preregistration"
        / "CLAUDE_CODEX_CONSENSUS_DATA_INTEGRITY.md",
        ROOT
        / "config"
        / "preregistration"
        / "AMENDMENT_002_AMBIGUOUS_AS_ABSTENTION.md",
        ROOT
        / "config"
        / "preregistration"
        / "AMENDMENT_003_CURRENT_QUOTE_VALIDITY.md",
        ROOT
        / "config"
        / "preregistration"
        / "ERRATA_001_MISSING_REFERENCE_ARTIFACT.md",
        ROOT
        / "config"
        / "preregistration"
        / "ERRATA_SCOPE_A1_EQUIVALENCE.md",
        ROOT / "config" / "discovery_config.json",
        Path(__file__).resolve(),
        ROOT / "run_regime_discovery_target.py",
        ROOT / "run_research.py",
        REPO / "atas_cache_decoder.py",
        ROOT / "src" / "post_lb_regime.py",
        ROOT / "src" / "efficiency_audit.py",
        ROOT / "src" / "vt_core.py",
        ROOT / "tests" / "test_post_lb_regime.py",
        ROOT / "tests" / "test_efficiency_audit.py",
        ROOT / "tests" / "test_vt_core.py",
        ROOT / "tests" / "test_regime_discovery_v3.py",
    )
    target_config = load_config(TARGET_CONFIG_PATH)
    manifest = {
        "target_id": target_config["target_id"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BEFORE_V3_DISCOVERY_TARGET_LABELS",
        "files": {
            (
                "../atas_cache_decoder.py"
                if path == REPO / "atas_cache_decoder.py"
                else str(path.relative_to(ROOT)).replace("\\", "/")
            ): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        },
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "pyarrow": pyarrow.__version__,
        },
        "threshold_ticks": 16,
        "hierarchy_consumed": True,
        "process_gate_evaluated_over_eligible": 1.0,
        "v2_cache_reuse_forbidden": True,
        "output_directory": "artifacts/regime_discovery_target_v3",
        "features_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
    }
    write_json(RUN_FREEZE_PATH, manifest)
    return manifest


def verify_freeze() -> dict[str, object]:
    if not RUN_FREEZE_PATH.is_file():
        raise RuntimeError("freeze V3 discovery target run first")
    manifest = json.loads(RUN_FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = (
            REPO / "atas_cache_decoder.py"
            if relative == "../atas_cache_decoder.py"
            else ROOT / relative
        )
        observed = sha256_file(path)
        if observed != expected["sha256"]:
            raise RuntimeError(f"frozen file changed: {relative}")
    return manifest


def excluded_audit(
    coverage_row,
) -> dict[str, object]:
    return {
        "session_date": str(coverage_row.session_date),
        "liquidity_bursts": None,
        "valid_reference_bursts": None,
        "reference_coverage": None,
        "status": f"EXCLUDED_DEPTH_{coverage_row.depth_status}",
        "reason": (
            "Outcome-blind coverage manifest: "
            f"{coverage_row.depth_status}"
        ),
        "trade_header_status": str(coverage_row.trade_status),
        "depth_header_status": str(coverage_row.depth_status),
        "trade_source": str(coverage_row.trade_path),
        "depth_source": str(coverage_row.depth_path),
    }


def classify_exception(
    session_date: str,
    exc: Exception,
) -> dict[str, object]:
    reason = f"{type(exc).__name__}: {exc}"
    frozen_qc = (
        isinstance(exc, ValueError)
        and "timestamp QC failed" in str(exc)
    )
    return {
        "session_date": session_date,
        "liquidity_bursts": None,
        "valid_reference_bursts": None,
        "reference_coverage": None,
        "status": (
            "EXCLUDED_FROZEN_TRADE_QC"
            if frozen_qc
            else "PROCESS_ERROR"
        ),
        "reason": reason,
    }


def cache_guard(
    cache_dir: Path,
    run_freeze_sha256: str,
) -> None:
    marker = cache_dir / "RUN_FREEZE_SHA256.txt"
    existing = list(cache_dir.glob("*"))
    if existing:
        if not marker.is_file():
            raise RuntimeError("V3 cache exists without freeze marker")
        observed = marker.read_text(encoding="utf-8").strip()
        if observed != run_freeze_sha256:
            raise RuntimeError("V3 cache freeze marker mismatch")
    else:
        marker.write_text(
            f"{run_freeze_sha256}\n",
            encoding="utf-8",
        )


def process_metrics(
    audits: pd.DataFrame,
    coverage: pd.DataFrame,
) -> dict[str, object]:
    depth_present = coverage["depth_status"].eq("DATA_PRESENT")
    trade_present = coverage["trade_status"].eq("DATA_PRESENT")
    header_eligible = set(
        coverage.loc[
            depth_present & trade_present,
            "session_date",
        ].astype(str)
    )
    frozen_qc_dates = set(
        audits.loc[
            audits["status"].eq("EXCLUDED_FROZEN_TRADE_QC"),
            "session_date",
        ].astype(str)
    )
    eligible = header_eligible - frozen_qc_dates
    evaluated_dates = set(
        audits.loc[
            audits["status"].isin(["PASS", "NO_LB"]),
            "session_date",
        ].astype(str)
    )
    evaluated_eligible = evaluated_dates & eligible
    share = len(evaluated_eligible) / max(len(eligible), 1)
    process_errors = int(audits["status"].eq("PROCESS_ERROR").sum())
    return {
        "sessions_attempted": int(len(coverage)),
        "depth_present_sessions": int(depth_present.sum()),
        "depth_present_share_report_only": float(depth_present.mean()),
        "header_eligible_sessions": int(len(header_eligible)),
        "frozen_qc_excluded_sessions": int(len(frozen_qc_dates)),
        "eligible_after_frozen_qc_sessions": int(len(eligible)),
        "evaluated_eligible_sessions": int(len(evaluated_eligible)),
        "evaluated_share_eligible_after_frozen_qc": float(share),
        "process_error_sessions": process_errors,
        "process_coverage_pass": bool(
            math.isclose(share, 1.0)
            and process_errors == 0
        ),
    }


def run(telegram_enabled: bool) -> dict[str, object]:
    freeze_manifest = verify_freeze()
    main_config = load_config(CONFIG_PATH)
    target_config = load_config(TARGET_CONFIG_PATH)
    coverage = pd.read_csv(COVERAGE_PATH)
    dates = stage_dates("discovery", main_config)
    expected_dates = [value.isoformat() for value in dates]
    if coverage["session_date"].astype(str).tolist() != expected_dates:
        raise RuntimeError("coverage manifest date order mismatch")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    cache_dir = OUTPUT / "session_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    run_freeze_sha = sha256_file(RUN_FREEZE_PATH)
    cache_guard(cache_dir, run_freeze_sha)
    telegram(
        "POST-LB REGIME V3 | INICIO TARGET-ONLY\n"
        "16t/5s/MID actual valido/250ms; AMBIGUOUS=abstencion. "
        "195 fechas, 111 con depth. Sin features/modelos/AUC/PnL.",
        telegram_enabled,
    )

    parts: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    for ordinal, row in enumerate(
        coverage.itertuples(index=False),
        start=1,
    ):
        stem = str(row.session_date)
        label_path = cache_dir / f"{stem}_labels.parquet"
        audit_path = cache_dir / f"{stem}_audit.json"
        if audit_path.is_file():
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            part = (
                pd.read_parquet(label_path)
                if label_path.is_file()
                else pd.DataFrame()
            )
        elif row.depth_status != "DATA_PRESENT":
            part = pd.DataFrame()
            audit = excluded_audit(row)
            write_json(audit_path, audit)
        else:
            try:
                part, audit = process_session(
                    datetime.fromisoformat(stem).date(),
                    main_config,
                    target_config,
                )
                if not part.empty:
                    part.to_parquet(label_path, index=False)
            except Exception as exc:
                part = pd.DataFrame()
                audit = classify_exception(stem, exc)
            write_json(audit_path, audit)
        if not part.empty:
            parts.append(part)
        audits.append(audit)
        if ordinal % 20 == 0 or ordinal == len(coverage):
            labels_so_far = sum(len(value) for value in parts)
            print(
                json.dumps(
                    {
                        "processed": ordinal,
                        "total": len(coverage),
                        "evaluated_sessions": sum(
                            value["status"] in ("PASS", "NO_LB")
                            for value in audits
                        ),
                        "valid_lbs": labels_so_far,
                    }
                ),
                flush=True,
            )

    labels = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame()
    )
    audit_frame = pd.DataFrame(audits)
    distribution, target_metrics = target_gates(
        labels,
        audit_frame,
        target_config,
    )
    process = process_metrics(audit_frame, coverage)
    without_technical_labels = labels[
        ~labels["session_date"].isin(TECHNICAL_DATES)
    ]
    without_technical_audits = audit_frame[
        ~audit_frame["session_date"].isin(TECHNICAL_DATES)
    ]
    _, sensitivity_metrics = target_gates(
        without_technical_labels,
        without_technical_audits,
        target_config,
    )
    primary_pass = bool(
        target_metrics["pass"] and process["process_coverage_pass"]
    )
    result = {
        "target_id": target_config["target_id"],
        "status": (
            "REGIME_V3_TARGET_DISCOVERY_PASS"
            if primary_pass
            else "REGIME_V3_TARGET_DISCOVERY_FAIL"
        ),
        "threshold_ticks": 16,
        "horizon_ms": int(target_config["horizon_ms"]),
        "ambiguous_policy": target_config["ambiguous_policy"],
        **target_metrics,
        **process,
        "primary_pass": primary_pass,
        "technical_sensitivity_is_not_selection_or_rescue": True,
        "without_technical_dates_sensitivity": sensitivity_metrics,
        "hierarchy_consumed": True,
        "return_to_prior_thresholds_forbidden": True,
        "features_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "run_freeze_sha256": run_freeze_sha,
        "input_freeze_status": freeze_manifest["status"],
    }
    labels.to_parquet(
        OUTPUT / "regime_discovery_labels.parquet",
        index=False,
    )
    audit_frame.to_csv(OUTPUT / "data_audit.csv", index=False)
    distribution.to_csv(
        OUTPUT / "regime_distribution.csv",
        index=False,
    )
    write_json(OUTPUT / "result.json", result)
    artifact_names = (
        "regime_discovery_labels.parquet",
        "data_audit.csv",
        "regime_distribution.csv",
        "result.json",
    )
    write_json(
        OUTPUT / "manifest.json",
        {
            name: sha256_file(OUTPUT / name)
            for name in artifact_names
        },
    )
    telegram(
        (
            "POST-LB REGIME V3 | RESULTADO TARGET-ONLY\n"
            f"Estado: {result['status']}\n"
            f"LB validos: {result['valid_liquidity_bursts']}; "
            f"min clase: {result['minimum_resolved_class_count']}; "
            f"meses min: {result['minimum_months_each_resolved_class']}\n"
            f"TVD: {result['buy_sell_total_variation']:.3f}; "
            f"AMBIGUOUS: {result['ambiguous_share']:.3f}; "
            f"proceso: {result['evaluated_share_eligible_after_frozen_qc']:.3f}\n"
            "Jerarquia consumida. Features/modelos aun cerrados."
        ),
        telegram_enabled,
    )
    print(json.dumps(result, indent=2, allow_nan=False), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("freeze")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--telegram", action="store_true")
    arguments = parser.parse_args()
    if arguments.command == "freeze":
        print(json.dumps(freeze(), indent=2))
        return 0
    run(arguments.telegram)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
