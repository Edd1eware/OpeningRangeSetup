"""Build Y_60 and run the single frozen discovery endpoint.

Per MH_SOURCE_ADDENDUM_SIGNED.md + OR_SOURCE_COUNTERSIGN.md:
  mH = midpoint of last complete BBO with ts_recv <= tH (staleness <= 1s),
       from the newly downloaded MBP-1.
  m1 = midpoint of last complete BBO before t1, from the SEALED MBO.
  Y_60 = sigma * [(mH - m1)/delta_p] / max(OR_ticks, 1)

Endpoint (single shot, frozen): rho_Spearman(S, Y_60) on discovery 2022-2023.
Success: rho_hat >= 0.25 AND IC95_low > 0. Bootstrap 10,000 by session,
seed 0x22f9cadf098b1625. No alternative endpoint, no second attempt.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from progress import track

BASE = Path(__file__).resolve().parent
V2 = BASE.parent
OUT = V2 / "output"
RAW = BASE / "raw_mbp1"
HANDOFF = (V2.parent / "mechanical_book_v1"
           / "MECHANICAL_BOOK_HANDOFF_AUDIT_98.csv")
sys.path.insert(0, str(V2))

TICK_SIZE = 0.25
FIXED = 1e-9
UNDEF = 9223372036854775807
T1_OFFSET = 5.000
H = 60.000
MAX_STALE = 1.000
SEED = 0x22f9cadf098b1625
N_BOOT = 10000
RHO_MIN = 0.25
MIN_PAIRS = 56
DISCOVERY_YEARS = {2022, 2023}


def cutoff_of(row: pd.Series) -> pd.Timestamp:
    strict = row.get("strict_feature_cutoff_utc_exclusive")
    value = strict if (pd.notna(strict) and str(strict).strip()
                       and str(strict).lower() != "nan") else row["decision_utc"]
    return pd.to_datetime(value, utc=True)


def mh_from_mbp1(path: Path, t_h: pd.Timestamp) -> tuple[float, str]:
    if not path.exists() or path.stat().st_size == 0:
        return math.nan, "MH_FILE_MISSING"
    try:
        frame = db.DBNStore.from_file(path).to_df(price_type="fixed")
    except Exception:  # noqa: BLE001
        return math.nan, "MH_DECODE_ERROR"
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    if frame.empty:
        return math.nan, "MH_EMPTY"
    for col in ("bid_px_00", "ask_px_00", "ts_recv"):
        if col not in frame.columns:
            return math.nan, f"MH_MISSING_{col}"
    frame["ts_recv"] = pd.to_datetime(frame["ts_recv"], utc=True,
                                      format="mixed")
    frame = frame[frame["ts_recv"] <= t_h]
    if frame.empty:
        return math.nan, "MH_NO_RECORD_BEFORE_TH"
    bid = frame["bid_px_00"].to_numpy()
    ask = frame["ask_px_00"].to_numpy()
    ok = np.array([
        (not pd.isna(b)) and (not pd.isna(a)) and int(b) != UNDEF
        and int(a) != UNDEF and int(b) > 0 and int(a) > 0 and int(a) >= int(b)
        for b, a in zip(bid, ask)])
    if not ok.any():
        return math.nan, "MH_NO_COMPLETE_BBO"
    idx = int(np.flatnonzero(ok)[-1])
    stale = (t_h - frame["ts_recv"].iloc[idx]).total_seconds()
    if stale < 0 or stale > MAX_STALE:
        return math.nan, "MH_STALE"
    return (int(bid[idx]) + int(ask[idx])) / 2.0 * FIXED, "OK"


def m1_from_sealed(row: pd.Series) -> tuple[float, str]:
    """Last complete BBO strictly before t1, rebuilt from the sealed MBO."""
    from v2_extractor import (best_price, logical_packets, normalize_mbo,
                              update_level)
    levels: dict = {}
    for item in pd.read_parquet(
            Path(row["state_cache_path"])).itertuples(index=False):
        update_level(levels, str(item.side), float(item.price),
                     float(item.size))

    def mid() -> float:
        bid, ask = best_price(levels, "B"), best_price(levels, "A")
        if math.isfinite(bid) and math.isfinite(ask) and ask >= bid:
            return (bid + ask) / 2.0
        return math.nan

    last = mid()
    try:
        outcome = normalize_mbo(
            db.DBNStore.from_file(Path(row["outcome_path"])).to_df())
        packets, _ = logical_packets(outcome, int(row["pre_overlap_records"]),
                                     cutoff_of(row), T1_OFFSET)
    except Exception:  # noqa: BLE001
        return math.nan, "M1_DECODE_ERROR"
    state: dict = {}
    for item in pd.read_parquet(
            Path(row["state_cache_path"])).itertuples(index=False):
        state[int(item.order_id)] = (str(item.side), float(item.price),
                                     float(item.size))
    for _close, packet in packets:
        for value in packet:
            action = str(value.action)
            if action in {"F", "T", "N"}:
                continue
            oid = int(value.order_id)
            side = str(value.side)
            price = float(value.price) if pd.notna(value.price) else math.nan
            size = float(value.size)
            if action == "R":
                state.clear()
                levels.clear()
                continue
            if action == "A":
                old = state.get(oid)
                if old is not None:
                    update_level(levels, old[0], old[1], -old[2])
                state[oid] = (side, price, size)
                update_level(levels, side, price, size)
            elif action == "M":
                old = state.get(oid)
                if old is not None:
                    update_level(levels, old[0], old[1], -old[2])
                state[oid] = (side, price, size)
                update_level(levels, side, price, size)
            elif action == "C":
                old = state.get(oid)
                if old is None:
                    continue
                removed = min(size, old[2])
                update_level(levels, old[0], old[1], -removed)
                rest = old[2] - removed
                if rest <= 0:
                    state.pop(oid, None)
                else:
                    state[oid] = (old[0], old[1], rest)
        value_mid = mid()
        if math.isfinite(value_mid):
            last = value_mid
    return (last, "OK") if math.isfinite(last) else (math.nan,
                                                     "M1_NO_COMPLETE_BBO")


def bootstrap_ci(s: np.ndarray, y: np.ndarray, sessions: np.ndarray):
    rng = np.random.default_rng(SEED)
    uniq = np.unique(sessions)
    by = {u: np.flatnonzero(sessions == u) for u in uniq}
    stats = []
    for _ in range(N_BOOT):
        picked = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([by[p] for p in picked])
        value = spearmanr(s[idx], y[idx]).statistic
        if np.isfinite(value):
            stats.append(value)
    arr = np.array(stats)
    return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


def main() -> int:
    handoff = pd.read_csv(HANDOFF).sort_values(
        ["fecha", "BurstId"]).reset_index(drop=True)
    or_frame = pd.read_csv(OUT / "V2_OR_TICKS_98.csv")[
        ["BurstId", "OR_ticks", "OR_reason"]]
    scores = pd.read_csv(OUT / "V2_SCORES_P0_98.csv")[
        ["BurstId", "S", "Q", "evaluable"]]

    rows = []
    for _, row in track(list(handoff.iterrows()), label="Y_60 (mH + m1)"):
        cut = cutoff_of(row)
        t1 = cut + pd.Timedelta(seconds=T1_OFFSET)
        t_h = t1 + pd.Timedelta(seconds=H)
        mh, mh_reason = mh_from_mbp1(RAW / f"{row['BurstId']}.mbp1.dbn.zst",
                                     t_h)
        m1, m1_reason = m1_from_sealed(row)
        rows.append({"BurstId": str(row["BurstId"]), "fecha": str(row["fecha"]),
                     "burst_side": str(row["burst_side"]).upper(),
                     "mH": mh, "mH_reason": mh_reason,
                     "m1": m1, "m1_reason": m1_reason})
    mid = pd.DataFrame(rows)

    data = (mid.merge(or_frame, on="BurstId", validate="one_to_one")
               .merge(scores, on="BurstId", validate="one_to_one"))
    data["year"] = data["fecha"].str[:4].astype(int)
    data["sigma"] = np.where(data["burst_side"] == "BUY", 1.0, -1.0)
    data["Y_60"] = (data["sigma"]
                    * ((data["mH"] - data["m1"]) / TICK_SIZE)
                    / np.maximum(data["OR_ticks"], 1))
    data["Y60_valid"] = (data["mH_reason"].eq("OK")
                         & data["m1_reason"].eq("OK")
                         & data["OR_reason"].eq("OK")
                         & np.isfinite(data["Y_60"]))
    data.to_csv(OUT / "V2_Y60_98.csv", index=False)

    disc = data[(data["year"].isin(DISCOVERY_YEARS)) & data["evaluable"]
                & data["Y60_valid"]].copy()
    n = len(disc)
    result = {
        "information_status": "V2_DISCOVERY_ENDPOINT_OPENED_ONCE",
        "n_pairs": int(n), "min_pairs": MIN_PAIRS,
        "mH_reasons": data["mH_reason"].value_counts().to_dict(),
        "m1_reasons": data["m1_reason"].value_counts().to_dict(),
        "OR_reasons": data["OR_reason"].value_counts().to_dict(),
    }
    if n < MIN_PAIRS:
        result.update({"VERDICT": "FAIL_COVERAGE"})
    else:
        s = disc["S"].to_numpy()
        y = disc["Y_60"].to_numpy()
        rho = float(spearmanr(s, y).statistic)
        lo, hi = bootstrap_ci(s, y, disc["fecha"].to_numpy())
        success = bool(rho >= RHO_MIN and lo > 0)
        result.update({
            "rho_hat": rho, "ci95_low": lo, "ci95_high": hi,
            "threshold_rho": RHO_MIN, "seed": hex(SEED), "n_boot": N_BOOT,
            "Y60_median": float(np.median(y)),
            "Y60_iqr": [float(np.percentile(y, 25)),
                        float(np.percentile(y, 75))],
            "VERDICT": "PASS" if success else "FAIL",
        })
    (OUT / "V2_DISCOVERY_ENDPOINT_RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
