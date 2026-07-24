from __future__ import annotations

import numpy as np
import pandas as pd

import lb_matrix_mbo_combined_research as research
import mbo_liquidity_burst_research as mbo


def synthetic_frame() -> pd.DataFrame:
    rows = []
    for year in (2022, 2023, 2024):
        for index in range(12):
            target = index % 2
            rows.append(
                {
                    "BurstId": f"LB_{year}_{index}",
                    "fecha": f"{year}-01-{index + 1:02d}",
                    "year": year,
                    "burst_side": "BUY" if index % 3 else "SELL",
                    "family": research.FAMILY_A if target else research.FAMILY_B,
                    "target": target,
                    "signal": float(target * 2 - 1) + index * 0.001,
                }
            )
    return pd.DataFrame(rows)


def test_loyo_predictions_are_out_of_year_and_complete() -> None:
    frame = synthetic_frame()
    predictions = research._loyo_predictions(frame, ["signal"])
    assert len(predictions) == len(frame)
    assert set(predictions["year"]) == {2022, 2023, 2024}
    assert predictions["BurstId"].nunique() == len(frame)
    assert research._metrics(predictions)["balanced_accuracy"] > 0.95


def test_frozen_feature_families_include_no_outcomes() -> None:
    frame = pd.DataFrame(
        {
            "tr__A>B": [0, 1],
            "sq__A>B>C": [1, 0],
            **{feature: [0.0, 1.0] for feature in mbo.CORE_MBO_FEATURES},
        }
    )
    families = research._feature_sets(frame)
    assert tuple(families) == research.FAMILY_ORDER
    assert set(families[research.PRIMARY_FAMILY]) == {
        "tr__A>B",
        "sq__A>B>C",
        *mbo.CORE_MBO_FEATURES,
    }
    assert not any(
        token in feature.lower()
        for features in families.values()
        for feature in features
        for token in ("mfe", "mae", "result", "pnl", "outcome")
    )


def test_bootstrap_and_label_are_finite() -> None:
    predictions = research._loyo_predictions(synthetic_frame(), ["signal"])
    low, high = research._bootstrap_ci(predictions)
    assert np.isfinite(low)
    assert low <= high
    metrics = pd.DataFrame(
        [
            {
                "feature_family": research.PRIMARY_FAMILY,
                "n": len(predictions),
                "balanced_accuracy": 1.0,
                "balanced_accuracy_ci_low": low,
                "balanced_accuracy_ci_high": high,
                "roc_auc_A_vs_B": 1.0,
                "sensitivity_A": 1.0,
                "specificity_B": 1.0,
                "permutation_p_within_year": 0.001,
                "minimum_year_side_balanced_accuracy": 1.0,
                "pilot_status": "PROMETEDORA_DISCOVERY",
            }
        ]
    )
    label = research._label_text(
        metrics,
        {
            "left_censored_pct": 21.88,
            "snapshot_rows": 0,
            "post_cutoff_rows_excluded": 5,
        },
    )
    assert label.startswith("ETIQUETA MATRIX+MBO")
    assert "no son WR ni PF" in label
    assert "SIRVEN PARCIALMENTE" in label


def test_feature_manifest_annotation_handles_empty_matrix_manifest() -> None:
    annotated = research._annotate_feature_manifest(pd.DataFrame())
    assert len(annotated) == len(mbo.CORE_MBO_FEATURES)
    assert annotated["information_status"].notna().all()
    assert annotated["limitation"].notna().all()
    assert set(annotated["feature"]) == set(mbo.CORE_MBO_FEATURES)
