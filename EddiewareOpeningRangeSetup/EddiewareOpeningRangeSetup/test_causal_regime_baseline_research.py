import unittest

import numpy as np
import pandas as pd

from causal_regime_baseline_research import REGIMES, assign_regimes_from_training, bh_adjust


class CausalRegimeTests(unittest.TestCase):
    def test_thresholds_use_training_years_only(self):
        rows = []
        for year, value in [(2022, 1.0), (2023, 3.0), (2024, 1000.0)]:
            for index in range(4):
                row = {"year": year}
                for spec in REGIMES:
                    row[spec.column] = value + index
                rows.append(row)
        frame = pd.DataFrame(rows)
        train = frame.loc[frame["year"].isin([2022, 2023])]
        test = frame.loc[frame["year"].eq(2024)]
        assignments, thresholds = assign_regimes_from_training(train, test)
        threshold_frame = pd.DataFrame(thresholds).set_index("regime_axis")
        self.assertLess(threshold_frame.loc["ATR5", "training_threshold"], 10)
        self.assertTrue(assignments["ATR5"].eq("HIGH").all())

    def test_bh_adjust_is_monotone_in_rank(self):
        values = pd.Series([0.01, 0.04, 0.03, np.nan])
        adjusted = bh_adjust(values)
        ordered = adjusted.dropna().sort_values()
        self.assertTrue(ordered.is_monotonic_increasing)
        self.assertTrue((ordered <= 1).all())


if __name__ == "__main__":
    unittest.main()
