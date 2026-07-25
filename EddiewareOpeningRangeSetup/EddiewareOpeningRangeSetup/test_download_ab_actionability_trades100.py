from __future__ import annotations

import pandas as pd

import download_ab_actionability_trades100 as downloader


def test_manifest_has_fixed_window_and_rollover_overrides() -> None:
    rows = []
    for index in range(100):
        fecha = (
            "2022-06-13"
            if index == 0
            else "2023-06-13"
            if index == 1
            else f"2024-01-{(index % 28) + 1:02d}"
        )
        rows.append(
            {
                "fecha": fecha,
                "BurstId": f"LB_{index}",
                "family_label_only": "A_TRUE_ABSORPTION",
                "burst_side": "BUY",
                "strategy_decision_timestamp_utc": (
                    f"{fecha}T13:31:01.123000Z"
                ),
                "resolved_raw_symbol": "NQM2" if index == 0 else "NQM3",
            }
        )
    manifest = downloader.build_manifest(pd.DataFrame(rows))
    assert len(manifest) == 100
    assert manifest["request_id"].nunique() == 100
    assert manifest.loc[0, "symbols"] == "NQU2"
    assert manifest.loc[1, "symbols"] == "NQU3"
    assert int(manifest["rollover_override_applied"].sum()) == 2
    assert manifest["window_milliseconds"].eq(1100).all()
    start = pd.to_datetime(manifest.loc[2, "start_utc"], utc=True)
    decision = pd.to_datetime(manifest.loc[2, "decision_utc"], utc=True)
    end = pd.to_datetime(manifest.loc[2, "end_utc_exclusive"], utc=True)
    assert (decision - start).total_seconds() == 0.1
    assert (end - decision).total_seconds() == 1.0

