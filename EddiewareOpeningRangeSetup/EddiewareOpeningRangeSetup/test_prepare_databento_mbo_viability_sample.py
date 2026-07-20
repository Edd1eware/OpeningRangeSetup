import unittest

import pandas as pd

from prepare_databento_mbo_viability_sample import QUOTAS, select_viability_sample


class ViabilitySampleTests(unittest.TestCase):
    def test_exact_quotas_and_no_validation_leakage(self):
        rows = []
        sequence = 0
        for (family, year, side), quota in QUOTAS.items():
            for month in range(1, quota + 3):
                sequence += 1
                rows.append(
                    {
                        "fecha": f"{year}-{month:02d}-01",
                        "BurstId": f"LB_{year}{month:02d}01_093000_{side}_{sequence:04d}",
                        "split": "discovery",
                        "family_label_only": family,
                        "request_id": f"REQ_{sequence}",
                    }
                )
        sample = select_viability_sample(pd.DataFrame(rows))
        self.assertEqual(len(sample), 30)
        self.assertEqual(sample["BurstId"].nunique(), 30)
        self.assertTrue(sample["split"].eq("discovery").all())
        self.assertEqual(sample["family_label_only"].value_counts().to_dict(), {"A_TRUE_ABSORPTION": 15, "B_CLEAN_BREAKOUT": 15})


if __name__ == "__main__":
    unittest.main()
