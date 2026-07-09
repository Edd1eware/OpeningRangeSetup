from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import lvn_OR_strategy_replay as runner


class LvnReplayRunnerTests(unittest.TestCase):
    def test_capture_validation_requires_csv_and_matching_marker(self) -> None:
        original_raw = runner.RAW_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                runner.RAW_DIR = Path(tmp)
                date = "2026-06-01"
                runner.raw_path(date).write_text(
                    "timestamp,symbol,price,bid_volume,ask_volume,volume\n"
                    "2026-06-01 09:30:00.000,NQ,100.5,10,12,22\n",
                    encoding="utf-8",
                )
                self.assertFalse(runner.inspect_capture(date)["complete"])
                runner.done_path(date).write_text(f"date={date}\nrows=1\n", encoding="utf-8")
                status = runner.inspect_capture(date)
                self.assertTrue(status["complete"])
                self.assertEqual(status["rows"], 1)
        finally:
            runner.RAW_DIR = original_raw

    def test_weekday_date_generation_is_inclusive(self) -> None:
        self.assertEqual(
            runner.weekday_dates("2026-07-02", "2026-07-06"),
            ["2026-07-02", "2026-07-03", "2026-07-06"],
        )


if __name__ == "__main__":
    unittest.main()

