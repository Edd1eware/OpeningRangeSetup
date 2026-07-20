from pathlib import Path
import time

import pandas as pd

import lb_absorption_breakout_validation as validation
import replay_sync_runner_common_after_sync as replay_sync


PROJECT = Path(__file__).resolve().parent


def test_freeze_uses_only_frozen_discovery(tmp_path):
    package = tmp_path / "frozen"
    spec = validation.freeze_package(PROJECT, package)

    assert spec["training"]["analysis_rows"] == 70
    assert spec["training"]["rows_2025_2026_selected"] == 0
    assert spec["training"]["validation_years_opened"] == []
    assert spec["features"] == validation.FEATURES
    assert spec["mixed_policy"].startswith("C_MIXED_PATH")
    assert spec["trading_logic_changed"] is False

    loaded_spec, bundle = validation.load_package(package)
    assert loaded_spec["training"]["model_sha256"] == spec["training"]["model_sha256"]
    assert bundle["features"] == validation.FEATURES


def test_regime_rule_is_strict_and_absolute():
    frame = pd.DataFrame({"x": [-5.0, -4.0, 4.0, 5.0]})
    rule = {"feature": "x", "transform": "absolute", "operator": ">", "threshold": 4.0}
    assert validation._rule_mask(frame, rule).tolist() == [True, False, False, True]


def test_metric_row_keeps_absorption_as_positive_class():
    frame = pd.DataFrame({
        "target": [1, 1, 0, 0],
        "probability_A": [0.9, 0.8, 0.2, 0.1],
        "predicted_A": [1, 1, 0, 0],
    })
    row = validation._metric_row(frame, "ALL_AB")
    assert row["roc_auc"] == 1.0
    assert row["sensitivity_absorption_A"] == 1.0
    assert row["specificity_breakout_B"] == 1.0


def test_terminal_copy_is_validated_at_destination(tmp_path):
    source = tmp_path / "source.csv"
    destination = tmp_path / "saved" / "destination.csv"
    started_at = time.time() - 1
    source.write_text(
        "Exporter_VERSION,Result_Label,ExitTime_NY,Exit_price,result TP SL BE\n"
        f"{replay_sync.EXPECTED_EXPORTER_VERSION},TP,09:31:23,19866.25,+60\n",
        encoding="utf-8",
    )

    assert replay_sync.copy_terminal_result_with_retry(
        source,
        destination,
        started_at,
        attempts=2,
        retry_seconds=0,
    )
    assert replay_sync.is_terminal_result(destination, require_expected_version=True)
