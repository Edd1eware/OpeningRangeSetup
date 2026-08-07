from __future__ import annotations

import ast
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

import volatility_trigger.run_pre_lb_precursor_f0_f1 as runner


def test_runner_imports_no_research_or_model_module() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert "run_research" not in imported
    assert "src.vt_model" not in imported
    lowered = source.lower()
    assert "regime_discovery_labels" not in lowered
    assert "label_regime_path" not in lowered


def test_freeze_and_verify_detect_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = tmp_path / "frozen.txt"
    frozen.write_text("frozen\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(runner, "FREEZE_FILES", ("frozen.txt",))
    monkeypatch.setattr(runner, "FREEZE_PATH", manifest_path)
    monkeypatch.setattr(
        runner,
        "_freeze_path",
        lambda relative: tmp_path / relative,
    )

    manifest = runner.freeze()
    assert manifest["models_opened"] is False
    assert runner.verify_freeze() == manifest

    frozen.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="frozen file size changed"):
        runner.verify_freeze()


def test_cache_guard_rejects_mismatched_or_unmarked_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "cache"
    monkeypatch.setattr(runner, "CACHE", cache)
    runner.cache_guard("ABC")
    runner.cache_guard("ABC")

    with pytest.raises(RuntimeError, match="freeze mismatch"):
        runner.cache_guard("DEF")

    marker = cache / "F0_F1_FREEZE_SHA256.txt"
    marker.unlink()
    (cache / "2022-07-27_audit.json").write_text(
        "{}",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="unmarked session cache"):
        runner.cache_guard("ABC")


def test_empty_frame_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "empty.parquet"
    runner._write_frame(path, runner._empty_frame())
    observed = runner._read_frame(path)
    assert observed.empty
    assert len(observed.columns) == 0


def test_process_session_accepts_eligible_session_with_zero_bursts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_date = date(2022, 7, 27)
    cache_root = tmp_path / "cache"
    depth_source = cache_root / "2022_07_26" / "marketdepth.dat"
    depth_source.parent.mkdir(parents=True)
    depth_source.write_bytes(b"x" * 34)
    row_dtype = np.dtype(
        [
            ("ticks", "<i8"),
            ("side_code", "u1"),
            ("price_raw", "<i4"),
            ("volume_raw", "<u4"),
        ]
    )
    empty = np.empty(0, dtype=row_dtype)
    context = SimpleNamespace(tick_size=0.25, lot_size=1.0)
    monkeypatch.setattr(
        runner,
        "load_trade_session",
        lambda *_args: (context, empty, tmp_path / "trades.dat"),
    )
    monkeypatch.setattr(
        runner,
        "load_cache_window",
        lambda *_args, **_kwargs: (context, empty),
    )
    monkeypatch.setattr(
        runner,
        "causalize_trade_timestamps",
        lambda rows, _qc: (rows, {}),
    )
    monkeypatch.setattr(
        runner,
        "causal_depth_timestamps",
        lambda rows, _jitter: (rows, np.asarray([], dtype=np.int64), {}),
    )
    monkeypatch.setattr(
        runner,
        "detect_liquidity_bursts",
        lambda *_args, **_kwargs: [],
    )
    main_config = {
        "cache_root": str(cache_root),
        "timestamp_qc": {},
        "detector": {},
    }
    audit_config = {
        "session": {
            "depth_load_start_ny": "09:25:00",
            "rth_start_ny": "09:30:00",
            "rth_end_ny": "16:00:00",
            "depth_load_end_ny": "16:00:20",
        },
        "depth": {
            "max_timestamp_jitter_ms": 50.0,
            "min_spread_ticks": 1,
            "max_spread_ticks": 4,
            "max_global_group_age_ms": 250.0,
            "level_ks": [1, 3, 5, 10],
            "far_level_diagnostic_ticks": 50,
            "startup_minutes": 15,
        },
        "pre_windows_seconds": [1, 5, 30],
        "profile": {
            "drift_seconds": 300,
            "value_area_fraction": 0.70,
        },
    }
    audit, _, _, _, missing, prewindow, clustering, profile = (
        runner.process_session(session_date, main_config, audit_config)
    )
    assert audit["liquidity_bursts"] == 0
    assert audit["valid_references"] == 0
    assert audit["invalid_references"] == 0
    assert missing.empty
    assert prewindow.empty
    assert clustering.empty
    assert profile.empty


def _aggregate_fixture() -> tuple[pd.DataFrame, dict]:
    coverage = pd.DataFrame(
        {
            "session_date": ["2022-07-27"],
            "depth_status": ["DATA_PRESENT"],
        }
    )
    config = {
        "audit_id": "TEST",
        "depth": {
            "aggregate_level_availability_min": 0.99,
            "each_session_level_availability_min": 0.95,
        },
        "expected_invariants": {
            "depth_present_sessions": 1,
            "eligible_after_frozen_trade_qc_sessions": 1,
            "liquidity_bursts": 1,
            "valid_references": 1,
            "invalid_references": 0,
        },
    }
    return coverage, config


def _cached_frames(
    *,
    future_column: bool = False,
) -> tuple[
    dict,
    dict,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    profile = pd.DataFrame(
        {
            "lb_id": ["LB"],
            "profile_raw_available": [True],
            "PRF_PocDrift_ticks_300s_available": [False],
        }
    )
    if future_column:
        profile["regime"] = "CONTINUATION"
    return (
        {
            "session_date": "2022-07-27",
            "eligible_after_trade_qc": True,
            "status": "PASS_ELIGIBLE",
        },
        {"session_date": "2022-07-27"},
        pd.DataFrame(
            {
                "session_date": ["2022-07-27"],
                "eligible_after_trade_qc": [True],
                "k": [1],
                "fresh_valid_seconds": [100.0],
                "both_ge_k_seconds": [100.0],
                "both_ge_k_fraction": [1.0],
            }
        ),
        pd.DataFrame(),
        pd.DataFrame(
            {
                "lb_id": ["LB"],
                "reference_status": [runner.VALID],
            }
        ),
        pd.DataFrame({"lb_id": ["LB"]}),
        pd.DataFrame({"lb_id": ["LB"]}),
        profile,
    )


def test_aggregate_aborts_on_non_nested_levels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coverage, config = _aggregate_fixture()
    monkeypatch.setattr(
        runner,
        "_read_session_cache",
        lambda _session: _cached_frames(),
    )
    monkeypatch.setattr(
        runner,
        "level_viability",
        lambda *_args, **_kwargs: (pd.DataFrame(), False),
    )
    with pytest.raises(RuntimeError, match="not nested"):
        runner.aggregate(
            coverage=coverage,
            audit_config=config,
            freeze_sha="ABC",
        )


def test_aggregate_guards_every_output_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coverage, config = _aggregate_fixture()
    monkeypatch.setattr(
        runner,
        "_read_session_cache",
        lambda _session: _cached_frames(future_column=True),
    )
    with pytest.raises(RuntimeError, match="forbidden output columns"):
        runner.aggregate(
            coverage=coverage,
            audit_config=config,
            freeze_sha="ABC",
        )


def test_pilot_is_runtime_only_and_full_calls_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    cache = output / "session_cache"
    monkeypatch.setattr(runner, "OUTPUT", output)
    monkeypatch.setattr(runner, "CACHE", cache)
    monkeypatch.setattr(runner, "verify_freeze", lambda: {"status": "FROZEN"})
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "ABC")
    monkeypatch.setattr(runner, "cache_guard", lambda _sha: None)

    audit_config = {"audit_id": "TEST"}
    main_config = {"telegram_results_folder": str(tmp_path)}
    monkeypatch.setattr(
        runner,
        "load_config",
        lambda path: (
            audit_config if path == runner.CONFIG_PATH else main_config
        ),
    )
    coverage = pd.DataFrame(
        {
            "session_date": ["2022-07-27"],
            "depth_status": ["DATA_PRESENT"],
        }
    )
    monkeypatch.setattr(runner.pd, "read_csv", lambda _path: coverage)
    monkeypatch.setattr(runner, "_read_session_cache", lambda _date: None)
    monkeypatch.setattr(
        runner,
        "process_session",
        lambda *_args: (
            {
                "session_date": date(2022, 7, 27).isoformat(),
                "elapsed_seconds": 1.25,
            },
            {},
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        runner,
        "_write_session_cache",
        lambda *_args, **_kwargs: None,
    )
    aggregate_calls: list[str] = []

    def fake_aggregate(**_kwargs) -> dict[str, object]:
        aggregate_calls.append("full")
        return {
            "status": "COMPLETE",
            "depth_present_sessions": 1,
            "eligible_after_frozen_trade_qc_sessions": 1,
            "liquidity_bursts": 1,
            "valid_references": 1,
            "invalid_references": 0,
            "reference_status_counts": {"VALID": 1},
            "level_viability": [],
        }

    monkeypatch.setattr(runner, "aggregate", fake_aggregate)
    pilot = runner.run(pilot_sessions=1, telegram_enabled=False)
    assert pilot["status"] == "PILOT_RUNTIME_ONLY_COMPLETE"
    assert pilot["metrics_not_aggregated_or_opened"] is True
    assert not aggregate_calls
    persisted = json.loads(
        (output / "pilot_runtime.json").read_text(encoding="utf-8")
    )
    assert persisted["median_seconds"] == 1.25

    full = runner.run(pilot_sessions=None, telegram_enabled=False)
    assert full["status"] == "COMPLETE"
    assert aggregate_calls == ["full"]
