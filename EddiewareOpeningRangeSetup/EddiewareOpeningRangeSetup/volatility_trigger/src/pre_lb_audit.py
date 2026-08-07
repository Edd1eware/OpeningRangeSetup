from __future__ import annotations

import bisect
import heapq
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .vt_core import LiquidityBurst, TICKS_PER_MILLISECOND, TICKS_PER_SECOND


VALID = "VALID"
NO_PRIOR_DEPTH = "NO_PRIOR_DEPTH"
ONE_SIDED_BOOK = "ONE_SIDED_BOOK"
SPREAD_LE_0 = "SPREAD_LE_0"
SPREAD_GT_4 = "SPREAD_GT_4"
STALE_DEPTH_GT_250MS = "STALE_DEPTH_GT_250MS"

REFERENCE_STATUSES = (
    VALID,
    NO_PRIOR_DEPTH,
    ONE_SIDED_BOOK,
    SPREAD_LE_0,
    SPREAD_GT_4,
    STALE_DEPTH_GT_250MS,
)


def _weighted_percentile(
    histogram: Mapping[int, float],
    percentile: float,
) -> float:
    if not histogram:
        return math.nan
    total = float(sum(histogram.values()))
    if total <= 0:
        return math.nan
    target = min(max(float(percentile), 0.0), 1.0) * total
    cumulative = 0.0
    for value in sorted(histogram):
        cumulative += float(histogram[value])
        if cumulative >= target:
            return float(value)
    return float(max(histogram))


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


@dataclass(frozen=True)
class ProfileSnapshot:
    target_ticks: int
    last_trade_raw: int
    trade_count: int
    total_volume: float
    poc_raw: float
    val_raw: int
    vah_raw: int
    poc_tie_count: int
    poc_candidate_span_ticks: int
    va_tie_steps: int
    va_exhausted: bool
    n_levels_traded: int
    poc_volume_share: float
    entropy_norm: float


def profile_snapshot(
    volume_by_price: Mapping[int, float],
    *,
    target_ticks: int,
    last_trade_raw: int,
    trade_count: int,
    value_area_fraction: float,
) -> ProfileSnapshot | None:
    if not 0 < float(value_area_fraction) <= 1:
        raise ValueError("value_area_fraction must be in (0, 1]")
    positive = {
        int(price): float(volume)
        for price, volume in volume_by_price.items()
        if float(volume) > 0
    }
    if not positive or trade_count <= 0:
        return None

    prices = sorted(positive)
    volumes = np.asarray([positive[price] for price in prices], dtype=float)
    total = float(volumes.sum())
    maximum = float(volumes.max())
    candidate_indices = np.flatnonzero(volumes == maximum)
    candidate_prices = [prices[int(index)] for index in candidate_indices]
    candidate_distances = [
        abs(int(price) - int(last_trade_raw)) for price in candidate_prices
    ]
    minimum_distance = min(candidate_distances)
    nearest = [
        price
        for price, distance in zip(candidate_prices, candidate_distances)
        if distance == minimum_distance
    ]
    poc_raw = float(sum(nearest) / len(nearest))

    lo = int(candidate_indices.min())
    hi = int(candidate_indices.max())
    accumulated = float(volumes[lo : hi + 1].sum())
    target = total * float(value_area_fraction)
    tie_steps = 0

    while accumulated < target and (lo > 0 or hi < len(prices) - 1):
        left_index = lo - 1 if lo > 0 else None
        right_index = hi + 1 if hi < len(prices) - 1 else None
        if left_index is None:
            hi = int(right_index)
            accumulated += float(volumes[hi])
            continue
        if right_index is None:
            lo = int(left_index)
            accumulated += float(volumes[lo])
            continue

        left_volume = float(volumes[left_index])
        right_volume = float(volumes[right_index])
        if math.isclose(left_volume, right_volume, rel_tol=0.0, abs_tol=0.0):
            lo = int(left_index)
            hi = int(right_index)
            accumulated += left_volume + right_volume
            tie_steps += 1
        elif left_volume > right_volume:
            lo = int(left_index)
            accumulated += left_volume
        else:
            hi = int(right_index)
            accumulated += right_volume

    # Defensive branch: with a valid fraction <=1, exhausting every level
    # necessarily reaches the target. Persist the flag to expose any future
    # numerical or implementation violation of that invariant.
    exhausted = bool(accumulated < target)
    probabilities = volumes / total
    if len(probabilities) <= 1:
        entropy = 0.0
    else:
        entropy = float(
            -np.sum(probabilities * np.log(probabilities))
            / math.log(len(probabilities))
        )

    return ProfileSnapshot(
        target_ticks=int(target_ticks),
        last_trade_raw=int(last_trade_raw),
        trade_count=int(trade_count),
        total_volume=total,
        poc_raw=poc_raw,
        val_raw=int(prices[lo]),
        vah_raw=int(prices[hi]),
        poc_tie_count=len(candidate_prices),
        poc_candidate_span_ticks=int(
            max(candidate_prices) - min(candidate_prices)
        ),
        va_tie_steps=tie_steps,
        va_exhausted=exhausted,
        n_levels_traded=len(prices),
        poc_volume_share=maximum / total,
        entropy_norm=entropy,
    )


def causal_profile_snapshots(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    target_ticks: Sequence[int],
    *,
    rth_start_ticks: int,
    value_area_fraction: float,
) -> dict[int, ProfileSnapshot | None]:
    targets = sorted(set(int(value) for value in target_ticks))
    snapshots: dict[int, ProfileSnapshot | None] = {}
    if not targets:
        return snapshots

    pointer = int(np.searchsorted(trade_ticks, rth_start_ticks, side="left"))
    volume_by_price: dict[int, float] = defaultdict(float)
    trade_count = 0
    last_trade_raw: int | None = None

    for target in targets:
        if target < rth_start_ticks:
            snapshots[target] = None
            continue
        stop = int(np.searchsorted(trade_ticks, target, side="left"))
        while pointer < stop:
            row = trades[pointer]
            price = int(row["price_raw"])
            volume_by_price[price] += float(row["volume_raw"])
            trade_count += 1
            last_trade_raw = price
            pointer += 1
        snapshots[target] = (
            profile_snapshot(
                volume_by_price,
                target_ticks=target,
                last_trade_raw=int(last_trade_raw),
                trade_count=trade_count,
                value_area_fraction=value_area_fraction,
            )
            if last_trade_raw is not None
            else None
        )
    return snapshots


def profile_diagnostics(
    trades: np.ndarray,
    trade_ticks: np.ndarray,
    bursts: Sequence[LiquidityBurst],
    *,
    rth_start_ticks: int,
    drift_seconds: int,
    value_area_fraction: float,
) -> pd.DataFrame:
    drift_ticks = int(drift_seconds) * TICKS_PER_SECOND
    targets: list[int] = []
    for burst in bursts:
        cut = int(burst.source_second_ticks)
        targets.extend([cut, cut - drift_ticks])
    snapshots = causal_profile_snapshots(
        trades,
        trade_ticks,
        targets,
        rth_start_ticks=rth_start_ticks,
        value_area_fraction=value_area_fraction,
    )

    records: list[dict[str, object]] = []
    for burst in bursts:
        cut = int(burst.source_second_ticks)
        current = snapshots.get(cut)
        prior = snapshots.get(cut - drift_ticks)
        base = {
            "lb_id": burst.lb_id,
            "session_date": burst.session_date,
            "source_second_ticks": cut,
            "publish_ticks": int(burst.publish_ticks),
            "side": burst.side,
            "direction": int(burst.direction),
            "profile_elapsed_seconds": max(
                (cut - int(rth_start_ticks)) / TICKS_PER_SECOND,
                0.0,
            ),
            "profile_raw_available": current is not None,
            "PRF_PocDrift_ticks_300s_available": prior is not None,
        }
        if current is None:
            records.append(
                {
                    **base,
                    "profile_trade_count": math.nan,
                    "profile_total_volume": math.nan,
                    "profile_last_trade_raw": math.nan,
                    "profile_poc_raw": math.nan,
                    "profile_val_raw": math.nan,
                    "profile_vah_raw": math.nan,
                    "PRF_PocSignedDistance_ticks": math.nan,
                    "PRF_PocSide_Favor": math.nan,
                    "PRF_VaSignedPositionNorm": math.nan,
                    "PRF_InsideValueArea": math.nan,
                    "PRF_VaWidth_ticks": math.nan,
                    "PRF_PocDrift_ticks_300s": math.nan,
                    "PRF_PocVolumeShare": math.nan,
                    "PRF_ProfileEntropyNorm": math.nan,
                    "poc_tie_count": math.nan,
                    "poc_candidate_span_ticks": math.nan,
                    "va_tie_steps": math.nan,
                    "va_exhausted": math.nan,
                    "n_levels_traded": math.nan,
                }
            )
            continue

        signed_distance = int(burst.direction) * (
            float(current.poc_raw) - float(current.last_trade_raw)
        )
        va_width = int(current.vah_raw - current.val_raw)
        va_center = (float(current.vah_raw) + float(current.val_raw)) / 2.0
        signed_position = int(burst.direction) * (
            float(current.last_trade_raw) - va_center
        ) / max(va_width, 1)
        drift = (
            int(burst.direction)
            * (float(current.poc_raw) - float(prior.poc_raw))
            if prior is not None
            else math.nan
        )
        records.append(
            {
                **base,
                "profile_trade_count": int(current.trade_count),
                "profile_total_volume": float(current.total_volume),
                "profile_last_trade_raw": int(current.last_trade_raw),
                "profile_poc_raw": float(current.poc_raw),
                "profile_val_raw": int(current.val_raw),
                "profile_vah_raw": int(current.vah_raw),
                "PRF_PocSignedDistance_ticks": signed_distance,
                "PRF_PocSide_Favor": _sign(signed_distance),
                "PRF_VaSignedPositionNorm": signed_position,
                "PRF_InsideValueArea": int(
                    current.val_raw
                    <= current.last_trade_raw
                    <= current.vah_raw
                ),
                "PRF_VaWidth_ticks": va_width,
                "PRF_PocDrift_ticks_300s": drift,
                "PRF_PocVolumeShare": float(current.poc_volume_share),
                "PRF_ProfileEntropyNorm": float(current.entropy_norm),
                "poc_tie_count": int(current.poc_tie_count),
                "poc_candidate_span_ticks": int(
                    current.poc_candidate_span_ticks
                ),
                "va_tie_steps": int(current.va_tie_steps),
                "va_exhausted": bool(current.va_exhausted),
                "n_levels_traded": int(current.n_levels_traded),
            }
        )
    return pd.DataFrame.from_records(records)


class IncrementalL2Book:
    def __init__(self) -> None:
        self.bid_volume: dict[int, int] = {}
        self.ask_volume: dict[int, int] = {}
        self.bid_prices: list[int] = []
        self.ask_prices: list[int] = []
        self.bid_last_update: dict[int, int] = {}
        self.ask_last_update: dict[int, int] = {}
        self.bid_recent: set[int] = set()
        self.ask_recent: set[int] = set()
        self.bid_update_heap: list[tuple[int, int]] = []
        self.ask_update_heap: list[tuple[int, int]] = []

    @staticmethod
    def _remove_price(prices: list[int], price: int) -> None:
        index = bisect.bisect_left(prices, price)
        if index < len(prices) and prices[index] == price:
            prices.pop(index)

    def _update_one(
        self,
        *,
        side: int,
        price: int,
        volume: int,
        ticks: int,
    ) -> None:
        if side == 0:
            levels = self.bid_volume
            prices = self.bid_prices
            last_update = self.bid_last_update
            recent = self.bid_recent
            update_heap = self.bid_update_heap
        elif side == 1:
            levels = self.ask_volume
            prices = self.ask_prices
            last_update = self.ask_last_update
            recent = self.ask_recent
            update_heap = self.ask_update_heap
        else:
            raise ValueError(f"invalid depth side {side}")

        if volume > 0:
            if price not in levels:
                bisect.insort(prices, price)
            levels[price] = volume
            last_update[price] = ticks
            recent.add(price)
            heapq.heappush(update_heap, (ticks, price))
        else:
            levels.pop(price, None)
            last_update.pop(price, None)
            recent.discard(price)
            self._remove_price(prices, price)

    def update_group(
        self,
        rows: np.ndarray,
        *,
        ticks: int,
        maximum_recent_age_ticks: int,
    ) -> None:
        self.expire_recent(ticks, maximum_recent_age_ticks)
        for row in rows:
            self._update_one(
                side=int(row["side_code"]),
                price=int(row["price_raw"]),
                volume=int(row["volume_raw"]),
                ticks=int(ticks),
            )

    @staticmethod
    def _expire_side(
        current_ticks: int,
        maximum_age_ticks: int,
        heap: list[tuple[int, int]],
        last_update: Mapping[int, int],
        recent: set[int],
    ) -> None:
        cutoff = current_ticks - maximum_age_ticks
        while heap and heap[0][0] < cutoff:
            update_ticks, price = heapq.heappop(heap)
            if last_update.get(price) == update_ticks:
                recent.discard(price)

    def expire_recent(
        self,
        current_ticks: int,
        maximum_age_ticks: int,
    ) -> None:
        self._expire_side(
            current_ticks,
            maximum_age_ticks,
            self.bid_update_heap,
            self.bid_last_update,
            self.bid_recent,
        )
        self._expire_side(
            current_ticks,
            maximum_age_ticks,
            self.ask_update_heap,
            self.ask_last_update,
            self.ask_recent,
        )

    def reason(self, minimum_spread: int, maximum_spread: int) -> str:
        if not self.bid_prices or not self.ask_prices:
            return ONE_SIDED_BOOK
        spread = self.ask_prices[0] - self.bid_prices[-1]
        if spread < minimum_spread:
            return SPREAD_LE_0
        if spread > maximum_spread:
            return SPREAD_GT_4
        return VALID

    def spread(self) -> int | None:
        if not self.bid_prices or not self.ask_prices:
            return None
        return int(self.ask_prices[0] - self.bid_prices[-1])

    def counts(self) -> tuple[int, int]:
        return len(self.bid_prices), len(self.ask_prices)

    def recent_counts_at(
        self,
        ticks: int,
        maximum_age_ticks: int,
    ) -> tuple[int, int]:
        cutoff = int(ticks) - int(maximum_age_ticks)
        bid = sum(value >= cutoff for value in self.bid_last_update.values())
        ask = sum(value >= cutoff for value in self.ask_last_update.values())
        return int(bid), int(ask)

    def kth_distance(self, side: int, k: int) -> int | None:
        if side == 0:
            if len(self.bid_prices) < k:
                return None
            return int(self.bid_prices[-1] - self.bid_prices[-k])
        if len(self.ask_prices) < k:
            return None
        return int(self.ask_prices[k - 1] - self.ask_prices[0])

    def far_share(self, side: int, distance_ticks: int) -> float:
        if side == 0:
            if not self.bid_prices:
                return math.nan
            threshold = self.bid_prices[-1] - int(distance_ticks)
            far = bisect.bisect_left(self.bid_prices, threshold)
            return far / len(self.bid_prices)
        if not self.ask_prices:
            return math.nan
        threshold = self.ask_prices[0] + int(distance_ticks)
        first_far = bisect.bisect_right(self.ask_prices, threshold)
        return (len(self.ask_prices) - first_far) / len(self.ask_prices)


def classify_reference(
    *,
    has_prior_depth: bool,
    state_reason: str,
    at_ticks: int,
    last_group_ticks: int | None,
    maximum_age_ticks: int,
) -> tuple[str, float]:
    if not has_prior_depth or last_group_ticks is None:
        return NO_PRIOR_DEPTH, math.nan
    age_ticks = int(at_ticks) - int(last_group_ticks)
    age_ms = age_ticks / TICKS_PER_MILLISECOND
    if state_reason != VALID:
        return state_reason, float(age_ms)
    if age_ticks > int(maximum_age_ticks):
        return STALE_DEPTH_GT_250MS, float(age_ms)
    return VALID, float(age_ms)


def cluster_bursts(bursts: Sequence[LiquidityBurst]) -> pd.DataFrame:
    ordered = sorted(
        bursts,
        key=lambda item: (
            int(item.source_second_ticks),
            item.lb_id,
        ),
    )
    last_any: LiquidityBurst | None = None
    last_by_side: dict[str, LiquidityBurst] = {}
    records: list[dict[str, object]] = []
    for burst in ordered:
        opposite = "SELL" if burst.side == "BUY" else "BUY"
        prior_same = last_by_side.get(burst.side)
        prior_opposite = last_by_side.get(opposite)

        def elapsed(prior: LiquidityBurst | None) -> float:
            if prior is None:
                return math.nan
            return (
                int(burst.source_second_ticks)
                - int(prior.source_second_ticks)
            ) / TICKS_PER_MILLISECOND

        elapsed_any = elapsed(last_any)
        records.append(
            {
                "lb_id": burst.lb_id,
                "session_date": burst.session_date,
                "side": burst.side,
                "source_second_ticks": int(burst.source_second_ticks),
                "time_since_previous_any_ms": elapsed_any,
                "time_since_previous_same_side_ms": elapsed(prior_same),
                "time_since_previous_opposite_side_ms": elapsed(
                    prior_opposite
                ),
                "previous_lb_direction": (
                    int(last_any.direction) if last_any is not None else math.nan
                ),
                "previous_lb_side": (
                    last_any.side if last_any is not None else None
                ),
                "overlap_any_1s": bool(
                    math.isfinite(elapsed_any) and elapsed_any <= 1_000
                ),
                "overlap_any_5s": bool(
                    math.isfinite(elapsed_any) and elapsed_any <= 5_000
                ),
                "overlap_any_30s": bool(
                    math.isfinite(elapsed_any) and elapsed_any <= 30_000
                ),
            }
        )
        last_any = burst
        last_by_side[burst.side] = burst
    return pd.DataFrame.from_records(records)


def _empty_weighted_histograms(
    ks: Sequence[int],
) -> tuple[
    dict[str, dict[int, float]],
    dict[str, dict[int, dict[int, float]]],
]:
    count_hist = {"BID": defaultdict(float), "ASK": defaultdict(float)}
    distance_hist = {
        "BID": {int(k): defaultdict(float) for k in ks},
        "ASK": {int(k): defaultdict(float) for k in ks},
    }
    return count_hist, distance_hist


def audit_book_session(
    *,
    session_date: str,
    depth: np.ndarray,
    effective_ticks: np.ndarray,
    bursts: Sequence[LiquidityBurst],
    load_start_ticks: int,
    rth_start_ticks: int,
    rth_end_ticks: int,
    load_end_ticks: int,
    minimum_spread: int,
    maximum_spread: int,
    maximum_age_ms: float,
    pre_windows_seconds: Sequence[int],
    level_ks: Sequence[int],
    far_level_ticks: int,
    startup_minutes: int,
    eligible: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if len(depth) != len(effective_ticks):
        raise ValueError("depth/effective tick length mismatch")
    if len(effective_ticks) and np.any(np.diff(effective_ticks) < 0):
        raise ValueError("effective depth timestamps are not monotonic")
    if int(far_level_ticks) != 50:
        raise ValueError(
            "far_level_ticks must remain 50 because output lineage is frozen"
        )

    max_age_ticks = int(round(maximum_age_ms * TICKS_PER_MILLISECOND))
    windows = tuple(sorted(set(int(value) for value in pre_windows_seconds)))
    ks = tuple(sorted(set(int(value) for value in level_ks)))

    pre_query_times: set[int] = set()
    for burst in bursts:
        cut = int(burst.source_second_ticks)
        pre_query_times.add(cut)
        for seconds in windows:
            pre_query_times.add(cut - seconds * TICKS_PER_SECOND)
    pre_targets = sorted(pre_query_times)
    pre_pointer = 0
    pre_integrals: dict[int, tuple[int, int]] = {}

    reference_targets = sorted(
        (
            int(burst.publish_ticks),
            index,
        )
        for index, burst in enumerate(bursts)
    )
    reference_pointer = 0
    reference_records: list[dict[str, object] | None] = [None] * len(bursts)

    startup_targets = [
        int(load_start_ticks) + minute * 60 * TICKS_PER_SECOND
        for minute in range(int(startup_minutes) + 1)
    ]
    startup_pointer = 0
    startup_records: list[dict[str, object]] = []

    book = IncrementalL2Book()
    current_reason = NO_PRIOR_DEPTH
    last_group_ticks: int | None = None
    state_start = int(load_start_ticks)
    cumulative_valid = 0
    cumulative_fresh = 0

    rth_total_ticks = int(rth_end_ticks) - int(rth_start_ticks)
    session_valid_ticks = 0
    session_fresh_ticks = 0
    session_reason_ticks = defaultdict(int)
    spread_ticks = defaultdict(int)
    count_hist, distance_hist = _empty_weighted_histograms(ks)
    min_count_hist: dict[int, float] = defaultdict(float)
    k_ticks = {
        k: {"BID": 0, "ASK": 0, "BOTH": 0}
        for k in ks
    }
    far_share_weighted = {"BID": 0.0, "ASK": 0.0}
    recent_share_weighted = {"BID": 0.0, "ASK": 0.0}
    fresh_weight_total = 0.0

    def interval_integrals_at(target: int) -> tuple[int, int]:
        delta = max(int(target) - int(state_start), 0)
        valid = cumulative_valid
        fresh = cumulative_fresh
        if current_reason == VALID and last_group_ticks is not None:
            valid += delta
            fresh += min(
                delta,
                max(
                    int(last_group_ticks) + max_age_ticks - int(state_start),
                    0,
                ),
            )
        return int(valid), int(fresh)

    def resolve_pre_through(target: int) -> None:
        nonlocal pre_pointer
        while (
            pre_pointer < len(pre_targets)
            and int(pre_targets[pre_pointer]) <= int(target)
        ):
            query = int(pre_targets[pre_pointer])
            pre_integrals[query] = interval_integrals_at(query)
            pre_pointer += 1

    def reference_record(index: int, at_ticks: int) -> dict[str, object]:
        status, age_ms = classify_reference(
            has_prior_depth=last_group_ticks is not None,
            state_reason=current_reason,
            at_ticks=at_ticks,
            last_group_ticks=last_group_ticks,
            maximum_age_ticks=max_age_ticks,
        )
        burst = bursts[index]
        return {
            "lb_id": burst.lb_id,
            "session_date": burst.session_date,
            "side": burst.side,
            "direction": int(burst.direction),
            "source_second_ticks": int(burst.source_second_ticks),
            "publish_ticks": int(burst.publish_ticks),
            "reference_status": status,
            "reference_available": status == VALID,
            "depth_age_ms": age_ms,
            "state_reason_before_freshness": current_reason,
            "last_depth_group_ticks": (
                int(last_group_ticks)
                if last_group_ticks is not None
                else math.nan
            ),
            "spread_ticks_at_reference": (
                book.spread() if book.spread() is not None else math.nan
            ),
            "bid_level_count_at_reference": len(book.bid_prices),
            "ask_level_count_at_reference": len(book.ask_prices),
        }

    def resolve_references_before(target: int) -> None:
        nonlocal reference_pointer
        while (
            reference_pointer < len(reference_targets)
            and reference_targets[reference_pointer][0] < int(target)
        ):
            at_ticks, index = reference_targets[reference_pointer]
            reference_records[index] = reference_record(index, at_ticks)
            reference_pointer += 1

    def resolve_references_equal(target: int) -> None:
        nonlocal reference_pointer
        while (
            reference_pointer < len(reference_targets)
            and reference_targets[reference_pointer][0] == int(target)
        ):
            at_ticks, index = reference_targets[reference_pointer]
            reference_records[index] = reference_record(index, at_ticks)
            reference_pointer += 1

    def startup_record(at_ticks: int) -> dict[str, object]:
        recent_bid, recent_ask = book.recent_counts_at(
            at_ticks,
            max_age_ticks,
        )
        status, age_ms = classify_reference(
            has_prior_depth=last_group_ticks is not None,
            state_reason=current_reason,
            at_ticks=at_ticks,
            last_group_ticks=last_group_ticks,
            maximum_age_ticks=max_age_ticks,
        )
        return {
            "session_date": session_date,
            "eligible_after_trade_qc": bool(eligible),
            "minutes_since_depth_load_start": (
                int(at_ticks) - int(load_start_ticks)
            )
            / (60 * TICKS_PER_SECOND),
            "snapshot_ticks": int(at_ticks),
            "book_status": status,
            "depth_age_ms": age_ms,
            "bid_published_level_count": len(book.bid_prices),
            "ask_published_level_count": len(book.ask_prices),
            "bid_recently_updated_level_count_250ms": recent_bid,
            "ask_recently_updated_level_count_250ms": recent_ask,
        }

    def resolve_startup_before(target: int) -> None:
        nonlocal startup_pointer
        while (
            startup_pointer < len(startup_targets)
            and startup_targets[startup_pointer] < int(target)
        ):
            query = int(startup_targets[startup_pointer])
            startup_records.append(startup_record(query))
            startup_pointer += 1

    def resolve_startup_equal(target: int) -> None:
        nonlocal startup_pointer
        while (
            startup_pointer < len(startup_targets)
            and startup_targets[startup_pointer] == int(target)
        ):
            query = int(startup_targets[startup_pointer])
            startup_records.append(startup_record(query))
            startup_pointer += 1

    def accumulate_session_interval(start: int, end: int) -> None:
        nonlocal session_valid_ticks, session_fresh_ticks
        nonlocal fresh_weight_total
        segment_start = max(int(start), int(rth_start_ticks))
        segment_end = min(int(end), int(rth_end_ticks))
        if segment_end <= segment_start:
            return
        duration = segment_end - segment_start
        if current_reason != VALID or last_group_ticks is None:
            session_reason_ticks[current_reason] += duration
            return

        session_valid_ticks += duration
        fresh_end = min(
            segment_end,
            int(last_group_ticks) + max_age_ticks,
        )
        fresh_duration = max(fresh_end - segment_start, 0)
        stale_duration = duration - fresh_duration
        session_fresh_ticks += fresh_duration
        session_reason_ticks[STALE_DEPTH_GT_250MS] += stale_duration
        if fresh_duration <= 0:
            return

        spread = book.spread()
        if spread is not None:
            spread_ticks[int(spread)] += fresh_duration

        bid_count, ask_count = book.counts()
        count_hist["BID"][bid_count] += fresh_duration
        count_hist["ASK"][ask_count] += fresh_duration
        min_count_hist[min(bid_count, ask_count)] += fresh_duration
        for k in ks:
            bid_has = bid_count >= k
            ask_has = ask_count >= k
            if bid_has:
                k_ticks[k]["BID"] += fresh_duration
                distance = book.kth_distance(0, k)
                if distance is not None:
                    distance_hist["BID"][k][distance] += fresh_duration
            if ask_has:
                k_ticks[k]["ASK"] += fresh_duration
                distance = book.kth_distance(1, k)
                if distance is not None:
                    distance_hist["ASK"][k][distance] += fresh_duration
            if bid_has and ask_has:
                k_ticks[k]["BOTH"] += fresh_duration

        far_share_weighted["BID"] += (
            book.far_share(0, far_level_ticks) * fresh_duration
        )
        far_share_weighted["ASK"] += (
            book.far_share(1, far_level_ticks) * fresh_duration
        )
        # update_group/expire_recent already maintain these sets at
        # last_group_ticks. Reading their sizes is O(1); rescanning every live
        # level here would make the multi-million-group loop intractable.
        recent_bid = len(book.bid_recent)
        recent_ask = len(book.ask_recent)
        recent_share_weighted["BID"] += (
            recent_bid / max(bid_count, 1)
        ) * fresh_duration
        recent_share_weighted["ASK"] += (
            recent_ask / max(ask_count, 1)
        ) * fresh_duration
        fresh_weight_total += fresh_duration

    def advance_to(target: int) -> None:
        nonlocal cumulative_valid, cumulative_fresh, state_start
        target = int(target)
        if target < state_start:
            raise ValueError("book audit time moved backward")
        delta = target - state_start
        if current_reason == VALID and last_group_ticks is not None:
            cumulative_valid += delta
            cumulative_fresh += min(
                delta,
                max(
                    int(last_group_ticks) + max_age_ticks - state_start,
                    0,
                ),
            )
        accumulate_session_interval(state_start, target)
        state_start = target

    pointer = 0
    total = len(depth)
    while pointer < total:
        group_ticks = int(effective_ticks[pointer])
        stop = pointer + 1
        while stop < total and int(effective_ticks[stop]) == group_ticks:
            stop += 1

        resolve_pre_through(group_ticks)
        resolve_references_before(group_ticks)
        resolve_startup_before(group_ticks)
        advance_to(group_ticks)
        book.update_group(
            depth[pointer:stop],
            ticks=group_ticks,
            maximum_recent_age_ticks=max_age_ticks,
        )
        current_reason = book.reason(minimum_spread, maximum_spread)
        last_group_ticks = group_ticks
        resolve_references_equal(group_ticks)
        resolve_startup_equal(group_ticks)
        pointer = stop

    resolve_pre_through(load_end_ticks)
    resolve_references_before(load_end_ticks + 1)
    resolve_startup_before(load_end_ticks + 1)
    advance_to(load_end_ticks)

    if any(record is None for record in reference_records):
        raise RuntimeError("not all reference queries were resolved")
    unresolved_pre = sorted(set(pre_targets) - set(pre_integrals))
    if unresolved_pre:
        raise RuntimeError(
            f"not all pre-window queries were resolved: {unresolved_pre[:5]}"
        )

    missingness = pd.DataFrame.from_records(
        [record for record in reference_records if record is not None]
    )
    pre_records: list[dict[str, object]] = []
    for burst in bursts:
        cut = int(burst.source_second_ticks)
        cut_valid, cut_fresh = pre_integrals[cut]
        record: dict[str, object] = {
            "lb_id": burst.lb_id,
            "session_date": burst.session_date,
            "side": burst.side,
            "direction": int(burst.direction),
            "source_second_ticks": cut,
            "publish_ticks": int(burst.publish_ticks),
        }
        for seconds in windows:
            start = cut - seconds * TICKS_PER_SECOND
            start_valid, start_fresh = pre_integrals[start]
            required = seconds * TICKS_PER_SECOND
            valid_duration = cut_valid - start_valid
            fresh_duration = cut_fresh - start_fresh
            record[f"book_valid_fraction_pre_{seconds}s"] = (
                valid_duration / required
            )
            record[f"book_fresh_valid_fraction_pre_{seconds}s"] = (
                fresh_duration / required
            )
            record[f"book_fresh_valid_full_pre_{seconds}s"] = bool(
                fresh_duration == required
            )
        pre_records.append(record)
    pre_window = pd.DataFrame.from_records(pre_records)

    seconds_denominator = TICKS_PER_SECOND
    group_mask = (
        (effective_ticks >= int(rth_start_ticks))
        & (effective_ticks < int(rth_end_ticks))
    )
    rth_group_ticks = effective_ticks[group_mask]
    if len(rth_group_ticks):
        unique_group_ticks = rth_group_ticks[
            np.r_[
                True,
                rth_group_ticks[1:] != rth_group_ticks[:-1],
            ]
        ]
    else:
        unique_group_ticks = np.asarray([], dtype=np.int64)
    gap_boundaries = np.concatenate(
        [
            np.asarray([rth_start_ticks], dtype=np.int64),
            unique_group_ticks,
            np.asarray([rth_end_ticks], dtype=np.int64),
        ]
    )
    gap_ms = np.diff(gap_boundaries) / TICKS_PER_MILLISECOND

    session_record: dict[str, object] = {
        "session_date": session_date,
        "eligible_after_trade_qc": bool(eligible),
        "rth_seconds": rth_total_ticks / seconds_denominator,
        "depth_rows_rth": int(group_mask.sum()),
        "depth_groups_rth": int(len(unique_group_ticks)),
        "depth_row_rate_per_second": float(
            group_mask.sum() / max(rth_total_ticks / seconds_denominator, 1)
        ),
        "depth_group_rate_per_second": float(
            len(unique_group_ticks)
            / max(rth_total_ticks / seconds_denominator, 1)
        ),
        "book_valid_fraction": session_valid_ticks / max(rth_total_ticks, 1),
        "fresh_valid_fraction": session_fresh_ticks
        / max(rth_total_ticks, 1),
        "book_valid_seconds": session_valid_ticks / seconds_denominator,
        "fresh_valid_seconds": session_fresh_ticks / seconds_denominator,
        "stale_valid_seconds": session_reason_ticks[
            STALE_DEPTH_GT_250MS
        ]
        / seconds_denominator,
        "no_prior_depth_seconds": session_reason_ticks[NO_PRIOR_DEPTH]
        / seconds_denominator,
        "one_sided_book_seconds": session_reason_ticks[ONE_SIDED_BOOK]
        / seconds_denominator,
        "spread_le_0_seconds": session_reason_ticks[SPREAD_LE_0]
        / seconds_denominator,
        "spread_gt_4_seconds": session_reason_ticks[SPREAD_GT_4]
        / seconds_denominator,
        "gap_median_ms": float(np.median(gap_ms)) if len(gap_ms) else math.nan,
        "gap_p95_ms": float(np.quantile(gap_ms, 0.95))
        if len(gap_ms)
        else math.nan,
        "gap_p99_ms": float(np.quantile(gap_ms, 0.99))
        if len(gap_ms)
        else math.nan,
        "gap_max_ms": float(gap_ms.max()) if len(gap_ms) else math.nan,
        "gap_gt_250ms_count": int(np.sum(gap_ms > maximum_age_ms)),
    }
    for spread in range(minimum_spread, maximum_spread + 1):
        session_record[f"fresh_spread_{spread}_share"] = (
            spread_ticks[spread] / max(session_fresh_ticks, 1)
        )

    depth_records: list[dict[str, object]] = []
    for k in ks:
        depth_records.append(
            {
                "session_date": session_date,
                "eligible_after_trade_qc": bool(eligible),
                "k": k,
                "fresh_valid_seconds": session_fresh_ticks
                / seconds_denominator,
                "bid_ge_k_seconds": k_ticks[k]["BID"] / seconds_denominator,
                "ask_ge_k_seconds": k_ticks[k]["ASK"] / seconds_denominator,
                "both_ge_k_seconds": k_ticks[k]["BOTH"] / seconds_denominator,
                "bid_ge_k_fraction": k_ticks[k]["BID"]
                / max(session_fresh_ticks, 1),
                "ask_ge_k_fraction": k_ticks[k]["ASK"]
                / max(session_fresh_ticks, 1),
                "both_ge_k_fraction": k_ticks[k]["BOTH"]
                / max(session_fresh_ticks, 1),
                "bid_k_distance_p50_ticks": _weighted_percentile(
                    distance_hist["BID"][k], 0.50
                ),
                "bid_k_distance_p95_ticks": _weighted_percentile(
                    distance_hist["BID"][k], 0.95
                ),
                "bid_k_distance_max_ticks": (
                    float(max(distance_hist["BID"][k]))
                    if distance_hist["BID"][k]
                    else math.nan
                ),
                "ask_k_distance_p50_ticks": _weighted_percentile(
                    distance_hist["ASK"][k], 0.50
                ),
                "ask_k_distance_p95_ticks": _weighted_percentile(
                    distance_hist["ASK"][k], 0.95
                ),
                "ask_k_distance_max_ticks": (
                    float(max(distance_hist["ASK"][k]))
                    if distance_hist["ASK"][k]
                    else math.nan
                ),
                "bid_published_level_count_p05": _weighted_percentile(
                    count_hist["BID"], 0.05
                ),
                "bid_published_level_count_p50": _weighted_percentile(
                    count_hist["BID"], 0.50
                ),
                "bid_published_level_count_p95": _weighted_percentile(
                    count_hist["BID"], 0.95
                ),
                "ask_published_level_count_p05": _weighted_percentile(
                    count_hist["ASK"], 0.05
                ),
                "ask_published_level_count_p50": _weighted_percentile(
                    count_hist["ASK"], 0.50
                ),
                "ask_published_level_count_p95": _weighted_percentile(
                    count_hist["ASK"], 0.95
                ),
                "min_side_level_count_p05": _weighted_percentile(
                    min_count_hist, 0.05
                ),
                "min_side_level_count_p50": _weighted_percentile(
                    min_count_hist, 0.50
                ),
                "min_side_level_count_p95": _weighted_percentile(
                    min_count_hist, 0.95
                ),
                "bid_far_level_share_gt50_mean": (
                    far_share_weighted["BID"] / max(fresh_weight_total, 1)
                ),
                "ask_far_level_share_gt50_mean": (
                    far_share_weighted["ASK"] / max(fresh_weight_total, 1)
                ),
                "bid_recently_updated_share_250ms_mean": (
                    recent_share_weighted["BID"]
                    / max(fresh_weight_total, 1)
                ),
                "ask_recently_updated_share_250ms_mean": (
                    recent_share_weighted["ASK"]
                    / max(fresh_weight_total, 1)
                ),
            }
        )
    depth_frame = pd.DataFrame.from_records(depth_records)
    startup_frame = pd.DataFrame.from_records(startup_records)

    return (
        missingness,
        pre_window,
        depth_frame,
        startup_frame,
        session_record,
    )


def level_viability(
    depth_characterization: pd.DataFrame,
    *,
    aggregate_minimum: float,
    each_session_minimum: float,
    expected_eligible_sessions: int,
) -> tuple[pd.DataFrame, bool]:
    eligible = depth_characterization[
        depth_characterization["eligible_after_trade_qc"].astype(bool)
    ].copy()
    records: list[dict[str, object]] = []
    prior_pass = True
    nested = True
    for k in sorted(eligible["k"].unique()):
        part = eligible[eligible["k"].eq(k)].copy()
        if len(part) != int(expected_eligible_sessions):
            raise ValueError(
                f"k={k} has {len(part)} eligible sessions; "
                f"expected {expected_eligible_sessions}"
            )
        aggregate_fraction = float(
            part["both_ge_k_seconds"].sum()
            / max(part["fresh_valid_seconds"].sum(), 1e-12)
        )
        binding = part.sort_values(
            ["both_ge_k_fraction", "session_date"]
        ).iloc[0]
        minimum_fraction = float(binding["both_ge_k_fraction"])
        passed = bool(
            aggregate_fraction >= float(aggregate_minimum)
            and minimum_fraction >= float(each_session_minimum)
        )
        if passed and not prior_pass:
            nested = False
        prior_pass = prior_pass and passed
        records.append(
            {
                "k": int(k),
                "aggregate_both_ge_k_fraction": aggregate_fraction,
                "minimum_session_both_ge_k_fraction": minimum_fraction,
                "binding_session": str(binding["session_date"]),
                "binding_margin_vs_minimum": minimum_fraction
                - float(each_session_minimum),
                "aggregate_pass": aggregate_fraction
                >= float(aggregate_minimum),
                "each_session_pass": minimum_fraction
                >= float(each_session_minimum),
                "viable": passed,
            }
        )
    return pd.DataFrame.from_records(records), nested


def forbidden_output_columns(frames: Iterable[pd.DataFrame]) -> list[str]:
    forbidden_fragments = (
        "regime",
        "time_to_continue",
        "time_to_reverse",
        "time_difference_continue_minus_reverse",
        "continue_reached",
        "reverse_reached",
        "first_expansion_direction",
        "future_trade_count",
        "max_move_continue",
        "max_move_reverse",
        "expansion_dominance",
        "net_move_signed",
        "out_postlbpoc",
    )
    observed: set[str] = set()
    for frame in frames:
        for column in frame.columns:
            lowered = str(column).lower()
            if any(fragment in lowered for fragment in forbidden_fragments):
                observed.add(str(column))
    return sorted(observed)


def burst_records(bursts: Sequence[LiquidityBurst]) -> pd.DataFrame:
    return pd.DataFrame.from_records([asdict(burst) for burst in bursts])
