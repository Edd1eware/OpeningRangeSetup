import unittest
from unittest.mock import patch

import pandas as pd

import absorption_breakout_research as research
import lb_dom_hypothesis_monitor as monitor


class LiquidityBurstDomMonitorTests(unittest.TestCase):
    def test_percentage_separates_clean_absorption_from_clean_continuation(self):
        frame = pd.DataFrame({
            "causal_row_flag": [True] * 6,
            "Detector_VERSION": [research.EXPECTED_BURST_VERSION] * 6,
            "DOM_Snapshot_Valid": [True] * 6,
            "family": [
                research.FAMILY_ABSORPTION,
                research.FAMILY_ABSORPTION,
                research.FAMILY_CONTINUATION,
                research.FAMILY_CONTINUATION,
                research.FAMILY_VARIABLE,
                research.FAMILY_VARIABLE,
            ],
            monitor.PRIMARY_FEATURE: [0.40, 0.30, 0.10, 0.05, 0.20, 0.18],
        })
        with (
            patch.object(research, "build_dataset", return_value=(frame, pd.DataFrame())),
            patch.object(monitor, "_completed_sessions", return_value=42),
        ):
            result = monitor.calculate("unused")

        self.assertEqual(result["status"], "PROVISIONAL")
        self.assertEqual((result["n_a"], result["n_b"], result["n_c"]), (2, 2, 2))
        self.assertAlmostEqual(result["percentage"], 100.0)
        self.assertEqual(
            monitor.format_status(result),
            "Efectividad del DOM antes del movimiento : 100.0% 42 sesiones",
        )

    def test_monitor_waits_for_both_clean_families(self):
        frame = pd.DataFrame({
            "causal_row_flag": [True] * 4,
            "Detector_VERSION": [research.EXPECTED_BURST_VERSION] * 4,
            "DOM_Snapshot_Valid": [True] * 4,
            "family": [research.FAMILY_ABSORPTION] * 2 + [research.FAMILY_VARIABLE] * 2,
            monitor.PRIMARY_FEATURE: [0.40, 0.30, 0.20, 0.18],
        })
        with (
            patch.object(research, "build_dataset", return_value=(frame, pd.DataFrame())),
            patch.object(monitor, "_completed_sessions", return_value=8),
        ):
            result = monitor.calculate("unused")

        self.assertEqual(result["status"], "CALCULANDO")
        self.assertIsNone(result["percentage"])
        self.assertEqual(
            monitor.format_status(result),
            "Efectividad del DOM antes del movimiento : CALCULANDO 8 sesiones",
        )


if __name__ == "__main__":
    unittest.main()
