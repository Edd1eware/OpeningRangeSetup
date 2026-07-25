from __future__ import annotations

import pandas as pd

from joint_ab_v4_label_outcomes import LABEL_A, LABEL_B, LABEL_C
from joint_ab_v5_label_pilot import v5_summary


def test_v5_prevalence_gate_requires_15_of_98() -> None:
    rows = []
    labels = [LABEL_A] * 15 + [LABEL_B] * 15 + [LABEL_C] * 68
    for index, label in enumerate(labels):
        rows.append(
            {
                "BurstId": f"B{index}",
                "year": 2022 + index % 3,
                "burst_side": "BUY" if index % 2 == 0 else "SELL",
                "base_label": label,
                "low_85_label": label,
                "high_115_label": label,
                "record_ordinal_unique": True,
                "used_match_events_closed": True,
                "used_match_events_single_ts_event": True,
                "maybe_bad_book_zero": True,
                "sequence_regressions_zero": True,
                "double_decode_deterministic": True,
                "p0_within_prior_100ms": True,
                "post_trade_available": True,
                "contract_single": True,
                "contract_symbol_match": True,
            }
        )
    result = v5_summary(pd.DataFrame(rows))
    assert result["gates"]["A_at_least_15pct"]
    assert result["gates"]["B_at_least_15pct"]
    assert result["minimum_class_count_15pct"] == 15
