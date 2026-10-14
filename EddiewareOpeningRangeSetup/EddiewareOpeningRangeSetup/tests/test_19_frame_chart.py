"""Calculos de encuadre sin acceder a ninguna ventana ni dispositivo de entrada."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


frame = module("frame_pure", "19_frame_chart.py")
journal = module("journal_pure", "19_journal_run.py")


def state(**changes):
    return {"region_right": "1400", "region_top": "0", "region_bottom": "700",
            "top": "160", "bottom": "80", "or_low": "100", "or_high": "110",
            "entry": "120", "exit": "125", "stop": "115", "target": "125", **changes}


def layout(**changes):
    return {"verified": True, "evidence": "test fixture, not a real UI calibration",
            "plot_offset_x": 20, "plot_offset_y": 30, "price_axis_offset_x": 25,
            "time_axis_bottom_offset": 40, "wheel_forward_direction": -1, **changes}


class FrameCalculationTests(unittest.TestCase):
    def test_geometry_uses_actual_container_not_trading_panel_width(self):
        full = frame.screen_geometry(state(region_right="1600"), (100, 200), (1680, 1000), layout())
        with_panel = frame.screen_geometry(state(), (100, 200), (1680, 1000), layout())
        self.assertEqual(full["price_axis"][0], 1745)
        self.assertEqual(with_panel["price_axis"][0], 1545)
        self.assertEqual(full["time_axis"][1], 1160)

    def test_bad_geometry_is_rejected_without_clamping_into_chart(self):
        with self.assertRaises(ValueError):
            frame.screen_geometry(state(region_right="1900"), (0, 0), (1680, 1000), layout())
        with self.assertRaises(ValueError):
            frame.screen_geometry(state(), (0, 0), (0, 0), layout())

    def test_scale_match_does_not_accept_hidden_or_uncentered_levels(self):
        goal = frame.vertical_goal(state())
        self.assertAlmostEqual(goal["center"], 112.5)
        r = goal["range"]
        bad = frame.vertical_status(state(top=str(160 + r / 2), bottom=str(160 - r / 2)), goal)
        self.assertTrue(bad["scale_ok"])
        self.assertFalse(bad["center_ok"])
        self.assertFalse(bad["contains"])
        good = frame.vertical_status(state(top=str(112.5 + r / 2), bottom=str(112.5 - r / 2)), goal)
        self.assertTrue(good["center_ok"] and good["contains"] and good["scale_ok"])

    def test_exit_is_inside_target_levels_without_assumed_bracket(self):
        goal = frame.vertical_goal(state(stop="0", target="0", exit="145"))
        self.assertEqual(goal["max"], 145)
        self.assertGreater(goal["range"], 45)

    def test_calibration_must_include_explicit_visual_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calibration.json"
            path.write_text(json.dumps(layout(verified=False)), encoding="utf-8")
            with self.assertRaises(ValueError):
                frame.load_calibration(path)
            path.write_text(json.dumps(layout()), encoding="utf-8")
            self.assertEqual(frame.load_calibration(path)["price_axis_offset_x"], 25)

    def test_time_goal_compares_full_dates_and_all_required_minutes(self):
        t = {"entry_clock": "09:34:16", "exit_clock": "09:37:39"}
        current = {"first_time": "2026-05-11 08:34", "last_time": "2026-05-11 09:04"}
        goal = journal.time_goal(current, "2026-05-11", t)
        self.assertFalse(goal["done"])
        self.assertEqual(goal["minutes_to_move"], 55)
        good = {"first_time": "2026-05-11 09:28", "last_time": "2026-05-11 09:58"}
        self.assertTrue(journal.time_goal(good, "2026-05-11", t)["done"])
        previous_day = {"first_time": "2026-05-08 09:28", "last_time": "2026-05-08 09:58"}
        self.assertFalse(journal.time_goal(previous_day, "2026-05-11", t)["done"])

    def test_time_goal_requires_or_and_exit_to_fit(self):
        t = {"entry_clock": "09:38:16", "exit_clock": "09:39:40"}
        narrow = {"first_time": "2026-05-11 09:35", "last_time": "2026-05-11 09:42"}
        with self.assertRaises(ValueError):
            journal.time_goal(narrow, "2026-05-11", t)
        missing_or = {"first_time": "2026-05-11 09:31", "last_time": "2026-05-11 10:01"}
        self.assertFalse(journal.time_goal(missing_or, "2026-05-11", t)["done"])


if __name__ == "__main__":
    unittest.main()
