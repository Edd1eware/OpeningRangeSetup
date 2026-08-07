from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from run_regime_discovery_target_v3 import (  # noqa: E402
    cache_guard,
    excluded_audit,
    process_metrics,
)


def test_excluded_session_is_not_recorded_as_zero_lb():
    row = SimpleNamespace(
        session_date="2022-04-04",
        depth_status="HEADER_ONLY_ZERO_SCALE",
        trade_status="DATA_PRESENT",
        trade_path="trades.dat",
        depth_path="marketdepth.dat",
    )
    audit = excluded_audit(row)
    assert audit["status"] == "EXCLUDED_DEPTH_HEADER_ONLY_ZERO_SCALE"
    assert audit["liquidity_bursts"] is None
    assert audit["valid_reference_bursts"] is None


def test_process_coverage_gate_counts_unexplained_failure():
    coverage = pd.DataFrame(
        [
            {
                "session_date": "2022-08-01",
                "trade_status": "DATA_PRESENT",
                "depth_status": "DATA_PRESENT",
            },
            {
                "session_date": "2022-08-02",
                "trade_status": "DATA_PRESENT",
                "depth_status": "DATA_PRESENT",
            },
        ]
    )
    audits = pd.DataFrame(
        [
            {
                "session_date": "2022-08-01",
                "status": "PASS",
            },
            {
                "session_date": "2022-08-02",
                "status": "PROCESS_ERROR",
            },
        ]
    )
    metrics = process_metrics(audits, coverage)
    assert metrics["eligible_after_frozen_qc_sessions"] == 2
    assert metrics["evaluated_eligible_sessions"] == 1
    assert metrics["evaluated_share_eligible_after_frozen_qc"] == 0.5
    assert not metrics["process_coverage_pass"]


def test_cache_guard_requires_matching_freeze(tmp_path):
    cache_guard(tmp_path, "ABC")
    marker = tmp_path / "RUN_FREEZE_SHA256.txt"
    assert marker.read_text(encoding="utf-8").strip() == "ABC"
    cache_guard(tmp_path, "ABC")
    with pytest.raises(RuntimeError, match="marker mismatch"):
        cache_guard(tmp_path, "DEF")
