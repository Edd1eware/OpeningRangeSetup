"""Free cost estimate (metadata.get_cost) for the bounded +65s MBP-1 fetch.

No data is downloaded here. Builds the 98-event manifest and quotes each.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import databento as db
import pandas as pd

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parents[2]
HANDOFF = (BASE.parents[1] / "mechanical_book_v1"
           / "MECHANICAL_BOOK_HANDOFF_AUDIT_98.csv")
RESOLVED = (PROJECT / "contexto_features_atas"
            / "DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_RESOLVED_20260723.csv")
KEY_FILE = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
                r"\databento_api_key.txt")

DATASET = "GLBX.MDP3"
SCHEMA = "mbp-1"
STYPE = "raw_symbol"
PRE_S = 64.000
POST_S = 65.050


def build_manifest() -> pd.DataFrame:
    m = pd.read_csv(HANDOFF).sort_values(["fecha", "BurstId"]).reset_index(
        drop=True)
    if "resolved_raw_symbol" not in m.columns:
        res = pd.read_csv(RESOLVED)[["BurstId", "resolved_raw_symbol"]]
        m = m.merge(res, on="BurstId", how="left", validate="one_to_one")
    if m["resolved_raw_symbol"].isna().any():
        missing = m.loc[m["resolved_raw_symbol"].isna(), "BurstId"].tolist()
        raise ValueError(f"Unresolved symbols: {missing}")
    strict = pd.to_datetime(m["strict_feature_cutoff_utc_exclusive"],
                            utc=True, errors="coerce", format="ISO8601")
    decision = pd.to_datetime(m["decision_utc"], utc=True, errors="coerce",
                              format="ISO8601")
    cut = strict.fillna(decision)
    if cut.isna().any():
        raise ValueError(f"NaN cutoff: {m.loc[cut.isna(),'BurstId'].tolist()}")
    m["start_utc"] = (cut + pd.Timedelta(seconds=PRE_S)).dt.strftime(
        "%Y-%m-%dT%H:%M:%S.%f") + "Z"
    m["end_utc_exclusive"] = (cut + pd.Timedelta(seconds=POST_S)).dt.strftime(
        "%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return m[["BurstId", "fecha", "resolved_raw_symbol",
              "start_utc", "end_utc_exclusive"]]


def main() -> int:
    manifest = build_manifest()
    manifest.to_csv(BASE / "MH_DOWNLOAD_MANIFEST_98.csv", index=False)
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    client = db.Historical(key)
    rows = []
    total = 0.0
    for i, row in manifest.iterrows():
        for attempt in range(4):
            try:
                cost = float(client.metadata.get_cost(
                    dataset=DATASET, symbols=[str(row["resolved_raw_symbol"])],
                    schema=SCHEMA, start=str(row["start_utc"]),
                    end=str(row["end_utc_exclusive"]), stype_in=STYPE))
                break
            except Exception as e:  # noqa
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        total += cost
        rows.append({"BurstId": row["BurstId"], "symbol":
                     row["resolved_raw_symbol"], "cost_usd": cost})
        if (i + 1) % 20 == 0:
            print(f"[{i+1}/98] running total ${total:.4f}", flush=True)
        time.sleep(0.05)
    detail = pd.DataFrame(rows)
    detail.to_csv(BASE / "MH_COST_DETAIL_98.csv", index=False)
    summary = {"n": int(len(detail)), "schema": SCHEMA, "dataset": DATASET,
               "window_s": [PRE_S, POST_S],
               "total_cost_usd": round(total, 6),
               "max_single_usd": round(float(detail["cost_usd"].max()), 6)}
    (BASE / "MH_COST_SUMMARY.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
