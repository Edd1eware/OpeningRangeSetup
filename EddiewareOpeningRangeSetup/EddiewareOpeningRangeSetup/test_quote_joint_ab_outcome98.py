from __future__ import annotations

import pandas as pd

import quote_joint_ab_outcome98 as quote


def test_manifest_is_98_sessions_times_two_schemas() -> None:
    rows = []
    excluded = ["2022-06-13", "2023-06-13"]
    dates = excluded + [
        f"2024-{(index // 28) + 1:02d}-{(index % 28) + 1:02d}"
        for index in range(98)
    ]
    for index, fecha in enumerate(dates):
        rows.append(
            {
                "fecha": fecha,
                "BurstId": f"LB_{index}",
                "burst_side": "BUY" if index % 2 == 0 else "SELL",
                "strategy_decision_timestamp_utc": (
                    f"{fecha}T13:31:01.123000Z"
                ),
                "resolved_raw_symbol": "NQM4",
            }
        )
    manifest = quote.build_manifest(pd.DataFrame(rows))
    assert len(manifest) == 196
    assert set(manifest["schema"]) == {"trades", "mbo"}
    assert manifest.groupby("schema").size().eq(98).all()
    assert manifest["window_milliseconds"].eq(5100).all()
    start = pd.to_datetime(manifest.iloc[0]["start_utc"], utc=True)
    decision = pd.to_datetime(manifest.iloc[0]["decision_utc"], utc=True)
    end = pd.to_datetime(manifest.iloc[0]["end_utc_exclusive"], utc=True)
    assert (decision - start).total_seconds() == 0.1
    assert (end - decision).total_seconds() == 5.0
