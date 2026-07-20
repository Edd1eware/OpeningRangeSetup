"""Select a deterministic, balanced 30-event MBO viability sample.

The sample is drawn only from the existing discovery split.  It reserves all
validation dates, balances A/B labels and BUY/SELL direction, and spreads the
selected observations through each calendar year instead of taking adjacent
dates.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


QUOTAS = {
    ("A_TRUE_ABSORPTION", 2022, "BUY"): 3,
    ("A_TRUE_ABSORPTION", 2022, "SELL"): 2,
    ("A_TRUE_ABSORPTION", 2023, "BUY"): 2,
    ("A_TRUE_ABSORPTION", 2023, "SELL"): 3,
    ("A_TRUE_ABSORPTION", 2024, "BUY"): 2,
    ("A_TRUE_ABSORPTION", 2024, "SELL"): 3,
    ("B_CLEAN_BREAKOUT", 2022, "BUY"): 2,
    ("B_CLEAN_BREAKOUT", 2022, "SELL"): 3,
    ("B_CLEAN_BREAKOUT", 2023, "BUY"): 3,
    ("B_CLEAN_BREAKOUT", 2023, "SELL"): 2,
    ("B_CLEAN_BREAKOUT", 2024, "BUY"): 3,
    ("B_CLEAN_BREAKOUT", 2024, "SELL"): 2,
}


def _evenly_spaced(group: pd.DataFrame, count: int) -> pd.DataFrame:
    group = group.sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    if len(group) < count:
        raise ValueError(f"Need {count} rows but only {len(group)} are available")
    positions = np.linspace(0, len(group) - 1, num=count, dtype=int)
    if len(set(positions.tolist())) != count:
        raise ValueError("Even-spacing produced duplicate positions")
    return group.iloc[positions]


def select_viability_sample(manifest: pd.DataFrame) -> pd.DataFrame:
    required = {"fecha", "BurstId", "split", "family_label_only"}
    missing = required.difference(manifest.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    frame = manifest.copy()
    if not frame["split"].eq("discovery").all():
        raise ValueError("Input must contain discovery rows only")
    frame["year"] = pd.to_datetime(frame["fecha"], errors="raise").dt.year
    frame["side"] = frame["BurstId"].str.extract(r"_(BUY|SELL)_", expand=False)
    if frame["side"].isna().any():
        raise ValueError("Could not parse BUY/SELL from every BurstId")

    selected = []
    for (family, year, side), count in QUOTAS.items():
        candidates = frame[
            frame["family_label_only"].eq(family)
            & frame["year"].eq(year)
            & frame["side"].eq(side)
        ]
        selected.append(_evenly_spaced(candidates, count))

    result = pd.concat(selected, ignore_index=True)
    result = result.sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    if len(result) != 30 or result["BurstId"].duplicated().any():
        raise ValueError("Viability sample must contain 30 unique events")
    return result.drop(columns=["year", "side"])


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=project / "contexto_features_atas" / "DATABENTO_MBO_PILOTO_DISCOVERY_AB_20260720.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "contexto_features_atas" / "DATABENTO_MBO_PILOTO_VIABILIDAD_30_AB_20260720.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=project / "contexto_features_atas" / "DATABENTO_MBO_PILOTO_VIABILIDAD_30_AB_20260720.json",
    )
    args = parser.parse_args()

    sample = select_viability_sample(pd.read_csv(args.source))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(args.output, index=False)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_policy": "DISCOVERY_ONLY_BALANCED_AB_SIDE_YEAR_EVENLY_SPACED",
        "request_rows": int(len(sample)),
        "unique_dates": int(sample["fecha"].nunique()),
        "families": sample["family_label_only"].value_counts().sort_index().to_dict(),
        "years": pd.to_datetime(sample["fecha"]).dt.year.value_counts().sort_index().to_dict(),
        "directions": sample["BurstId"].str.extract(r"_(BUY|SELL)_", expand=False).value_counts().sort_index().to_dict(),
        "validation_dates_used": 0,
        "data_downloaded_by_this_script": False,
        "output_csv": str(args.output),
    }
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
