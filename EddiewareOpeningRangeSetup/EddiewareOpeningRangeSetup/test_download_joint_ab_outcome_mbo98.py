from __future__ import annotations

import numpy as np
import pandas as pd

import download_joint_ab_outcome_mbo98 as downloader


def test_match_event_can_span_sequences_and_last_trade_is_used() -> None:
    base = pd.Timestamp("2024-01-01T00:00:00Z")
    frame = pd.DataFrame(
        {
            "ts_event": [base, base, base, base + pd.Timedelta(milliseconds=1)],
            "sequence": [10, 10, 11, 12],
            "action": ["T", "F", "C", "T"],
            "side": ["B", "A", "A", "A"],
            "price": [100.25, 100.25, 100.25, 100.0],
            "size": [1, 1, 1, 1],
            "flags": [0, 0, 128, 128],
            "instrument_id": [1, 1, 1, 1],
            "record_ordinal": np.arange(4),
        }
    )
    sales, quality = downloader.last_sales_by_match_event(frame)
    assert len(sales) == 2
    assert list(sales["price"]) == [100.25, 100.0]
    assert quality["unclosed_t_match_events"] == 0
    assert quality["multi_sequence_t_match_events"] == 1


def test_unclosed_t_event_fails() -> None:
    base = pd.Timestamp("2024-01-01T00:00:00Z")
    frame = pd.DataFrame(
        {
            "ts_event": [base],
            "sequence": [10],
            "action": ["T"],
            "side": ["B"],
            "price": [100.25],
            "size": [1],
            "flags": [0],
            "instrument_id": [1],
            "record_ordinal": [0],
        }
    )
    try:
        downloader.last_sales_by_match_event(frame)
    except ValueError as error:
        assert "lack F_LAST" in str(error)
    else:
        raise AssertionError("Expected unclosed event failure")
