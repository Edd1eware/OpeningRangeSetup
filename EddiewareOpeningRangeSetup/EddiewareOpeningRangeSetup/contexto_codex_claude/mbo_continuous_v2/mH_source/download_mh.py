"""Bounded MBP-1 fetch for mH, per MH_SOURCE_ADDENDUM_SIGNED.md.

Frozen spec: GLBX.MDP3 / mbp-1 / raw_symbol / [cutoff+64.000s, cutoff+65.050s).
Hard cost cap USD 5.00. Writes one DBN per event plus a SHA-256 receipt.
Downloads only; mH is computed in a separate step.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import databento as db
import pandas as pd

from progress import track

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw_mbp1"
KEY_FILE = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
                r"\databento_api_key.txt")
DATASET = "GLBX.MDP3"
SCHEMA = "mbp-1"
STYPE = "raw_symbol"
COST_CAP_USD = 5.00
ADDENDUM_SHA = "f4c5637eea52a4d982281cdc0088ffc3935567246847bb65c8f1f77091df9395"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    addendum = BASE / "MH_SOURCE_ADDENDUM_SIGNED.md"
    if sha256_file(addendum) != ADDENDUM_SHA:
        raise SystemExit("Addendum hash mismatch - refusing to download")

    cost = json.loads((BASE / "MH_COST_SUMMARY.json").read_text())
    if cost["total_cost_usd"] > COST_CAP_USD:
        raise SystemExit(
            f"Quoted {cost['total_cost_usd']} exceeds cap {COST_CAP_USD}")

    manifest = pd.read_csv(BASE / "MH_DOWNLOAD_MANIFEST_98.csv")
    if len(manifest) != 98:
        raise SystemExit(f"Manifest must have 98 rows, got {len(manifest)}")
    RAW.mkdir(exist_ok=True)

    client = db.Historical(KEY_FILE.read_text(encoding="utf-8").strip())
    receipt = []
    for _, row in track(list(manifest.iterrows()), label="descarga MBP-1 +65s"):
        burst = str(row["BurstId"])
        out = RAW / f"{burst}.mbp1.dbn.zst"
        if out.exists() and out.stat().st_size > 0:
            receipt.append({"BurstId": burst, "file": out.name,
                            "bytes": out.stat().st_size,
                            "sha256": sha256_file(out), "cached": True})
            continue
        last_error = None
        for attempt in range(4):
            try:
                store = client.timeseries.get_range(
                    dataset=DATASET, symbols=[str(row["resolved_raw_symbol"])],
                    schema=SCHEMA, start=str(row["start_utc"]),
                    end=str(row["end_utc_exclusive"]), stype_in=STYPE)
                store.to_file(out)
                last_error = None
                break
            except Exception as error:  # noqa: BLE001
                last_error = error
                time.sleep(1.5 * (attempt + 1))
        if last_error is not None:
            raise RuntimeError(f"Download failed for {burst}: {last_error}")
        receipt.append({"BurstId": burst, "file": out.name,
                        "bytes": out.stat().st_size,
                        "sha256": sha256_file(out), "cached": False})
        time.sleep(0.05)

    frame = pd.DataFrame(receipt)
    frame.to_csv(BASE / "MH_DOWNLOAD_RECEIPT_FILES.csv", index=False)
    summary = {
        "information_status": "MH_RAW_DOWNLOADED_NO_OUTCOME",
        "dataset": DATASET, "schema": SCHEMA, "stype_in": STYPE,
        "n_files": int(len(frame)),
        "total_bytes": int(frame["bytes"].sum()),
        "quoted_cost_usd": cost["total_cost_usd"],
        "cost_cap_usd": COST_CAP_USD,
        "addendum_sha256": ADDENDUM_SHA,
        "empty_files": frame.loc[frame["bytes"] <= 0, "BurstId"].tolist(),
    }
    (BASE / "MH_DOWNLOAD_RECEIPT.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
