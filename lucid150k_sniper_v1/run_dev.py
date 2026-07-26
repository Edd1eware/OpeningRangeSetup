"""DEV and pseudo-validation for LUCID150K-SNIPER-V1."""

from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
NQ_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
)
ES_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_es"
)
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V1.md"
PREREG_SHA = "a173f38b9da683fcf170989c13e52d8e0d372fd08d368af018a5e5a17d8ea09a"

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TICK = 0.25
COST_TICKS = 4.0
MIN_R = 20.0
MAX_R = 80.0
RECLAIM_SECONDS = 15
SEED = 0x22F9CADF098B1625
BOOTSTRAPS = 10_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_session(root: Path, date: str) -> pd.DataFrame | None:
    hits = glob.glob(str(root / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    frame = db.DBNStore.from_file(hits[0]).to_df()
    if frame.empty:
        return None
    return frame[["open", "high", "low", "close"]].sort_index()


def local_ts(date: str, time_text: str) -> pd.Timestamp:
    return pd.Timestamp(f"{date} {time_text}", tz=NY).tz_convert(UTC)


def opening_range(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[float, float] | None:
    window = frame.loc[(frame.index >= start) & (frame.index < end)]
    if window.empty:
        return None
    return float(window["high"].max()), float(window["low"].min())


def last_close_before(frame: pd.DataFrame, timestamp: pd.Timestamp) -> float | None:
    prior = frame.loc[frame.index < timestamp, "close"]
    return float(prior.iloc[-1]) if not prior.empty else None


def simulate_management(
    nq: pd.DataFrame,
    entry_time: pd.Timestamp,
    cutoff: pd.Timestamp,
    sign: int,
    entry: float,
    risk_ticks: float,
    mode: str,
) -> dict:
    forward = nq.loc[(nq.index >= entry_time) & (nq.index <= cutoff)]
    if forward.empty:
        raise ValueError("No bars after entry")

    stop = entry - sign * risk_ticks * TICK
    target_multiple = 2.0 if mode == "RR2_TRAIL_1R" else 1.0
    target = entry + sign * target_multiple * risk_ticks * TICK
    best = entry
    mae = 0.0
    activated = False
    close = entry

    for high, low, bar_close in zip(
        forward["high"].to_numpy(float),
        forward["low"].to_numpy(float),
        forward["close"].to_numpy(float),
    ):
        close = bar_close
        adverse_ticks = (
            (low - entry) / TICK if sign == 1 else (entry - high) / TICK
        )
        mae = min(mae, adverse_ticks)

        stop_hit = low <= stop if sign == 1 else high >= stop
        if stop_hit:
            gross = sign * (stop - entry) / TICK
            return {
                "gross_ticks": gross,
                "net_ticks": gross - COST_TICKS,
                "net_R": (gross - COST_TICKS) / risk_ticks,
                "mae_ticks": mae,
                "exit_reason": "STOP",
                "trailing_activated": activated,
            }

        target_hit = high >= target if sign == 1 else low <= target
        if target_hit:
            gross = target_multiple * risk_ticks
            return {
                "gross_ticks": gross,
                "net_ticks": gross - COST_TICKS,
                "net_R": (gross - COST_TICKS) / risk_ticks,
                "mae_ticks": mae,
                "exit_reason": "TARGET",
                "trailing_activated": activated,
            }

        best = max(best, high) if sign == 1 else min(best, low)
        favorable_ticks = sign * (best - entry) / TICK
        if mode == "RR2_TRAIL_1R" and favorable_ticks >= risk_ticks:
            activated = True
            break_even_stop = entry + sign * COST_TICKS * TICK
            trailing_stop = best - sign * risk_ticks * TICK
            if sign == 1:
                stop = max(stop, break_even_stop, trailing_stop)
            else:
                stop = min(stop, break_even_stop, trailing_stop)

    gross = sign * (close - entry) / TICK
    return {
        "gross_ticks": gross,
        "net_ticks": gross - COST_TICKS,
        "net_R": (gross - COST_TICKS) / risk_ticks,
        "mae_ticks": mae,
        "exit_reason": "EOD",
        "trailing_activated": activated,
    }


def s1_es_leads(
    date: str,
    nq: pd.DataFrame,
    es: pd.DataFrame,
    nq_or: tuple[float, float],
    es_or: tuple[float, float],
    scan_start: pd.Timestamp,
    entry_cutoff: pd.Timestamp,
    exit_cutoff: pd.Timestamp,
) -> dict | None:
    nq_high, nq_low = nq_or
    es_high, es_low = es_or
    midpoint = (nq_high + nq_low) / 2.0
    post = nq.loc[(nq.index >= scan_start) & (nq.index <= entry_cutoff)]
    armed_sign = 0

    for timestamp, bar in post.iterrows():
        es_close = last_close_before(es, timestamp)
        if es_close is None:
            continue
        if armed_sign == 0:
            if es_close > es_high:
                armed_sign = 1
            elif es_close < es_low:
                armed_sign = -1

        up_boundary = float(bar["high"]) >= nq_high + TICK
        down_boundary = float(bar["low"]) <= nq_low - TICK
        if up_boundary and down_boundary:
            return None
        if armed_sign == 0:
            if up_boundary or down_boundary:
                return None
            continue
        if armed_sign == 1 and down_boundary:
            return None
        if armed_sign == -1 and up_boundary:
            return None

        entry_hit = up_boundary if armed_sign == 1 else down_boundary
        if not entry_hit:
            continue
        entry = nq_high + TICK if armed_sign == 1 else nq_low - TICK
        risk = abs(entry - midpoint) / TICK
        if not (MIN_R <= risk <= MAX_R):
            return None
        return trade_record(
            "S1_ES_LEADS_NQ_BREAKOUT",
            date,
            nq,
            timestamp,
            exit_cutoff,
            armed_sign,
            entry,
            risk,
        )
    return None


def s2_divergence_reclaim(
    date: str,
    nq: pd.DataFrame,
    es: pd.DataFrame,
    nq_or: tuple[float, float],
    es_or: tuple[float, float],
    scan_start: pd.Timestamp,
    entry_cutoff: pd.Timestamp,
    exit_cutoff: pd.Timestamp,
) -> dict | None:
    nq_high, nq_low = nq_or
    es_high, es_low = es_or
    post = nq.loc[(nq.index >= scan_start) & (nq.index <= entry_cutoff)]

    for sweep_pos, (timestamp, bar) in enumerate(post.iterrows()):
        up_sweep = float(bar["high"]) >= nq_high + TICK
        down_sweep = float(bar["low"]) <= nq_low - TICK
        if not (up_sweep or down_sweep):
            continue
        if up_sweep and down_sweep:
            return None

        es_close = last_close_before(es, timestamp)
        if es_close is None:
            return None
        if up_sweep and es_close > es_high:
            return None
        if down_sweep and es_close < es_low:
            return None

        sign = -1 if up_sweep else 1
        deadline = timestamp + pd.Timedelta(seconds=RECLAIM_SECONDS)
        segment = post.loc[
            (post.index >= timestamp) & (post.index <= deadline)
        ]
        sweep_extreme = (
            float(segment.iloc[0]["high"])
            if up_sweep
            else float(segment.iloc[0]["low"])
        )
        reclaim_time = None
        for current_time, current_bar in segment.iterrows():
            if up_sweep:
                sweep_extreme = max(sweep_extreme, float(current_bar["high"]))
                reclaimed = float(current_bar["close"]) < nq_high
            else:
                sweep_extreme = min(sweep_extreme, float(current_bar["low"]))
                reclaimed = float(current_bar["close"]) > nq_low
            if reclaimed:
                reclaim_time = current_time
                break
        if reclaim_time is None:
            return None

        future = nq.loc[
            (nq.index > reclaim_time) & (nq.index <= entry_cutoff)
        ]
        if future.empty:
            return None
        entry_time = future.index[0]
        next_open = float(future.iloc[0]["open"])
        entry = next_open + sign * TICK
        stop = (
            sweep_extreme + 2 * TICK
            if sign == -1
            else sweep_extreme - 2 * TICK
        )
        risk = sign * (entry - stop) / TICK
        if not (MIN_R <= risk <= MAX_R):
            return None
        return trade_record(
            "S2_NQ_DIVERGENCE_RECLAIM",
            date,
            nq,
            entry_time,
            exit_cutoff,
            sign,
            entry,
            risk,
        )
    return None


def trade_record(
    family: str,
    date: str,
    nq: pd.DataFrame,
    entry_time: pd.Timestamp,
    exit_cutoff: pd.Timestamp,
    sign: int,
    entry: float,
    risk: float,
) -> dict:
    trailing = simulate_management(
        nq, entry_time, exit_cutoff, sign, entry, risk, "RR2_TRAIL_1R"
    )
    fixed = simulate_management(
        nq, entry_time, exit_cutoff, sign, entry, risk, "FIXED_1R"
    )
    return {
        "family": family,
        "date": date,
        "year": int(date[:4]),
        "half": f"{date[:4]}-H{1 if int(date[5:7]) <= 6 else 2}",
        "side": "LONG" if sign == 1 else "SHORT",
        "entry_utc": entry_time.isoformat(),
        "entry": entry,
        "risk_ticks": risk,
        **trailing,
        "fixed_net_ticks": fixed["net_ticks"],
        "fixed_net_R": fixed["net_R"],
        "fixed_exit_reason": fixed["exit_reason"],
    }


def metrics(frame: pd.DataFrame, value_column: str = "net_R") -> dict:
    if frame.empty:
        return {"n": 0}
    values = frame[value_column].to_numpy(float)
    gains = values[values > 0].sum()
    losses = -values[values < 0].sum()
    year_ev = {
        str(int(year)): round(float(group[value_column].mean()), 5)
        for year, group in frame.groupby("year")
    }
    half_ev = {
        str(half): round(float(group[value_column].mean()), 5)
        for half, group in frame.groupby("half")
    }
    return {
        "n": int(values.size),
        "ev_R": round(float(values.mean()), 5),
        "median_R": round(float(np.median(values)), 5),
        "pf": round(float(gains / losses), 4) if losses > 0 else None,
        "win_rate_pct": round(float((values > 0).mean() * 100), 3),
        "positive_years": int(sum(value > 0 for value in year_ev.values())),
        "positive_halves_pct": round(
            100 * sum(value > 0 for value in half_ev.values()) / len(half_ev), 2
        ),
        "median_half_EV_R": round(float(np.median(list(half_ev.values()))), 5),
        "year_EV_R": year_ev,
        "half_EV_R": half_ev,
    }


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
        set(path.name for path in NQ_ROOT.iterdir() if path.is_dir())
        & set(path.name for path in ES_ROOT.iterdir() if path.is_dir())
    )
    rows: list[dict] = []
    errors: list[dict] = []
    for index, date in enumerate(dates, start=1):
        try:
            nq = load_session(NQ_ROOT, date)
            es = load_session(ES_ROOT, date)
            if nq is None or es is None:
                continue
            or_start = local_ts(date, "09:30:00")
            or_end = local_ts(date, "09:31:00")
            entry_cutoff = local_ts(date, "10:00:00")
            exit_cutoff = local_ts(date, "15:55:00")
            nq_or = opening_range(nq, or_start, or_end)
            es_or = opening_range(es, or_start, or_end)
            if nq_or is None or es_or is None:
                continue
            for finder in (s1_es_leads, s2_divergence_reclaim):
                row = finder(
                    date,
                    nq,
                    es,
                    nq_or,
                    es_or,
                    or_end,
                    entry_cutoff,
                    exit_cutoff,
                )
                if row is not None:
                    rows.append(row)
        except Exception as exc:  # noqa: BLE001
            errors.append({"date": date, "error": repr(exc)})
        if index % 100 == 0 or index == len(dates):
            print(
                f"[{index:4d}/{len(dates)}] trades={len(rows)} "
                f"errors={len(errors)}",
                flush=True,
            )

    trades = pd.DataFrame(rows).sort_values(["family", "date"])
    trades.to_csv(OUT / "DEV_ALL_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )

    dev = trades[
        (trades["date"] >= "2022-04-25") & (trades["date"] <= "2023-12-31")
    ]
    pseudo = trades[
        (trades["date"] >= "2024-01-01") & (trades["date"] <= "2024-12-31")
    ]
    stress = trades[trades["date"] >= "2025-01-01"]

    families = sorted(trades["family"].unique())
    dev_results = {}
    passing = []
    for family in families:
        frame = dev[dev["family"] == family]
        trail = metrics(frame)
        fixed = metrics(frame, "fixed_net_R")
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
                trail.get("ev_R", -999) - fixed.get("ev_R", 999) >= -0.05
            ),
        }
        dev_results[family] = {
            "TRAILING": trail,
            "FIXED_1R_DIAGNOSTIC": fixed,
            "trailing_minus_fixed_EV_R": round(
                trail.get("ev_R", 0) - fixed.get("ev_R", 0), 5
            ),
            "gates": gates,
            "PASS": all(gates.values()),
        }
        if all(gates.values()):
            passing.append(family)

    selected = None
    if passing:
        selected = sorted(
            passing,
            key=lambda family: (
                -dev_results[family]["TRAILING"]["median_half_EV_R"],
                family,
            ),
        )[0]

    pseudo_result = None
    authorize_holdout = False
    if selected is not None:
        selected_pseudo = pseudo[pseudo["family"] == selected]
        pseudo_metrics = metrics(selected_pseudo)
        ci = bootstrap_ci(selected_pseudo["net_R"].to_numpy(float))
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
        "study": "LUCID150K-SNIPER-V1",
        "prereg_sha256": PREREG_SHA,
        "dates_scanned": len(dates),
        "errors": len(errors),
        "trades_total": len(trades),
        "DEV": dev_results,
        "selected_family": selected,
        "PSEUDO_VAL_2024": pseudo_result,
        "STRESS_SEEN_2025_2026": {
            family: metrics(stress[stress["family"] == family])
            for family in families
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
