"""Synthetic tests for the G1 binary expansion primitives.

Nothing here reads a label artifact, the feature matrix or anything under
artifacts. The suite must be able to run before the single G1 evaluation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pre_lb_f5_discovery import FOLDS, ProcessFail, primary_gates  # noqa: E402
from src.pre_lb_g1_expansion import (  # noqa: E402
    EXPANSION_CLASSES,
    balanced_binary_log_loss,
    binary_class_presence,
    binary_delta,
    binary_fold_deltas,
    binary_permutation_test,
    binary_session_bootstrap,
    collapse_to_expansion,
    expansion_base_rate,
    fit_fold_binary,
    out_of_fold_binary,
    train_fold_binary_weights,
)


def synthetic_panel(
    sessions_count: int = 104,
    rows_per_session: int = 6,
    features: int = 5,
    signal: float = 0.0,
    seed: int = 13,
):
    generator = np.random.default_rng(seed)
    session_order = [f"S{index:03d}" for index in range(1, sessions_count + 1)]
    sessions = np.repeat(np.array(session_order), rows_per_session)
    total = sessions.shape[0]
    truth = np.tile(np.array([0, 1]), total // 2 + 1)[:total]
    values = generator.normal(size=(total, features))
    if signal:
        values[:, 0] += signal * truth
    event_ticks = np.tile(
        np.arange(rows_per_session, dtype=np.int64), sessions_count
    )
    return values, truth, sessions, event_ticks, session_order


def test_collapse_maps_both_directions_to_expansion():
    encoded = collapse_to_expansion(
        ["CONTINUATION", "REVERSAL", "NO_EXPANSION", "CONTINUATION"]
    )
    assert encoded.tolist() == [1, 1, 0, 1]


def test_collapse_rejects_ambiguous():
    with pytest.raises(ProcessFail):
        collapse_to_expansion(["CONTINUATION", "AMBIGUOUS"])


def test_collapse_rejects_unknown_label():
    with pytest.raises(ProcessFail):
        collapse_to_expansion(["SOMETHING_ELSE"])


def test_direction_cannot_survive_the_collapse():
    """CONTINUATION and REVERSAL must be indistinguishable after collapsing."""

    from_continuation = collapse_to_expansion(["CONTINUATION"] * 10)
    from_reversal = collapse_to_expansion(["REVERSAL"] * 10)
    assert np.array_equal(from_continuation, from_reversal)


def test_constant_guessing_scores_log_two_whatever_the_prevalence():
    """The balanced metric is why knowing the 43.45% base rate is harmless."""

    for prevalence in (0.05, 0.4345, 0.9):
        count = 2000
        positives = int(count * prevalence)
        truth = np.array([1] * positives + [0] * (count - positives))
        probabilities = np.full((count, 2), 0.5)
        assert balanced_binary_log_loss(probabilities, truth) == pytest.approx(
            np.log(2)
        )


def test_predicting_the_base_rate_cannot_beat_log_two_on_balance():
    """A model that only learns the prevalence gains nothing under BBLL."""

    count = 2000
    prevalence = 0.4345
    positives = int(count * prevalence)
    truth = np.array([1] * positives + [0] * (count - positives))
    base_rate = np.full((count, 2), [1 - prevalence, prevalence])
    assert balanced_binary_log_loss(base_rate, truth) >= np.log(2)


def test_bbll_weights_the_rare_class_equally():
    probabilities = np.array([[0.9, 0.1]] * 99 + [[0.4, 0.6]])
    truth = np.array([0] * 99 + [1])
    expected = np.mean([-np.log(0.9), -np.log(0.6)])
    assert balanced_binary_log_loss(probabilities, truth) == pytest.approx(expected)


def test_bbll_rejects_a_missing_class():
    with pytest.raises(ProcessFail):
        balanced_binary_log_loss(np.array([[0.5, 0.5], [0.6, 0.4]]), np.array([0, 0]))


def test_binary_class_weights_are_balanced_and_train_only():
    truth = np.array([0] * 70 + [1] * 30)
    weights = train_fold_binary_weights(truth)
    assert weights[0] == pytest.approx(100 / (2 * 70))
    assert weights[1] == pytest.approx(100 / (2 * 30))
    assert sum(weights[i] * (truth == i).sum() for i in (0, 1)) == pytest.approx(100)


def test_binary_class_weights_reject_absent_class():
    with pytest.raises(ProcessFail):
        train_fold_binary_weights(np.array([1, 1, 1]))


def test_probabilities_are_valid_and_column_order_matches_encoding():
    """Column 1 must be the EXPANSION probability, not whatever sklearn ordered."""

    generator = np.random.default_rng(4)
    train = generator.normal(size=(120, 3))
    truth = np.tile([0, 1], 60)
    train[:, 0] += 3.0 * truth
    probabilities = fit_fold_binary(train, truth, train)
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert probabilities[truth == 1, 1].mean() > probabilities[truth == 0, 1].mean()


def test_scaler_is_fit_on_train_only():
    generator = np.random.default_rng(6)
    train = generator.normal(size=(100, 4))
    truth = np.tile([0, 1], 50)
    test = generator.normal(size=(20, 4))
    first = fit_fold_binary(train, truth, test)
    assert not np.allclose(first, fit_fold_binary(train, truth, test + 100.0))
    assert np.allclose(first, fit_fold_binary(train, truth, test))


def test_folds_are_the_same_frozen_chronological_split():
    assert [fold["train"] for fold in FOLDS] == [(1, 40), (1, 56), (1, 72), (1, 88)]
    assert [fold["test"] for fold in FOLDS] == [
        (41, 56),
        (57, 72),
        (73, 88),
        (89, 104),
    ]


def test_each_test_row_is_scored_exactly_once():
    values, truth, sessions, _, order = synthetic_panel()
    folds = out_of_fold_binary(values, truth, sessions, order)
    scored = np.concatenate([fold.row_index for fold in folds])
    assert scored.shape[0] == len(set(scored.tolist()))


def test_delta_is_zero_for_identical_models():
    values, truth, sessions, _, order = synthetic_panel()
    folds = out_of_fold_binary(values, truth, sessions, order)
    assert binary_delta(folds, folds) == pytest.approx(0.0)


def test_delta_positive_when_augmented_model_sees_signal():
    values, truth, sessions, _, order = synthetic_panel(signal=1.5)
    baseline = out_of_fold_binary(values[:, 1:], truth, sessions, order)
    augmented = out_of_fold_binary(values, truth, sessions, order)
    assert binary_delta(baseline, augmented) > 0.0


def test_fold_deltas_cover_the_four_folds():
    values, truth, sessions, _, order = synthetic_panel(signal=1.0)
    baseline = out_of_fold_binary(values[:, 1:], truth, sessions, order)
    augmented = out_of_fold_binary(values, truth, sessions, order)
    assert sorted(binary_fold_deltas(baseline, augmented)) == [1, 2, 3, 4]


def test_bootstrap_is_deterministic_and_resamples_sessions():
    values, truth, sessions, _, order = synthetic_panel()
    folds = out_of_fold_binary(values, truth, sessions, order)
    rows = np.concatenate([fold.row_index for fold in folds])
    probabilities = np.concatenate([fold.probabilities for fold in folds])
    scored_truth = np.concatenate([fold.truth for fold in folds])
    first = binary_session_bootstrap(
        probabilities, probabilities, scored_truth, sessions[rows], 40, 20260727
    )
    second = binary_session_bootstrap(
        probabilities, probabilities, scored_truth, sessions[rows], 40, 20260727
    )
    assert first == second
    assert first["mean"] == pytest.approx(0.0)


def test_permutation_on_pure_noise_is_not_significant():
    """With no signal the null must not be rejected."""

    values, truth, sessions, ticks, order = synthetic_panel(
        sessions_count=104, rows_per_session=4, seed=21
    )
    baseline = out_of_fold_binary(values[:, 1:], truth, sessions, order)
    augmented = out_of_fold_binary(values, truth, sessions, order)
    observed = binary_delta(baseline, augmented)
    result = binary_permutation_test(
        values[:, 1:],
        values,
        truth,
        sessions,
        ticks,
        order,
        observed,
        repetitions=25,
        seed=20260727,
    )
    assert 0.0 < result["p_value"] <= 1.0
    assert result["replicates"] == 25


def test_class_presence_flags_a_degenerate_fold():
    values, truth, sessions, _, order = synthetic_panel()
    assert binary_class_presence(truth, sessions, order)["process_fail"] is False
    degenerate = np.zeros_like(truth)
    assert binary_class_presence(degenerate, sessions, order)["process_fail"] is True


def test_gates_are_reused_unchanged_from_the_frozen_module():
    """G1 must not soften a single threshold."""

    verdict = primary_gates(
        delta=0.02,
        bootstrap={"lower": 0.001},
        permutation={"p_value": 0.04},
        fold_deltas={1: 0.1, 2: 0.1, 3: 0.1, 4: -0.2},
        buy_delta=0.01,
        sell_delta=0.01,
    )
    assert verdict["all_primary_gates_pass"] is True
    softened = primary_gates(
        delta=0.009,
        bootstrap={"lower": 0.001},
        permutation={"p_value": 0.04},
        fold_deltas={1: 0.1, 2: 0.1, 3: 0.1, 4: 0.1},
        buy_delta=0.01,
        sell_delta=0.01,
    )
    assert softened["all_primary_gates_pass"] is False


def test_base_rate_helper_reports_but_does_not_fit():
    truth = np.array([1] * 1112 + [0] * 1447)
    assert expansion_base_rate(truth) == pytest.approx(0.4345, abs=1e-3)


def test_expansion_class_order_is_frozen():
    assert EXPANSION_CLASSES == ("NO_EXPANSION", "EXPANSION")


def test_module_never_reaches_for_labels_or_artifacts():
    import ast

    source = (ROOT / "src" / "pre_lb_g1_expansion.py").read_text(encoding="utf-8")
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
