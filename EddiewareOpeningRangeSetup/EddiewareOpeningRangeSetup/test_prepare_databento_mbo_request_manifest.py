import tempfile
import unittest
from pathlib import Path

import pandas as pd

from prepare_databento_mbo_request_manifest import build_manifest


class DatabentoManifestTests(unittest.TestCase):
    def test_window_ends_after_cutoff_but_requires_causal_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.csv"
            pd.DataFrame(
                {
                    "fecha": ["2024-07-26"],
                    "BurstId": ["LB_TEST"],
                    "split": ["validation"],
                    "family": ["A_TRUE_ABSORPTION"],
                    "prediction_timestamp": ["2024-07-26T13:33:47.026Z"],
                }
            ).to_csv(source, index=False)
            row = build_manifest(source).iloc[0]
            self.assertEqual(row["start_utc"], "2024-07-26T13:33:37.026000Z")
            self.assertEqual(row["end_utc_exclusive"], "2024-07-26T13:33:47.027000Z")
            self.assertEqual(row["post_download_filter"], "ts_event<=causal_cutoff_utc_inclusive")
            self.assertAlmostEqual(row["requested_seconds"], 10.001)


if __name__ == "__main__":
    unittest.main()
