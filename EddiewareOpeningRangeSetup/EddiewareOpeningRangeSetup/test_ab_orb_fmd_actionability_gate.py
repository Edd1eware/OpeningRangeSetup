from __future__ import annotations

import numpy as np
import pandas as pd

import ab_orb_fmd_actionability_gate as gate


def _frame(a: list[float], b: list[float]) -> pd.DataFrame:
    values = a + b
    families = [gate.FAMILY_A] * len(a) + [gate.FAMILY_B] * len(b)
    return pd.DataFrame(
        {
            "fecha": [f"2024-01-{index + 1:02d}" for index in range(len(values))],
            "year": [2024] * len(values),
            "burst_side": ["BUY", "SELL"] * (len(values) // 2),
            "family": families,
            gate.PRIMARY_ENDPOINT: values,
        }
    )


def test_effect_is_b_minus_a() -> None:
    frame = _frame([-2.0, -1.0], [3.0, 4.0])
    assert gate._effect(frame) == 5.0


def test_gate_passes_only_above_utility_and_significance() -> None:
    assert gate.classify_gate(3.0, 1.1, 4.5, 0.01, 0.9) == "PASS"
    assert (
        gate.classify_gate(1.5, 0.2, 2.8, 0.02, 0.9)
        == "SENAL_SUBUMBRAL"
    )


def test_gate_distinguishes_low_power_from_refutation() -> None:
    assert (
        gate.classify_gate(0.2, -1.0, 1.4, 0.7, 0.5)
        == "NO_CONCLUYENTE"
    )
    assert gate.classify_gate(0.2, -0.2, 0.6, 0.5, 0.9) == "REFUTACION"
    assert gate.classify_gate(-2.0, -3.0, -1.0, 0.01, 0.9) == "REFUTACION"


def test_permutation_preserves_length() -> None:
    frame = _frame(
        [-2.0, -1.0, -0.5, -1.5],
        [2.0, 1.0, 0.5, 1.5],
    )
    values = gate.stratified_permutation(frame, n_perm=50, seed=1)
    assert len(values) == 50
    assert np.isfinite(values).all()

