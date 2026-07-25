"""Compare legacy and padded versions of the first two MBO outcome windows."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import pandas as pd


LOGICAL_COLUMNS = [
    "ts_recv",
    "ts_event",
    "rtype",
    "publisher_id",
    "instrument_id",
    "action",
    "side",
    "price",
    "size",
    "channel_id",
    "order_id",
    "flags",
    "ts_in_delta",
    "sequence",
]


def _read(path: Path) -> pd.DataFrame:
    frame = db.DBNStore.from_file(path).to_df().reset_index()
    for field in ("ts_recv", "ts_event"):
        frame[field] = pd.to_datetime(frame[field], utc=True)
    return frame


def _logical_sha(frame: pd.DataFrame) -> str:
    payload = frame.loc[:, LOGICAL_COLUMNS].to_csv(
        index=False, lineterminator="\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compare_pair(
    legacy_path: Path,
    padded_path: Path,
    decision: pd.Timestamp,
) -> dict:
    legacy = _read(legacy_path)
    padded = _read(padded_path)
    label_end = decision + pd.Timedelta(seconds=5)
    old_receive_end = label_end

    padded_common = padded.loc[padded["ts_recv"].lt(old_receive_end)].copy()
    common_exact = (
        len(legacy) == len(padded_common)
        and _logical_sha(legacy) == _logical_sha(padded_common)
    )
    padding = padded.loc[padded["ts_recv"].ge(old_receive_end)].copy()
    late_but_label_eligible = padding.loc[
        padding["ts_event"].lt(label_end)
    ].copy()
    late_t_eligible = late_but_label_eligible.loc[
        late_but_label_eligible["action"].astype(str).eq("T")
    ]
    return {
        "legacy_path": str(legacy_path),
        "padded_path": str(padded_path),
        "legacy_records": int(len(legacy)),
        "padded_records": int(len(padded)),
        "padded_common_receive_records": int(len(padded_common)),
        "common_receive_interval_exact": bool(common_exact),
        "legacy_logical_sha256": _logical_sha(legacy),
        "padded_common_logical_sha256": _logical_sha(padded_common),
        "transport_padding_records": int(len(padding)),
        "padding_records_with_ts_event_before_label_end": int(
            len(late_but_label_eligible)
        ),
        "padding_T_records_with_ts_event_before_label_end": int(
            len(late_t_eligible)
        ),
        "old_version_would_change_label_path": bool(len(late_t_eligible) > 0),
    }


def main() -> int:
    project = Path(__file__).resolve().parent
    base = project / "contexto_codex_claude" / "joint_ab_v4"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=base / "AB_V4_OUTCOME_FIRST2_PAD100_RECEIPT.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=base / "AB_V4_OUTCOME_FIRST2_PAD100_MANIFEST.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=base / "AB_V4_OUTCOME_FIRST2_PADDING_COMPARISON.json",
    )
    args = parser.parse_args()

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    manifest = pd.read_csv(args.manifest).set_index("request_id")
    rows = []
    for request_id, item in receipt["rows"].items():
        row = manifest.loc[request_id]
        result = compare_pair(
            Path(item["legacy_path"]),
            Path(item["path"]),
            pd.to_datetime(row["decision_utc"], utc=True),
        )
        rows.append(
            {
                "request_id": request_id,
                "fecha": str(row["fecha"]),
                **result,
            }
        )
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "all_common_receive_intervals_exact": all(
            row["common_receive_interval_exact"] for row in rows
        ),
        "total_transport_padding_records": sum(
            row["transport_padding_records"] for row in rows
        ),
        "total_late_label_eligible_records": sum(
            row["padding_records_with_ts_event_before_label_end"]
            for row in rows
        ),
        "total_late_label_eligible_T_records": sum(
            row["padding_T_records_with_ts_event_before_label_end"]
            for row in rows
        ),
        "any_old_label_path_would_change": any(
            row["old_version_would_change_label_path"] for row in rows
        ),
    }
    args.output.write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_common_receive_intervals_exact"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
