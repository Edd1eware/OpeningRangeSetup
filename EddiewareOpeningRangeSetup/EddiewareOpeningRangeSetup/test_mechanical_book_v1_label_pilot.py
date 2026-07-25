from __future__ import annotations

from mechanical_book_v1_label_pilot import (
    LABEL_A,
    LABEL_B,
    LABEL_C,
    classify_metrics,
)


def test_absorption_fixed_point() -> None:
    metrics = {
        "Q0": 100,
        "F_dep": 60,
        "C_dep": 0,
        "never_ceded": True,
        "Q_end": 40,
        "queue_zero": False,
        "ceded_terminal": False,
    }
    assert classify_metrics(metrics, 0.5) == LABEL_A


def test_breakout_fixed_point() -> None:
    metrics = {
        "Q0": 100,
        "F_dep": 60,
        "C_dep": 40,
        "never_ceded": False,
        "Q_end": 0,
        "queue_zero": True,
        "ceded_terminal": True,
    }
    assert classify_metrics(metrics, 0.5) == LABEL_B


def test_cancel_dominant_depletion_is_variable() -> None:
    metrics = {
        "Q0": 100,
        "F_dep": 10,
        "C_dep": 90,
        "never_ceded": False,
        "Q_end": 0,
        "queue_zero": True,
        "ceded_terminal": True,
    }
    assert classify_metrics(metrics, 0.5) == LABEL_C
