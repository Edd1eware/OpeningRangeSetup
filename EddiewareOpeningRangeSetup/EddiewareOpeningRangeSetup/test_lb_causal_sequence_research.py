import unittest
from pathlib import Path

import pandas as pd

import lb_causal_sequence_research as sequence


def timeline_frame(states, burst_id="LB_TEST", side="BUY"):
    decision = pd.Timestamp("2026-07-21T13:31:19Z")
    rows = []
    for index, state in enumerate(states, start=1):
        causal = decision - pd.Timedelta(milliseconds=(len(states) - index) * 100)
        is_depth = state.startswith("DEPTH_")
        replenishment = "REPLENISHMENT" in state
        ahead = "AHEAD" in state
        rows.append({
            "Detector_VERSION": sequence.EXPECTED_VERSION,
            "BurstId": burst_id,
            "Burst_Side": side,
            "Burst_Timestamp_UTC": decision - pd.Timedelta(seconds=1),
            "Decision_Timestamp_UTC": decision,
            "Event_Sequence_In_Burst": index,
            "Global_Arrival_Sequence": 100 + index,
            "Event_Source_Timestamp_UTC": causal,
            "Event_Causal_Timestamp_UTC": causal,
            "Event_Available_Timestamp_UTC": causal,
            "Offset_To_Decision_Milliseconds": (causal - decision).total_seconds() * 1000,
            "Event_Type": "DEPTH_INCREASE" if is_depth and replenishment else "DEPTH_DECREASE" if is_depth else "TAPE_BUY",
            "Event_State": state,
            "Book_Side": "Ask" if is_depth else "",
            "Ahead_Behind": "AHEAD" if ahead else "NA",
            "Trade_Alignment": "NA" if is_depth else "ALIGNED",
            "Depth_Delta": 5 if replenishment else -5 if is_depth else None,
            "Trade_Volume": None if is_depth else 10,
            "Trade_Direction": 0 if is_depth else 1,
            "Directional_Trade_Price_Change_Ticks": 0 if state == "AGGRESSION_STALL" else 1,
            "Directional_Microprice_Ticks": -0.1,
            "Directional_Depth_Imbalance_L1": -0.2,
            "Directional_Depth_Imbalance_L3": -0.1,
            "Directional_Depth_Imbalance_L5": -0.05,
            "Directional_Price_From_Burst_Ticks": 0,
            "Book_Snapshot_Valid": 1,
            "Available_Before_Decision": 1,
            "Causal_Flag": 1,
            "Model_Eligibility": "CAUSAL_PRE_DECISION",
            "Clock_Quality": "TRADE_TIMESTAMP" if not is_depth else "LAST_TRADE_CAUSAL_CLOCK",
        })
    return pd.DataFrame(rows)


class CausalSequenceResearchTests(unittest.TestCase):
    def test_causal_audit_accepts_ordered_predecision_events(self):
        frame = timeline_frame([
            "AGGRESSION_PROGRESS", "AGGRESSION_STALL", "DEPTH_REPLENISHMENT_AHEAD"
        ])
        audit, passed = sequence.audit_timeline(frame)
        self.assertTrue(passed, audit.to_dict("records"))

    def test_causal_audit_rejects_postdecision_event(self):
        frame = timeline_frame(["AGGRESSION_PROGRESS", "DEPTH_DEPLETION_AHEAD"])
        frame.loc[1, "Event_Causal_Timestamp_UTC"] = frame.loc[1, "Decision_Timestamp_UTC"] + pd.Timedelta(milliseconds=1)
        frame.loc[1, "Offset_To_Decision_Milliseconds"] = 1
        _, passed = sequence.audit_timeline(frame)
        self.assertFalse(passed)

    def test_absorption_grammar_scores_above_breakout(self):
        frame = timeline_frame([
            "AGGRESSION_PROGRESS", "AGGRESSION_STALL", "DEPTH_REPLENISHMENT_AHEAD"
        ])
        features = sequence.build_sequence_features(frame).iloc[0]
        self.assertGreater(features["absorption_order_score"], features["breakout_order_score"])
        self.assertGreater(features["grammar_margin"], 0)

    def test_detector_source_declares_exact_sequence_schema(self):
        source = (Path(__file__).parent / "12_LiquidityBurstDetector.cs").read_text(encoding="utf-8")
        self.assertTrue(
            sequence.EXPECTED_VERSION in source
            or "liquidity-burst-detector-2026-07-22-v7-postburst-matrix" in source
        )
        self.assertIn("burst_causal_timeline.csv", source)
        self.assertIn("Event_Causal_Timestamp_UTC", source)
        self.assertIn("Available_Before_Decision", source)
        self.assertIn("Global_Arrival_Sequence", source)


if __name__ == "__main__":
    unittest.main()
