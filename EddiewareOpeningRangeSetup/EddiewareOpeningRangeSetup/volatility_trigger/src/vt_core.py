from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY = ZoneInfo("America/New_York")
TICKS_PER_SECOND = 10_000_000
TICKS_PER_MILLISECOND = 10_000
DOTNET_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class LiquidityBurst:
    lb_id: str
    session_date: str
    source_second_ticks: int
    publish_ticks: int
    side: str
    direction: int
    price_raw: int
    delta_1s: int
    delta_3s: int
    delta_change_1s: int
    delta_change_zscore: float
    delta_percentile: float
    trades_per_second: int
    contracts_per_second: int
    velocity_1s: float
    acceleration_1s: float
    cumulative_delta: int


@dataclass(frozen=True)
class SecondBucket:
    second_ticks: int
    open_raw: int
    high_raw: int
    low_raw: int
    close_raw: int
    buy_volume: int
    sell_volume: int
    volume: int
    delta: int
    trades: int
    first_trade_ticks: int
    delta_change_1s: int = 0


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def datetime_to_dotnet_ticks(value: datetime) -> int:
    value = value.astimezone(timezone.utc)
    ordinal_days = value.date().toordinal() - 1
    day_ticks = (
        (value.hour * 3600 + value.minute * 60 + value.second)
        * TICKS_PER_SECOND
        + value.microsecond * 10
    )
    return ordinal_days * 86400 * TICKS_PER_SECOND + day_ticks


def dotnet_ticks_to_datetime(value: int) -> datetime:
    seconds, remainder = divmod(int(value), TICKS_PER_SECOND)
    return DOTNET_EPOCH + timedelta(
        seconds=seconds,
        microseconds=remainder // 10,
    )


def ticks_iso(value: int) -> str:
    return dotnet_ticks_to_datetime(value).isoformat()


def business_dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def session_bounds(session_date: date) -> dict[str, int]:
    def at(clock: time) -> int:
        return datetime_to_dotnet_ticks(
            datetime.combine(session_date, clock, tzinfo=NY)
        )

    return {
        "session_start": at(time(0, 0)),
        "detection_start": at(time(9, 30)),
        "detection_end": at(time(16, 0)),
        "load_end": at(time(16, 0, 20)),
    }


def contiguous_trade_ticks(trades: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(trades["ticks"], dtype=np.int64)


def causalize_trade_timestamps(
    trades: np.ndarray,
    qc: Mapping[str, object],
) -> tuple[np.ndarray, dict[str, float | int | str]]:
    """Make file-order timestamps monotonic without advancing any trade."""
    raw_ticks = contiguous_trade_ticks(trades)
    differences = np.diff(raw_ticks)
    negative = differences[differences < 0]
    count = int(len(negative))
    largest_ms = (
        float(-negative.min() / TICKS_PER_MILLISECOND)
        if count
        else 0.0
    )
    max_count = int(qc["max_backtrack_count"])
    max_single_ms = float(qc["max_single_backtrack_ms"])
    if count > max_count or largest_ms > max_single_ms:
        raise ValueError(
            "timestamp QC failed: "
            f"backtracks={count}>{max_count} or "
            f"largest_ms={largest_ms:.6f}>{max_single_ms:.6f}"
        )

    if count:
        effective_ticks = np.maximum.accumulate(raw_ticks)
        normalized = trades.copy()
        normalized["ticks"] = effective_ticks
    else:
        effective_ticks = raw_ticks
        normalized = trades
    return normalized, {
        "timestamp_policy": str(qc["causal_policy"]),
        "raw_timestamp_backtracks": count,
        "largest_raw_backtrack_ms": largest_ms,
        "timestamps_repaired": count,
        "effective_timestamp_backtracks": int(
            np.sum(np.diff(effective_ticks) < 0)
        ),
    }


def _bucket_from_slice(rows: np.ndarray, start: int, stop: int) -> SecondBucket:
    part = rows[start:stop]
    prices = part["price_raw"].astype(np.int64)
    volumes = part["volume_raw"].astype(np.int64)
    sides = part["side_code"]
    buy = int(volumes[sides == 1].sum())
    sell = int(volumes[sides == 2].sum())
    return SecondBucket(
        second_ticks=int(part[0]["ticks"] // TICKS_PER_SECOND * TICKS_PER_SECOND),
        open_raw=int(prices[0]),
        high_raw=int(prices.max()),
        low_raw=int(prices.min()),
        close_raw=int(prices[-1]),
        buy_volume=buy,
        sell_volume=sell,
        volume=int(volumes.sum()),
        delta=buy - sell,
        trades=int(len(part)),
        first_trade_ticks=int(part[0]["ticks"]),
    )


def aggregate_trade_seconds(trades: np.ndarray) -> list[SecondBucket]:
    if len(trades) == 0:
        return []
    seconds = trades["ticks"] // TICKS_PER_SECOND
    starts = np.flatnonzero(
        np.r_[True, seconds[1:] != seconds[:-1]]
    )
    stops = np.r_[starts[1:], len(trades)]
    return [
        _bucket_from_slice(trades, int(start), int(stop))
        for start, stop in zip(starts, stops)
    ]


def _reference_bucket(
    history: Sequence[SecondBucket],
    reference_second_ticks: int,
) -> SecondBucket | None:
    for bucket in reversed(history):
        if bucket.second_ticks <= reference_second_ticks:
            return bucket
    return None


def _velocity(
    history: Sequence[SecondBucket],
    current: SecondBucket,
    seconds: int,
) -> float:
    reference = _reference_bucket(
        history,
        current.second_ticks - max(1, seconds) * TICKS_PER_SECOND,
    )
    if reference is None:
        return 0.0
    return (current.close_raw - reference.close_raw) / max(1, seconds)


def _sum_delta(
    history: Sequence[SecondBucket],
    current: SecondBucket,
    seconds: int,
) -> int:
    start = current.second_ticks - (max(1, seconds) - 1) * TICKS_PER_SECOND
    total = current.delta
    for bucket in reversed(history):
        if bucket.second_ticks < start:
            break
        total += bucket.delta
    return int(total)


def detect_liquidity_bursts(
    trades: np.ndarray,
    session_date: date,
    detector: Mapping[str, object],
) -> list[LiquidityBurst]:
    """Reproduce the frozen one-second detector using trade data only.

    The publish timestamp is the first trade timestamp of the next real second,
    matching `AdvanceToSecond(..., detectorPublishTimestampUtc=timeUtc)`.
    """

    raw_buckets = aggregate_trade_seconds(trades)
    if len(raw_buckets) < 2:
        return []

    bounds = session_bounds(session_date)
    history: list[SecondBucket] = []
    bursts: list[LiquidityBurst] = []
    last_velocity_1s = 0.0
    last_velocity_3s = 0.0
    last_buy_second: int | None = None
    last_sell_second: int | None = None
    burst_sequence = 0
    max_gap = int(detector["max_gap_fill_seconds"])

    def finalize(
        current: SecondBucket,
        publish_ticks: int,
    ) -> None:
        nonlocal last_velocity_1s, last_velocity_3s
        nonlocal last_buy_second, last_sell_second, burst_sequence

        previous_delta = history[-1].delta if history else 0
        delta_change = current.delta - previous_delta
        baseline_ready = len(history) >= int(detector["min_baseline_seconds"])
        baseline = history[
            max(0, len(history) - int(detector["history_seconds"])) :
        ]
        if baseline_ready and len(baseline) >= 2:
            prior_changes = np.asarray(
                [row.delta_change_1s for row in baseline],
                dtype=float,
            )
            std = float(prior_changes.std(ddof=0))
            zscore = (
                (delta_change - float(prior_changes.mean())) / std
                if std > 0
                else 0.0
            )
            percentile = float(
                np.mean(np.abs(prior_changes) <= abs(delta_change))
            )
        else:
            zscore = 0.0
            percentile = 0.0

        delta_1s = _sum_delta(history, current, 1)
        delta_3s = _sum_delta(history, current, 3)
        cumulative = _sum_delta(
            history,
            current,
            int(detector["cumulative_window_seconds"]),
        )
        velocity_1s = _velocity(history, current, 1)
        velocity_3s = _velocity(history, current, 3)
        acceleration_1s = velocity_1s - last_velocity_1s
        _ = velocity_3s - last_velocity_3s

        in_window = (
            bounds["detection_start"]
            <= current.second_ticks
            <= bounds["detection_end"]
        )
        percentile_pass = (
            percentile >= float(detector["delta_percentile_threshold"])
        )
        activity_pass = (
            current.trades >= int(detector["min_trades_per_second"])
            and current.volume >= int(detector["min_contracts_per_second"])
        )
        velocity_required = bool(detector["require_price_velocity"])
        min_velocity = float(detector.get("min_velocity_ticks_per_second", 1.0))

        buy_core = (
            baseline_ready
            and delta_1s > int(detector["min_abs_delta_1s"])
            and delta_change > int(detector["min_abs_delta_change_1s"])
            and zscore >= float(detector["delta_change_zscore_threshold"])
            and percentile_pass
            and activity_pass
            and cumulative >= int(detector["min_abs_cumulative_delta"])
            and (not velocity_required or velocity_1s >= min_velocity)
        )
        sell_core = (
            baseline_ready
            and delta_1s < -int(detector["min_abs_delta_1s"])
            and delta_change < -int(detector["min_abs_delta_change_1s"])
            and zscore <= -float(detector["delta_change_zscore_threshold"])
            and percentile_pass
            and activity_pass
            and cumulative <= -int(detector["min_abs_cumulative_delta"])
            and (not velocity_required or velocity_1s <= -min_velocity)
        )

        cooldown_ticks = int(detector["cooldown_seconds"]) * TICKS_PER_SECOND
        candidates: list[tuple[str, int]] = []
        if (
            in_window
            and current.trades > 0
            and buy_core
            and (
                last_buy_second is None
                or current.second_ticks - last_buy_second >= cooldown_ticks
            )
        ):
            candidates.append(("BUY", 1))
        if (
            in_window
            and current.trades > 0
            and sell_core
            and (
                last_sell_second is None
                or current.second_ticks - last_sell_second >= cooldown_ticks
            )
        ):
            candidates.append(("SELL", -1))

        for side, direction in candidates:
            burst_sequence += 1
            ny_time = dotnet_ticks_to_datetime(
                current.second_ticks
            ).astimezone(NY)
            lb_id = (
                f"LB_{ny_time:%Y%m%d_%H%M%S}_{side}_{burst_sequence:04d}"
            )
            bursts.append(
                LiquidityBurst(
                    lb_id=lb_id,
                    session_date=session_date.isoformat(),
                    source_second_ticks=current.second_ticks,
                    publish_ticks=publish_ticks,
                    side=side,
                    direction=direction,
                    price_raw=current.close_raw,
                    delta_1s=delta_1s,
                    delta_3s=delta_3s,
                    delta_change_1s=delta_change,
                    delta_change_zscore=zscore,
                    delta_percentile=percentile,
                    trades_per_second=current.trades,
                    contracts_per_second=current.volume,
                    velocity_1s=velocity_1s,
                    acceleration_1s=acceleration_1s,
                    cumulative_delta=cumulative,
                )
            )
            if side == "BUY":
                last_buy_second = current.second_ticks
            else:
                last_sell_second = current.second_ticks

        history.append(
            SecondBucket(
                **{
                    **asdict(current),
                    "delta_change_1s": delta_change,
                }
            )
        )
        keep = max(
            int(detector["history_seconds"]),
            int(detector["cumulative_window_seconds"]),
            10,
        ) + 15
        min_second = current.second_ticks - keep * TICKS_PER_SECOND
        while history and history[0].second_ticks < min_second:
            history.pop(0)
        last_velocity_1s = velocity_1s
        last_velocity_3s = velocity_3s

    for index, current in enumerate(raw_buckets[:-1]):
        next_real = raw_buckets[index + 1]
        publish_ticks = next_real.first_trade_ticks
        finalize(current, publish_ticks)
        gap = (
            next_real.second_ticks - current.second_ticks
        ) // TICKS_PER_SECOND - 1
        carry = current.close_raw
        for offset in range(1, min(max(0, int(gap)), max_gap) + 1):
            empty = SecondBucket(
                second_ticks=current.second_ticks + offset * TICKS_PER_SECOND,
                open_raw=carry,
                high_raw=carry,
                low_raw=carry,
                close_raw=carry,
                buy_volume=0,
                sell_volume=0,
                volume=0,
                delta=0,
                trades=0,
                first_trade_ticks=publish_ticks,
            )
            finalize(empty, publish_ticks)
    return bursts


def _last_index_at(trade_ticks: np.ndarray, at_ticks: int) -> int:
    return int(np.searchsorted(trade_ticks, at_ticks, side="right")) - 1


def _window(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    end_ticks: int,
    milliseconds: int,
) -> np.ndarray:
    start_ticks = end_ticks - milliseconds * TICKS_PER_MILLISECOND
    start = int(np.searchsorted(trade_ticks, start_ticks, side="left"))
    stop = int(np.searchsorted(trade_ticks, end_ticks, side="right"))
    return trades[start:stop]


def _last_price_at(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    at_ticks: int,
) -> int | None:
    index = _last_index_at(trade_ticks, at_ticks)
    if index < 0:
        return None
    return int(trades[index]["price_raw"])


def _signed_velocity(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    end_ticks: int,
    milliseconds: int,
    direction: int,
) -> float:
    end_price = _last_price_at(trades, trade_ticks, end_ticks)
    start_price = _last_price_at(
        trades,
        trade_ticks,
        end_ticks - milliseconds * TICKS_PER_MILLISECOND,
    )
    if end_price is None or start_price is None:
        return math.nan
    return (
        direction
        * (end_price - start_price)
        / max(milliseconds / 1000.0, 1e-9)
    )


def _trade_rate(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    end_ticks: int,
    milliseconds: int,
) -> float:
    return len(_window(trades, trade_ticks, end_ticks, milliseconds)) / (
        milliseconds / 1000.0
    )


def _delta_and_volume(rows: np.ndarray) -> tuple[int, int, int]:
    if len(rows) == 0:
        return 0, 0, 0
    volume = rows["volume_raw"].astype(np.int64)
    buy = int(volume[rows["side_code"] == 1].sum())
    sell = int(volume[rows["side_code"] == 2].sum())
    return buy - sell, buy, sell


def _directional_efficiency(
    rows: np.ndarray,
    entry_price_raw: int,
    direction: int,
) -> float:
    if len(rows) == 0:
        return 0.0
    prices = np.r_[entry_price_raw, rows["price_raw"].astype(np.int64)]
    path = float(np.abs(np.diff(prices)).sum())
    net = float(direction * (prices[-1] - entry_price_raw))
    return max(0.0, net) / max(path, 1e-12)


def _max_run(values: np.ndarray, target: int) -> int:
    best = 0
    current = 0
    for value in values:
        if int(value) == target:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _terminal_run(values: np.ndarray, target: int) -> int:
    result = 0
    for value in values[::-1]:
        if int(value) != target:
            break
        result += 1
    return result


def _value_area(
    volume_by_price: np.ndarray,
    price_min: int,
    coverage: float = 0.70,
) -> tuple[int, int, int]:
    if len(volume_by_price) == 0 or float(volume_by_price.sum()) <= 0:
        return price_min, price_min, price_min
    poc_index = int(np.argmax(volume_by_price))
    target = float(volume_by_price.sum()) * coverage
    lo = hi = poc_index
    accumulated = float(volume_by_price[poc_index])
    while accumulated < target and (lo > 0 or hi < len(volume_by_price) - 1):
        left = float(volume_by_price[lo - 1]) if lo > 0 else -1.0
        right = (
            float(volume_by_price[hi + 1])
            if hi < len(volume_by_price) - 1
            else -1.0
        )
        if right >= left:
            hi += 1
            accumulated += float(volume_by_price[hi])
        else:
            lo -= 1
            accumulated += float(volume_by_price[lo])
    return price_min + poc_index, price_min + hi, price_min + lo


def profile_snapshots(
    trades: np.ndarray,
    target_ticks: Sequence[int],
    trade_ticks: np.ndarray | None = None,
) -> dict[int, dict[str, object]]:
    if len(trades) == 0:
        return {}
    if trade_ticks is None:
        trade_ticks = contiguous_trade_ticks(trades)
    targets = sorted(set(int(value) for value in target_ticks))
    prices = trades["price_raw"].astype(np.int64)
    price_min = int(prices.min())
    price_max = int(prices.max())
    width = price_max - price_min + 1
    volume_by_price = np.zeros(width, dtype=np.float64)
    delta_by_price = np.zeros(width, dtype=np.float64)
    snapshots: dict[int, dict[str, object]] = {}
    prior_stop = 0
    total_volume = 0.0
    total_pv = 0.0
    total_p2v = 0.0

    for target in targets:
        stop = int(np.searchsorted(trade_ticks, target, side="right"))
        if stop > prior_stop:
            part = trades[prior_stop:stop]
            indices = part["price_raw"].astype(np.int64) - price_min
            volumes = part["volume_raw"].astype(np.float64)
            signs = np.where(
                part["side_code"] == 1,
                1.0,
                np.where(part["side_code"] == 2, -1.0, 0.0),
            )
            volume_by_price += np.bincount(
                indices,
                weights=volumes,
                minlength=width,
            )
            delta_by_price += np.bincount(
                indices,
                weights=volumes * signs,
                minlength=width,
            )
            raw_prices = part["price_raw"].astype(np.float64)
            total_volume += float(volumes.sum())
            total_pv += float((raw_prices * volumes).sum())
            total_p2v += float((raw_prices * raw_prices * volumes).sum())
            prior_stop = stop

        poc, vah, val = _value_area(volume_by_price, price_min)
        vwap = total_pv / total_volume if total_volume > 0 else math.nan
        variance = (
            max(total_p2v / total_volume - vwap * vwap, 0.0)
            if total_volume > 0
            else math.nan
        )
        active = volume_by_price > 0
        active_delta = np.abs(delta_by_price[active])
        threshold = (
            float(np.quantile(active_delta, 0.95))
            if active_delta.size
            else math.inf
        )
        prices_axis = np.arange(price_min, price_max + 1)
        bull_levels = tuple(
            int(value)
            for value in prices_axis[
                (delta_by_price >= threshold) & active
            ]
        )
        bear_levels = tuple(
            int(value)
            for value in prices_axis[
                (delta_by_price <= -threshold) & active
            ]
        )
        snapshots[target] = {
            "poc_raw": poc,
            "vah_raw": vah,
            "val_raw": val,
            "vwap_raw": vwap,
            "profile_std_ticks": math.sqrt(variance)
            if math.isfinite(variance)
            else math.nan,
            "total_volume": total_volume,
            "bull_delta_levels": bull_levels,
            "bear_delta_levels": bear_levels,
        }
    return snapshots


def _nearest_distance(
    levels: Sequence[int],
    price_raw: int,
) -> float:
    if not levels:
        return math.nan
    return float(min(abs(int(level) - price_raw) for level in levels))


def _acceptance_features(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    start_ticks: int,
    end_ticks: int,
    level_raw: int,
    direction: int,
) -> dict[str, float]:
    start = int(np.searchsorted(trade_ticks, start_ticks, side="left"))
    stop = int(np.searchsorted(trade_ticks, end_ticks, side="right"))
    rows = trades[start:stop]
    if len(rows) == 0 or end_ticks <= start_ticks:
        return {
            "acc_hold_duration_ms": 0.0,
            "acc_retention_ratio": 0.0,
            "acc_volume_ratio": 0.0,
            "acc_volume_time_agreement": 0.0,
        }

    relative = direction * (
        rows["price_raw"].astype(np.int64) - int(level_raw)
    )
    outside = relative > 0
    event_ticks = trade_ticks[start:stop]
    segment_ends = np.r_[event_ticks[1:], end_ticks]
    durations = np.maximum(segment_ends - event_ticks, 0)
    retention = float(
        durations[outside].sum() / max(end_ticks - start_ticks, 1)
    )
    volumes = rows["volume_raw"].astype(np.float64)
    volume_ratio = float(
        volumes[outside].sum() / max(volumes.sum(), 1.0)
    )
    if bool(outside[-1]):
        last_inside = np.flatnonzero(~outside)
        hold_start = (
            int(event_ticks[last_inside[-1] + 1])
            if last_inside.size and last_inside[-1] + 1 < len(rows)
            else int(event_ticks[0])
        )
        hold_ms = (end_ticks - hold_start) / TICKS_PER_MILLISECOND
    else:
        hold_ms = 0.0
    return {
        "acc_hold_duration_ms": float(max(hold_ms, 0.0)),
        "acc_retention_ratio": retention,
        "acc_volume_ratio": volume_ratio,
        "acc_volume_time_agreement": (retention + volume_ratio) / 2.0,
    }


def _footprint_features(
    rows: np.ndarray,
    direction: int,
) -> dict[str, float]:
    if len(rows) == 0:
        return {
            "fp_aligned_stacked_count": 0.0,
            "fp_opposing_stacked_count": 0.0,
            "fp_effort_result_ratio": 0.0,
        }
    prices = rows["price_raw"].astype(np.int64)
    lo = int(prices.min())
    width = int(prices.max()) - lo + 1
    indices = prices - lo
    volumes = rows["volume_raw"].astype(np.float64)
    buy = np.bincount(
        indices,
        weights=volumes * (rows["side_code"] == 1),
        minlength=width,
    )
    sell = np.bincount(
        indices,
        weights=volumes * (rows["side_code"] == 2),
        minlength=width,
    )
    buy_imbalance = np.zeros(width, dtype=bool)
    sell_imbalance = np.zeros(width, dtype=bool)
    if width > 1:
        buy_imbalance[1:] = buy[1:] >= 3.0 * np.maximum(sell[:-1], 1.0)
        sell_imbalance[:-1] = sell[:-1] >= 3.0 * np.maximum(buy[1:], 1.0)
    buy_stacks = _max_run(buy_imbalance.astype(np.int8), 1)
    sell_stacks = _max_run(sell_imbalance.astype(np.int8), 1)
    delta = float(buy.sum() - sell.sum())
    progress = float(abs(int(prices[-1]) - int(prices[0])))
    aligned = buy_stacks if direction > 0 else sell_stacks
    opposing = sell_stacks if direction > 0 else buy_stacks
    return {
        "fp_aligned_stacked_count": float(aligned),
        "fp_opposing_stacked_count": float(opposing),
        "fp_effort_result_ratio": abs(delta) / max(progress, 1.0),
    }


def compute_outcomes(
    trades: np.ndarray,
    candidate_ticks: int,
    direction: int,
    config: Mapping[str, object],
    trade_ticks: np.ndarray | None = None,
) -> dict[str, float | int | str]:
    if trade_ticks is None:
        trade_ticks = contiguous_trade_ticks(trades)
    entry_price = _last_price_at(trades, trade_ticks, candidate_ticks)
    if entry_price is None:
        return {"outcome_valid": 0, "sniper_success": 0}
    horizon_ms = int(config["outcome_horizon_ms"])
    stop = int(
        np.searchsorted(
            trade_ticks,
            candidate_ticks + horizon_ms * TICKS_PER_MILLISECOND,
            side="right",
        )
    )
    start = int(np.searchsorted(trade_ticks, candidate_ticks, side="right"))
    future = trades[start:stop]
    if len(future) == 0:
        return {"outcome_valid": 0, "sniper_success": 0}

    signed_moves = direction * (
        future["price_raw"].astype(np.int64) - entry_price
    )
    future_ticks = trade_ticks[start:stop]
    reach4 = np.flatnonzero(signed_moves >= 4)
    time_to_4_ms = (
        (int(future_ticks[reach4[0]]) - candidate_ticks)
        / TICKS_PER_MILLISECOND
        if reach4.size
        else math.inf
    )
    until = int(reach4[0]) + 1 if reach4.size else len(future)
    pre_ae = float(max(0, -int(signed_moves[:until].min())))

    running_favorable = np.maximum.accumulate(signed_moves)
    pullback = running_favorable - signed_moves
    pullback_hit = np.flatnonzero(pullback >= 3)
    impulse_stop = int(pullback_hit[0]) if pullback_hit.size else len(future) - 1
    initial_mfe = float(max(0, int(running_favorable[impulse_stop])))

    displacements: dict[int, float] = {}
    efficiencies: dict[int, float] = {}
    for milliseconds in (100, 250, 500, 1000, 2000, 3000, 5000):
        target = candidate_ticks + milliseconds * TICKS_PER_MILLISECOND
        end_index = int(np.searchsorted(future_ticks, target, side="right"))
        path_rows = future[:end_index]
        price = (
            int(path_rows[-1]["price_raw"])
            if len(path_rows)
            else entry_price
        )
        displacements[milliseconds] = float(direction * (price - entry_price))
        efficiencies[milliseconds] = _directional_efficiency(
            path_rows,
            entry_price,
            direction,
        )

    gate = config["sniper_success"]
    sniper = int(
        time_to_4_ms <= float(gate["time_to_impulse_4t_max_ms"])
        and displacements[1000]
        >= float(gate["signed_displacement_1s_min_ticks"])
        and displacements[2000]
        >= float(gate["signed_displacement_2s_min_ticks"])
        and pre_ae <= float(gate["pre_expansion_ae_4t_max_ticks"])
        and initial_mfe
        >= float(gate["initial_impulse_mfe_3t_pullback_min_ticks"])
        and efficiencies[2000]
        >= float(gate["directional_efficiency_2s_min"])
    )
    return {
        "outcome_valid": 1,
        "entry_price_raw": entry_price,
        "time_to_impulse_4t_ms": time_to_4_ms,
        "pre_expansion_ae_4t": pre_ae,
        "initial_impulse_mfe_3t_pullback": initial_mfe,
        **{
            f"signed_displacement_{milliseconds}ms": value
            for milliseconds, value in displacements.items()
        },
        **{
            f"directional_efficiency_{milliseconds}ms": value
            for milliseconds, value in efficiencies.items()
        },
        "sniper_success": sniper,
    }


def _profile_for(
    snapshots: Mapping[int, dict[str, object]],
    target: int,
) -> dict[str, object]:
    return snapshots[int(target)]


def compute_candidate_features(
    trades: np.ndarray,
    burst: LiquidityBurst,
    candidate_ticks: int,
    direction: int,
    profiles: Mapping[int, dict[str, object]],
    trade_ticks: np.ndarray | None = None,
) -> dict[str, float | int | str]:
    if trade_ticks is None:
        trade_ticks = contiguous_trade_ticks(trades)
    last_index = _last_index_at(trade_ticks, candidate_ticks)
    if last_index < 0:
        raise ValueError("candidate has no causal trade")
    price_raw = int(trades[last_index]["price_raw"])
    max_feature_ticks = int(trade_ticks[last_index])
    profile = _profile_for(profiles, candidate_ticks)
    profile_30 = _profile_for(
        profiles,
        candidate_ticks - 30 * TICKS_PER_SECOND,
    )

    rows_100 = _window(trades, trade_ticks, candidate_ticks, 100)
    rows_250 = _window(trades, trade_ticks, candidate_ticks, 250)
    rows_500 = _window(trades, trade_ticks, candidate_ticks, 500)
    rows_1000 = _window(trades, trade_ticks, candidate_ticks, 1000)
    rows_2000 = _window(trades, trade_ticks, candidate_ticks, 2000)
    delta_500, buy_500, sell_500 = _delta_and_volume(rows_500)
    total_500 = buy_500 + sell_500
    signed_move_500 = _signed_velocity(
        trades,
        trade_ticks,
        candidate_ticks,
        500,
        direction,
    ) * 0.5
    aligned_aggression = buy_500 if direction > 0 else sell_500

    interarrival_recent = (
        np.diff(rows_100["ticks"].astype(np.int64))
        / TICKS_PER_MILLISECOND
        if len(rows_100) >= 2
        else np.asarray([], dtype=float)
    )
    interarrival_slow = (
        np.diff(rows_2000["ticks"].astype(np.int64))
        / TICKS_PER_MILLISECOND
        if len(rows_2000) >= 2
        else np.asarray([], dtype=float)
    )
    recent_median = (
        float(np.median(interarrival_recent))
        if interarrival_recent.size
        else math.nan
    )
    slow_median = (
        float(np.median(interarrival_slow))
        if interarrival_slow.size
        else math.nan
    )
    compression = (
        slow_median / max(recent_median, 1e-9)
        if math.isfinite(recent_median) and math.isfinite(slow_median)
        else math.nan
    )
    target_side = 1 if direction > 0 else 2
    aggressor_run = _terminal_run(rows_500["side_code"], target_side)

    signed_velocities = [
        _signed_velocity(
            trades,
            trade_ticks,
            candidate_ticks,
            ms,
            direction,
        )
        for ms in (100, 250, 500, 1000)
    ]
    multiscale = float(
        np.mean([value > 0 for value in signed_velocities if math.isfinite(value)])
    )

    vwap_raw = float(profile["vwap_raw"])
    profile_std = float(profile["profile_std_ticks"])
    vwap_distance = direction * (price_raw - vwap_raw)
    vwap_30 = float(profile_30["vwap_raw"])
    vwap_slope = direction * (vwap_raw - vwap_30) / 30.0
    start_500_price = _last_price_at(
        trades,
        trade_ticks,
        candidate_ticks - 500 * TICKS_PER_MILLISECOND,
    )
    vwap_reclaim = int(
        start_500_price is not None
        and direction * (start_500_price - vwap_raw) <= 0
        and direction * (price_raw - vwap_raw) > 0
    )
    vwap_hold = (
        float(
            np.mean(
                direction
                * (rows_500["price_raw"].astype(np.float64) - vwap_raw)
                > 0
            )
        )
        if len(rows_500)
        else 0.0
    )

    acceptance = _acceptance_features(
        trades,
        trade_ticks,
        burst.publish_ticks,
        candidate_ticks,
        burst.price_raw,
        direction,
    )
    footprint = _footprint_features(rows_500, direction)
    bull_levels = profile["bull_delta_levels"]
    bear_levels = profile["bear_delta_levels"]
    favorable_levels = bull_levels if direction > 0 else bear_levels
    opposing_levels = bear_levels if direction > 0 else bull_levels

    directional_eff_500 = _directional_efficiency(
        rows_500,
        int(rows_500[0]["price_raw"]) if len(rows_500) else price_raw,
        direction,
    )
    inside_value = int(
        int(profile["val_raw"]) <= price_raw <= int(profile["vah_raw"])
    )
    poc_migration = direction * (
        int(profile["poc_raw"]) - int(profile_30["poc_raw"])
    )
    path_eff_2s = _directional_efficiency(
        rows_2000,
        int(rows_2000[0]["price_raw"]) if len(rows_2000) else price_raw,
        direction,
    )
    vwap_crosses = 0
    if len(rows_2000) >= 2:
        relative = rows_2000["price_raw"].astype(np.float64) - vwap_raw
        signs = np.sign(relative)
        vwap_crosses = int(np.sum(signs[1:] * signs[:-1] < 0))
    amt_balance = float(
        np.mean(
            [
                inside_value,
                min(vwap_crosses / 3.0, 1.0),
                1.0 - min(path_eff_2s, 1.0),
                1.0 if abs(poc_migration) <= 1 else 0.0,
            ]
        )
    )
    directional_outside = (
        price_raw > int(profile["vah_raw"])
        if direction > 0
        else price_raw < int(profile["val_raw"])
    )
    amt_imbalance = float(
        np.mean(
            [
                float(directional_outside),
                float(poc_migration > 0),
                min(path_eff_2s, 1.0),
                float(vwap_distance > 0),
            ]
        )
    )

    return {
        "session_date": burst.session_date,
        "lb_id": burst.lb_id,
        "lb_source_second_utc": ticks_iso(burst.source_second_ticks),
        "lb_publish_utc": ticks_iso(burst.publish_ticks),
        "candidate_utc": ticks_iso(candidate_ticks),
        "candidate_ticks": candidate_ticks,
        "candidate_direction": direction,
        "candidate_side": "BUY" if direction > 0 else "SELL",
        "time_since_lb_ms": (
            candidate_ticks - burst.publish_ticks
        ) / TICKS_PER_MILLISECOND,
        "max_feature_timestamp_ticks": max_feature_ticks,
        "causality_pass": int(max_feature_ticks <= candidate_ticks),
        "price_raw": price_raw,
        "lb_direction": burst.direction,
        "lb_direction_agreement": direction * burst.direction,
        "lb_delta_1s_signed": direction * burst.delta_1s,
        "lb_delta_3s_signed": direction * burst.delta_3s,
        "lb_delta_change_z_signed": direction * burst.delta_change_zscore,
        "lb_delta_percentile": burst.delta_percentile,
        "lb_trades_per_second": burst.trades_per_second,
        "lb_contracts_per_second": burst.contracts_per_second,
        "lb_velocity_1s_signed": direction * burst.velocity_1s,
        "lb_acceleration_1s_signed": direction * burst.acceleration_1s,
        "base_trade_rate_100ms": _trade_rate(
            trades,
            trade_ticks,
            candidate_ticks,
            100,
        ),
        "base_trade_rate_500ms": _trade_rate(
            trades,
            trade_ticks,
            candidate_ticks,
            500,
        ),
        "base_price_velocity_100ms": signed_velocities[0],
        "base_price_velocity_500ms": signed_velocities[2],
        "rhy_trade_rate_acceleration": (
            _trade_rate(
                trades,
                trade_ticks,
                candidate_ticks,
                100,
            )
            - _trade_rate(
                trades,
                trade_ticks,
                candidate_ticks,
                1000,
            )
        ),
        "rhy_interarrival_compression": compression,
        "rhy_aggressor_run_length": aggressor_run,
        "rhy_multiscale_agreement": multiscale,
        "dva_normalized_position": (
            (price_raw - int(profile["val_raw"]))
            / max(int(profile["vah_raw"]) - int(profile["val_raw"]), 1)
        ),
        "dva_distance_poc_signed": direction
        * (price_raw - int(profile["poc_raw"])),
        "dva_distance_vah_signed": direction
        * (price_raw - int(profile["vah_raw"])),
        "dva_distance_val_signed": direction
        * (price_raw - int(profile["val_raw"])),
        "dva_poc_slope_30s_signed": poc_migration / 30.0,
        "dva_migration_speed_signed": poc_migration / 30.0,
        **acceptance,
        "vwap_zscore_signed": vwap_distance / max(profile_std, 1.0),
        "vwap_slope_30s_signed": vwap_slope,
        "vwap_reclaim_flag": vwap_reclaim,
        "vwap_hold_after_reclaim": vwap_hold,
        "of_delta_500ms_signed": direction * delta_500,
        "of_aggressor_imbalance_500ms_signed": (
            direction * delta_500 / max(total_500, 1)
        ),
        "of_impact_efficiency": signed_move_500
        / max(aligned_aggression, 1),
        "of_aggressive_volume_without_progress": aligned_aggression
        * max(0.0, 1.0 - max(signed_move_500, 0.0) / 4.0)
        / max(total_500, 1),
        **footprint,
        "dl_distance_nearest_favorable": _nearest_distance(
            favorable_levels,
            price_raw,
        ),
        "dl_distance_nearest_opposing": _nearest_distance(
            opposing_levels,
            price_raw,
        ),
        "dl_delta_extreme_no_progress": abs(delta_500)
        / max(total_500, 1)
        * max(0.0, 1.0 - directional_eff_500),
        "amt_balance_score": amt_balance,
        "amt_imbalance_score": amt_imbalance,
    }


def build_session_candidates(
    trades: np.ndarray,
    session_date: date,
    config: Mapping[str, object],
) -> tuple[list[LiquidityBurst], pd.DataFrame]:
    trade_ticks = contiguous_trade_ticks(trades)
    bursts = detect_liquidity_bursts(
        trades,
        session_date,
        config["detector"],
    )
    if not bursts:
        return bursts, pd.DataFrame()

    step = int(config["candidate_grid_ms"])
    maximum = int(config["candidate_max_ms"])
    offsets = range(0, maximum + 1, step)
    candidate_times = [
        burst.publish_ticks + offset * TICKS_PER_MILLISECOND
        for burst in bursts
        for offset in offsets
    ]
    profile_targets = candidate_times + [
        value - 30 * TICKS_PER_SECOND for value in candidate_times
    ]
    profiles = profile_snapshots(
        trades,
        profile_targets,
        trade_ticks=trade_ticks,
    )

    rows: list[dict[str, object]] = []
    for burst in bursts:
        for offset in offsets:
            candidate_ticks = (
                burst.publish_ticks + offset * TICKS_PER_MILLISECOND
            )
            if _last_index_at(trade_ticks, candidate_ticks) < 0:
                continue
            for direction in config["candidate_directions"]:
                features = compute_candidate_features(
                    trades,
                    burst,
                    candidate_ticks,
                    int(direction),
                    profiles,
                    trade_ticks=trade_ticks,
                )
                outcomes = compute_outcomes(
                    trades,
                    candidate_ticks,
                    int(direction),
                    config,
                    trade_ticks=trade_ticks,
                )
                rows.append({**features, **outcomes})
    return bursts, pd.DataFrame(rows)


FEATURE_GROUPS: dict[str, list[str]] = {
    "base": [
        "time_since_lb_ms",
        "lb_direction_agreement",
        "lb_delta_1s_signed",
        "lb_delta_3s_signed",
        "lb_delta_change_z_signed",
        "lb_delta_percentile",
        "lb_trades_per_second",
        "lb_contracts_per_second",
        "lb_velocity_1s_signed",
        "lb_acceleration_1s_signed",
        "base_trade_rate_100ms",
        "base_trade_rate_500ms",
        "base_price_velocity_100ms",
        "base_price_velocity_500ms",
    ],
    "rhythm": [
        "rhy_trade_rate_acceleration",
        "rhy_interarrival_compression",
        "rhy_aggressor_run_length",
        "rhy_multiscale_agreement",
    ],
    "dva": [
        "dva_normalized_position",
        "dva_distance_poc_signed",
        "dva_distance_vah_signed",
        "dva_distance_val_signed",
        "dva_poc_slope_30s_signed",
        "dva_migration_speed_signed",
    ],
    "acceptance": [
        "acc_hold_duration_ms",
        "acc_retention_ratio",
        "acc_volume_ratio",
        "acc_volume_time_agreement",
    ],
    "vwap": [
        "vwap_zscore_signed",
        "vwap_slope_30s_signed",
        "vwap_reclaim_flag",
        "vwap_hold_after_reclaim",
    ],
    "order_flow": [
        "of_delta_500ms_signed",
        "of_aggressor_imbalance_500ms_signed",
        "of_impact_efficiency",
        "of_aggressive_volume_without_progress",
    ],
    "footprint": [
        "fp_aligned_stacked_count",
        "fp_opposing_stacked_count",
        "fp_effort_result_ratio",
    ],
    "delta_levels": [
        "dl_distance_nearest_favorable",
        "dl_distance_nearest_opposing",
        "dl_delta_extreme_no_progress",
    ],
    "amt": [
        "amt_balance_score",
        "amt_imbalance_score",
    ],
}
