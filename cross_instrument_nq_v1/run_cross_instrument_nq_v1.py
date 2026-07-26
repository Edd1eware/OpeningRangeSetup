"""CROSS-INSTRUMENT-NQ-V1.

Rebuilds the 09:30 New York opening range with DST-aware timestamps, evaluates
the previously omitted EST sessions, and tests one frozen ES confirmation rule.
See PREREGISTRO_CROSS_INSTRUMENT_NQ_V1.md.
"""

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
PREREG = BASE / "PREREGISTRO_CROSS_INSTRUMENT_NQ_V1.md"
PREREG_SHA = "72fc5eae6be0b8aac00b5b7a29c64692ad1d2f0322b37c2027b9ed23f9a31637"

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TICK = 0.25
TP_SL = 60.0
COST_TICKS = 4.0
TICK_USD = 5.0
CONTRACTS = 3
TARGET_USD = 9_000.0
MLL_USD = 4_500.0
LOCKED_FLOOR_USD = 100.0
DLL_USD = 2_700.0
N_ATTEMPTS = 50_000
BOOTSTRAPS = 10_000
SEED = 0x22F9CADF098B1625


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


def session_boundaries(date: str) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    start_local = pd.Timestamp(f"{date} 09:30:00", tz=NY)
    end_local = pd.Timestamp(f"{date} 09:31:00", tz=NY)
    offset_hours = int(start_local.utcoffset().total_seconds() // 3600)
    return start_local.tz_convert(UTC), end_local.tz_convert(UTC), offset_hours


def opening_range(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[float, float] | None:
    window = frame.loc[(frame.index >= start) & (frame.index < end)]
    if window.empty:
        return None
    return float(window["high"].max()), float(window["low"].min())


def first_up_breakout(
    frame: pd.DataFrame, or_high: float, or_low: float, scan_start: pd.Timestamp
) -> pd.Timestamp | None:
    post = frame.loc[frame.index >= scan_start]
    if post.empty:
        return None
    up = post.index[post["high"] > or_high]
    down = post.index[post["low"] < or_low]
    if len(up) == 0:
        return None
    t_up = up[0]
    if len(down) and down[0] <= t_up:
        return None
    return t_up


def bracket_outcome(
    frame: pd.DataFrame, entry_time: pd.Timestamp, entry: float
) -> tuple[float, float, str]:
    """Return gross PnL ticks, MAE ticks through exit, and exit reason."""
    forward = frame.loc[frame.index >= entry_time]
    tp = entry + TP_SL * TICK
    sl = entry - TP_SL * TICK
    mae = 0.0
    last_close = entry
    for high, low, close in zip(
        forward["high"].to_numpy(float),
        forward["low"].to_numpy(float),
        forward["close"].to_numpy(float),
    ):
        last_close = close
        mae = min(mae, (low - entry) / TICK)
        if low <= sl:
            return -TP_SL, min(mae, -TP_SL), "SL"
        if high >= tp:
            return TP_SL, mae, "TP"
    return (last_close - entry) / TICK, mae, "EOD"


def build_row(date: str) -> dict | None:
    nq = load_session(NQ_ROOT, date)
    es = load_session(ES_ROOT, date)
    if nq is None or es is None:
        return None

    start, end, offset = session_boundaries(date)
    nq_or = opening_range(nq, start, end)
    es_or = opening_range(es, start, end)
    if nq_or is None or es_or is None:
        return None
    nq_high, nq_low = nq_or
    es_high, es_low = es_or

    entry_time = first_up_breakout(nq, nq_high, nq_low, end)
    if entry_time is None:
        return None

    es_prior = es.loc[es.index < entry_time]
    if es_prior.empty:
        return None
    es_last_time = es_prior.index[-1]
    es_last_close = float(es_prior.iloc[-1]["close"])
    es_confirm = es_last_close > es_high

    gross, mae, exit_reason = bracket_outcome(nq, entry_time, nq_high)
    return {
        "date": date,
        "year": int(date[:4]),
        "ny_utc_offset": offset,
        "season": "EST_HOLDOUT" if offset == -5 else "EDT_SEEN",
        "nq_entry_utc": entry_time.isoformat(),
        "nq_or_high": nq_high,
        "nq_or_low": nq_low,
        "es_or_high": es_high,
        "es_or_low": es_low,
        "es_last_utc": es_last_time.isoformat(),
        "es_lag_seconds": (entry_time - es_last_time).total_seconds(),
        "es_last_close": es_last_close,
        "es_confirm": bool(es_confirm),
        "gross_ticks": gross,
        "net_ticks": gross - COST_TICKS,
        "mae_ticks": mae,
        "mae_net_ticks": mae - COST_TICKS,
        "exit_reason": exit_reason,
    }


def metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"n": 0}
    net = frame["net_ticks"].to_numpy(float)
    gains = net[net > 0].sum()
    losses = -net[net < 0].sum()
    by_year = {
        str(int(year)): {
            "n": int(len(group)),
            "ev_net": round(float(group["net_ticks"].mean()), 4),
            "pf": round(
                float(
                    group.loc[group["net_ticks"] > 0, "net_ticks"].sum()
                    / -group.loc[group["net_ticks"] < 0, "net_ticks"].sum()
                ),
                4,
            )
            if (group["net_ticks"] < 0).any()
            else None,
        }
        for year, group in frame.groupby("year")
    }
    months = pd.to_datetime(frame["date"]).dt.to_period("M").nunique()
    return {
        "n": int(net.size),
        "months_observed": int(months),
        "trades_per_active_month": round(float(net.size / max(months, 1)), 3),
        "wr_pct": round(float((net > 0).mean() * 100), 3),
        "ev_net": round(float(net.mean()), 4),
        "pf": round(float(gains / losses), 4) if losses > 0 else None,
        "positive_year_blocks": int(
            sum(item["ev_net"] > 0 for item in by_year.values())
        ),
        "by_year": by_year,
    }


def bootstrap_mean_ci(net: np.ndarray) -> list[float]:
    rng = np.random.default_rng(SEED)
    means = np.empty(BOOTSTRAPS, dtype=float)
    for idx in range(BOOTSTRAPS):
        means[idx] = rng.choice(net, size=net.size, replace=True).mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return [round(float(low), 4), round(float(high), 4)]


def simulate_lucid(frame: pd.DataFrame, seed: int) -> dict:
    """Bootstrap complete LucidPro attempts, including intratrade MAE."""
    if frame.empty:
        return {"attempts": 0}
    net_usd = frame["net_ticks"].to_numpy(float) * TICK_USD * CONTRACTS
    mae_usd = frame["mae_net_ticks"].to_numpy(float) * TICK_USD * CONTRACTS
    rng = np.random.default_rng(seed)

    equity = np.zeros(N_ATTEMPTS, dtype=float)
    peak = np.zeros(N_ATTEMPTS, dtype=float)
    floor = np.full(N_ATTEMPTS, -MLL_USD, dtype=float)
    state = np.zeros(N_ATTEMPTS, dtype=np.int8)  # 0 active, 1 pass, -1 burn
    trades = np.zeros(N_ATTEMPTS, dtype=np.int32)

    for _ in range(20_000):  # computational guard, not an account timeout
        active = np.flatnonzero(state == 0)
        if active.size == 0:
            break
        samples = rng.integers(0, net_usd.size, size=active.size)
        trades[active] += 1

        intraday_low = equity[active] + mae_usd[samples]
        breached = intraday_low <= floor[active]
        if breached.any():
            state[active[breached]] = -1

        survivors = active[~breached]
        survivor_samples = samples[~breached]
        if survivors.size == 0:
            continue
        equity[survivors] += net_usd[survivor_samples]
        eod_breach = equity[survivors] <= floor[survivors]
        if eod_breach.any():
            state[survivors[eod_breach]] = -1

        still = survivors[~eod_breach]
        if still.size == 0:
            continue
        passed = equity[still] >= TARGET_USD
        if passed.any():
            state[still[passed]] = 1
        continuing = still[~passed]
        if continuing.size:
            peak[continuing] = np.maximum(peak[continuing], equity[continuing])
            floor[continuing] = np.minimum(
                peak[continuing] - MLL_USD, LOCKED_FLOOR_USD
            )

    passed_trades = trades[state == 1]
    monthly_frequency = metrics(frame).get("trades_per_active_month", 0.0)
    median_trades = (
        float(np.median(passed_trades)) if passed_trades.size else None
    )
    return {
        "attempts": N_ATTEMPTS,
        "p_pass": round(float((state == 1).mean()), 5),
        "p_burn": round(float((state == -1).mean()), 5),
        "p_unresolved_at_computational_guard": round(float((state == 0).mean()), 7),
        "median_trades_to_pass": median_trades,
        "estimated_active_months_to_pass": round(
            median_trades / monthly_frequency, 2
        )
        if median_trades is not None and monthly_frequency > 0
        else None,
        "contracts": CONTRACTS,
        "max_intraday_loss_usd": round(float(-mae_usd.min()), 2),
        "dll_usd": DLL_USD,
    }


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
    for idx, date in enumerate(dates, start=1):
        try:
            row = build_row(date)
            if row is not None:
                rows.append(row)
        except Exception as exc:  # noqa: BLE001
            errors.append({"date": date, "error": repr(exc)})
        if idx % 100 == 0 or idx == len(dates):
            print(f"[{idx:4d}/{len(dates)}] trades={len(rows)} errors={len(errors)}")

    trades = pd.DataFrame(rows).sort_values("date")
    trades.to_csv(OUT / "DST_CORRECT_ES_NQ_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )

    holdout = trades[trades["season"] == "EST_HOLDOUT"].copy()
    seen = trades[trades["season"] == "EDT_SEEN"].copy()
    holdout_confirm = holdout[holdout["es_confirm"]].copy()
    seen_confirm = seen[seen["es_confirm"]].copy()

    base_metrics = metrics(holdout)
    confirm_metrics = metrics(holdout_confirm)
    confirm_ci = bootstrap_mean_ci(
        holdout_confirm["net_ticks"].to_numpy(float)
    )
    ev_improvement = (
        confirm_metrics.get("ev_net", float("nan"))
        - base_metrics.get("ev_net", float("nan"))
    )

    base_gates = {
        "B1_ev_net_gt_0": bool(base_metrics.get("ev_net", 0) > 0),
        "B2_pf_gt_1_10": bool(
            base_metrics.get("pf") is not None and base_metrics["pf"] > 1.10
        ),
        "B3_positive_year_blocks_ge_3": bool(
            base_metrics.get("positive_year_blocks", 0) >= 3
        ),
        "B4_n_ge_100": bool(base_metrics.get("n", 0) >= 100),
    }
    confirm_gates = {
        "C1_ev_net_gt_0": bool(confirm_metrics.get("ev_net", 0) > 0),
        "C2_pf_gt_1_15": bool(
            confirm_metrics.get("pf") is not None
            and confirm_metrics["pf"] > 1.15
        ),
        "C3_ev_improvement_ge_2": bool(ev_improvement >= 2.0),
        "C4_positive_year_blocks_ge_3": bool(
            confirm_metrics.get("positive_year_blocks", 0) >= 3
        ),
        "C5_n_ge_50": bool(confirm_metrics.get("n", 0) >= 50),
        "C6_bootstrap_ci_low_gt_0": bool(confirm_ci[0] > 0),
    }

    base_pass = all(base_gates.values())
    confirm_pass = all(confirm_gates.values())
    if base_pass and confirm_pass:
        classification = "BASE_PASS_ES_CONFIRM_PASS"
    elif base_pass:
        classification = "BASE_PASS_ES_CONFIRM_FAIL"
    elif confirm_pass:
        classification = "BASE_FAIL_ES_CONFIRM_PASS_REQUIRES_FORWARD"
    else:
        classification = "BASE_FAIL_ES_CONFIRM_FAIL"

    result = {
        "study": "CROSS-INSTRUMENT-NQ-V1",
        "prereg_sha256": PREREG_SHA,
        "paired_dates_scanned": len(dates),
        "errors": len(errors),
        "trade_rows": len(trades),
        "cost_ticks": COST_TICKS,
        "PRIMARY_EST_HOLDOUT": {
            "BASE": base_metrics,
            "ES_CONFIRM": confirm_metrics,
            "ES_CONFIRM_bootstrap_EV_CI95": confirm_ci,
            "ES_CONFIRM_EV_improvement_vs_BASE": round(
                float(ev_improvement), 4
            ),
            "BASE_gates": base_gates,
            "ES_CONFIRM_gates": confirm_gates,
            "lucid150k_BASE": simulate_lucid(holdout, SEED + 1),
            "lucid150k_ES_CONFIRM": simulate_lucid(holdout_confirm, SEED + 2),
        },
        "DESCRIPTIVE_EDT_SEEN": {
            "BASE": metrics(seen),
            "ES_CONFIRM": metrics(seen_confirm),
        },
        "classification": classification,
    }
    (OUT / "RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
