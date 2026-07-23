import unittest

import pandas as pd

import absorption_breakout_research as research


class AbsorptionBreakoutResearchTests(unittest.TestCase):
    DOM_FEATURES = {
        "DOM_Spread_Ticks",
        "DOM_Directional_Microprice_Ticks",
        "DOM_Directional_Depth_Imbalance_L1",
        "DOM_Directional_Depth_Imbalance_L3",
        "DOM_Directional_Depth_Imbalance_L5",
        "DOM_Ahead_Depth_Per_Aggressive_L3",
        "DOM_Ahead_L1_Concentration_L5",
        "DOM_Directional_PullStack_1s",
        "DOM_Directional_PullStack_3s",
        "DOM_Ahead_Stack_Share_1s",
        "DOM_Near_Churn_Per_Aggressive_1s",
    }

    def test_strict_family_labels_use_only_terminal_outcomes(self):
        cases = (
            ({"Result_Label": "TP", "MAE_ticks": 10, "MFE_ticks": 60, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, research.FAMILY_ABSORPTION),
            ({"Result_Label": "SL", "MAE_ticks": 60, "MFE_ticks": 10, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, research.FAMILY_CONTINUATION),
            ({"Result_Label": "TP", "MAE_ticks": 25, "MFE_ticks": 60, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, research.FAMILY_VARIABLE),
            ({"Result_Label": "BE", "MAE_ticks": 15, "MFE_ticks": 20, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, research.FAMILY_VARIABLE),
            ({"Result_Label": "TIME_OVER", "MAE_ticks": None, "MFE_ticks": None, "Initial_SL_ticks": 60, "Initial_TP_ticks": 60}, research.FAMILY_EXCLUDED),
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
        self.assertEqual(family, research.FAMILY_ABSORPTION)

    def test_family_ordinal_is_absorption_variable_continuation(self):
        self.assertEqual(
            research.FAMILY_ORDINAL,
            {
                research.FAMILY_CONTINUATION: 0,
                research.FAMILY_VARIABLE: 1,
                research.FAMILY_ABSORPTION: 2,
            },
        )

    def test_feature_catalog_contains_no_outcome_columns(self):
        leaked = [name for name in research.FEATURE_NAMES if research.OUTCOME_PATTERNS.search(name)]
        self.assertEqual(leaked, [])

    def test_dom_geometry_is_a_distinct_causal_family(self):
        specs = {spec.name: spec for spec in research.ALL_SPECS}
        self.assertTrue(self.DOM_FEATURES.issubset(specs))
        for feature in self.DOM_FEATURES:
            with self.subTest(feature=feature):
                self.assertEqual(research._mechanism_family(feature), "DOM_GEOMETRY")
                self.assertEqual(specs[feature].source, "burst_events")
                self.assertLessEqual(specs[feature].window_end_seconds, 0)

    def test_dom_only_scope_exposes_exactly_the_preregistered_dom_features(self):
        original = tuple(research.FEATURE_NAMES)
        try:
            configured = research.configure_feature_scope("DOM_ONLY")
            self.assertEqual(set(configured), self.DOM_FEATURES)
            self.assertEqual(len(configured), 11)
            self.assertTrue(all(name.startswith("DOM_") for name in configured))
            self.assertEqual(set(research._feature_catalog()["feature"]), self.DOM_FEATURES)
            self.assertEqual(set(research._candidate_features()["feature"]), self.DOM_FEATURES)
        finally:
            research.FEATURE_NAMES = list(original)

    def test_previous_detector_capture_remains_readable_for_audit(self):
        self.assertIn(
            "liquidity-burst-detector-2026-07-19-v4-publish-clock-audit",
            research.SUPPORTED_BURST_VERSIONS,
        )
        self.assertIn(research.EXPECTED_BURST_VERSION, research.SUPPORTED_BURST_VERSIONS)

    def test_required_telegram_heading_is_exact(self):
        self.assertEqual(research.TELEGRAM_TITLE, "ANALISIS  FAMILIAS A, B, C, ETC.")


if __name__ == "__main__":
    unittest.main()
