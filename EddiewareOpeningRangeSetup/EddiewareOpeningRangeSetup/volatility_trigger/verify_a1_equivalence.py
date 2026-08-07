from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

from run_research import (
    CONFIG_PATH,
    ROOT,
    load_session,
    session_audit,
)
from src.vt_core import (
    build_session_candidates,
    causalize_trade_timestamps,
    load_config,
)


REFERENCE_DATES = (
    date(2022, 8, 1),
    date(2022, 8, 3),
    date(2022, 8, 4),
    date(2022, 8, 5),
)


def main() -> int:
    config = load_config(CONFIG_PATH)
    cache_root = Path(config["cache_root"])
    reference_root = ROOT / "artifacts" / "smoke" / "session_cache"
    records: list[dict[str, object]] = []

    for session_date in REFERENCE_DATES:
        started = time.perf_counter()
        context, raw_rows, source = load_session(
            session_date,
            cache_root,
        )
        rows, timestamp_qc = causalize_trade_timestamps(
            raw_rows,
            config["timestamp_qc"],
        )
        audit = session_audit(
            session_date,
            context,
            rows,
            source,
            timestamp_qc,
        )
        bursts, actual = build_session_candidates(
            rows,
            session_date,
            config,
        )
        stem = session_date.isoformat()
        expected = pd.read_parquet(
            reference_root / f"{stem}_candidates.parquet"
        )
        pd.testing.assert_frame_equal(
            actual,
            expected,
            check_dtype=True,
            check_exact=True,
            check_like=False,
        )
        expected_bursts = json.loads(
            (
                reference_root / f"{stem}_bursts.json"
            ).read_text(encoding="utf-8")
        )
        actual_bursts = [asdict(value) for value in bursts]
        if actual_bursts != expected_bursts:
            raise AssertionError(f"burst mismatch: {stem}")
        records.append(
            {
                "session_date": stem,
                "status": "EXACT_PASS",
                "rows": len(actual),
                "bursts": len(bursts),
                "raw_timestamp_backtracks": audit[
                    "raw_timestamp_backtracks"
                ],
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
        print(json.dumps(records[-1]), flush=True)

    result = {
        "status": "EXACT_PASS",
        "sessions": len(records),
        "candidate_rows": sum(int(row["rows"]) for row in records),
        "liquidity_bursts": sum(int(row["bursts"]) for row in records),
        "records": records,
    }
    output = ROOT / "artifacts" / "equivalence"
    output.mkdir(parents=True, exist_ok=True)
    (output / "A1_equivalence.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
