"""Pruebas puras del recorrido historico. No conectan ni controlan ATAS."""

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


SPEC = importlib.util.spec_from_file_location("journal_run", Path(__file__).parents[1] / "19_journal_run.py")
journal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(journal)


def trade(n=1, session="2026-05-08", clock="09:33:10"):
    return {"n": str(n), "session": session, "entry_clock": clock, "exit_clock": "09:34:10",
            "entry": "100", "exit": "102.5", "stop": "95", "target": "105",
            "or_low": "90", "or_high": "98"}


def view(t, now):
    return {"session": t["session"], "trade_n": t["n"], "cursor_n": t["n"],
            "timestamp_utc": now.isoformat(), "top": "110", "bottom": "80",
            "entry": t["entry"], "exit": t["exit"], "stop": t["stop"], "target": t["target"],
            "or_low": t["or_low"], "or_high": t["or_high"],
            "first_time": f"{t['session']} 09:30", "last_time": f"{t['session']} 09:40"}


def args(**changes):
    values = dict(dates=[], from_session=None, trade=None, by="trade", redo=False)
    values.update(changes)
    return SimpleNamespace(**values)


class HistoricalCaptureTests(unittest.TestCase):
    def test_date_verification_rejects_correct_clock_wrong_day(self):
        self.assertTrue(journal.date_field_matches("08/05/2026 09:30 a. m.", "2026-05-08", "09:30"))
        self.assertFalse(journal.date_field_matches("07/05/2026 09:30 a. m.", "2026-05-08", "09:30"))
        self.assertFalse(journal.date_field_matches("08/05/2026 09:30 p. m.", "2026-05-08", "09:30"))

    def test_all_entries_survive_same_day_plan(self):
        rows = [trade(2, clock="09:34:00"), trade(1)]
        pending, skipped = journal.plan_rows(rows, args(), [], "feed")
        self.assertEqual([t["n"] for t in pending], ["1", "2"])
        self.assertEqual(skipped, 0)
        first, _ = journal.plan_rows(rows, args(by="session"), [], "feed")
        self.assertEqual([t["n"] for t in first], ["1"])

    def test_resume_requires_matching_row_feed_and_png_hash(self):
        t = trade()
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "capture.png"
            image.write_bytes(b"captured-image")
            event = {"status": "captured", "key": journal.capture_key(t), "feed_sha256": "feed",
                     "row_sha256": journal.row_fingerprint(t), "path": str(image),
                     "image_sha256": journal.sha256_file(image)}
            self.assertIsNotNone(journal.verified_capture(t, [event], "feed"))
            self.assertIsNone(journal.verified_capture(t, [event], "different-source"))
            self.assertIsNone(journal.verified_capture({**t, "entry": "100.25"}, [event], "feed"))
            image.write_bytes(b"modified-image")
            self.assertIsNone(journal.verified_capture(t, [event], "feed"))

    def test_manual_image_does_not_skip_unverified_entry_and_redo_does_not_overwrite(self):
        t = trade()
        with tempfile.TemporaryDirectory() as tmp:
            shots = Path(tmp)
            original = journal.capture_path(shots, t)
            original.write_bytes(b"manual")
            second = journal.capture_path(shots, t)
            self.assertNotEqual(original, second)
            self.assertTrue(second.name.endswith("_v002.png"))
            pending, _ = journal.plan_rows([t], args(), [], "feed")
            self.assertEqual(len(pending), 1)
            self.assertEqual(original.read_bytes(), b"manual")

    def test_interrupted_manifest_tail_can_be_resumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.jsonl"
            journal.append_event(path, {"status": "captured", "key": "first"})
            with path.open("a", encoding="utf-8") as stream:
                stream.write('{"status":"started"')
            journal.append_event(path, {"status": "captured", "key": "second"})
            self.assertEqual([e["key"] for e in journal.read_manifest(path)], ["first", "second"])

    def test_state_rejects_other_trade_stale_publisher_and_offscreen_exit(self):
        now = datetime.now(timezone.utc)
        t = trade()
        state = view(t, now)
        self.assertTrue(journal.state_validation(t["session"], t, state, now=now)[0])
        for change in ({"trade_n": "2"}, {"cursor_n": "2"}, {"entry": "100.25"}, {"exit": "102.75"},
                       {"timestamp_utc": (now - timedelta(seconds=30)).isoformat()},
                       {"top": "101"}, {"last_time": "2026-05-08 09:33"}):
            with self.subTest(change=change):
                self.assertFalse(journal.state_validation(t["session"], t, {**state, **change}, now=now)[0])

    def test_unknown_brackets_are_not_fabricated_or_required(self):
        now = datetime.now(timezone.utc)
        t = {**trade(), "stop": "0", "target": "0", "or_low": "0", "or_high": "0"}
        self.assertTrue(journal.state_validation(t["session"], t, view(t, now), now=now)[0])

    def test_loaded_indicator_feed_must_match_exact_csv_version(self):
        now = datetime.now(timezone.utc)
        t = trade()
        state = {**view(t, now), "csv_sha256": "ABC123"}
        self.assertTrue(journal.state_validation(t["session"], t, state, now=now, feed_sha256="abc123")[0])
        self.assertFalse(journal.state_validation(t["session"], t, state, now=now, feed_sha256="different")[0])

    def test_atas_structural_bracket_is_kept_separate_from_csv_estimate(self):
        now = datetime.now(timezone.utc)
        t = trade()
        state = {**view(t, now), "stop": "94", "target": "106",
                 "bracket_source": "reconstructed_atas_last_closed_proxy"}
        self.assertTrue(journal.state_validation(t["session"], t, state, now=now)[0])
        self.assertFalse(journal.state_validation(t["session"], t, {**state, "target": "107"}, now=now)[0])
        self.assertFalse(journal.state_validation(t["session"], t, {**state, "exit": "103"}, now=now)[0])

    def test_unknown_csv_or_can_be_reconstructed_but_known_or_has_grid_tolerance(self):
        now = datetime.now(timezone.utc)
        t = trade()
        state = view(t, now)
        self.assertTrue(journal.state_validation(t["session"], t, {**state, "or_low": "91.25"}, now=now)[0])
        self.assertFalse(journal.state_validation(t["session"], t, {**state, "or_low": "91.50"}, now=now)[0])
        t = {**t, "or_low": "0", "or_high": "0"}
        self.assertTrue(journal.state_validation(t["session"], t, state, now=now)[0])

    def test_price_frame_includes_real_exit_with_no_bracket(self):
        state = {"or_low": "0", "or_high": "0", "entry": "100", "exit": "125", "stop": "0", "target": "0"}
        self.assertAlmostEqual(journal.desired_price_range(state), 25 * 1.18)

    def test_filters_and_invalid_indices(self):
        rows = [trade(1), trade(2, "2026-05-11"), trade(3, "2026-05-11")]
        pending, _ = journal.plan_rows(rows, args(from_session="2026-05-11", trade=[3]), [], "feed")
        self.assertEqual([t["n"] for t in pending], ["3"])
        with self.assertRaises(ValueError):
            journal.plan_rows(rows, args(trade=[999]), [], "feed")
        with self.assertRaises(ValueError):
            journal.plan_rows([trade(1), trade(1)], args(), [], "feed")

    def test_replay_covers_all_exits_not_only_first_entry(self):
        self.assertEqual(journal.replay_end([trade()]), "09:50")
        self.assertEqual(journal.replay_end([trade(), {**trade(2), "exit_clock": "09:55:30"}]), "09:57")


if __name__ == "__main__":
    unittest.main()
