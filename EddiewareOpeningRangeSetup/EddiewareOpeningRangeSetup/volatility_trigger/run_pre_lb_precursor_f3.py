from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time as wall_time
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import load_cache_window  # noqa: E402
from telegram_run_summary_after_sync import send_persistent_text  # noqa: E402
from src.efficiency_audit import causal_depth_timestamps  # noqa: E402
from src.pre_lb_features import (  # noqa: E402
    build_feature_matrix,
    catalog_features,
    validate_catalog,
)
from src.vt_core import (  # noqa: E402
    LiquidityBurst,
    causalize_trade_timestamps,
    datetime_to_dotnet_ticks,
    detect_liquidity_bursts,
    load_config,
    session_bounds as trade_session_bounds,
)


CONFIG_PATH = ROOT / "config" / "pre_lb_precursor_f2_config.json"
F0_CONFIG_PATH = ROOT / "config" / "pre_lb_precursor_f0_config.json"
MAIN_CONFIG_PATH = ROOT / "config" / "discovery_config.json"
COVERAGE_PATH = (
    ROOT / "artifacts" / "data_coverage" / "depth_coverage_manifest.csv"
)
PREREGISTRATION_MANIFEST_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "PRE_LB_PRECURSOR_F2_PREREGISTRATION_MANIFEST.json"
)
FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "PRE_LB_PRECURSOR_F3_FREEZE_MANIFEST.json"
)
OUTPUT = ROOT / "artifacts" / "pre_lb_precursor_f3"
CACHE = OUTPUT / "session_cache"
NY_ZONE = ZoneInfo("America/New_York")


FREEZE_FILES = (
    "config/pre_lb_precursor_f2_config.json",
    "config/pre_lb_precursor_f0_config.json",
    "config/discovery_config.json",
    "config/preregistration/PRE_LB_PRECURSOR_F2_PREREGISTRATION.md",
    "config/preregistration/PRE_LB_PRECURSOR_F2_PREREGISTRATION_MANIFEST.json",
    "config/preregistration/GEMINI_CODEX_PRE_LB_F2_SUPPORT_MASK_AMENDMENT.md",
    "config/preregistration/GEMINI_CODEX_PRE_LB_F3_IMPLEMENTATION_APPROVAL.md",
    "config/preregistration/GEMINI_CODEX_CONSENSUS_PRE_LB_F0_F1_FINAL.md",
    "config/preregistration/GEMINI_CODEX_CONSENSUS_PRE_LB_F0_F1_FINAL_APPROVAL.json",
    "config/preregistration/PRE_LB_PRECURSOR_F0_F1_FREEZE_MANIFEST.json",
    "artifacts/data_coverage/depth_coverage_manifest.csv",
    "artifacts/pre_lb_precursor_f0_f1/manifest.json",
    "src/pre_lb_features.py",
    "src/pre_lb_audit.py",
    "src/efficiency_audit.py",
    "src/vt_core.py",
    "run_pre_lb_precursor_f3.py",
    "../atas_cache_decoder.py",
    "tests/test_pre_lb_features.py",
    "tests/test_pre_lb_f3_runner.py",
)

SUPPORT_COLUMNS = (
    "BASELINE_SUPPORT",
    "DOM_STATE_SUPPORT",
    "DOM_W1_SUPPORT",
    "DOM_W5_SUPPORT",
    "DOM_W30_SUPPORT",
    "PROFILE_RAW_SUPPORT",
    "PROFILE_F11_SUPPORT",
    "COMBINED_W1_SUPPORT",
    "COMBINED_W5_SUPPORT",
    "COMBINED_W30_SUPPORT",
)
NON_PREDICTOR_METADATA = (
    *SUPPORT_COLUMNS,
    "LB_CLUSTER_ID_30S",
    "LB_CLUSTER_SIZE_30S",
)
CAUSAL_AUDIT_COLUMNS = (
    "MAX_PRECURSOR_TRADE_TICKS",
    "MAX_PRECURSOR_DEPTH_TICKS",
    "MAX_PROFILE_TRADE_TICKS",
)
IDENTITY_AND_EVENT_METADATA = (
    "lb_id",
    "session_date",
    "source_second_ticks",
    "publish_ticks",
    "side",
    "direction",
)


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
                if isinstance(item, np.floating)
                else str(item)
            ),
        ),
        encoding="utf-8",
    )


def _freeze_path(relative: str) -> Path:
    return (ROOT / relative).resolve()


def verify_preregistration() -> dict[str, object]:
    if not PREREGISTRATION_MANIFEST_PATH.is_file():
        raise FileNotFoundError(PREREGISTRATION_MANIFEST_PATH)
    manifest = json.loads(
        PREREGISTRATION_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    if (
        manifest.get("authorized_next_step")
        != "IMPLEMENT_AND_TEST_F3_OUTCOME_BLIND_EXTRACTOR"
    ):
        raise RuntimeError("F2 manifest does not authorize F3")
    for relative, expected in manifest["files"].items():
        path = _freeze_path(str(relative))
        if not path.is_file():
            raise RuntimeError(f"F2 preregistered file missing: {relative}")
        if path.stat().st_size != int(expected["bytes"]):
            raise RuntimeError(
                f"F2 preregistered file size changed: {relative}"
            )
        if sha256_file(path) != str(expected["sha256"]):
            raise RuntimeError(
                f"F2 preregistered file hash changed: {relative}"
            )
    config = load_config(CONFIG_PATH)
    observed = validate_catalog(config)
    catalog = manifest["catalog"]
    if (
        len(observed) != int(catalog["declared_features"])
        or len(observed) != int(catalog["observed_features"])
        or len(set(observed)) != int(catalog["unique_features"])
    ):
        raise RuntimeError("F2 catalog integrity mismatch")
    return manifest


def freeze() -> dict[str, object]:
    preregistration = verify_preregistration()
    files: dict[str, object] = {}
    for relative in FREEZE_FILES:
        path = _freeze_path(relative)
        if not path.is_file():
            raise FileNotFoundError(path)
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    manifest = {
        "audit_id": "PRE_LB_PRECURSOR_F3_OUTCOME_BLIND_V1",
        "frozen_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "status": "BEFORE_REAL_F3_DATA",
        "f2_preregistration_manifest_sha256": sha256_file(
            PREREGISTRATION_MANIFEST_PATH
        ),
        "f2_preregistration_audit_id": preregistration["audit_id"],
        "files": files,
        "catalog": {
            "feature_count": len(
                validate_catalog(load_config(CONFIG_PATH))
            ),
            "support_columns": list(SUPPORT_COLUMNS),
            "non_predictor_metadata": list(NON_PREDICTOR_METADATA),
        },
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "pyarrow": pyarrow.__version__,
        },
        "pytest_command": (
            "python -m pytest volatility_trigger/tests -q "
            "(cwd=repository root)"
        ),
        "real_f3_data_opened_before_freeze": False,
        "labels_opened": False,
        "outcomes_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
    }
    write_json(FREEZE_PATH, manifest)
    return manifest


def verify_freeze() -> dict[str, object]:
    if not FREEZE_PATH.is_file():
        raise FileNotFoundError(
            f"freeze manifest missing: run `{Path(__file__).name} freeze`"
        )
    verify_preregistration()
    manifest = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = _freeze_path(str(relative))
        if not path.is_file():
            raise RuntimeError(f"frozen F3 file missing: {relative}")
        if path.stat().st_size != int(expected["bytes"]):
            raise RuntimeError(f"frozen F3 file size changed: {relative}")
        if sha256_file(path) != str(expected["sha256"]):
            raise RuntimeError(f"frozen F3 file hash changed: {relative}")
    return manifest


def telegram(message: str, enabled: bool, main_config: Mapping) -> bool:
    if not enabled:
        return False
    return bool(
        send_persistent_text(
            main_config["telegram_results_folder"],
            message,
        )
    )


def _clock(value: str) -> time:
    return time.fromisoformat(value)


def pre_lb_session_bounds(
    session_date: date,
    f0_config: Mapping,
) -> dict[str, int]:
    session = f0_config["session"]

    def at(key: str) -> int:
        return datetime_to_dotnet_ticks(
            datetime.combine(
                session_date,
                _clock(str(session[key])),
                tzinfo=NY_ZONE,
            )
        )

    return {
        "load_start": at("depth_load_start_ny"),
        "rth_start": at("rth_start_ny"),
        "rth_end": at("rth_end_ny"),
        "load_end": at("depth_load_end_ny"),
    }


def load_trade_session(
    session_date: date,
    cache_root: Path,
) -> tuple[object, np.ndarray, Path]:
    source_date = session_date - timedelta(days=1)
    source = cache_root / source_date.strftime("%Y_%m_%d") / "trades.dat"
    if not source.is_file() or source.stat().st_size <= 33:
        raise FileNotFoundError(f"missing trade cache: {source}")
    bounds = trade_session_bounds(session_date)
    context, rows = load_cache_window(
        source,
        start_ticks=bounds["session_start"],
        end_ticks=bounds["load_end"],
    )
    return context, rows, source


def _session_paths(session_date: str) -> dict[str, Path]:
    prefix = CACHE / session_date
    return {
        "audit": prefix.with_name(prefix.name + "_audit.json"),
        "features": prefix.with_name(prefix.name + "_features.parquet"),
    }


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if frame.empty and not len(frame.columns):
        frame = pd.DataFrame({"_empty": pd.Series(dtype="int8")})
    frame.to_parquet(path, index=False)


def _read_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if list(frame.columns) == ["_empty"]:
        return pd.DataFrame()
    return frame


def _write_session_cache(
    session_date: str,
    *,
    audit: Mapping,
    features: pd.DataFrame,
) -> None:
    paths = _session_paths(session_date)
    _write_frame(paths["features"], features)
    # Completeness marker is written last.
    write_json(paths["audit"], audit)


def _read_session_cache(
    session_date: str,
) -> tuple[dict[str, object], pd.DataFrame] | None:
    paths = _session_paths(session_date)
    if not all(path.is_file() for path in paths.values()):
        return None
    return (
        json.loads(paths["audit"].read_text(encoding="utf-8")),
        _read_frame(paths["features"]),
    )


def cache_guard(freeze_sha: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    marker = CACHE / "F3_FREEZE_SHA256.txt"
    if marker.is_file():
        observed = marker.read_text(encoding="utf-8").strip()
        if observed != freeze_sha:
            raise RuntimeError(
                "F3 session cache freeze mismatch; quarantine before rerun"
            )
        return
    existing = list(CACHE.glob("*_audit.json"))
    if existing:
        raise RuntimeError(
            "unmarked F3 session cache exists; quarantine before rerun"
        )
    marker.write_text(freeze_sha + "\n", encoding="utf-8")


def _finite(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    return pd.Series(
        np.isfinite(frame[list(columns)].to_numpy(dtype=float)).all(axis=1),
        index=frame.index,
    )


def _all_nan(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    return pd.Series(
        np.isnan(frame[list(columns)].to_numpy(dtype=float)).all(axis=1),
        index=frame.index,
    )


def _support_nan_contract(
    frame: pd.DataFrame,
    columns: Sequence[str],
    support_column: str,
) -> bool:
    support = frame[support_column].astype(bool)
    return bool(
        (_finite(frame, columns) == support).all()
        and (_all_nan(frame, columns) == ~support).all()
    )


def validate_feature_matrix(
    matrix: pd.DataFrame,
    *,
    expected_rows: int,
    config: Mapping,
) -> None:
    expected_features = validate_catalog(config)
    if len(matrix) != int(expected_rows):
        raise RuntimeError(
            f"F3 row mismatch: {len(matrix)} != {expected_rows}"
        )
    if matrix.empty:
        return
    if matrix["lb_id"].nunique() != len(matrix):
        raise RuntimeError("F3 lb_id is not unique")
    missing = [
        column
        for column in (
            *expected_features,
            *NON_PREDICTOR_METADATA,
            *CAUSAL_AUDIT_COLUMNS,
        )
        if column not in matrix.columns
    ]
    if missing:
        raise RuntimeError(f"F3 required columns missing: {missing}")
    if any(column in expected_features for column in NON_PREDICTOR_METADATA):
        raise RuntimeError("support/cluster metadata entered feature catalog")
    allowed = {
        *expected_features,
        *NON_PREDICTOR_METADATA,
        *CAUSAL_AUDIT_COLUMNS,
        *IDENTITY_AND_EVENT_METADATA,
    }
    extras = sorted(set(matrix.columns) - allowed)
    if extras:
        raise RuntimeError(f"F3 undeclared matrix columns: {extras}")

    forbidden_fragments = (
        "regime",
        "continue_reached",
        "reverse_reached",
        "future",
        "out_post",
        "time_to_continue",
        "time_to_reverse",
        "max_move",
        "expansion_dominance",
    )
    forbidden = [
        str(column)
        for column in matrix.columns
        if any(
            fragment in str(column).lower()
            for fragment in forbidden_fragments
        )
    ]
    if forbidden:
        raise RuntimeError(f"F3 forbidden columns: {sorted(forbidden)}")

    numeric = matrix[expected_features].to_numpy(dtype=float)
    if np.isinf(numeric).any():
        raise RuntimeError("F3 feature matrix contains infinity")

    catalog = config["feature_catalog"]
    always_finite = [
        *catalog["baseline_detector_and_controls"],
        *catalog["baseline_price_history"],
        *catalog["baseline_tape_history"],
    ]
    if not _finite(matrix, always_finite).all():
        raise RuntimeError("F3 baseline feature contains non-finite value")

    state_features = list(catalog["dom_top10_state"])
    if not _support_nan_contract(
        matrix,
        state_features,
        "DOM_STATE_SUPPORT",
    ):
        raise RuntimeError("F3 DOM state support/NaN contract failed")

    dynamic_features = list(catalog["dom_top10_dynamics"])
    for seconds in (1, 5, 30):
        columns = [
            column
            for column in dynamic_features
            if column.endswith(f"_pre_{seconds}s")
        ]
        if not _support_nan_contract(
            matrix,
            columns,
            f"DOM_W{seconds}_SUPPORT",
        ):
            raise RuntimeError(
                f"F3 DOM W{seconds} support/NaN contract failed"
            )

    profile_features = list(catalog["profile_f11"])
    if not _support_nan_contract(
        matrix,
        profile_features,
        "PROFILE_F11_SUPPORT",
    ):
        raise RuntimeError("F3 profile support/NaN contract failed")

    for seconds in (1, 5, 30):
        expected_combined = (
            matrix["BASELINE_SUPPORT"].astype(bool)
            & matrix["DOM_STATE_SUPPORT"].astype(bool)
            & matrix[f"DOM_W{seconds}_SUPPORT"].astype(bool)
            & matrix["PROFILE_F11_SUPPORT"].astype(bool)
        )
        if not expected_combined.equals(
            matrix[f"COMBINED_W{seconds}_SUPPORT"].astype(bool)
        ):
            raise RuntimeError(
                f"F3 combined W{seconds} support contract failed"
            )

    cut = matrix["source_second_ticks"].astype(np.int64)
    for column in CAUSAL_AUDIT_COLUMNS:
        observed = pd.to_numeric(matrix[column], errors="coerce")
        leak = observed.notna() & observed.ge(cut)
        if leak.any():
            raise RuntimeError(f"F3 causal timestamp violation: {column}")


def process_session(
    session_date: date,
    main_config: Mapping,
    f0_config: Mapping,
    f2_config: Mapping,
) -> tuple[dict[str, object], pd.DataFrame]:
    started = wall_time.perf_counter()
    cache_root = Path(main_config["cache_root"])
    trade_context, raw_trades, trade_source = load_trade_session(
        session_date,
        cache_root,
    )
    try:
        trades, trade_qc = causalize_trade_timestamps(
            raw_trades,
            main_config["timestamp_qc"],
        )
    except ValueError as exc:
        if "timestamp QC failed" not in str(exc):
            raise
        return (
            {
                "session_date": session_date.isoformat(),
                "status": "PASS_FROZEN_TRADE_QC_EXCLUDED",
                "eligible_after_trade_qc": False,
                "trade_qc_exclusion_reason": str(exc),
                "trade_source": str(trade_source),
                "depth_source": None,
                "liquidity_bursts": None,
                "feature_rows": 0,
                "elapsed_seconds": wall_time.perf_counter() - started,
                "labels_opened": False,
                "outcomes_opened": False,
                "models_opened": False,
            },
            pd.DataFrame(),
        )

    source_date = session_date - timedelta(days=1)
    depth_source = (
        cache_root
        / source_date.strftime("%Y_%m_%d")
        / "marketdepth.dat"
    )
    if not depth_source.is_file() or depth_source.stat().st_size <= 33:
        raise FileNotFoundError(f"missing depth cache: {depth_source}")
    bounds = pre_lb_session_bounds(session_date, f0_config)
    depth_context, raw_depth = load_cache_window(
        depth_source,
        start_ticks=bounds["load_start"],
        end_ticks=bounds["load_end"],
    )
    if (
        not math.isclose(
            trade_context.tick_size,
            depth_context.tick_size,
        )
        or not math.isclose(
            trade_context.lot_size,
            depth_context.lot_size,
        )
    ):
        raise ValueError("trade/depth scale mismatch")

    depth, effective_ticks, depth_qc = causal_depth_timestamps(
        raw_depth,
        float(f0_config["depth"]["max_timestamp_jitter_ms"]),
    )
    bursts = detect_liquidity_bursts(
        trades,
        session_date,
        main_config["detector"],
    )
    if bursts:
        matrix, _ = build_feature_matrix(
            trades=trades,
            depth=depth,
            effective_depth_ticks=effective_ticks,
            bursts=bursts,
            rth_start_ticks=bounds["rth_start"],
            depth_load_start_ticks=bounds["load_start"],
            config=f2_config,
        )
        validate_feature_matrix(
            matrix,
            expected_rows=len(bursts),
            config=f2_config,
        )
    else:
        matrix = pd.DataFrame()

    audit = {
        "session_date": session_date.isoformat(),
        "status": "PASS_ELIGIBLE_F3",
        "eligible_after_trade_qc": True,
        "trade_qc_exclusion_reason": None,
        "trade_source": str(trade_source),
        "depth_source": str(depth_source),
        "liquidity_bursts": len(bursts),
        "feature_rows": len(matrix),
        "buy_rows": (
            int(matrix["side"].eq("BUY").sum()) if len(matrix) else 0
        ),
        "sell_rows": (
            int(matrix["side"].eq("SELL").sum()) if len(matrix) else 0
        ),
        **{
            f"{column}_count": (
                int(matrix[column].astype(bool).sum())
                if len(matrix)
                else 0
            )
            for column in SUPPORT_COLUMNS
        },
        "elapsed_seconds": wall_time.perf_counter() - started,
        **{f"trade_{key}": value for key, value in trade_qc.items()},
        **{f"depth_{key}": value for key, value in depth_qc.items()},
        "labels_opened": False,
        "outcomes_opened": False,
        "models_opened": False,
    }
    return audit, matrix


def support_summary(matrix: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    groups = {
        "ALL": pd.Series(True, index=matrix.index),
        "BUY": matrix["side"].eq("BUY"),
        "SELL": matrix["side"].eq("SELL"),
    }
    for group, mask in groups.items():
        total = int(mask.sum())
        for support in SUPPORT_COLUMNS:
            count = int(matrix.loc[mask, support].astype(bool).sum())
            records.append(
                {
                    "group": group,
                    "support": support,
                    "supported_rows": count,
                    "total_rows": total,
                    "support_fraction": count / total if total else math.nan,
                }
            )
    return pd.DataFrame.from_records(records)


def aggregate(
    *,
    coverage: pd.DataFrame,
    f0_config: Mapping,
    f2_config: Mapping,
    freeze_sha: str,
) -> dict[str, object]:
    audits: list[dict[str, object]] = []
    feature_frames: list[pd.DataFrame] = []
    depth_dates = coverage.loc[
        coverage["depth_status"].eq("DATA_PRESENT"),
        "session_date",
    ].astype(str)
    for session_date in depth_dates:
        cached = _read_session_cache(session_date)
        if cached is None:
            raise RuntimeError(f"incomplete F3 session cache: {session_date}")
        audit, features = cached
        audits.append(audit)
        if len(features.columns):
            feature_frames.append(features)

    audit_frame = pd.DataFrame(audits)
    matrix = (
        pd.concat(feature_frames, ignore_index=True)
        if feature_frames
        else pd.DataFrame()
    )
    if len(matrix):
        matrix = matrix.sort_values(
            ["session_date", "source_second_ticks", "lb_id"],
            kind="stable",
        ).reset_index(drop=True)
    expected = f0_config["expected_invariants"]
    checks = {
        "depth_sessions_pass": len(audit_frame)
        == int(expected["depth_present_sessions"]),
        "eligible_sessions_pass": int(
            audit_frame["eligible_after_trade_qc"].astype(bool).sum()
        )
        == int(expected["eligible_after_frozen_trade_qc_sessions"]),
        "liquidity_bursts_pass": len(matrix)
        == int(expected["liquidity_bursts"]),
        "feature_rows_pass": int(audit_frame["feature_rows"].sum())
        == len(matrix),
        "process_errors_pass": not audit_frame["status"]
        .astype(str)
        .str.contains("ERROR")
        .any(),
    }
    validate_feature_matrix(
        matrix,
        expected_rows=int(expected["liquidity_bursts"]),
        config=f2_config,
    )
    if not all(checks.values()):
        raise RuntimeError(f"F3 process gates failed: {checks}")

    supports = support_summary(matrix)
    expected_features = catalog_features(f2_config)
    feature_lineage = {
        "audit_id": "PRE_LB_PRECURSOR_F3_OUTCOME_BLIND_V1",
        "f2_audit_id": f2_config["audit_id"],
        "feature_count": len(expected_features),
        "feature_order": expected_features,
        "feature_families": f2_config["feature_catalog"],
        "support_columns": list(SUPPORT_COLUMNS),
        "support_columns_are_predictors": False,
        "cluster_metadata_are_predictors": False,
        "identity_and_event_metadata": list(IDENTITY_AND_EVENT_METADATA),
        "identity_and_event_metadata_are_predictors": False,
        "causal_audit_columns": list(CAUSAL_AUDIT_COLUMNS),
        "causal_audit_columns_are_predictors": False,
        "predictor_event_time": "< source_second_ticks",
        "trade_windows": "[cut-W,cut)",
        "dom_window_start_group": "INCLUDED",
        "dom_cut_group": "EXCLUDED",
        "depth_domain": f2_config["depth"]["domain"],
        "full_depth_features_used": False,
        "far_tail_features_used": False,
        "mbo_or_order_ids_used": False,
        "post_lb_poc_used": False,
        "imputation_or_locf_used": False,
        "session_exclusion_beyond_frozen_trade_qc": False,
        "historical_rankings_used": False,
        "labels_opened": False,
        "outcomes_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "freeze_sha256": freeze_sha,
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    matrix.to_parquet(OUTPUT / "feature_matrix.parquet", index=False)
    audit_frame.to_csv(OUTPUT / "session_audit.csv", index=False)
    supports.to_csv(OUTPUT / "support_summary.csv", index=False)
    write_json(OUTPUT / "feature_lineage.json", feature_lineage)

    result = {
        "audit_id": "PRE_LB_PRECURSOR_F3_OUTCOME_BLIND_V1",
        "status": "OUTCOME_BLIND_F3_COMPLETE_PENDING_GEMINI_CODEX_REVIEW",
        "process_pass": all(checks.values()),
        "depth_present_sessions": len(audit_frame),
        "eligible_after_frozen_trade_qc_sessions": int(
            audit_frame["eligible_after_trade_qc"].astype(bool).sum()
        ),
        "liquidity_bursts": len(matrix),
        "buy_rows": int(matrix["side"].eq("BUY").sum()),
        "sell_rows": int(matrix["side"].eq("SELL").sum()),
        "feature_count": len(expected_features),
        "support_counts": {
            column: int(matrix[column].astype(bool).sum())
            for column in SUPPORT_COLUMNS
        },
        **checks,
        "parent_v3_status": "REGIME_V3_TARGET_DISCOVERY_FAIL",
        "labels_opened": False,
        "outcomes_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "freeze_sha256": freeze_sha,
    }
    write_json(OUTPUT / "result.json", result)

    output_files = (
        "feature_matrix.parquet",
        "feature_lineage.json",
        "support_summary.csv",
        "session_audit.csv",
        "result.json",
    )
    manifest = {
        "audit_id": "PRE_LB_PRECURSOR_F3_OUTPUT_V1",
        "files": {
            name: {
                "bytes": (OUTPUT / name).stat().st_size,
                "sha256": sha256_file(OUTPUT / name),
            }
            for name in output_files
        },
        "labels_opened": False,
        "outcomes_opened": False,
        "models_opened": False,
    }
    write_json(OUTPUT / "manifest.json", manifest)
    return result


def run(
    *,
    pilot_sessions: int | None,
    telegram_enabled: bool,
) -> dict[str, object]:
    verify_freeze()
    freeze_sha = sha256_file(FREEZE_PATH)
    cache_guard(freeze_sha)
    f2_config = load_config(CONFIG_PATH)
    f0_config = load_config(F0_CONFIG_PATH)
    main_config = load_config(MAIN_CONFIG_PATH)
    coverage = pd.read_csv(COVERAGE_PATH)
    depth_dates = [
        date.fromisoformat(value)
        for value in coverage.loc[
            coverage["depth_status"].eq("DATA_PRESENT"),
            "session_date",
        ].astype(str)
    ]
    if pilot_sessions is not None:
        if int(pilot_sessions) <= 0:
            raise ValueError("pilot_sessions must be positive")
        depth_dates = depth_dates[: int(pilot_sessions)]

    CACHE.mkdir(parents=True, exist_ok=True)
    new_elapsed: list[float] = []
    for index, session_date in enumerate(depth_dates, start=1):
        label = session_date.isoformat()
        cached = _read_session_cache(label)
        if cached is None:
            audit, features = process_session(
                session_date,
                main_config,
                f0_config,
                f2_config,
            )
            _write_session_cache(
                label,
                audit=audit,
                features=features,
            )
            new_elapsed.append(float(audit["elapsed_seconds"]))
        if index % 5 == 0 or index == len(depth_dates):
            print(
                json.dumps(
                    {
                        "processed_depth_sessions": index,
                        "target_depth_sessions": len(depth_dates),
                        "pilot": pilot_sessions is not None,
                    }
                ),
                flush=True,
            )

    if pilot_sessions is not None:
        pilot = {
            "status": "PILOT_F3_RUNTIME_ONLY_COMPLETE",
            "sessions_requested": int(pilot_sessions),
            "sessions_newly_processed": len(new_elapsed),
            "elapsed_seconds_each": new_elapsed,
            "median_seconds": (
                float(np.median(new_elapsed)) if new_elapsed else 0.0
            ),
            "maximum_seconds": max(new_elapsed) if new_elapsed else 0.0,
            "features_not_aggregated_or_inspected": True,
            "labels_opened": False,
            "outcomes_opened": False,
            "models_opened": False,
            "freeze_sha256": freeze_sha,
        }
        write_json(OUTPUT / "pilot_runtime.json", pilot)
        telegram(
            (
                "VT PRE-LB | PILOTO F3 SELLADO\n\n"
                f"Sesiones nuevas: {len(new_elapsed)}; "
                f"mediana: {pilot['median_seconds']:.2f}s; "
                f"máximo: {pilot['maximum_seconds']:.2f}s.\n"
                "Sólo runtime/errores; matriz no agregada. "
                "Labels/outcomes/modelos cerrados."
            ),
            telegram_enabled,
            main_config,
        )
        return pilot

    result = aggregate(
        coverage=coverage,
        f0_config=f0_config,
        f2_config=f2_config,
        freeze_sha=freeze_sha,
    )
    telegram(
        (
            "VT PRE-LB | F3 OUTCOME-BLIND COMPLETO\n\n"
            f"Status: {result['status']}\n"
            f"Sesiones depth/elegibles: "
            f"{result['depth_present_sessions']}/"
            f"{result['eligible_after_frozen_trade_qc_sessions']}\n"
            f"LB: {result['liquidity_bursts']}; "
            f"BUY/SELL: {result['buy_rows']}/{result['sell_rows']}; "
            f"features: {result['feature_count']}\n"
            f"Supports: {result['support_counts']}\n"
            "Labels/outcomes/modelos cerrados. "
            "Pendiente auditoría conjunta Gemini-Codex; no abre discovery."
        ),
        telegram_enabled,
        main_config,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("freeze")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--pilot-sessions", type=int)
    run_parser.add_argument("--telegram", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        manifest = freeze()
        print(json.dumps(manifest, indent=2))
        return 0
    result = run(
        pilot_sessions=args.pilot_sessions,
        telegram_enabled=args.telegram,
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
