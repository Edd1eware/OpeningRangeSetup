"""Synthetic tests for the F5 discovery primitives.

No test reads a label artifact, the feature matrix, or any file under
artifacts. Everything is generated in memory so the suite can run before the
single authorised join.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pre_lb_f5_discovery import (  # noqa: E402
    BENJAMINI_HOCHBERG_Q_MAX,
    FOLDS,
    MINIMUM_DELTA,
    PROBABILITY_FLOOR,
    RESOLVED_CLASSES,
    FoldPredictions,
    ProcessFail,
    balanced_multiclass_log_loss,
    benjamini_hochberg,
    circular_shift_labels,
    delta_from_predictions,
    encode_truth,
    fit_fold,
    model_feature_sets,
    out_of_fold_predictions,
    per_fold_deltas,
    primary_gates,
    resolved_class_presence,
    session_bootstrap,
    session_positions,
    train_fold_class_weights,
)


FAMILIES = {
    "baseline_detector_and_controls": [f"BLB_{i}" for i in range(11)],
    "baseline_price_history": [f"PX_{i}" for i in range(9)],
    "baseline_tape_history": [f"TAPE_{i}" for i in range(12)],
    "dom_top10_state": [f"DOM_S{i}" for i in range(8)],
    "dom_top10_dynamics": [
        f"DOM_D{i}_pre_{window}s" for window in (1, 5, 30) for i in range(4)
    ],
    "profile_f11": [f"PRF_{i}" for i in range(8)],
}


def synthetic_panel(
    sessions_count: int = 104,
    rows_per_session: int = 6,
    features: int = 5,
    signal: float = 0.0,
    seed: int = 7,
):
    """Build a balanced synthetic panel with an optional injected signal."""

    generator = np.random.default_rng(seed)
    session_order = [f"S{index:03d}" for index in range(1, sessions_count + 1)]
    sessions = np.repeat(np.array(session_order), rows_per_session)
    total = sessions.shape[0]
    truth = np.tile(np.arange(len(RESOLVED_CLASSES)), total // 3 + 1)[:total]
    noise = generator.normal(size=(total, features))
    if signal:
        noise[:, 0] += signal * truth
    event_ticks = np.tile(
        np.arange(rows_per_session, dtype=np.int64), sessions_count
    )
    return noise, truth, sessions, event_ticks, session_order


def test_bmll_weights_every_class_equally():
    """A rare class must count as much as a frequent one."""

    probabilities = np.array(
        [[0.9, 0.05, 0.05]] * 99 + [[0.1, 0.8, 0.1]] + [[0.2, 0.2, 0.6]]
    )
    truth = np.array([0] * 99 + [1] + [2])
    loss = balanced_multiclass_log_loss(probabilities, truth)
    expected = np.mean(
        [-np.log(0.9), -np.log(0.8), -np.log(0.6)]
    )
    assert loss == pytest.approx(expected)


def test_bmll_rejects_missing_class():
    probabilities = np.array([[0.5, 0.3, 0.2], [0.4, 0.4, 0.2]])
    truth = np.array([0, 0])
    with pytest.raises(ProcessFail):
        balanced_multiclass_log_loss(probabilities, truth)


def test_bmll_floor_prevents_infinity():
    probabilities = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    truth = np.array([0, 1, 2])
    loss = balanced_multiclass_log_loss(probabilities, truth)
    assert np.isfinite(loss)
    assert loss == pytest.approx(-np.log(PROBABILITY_FLOOR) * 2 / 3, rel=1e-6)


def test_class_weights_are_balanced_and_train_only():
    truth = np.array([0] * 60 + [1] * 30 + [2] * 10)
    weights = train_fold_class_weights(truth)
    assert weights[0] == pytest.approx(100 / (3 * 60))
    assert weights[1] == pytest.approx(100 / (3 * 30))
    assert weights[2] == pytest.approx(100 / (3 * 10))
    assert sum(weights[i] * (truth == i).sum() for i in range(3)) == pytest.approx(
        len(truth)
    )


def test_class_weights_reject_absent_class():
    with pytest.raises(ProcessFail):
        train_fold_class_weights(np.array([0, 0, 1, 1]))


def test_folds_never_train_on_future_sessions():
    """Every training position must be strictly below the test positions."""

    for fold in FOLDS:
        assert fold["train"][0] == 1
        assert fold["train"][1] < fold["test"][0]
        assert fold["test"][0] <= fold["test"][1]
    assert FOLDS[-1]["test"][1] == 104


def test_session_positions_are_one_based_and_ordered():
    positions = session_positions(["a", "b", "c"])
    assert positions == {"a": 1, "b": 2, "c": 3}


def test_out_of_fold_predictions_score_each_test_row_once():
    features, truth, sessions, _, order = synthetic_panel()
    folds = out_of_fold_predictions(features, truth, sessions, order)
    scored = np.concatenate([fold.row_index for fold in folds])
    assert scored.shape[0] == len(set(scored.tolist()))
    positions = session_positions(order)
    row_positions = np.array([positions[value] for value in sessions])
    expected = np.flatnonzero((row_positions >= 41) & (row_positions <= 104))
    assert sorted(scored.tolist()) == sorted(expected.tolist())


def test_probabilities_are_valid_distributions():
    features, truth, sessions, _, order = synthetic_panel()
    folds = out_of_fold_predictions(features, truth, sessions, order)
    for fold in folds:
        assert np.all(fold.probabilities >= 0.0)
        assert np.allclose(fold.probabilities.sum(axis=1), 1.0)


def test_scaler_is_fit_on_train_only():
    """Shifting test rows must not move the fitted training statistics."""

    generator = np.random.default_rng(3)
    train = generator.normal(size=(90, 4))
    truth = np.tile(np.arange(3), 30)
    test = generator.normal(size=(20, 4))
    first = fit_fold(train, truth, test)
    second = fit_fold(train, truth, test + 100.0)
    assert not np.allclose(first, second)
    third = fit_fold(train, truth, test)
    assert np.allclose(first, third)


def test_delta_is_zero_for_identical_models():
    features, truth, sessions, _, order = synthetic_panel()
    folds = out_of_fold_predictions(features, truth, sessions, order)
    assert delta_from_predictions(folds, folds) == pytest.approx(0.0)


def test_delta_positive_when_augmented_model_sees_signal():
    features, truth, sessions, _, order = synthetic_panel(signal=1.5)
    baseline = out_of_fold_predictions(features[:, 1:], truth, sessions, order)
    augmented = out_of_fold_predictions(features, truth, sessions, order)
    assert delta_from_predictions(baseline, augmented) > 0.0


def test_delta_rejects_mismatched_row_sets():
    features, truth, sessions, _, order = synthetic_panel()
    folds = out_of_fold_predictions(features, truth, sessions, order)
    tampered = [
        FoldPredictions(
            fold=fold.fold,
            row_index=fold.row_index,
            probabilities=fold.probabilities,
            truth=(fold.truth + 1) % 3,
        )
        for fold in folds
    ]
    with pytest.raises(ProcessFail):
        delta_from_predictions(folds, tampered)


def test_per_fold_deltas_cover_all_four_folds():
    features, truth, sessions, _, order = synthetic_panel(signal=1.0)
    baseline = out_of_fold_predictions(features[:, 1:], truth, sessions, order)
    augmented = out_of_fold_predictions(features, truth, sessions, order)
    deltas = per_fold_deltas(baseline, augmented)
    assert sorted(deltas) == [1, 2, 3, 4]


def test_circular_shift_preserves_label_multiset_per_session():
    truth = np.array([0, 1, 2, 0, 1, 2])
    sessions = np.array(["a", "a", "a", "b", "b", "b"])
    ticks = np.array([1, 2, 3, 1, 2, 3], dtype=np.int64)
    generator = np.random.default_rng(11)
    shifted = circular_shift_labels(truth, sessions, ticks, generator)
    for session in ("a", "b"):
        rows = sessions == session
        assert sorted(shifted[rows].tolist()) == sorted(truth[rows].tolist())


def test_circular_shift_offset_is_never_zero():
    """A rotation that returns the original vector would not break alignment."""

    truth = np.array([0, 1, 2, 0, 1, 2, 0, 1])
    sessions = np.array(["a"] * 8)
    ticks = np.arange(8, dtype=np.int64)
    for seed in range(40):
        generator = np.random.default_rng(seed)
        shifted = circular_shift_labels(truth, sessions, ticks, generator)
        assert not np.array_equal(shifted, truth)


def test_circular_shift_leaves_single_event_sessions_untouched():
    truth = np.array([0, 1, 2])
    sessions = np.array(["a", "b", "c"])
    ticks = np.array([1, 1, 1], dtype=np.int64)
    generator = np.random.default_rng(5)
    shifted = circular_shift_labels(truth, sessions, ticks, generator)
    assert np.array_equal(shifted, truth)


def test_circular_shift_orders_by_event_time_not_row_order():
    truth = np.array([0, 1, 2])
    sessions = np.array(["a", "a", "a"])
    ticks = np.array([30, 10, 20], dtype=np.int64)
    generator = np.random.default_rng(2)
    shifted = circular_shift_labels(truth, sessions, ticks, generator)
    assert sorted(shifted.tolist()) == [0, 1, 2]


def test_bootstrap_is_deterministic_under_the_frozen_seed():
    features, truth, sessions, _, order = synthetic_panel(signal=1.0)
    baseline = out_of_fold_predictions(features[:, 1:], truth, sessions, order)
    augmented = out_of_fold_predictions(features, truth, sessions, order)
    rows, baseline_probabilities, scored_truth = (
        np.concatenate([fold.row_index for fold in baseline]),
        np.concatenate([fold.probabilities for fold in baseline]),
        np.concatenate([fold.truth for fold in baseline]),
    )
    augmented_probabilities = np.concatenate(
        [fold.probabilities for fold in augmented]
    )
    scored_sessions = sessions[rows]
    first = session_bootstrap(
        baseline_probabilities,
        augmented_probabilities,
        scored_truth,
        scored_sessions,
        repetitions=50,
    )
    second = session_bootstrap(
        baseline_probabilities,
        augmented_probabilities,
        scored_truth,
        scored_sessions,
        repetitions=50,
    )
    assert first == second
    assert first["lower"] <= first["mean"] <= first["upper"]


def test_bootstrap_resamples_sessions_not_rows():
    """Rows of one session must move together, so a session appears 0 or n times."""

    features, truth, sessions, _, order = synthetic_panel(
        sessions_count=104, rows_per_session=3
    )
    folds = out_of_fold_predictions(features, truth, sessions, order)
    rows = np.concatenate([fold.row_index for fold in folds])
    probabilities = np.concatenate([fold.probabilities for fold in folds])
    scored_truth = np.concatenate([fold.truth for fold in folds])
    result = session_bootstrap(
        probabilities,
        probabilities,
        scored_truth,
        sessions[rows],
        repetitions=25,
    )
    assert result["mean"] == pytest.approx(0.0)
    assert result["lower"] == pytest.approx(0.0)
    assert result["upper"] == pytest.approx(0.0)


def test_benjamini_hochberg_matches_manual_step_up():
    """n=5, q=0.10 gives thresholds 0.02 0.04 0.06 0.08 0.10.

    Ranks 1 to 3 clear their thresholds, so the step-up rejects three.
    """

    p_values = [0.001, 0.02, 0.04, 0.2, 0.5]
    rejected = benjamini_hochberg(p_values, q_max=0.10)
    assert rejected == [True, True, True, False, False]


def test_benjamini_hochberg_rejects_below_threshold_after_larger_rank():
    """A small p must be rejected when a later rank clears the line."""

    p_values = [0.019, 0.02]
    assert benjamini_hochberg(p_values, q_max=0.10) == [True, True]


def test_benjamini_hochberg_handles_empty_input():
    assert benjamini_hochberg([]) == []
    assert BENJAMINI_HOCHBERG_Q_MAX == 0.10


def test_primary_gates_require_every_gate():
    good = {
        "delta": 0.05,
        "bootstrap": {"lower": 0.01},
        "permutation": {"p_value": 0.01},
        "fold_deltas": {1: 0.1, 2: 0.1, 3: 0.1, 4: -0.1},
        "buy_delta": 0.02,
        "sell_delta": 0.02,
    }
    passing = primary_gates(**good)
    assert passing["all_primary_gates_pass"] is True
    assert passing["terminal_verdict"] == "DISCOVERY_ONLY_SIGNAL"

    for key, broken in (
        ("delta", MINIMUM_DELTA - 0.001),
        ("bootstrap", {"lower": 0.0}),
        ("permutation", {"p_value": 0.051}),
        ("fold_deltas", {1: 0.1, 2: 0.1, 3: -0.1, 4: -0.1}),
        ("buy_delta", 0.0),
        ("sell_delta", -0.01),
    ):
        payload = dict(good)
        payload[key] = broken
        result = primary_gates(**payload)
        assert result["all_primary_gates_pass"] is False
        assert result["terminal_verdict"] == "NO_DISCOVERY_SIGNAL_CLOSE_LINE"


def test_encode_truth_rejects_ambiguous():
    with pytest.raises(ProcessFail):
        encode_truth(["CONTINUATION", "AMBIGUOUS"])


def test_encode_truth_uses_frozen_class_order():
    encoded = encode_truth(list(RESOLVED_CLASSES))
    assert encoded.tolist() == [0, 1, 2]


def test_resolved_class_presence_flags_missing_class():
    features, truth, sessions, _, order = synthetic_panel()
    clean = resolved_class_presence(truth, sessions, order)
    assert clean["process_fail"] is False
    degenerate = np.where(truth == 2, 0, truth)
    broken = resolved_class_presence(degenerate, sessions, order)
    assert broken["process_fail"] is True


def test_model_feature_sets_are_exactly_as_declared():
    sets = model_feature_sets(FAMILIES)
    assert len(sets["M0_BASE"]) == 32
    assert len(sets["M_DOM_W1"]) == 44
    assert len(sets["M_PRF"]) == 40
    assert len(sets["M_ALL_W1"]) == 52
    assert set(sets["M0_BASE"]).issubset(set(sets["M_ALL_W1"]))
    assert all(
        name.endswith("_pre_1s")
        for name in sets["M_ALL_W1"]
        if name.startswith("DOM_D")
    )


def test_amended_model_sets_follow_option_a():
    """GEMINI_F5_MODEL_SET_AMENDMENT: APPROVE_A, substitution not accumulation."""

    sets = model_feature_sets(FAMILIES)
    assert len(sets["B_LB"]) == 11
    assert len(sets["B_PRICE"]) == 9
    assert len(sets["B_PRICE_PLUS_PRF"]) == 17
    assert len(sets["M_ALL_W5"]) == 52
    assert len(sets["M_ALL_W30"]) == 52


def test_window_ladder_swaps_the_window_and_keeps_capacity_constant():
    """W1, W5 and W30 variants must differ only in the DOM dynamics window."""

    sets = model_feature_sets(FAMILIES)
    sizes = {len(sets[name]) for name in ("M_ALL_W1", "M_ALL_W5", "M_ALL_W30")}
    assert sizes == {52}
    for name, window in (
        ("M_ALL_W1", "_pre_1s"),
        ("M_ALL_W5", "_pre_5s"),
        ("M_ALL_W30", "_pre_30s"),
    ):
        dom_dynamics = [
            feature for feature in sets[name] if feature.startswith("DOM_D")
        ]
        assert len(dom_dynamics) == 4
        assert all(feature.endswith(window) for feature in dom_dynamics)
    shared = set(sets["M_ALL_W1"]) & set(sets["M_ALL_W5"]) & set(sets["M_ALL_W30"])
    assert len(shared) == 48


def test_price_plus_profile_extends_the_price_baseline_exactly():
    sets = model_feature_sets(FAMILIES)
    assert set(sets["B_PRICE"]).issubset(set(sets["B_PRICE_PLUS_PRF"]))
    added = set(sets["B_PRICE_PLUS_PRF"]) - set(sets["B_PRICE"])
    assert added == set(FAMILIES["profile_f11"])


def test_module_does_not_import_labels_or_artifacts():
    """Executable code must not reach for labels or artifacts.

    Docstrings are stripped first, so prose describing the constraint cannot
    satisfy or break the check.
    """

    import ast

    source = (ROOT / "src" / "pre_lb_f5_discovery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body[0].value.value = ""
    stripped = ast.unparse(tree)
    for forbidden in (
        "regime_discovery_labels",
        "artifacts",
        "read_parquet",
        "read_csv",
        "validation",
        "holdout",
        "open(",
    ):
        assert forbidden not in stripped

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported <= {
        "__future__",
        "dataclasses",
        "typing",
        "numpy",
        "sklearn.linear_model",
        "sklearn.preprocessing",
    }
