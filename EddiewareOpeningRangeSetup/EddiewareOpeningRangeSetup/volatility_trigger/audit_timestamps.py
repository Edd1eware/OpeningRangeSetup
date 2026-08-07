from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from run_research import (
    CONFIG_PATH,
    ROOT,
    load_cache_window,
    load_session,
    stage_dates,
)
from src.vt_core import (
    TICKS_PER_MILLISECOND,
    load_config,
    session_bounds,
)


def audit_stage(stage: str, source_kind: str) -> pd.DataFrame:
    config = load_config(CONFIG_PATH)
    cache_root = Path(config["cache_root"])
    records: list[dict[str, object]] = []
    dates = stage_dates(stage, config)

    for ordinal, session_date in enumerate(dates, start=1):
        try:
            if source_kind == "trade":
                _, rows, source = load_session(session_date, cache_root)
            else:
                source_date = session_date - timedelta(days=1)
                source = (
                    cache_root
                    / source_date.strftime("%Y_%m_%d")
                    / "marketdepth.dat"
                )
                bounds = session_bounds(session_date)
                _, rows = load_cache_window(
                    source,
                    start_ticks=bounds["session_start"],
                    end_ticks=bounds["load_end"],
                )
            differences = np.diff(rows["ticks"].astype(np.int64))
            negative = differences[differences < 0]
            records.append(
                {
                    "session_date": session_date.isoformat(),
                    "source": str(source),
                    "trade_rows": int(len(rows)),
                    "backtrack_count": int(len(negative)),
                    "largest_backtrack_ms": (
                        float(-negative.min() / TICKS_PER_MILLISECOND)
                        if len(negative)
                        else 0.0
                    ),
                    "status": "PASS",
                    "reason": "",
                }
            )
        except Exception as exc:
            records.append(
                {
                    "session_date": session_date.isoformat(),
                    "source": "",
                    "trade_rows": 0,
                    "backtrack_count": 0,
                    "largest_backtrack_ms": 0.0,
                    "status": "UNREADABLE",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
        if ordinal % 20 == 0 or ordinal == len(dates):
            affected = sum(
                int(record["backtrack_count"]) > 0 for record in records
            )
            print(
                json.dumps(
                    {
                        "stage": stage,
                        "source_kind": source_kind,
                        "processed": ordinal,
                        "total": len(dates),
                        "sessions_with_backtracks": affected,
                    }
                ),
                flush=True,
            )

    result = pd.DataFrame(records)
    output = ROOT / "artifacts" / "qc"
    output.mkdir(parents=True, exist_ok=True)
    stem = f"{stage}_{source_kind}_timestamp"
    result.to_csv(output / f"{stem}_audit.csv", index=False)
    summary = {
        "stage": stage,
        "source_kind": source_kind,
        "sessions": len(result),
        "readable_sessions": int((result["status"] == "PASS").sum()),
        "sessions_with_backtracks": int((result["backtrack_count"] > 0).sum()),
        "total_backtracks": int(result["backtrack_count"].sum()),
        "largest_backtrack_ms": float(result["largest_backtrack_ms"].max()),
    }
    (output / f"{stem}_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Outcome-blind timestamp integrity audit."
    )
    parser.add_argument("stage", choices=("smoke", "discovery"))
    parser.add_argument(
        "--source",
        choices=("trade", "depth"),
        default="trade",
    )
    arguments = parser.parse_args()
    audit_stage(arguments.stage, arguments.source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
