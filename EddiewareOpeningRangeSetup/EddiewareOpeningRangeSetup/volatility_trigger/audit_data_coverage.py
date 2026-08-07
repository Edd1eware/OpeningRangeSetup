from __future__ import annotations

import hashlib
import json
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import ATAS_MAGIC  # noqa: E402
from run_research import CONFIG_PATH, stage_dates  # noqa: E402
from src.vt_core import load_config  # noqa: E402


OUTPUT = ROOT / "artifacts" / "data_coverage"
COVERAGE_PATH = OUTPUT / "depth_coverage_manifest.csv"
SUMMARY_PATH = OUTPUT / "depth_coverage_summary.json"
MANIFEST_PATH = OUTPUT / "manifest.json"
SHA_PATH = OUTPUT / "depth_coverage_manifest.csv.sha256"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def inspect_cache_header(
    path: Path,
    expected_template: int,
) -> dict[str, object]:
    base = {
        "path": str(path),
        "bytes": int(path.stat().st_size) if path.is_file() else 0,
        "magic": None,
        "context_length": None,
        "template_id": None,
        "tick_size": None,
        "lot_size": None,
        "header_bytes": None,
        "has_blocks": False,
    }
    if not path.is_file():
        return {**base, "status": "MISSING"}

    with path.open("rb") as stream:
        prefix = stream.read(64)
    if len(prefix) < 8:
        return {**base, "status": "TRUNCATED_FILE_HEADER"}

    magic, context_length = struct.unpack_from("<ii", prefix, 0)
    base["magic"] = int(magic)
    base["context_length"] = int(context_length)
    if magic != ATAS_MAGIC:
        return {**base, "status": "INVALID_MAGIC"}
    if context_length <= 0 or context_length > 1024:
        return {**base, "status": "INVALID_CONTEXT_LENGTH"}

    header_bytes = 8 + context_length
    base["header_bytes"] = int(header_bytes)
    base["has_blocks"] = bool(base["bytes"] > header_bytes)
    if len(prefix) < min(header_bytes, 64):
        return {**base, "status": "TRUNCATED_CONTEXT"}
    if context_length < 25:
        return {**base, "status": "CONTEXT_TOO_SHORT"}

    template_id = int(prefix[8])
    tick_size, lot_size = struct.unpack_from("<dd", prefix, 9)
    base["template_id"] = template_id
    base["tick_size"] = float(tick_size)
    base["lot_size"] = float(lot_size)
    if template_id != expected_template:
        return {**base, "status": "UNEXPECTED_TEMPLATE"}
    if tick_size <= 0 or lot_size <= 0:
        status = (
            "HEADER_ONLY_ZERO_SCALE"
            if not base["has_blocks"]
            else "INVALID_SCALE_WITH_BLOCKS"
        )
        return {**base, "status": status}
    if not base["has_blocks"]:
        return {**base, "status": "HEADER_ONLY_VALID_SCALE"}
    return {**base, "status": "DATA_PRESENT"}


def build_coverage() -> tuple[pd.DataFrame, dict[str, object]]:
    config = load_config(CONFIG_PATH)
    cache_root = Path(config["cache_root"])
    dates = stage_dates("discovery", config)
    records: list[dict[str, object]] = []
    for ordinal, session_date in enumerate(dates, start=1):
        source_date = session_date - timedelta(days=1)
        source_dir = cache_root / source_date.strftime("%Y_%m_%d")
        trade = inspect_cache_header(source_dir / "trades.dat", 92)
        depth = inspect_cache_header(source_dir / "marketdepth.dat", 93)
        record: dict[str, object] = {
            "ordinal": ordinal,
            "session_date": session_date.isoformat(),
            "source_date": source_date.isoformat(),
        }
        record.update({f"trade_{key}": value for key, value in trade.items()})
        record.update({f"depth_{key}": value for key, value in depth.items()})
        records.append(record)

    frame = pd.DataFrame(records)
    depth_counts = {
        str(key): int(value)
        for key, value in frame["depth_status"].value_counts().items()
    }
    trade_counts = {
        str(key): int(value)
        for key, value in frame["trade_status"].value_counts().items()
    }
    depth_present = frame["depth_status"].eq("DATA_PRESENT")
    summary = {
        "audit_id": "POST_LB_2022_CACHE_HEADER_COVERAGE_V1",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "outcome_blind": True,
        "features_opened": False,
        "models_opened": False,
        "sessions_attempted": int(len(frame)),
        "min_session_date": str(frame["session_date"].min()),
        "max_session_date": str(frame["session_date"].max()),
        "trade_status_counts": trade_counts,
        "depth_status_counts": depth_counts,
        "depth_present_sessions": int(depth_present.sum()),
        "depth_present_share": float(depth_present.mean()),
        "first_depth_present_session": (
            str(frame.loc[depth_present, "session_date"].min())
            if depth_present.any()
            else None
        ),
        "last_depth_present_session": (
            str(frame.loc[depth_present, "session_date"].max())
            if depth_present.any()
            else None
        ),
        "two_distinct_111_warning": (
            "111 depth-present sessions is unrelated to the 111 LB events "
            "in the five-session smoke set"
        ),
    }
    return frame, summary


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame, summary = build_coverage()
    frame.to_csv(COVERAGE_PATH, index=False, lineterminator="\n")
    coverage_hash = sha256_file(COVERAGE_PATH)
    SHA_PATH.write_text(
        f"{coverage_hash}  {COVERAGE_PATH.name}\n",
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    manifest = {
        "audit_id": summary["audit_id"],
        "outcome_blind": True,
        "files": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in (COVERAGE_PATH, SHA_PATH, SUMMARY_PATH)
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps({"coverage_sha256": coverage_hash}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
