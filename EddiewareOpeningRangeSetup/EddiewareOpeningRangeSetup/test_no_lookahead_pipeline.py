import unittest

from causal_feature_audit import audit_feature_columns, audit_timestamp_order
from edge_optimization_fast import CAUSAL_FEATURE_COLUMNS
from rebuild_causal_trade_dataset import input_from_legacy, result_from_legacy


class NoLookaheadPipelineTests(unittest.TestCase):
    def test_optimizer_allows_only_causal_feature_set(self):
        audit_feature_columns(CAUSAL_FEATURE_COLUMNS)

    def test_optimizer_rejects_legacy_final_or_outcome_columns(self):
        forbidden = [
            "Cvd_Pullback_Label",
            "Cvd_Label_Final",
            "MFE_ticks",
            "MAE_ticks",
            "Exit_price",
            "result TP SL BE",
            "Dynamic_Alarm_Triggered",
            "Future_MFE_After_Alarm",
            "SL_ticks_AtEntry",
            "TP_ticks_AtEntry",
        ]
        for column in forbidden:
            with self.subTest(column=column):
                with self.assertRaises(RuntimeError):
                    audit_feature_columns([column])

    def test_timestamp_audit_rejects_future_feature_time(self):
        with self.assertRaises(RuntimeError):
            audit_timestamp_order(
                [
                    {
                        "fecha": "2026-07-10",
                        "feature_timestamp_utc": "2026-07-10T13:31:15+00:00",
                        "entry_timestamp_utc": "2026-07-10T13:31:14+00:00",
                    }
                ]
            )

    def test_reconstruction_freezes_entry_cvd_and_moves_final_cvd_to_results(self):
        legacy = {
            "fecha": "2026-07-10",
            "EntryTime_NY_Milliseconds": "09:31:14.549",
            "ExitTime_NY_Milliseconds": "09:31:17.441",
            "Trade_Duration": "00:02",
            "EntryBar": "2311",
            "Side": "BUY",
            "Signal_Source": "BREAKOUT",
            "Speed_Profile": "SCALP_NORMAL",
            "Entry_price": "29891.25",
            "SL_price": "29886.25",
            "TP_price": "29896.25",
            "SL_ticks": "20",
            "TP_ticks": "20",
            "or_low": "29812.50",
            "or_high": "29876.25",
            "range": "255",
            "VWAP_entry": "29829.05",
            "Body": "60",
            "Volume_entry": "1022",
            "Delta_entry": "106",
            "Cumulative_Delta_entry": "-245",
            "Cumulative_Delta_Source": "SessionDeltaSum",
            "Cvd_Pullback_Label": "Riesgo de reversion",
            "Cvd_Current": "-253",
            "Cvd_Peak": "-242",
            "Cvd_Pullback_Pct": "3.67",
            "Result_Label": "SL",
            "Exit_price": "29886.25",
            "result TP SL BE": "-20",
            "MAE_ticks": "20",
            "MFE_ticks": "5",
        }
        input_row = input_from_legacy(legacy)
        result_row = result_from_legacy(legacy, input_row)

        self.assertEqual(input_row["Cvd_Label_AtEntry"], "Excelente")
        self.assertEqual(input_row["Cvd_Current_AtEntry"], "-245")
        self.assertEqual(result_row["Cvd_Label_Final"], "Riesgo de reversion")
        self.assertEqual(result_row["result_ticks"], "-20")


if __name__ == "__main__":
    unittest.main()
