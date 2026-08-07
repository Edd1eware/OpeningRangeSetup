"""G1 expansion primitives: does the pre-LB book predict expansion, not direction.

The F5 module is frozen and hashed, so nothing here modifies it. Everything that
is genuinely class-agnostic is imported from F5 and reused unchanged: the fold
definitions, the session position map, the within-session circular shift, the
Benjamini-Hochberg step-up, the gate logic and the prediction container. Only
the pieces that hard-code three classes are re-expressed for two.

Like the F5 module, this file never reads a label file and never touches the
artifacts directory. It receives arrays and returns numbers.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.pre_lb_f5_discovery import (
    FOLDS,
    PROBABILITY_FLOOR,
    FoldPredictions,
    ProcessFail,
    session_positions,
    stack_folds,
)

EXPANSION_CLASSES = ("NO_EXPANSION", "EXPANSION")
DIRECTIONAL_CLASSES = ("CONTINUATION", "REVERSAL")
ABSTENTION_CLASS = "AMBIGUOUS"


def collapse_to_expansion(labels: Sequence[str]) -> np.ndarray:
    """Map the frozen resolved classes onto the binary expansion target.

    CONTINUATION and REVERSAL both mean the price travelled 16 ticks inside the
    horizon, so both are EXPANSION. The mapping is deterministic and fixed by
    the G1 preregistration; direction is discarded and can never re-enter.
    """

    encoded = np.empty(len(labels), dtype=np.int64)
    for position, value in enumerate(labels):
        if value in DIRECTIONAL_CLASSES:
            encoded[position] = 1
        elif value == EXPANSION_CLASSES[0]:
            encoded[position] = 0
        else:
            raise ProcessFail(f"unresolved label reached the model: {value}")
    return encoded


def balanced_binary_log_loss(
    probabilities: np.ndarray,
    truth: np.ndarray,
) -> float:
    """Mean over the two classes of the mean negative log probability.

    Constant guessing scores log(2) whatever the prevalence, so the 43.45%
    expansion base rate cannot buy a positive delta.
    """

    if probabilities.shape[0] != truth.shape[0]:
        raise ValueError("probability/truth length mismatch")
    if probabilities.shape[1] != len(EXPANSION_CLASSES):
        raise ValueError("probability matrix must have one column per class")

    losses = []
    for index in range(len(EXPANSION_CLASSES)):
        rows = truth == index
        if not rows.any():
            raise ProcessFail(
                f"class {EXPANSION_CLASSES[index]} absent from the scored set"
            )
        picked = probabilities[rows, index]
        losses.append(float(np.mean(-np.log(np.maximum(picked, PROBABILITY_FLOOR)))))
    return float(np.mean(losses))


def train_fold_binary_weights(train_truth: np.ndarray) -> dict[int, float]:
    """n_train / (2 * n_train_class), computed on the training fold only."""

    total = int(train_truth.shape[0])
    weights: dict[int, float] = {}
    for index in range(len(EXPANSION_CLASSES)):
        count = int((train_truth == index).sum())
        if count == 0:
            raise ProcessFail(
                f"class {EXPANSION_CLASSES[index]} absent from a train fold"
            )
        weights[index] = total / (len(EXPANSION_CLASSES) * count)
    return weights


def fit_fold_binary(
    train_features: np.ndarray,
    train_truth: np.ndarray,
    test_features: np.ndarray,
) -> np.ndarray:
    """Fit the frozen pipeline in its binomial form and score the test rows."""

    scaler = StandardScaler()
    scaled_train = scaler.fit_transform(train_features)
    scaled_test = scaler.transform(test_features)
    model = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        max_iter=10000,
        class_weight=train_fold_binary_weights(train_truth),
    )
    model.fit(scaled_train, train_truth)
    predicted = model.predict_proba(scaled_test)
    probabilities = np.zeros((scaled_test.shape[0], len(EXPANSION_CLASSES)))
    for column, class_index in enumerate(model.classes_):
        probabilities[:, int(class_index)] = predicted[:, column]
    return probabilities


def out_of_fold_binary(
    features: np.ndarray,
    truth: np.ndarray,
    sessions: np.ndarray,
    session_order: Sequence[str],
) -> list[FoldPredictions]:
    """Score every test fold using only sessions earlier in the frozen order."""

    positions = session_positions(session_order)
    row_positions = np.array([positions[value] for value in sessions])
    results: list[FoldPredictions] = []
    for fold in FOLDS:
        train_low, train_high = fold["train"]
        test_low, test_high = fold["test"]
        train_rows = (row_positions >= train_low) & (row_positions <= train_high)
        test_rows = (row_positions >= test_low) & (row_positions <= test_high)
        if not train_rows.any() or not test_rows.any():
            raise ProcessFail(f"fold {fold['fold']} has an empty train or test side")
        results.append(
            FoldPredictions(
                fold=int(fold["fold"]),
                row_index=np.flatnonzero(test_rows),
                probabilities=fit_fold_binary(
                    features[train_rows], truth[train_rows], features[test_rows]
                ),
                truth=truth[test_rows],
            )
        )
    return results


def binary_delta(
    baseline: Sequence[FoldPredictions],
    augmented: Sequence[FoldPredictions],
) -> float:
    """Delta = BBLL(baseline) - BBLL(augmented). Positive means improvement."""

    _, baseline_probabilities, baseline_truth = stack_folds(baseline)
    _, augmented_probabilities, augmented_truth = stack_folds(augmented)
    if not np.array_equal(baseline_truth, augmented_truth):
        raise ProcessFail("baseline and augmented models scored different rows")
    return balanced_binary_log_loss(
        baseline_probabilities, baseline_truth
    ) - balanced_binary_log_loss(augmented_probabilities, augmented_truth)


def binary_fold_deltas(
    baseline: Sequence[FoldPredictions],
    augmented: Sequence[FoldPredictions],
) -> dict[int, float]:
    deltas: dict[int, float] = {}
    for base_fold, augmented_fold in zip(baseline, augmented):
        if base_fold.fold != augmented_fold.fold:
            raise ProcessFail("fold order mismatch")
        deltas[base_fold.fold] = balanced_binary_log_loss(
            base_fold.probabilities, base_fold.truth
        ) - balanced_binary_log_loss(
            augmented_fold.probabilities, augmented_fold.truth
        )
    return deltas


def binary_session_bootstrap(
    baseline_probabilities: np.ndarray,
    augmented_probabilities: np.ndarray,
    truth: np.ndarray,
    sessions: np.ndarray,
    repetitions: int,
    seed: int,
    confidence: float = 0.95,
) -> dict[str, float]:
    """Resample whole sessions with replacement and re-score the delta."""

    unique_sessions = np.unique(sessions)
    rows_by_session = {
        session: np.flatnonzero(sessions == session) for session in unique_sessions
    }
    generator = np.random.default_rng(seed)
    deltas: list[float] = []
    skipped = 0
    for _ in range(repetitions):
        drawn = generator.choice(
            unique_sessions, size=unique_sessions.shape[0], replace=True
        )
        rows = np.concatenate([rows_by_session[session] for session in drawn])
        sample_truth = truth[rows]
        if any(
            not (sample_truth == index).any()
            for index in range(len(EXPANSION_CLASSES))
        ):
            skipped += 1
            continue
        deltas.append(
            balanced_binary_log_loss(baseline_probabilities[rows], sample_truth)
            - balanced_binary_log_loss(augmented_probabilities[rows], sample_truth)
        )
    if not deltas:
        raise ProcessFail("every bootstrap replicate lacked a class")
    values = np.array(deltas)
    lower_quantile = (1.0 - confidence) / 2.0
    return {
        "lower": float(np.quantile(values, lower_quantile)),
        "upper": float(np.quantile(values, 1.0 - lower_quantile)),
        "mean": float(values.mean()),
        "replicates": int(values.shape[0]),
        "skipped_replicates": int(skipped),
    }


def binary_permutation_test(
    features_baseline: np.ndarray,
    features_augmented: np.ndarray,
    truth: np.ndarray,
    sessions: np.ndarray,
    event_ticks: np.ndarray,
    session_order: Sequence[str],
    observed_delta: float,
    repetitions: int,
    seed: int,
    progress=None,
) -> dict[str, float]:
    """Full refit permutation under within-session non-zero circular shifts."""

    from src.pre_lb_f5_discovery import circular_shift_labels

    generator = np.random.default_rng(seed)
    at_least_as_extreme = 0
    completed = 0
    for repetition in range(repetitions):
        shifted = circular_shift_labels(truth, sessions, event_ticks, generator)
        try:
            null_delta = binary_delta(
                out_of_fold_binary(
                    features_baseline, shifted, sessions, session_order
                ),
                out_of_fold_binary(
                    features_augmented, shifted, sessions, session_order
                ),
            )
        except ProcessFail:
            continue
        completed += 1
        if null_delta >= observed_delta:
            at_least_as_extreme += 1
        if progress is not None:
            progress(repetition + 1, repetitions)
    if completed == 0:
        raise ProcessFail("no permutation replicate could be refit")
    return {
        "p_value": float((at_least_as_extreme + 1) / (completed + 1)),
        "replicates": int(completed),
        "at_least_as_extreme": int(at_least_as_extreme),
    }


def binary_class_presence(
    truth: np.ndarray,
    sessions: np.ndarray,
    session_order: Sequence[str],
) -> dict[str, object]:
    """Declare PROCESS_FAIL before fitting if any fold lacks a class."""

    positions = session_positions(session_order)
    row_positions = np.array([positions[value] for value in sessions])
    report: dict[str, object] = {"folds": {}, "process_fail": False}
    for fold in FOLDS:
        train_low, train_high = fold["train"]
        test_low, test_high = fold["test"]
        train_rows = (row_positions >= train_low) & (row_positions <= train_high)
        test_rows = (row_positions >= test_low) & (row_positions <= test_high)
        complete = len(set(truth[train_rows].tolist())) == len(
            EXPANSION_CLASSES
        ) and len(set(truth[test_rows].tolist())) == len(EXPANSION_CLASSES)
        report["folds"][int(fold["fold"])] = {
            "train_rows": int(train_rows.sum()),
            "test_rows": int(test_rows.sum()),
            "complete": bool(complete),
        }
        if not complete:
            report["process_fail"] = True
    if len(set(truth.tolist())) != len(EXPANSION_CLASSES):
        report["process_fail"] = True
    return report


def expansion_base_rate(truth: np.ndarray) -> float:
    """Share of EXPANSION rows, reported for the audit, never used to fit."""

    return float((truth == 1).mean())
