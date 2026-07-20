import unittest

import numpy as np
import pandas as pd

from mbo_liquidity_burst_research import (
    _order_lifecycle_features,
    _refill_features,
    aggregate_window,
    mark_pure_cancels,
)


def sample_frame() -> pd.DataFrame:
    timestamps = pd.to_datetime(
        [
            "2024-01-01T00:00:00.000Z",
            "2024-01-01T00:00:00.050Z",
            "2024-01-01T00:00:00.050Z",
            "2024-01-01T00:00:00.080Z",
            "2024-01-01T00:00:00.150Z",
        ],
        utc=True,
    )
    frame = pd.DataFrame(
        {
            "ts_event": timestamps,
            "action": ["A", "F", "C", "A", "C"],
            "side": ["A", "A", "A", "A", "A"],
            "price": [100.0] * 5,
            "size": [2, 2, 2, 1, 1],
            "order_id": np.array([1, 1, 1, 2, 2], dtype="uint64"),
            "sequence_index_local": range(5),
        }
    )
    return mark_pure_cancels(frame)


class MboFeatureTests(unittest.TestCase):
    def test_fill_paired_cancel_is_not_double_counted(self):
        frame = sample_frame()
        self.assertFalse(bool(frame.loc[2, "pure_cancel"]))
        self.assertTrue(bool(frame.loc[4, "pure_cancel"]))

    def test_lifecycle_and_refill_are_causal(self):
        frame = sample_frame()
        lifecycle = _order_lifecycle_features(frame, frame)
        self.assertEqual(lifecycle["new_order_count"], 2)
        self.assertEqual(lifecycle["new_order_survival_share"], 0.0)
        self.assertAlmostEqual(lifecycle["median_observed_lifetime_ms"], 60.0)
        refill = _refill_features(frame)
        self.assertEqual(refill["refill_50ms_count"], 1.0)
        self.assertAlmostEqual(refill["refill_50ms_share"], 0.5)

    def test_aligned_side_imbalance(self):
        frame = sample_frame()
        features = aggregate_window(frame, frame, window_seconds=1, passive_side="A")
        self.assertEqual(features["passive_add_size"], 3.0)
        self.assertEqual(features["opposite_add_size"], 0.0)
        self.assertEqual(features["add_size_side_imbalance"], 1.0)


if __name__ == "__main__":
    unittest.main()
