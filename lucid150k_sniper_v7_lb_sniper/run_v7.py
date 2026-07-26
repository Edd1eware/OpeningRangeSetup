"""Fixed-risk, non-overlapping LB continuation sniper for V7."""

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
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V7.md"
PREREG_SHA = "4c96e1b79ad3c48715d2574faae5e236589508f5dd7822878cf448191b4c1034"
DETECTOR = "liquidity-burst-detector-2026-07-22-v7-postburst-matrix"
FAMILY = "LB_CONTINUATION_ACCEPTANCE_FIXED20"
STOP_TICKS = 20.0
TARGET_TICKS = 40.0
COST_TICKS = 4.0
SEED = 0x4C8E1A70B2D659F3
BOOTSTRAPS = 10_000
USECOLS = [
    "Detector_VERSION",
    "BurstId",
    "Detector_Publish_Timestamp_UTC",
    "Side",
    "Mechanism_Validity",
    "Reference_Type",
    "OR_High",
    "OR_Low",
    "Episode_ID",
    "Burst_Index_In_Episode",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_events(
    path: Path,
    start: str,
    end: str,
    block: str,
) -> dict[str, list[dict]]:
    frame = pd.read_csv(path, usecols=USECOLS)
    frame = frame[frame["Detector_VERSION"].eq(DETECTOR)].copy()
    frame["publish"] = pd.to_datetime(
        frame["Detector_Publish_Timestamp_UTC"], utc=True
    )
    local = frame["publish"].dt.tz_convert("America/New_York")
    frame["date"] = local.dt.strftime("%Y-%m-%d")
    frame["time_text"] = local.dt.strftime("%H:%M:%S")
    coherent = (
        (frame["Side"].eq("BUY") & frame["Reference_Type"].eq("OR_HIGH"))
        | (frame["Side"].eq("SELL") & frame["Reference_Type"].eq("OR_LOW"))
    )
    frame = frame[
        frame["Mechanism_Validity"].eq("VALID")
        & coherent
        & frame["Burst_Index_In_Episode"].eq(1)
        & frame["time_text"].between("09:31:00", "10:00:00")
        & frame["date"].between(start, end)
    ].sort_values(["date", "publish"])
    frame["block"] = block
    return {
        date: group.to_dict("records")
        for date, group in frame.groupby("date", sort=True)
    }


def next_integer_second(timestamp: pd.Timestamp) -> pd.Timestamp:
    rounded = timestamp.ceil("s")
    if rounded == timestamp:
        rounded += pd.Timedelta(seconds=1)
    return rounded


def simulate(
    nq: pd.DataFrame,
    entry_time: pd.Timestamp,
    exit_cutoff: pd.Timestamp,
    sign: int,
    entry: float,
    trailing: bool,
) -> dict:
    forward = nq.loc[(nq.index >= entry_time) & (nq.index <= exit_cutoff)]
    if forward.empty:
        raise ValueError("No bars after entry")
    stop = entry - sign * STOP_TICKS * common.TICK
    target = entry + sign * TARGET_TICKS * common.TICK
    best = entry
    mae = 0.0
    activated = False
    close = entry
    last_time = entry_time
    for timestamp, bar in forward.iterrows():
        last_time = timestamp
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        adverse = (
            (low - entry) / common.TICK
            if sign == 1
            else (entry - high) / common.TICK
        )
        mae = min(mae, adverse)
        stop_hit = low <= stop if sign == 1 else high >= stop
        if stop_hit:
            gross = sign * (stop - entry) / common.TICK
            return outcome(
                gross, mae, "STOP", activated, timestamp
            )
        target_hit = high >= target if sign == 1 else low <= target
        if target_hit:
            return outcome(
                TARGET_TICKS, mae, "TARGET", activated, timestamp
            )
        if trailing:
            best = max(best, high) if sign == 1 else min(best, low)
            favorable = sign * (best - entry) / common.TICK
            if favorable >= STOP_TICKS:
                activated = True
                break_even = entry + sign * COST_TICKS * common.TICK
                trail = best - sign * STOP_TICKS * common.TICK
                stop = (
                    max(stop, break_even, trail)
                    if sign == 1
                    else min(stop, break_even, trail)
                )
    gross = sign * (close - entry) / common.TICK
    return outcome(gross, mae, "EOD", activated, last_time)


def outcome(
    gross: float,
    mae: float,
    reason: str,
    activated: bool,
    exit_time: pd.Timestamp,
) -> dict:
    net = gross - COST_TICKS
    return {
        "gross_ticks": gross,
        "net_ticks": net,
        "net_R": net / STOP_TICKS,
        "mae_ticks": mae,
        "exit_reason": reason,
        "trailing_activated": activated,
        "exit_utc": exit_time.isoformat(),
    }


def accepted_signal(
    nq: pd.DataFrame,
    event: dict,
    entry_cutoff: pd.Timestamp,
) -> tuple[pd.Timestamp, int, float, int, pd.Timestamp] | None:
    publish = pd.Timestamp(event["publish"])
    first_bar_time = next_integer_second(publish)
    after = nq.loc[nq.index >= first_bar_time]
    if len(after) < 5:
        return None
    observed = after.iloc[:5]
    if observed.index[-1] > publish + pd.Timedelta(seconds=7):
        return None
    side = str(event["Side"])
    sign = 1 if side == "BUY" else -1
    level = (
        float(event["OR_High"])
        if sign == 1
        else float(event["OR_Low"])
    )
    closes = observed["close"].to_numpy(float)
    outside = (
        closes >= level + common.TICK
        if sign == 1
        else closes <= level - common.TICK
    )
    final_outside = bool(outside[-1])
    if int(outside.sum()) < 4 or not final_outside:
        return None
    following = nq.loc[
        (nq.index > observed.index[-1])
        & (nq.index <= entry_cutoff)
    ]
    if following.empty:
        return None
    entry_time = following.index[0]
    entry = float(following.iloc[0]["open"]) + sign * common.TICK
    return entry_time, sign, entry, int(outside.sum()), observed.index[-1]


def process_day(
    date: str,
    events: list[dict],
) -> tuple[list[dict], str | None, dict[str, int]]:
    dispositions: dict[str, int] = {}
    try:
        nq = common.load_session(common.NQ_ROOT, date)
        if nq is None:
            return [], None, {"missing_nq": 1}
        first_publish = pd.Timestamp(events[0]["publish"])
        last_exit: pd.Timestamp | None = None
        trades = []
        entry_cutoff = common.local_ts(date, "10:00:00")
        exit_cutoff = common.local_ts(date, "15:55:00")

        for event in events:
            publish = pd.Timestamp(event["publish"])
            if publish != first_publish and (
                publish - first_publish
            ) < pd.Timedelta(seconds=120):
                dispositions["episode_lt_120s"] = (
                    dispositions.get("episode_lt_120s", 0) + 1
                )
                continue
            signal = accepted_signal(nq, event, entry_cutoff)
            if signal is None:
                dispositions["not_accepted"] = (
                    dispositions.get("not_accepted", 0) + 1
                )
                continue
            entry_time, sign, entry, outside_count, observation_end = signal
            if last_exit is not None and entry_time <= last_exit:
                dispositions["overlap"] = dispositions.get("overlap", 0) + 1
                continue
            trail = simulate(
                nq, entry_time, exit_cutoff, sign, entry, True
            )
            fixed = simulate(
                nq, entry_time, exit_cutoff, sign, entry, False
            )
            row = {
                "family": FAMILY,
                "date": date,
                "year": int(date[:4]),
                "half": f"{date[:4]}-H{1 if int(date[5:7]) <= 6 else 2}",
                "block": event["block"],
                "burst_id": event["BurstId"],
                "episode_id": event["Episode_ID"],
                "side": "LONG" if sign == 1 else "SHORT",
                "entry_utc": entry_time.isoformat(),
                "entry": entry,
                "risk_ticks": STOP_TICKS,
                "outside_count": outside_count,
                "observation_end_utc": observation_end.isoformat(),
                **trail,
                "fixed_net_ticks": fixed["net_ticks"],
                "fixed_net_R": fixed["net_R"],
                "fixed_exit_reason": fixed["exit_reason"],
            }
            trades.append(row)
            last_exit = pd.Timestamp(trail["exit_utc"])
            dispositions["trade"] = dispositions.get("trade", 0) + 1
            if len(trades) >= 2:
                break
        return trades, None, dispositions
    except Exception as exc:  # noqa: BLE001
        return [], repr(exc), {"error": 1}


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
    dev = load_events(
        DEV_EVENTS, "2022-04-25", "2023-12-31", "DEV"
    )
    pseudo = load_events(
        PSEUDO_EVENTS, "2025-01-01", "2026-06-30", "PSEUDO_VAL"
    )
    all_days = {**dev, **pseudo}
    rows = []
    errors = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(process_day, date, events): date
            for date, events in all_days.items()
        }
        complete = 0
        for future in concurrent.futures.as_completed(pending):
            date = pending[future]
            complete += 1
            day_rows, error, day_dispositions = future.result()
            rows.extend(day_rows)
            if error is not None:
                errors.append({"date": date, "error": error})
            for key, value in day_dispositions.items():
                dispositions[key] = dispositions.get(key, 0) + value
            if complete % 25 == 0 or complete == len(all_days):
                print(
                    f"[{complete:3d}/{len(all_days)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )

    trades = pd.DataFrame(rows).sort_values(["block", "date", "entry_utc"])
    trades.to_csv(OUT / "ALL_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )
    dev_trades = trades[trades["block"].eq("DEV")]
    pseudo_trades = trades[trades["block"].eq("PSEUDO_VAL")]
    trail = common.metrics(dev_trades)
    fixed = common.metrics(dev_trades, "fixed_net_R")
    difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
    dev_frequency = trail.get("n", 0) / 21.0
    dev_gates = {
        "D1_n_ge_30": bool(trail.get("n", 0) >= 30),
        "D2_frequency_ge_15": bool(dev_frequency >= 1.5),
        "D3_ev_gt_015R": bool(trail.get("ev_R", -999) > 0.15),
        "D4_pf_gt_140": bool(
            trail.get("pf") is not None and trail["pf"] > 1.40
        ),
        "D5_two_positive_years": bool(trail.get("positive_years", 0) == 2),
        "D6_positive_halves_ge_60pct": bool(
            trail.get("positive_halves_pct", 0) >= 60.0
        ),
        "D7_trailing_minus_fixed_ge_minus005R": bool(
            difference >= -0.05
        ),
    }
    dev_pass = all(dev_gates.values())

    pseudo_result = None
    authorize_holdout = False
    if dev_pass:
        metrics = common.metrics(pseudo_trades)
        frequency = metrics.get("n", 0) / 18.0
        ci = bootstrap_ci(pseudo_trades["net_R"].to_numpy(float))
        years = metrics.get("year_EV_R", {})
        gates = {
            "V1_n_ge_25": bool(metrics.get("n", 0) >= 25),
            "V2_frequency_ge_15": bool(frequency >= 1.5),
            "V3_ev_gt_010R": bool(metrics.get("ev_R", -999) > 0.10),
            "V4_pf_gt_130": bool(
                metrics.get("pf") is not None and metrics["pf"] > 1.30
            ),
            "V5_both_years_positive": bool(
                years.get("2025", -999) > 0
                and years.get("2026", -999) > 0
            ),
            "V6_ci_low_gt_minus010R": bool(ci[0] > -0.10),
        }
        authorize_holdout = all(gates.values())
        pseudo_result = {
            "metrics": metrics,
            "trades_per_month": round(frequency, 4),
            "bootstrap_EV_R_CI95": ci,
            "gates": gates,
            "PASS": authorize_holdout,
        }

    result = {
        "study": "LUCID150K-SNIPER-V7-LB-SNIPER",
        "prereg_sha256": PREREG_SHA,
        "days_with_eligible_episodes": len(all_days),
        "errors": len(errors),
        "dispositions": dispositions,
        "DEV": {
            "TRAILING": trail,
            "FIXED_40_20_DIAGNOSTIC": fixed,
            "trades_per_month": round(dev_frequency, 4),
            "trailing_minus_fixed_EV_R": round(difference, 5),
            "gates": dev_gates,
            "PASS": dev_pass,
        },
        "PSEUDO_VAL": pseudo_result,
        "DESCRIPTIVE_PSEUDO": common.metrics(pseudo_trades),
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
