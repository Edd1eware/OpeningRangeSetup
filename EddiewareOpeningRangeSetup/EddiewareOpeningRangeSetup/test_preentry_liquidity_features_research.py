import unittest

import numpy as np
import pandas as pd

from preentry_liquidity_features_research import level_window_features, prepare_mbp


class PreEntryLiquidityFeatureTests(unittest.TestCase):
    def test_cutoff_and_depth_changes(self):
        raw = pd.DataFrame({
            "seconds": [8.0, 9.0, 9.5, 10.1],
            "side": ["Ask"] * 4,
            "price": [100.0] * 4,
            "volume": [10.0, 6.0, 12.0, 99.0],
        })
        prepared = prepare_mbp(raw, 10.0)
        self.assertEqual(len(prepared), 3)
        self.assertTrue(np.isnan(prepared.iloc[0]["depth_change"]))
        self.assertEqual(prepared.iloc[1]["depth_change"], -4)
        self.assertEqual(prepared.iloc[2]["depth_change"], 6)

    def test_refill_is_computed_before_cutoff(self):
        mbp = prepare_mbp(pd.DataFrame({
            "seconds": [8.0, 9.0, 9.5, 10.1],
            "side": ["Ask"] * 4,
            "price": [100.0] * 4,
            "volume": [10.0, 6.0, 12.0, 99.0],
        }), 10.0)
        tape = pd.DataFrame({
            "seconds": [9.2, 10.2],
            "price": [100.0, 100.0],
            "volume": [4.0, 100.0],
            "direction": ["Buy", "Buy"],
        })
        values = level_window_features(mbp, tape, cutoff_seconds=10.0, window_seconds=2, level=100.0, burst_side="BUY")
        self.assertEqual(values["remove_volume"], 4)
        self.assertEqual(values["add_volume"], 6)
        self.assertEqual(values["aggressive_volume"], 4)
        self.assertEqual(values["add_to_aggressive"], 1.5)
        self.assertAlmostEqual(values["refill_latency_ms"], 300)

    def test_missing_level_is_not_fabricated_as_zero(self):
        mbp = prepare_mbp(pd.DataFrame({
            "seconds": [9.0], "side": ["Ask"], "price": [101.0], "volume": [10.0],
        }), 10.0)
        tape = pd.DataFrame({
            "seconds": [9.5], "price": [100.0], "volume": [2.0], "direction": ["Buy"],
        })
        values = level_window_features(mbp, tape, cutoff_seconds=10.0, window_seconds=2, level=100.0, burst_side="BUY")
        self.assertEqual(values["level_seen"], 0)
        self.assertTrue(np.isnan(values["add_volume"]))
        self.assertTrue(np.isnan(values["update_count"]))
        self.assertEqual(values["aggressive_volume"], 2)


if __name__ == "__main__":
    unittest.main()
