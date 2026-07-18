import unittest

import pandas as pd

import absorption_breakout_research as base
import born_bad_trade_research as research


class BornBadSecondIterationTests(unittest.TestCase):
    def test_directional_clv_requires_reproducible_trade_event_range(self):
        prediction = pd.Timestamp("2026-07-16T13:31:05Z")
        frame = pd.DataFrame([{
            "fecha": "2026-07-16",
            "BurstId": "burst-1",
            "prediction_timestamp": prediction,
            "ExecutionSide": "BUY",
            "Entry_price": 101.0,
            "Directional_CLV_AtEntry": 0.5,
            "Causal_Entry_High_AtEntry": 102.0,
            "Causal_Entry_Low_AtEntry": 98.0,
            "Causal_Entry_Observation_Count_AtEntry": 4,
            "Causal_Entry_First_Timestamp_UTC": prediction - pd.Timedelta(seconds=3),
            "Causal_Entry_Last_Timestamp_UTC": prediction,
            "Causal_Entry_Source_AtEntry": "MARKET_TRADE_EVENTS",
            "CLV_Causality_Status_AtEntry": "CAUSAL_EVENT_RANGE",
        }])
        audit, _ = research._clv_audit(frame)
        self.assertEqual(int(audit.iloc[0]["causal_row_ok"]), 1)

    def test_clv_rejects_platform_state_source(self):
        prediction = pd.Timestamp("2026-07-16T13:31:05Z")
        frame = pd.DataFrame([{
            "fecha": "2026-07-16",
            "BurstId": "burst-1",
            "prediction_timestamp": prediction,
            "ExecutionSide": "SELL",
            "Entry_price": 99.0,
            "Directional_CLV_AtEntry": 0.5,
            "Causal_Entry_High_AtEntry": 102.0,
            "Causal_Entry_Low_AtEntry": 98.0,
            "Causal_Entry_Observation_Count_AtEntry": 4,
            "Causal_Entry_First_Timestamp_UTC": prediction - pd.Timedelta(seconds=3),
            "Causal_Entry_Last_Timestamp_UTC": prediction,
            "Causal_Entry_Source_AtEntry": "MARKET_STATE_PRICES",
            "CLV_Causality_Status_AtEntry": "CAUSAL_EVENT_RANGE",
        }])
        audit, _ = research._clv_audit(frame)
        self.assertEqual(int(audit.iloc[0]["causal_row_ok"]), 0)

    def test_post_burst_responses_are_not_preentry_features(self):
        self.assertTrue(set(research.RESPONSE_METRICS).isdisjoint(base.FEATURE_NAMES))


if __name__ == "__main__":
    unittest.main()
