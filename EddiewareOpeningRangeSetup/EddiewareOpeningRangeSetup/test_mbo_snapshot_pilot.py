from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import databento as db
import pandas as pd

import download_databento_mbo_manifest as downloader
import prepare_mbo_snapshot_pilot as pilot
import resolve_databento_manifest_symbols as resolver


class SnapshotPilotTests(unittest.TestCase):
    def _candidate_frame(self) -> pd.DataFrame:
        rows = []
        dates = pd.bdate_range("2022-04-04", periods=1000)
        position = 0
        for year in pilot.YEARS:
            for side in pilot.SIDES:
                for family in pilot.CLEAN_FAMILIES:
                    created = 0
                    while created < 2:
                        day = dates[position]
                        position += 1
                        if day.year != year:
                            day = pd.Timestamp(f"{year}-04-{4 + created:02d}")
                        date_text = day.strftime("%Y-%m-%d")
                        if date_text in pilot.excluded_holidays():
                            continue
                        burst_id = f"LB_{year}_{side}_{family}_{created}"
                        rows.append(
                            {
                                "BurstId": burst_id,
                                "fecha": date_text,
                                "year": year,
                                "burst_side": side,
                                "family": family,
                                "burst_price": 15000.0,
                                "reference_level": 14999.0,
                                "causal_cutoff_utc": f"{date_text}T13:30:01.025000Z",
                                "burst_timestamp_utc": f"{date_text}T13:30:00.000000Z",
                                "selection_hash": pilot._stable_rank(burst_id),
                                "excluded_holiday": False,
                            }
                        )
                        created += 1
        return pd.DataFrame(rows)

    def test_signal_and_technical_selection_are_balanced(self) -> None:
        signal = pilot.select_signal_24(self._candidate_frame())
        technical = pilot.select_technical_6(signal)
        self.assertEqual(len(signal), 24)
        self.assertTrue(
            signal.groupby(["year", "burst_side", "family"]).size().eq(2).all()
        )
        self.assertEqual(len(technical), 6)
        self.assertEqual(
            technical["family"].value_counts().to_dict(),
            {"A_TRUE_ABSORPTION": 3, "B_CLEAN_BREAKOUT": 3},
        )

    def test_manifest_starts_at_midnight_and_uses_strict_cutoff(self) -> None:
        signal = pilot.select_signal_24(self._candidate_frame())
        manifest = pilot.build_manifest(signal, "SIGNAL_24")
        starts = pd.to_datetime(manifest["start_utc"], utc=True)
        decisions = pd.to_datetime(
            manifest["strategy_decision_timestamp_utc"], utc=True
        )
        ends = pd.to_datetime(manifest["end_utc_exclusive"], utc=True)
        inclusive = pd.to_datetime(
            manifest["causal_cutoff_utc_inclusive"], utc=True
        )
        self.assertTrue(starts.dt.hour.eq(0).all())
        self.assertTrue(ends.eq(decisions.dt.floor("ms")).all())
        self.assertTrue(inclusive.eq(ends - pd.to_timedelta(1, unit="ns")).all())
        self.assertTrue(manifest["require_snapshot"].all())
        self.assertTrue(manifest["holiday_exclusion_pass"].all())

    def test_downloader_request_preserves_supported_output_mapping(self) -> None:
        row = pd.Series(
            {
                "dataset": "GLBX.MDP3",
                "symbols": "NQ.v.0",
                "schema": "mbo",
                "start_utc": "2024-04-02T00:00:00Z",
                "end_utc_exclusive": "2024-04-02T13:30:01Z",
                "stype_in": "continuous",
                "stype_out": "instrument_id",
            }
        )
        kwargs = downloader.request_kwargs(row)
        self.assertEqual(kwargs["stype_out"], "instrument_id")
        self.assertEqual(kwargs["symbols"], ["NQ.v.0"])

    def test_snapshot_validator_requires_r_a_and_last(self) -> None:
        frame = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(
                    [
                        "2024-04-02T00:00:00Z",
                        "2024-04-01T20:00:00Z",
                    ],
                    utc=True,
                ),
                "flags": [
                    int(db.RecordFlags.F_SNAPSHOT),
                    int(db.RecordFlags.F_SNAPSHOT | db.RecordFlags.F_LAST),
                ],
                "action": ["R", "A"],
                "instrument_id": [1, 1],
            }
        )

        class Metadata:
            stype_out = "instrument_id"

        class Store:
            metadata = Metadata()

            def to_df(self) -> pd.DataFrame:
                return frame

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.dbn.zst"
            path.write_bytes(b"x")
            with patch.object(downloader.db.DBNStore, "from_file", return_value=Store()):
                result = downloader.inspect_dbn(
                    path,
                    "2024-04-02T13:30:00Z",
                    require_snapshot=True,
                    expected_stype_out="instrument_id",
                    expected_instrument_id=1,
                )
        self.assertEqual(result["snapshot_rows"], 2)
        self.assertEqual(result["snapshot_clear_rows"], 1)
        self.assertEqual(result["snapshot_add_rows"], 1)
        self.assertEqual(result["snapshot_last_rows"], 1)
        self.assertEqual(result["expected_instrument_id"], 1)

    def test_two_step_symbology_response_parser(self) -> None:
        payload = {
            "status": 0,
            "not_found": [],
            "result": {
                "NQ.v.0": [
                    {"d0": "2022-04-05", "d1": "2022-04-06", "s": "2895"}
                ]
            },
        }
        self.assertEqual(resolver._resolved_symbol(payload, "NQ.v.0"), "2895")


if __name__ == "__main__":
    unittest.main()
