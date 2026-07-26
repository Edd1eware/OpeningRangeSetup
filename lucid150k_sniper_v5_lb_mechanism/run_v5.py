"""Causal five-bar LB mechanism test for LUCID150K-SNIPER-V5."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
V1_ROOT = BASE.parent / "lucid150k_sniper_v1"
sys.path.insert(0, str(V1_ROOT))
import run_dev as common  # noqa: E402

RESULTS_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
    r"\trade_results_score"
)
DEV_EVENTS = RESULTS_ROOT / "burst_events.csv"
PSEUDO_EVENTS = (
    RESULTS_ROOT
    / "visual_tests"
    / "04_run_replay_lb_matrix_classification_r5_dst_2025_2026_runs"
    / "observational"
    / "burst_events.csv"
)
OUT = BASE / "output"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V5.md"
PREREG_SHA = "3887e468ff4147790eb03da30f99caa9f45c2f736a5883768b1ba748645f2f87"
DETECTOR = "liquidity-burst-detector-2026-07-22-v7-postburst-matrix"
FAMILIES = (
    "A_LB_CONTINUATION_ACCEPTANCE",
    "B_LB_ABSORPTION_RECLAIM",
)
SEED = 0x9B7C240E15D86AF3
BOOTSTRAPS = 10_000
USECOLS = [
    "Detector_VERSION",
    "BurstId",
    "Detector_Publish_Timestamp_UTC",
    "Timestamp_NY",
    "Side",
    "Price",
    "Mechanism_Validity",
    "Reference_Type",
    "OR_High",
    "OR_Low",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_first_events(
    path: Path,
    start: str,
    end: str,
    block: str,
) -> list[dict]:
    frame = pd.read_csv(path, usecols=USECOLS)
    frame = frame[frame["Detector_VERSION"].eq(DETECTOR)].copy()
    frame["publish"] = pd.to_datetime(
        frame["Detector_Publish_Timestamp_UTC"], utc=True
    )
    frame["date"] = frame["publish"].dt.tz_convert("America/New_York").dt.strftime(
        "%Y-%m-%d"
    )
    frame["time_ny"] = frame["publish"].dt.tz_convert(
        "America/New_York"
    ).dt.time
    valid_reference = frame["Reference_Type"].isin(["OR_HIGH", "OR_LOW"])
    coherent = (
        (frame["Side"].eq("BUY") & frame["Reference_Type"].eq("OR_HIGH"))
        | (frame["Side"].eq("SELL") & frame["Reference_Type"].eq("OR_LOW"))
    )
    in_time = (
        frame["time_ny"].astype(str).ge("09:31:00")
        & frame["time_ny"].astype(str).le("10:00:00")
    )
    frame = frame[
        frame["Mechanism_Validity"].eq("VALID")
        & valid_reference
        & coherent
        & in_time
        & frame["date"].between(start, end)
    ].sort_values("publish")
    first = frame.groupby("date", as_index=False).first()
    first["block"] = block
    return first.to_dict("records")


def next_integer_second(timestamp: pd.Timestamp) -> pd.Timestamp:
    rounded = timestamp.ceil("s")
    if rounded == timestamp:
        rounded += pd.Timedelta(seconds=1)
    return rounded


def process_event(event: dict) -> tuple[dict | None, str | None, str]:
    date = str(event["date"])
    try:
        nq = common.load_session(common.NQ_ROOT, date)
        if nq is None:
            return None, None, "missing_nq"
        publish = pd.Timestamp(event["publish"])
        first_bar_time = next_integer_second(publish)
        after = nq.loc[nq.index >= first_bar_time]
        if len(after) < 5:
            return None, None, "fewer_than_5_bars"
        observed = after.iloc[:5]
        if observed.index[-1] > publish + pd.Timedelta(seconds=7):
            return None, None, "five_bar_gap"

        side = str(event["Side"])
        burst_sign = 1 if side == "BUY" else -1
        level = (
            float(event["OR_High"])
            if side == "BUY"
            else float(event["OR_Low"])
        )
        closes = observed["close"].to_numpy(float)
        if burst_sign == 1:
            outside = closes >= level + common.TICK
            inside = closes < level
            final_outside = closes[-1] >= level + common.TICK
            final_deep_inside = closes[-1] <= level - 2 * common.TICK
        else:
            outside = closes <= level - common.TICK
            inside = closes > level
            final_outside = closes[-1] <= level - common.TICK
            final_deep_inside = closes[-1] >= level + 2 * common.TICK

        if int(outside.sum()) >= 4 and bool(final_outside):
            family = FAMILIES[0]
            sign = burst_sign
        elif bool(inside.any()) and bool(final_deep_inside):
            family = FAMILIES[1]
            sign = -burst_sign
        else:
            return None, None, "ambiguous"

        entry_cutoff = common.local_ts(date, "10:00:00")
        next_bars = nq.loc[
            (nq.index > observed.index[-1])
            & (nq.index <= entry_cutoff)
        ]
        if next_bars.empty:
            return None, None, "no_entry_bar"
        entry_time = next_bars.index[0]
        entry = float(next_bars.iloc[0]["open"]) + sign * common.TICK

        if family == FAMILIES[0]:
            or_start = common.local_ts(date, "09:30:00")
            or_end = common.local_ts(date, "09:31:00")
            opening = common.opening_range(nq, or_start, or_end)
            if opening is None:
                return None, None, "missing_or"
            midpoint = (opening[0] + opening[1]) / 2.0
            stop = midpoint
        elif burst_sign == 1:
            stop = max(
                float(event["Price"]),
                float(observed["high"].max()),
            ) + 2 * common.TICK
        else:
            stop = min(
                float(event["Price"]),
                float(observed["low"].min()),
            ) - 2 * common.TICK

        risk = sign * (entry - stop) / common.TICK
        if family == FAMILIES[1] and risk < common.MIN_R:
            risk = common.MIN_R
            stop = entry - sign * risk * common.TICK
        if not (common.MIN_R <= risk <= common.MAX_R):
            return None, None, "risk_outside"

        exit_cutoff = common.local_ts(date, "15:55:00")
        row = common.trade_record(
            family,
            date,
            nq,
            entry_time,
            exit_cutoff,
            sign,
            entry,
            risk,
        )
        row.update(
            {
                "block": event["block"],
                "burst_id": event["BurstId"],
                "burst_side": side,
                "publish_utc": publish.isoformat(),
                "observation_end_utc": observed.index[-1].isoformat(),
                "outside_count": int(outside.sum()),
            }
        )
        return row, None, "trade"
    except Exception as exc:  # noqa: BLE001
        return None, repr(exc), "error"


def bootstrap_ci(values: np.ndarray) -> list[float]:
    rng = np.random.default_rng(SEED)
    means = np.empty(BOOTSTRAPS, dtype=float)
    for index in range(BOOTSTRAPS):
        means[index] = rng.choice(values, size=values.size, replace=True).mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return [round(float(low), 5), round(float(high), 5)]


def main() -> int:
    if sha256_file(PREREG) != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    OUT.mkdir(exist_ok=True)
    events = load_first_events(
        DEV_EVENTS,
        "2022-04-25",
        "2023-12-31",
        "DEV",
    )
    events += load_first_events(
        PSEUDO_EVENTS,
        "2025-01-01",
        "2026-06-30",
        "PSEUDO_VAL",
    )

    rows: list[dict] = []
    errors: list[dict] = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(process_event, event): event for event in events
        }
        complete = 0
        for future in concurrent.futures.as_completed(pending):
            event = pending[future]
            complete += 1
            try:
                row, error, disposition = future.result()
                dispositions[disposition] = dispositions.get(disposition, 0) + 1
                if row is not None:
                    rows.append(row)
                if error is not None:
                    errors.append(
                        {"burst_id": event["BurstId"], "error": error}
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {"burst_id": event["BurstId"], "error": repr(exc)}
                )
            if complete % 25 == 0 or complete == len(events):
                print(
                    f"[{complete:3d}/{len(events)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )

    trades = pd.DataFrame(rows)
    if not trades.empty:
        trades = trades.sort_values(["family", "date"])
    trades.to_csv(OUT / "ALL_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )

    dev = trades[trades["block"].eq("DEV")]
    pseudo = trades[trades["block"].eq("PSEUDO_VAL")]
    dev_results = {}
    passing = []
    for family in FAMILIES:
        frame = dev[dev["family"].eq(family)]
        trail = common.metrics(frame)
        fixed = common.metrics(frame, "fixed_net_R")
        difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
        gates = {
            "D1_n_ge_18": bool(trail.get("n", 0) >= 18),
            "D2_ev_gt_010R": bool(trail.get("ev_R", -999) > 0.10),
            "D3_pf_gt_130": bool(
                trail.get("pf") is not None and trail["pf"] > 1.30
            ),
            "D4_two_positive_years": bool(
                trail.get("positive_years", 0) == 2
            ),
            "D5_positive_halves_ge_60pct": bool(
                trail.get("positive_halves_pct", 0) >= 60.0
            ),
            "D6_trailing_minus_fixed_ge_minus005R": bool(
                difference >= -0.05
            ),
        }
        passed = all(gates.values())
        dev_results[family] = {
            "TRAILING": trail,
            "FIXED_1R_DIAGNOSTIC": fixed,
            "trailing_minus_fixed_EV_R": round(difference, 5),
            "gates": gates,
            "PASS": passed,
        }
        if passed:
            passing.append(family)

    selected = None
    if passing:
        selected = sorted(
            passing,
            key=lambda family: (
                -dev_results[family]["TRAILING"]["median_half_EV_R"],
                FAMILIES.index(family),
            ),
        )[0]

    pseudo_result = None
    authorize_holdout = False
    if selected is not None:
        frame = pseudo[pseudo["family"].eq(selected)]
        metrics = common.metrics(frame)
        ci = bootstrap_ci(frame["net_R"].to_numpy(float))
        year_ev = metrics.get("year_EV_R", {})
        gates = {
            "V1_n_ge_18": bool(metrics.get("n", 0) >= 18),
            "V2_ev_gt_0": bool(metrics.get("ev_R", -999) > 0),
            "V3_pf_gt_115": bool(
                metrics.get("pf") is not None and metrics["pf"] > 1.15
            ),
            "V4_2025_and_2026_positive": bool(
                year_ev.get("2025", -999) > 0
                and year_ev.get("2026", -999) > 0
            ),
            "V5_ci_low_gt_minus015R": bool(ci[0] > -0.15),
        }
        authorize_holdout = all(gates.values())
        pseudo_result = {
            "family": selected,
            "metrics": metrics,
            "bootstrap_EV_R_CI95": ci,
            "gates": gates,
            "PASS": authorize_holdout,
        }

    result = {
        "study": "LUCID150K-SNIPER-V5-LB-MECHANISM",
        "prereg_sha256": PREREG_SHA,
        "events_first_eligible": len(events),
        "errors": len(errors),
        "dispositions": dispositions,
        "DEV": dev_results,
        "selected_family": selected,
        "PSEUDO_VAL_2025_2026": pseudo_result,
        "DESCRIPTIVE_PSEUDO_ALL_FAMILIES": {
            family: common.metrics(pseudo[pseudo["family"].eq(family)])
            for family in FAMILIES
        },
        "AUTHORIZE_HOLDOUT_BUILD": authorize_holdout,
        "VERDICT_STAGE": (
            "PASS_TO_HOLDOUT_BUILD"
            if authorize_holdout
            else "FAIL_NO_HOLDOUT"
        ),
    }
    (OUT / "RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
