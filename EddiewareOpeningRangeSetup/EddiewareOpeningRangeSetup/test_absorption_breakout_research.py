import unittest

import pandas as pd

import absorption_breakout_research as research


class AbsorptionBreakoutResearchTests(unittest.TestCase):
    def test_strict_family_labels_use_only_terminal_outcomes(self):
        cases = (
            ({"Result_Label": "TP", "MAE_ticks": 10, "MFE_ticks": 60, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, "A_TRUE_ABSORPTION"),
            ({"Result_Label": "SL", "MAE_ticks": 60, "MFE_ticks": 10, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, "B_CLEAN_BREAKOUT"),
            ({"Result_Label": "TP", "MAE_ticks": 25, "MFE_ticks": 60, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, "C_MIXED_PATH"),
            ({"Result_Label": "BE", "MAE_ticks": 15, "MFE_ticks": 20, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, "D_OTHER_EXIT"),
        )
        for values, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(research._label_family(pd.Series(values))[0], expected)

    def test_initial_rr_does_not_change_family_definition(self):
        family, _ = research._label_family(pd.Series({
            "Result_Label": "TP",
            "MAE_ticks": 0,
            "MFE_ticks": 60,
            "Initial_SL_ticks": 60,
            "Initial_TP_ticks": 60,
        }))
        self.assertEqual(family, "A_TRUE_ABSORPTION")

    def test_feature_catalog_contains_no_outcome_columns(self):
        leaked = [name for name in research.FEATURE_NAMES if research.OUTCOME_PATTERNS.search(name)]
        self.assertEqual(leaked, [])

    def test_required_telegram_heading_is_exact(self):
        self.assertEqual(research.TELEGRAM_TITLE, "ANALISIS  FAMILIAS A, B, C, ETC.")


if __name__ == "__main__":
    unittest.main()
