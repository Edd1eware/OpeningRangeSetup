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
from src.pre_lb_audit import (  # noqa: E402
    VALID,
    audit_book_session,
    cluster_bursts,
    forbidden_output_columns,
    level_viability,
    profile_diagnostics,
)
from src.vt_core import (  # noqa: E402
    NY,
    causalize_trade_timestamps,
    contiguous_trade_ticks,
    datetime_to_dotnet_ticks,
    detect_liquidity_bursts,
    load_config,
    session_bounds as trade_session_bounds,
)


CONFIG_PATH = ROOT / "config" / "pre_lb_precursor_f0_config.json"
MAIN_CONFIG_PATH = ROOT / "config" / "discovery_config.json"
COVERAGE_PATH = (
    ROOT / "artifacts" / "data_coverage" / "depth_coverage_manifest.csv"
)
FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "PRE_LB_PRECURSOR_F0_F1_FREEZE_MANIFEST.json"
)
OUTPUT = ROOT / "artifacts" / "pre_lb_precursor_f0_f1"
CACHE = OUTPUT / "session_cache"
NY_ZONE = ZoneInfo("America/New_York")


FREEZE_FILES = (
    "config/pre_lb_precursor_f0_config.json",
    "config/discovery_config.json",
    "config/preregistration/PRE_LB_PRECURSOR_CLAUDE_CODEX_DESIGN_CONSENSUS.md",
    "config/preregistration/PRE_LB_PRECURSOR_F0_F1_PREREGISTRATION.md",
    "config/preregistration/CLAUDE_CODEX_CONSENSUS_REGIME_V3_FINAL.md",
    "artifacts/data_coverage/depth_coverage_manifest.csv",
    "src/pre_lb_audit.py",
    "src/efficiency_audit.py",
    "src/vt_core.py",
    "run_pre_lb_precursor_f0_f1.py",
    "run_research.py",
    "../atas_cache_decoder.py",
    "tests/test_pre_lb_audit.py",
    "tests/test_pre_lb_runner.py",
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


def freeze() -> dict[str, object]:
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
        "audit_id": "PRE_LB_PRECURSOR_F0_F1_OUTCOME_BLIND_V1",
        "frozen_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "status": "BEFORE_REAL_F0_F1_DATA",
        "files": files,
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
        "real_data_opened_before_freeze": False,
        "regime_labels_imported": False,
        "feature_outcome_associations_opened": False,
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
    manifest = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = _freeze_path(relative)
        if not path.is_file():
            raise RuntimeError(f"frozen file missing: {relative}")
        if path.stat().st_size != int(expected["bytes"]):
            raise RuntimeError(f"frozen file size changed: {relative}")
        observed = sha256_file(path)
        if observed != expected["sha256"]:
            raise RuntimeError(f"frozen file changed: {relative}")
    return manifest


def telegram(message: str, enabled: bool, main_config: dict) -> bool:
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
    audit_config: dict,
) -> dict[str, int]:
    session = audit_config["session"]

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
        "quality": prefix.with_name(prefix.name + "_quality.json"),
        "depth": prefix.with_name(prefix.name + "_depth.parquet"),
        "startup": prefix.with_name(prefix.name + "_startup.parquet"),
        "missing": prefix.with_name(prefix.name + "_missing.parquet"),
        "prewindow": prefix.with_name(prefix.name + "_prewindow.parquet"),
        "clustering": prefix.with_name(prefix.name + "_clustering.parquet"),
        "profile": prefix.with_name(prefix.name + "_profile.parquet"),
    }


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame({"_empty": pd.Series(dtype="int8")})


def _write_session_cache(
    session_date: str,
    *,
    audit: dict[str, object],
    quality: dict[str, object],
    depth: pd.DataFrame,
    startup: pd.DataFrame,
    missing: pd.DataFrame,
    prewindow: pd.DataFrame,
    clustering: pd.DataFrame,
    profile: pd.DataFrame,
) -> None:
    paths = _session_paths(session_date)
    write_json(paths["quality"], quality)
    _write_frame(paths["depth"], depth if len(depth.columns) else _empty_frame())
    _write_frame(
        paths["startup"],
        startup if len(startup.columns) else _empty_frame(),
    )
    _write_frame(
        paths["missing"],
        missing if len(missing.columns) else _empty_frame(),
    )
    _write_frame(
        paths["prewindow"],
        prewindow if len(prewindow.columns) else _empty_frame(),
    )
    _write_frame(
        paths["clustering"],
        clustering if len(clustering.columns) else _empty_frame(),
    )
    _write_frame(
        paths["profile"],
        profile if len(profile.columns) else _empty_frame(),
    )
    # Completeness marker is written last.
    write_json(paths["audit"], audit)


def _read_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    return (
        pd.DataFrame()
        if list(frame.columns) == ["_empty"]
        else frame
    )


def _read_session_cache(
    session_date: str,
) -> tuple[
    dict[str, object],
    dict[str, object],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
] | None:
    paths = _session_paths(session_date)
    if not all(path.is_file() for path in paths.values()):
        return None
    return (
        json.loads(paths["audit"].read_text(encoding="utf-8")),
        json.loads(paths["quality"].read_text(encoding="utf-8")),
        _read_frame(paths["depth"]),
        _read_frame(paths["startup"]),
        _read_frame(paths["missing"]),
        _read_frame(paths["prewindow"]),
        _read_frame(paths["clustering"]),
        _read_frame(paths["profile"]),
    )


def cache_guard(freeze_sha: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    marker = CACHE / "F0_F1_FREEZE_SHA256.txt"
    if marker.is_file():
        observed = marker.read_text(encoding="utf-8").strip()
        if observed != freeze_sha:
            raise RuntimeError(
                "session cache freeze mismatch; quarantine it before rerun"
            )
    else:
        existing = list(CACHE.glob("*_audit.json"))
        if existing:
            raise RuntimeError(
                "unmarked session cache exists; quarantine it before rerun"
            )
        marker.write_text(freeze_sha + "\n", encoding="utf-8")


def process_session(
    session_date: date,
    main_config: dict,
    audit_config: dict,
) -> tuple[
    dict[str, object],
    dict[str, object],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    started = wall_time.perf_counter()
    cache_root = Path(main_config["cache_root"])
    source_date = session_date - timedelta(days=1)
    depth_source = (
        cache_root
        / source_date.strftime("%Y_%m_%d")
        / "marketdepth.dat"
    )
    if not depth_source.is_file() or depth_source.stat().st_size <= 33:
        raise FileNotFoundError(f"missing depth cache: {depth_source}")

    trade_context, raw_trades, trade_source = load_trade_session(
        session_date,
        cache_root,
    )
    eligible = True
    trade_qc: dict[str, object]
    trade_qc_exclusion_reason: str | None = None
    try:
        trades, trade_qc = causalize_trade_timestamps(
            raw_trades,
            main_config["timestamp_qc"],
        )
    except ValueError as exc:
        if "timestamp QC failed" not in str(exc):
            raise
        eligible = False
        trades = raw_trades[:0]
        trade_qc = {}
        trade_qc_exclusion_reason = str(exc)

    bounds = pre_lb_session_bounds(session_date, audit_config)
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
        float(audit_config["depth"]["max_timestamp_jitter_ms"]),
    )
    bursts = (
        detect_liquidity_bursts(
            trades,
            session_date,
            main_config["detector"],
        )
        if eligible
        else []
    )

    (
        missing,
        prewindow,
        depth_frame,
        startup,
        quality,
    ) = audit_book_session(
        session_date=session_date.isoformat(),
        depth=depth,
        effective_ticks=effective_ticks,
        bursts=bursts,
        load_start_ticks=bounds["load_start"],
        rth_start_ticks=bounds["rth_start"],
        rth_end_ticks=bounds["rth_end"],
        load_end_ticks=bounds["load_end"],
        minimum_spread=int(audit_config["depth"]["min_spread_ticks"]),
        maximum_spread=int(audit_config["depth"]["max_spread_ticks"]),
        maximum_age_ms=float(
            audit_config["depth"]["max_global_group_age_ms"]
        ),
        pre_windows_seconds=audit_config["pre_windows_seconds"],
        level_ks=audit_config["depth"]["level_ks"],
        far_level_ticks=int(
            audit_config["depth"]["far_level_diagnostic_ticks"]
        ),
        startup_minutes=int(audit_config["depth"]["startup_minutes"]),
        eligible=eligible,
    )

    clustering = cluster_bursts(bursts)
    if eligible and bursts:
        trade_ticks = contiguous_trade_ticks(trades)
        profile = profile_diagnostics(
            trades,
            trade_ticks,
            bursts,
            rth_start_ticks=bounds["rth_start"],
            drift_seconds=int(audit_config["profile"]["drift_seconds"]),
            value_area_fraction=float(
                audit_config["profile"]["value_area_fraction"]
            ),
        )
        profile = profile.merge(
            missing[
                [
                    "lb_id",
                    "reference_status",
                    "reference_available",
                ]
            ],
            on="lb_id",
            how="left",
            validate="one_to_one",
        )
    else:
        profile = pd.DataFrame()

    frames = [
        depth_frame,
        startup,
        missing,
        prewindow,
        clustering,
        profile,
    ]
    forbidden = forbidden_output_columns(frames)
    if forbidden:
        raise RuntimeError(f"forbidden output columns: {forbidden}")

    elapsed = wall_time.perf_counter() - started
    audit = {
        "session_date": session_date.isoformat(),
        "status": (
            "PASS_ELIGIBLE"
            if eligible
            else "PASS_DEPTH_CONTEXT_TRADE_QC_EXCLUDED"
        ),
        "eligible_after_trade_qc": eligible,
        "trade_qc_exclusion_reason": trade_qc_exclusion_reason,
        "trade_source": str(trade_source),
        "depth_source": str(depth_source),
        "liquidity_bursts": len(bursts) if eligible else None,
        "valid_references": (
            int(missing["reference_status"].eq(VALID).sum())
            if eligible and len(missing)
            else 0
            if eligible
            else None
        ),
        "invalid_references": (
            int(missing["reference_status"].ne(VALID).sum())
            if eligible and len(missing)
            else 0
            if eligible
            else None
        ),
        "elapsed_seconds": elapsed,
        **{f"trade_{key}": value for key, value in trade_qc.items()},
        **{f"depth_{key}": value for key, value in depth_qc.items()},
    }
    return (
        audit,
        quality,
        depth_frame,
        startup,
        missing,
        prewindow,
        clustering,
        profile,
    )


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if len(frame.columns)]
    return (
        pd.concat(usable, ignore_index=True)
        if usable
        else pd.DataFrame()
    )


def aggregate(
    *,
    coverage: pd.DataFrame,
    audit_config: dict,
    freeze_sha: str,
) -> dict[str, object]:
    collections: dict[str, list] = {
        "audit": [],
        "quality": [],
        "depth": [],
        "startup": [],
        "missing": [],
        "prewindow": [],
        "clustering": [],
        "profile": [],
    }
    depth_dates = coverage.loc[
        coverage["depth_status"].eq("DATA_PRESENT"),
        "session_date",
    ].astype(str)
    for session_date in depth_dates:
        cached = _read_session_cache(session_date)
        if cached is None:
            raise RuntimeError(f"incomplete session cache: {session_date}")
        (
            audit,
            quality,
            depth,
            startup,
            missing,
            prewindow,
            clustering,
            profile,
        ) = cached
        collections["audit"].append(audit)
        collections["quality"].append(quality)
        collections["depth"].append(depth)
        collections["startup"].append(startup)
        collections["missing"].append(missing)
        collections["prewindow"].append(prewindow)
        collections["clustering"].append(clustering)
        collections["profile"].append(profile)

    audit_frame = pd.DataFrame(collections["audit"])
    quality_frame = pd.DataFrame(collections["quality"])
    depth_frame = _concat(collections["depth"])
    startup_frame = _concat(collections["startup"])
    missing_frame = _concat(collections["missing"])
    prewindow_frame = _concat(collections["prewindow"])
    clustering_frame = _concat(collections["clustering"])
    profile_frame = _concat(collections["profile"])

    forbidden = forbidden_output_columns(
        [
            audit_frame,
            quality_frame,
            depth_frame,
            startup_frame,
            missing_frame,
            prewindow_frame,
            clustering_frame,
            profile_frame,
        ]
    )
    if forbidden:
        raise RuntimeError(f"forbidden output columns: {forbidden}")

    expected = audit_config["expected_invariants"]
    depth_sessions = len(audit_frame)
    eligible_sessions = int(
        audit_frame["eligible_after_trade_qc"].astype(bool).sum()
    )
    process_errors = int(
        audit_frame["status"].astype(str).str.contains("ERROR").sum()
    )
    burst_count = len(missing_frame)
    valid_count = int(missing_frame["reference_status"].eq(VALID).sum())
    invalid_count = int(missing_frame["reference_status"].ne(VALID).sum())
    exclusive_causes = bool(
        len(missing_frame)
        == missing_frame["lb_id"].nunique()
        == len(prewindow_frame)
        == len(clustering_frame)
        == len(profile_frame)
    )

    viability, nested = level_viability(
        depth_frame,
        aggregate_minimum=float(
            audit_config["depth"]["aggregate_level_availability_min"]
        ),
        each_session_minimum=float(
            audit_config["depth"][
                "each_session_level_availability_min"
            ]
        ),
        expected_eligible_sessions=int(
            expected["eligible_after_frozen_trade_qc_sessions"]
        ),
    )
    if not nested:
        raise RuntimeError("level viability is not nested")

    checks = {
        "depth_sessions_pass": depth_sessions
        == int(expected["depth_present_sessions"]),
        "eligible_sessions_pass": eligible_sessions
        == int(expected["eligible_after_frozen_trade_qc_sessions"]),
        "liquidity_bursts_pass": burst_count
        == int(expected["liquidity_bursts"]),
        "valid_references_pass": valid_count
        == int(expected["valid_references"]),
        "invalid_references_pass": invalid_count
        == int(expected["invalid_references"]),
        "process_errors_pass": process_errors == 0,
        "exclusive_causes_and_row_alignment_pass": exclusive_causes,
        "level_nesting_pass": nested,
        "forbidden_columns_pass": not forbidden,
    }
    process_pass = all(checks.values())
    if not process_pass:
        raise RuntimeError(f"F0/F1 process gates failed: {checks}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    quality_frame.to_csv(OUTPUT / "session_quality.csv", index=False)
    depth_frame.to_csv(
        OUTPUT / "book_depth_characterization.csv",
        index=False,
    )
    startup_frame.to_csv(
        OUTPUT / "book_startup_convergence.csv",
        index=False,
    )
    missing_frame.to_csv(
        OUTPUT / "reference_missingness_audit.csv",
        index=False,
    )
    prewindow_frame.to_csv(
        OUTPUT / "pre_window_availability.csv",
        index=False,
    )
    clustering_frame.to_csv(
        OUTPUT / "lb_clustering_audit.csv",
        index=False,
    )
    profile_frame.to_csv(
        OUTPUT / "profile_missingness_diagnostic.csv",
        index=False,
    )
    audit_frame.to_csv(OUTPUT / "data_audit.csv", index=False)
    viability.to_csv(OUTPUT / "level_viability.csv", index=False)

    status_counts = {
        str(key): int(value)
        for key, value in missing_frame[
            "reference_status"
        ].value_counts().items()
    }
    result = {
        "audit_id": audit_config["audit_id"],
        "status": "OUTCOME_BLIND_F0_F1_COMPLETE_PENDING_JOINT_REVIEW",
        "process_pass": process_pass,
        "depth_present_sessions": depth_sessions,
        "eligible_after_frozen_trade_qc_sessions": eligible_sessions,
        "liquidity_bursts": burst_count,
        "valid_references": valid_count,
        "invalid_references": invalid_count,
        "reference_status_counts": status_counts,
        "level_viability": viability.to_dict(orient="records"),
        "startup_convergence_requires_joint_review": True,
        "level_pathology_requires_joint_review": True,
        "profile_raw_available": int(
            profile_frame["profile_raw_available"].astype(bool).sum()
        ),
        "profile_drift_300s_available": int(
            profile_frame[
                "PRF_PocDrift_ticks_300s_available"
            ].astype(bool).sum()
        ),
        **checks,
        "parent_v3_status": "REGIME_V3_TARGET_DISCOVERY_FAIL",
        "f0_may_not_exclude_sessions_or_rescue_parent": True,
        "regime_labels_imported": False,
        "feature_outcome_associations_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "freeze_sha256": freeze_sha,
    }
    write_json(OUTPUT / "result.json", result)

    output_files = (
        "session_quality.csv",
        "book_depth_characterization.csv",
        "book_startup_convergence.csv",
        "reference_missingness_audit.csv",
        "pre_window_availability.csv",
        "lb_clustering_audit.csv",
        "profile_missingness_diagnostic.csv",
        "data_audit.csv",
        "level_viability.csv",
        "result.json",
    )
    manifest = {
        name: sha256_file(OUTPUT / name)
        for name in output_files
    }
    write_json(OUTPUT / "manifest.json", manifest)
    return result


def run(
    *,
    pilot_sessions: int | None,
    telegram_enabled: bool,
) -> dict[str, object]:
    freeze_manifest = verify_freeze()
    freeze_sha = sha256_file(FREEZE_PATH)
    cache_guard(freeze_sha)
    audit_config = load_config(CONFIG_PATH)
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
            (
                audit,
                quality,
                depth,
                startup,
                missing,
                prewindow,
                clustering,
                profile,
            ) = process_session(session_date, main_config, audit_config)
            _write_session_cache(
                label,
                audit=audit,
                quality=quality,
                depth=depth,
                startup=startup,
                missing=missing,
                prewindow=prewindow,
                clustering=clustering,
                profile=profile,
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
            "status": "PILOT_RUNTIME_ONLY_COMPLETE",
            "sessions_requested": int(pilot_sessions),
            "sessions_newly_processed": len(new_elapsed),
            "elapsed_seconds_each": new_elapsed,
            "median_seconds": (
                float(np.median(new_elapsed)) if new_elapsed else 0.0
            ),
            "maximum_seconds": max(new_elapsed) if new_elapsed else 0.0,
            "metrics_not_aggregated_or_opened": True,
            "freeze_sha256": freeze_sha,
        }
        write_json(OUTPUT / "pilot_runtime.json", pilot)
        telegram(
            (
                "VT PRE-LB | PILOTO F0/F1 SELLADO\n\n"
                f"Sesiones nuevas: {len(new_elapsed)}; "
                f"mediana: {pilot['median_seconds']:.2f}s; "
                f"máximo: {pilot['maximum_seconds']:.2f}s.\n"
                "Sólo runtime/errores; métricas científicas no agregadas. "
                "Pendiente acuerdo Claude-Codex para continuar full."
            ),
            telegram_enabled,
            main_config,
        )
        return pilot

    result = aggregate(
        coverage=coverage,
        audit_config=audit_config,
        freeze_sha=freeze_sha,
    )
    telegram(
        (
            "VT PRE-LB | F0/F1 OUTCOME-BLIND COMPLETO\n\n"
            f"Status: {result['status']}\n"
            f"Sesiones depth/elegibles: "
            f"{result['depth_present_sessions']}/"
            f"{result['eligible_after_frozen_trade_qc_sessions']}\n"
            f"LB: {result['liquidity_bursts']}; "
            f"VALID: {result['valid_references']}; "
            f"invalid: {result['invalid_references']}\n"
            f"Causas: {result['reference_status_counts']}\n"
            f"Lk: {result['level_viability']}\n"
            "Outcomes/modelos/validation/holdout cerrados. "
            "Pendiente auditoría conjunta Claude-Codex; no abre F2."
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
