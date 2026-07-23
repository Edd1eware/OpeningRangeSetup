import unittest
from pathlib import Path

import pandas as pd

import lb_matrix_classification_research as matrix
from lb_matrix_classification_monitor import format_status


def _row(sequence, offset_ms, event_type, state, *, depth=0, volume=0, alignment="", ahead=""):
    burst = pd.Timestamp("2026-03-10T13:31:18Z")
    decision = burst + pd.Timedelta(seconds=1)
    event = burst + pd.Timedelta(milliseconds=offset_ms)
    return {
        "Detector_VERSION": matrix.EXPECTED_VERSION,
        "BurstId": "LB_TEST_BUY_0001",
        "Burst_Side": "BUY",
        "Burst_Timestamp_UTC": burst,
        "Decision_Timestamp_UTC": decision,
        "Event_Sequence_In_Burst": sequence,
        "Global_Arrival_Sequence": sequence,
        "Event_Causal_Timestamp_UTC": event,
        "Event_Available_Timestamp_UTC": event,
        "Offset_To_Decision_Milliseconds": 1000 - offset_ms,
        "Event_Type": event_type,
        "Event_State": state,
        "Ahead_Behind": ahead,
        "Trade_Alignment": alignment,
        "Price": 20000.0,
        "Directional_Price_From_Burst_Ticks": 1.0 if offset_ms >= 200 else 0.0,
        "Depth_Delta": depth,
        "Trade_Volume": volume,
        "Directional_Microprice_Ticks": 0.2,
        "Directional_Depth_Imbalance_L1": 0.1,
        "Book_Snapshot_Valid": 1,
        "Available_Before_Decision": 1,
        "Causal_Flag": 1,
        "Model_Eligibility": "CAUSAL_PRE_DECISION",
    }


class MatrixClassificationResearchTests(unittest.TestCase):
    def test_strict_audit_accepts_only_postburst_v7(self):
        rows = []
        for index in range(30):
            rows.append(_row(
                index + 1,
                10 + index * 20,
                "TAPE_BUY" if index % 2 else "DEPTH_DECREASE",
                "AGGRESSION_STALL" if index % 2 else "DEPTH_DEPLETION_AHEAD",
                depth=-5 if index % 2 == 0 else 0,
                volume=2 if index % 2 else 0,
                alignment="ALIGNED" if index % 2 else "",
                ahead="AHEAD" if index % 2 == 0 else "",
            ))
        frame = pd.DataFrame(rows)
        audit, passed, post = matrix.audit_timeline(frame)
        self.assertTrue(passed, audit.to_string(index=False))
        self.assertEqual(len(post), 30)

    def test_filter_rejects_preburst_and_postdecision(self):
        frame = pd.DataFrame([
            _row(1, -10, "TAPE_BUY", "AGGRESSION_STALL", volume=1, alignment="ALIGNED"),
            _row(2, 100, "TAPE_BUY", "AGGRESSION_STALL", volume=1, alignment="ALIGNED"),
            _row(3, 1100, "TAPE_BUY", "AGGRESSION_STALL", volume=1, alignment="ALIGNED"),
        ])
        post = matrix.filter_postburst(frame)
        self.assertEqual(post["Event_Sequence_In_Burst"].tolist(), [2])

    def test_macro_sequence_begins_at_lb(self):
        frame = pd.DataFrame([
            _row(1, 10, "TAPE_BUY", "AGGRESSION_STALL", volume=5, alignment="ALIGNED"),
            _row(2, 20, "DEPTH_DECREASE", "DEPTH_DEPLETION_AHEAD", depth=-20, ahead="AHEAD"),
            _row(3, 150, "TAPE_BUY", "AGGRESSION_PROGRESS", volume=8, alignment="ALIGNED"),
            _row(4, 160, "DEPTH_INCREASE", "DEPTH_REPLENISHMENT_AHEAD", depth=15, ahead="AHEAD"),
        ])
        states, sequences = matrix.build_macro_states(frame)
        self.assertFalse(states.empty)
        self.assertTrue(sequences.iloc[0]["sequence"].startswith("LB>"))
        self.assertIn("STALL+CON", sequences.iloc[0]["sequence"])

    def test_source_contains_explicit_postburst_export_bound(self):
        source = Path(__file__).with_name("12_LiquidityBurstDetector.cs").read_text(encoding="utf-8")
        self.assertIn(matrix.EXPECTED_VERSION, source)
        self.assertIn("snapshot.TimestampUtc > configuredStartTimestampUtc", source)
        self.assertIn("item.CausalTimestampUtc <= decisionTimestampUtc", source)

    def test_telegram_status_name(self):
        text = format_status({"bursts": 4, "events": 1000, "causal_pct": 100.0, "sessions": 4})
        self.assertEqual(
            text,
            "MATRIX CLASSIFICATION TEST : 4 bursts post-LB | 1000 eventos | 100.0% causal | 4 sesiones",
        )

    def test_runner_contains_required_final_capability_messages(self):
        runner = Path(__file__).with_name("04_run_replay_lb_matrix_classification_dst_2025_2026.py").read_text(encoding="utf-8")
        self.assertIn("YA SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO", runner)
        self.assertIn("NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO", runner)
        self.assertIn("me falta analizar:", runner)


if __name__ == "__main__":
    unittest.main()
