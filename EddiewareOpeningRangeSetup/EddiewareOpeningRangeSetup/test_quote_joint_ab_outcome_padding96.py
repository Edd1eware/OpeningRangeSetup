from __future__ import annotations

import pandas as pd

import quote_joint_ab_outcome_padding96 as quote


def test_pending_manifest_adds_only_end_padding() -> None:
    rows = []
    for index in range(98):
        request_id = (
            quote.LOST_REQUEST_ID if index == 2 else f"REQ_{index}"
        )
        rows.append(
            {
                "request_id": request_id,
                "fecha": f"2024-01-{(index % 28) + 1:02d}",
                "BurstId": f"LB_{index}",
                "schema": "mbo",
                "start_utc": "2024-01-01T13:30:59.900Z",
                "end_utc_exclusive": "2024-01-01T13:31:05.000Z",
            }
        )
    receipt = {"rows": {"REQ_0": {}, "REQ_1": {}}}
    pending = quote.build_pending_manifest(pd.DataFrame(rows), receipt)
    assert len(pending) == 96
    start = pd.to_datetime(pending.iloc[0]["start_utc"], utc=True)
    label_end = pd.to_datetime(
        pending.iloc[0]["label_end_utc_exclusive"], utc=True
    )
    request_end = pd.to_datetime(
        pending.iloc[0]["end_utc_exclusive"], utc=True
    )
    assert (request_end - label_end).total_seconds() == 0.1
    assert (request_end - start).total_seconds() == 5.2
