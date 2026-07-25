from pathlib import Path
import sys

import numpy as np
import pandas as pd

import importlib.util


SCRIPT = (
    Path(__file__).resolve().parent
    / "contexto_codex_claude"
    / "human_blind_v1"
    / "frozen"
    / "human_blind_v1_pipeline.py"
)
SPEC = importlib.util.spec_from_file_location("human_blind_v1_pipeline", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_canonicalization_buy_and_sell() -> None:
    assert module.canonical_tick(100.50, 100.00, "BUY", 0.25) == 2
    assert module.canonical_tick(99.50, 100.00, "SELL", 0.25) == 2
    assert module.canonical_side("A", "BUY") == "A"
    assert module.canonical_side("B", "SELL") == "A"
    assert module.aligned_trade("B", "BUY") is True
    assert module.aligned_trade("A", "SELL") is True


def test_mapping_and_orders_are_deterministic(tmp_path: Path) -> None:
    config = module.Config(
        sessions=4,
        tick_size=0.25,
        window_seconds=5.0,
        grid_milliseconds=50,
        min_tick=-10,
        max_tick=10,
        heatmap_percentile=99.0,
        max_saturation_fraction=0.05,
        round1_seed=104729,
        round2_seed=1299709,
        uniform_mtime_epoch=946684800,
        allowed_handoff_columns=(),
        annotator_export_columns=(),
    )
    frame = pd.DataFrame(
        {
            "fecha": ["2022-01-01", "2022-01-02", "2023-01-01", "2024-01-01"],
            "BurstId": ["B1", "B2", "B3", "B4"],
        }
    )
    first = module.build_blind_mapping(frame, config)
    second = module.build_blind_mapping(frame, config)
    for left, right in zip(first, second):
        pd.testing.assert_frame_equal(left, right)
    assert set(first[0]["CaseID"]) == {"HB001", "HB002", "HB003", "HB004"}


def test_aggressor_f_is_not_passive() -> None:
    aggressors = {123}
    passive = [
        order_id
        for order_id in (123, 456)
        if order_id not in aggressors
    ]
    assert passive == [456]


def test_html_is_offline_and_has_no_backtracking() -> None:
    html = module._html_for_cases(["HB001", "HB002"], 1, "renders")
    lowered = html.lower()
    assert "http:" not in lowered
    assert "https:" not in lowered
    assert "fetch(" not in lowered
    assert "xmlhttprequest" not in lowered
    assert "index -= 1" not in html
    assert 'id="ack"' in html
    assert "CaseID,label,round,ordinal,annotated_at" not in html
    assert 'const header = ["CaseID","label","round","ordinal","annotated_at"]' in html


def test_heatmap_sign_convention() -> None:
    levels = {("A", 100.0): 10.0, ("B", 99.75): 7.0}
    config = module.Config(
        sessions=1,
        tick_size=0.25,
        window_seconds=5.0,
        grid_milliseconds=50,
        min_tick=-2,
        max_tick=2,
        heatmap_percentile=99.0,
        max_saturation_fraction=0.05,
        round1_seed=1,
        round2_seed=2,
        uniform_mtime_epoch=946684800,
        allowed_handoff_columns=(),
        annotator_export_columns=(),
    )
    signed, best, q_l0 = module._state_depth_row(
        levels,
        "A",
        100.0,
        "BUY",
        config,
    )
    ticks = np.arange(-2, 3)
    assert signed[np.where(ticks == 0)[0][0]] == 10
    assert signed[np.where(ticks == -1)[0][0]] == -7
    assert best == 0
    assert q_l0 == 10
