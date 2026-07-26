"""DEV and pseudo-validation for preregistered LUCID150K-SNIPER-V2."""

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

OUT = BASE / "output"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V2.md"
PREREG_SHA = "78467379fd13c27e7bed05b9932695d29bfc180ae625c572e0d7ccf75c19157f"

TICK = 0.25
MIN_R = 20.0
MAX_R = 80.0
RETEST_SECONDS = 120
RECLAIM_SECONDS = 15
REBREAK_SECONDS = 120
SEED = 0x5F06A76E51C2D94B
BOOTSTRAPS = 10_000
FAMILIES = (
    "A_CROSS_ACCEPTANCE_RETEST",
    "B_FAILED_RECLAIM_CROSS_REBREAK",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PriorClose:
    """Causal ES close lookup: timestamp must be strictly earlier."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.times = frame.index.asi8
        self.closes = frame["close"].to_numpy(float)

    def before(self, timestamp: pd.Timestamp) -> float | None:
        position = int(np.searchsorted(self.times, timestamp.value, side="left")) - 1
        if position < 0:
            return None
        return float(self.closes[position])


def next_bar(
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Series] | None:
    future = frame.loc[(frame.index > timestamp) & (frame.index <= cutoff)]
    if future.empty:
        return None
    return future.index[0], future.iloc[0]


def family_a_acceptance_retest(
    date: str,
    nq: pd.DataFrame,
    es_lookup: PriorClose,
    nq_or: tuple[float, float],
    es_or: tuple[float, float],
    scan_start: pd.Timestamp,
    entry_cutoff: pd.Timestamp,
    exit_cutoff: pd.Timestamp,
) -> dict | None:
    nq_high, nq_low = nq_or
    es_high, es_low = es_or
    post = nq.loc[(nq.index >= scan_start) & (nq.index <= entry_cutoff)]

    previous_sign = 0
    consecutive = 0
    accepted_sign = 0
    accepted_time: pd.Timestamp | None = None

    for timestamp, bar in post.iterrows():
        close = float(bar["close"])
        sign = 1 if close >= nq_high + TICK else (
            -1 if close <= nq_low - TICK else 0
        )
        if sign == 0:
            previous_sign = 0
            consecutive = 0
            continue
        if sign == previous_sign:
            consecutive += 1
        else:
            previous_sign = sign
            consecutive = 1
        if consecutive < 2:
            continue

        es_close = es_lookup.before(timestamp)
        if es_close is None:
            return None
        confirmed = (
            es_close >= es_high + TICK
            if sign == 1
            else es_close <= es_low - TICK
        )
        if not confirmed:
            return None
        accepted_sign = sign
        accepted_time = timestamp
        break

    if accepted_time is None:
        return None

    deadline = min(
        accepted_time + pd.Timedelta(seconds=RETEST_SECONDS),
        entry_cutoff,
    )
    retest_window = post.loc[
        (post.index > accepted_time) & (post.index <= deadline)
    ]
    retest_time: pd.Timestamp | None = None
    for timestamp, bar in retest_window.iterrows():
        close = float(bar["close"])
        if accepted_sign == 1 and close <= nq_low - TICK:
            return None
        if accepted_sign == -1 and close >= nq_high + TICK:
            return None
        defended = (
            float(bar["low"]) <= nq_high and close >= nq_high + TICK
            if accepted_sign == 1
            else float(bar["high"]) >= nq_low and close <= nq_low - TICK
        )
        if not defended:
            continue
        es_close = es_lookup.before(timestamp)
        if es_close is None:
            return None
        confirmed = (
            es_close >= es_high + TICK
            if accepted_sign == 1
            else es_close <= es_low - TICK
        )
        if not confirmed:
            return None
        retest_time = timestamp
        break

    if retest_time is None:
        return None
    following = next_bar(nq, retest_time, entry_cutoff)
    if following is None:
        return None
    entry_time, bar = following
    entry = float(bar["open"]) + accepted_sign * TICK
    midpoint = (nq_high + nq_low) / 2.0
    risk = accepted_sign * (entry - midpoint) / TICK
    if not (MIN_R <= risk <= MAX_R):
        return None
    return common.trade_record(
        FAMILIES[0],
        date,
        nq,
        entry_time,
        exit_cutoff,
        accepted_sign,
        entry,
        risk,
    )


def family_b_failed_reclaim_rebreak(
    date: str,
    nq: pd.DataFrame,
    es_lookup: PriorClose,
    nq_or: tuple[float, float],
    es_or: tuple[float, float],
    scan_start: pd.Timestamp,
    entry_cutoff: pd.Timestamp,
    exit_cutoff: pd.Timestamp,
) -> dict | None:
    nq_high, nq_low = nq_or
    es_high, es_low = es_or
    post = nq.loc[(nq.index >= scan_start) & (nq.index <= entry_cutoff)]

    sweep_time: pd.Timestamp | None = None
    sign = 0
    for timestamp, bar in post.iterrows():
        up = float(bar["high"]) >= nq_high + TICK
        down = float(bar["low"]) <= nq_low - TICK
        if not (up or down):
            continue
        if up and down:
            return None
        sign = 1 if up else -1
        es_close = es_lookup.before(timestamp)
        if es_close is None:
            return None
        nonconfirmed = (
            es_close < es_high + TICK
            if sign == 1
            else es_close > es_low - TICK
        )
        if not nonconfirmed:
            return None
        sweep_time = timestamp
        break

    if sweep_time is None:
        return None

    reclaim_deadline = min(
        sweep_time + pd.Timedelta(seconds=RECLAIM_SECONDS),
        entry_cutoff,
    )
    reclaim_window = post.loc[
        (post.index >= sweep_time) & (post.index <= reclaim_deadline)
    ]
    frozen_sweep = (
        float(reclaim_window.iloc[0]["high"])
        if sign == 1
        else float(reclaim_window.iloc[0]["low"])
    )
    reclaim_time: pd.Timestamp | None = None
    for timestamp, bar in reclaim_window.iterrows():
        frozen_sweep = (
            max(frozen_sweep, float(bar["high"]))
            if sign == 1
            else min(frozen_sweep, float(bar["low"]))
        )
        reclaimed = (
            float(bar["close"]) < nq_high
            if sign == 1
            else float(bar["close"]) > nq_low
        )
        if reclaimed:
            reclaim_time = timestamp
            break

    if reclaim_time is None:
        return None

    rebreak_deadline = min(
        reclaim_time + pd.Timedelta(seconds=REBREAK_SECONDS),
        entry_cutoff,
    )
    rebreak_window = post.loc[
        (post.index >= reclaim_time) & (post.index <= rebreak_deadline)
    ]
    adverse_extreme = (
        float(rebreak_window.iloc[0]["low"])
        if sign == 1
        else float(rebreak_window.iloc[0]["high"])
    )
    rebreak_time: pd.Timestamp | None = None
    for timestamp, bar in rebreak_window.iterrows():
        adverse_extreme = (
            min(adverse_extreme, float(bar["low"]))
            if sign == 1
            else max(adverse_extreme, float(bar["high"]))
        )
        rebroken = (
            float(bar["close"]) >= frozen_sweep + TICK
            if sign == 1
            else float(bar["close"]) <= frozen_sweep - TICK
        )
        if not rebroken:
            continue
        es_close = es_lookup.before(timestamp)
        if es_close is None:
            return None
        confirmed = (
            es_close >= es_high + TICK
            if sign == 1
            else es_close <= es_low - TICK
        )
        if confirmed:
            rebreak_time = timestamp
            break

    if rebreak_time is None:
        return None
    following = next_bar(nq, rebreak_time, entry_cutoff)
    if following is None:
        return None
    entry_time, bar = following
    entry = float(bar["open"]) + sign * TICK
    stop = (
        adverse_extreme - 2 * TICK
        if sign == 1
        else adverse_extreme + 2 * TICK
    )
    risk = sign * (entry - stop) / TICK
    if not (MIN_R <= risk <= MAX_R):
        return None
    return common.trade_record(
        FAMILIES[1],
        date,
        nq,
        entry_time,
        exit_cutoff,
        sign,
        entry,
        risk,
    )


def process_date(date: str) -> tuple[list[dict], str | None]:
    try:
        nq = common.load_session(common.NQ_ROOT, date)
        es = common.load_session(common.ES_ROOT, date)
        if nq is None or es is None:
            return [], None
        or_start = common.local_ts(date, "09:30:00")
        or_end = common.local_ts(date, "09:31:00")
        entry_cutoff = common.local_ts(date, "10:00:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        nq_or = common.opening_range(nq, or_start, or_end)
        es_or = common.opening_range(es, or_start, or_end)
        if nq_or is None or es_or is None:
            return [], None
        es_lookup = PriorClose(es)
        rows = []
        for finder in (
            family_a_acceptance_retest,
            family_b_failed_reclaim_rebreak,
        ):
            row = finder(
                date,
                nq,
                es_lookup,
                nq_or,
                es_or,
                or_end,
                entry_cutoff,
                exit_cutoff,
            )
            if row is not None:
                rows.append(row)
        return rows, None
    except Exception as exc:  # noqa: BLE001
        return [], repr(exc)


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

    dates = sorted(
        set(path.name for path in common.NQ_ROOT.iterdir() if path.is_dir())
        & set(path.name for path in common.ES_ROOT.iterdir() if path.is_dir())
    )
    rows: list[dict] = []
    errors: list[dict] = []
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(process_date, date): date for date in dates
        }
        complete = 0
        for future in concurrent.futures.as_completed(pending):
            date = pending[future]
            complete += 1
            try:
                day_rows, error = future.result()
                rows.extend(day_rows)
                if error is not None:
                    errors.append({"date": date, "error": error})
            except Exception as exc:  # noqa: BLE001
                errors.append({"date": date, "error": repr(exc)})
            if complete % 100 == 0 or complete == len(dates):
                print(
                    f"[{complete:4d}/{len(dates)}] trades={len(rows)} "
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

    dev = trades[
        (trades["date"] >= "2022-04-25")
        & (trades["date"] <= "2023-12-31")
    ]
    pseudo = trades[
        (trades["date"] >= "2024-01-01")
        & (trades["date"] <= "2024-12-31")
    ]
    stress = trades[trades["date"] >= "2025-01-01"]

    dev_results = {}
    passing = []
    for family in FAMILIES:
        frame = dev[dev["family"] == family]
        trail = common.metrics(frame)
        fixed = common.metrics(frame, "fixed_net_R")
        difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
        gates = {
            "D1_n_ge_40": bool(trail.get("n", 0) >= 40),
            "D2_ev_gt_005R": bool(trail.get("ev_R", -999) > 0.05),
            "D3_pf_gt_120": bool(
                trail.get("pf") is not None and trail["pf"] > 1.20
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
        selected_frame = pseudo[pseudo["family"] == selected]
        pseudo_metrics = common.metrics(selected_frame)
        ci = bootstrap_ci(selected_frame["net_R"].to_numpy(float))
        gates = {
            "V1_n_ge_20": bool(pseudo_metrics.get("n", 0) >= 20),
            "V2_ev_gt_0": bool(pseudo_metrics.get("ev_R", -999) > 0),
            "V3_pf_gt_110": bool(
                pseudo_metrics.get("pf") is not None
                and pseudo_metrics["pf"] > 1.10
            ),
            "V4_ci_low_gt_minus010R": bool(ci[0] > -0.10),
        }
        pseudo_result = {
            "family": selected,
            "metrics": pseudo_metrics,
            "bootstrap_EV_R_CI95": ci,
            "gates": gates,
            "PASS": all(gates.values()),
        }
        authorize_holdout = all(gates.values())

    result = {
        "study": "LUCID150K-SNIPER-V2",
        "prereg_sha256": PREREG_SHA,
        "workers": workers,
        "dates_scanned": len(dates),
        "errors": len(errors),
        "trades_total": len(trades),
        "DEV": dev_results,
        "selected_family": selected,
        "PSEUDO_VAL_2024": pseudo_result,
        "STRESS_SEEN_2025_2026": {
            family: common.metrics(stress[stress["family"] == family])
            for family in FAMILIES
        },
        "AUTHORIZE_HOLDOUT_DOWNLOAD": authorize_holdout,
        "VERDICT_STAGE": (
            "PASS_TO_HOLDOUT" if authorize_holdout else "FAIL_NO_DOWNLOAD"
        ),
    }
    (OUT / "DEV_RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
