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

import volatility_trigger.run_pre_lb_precursor_f3 as runner  # noqa: E402


def _config() -> dict[str, object]:
    return runner.load_config(runner.CONFIG_PATH)


def _valid_unsupported_matrix() -> pd.DataFrame:
    config = _config()
    row: dict[str, object] = {
        "lb_id": "LB_TEST",
        "session_date": "2022-08-01",
        "source_second_ticks": 100,
        "publish_ticks": 110,
        "side": "BUY",
        "direction": 1,
        "BASELINE_SUPPORT": True,
        "DOM_STATE_SUPPORT": False,
        "DOM_W1_SUPPORT": False,
        "DOM_W5_SUPPORT": False,
        "DOM_W30_SUPPORT": False,
        "PROFILE_RAW_SUPPORT": False,
        "PROFILE_F11_SUPPORT": False,
        "COMBINED_W1_SUPPORT": False,
        "COMBINED_W5_SUPPORT": False,
        "COMBINED_W30_SUPPORT": False,
        "LB_CLUSTER_ID_30S": "2022-08-01_C00000",
        "LB_CLUSTER_SIZE_30S": 1,
        "MAX_PRECURSOR_TRADE_TICKS": 99,
        "MAX_PRECURSOR_DEPTH_TICKS": np.nan,
        "MAX_PROFILE_TRADE_TICKS": np.nan,
    }
    catalog = config["feature_catalog"]
    for family in (
        "baseline_detector_and_controls",
        "baseline_price_history",
        "baseline_tape_history",
    ):
        for feature in catalog[family]:
            row[feature] = 0.0
    for family in (
        "dom_top10_state",
        "dom_top10_dynamics",
        "profile_f11",
    ):
        for feature in catalog[family]:
            row[feature] = np.nan
    return pd.DataFrame([row])


def test_runner_import_graph_has_no_model_or_label_loader() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden = (
        "run_research",
        "vt_model",
        "regime_discovery",
        "post_lb_regime",
    )
    assert not [
        name
        for name in imports
        if any(token in name for token in forbidden)
    ]
    lowered = source.lower()
    assert "labels.parquet" not in lowered
    assert "regime_distribution.csv" not in lowered


def test_runner_support_metadata_matches_amended_preregistration() -> None:
    config = _config()
    assert tuple(config["support_columns_not_predictors"][:-2]) == (
        *runner.SUPPORT_COLUMNS,
    )
    assert config["support_mask_technical_amendment"][
        "gemini_verdict"
    ] == "GEMINI_F2_SUPPORT_AMENDMENT: APPROVE"


def test_verify_preregistration_detects_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = tmp_path / "frozen.txt"
    frozen.write_text("fixed\n", encoding="utf-8")
    config = _config()
    manifest = {
        "audit_id": "TEST",
        "authorized_next_step": (
            "IMPLEMENT_AND_TEST_F3_OUTCOME_BLIND_EXTRACTOR"
        ),
        "files": {
            "frozen.txt": {
                "bytes": frozen.stat().st_size,
                "sha256": runner.sha256_file(frozen),
            }
        },
        "catalog": {
            "declared_features": 60,
            "observed_features": 60,
            "unique_features": 60,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "PREREGISTRATION_MANIFEST_PATH",
        manifest_path,
    )
    monkeypatch.setattr(
        runner,
        "_freeze_path",
        lambda relative: tmp_path / relative,
    )
    monkeypatch.setattr(runner, "load_config", lambda _path: config)
    assert runner.verify_preregistration()["audit_id"] == "TEST"

    frozen.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="size changed"):
        runner.verify_preregistration()


def test_freeze_and_verify_detect_runner_lineage_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = tmp_path / "runner.py"
    frozen.write_text("fixed\n", encoding="utf-8")
    freeze_path = tmp_path / "freeze.json"
    monkeypatch.setattr(runner, "FREEZE_FILES", ("runner.py",))
    monkeypatch.setattr(runner, "FREEZE_PATH", freeze_path)
    monkeypatch.setattr(
        runner,
        "PREREGISTRATION_MANIFEST_PATH",
        tmp_path / "f2.json",
    )
    (tmp_path / "f2.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "_freeze_path",
        lambda relative: tmp_path / relative,
    )
    monkeypatch.setattr(
        runner,
        "verify_preregistration",
        lambda: {"audit_id": "F2"},
    )
    manifest = runner.freeze()
    assert manifest["real_f3_data_opened_before_freeze"] is False
    assert runner.verify_freeze() == manifest

    frozen.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="size changed"):
        runner.verify_freeze()


def test_cache_guard_rejects_mismatch_and_unmarked_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "session_cache"
    monkeypatch.setattr(runner, "CACHE", cache)
    runner.cache_guard("ABC")
    runner.cache_guard("ABC")
    with pytest.raises(RuntimeError, match="freeze mismatch"):
        runner.cache_guard("DEF")

    (cache / "F3_FREEZE_SHA256.txt").unlink()
    (cache / "2022-08-01_audit.json").write_text(
        "{}",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="unmarked"):
        runner.cache_guard("ABC")


def test_validate_feature_matrix_enforces_support_nan_contract() -> None:
    matrix = _valid_unsupported_matrix()
    runner.validate_feature_matrix(
        matrix,
        expected_rows=1,
        config=_config(),
    )
    state_feature = _config()["feature_catalog"]["dom_top10_state"][0]
    matrix.loc[0, state_feature] = 1.0
    with pytest.raises(RuntimeError, match="DOM state support/NaN"):
        runner.validate_feature_matrix(
            matrix,
            expected_rows=1,
            config=_config(),
        )

    matrix = _valid_unsupported_matrix()
    matrix["UNDECLARED_DIAGNOSTIC"] = 1.0
    with pytest.raises(RuntimeError, match="undeclared matrix columns"):
        runner.validate_feature_matrix(
            matrix,
            expected_rows=1,
            config=_config(),
        )


def test_process_session_trade_qc_exclusion_never_opens_depth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = SimpleNamespace(tick_size=0.25, lot_size=1.0)
    rows = np.empty(
        0,
        dtype=np.dtype(
            [
                ("ticks", "<i8"),
                ("side_code", "u1"),
                ("price_raw", "<i4"),
                ("volume_raw", "<u4"),
            ]
        ),
    )
    monkeypatch.setattr(
        runner,
        "load_trade_session",
        lambda *_args: (context, rows, tmp_path / "trades.dat"),
    )

    def excluded(*_args, **_kwargs):
        raise ValueError("timestamp QC failed: frozen exclusion")

    monkeypatch.setattr(runner, "causalize_trade_timestamps", excluded)
    monkeypatch.setattr(
        runner,
        "load_cache_window",
        lambda *_args, **_kwargs: pytest.fail("depth was opened"),
    )
    audit, features = runner.process_session(
        date(2022, 8, 1),
        {"cache_root": str(tmp_path), "timestamp_qc": {}},
        {},
        _config(),
    )
    assert not audit["eligible_after_trade_qc"]
    assert audit["depth_source"] is None
    assert features.empty


def test_support_summary_is_outcome_blind_and_side_stratified() -> None:
    matrix = pd.concat(
        [
            _valid_unsupported_matrix(),
            _valid_unsupported_matrix().assign(
                lb_id="LB_SELL",
                side="SELL",
                DOM_STATE_SUPPORT=True,
            ),
        ],
        ignore_index=True,
    )
    summary = runner.support_summary(matrix)
    all_state = summary[
        summary["group"].eq("ALL")
        & summary["support"].eq("DOM_STATE_SUPPORT")
    ].iloc[0]
    assert all_state["supported_rows"] == 1
    assert all_state["total_rows"] == 2
    assert all_state["support_fraction"] == 0.5
    assert set(summary["group"]) == {"ALL", "BUY", "SELL"}


def test_aggregate_writes_only_outcome_blind_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = _valid_unsupported_matrix()
    audit = {
        "session_date": "2022-08-01",
        "status": "PASS_ELIGIBLE_F3",
        "eligible_after_trade_qc": True,
        "feature_rows": 1,
    }
    monkeypatch.setattr(runner, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(
        runner,
        "_read_session_cache",
        lambda _session: (audit, matrix),
    )
    result = runner.aggregate(
        coverage=pd.DataFrame(
            {
                "session_date": ["2022-08-01"],
                "depth_status": ["DATA_PRESENT"],
            }
        ),
        f0_config={
            "expected_invariants": {
                "depth_present_sessions": 1,
                "eligible_after_frozen_trade_qc_sessions": 1,
                "liquidity_bursts": 1,
            }
        },
        f2_config=_config(),
        freeze_sha="ABC",
    )
    assert result["process_pass"]
    assert result["labels_opened"] is False
    assert result["outcomes_opened"] is False
    output_names = {
        path.name
        for path in (tmp_path / "output").iterdir()
    }
    assert output_names == {
        "feature_matrix.parquet",
        "feature_lineage.json",
        "support_summary.csv",
        "session_audit.csv",
        "result.json",
        "manifest.json",
    }


def test_pilot_does_not_aggregate_or_inspect_feature_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    output = tmp_path / "output"
    cache = output / "session_cache"
    monkeypatch.setattr(runner, "OUTPUT", output)
    monkeypatch.setattr(runner, "CACHE", cache)
    monkeypatch.setattr(runner, "verify_freeze", lambda: {})
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "ABC")
    monkeypatch.setattr(runner, "cache_guard", lambda _sha: None)
    monkeypatch.setattr(runner, "load_config", lambda _path: config)
    monkeypatch.setattr(
        runner.pd,
        "read_csv",
        lambda _path: pd.DataFrame(
            {
                "session_date": ["2022-08-01"],
                "depth_status": ["DATA_PRESENT"],
            }
        ),
    )
    monkeypatch.setattr(runner, "_read_session_cache", lambda _date: None)
    monkeypatch.setattr(
        runner,
        "process_session",
        lambda *_args: (
            {
                "session_date": "2022-08-01",
                "elapsed_seconds": 1.25,
            },
            _valid_unsupported_matrix(),
        ),
    )
    monkeypatch.setattr(
        runner,
        "_write_session_cache",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        runner,
        "aggregate",
        lambda **_kwargs: pytest.fail("pilot aggregated features"),
    )
    result = runner.run(
        pilot_sessions=1,
        telegram_enabled=False,
    )
    assert result["status"] == "PILOT_F3_RUNTIME_ONLY_COMPLETE"
    assert result["features_not_aggregated_or_inspected"] is True
