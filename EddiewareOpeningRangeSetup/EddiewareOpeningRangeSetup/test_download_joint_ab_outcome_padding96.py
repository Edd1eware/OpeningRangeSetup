from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import download_joint_ab_outcome_padding96 as downloader


def _row() -> pd.Series:
    decision = pd.Timestamp("2024-01-01T00:00:01Z")
    return pd.Series(
        {
            "start_utc": (decision - pd.Timedelta(milliseconds=100)).isoformat(),
            "decision_utc": decision.isoformat(),
            "label_end_utc_exclusive": (
                decision + pd.Timedelta(seconds=5)
            ).isoformat(),
            "end_utc_exclusive": (
                decision + pd.Timedelta(seconds=5, milliseconds=100)
            ).isoformat(),
            "symbols": "NQH4",
        }
    )


def test_normalize_accepts_exchange_time_before_receive_start() -> None:
    start = pd.Timestamp("2024-01-01T00:00:00.900Z")
    frame = pd.DataFrame(
        {
            "ts_recv": [start, start + pd.Timedelta(milliseconds=1)],
            "ts_event": [
                start - pd.Timedelta(milliseconds=2),
                start - pd.Timedelta(milliseconds=1),
            ],
            "sequence": [1, 2],
            "action": ["A", "A"],
            "side": ["B", "A"],
            "price": [100.0, 100.25],
            "size": [1, 1],
            "flags": [128, 128],
            "instrument_id": [1, 1],
        }
    )
    normalized = downloader._normalize(frame)
    assert normalized["ts_event"].min() < start
    assert normalized["ts_recv"].min() == start


def test_match_event_keeps_physical_last_trade() -> None:
    base = pd.Timestamp("2024-01-01T00:00:01Z")
    frame = pd.DataFrame(
        {
            "ts_recv": [base] * 4,
            "ts_event": [base] * 4,
            "sequence": [10, 10, 11, 11],
            "action": ["T", "F", "T", "C"],
            "side": ["B", "A", "B", "A"],
            "price": [100.0, 100.0, 100.25, 100.25],
            "size": [1, 1, 2, 2],
            "flags": [0, 0, 0, 128],
            "instrument_id": [1] * 4,
            "record_ordinal": np.arange(4),
        }
    )
    sales, summary = downloader._match_event_tables(frame)
    assert len(sales) == 1
    assert sales.iloc[0]["price"] == 100.25
    assert bool(summary.iloc[0]["closed"])
    assert int(summary.iloc[0]["sequence_count"]) == 2


def test_download_failure_moves_billable_temp_to_quarantine(
    tmp_path: Path, monkeypatch
) -> None:
    class Store:
        def to_file(self, path):
            Path(path).write_bytes(b"billable")

    class TimeSeries:
        def get_range(self, **kwargs):
            return Store()

    class Client:
        timeseries = TimeSeries()

    monkeypatch.setattr(
        downloader,
        "inspect_file",
        lambda path, row: (_ for _ in ()).throw(ValueError("bad")),
    )
    output = tmp_path / "out"
    output.mkdir()
    quarantine = output / "quarantine"
    row = _row()
    row["request_id"] = "request"
    row["dataset"] = "GLBX.MDP3"
    row["stype_in"] = "raw_symbol"
    row["stype_out"] = "instrument_id"
    try:
        downloader.download_one(Client(), row, output, quarantine)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected validation failure")
    files = list(quarantine.glob("*.dbn.zst"))
    assert len(files) == 1
    assert files[0].read_bytes() == b"billable"
