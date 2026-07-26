"""Compute OR_ticks per OR_SOURCE_COUNTERSIGN.md (Codex normative spec).

Window W = [D 09:30:00, D 09:31:00) America/New_York, D = civil date of t0.
Eligible: frozen contract, action=='T', ts_event in W, ts_recv < t0, valid price.
ts_event decides candle membership; ts_recv is only an anti-lookahead guard.
Arithmetic in Databento fixed-price integers. Sealed regression test enforced.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from progress import track

BASE = Path(__file__).resolve().parent
V2 = BASE.parent
OUT = V2 / "output"
HANDOFF = (V2.parent / "mechanical_book_v1"
           / "MECHANICAL_BOOK_HANDOFF_AUDIT_98.csv")
SNAP = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_mbo\liquidity_burst_snapshot_discovery100_20260723")

NY = "America/New_York"
TICK_FIXED = 250_000_000          # 0.25 in Databento 1e-9 fixed price
UNDEF_PRICE = 9223372036854775807
REGRESSION = {"fecha": "2022-04-05", "trades": 3726,
              "or_high": 15129.50, "or_low": 15095.75, "or_ticks": 135}


def cutoff_of(row: pd.Series) -> pd.Timestamp:
    strict = row.get("strict_feature_cutoff_utc_exclusive")
    value = strict if (pd.notna(strict) and str(strict).strip()
                       and str(strict).lower() != "nan") else row["decision_utc"]
    return pd.to_datetime(value, utc=True)


def or_for_event(row: pd.Series) -> dict:
    burst = str(row["BurstId"])
    result = {"BurstId": burst, "fecha": str(row["fecha"]),
              "OR_ticks": math.nan, "OR_high": math.nan, "OR_low": math.nan,
              "n_trades": 0, "n_invalid_price": 0, "OR_reason": ""}
    t0 = cutoff_of(row)

    # window boundaries: build local wall time, localize with IANA zone (DST safe)
    day = t0.tz_convert(NY).normalize()
    w_start = (day + pd.Timedelta(hours=9, minutes=30))
    w_end = (day + pd.Timedelta(hours=9, minutes=31))
    if w_end.tz_convert("UTC") > t0:
        result["OR_reason"] = "OR_WINDOW_NOT_PRE_T0"
        return result

    files = list(SNAP.glob(f"*{burst}*.mbo.dbn.zst"))
    if not files:
        result["OR_reason"] = "OR_SOURCE_FILE_MISSING"
        return result
    try:
        frame = db.DBNStore.from_file(files[0]).to_df(price_type="fixed")
    except Exception:  # noqa: BLE001
        result["OR_reason"] = "OR_SOURCE_DECODE_ERROR"
        return result
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()

    frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True,
                                       format="mixed")
    frame["ts_recv"] = pd.to_datetime(frame["ts_recv"], utc=True,
                                      format="mixed")
    eligible = frame[
        (frame["action"].astype(str) == "T")
        & (frame["ts_event"] >= w_start.tz_convert("UTC"))
        & (frame["ts_event"] < w_end.tz_convert("UTC"))
        & (frame["ts_recv"] < t0)
    ]
    if eligible.empty:
        result["OR_reason"] = "OR_NO_VALID_TRADE"
        return result

    price = eligible["price"].to_numpy()
    valid = np.array([
        (p is not None) and (not pd.isna(p)) and int(p) != UNDEF_PRICE
        and int(p) > 0 for p in price])
    result["n_invalid_price"] = int((~valid).sum())
    price = price[valid]
    if price.size == 0:
        result["OR_reason"] = "OR_NO_VALID_TRADE"
        return result

    ints = np.array([int(p) for p in price], dtype=np.int64)
    if np.any(ints % TICK_FIXED != 0):
        result["OR_reason"] = "OR_OFF_TICK_PRICE"
        return result

    hi, lo = int(ints.max()), int(ints.min())
    result.update({
        "OR_ticks": int((hi - lo) // TICK_FIXED),
        "OR_high": hi * 1e-9, "OR_low": lo * 1e-9,
        "n_trades": int(price.size), "OR_reason": "OK",
    })
    return result


def main() -> int:
    handoff = pd.read_csv(HANDOFF).sort_values(
        ["fecha", "BurstId"]).reset_index(drop=True)
    rows = [or_for_event(row) for _, row in
            track(list(handoff.iterrows()), label="OR 09:30 (98 sesiones)")]
    frame = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)

    # sealed regression test
    ref = frame[frame["fecha"] == REGRESSION["fecha"]]
    if ref.empty:
        raise SystemExit("Regression date missing")
    got = ref.iloc[0]
    checks = {
        "trades": int(got["n_trades"]) == REGRESSION["trades"],
        "or_high": abs(float(got["OR_high"]) - REGRESSION["or_high"]) < 1e-6,
        "or_low": abs(float(got["OR_low"]) - REGRESSION["or_low"]) < 1e-6,
        "or_ticks": int(got["OR_ticks"]) == REGRESSION["or_ticks"],
    }
    if not all(checks.values()):
        print(json.dumps({"REGRESSION": "FAIL", "checks": checks,
                          "got": {k: str(got[k]) for k in
                                  ("n_trades", "OR_high", "OR_low",
                                   "OR_ticks")}}, indent=2))
        raise SystemExit("Regression test FAILED - halting per countersign")

    frame.to_csv(OUT / "V2_OR_TICKS_98.csv", index=False)
    summary = {
        "information_status": "OR_TICKS_COMPUTED_NO_OUTCOME",
        "regression": "PASS",
        "n_ok": int((frame["OR_reason"] == "OK").sum()),
        "reasons": frame["OR_reason"].value_counts().to_dict(),
        "or_ticks_min": int(frame.loc[frame["OR_reason"] == "OK",
                                      "OR_ticks"].min()),
        "or_ticks_median": float(frame.loc[frame["OR_reason"] == "OK",
                                           "OR_ticks"].median()),
        "or_ticks_max": int(frame.loc[frame["OR_reason"] == "OK",
                                      "OR_ticks"].max()),
    }
    (OUT / "V2_OR_SUMMARY.json").write_text(json.dumps(summary, indent=2),
                                            encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
