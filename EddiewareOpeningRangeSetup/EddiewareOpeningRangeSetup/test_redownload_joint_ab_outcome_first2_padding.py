from __future__ import annotations

import pandas as pd

import redownload_joint_ab_outcome_first2_padding as redownload


def test_build_manifest_only_selects_two_and_adds_padding() -> None:
    rows = []
    for index, request_id in enumerate(sorted(redownload.TARGET_IDS)):
        decision = pd.Timestamp("2022-04-05T13:32:01Z") + pd.Timedelta(
            days=index
        )
        rows.append(
            {
                "request_id": request_id,
                "schema": "mbo",
                "fecha": decision.date().isoformat(),
                "decision_utc": decision.isoformat(),
                "start_utc": (
                    decision - pd.Timedelta(milliseconds=100)
                ).isoformat(),
                "end_utc_exclusive": (
                    decision + pd.Timedelta(seconds=5)
                ).isoformat(),
            }
        )
    manifest = redownload.build_manifest(pd.DataFrame(rows))
    assert len(manifest) == 2
    assert manifest["request_id"].str.endswith("_PAD100MS").all()
    label_end = pd.to_datetime(
        manifest["label_end_utc_exclusive"], utc=True
    )
    request_end = pd.to_datetime(
        manifest["end_utc_exclusive"], utc=True
    )
    assert (request_end - label_end == pd.Timedelta(milliseconds=100)).all()
