"""F5 discovery evaluation primitives for the pre-LB precursor line.

This module is deliberately outcome-agnostic at import time. It never reads a
label file, never touches the artifacts directory and never opens validation or
holdout. Labels arrive only as arrays passed in by the runner, which performs
the single authorised join.

Every routine here is deterministic given its inputs and the frozen seeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


RESOLVED_CLASSES = ("CONTINUATION", "REVERSAL", "NO_EXPANSION")
ABSTENTION_CLASS = "AMBIGUOUS"
BOOTSTRAP_SEED = 20260727
PERMUTATION_SEED = 20260727
BOOTSTRAP_REPETITIONS = 2000
PERMUTATION_REPETITIONS = 1000
BOOTSTRAP_CI = 0.95
MINIMUM_DELTA = 0.01
POSITIVE_FOLDS_MINIMUM = 3
PERMUTATION_P_MAX = 0.05
BENJAMINI_HOCHBERG_Q_MAX = 0.10
PROBABILITY_FLOOR = 1e-15

FOLDS = (
    {"fold": 1, "train": (1, 40), "test": (41, 56)},
    {"fold": 2, "train": (1, 56), "test": (57, 72)},
    {"fold": 3, "train": (1, 72), "test": (73, 88)},
    {"fold": 4, "train": (1, 88), "test": (89, 104)},
)


class ProcessFail(RuntimeError):
    """Raised when the frozen protocol cannot be executed as declared."""


@dataclass(frozen=True)
class FoldPredictions:
    fold: int
    row_index: np.ndarray
    probabilities: np.ndarray
    truth: np.ndarray


def model_feature_sets(
    families: Mapping[str, Sequence[str]],
) -> dict[str, list[str]]:
    """Return the feature composition of every declared model.

    B_LB, B_PRICE, M_ALL_W5 and M_ALL_W30 were named in the preregistration
    without a composition. The gap was resolved before any label was opened by
    the substitution amendment, verdict GEMINI_F5_MODEL_SET_AMENDMENT:
    APPROVE_A: the baselines map to their catalog families, and the W5 and W30
    variants swap the DOM dynamics window instead of accumulating it, so model
    capacity stays at 52 features and the ladder isolates window horizon rather
    than feature count.
    """

    detector = list(families["baseline_detector_and_controls"])
    price = list(families["baseline_price_history"])
    tape = list(families["baseline_tape_history"])
    dom_state = list(families["dom_top10_state"])
    dom_dynamics = list(families["dom_top10_dynamics"])
    profile = list(families["profile_f11"])
    dom_by_window = {
        window: [
            name for name in dom_dynamics if name.endswith(f"_pre_{window}s")
        ]
        for window in (1, 5, 30)
    }

    base = detector + price + tape
    return {
        "B_LB": detector,
        "B_PRICE": price,
        "B_PRICE_PLUS_PRF": price + profile,
        "M0_BASE": base,
        "M_DOM_W1": base + dom_state + dom_by_window[1],
        "M_PRF": base + profile,
        "M_ALL_W1": base + dom_state + dom_by_window[1] + profile,
        "M_ALL_W5": base + dom_state + dom_by_window[5] + profile,
        "M_ALL_W30": base + dom_state + dom_by_window[30] + profile,
    }


def balanced_multiclass_log_loss(
    probabilities: np.ndarray,
    truth: np.ndarray,
) -> float:
    """Mean over classes of the mean negative log probability within class.

    Every resolved class contributes equally regardless of its frequency, so a
    model cannot win by exploiting class imbalance.
    """

    if probabilities.shape[0] != truth.shape[0]:
        raise ValueError("probability/truth length mismatch")
    if probabilities.shape[1] != len(RESOLVED_CLASSES):
        raise ValueError("probability matrix must have one column per class")

    losses = []
    for index in range(len(RESOLVED_CLASSES)):
        rows = truth == index
        if not rows.any():
            raise ProcessFail(
                f"resolved class {RESOLVED_CLASSES[index]} absent from scored set"
            )
        picked = probabilities[rows, index]
        losses.append(float(np.mean(-np.log(np.maximum(picked, PROBABILITY_FLOOR)))))
    return float(np.mean(losses))


def train_fold_class_weights(train_truth: np.ndarray) -> dict[int, float]:
    """n_train / (3 * n_train_class), computed on the training fold only."""

    total = int(train_truth.shape[0])
    weights: dict[int, float] = {}
    for index in range(len(RESOLVED_CLASSES)):
        count = int((train_truth == index).sum())
        if count == 0:
            raise ProcessFail(
                f"resolved class {RESOLVED_CLASSES[index]} absent from a train fold"
            )
        weights[index] = total / (len(RESOLVED_CLASSES) * count)
    return weights


def fit_fold(
    train_features: np.ndarray,
    train_truth: np.ndarray,
    test_features: np.ndarray,
) -> np.ndarray:
    """Fit the single frozen pipeline on one fold and score its test rows."""

    scaler = StandardScaler()
    scaled_train = scaler.fit_transform(train_features)
    scaled_test = scaler.transform(test_features)
    model = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        max_iter=10000,
        class_weight=train_fold_class_weights(train_truth),
    )
    model.fit(scaled_train, train_truth)
    probabilities = np.zeros((scaled_test.shape[0], len(RESOLVED_CLASSES)))
    for column, class_index in enumerate(model.classes_):
        probabilities[:, int(class_index)] = model.predict_proba(scaled_test)[
            :, column
        ]
    return probabilities


def session_positions(session_order: Sequence[str]) -> dict[str, int]:
    """Map each session to its 1-based chronological position."""

    return {session: index for index, session in enumerate(session_order, start=1)}


def out_of_fold_predictions(
    features: np.ndarray,
    truth: np.ndarray,
    sessions: np.ndarray,
    session_order: Sequence[str],
) -> list[FoldPredictions]:
    """Score every test fold using only sessions strictly earlier in the order."""

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
        probabilities = fit_fold(
            features[train_rows],
            truth[train_rows],
            features[test_rows],
        )
        results.append(
            FoldPredictions(
                fold=int(fold["fold"]),
                row_index=np.flatnonzero(test_rows),
                probabilities=probabilities,
                truth=truth[test_rows],
            )
        )
    return results


def stack_folds(
    folds: Sequence[FoldPredictions],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Concatenate fold predictions into a single out-of-fold set."""

    order = np.concatenate([fold.row_index for fold in folds])
    probabilities = np.concatenate([fold.probabilities for fold in folds])
    truth = np.concatenate([fold.truth for fold in folds])
    return order, probabilities, truth


def delta_from_predictions(
    baseline: Sequence[FoldPredictions],
    augmented: Sequence[FoldPredictions],
) -> float:
    """Delta = BMLL(baseline) - BMLL(augmented). Positive means improvement."""

    _, baseline_probabilities, baseline_truth = stack_folds(baseline)
    _, augmented_probabilities, augmented_truth = stack_folds(augmented)
    if not np.array_equal(baseline_truth, augmented_truth):
        raise ProcessFail("baseline and augmented models scored different rows")
    return balanced_multiclass_log_loss(
        baseline_probabilities, baseline_truth
    ) - balanced_multiclass_log_loss(augmented_probabilities, augmented_truth)


def per_fold_deltas(
    baseline: Sequence[FoldPredictions],
    augmented: Sequence[FoldPredictions],
) -> dict[int, float]:
    """Delta computed independently inside each test fold."""

    deltas: dict[int, float] = {}
    for base_fold, augmented_fold in zip(baseline, augmented):
        if base_fold.fold != augmented_fold.fold:
            raise ProcessFail("fold order mismatch")
        deltas[base_fold.fold] = balanced_multiclass_log_loss(
            base_fold.probabilities, base_fold.truth
        ) - balanced_multiclass_log_loss(
            augmented_fold.probabilities, augmented_fold.truth
        )
    return deltas


def session_bootstrap(
    baseline_probabilities: np.ndarray,
    augmented_probabilities: np.ndarray,
    truth: np.ndarray,
    sessions: np.ndarray,
    repetitions: int = BOOTSTRAP_REPETITIONS,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CI,
) -> dict[str, float]:
    """Resample whole sessions with replacement and re-score the delta.

    Sessions are the resampling unit because events inside a session are
    dependent, so resampling rows would understate the variance.
    """

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
            for index in range(len(RESOLVED_CLASSES))
        ):
            skipped += 1
            continue
        deltas.append(
            balanced_multiclass_log_loss(baseline_probabilities[rows], sample_truth)
            - balanced_multiclass_log_loss(
                augmented_probabilities[rows], sample_truth
            )
        )
    if not deltas:
        raise ProcessFail("every bootstrap replicate lacked a resolved class")
    values = np.array(deltas)
    lower_quantile = (1.0 - confidence) / 2.0
    return {
        "lower": float(np.quantile(values, lower_quantile)),
        "upper": float(np.quantile(values, 1.0 - lower_quantile)),
        "mean": float(values.mean()),
        "replicates": int(values.shape[0]),
        "skipped_replicates": int(skipped),
    }


def circular_shift_labels(
    truth: np.ndarray,
    sessions: np.ndarray,
    event_ticks: np.ndarray,
    generator: np.random.Generator,
) -> np.ndarray:
    """Rotate the label vector inside each session by a non-zero offset.

    Events are ordered by event time inside the session, the whole label vector
    is rotated, and no class is pinned or protected. Sessions with a single
    event stay unchanged because no non-zero rotation exists for them.
    """

    shifted = truth.copy()
    for session in np.unique(sessions):
        rows = np.flatnonzero(sessions == session)
        if rows.shape[0] < 2:
            continue
        ordered = rows[np.argsort(event_ticks[rows], kind="stable")]
        offset = int(generator.integers(1, ordered.shape[0]))
        shifted[ordered] = truth[np.roll(ordered, offset)]
    return shifted


def permutation_test(
    features_baseline: np.ndarray,
    features_augmented: np.ndarray,
    truth: np.ndarray,
    sessions: np.ndarray,
    event_ticks: np.ndarray,
    session_order: Sequence[str],
    observed_delta: float,
    repetitions: int = PERMUTATION_REPETITIONS,
    seed: int = PERMUTATION_SEED,
    progress=None,
) -> dict[str, float]:
    """Full refit permutation test under within-session circular shifts."""

    generator = np.random.default_rng(seed)
    at_least_as_extreme = 0
    completed = 0
    for repetition in range(repetitions):
        shifted = circular_shift_labels(truth, sessions, event_ticks, generator)
        try:
            baseline = out_of_fold_predictions(
                features_baseline, shifted, sessions, session_order
            )
            augmented = out_of_fold_predictions(
                features_augmented, shifted, sessions, session_order
            )
            null_delta = delta_from_predictions(baseline, augmented)
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


def benjamini_hochberg(
    p_values: Sequence[float],
    q_max: float = BENJAMINI_HOCHBERG_Q_MAX,
) -> list[bool]:
    """Standard step-up procedure; returns the rejection flag per input."""

    count = len(p_values)
    if count == 0:
        return []
    order = np.argsort(np.array(p_values), kind="stable")
    rejected = [False] * count
    largest = -1
    for rank, index in enumerate(order, start=1):
        if p_values[index] <= q_max * rank / count:
            largest = rank
    for rank, index in enumerate(order, start=1):
        if rank <= largest:
            rejected[index] = True
    return rejected


def primary_gates(
    delta: float,
    bootstrap: Mapping[str, float],
    permutation: Mapping[str, float],
    fold_deltas: Mapping[int, float],
    buy_delta: float,
    sell_delta: float,
) -> dict[str, object]:
    """Evaluate the six mandatory primary gates and the terminal rule."""

    positive_folds = sum(1 for value in fold_deltas.values() if value > 0.0)
    gates = {
        "delta_at_least_minimum": bool(delta >= MINIMUM_DELTA),
        "bootstrap_lower_bound_positive": bool(bootstrap["lower"] > 0.0),
        "permutation_p_within_max": bool(
            permutation["p_value"] <= PERMUTATION_P_MAX
        ),
        "positive_folds_at_least_minimum": bool(
            positive_folds >= POSITIVE_FOLDS_MINIMUM
        ),
        "buy_delta_positive": bool(buy_delta > 0.0),
        "sell_delta_positive": bool(sell_delta > 0.0),
    }
    all_pass = all(gates.values())
    return {
        "gates": gates,
        "positive_folds": int(positive_folds),
        "all_primary_gates_pass": bool(all_pass),
        "terminal_verdict": (
            "DISCOVERY_ONLY_SIGNAL" if all_pass else "NO_DISCOVERY_SIGNAL_CLOSE_LINE"
        ),
    }


def encode_truth(labels: Sequence[str]) -> np.ndarray:
    """Map resolved class names to their frozen integer order."""

    lookup = {name: index for index, name in enumerate(RESOLVED_CLASSES)}
    encoded = np.empty(len(labels), dtype=np.int64)
    for position, value in enumerate(labels):
        if value not in lookup:
            raise ProcessFail(f"unresolved label reached the model: {value}")
        encoded[position] = lookup[value]
    return encoded


def resolved_class_presence(
    truth: np.ndarray,
    sessions: np.ndarray,
    session_order: Sequence[str],
) -> dict[str, object]:
    """Declare PROCESS_FAIL conditions before any model is fitted."""

    positions = session_positions(session_order)
    row_positions = np.array([positions[value] for value in sessions])
    report: dict[str, object] = {"folds": {}, "process_fail": False}
    for fold in FOLDS:
        train_low, train_high = fold["train"]
        test_low, test_high = fold["test"]
        train_rows = (row_positions >= train_low) & (row_positions <= train_high)
        test_rows = (row_positions >= test_low) & (row_positions <= test_high)
        train_classes = sorted(set(truth[train_rows].tolist()))
        test_classes = sorted(set(truth[test_rows].tolist()))
        complete = len(train_classes) == len(RESOLVED_CLASSES) and len(
            test_classes
        ) == len(RESOLVED_CLASSES)
        report["folds"][int(fold["fold"])] = {
            "train_rows": int(train_rows.sum()),
            "test_rows": int(test_rows.sum()),
            "train_classes": len(train_classes),
            "test_classes": len(test_classes),
            "complete": bool(complete),
        }
        if not complete:
            report["process_fail"] = True
    if len(set(truth.tolist())) != len(RESOLVED_CLASSES):
        report["process_fail"] = True
    return report
