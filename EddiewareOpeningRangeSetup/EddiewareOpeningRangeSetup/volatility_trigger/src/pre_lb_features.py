from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .pre_lb_audit import VALID, profile_diagnostics
from .vt_core import (
    LiquidityBurst,
    TICKS_PER_MILLISECOND,
    TICKS_PER_SECOND,
    contiguous_trade_ticks,
)


WINDOWS_SECONDS = (1, 5, 30)
LEVEL_KS = (1, 3, 5, 10)


def catalog_features(config: Mapping[str, object]) -> list[str]:
    catalog = config["feature_catalog"]
    return [
        str(feature)
        for family in catalog.values()
        for feature in family
    ]


def validate_catalog(config: Mapping[str, object]) -> list[str]:
    features = catalog_features(config)
    declared = int(config["feature_count"])
    if len(features) != declared:
        raise ValueError(
            f"feature count mismatch: observed={len(features)} "
            f"declared={declared}"
        )
    if len(set(features)) != len(features):
        duplicates = sorted(
            {
                feature
                for feature in features
                if features.count(feature) > 1
            }
        )
        raise ValueError(f"duplicate catalog features: {duplicates}")
    return features


def _window_slice(
    rows: np.ndarray,
    ticks: np.ndarray,
    start_ticks: int,
    end_ticks: int,
) -> np.ndarray:
    start = int(np.searchsorted(ticks, int(start_ticks), side="left"))
    stop = int(np.searchsorted(ticks, int(end_ticks), side="left"))
    return rows[start:stop]


def _window_trade_features(
    rows: np.ndarray,
    *,
    direction: int,
    window_seconds: int,
    midpoint_ticks: int,
) -> dict[str, float]:
    suffix = f"pre_{int(window_seconds)}s"
    if len(rows):
        prices = rows["price_raw"].astype(np.float64)
        volumes = rows["volume_raw"].astype(np.float64)
        sides = rows["side_code"]
        net_favor = int(direction) * float(prices[-1] - prices[0])
        price_range = float(prices.max() - prices.min())
        path = float(np.abs(np.diff(prices)).sum())
        efficiency = net_favor / path if path > 0 else 0.0
        buy_volume = float(volumes[sides == 1].sum())
        sell_volume = float(volumes[sides == 2].sum())
        total_volume = buy_volume + sell_volume
        imbalance = (
            int(direction) * (buy_volume - sell_volume) / total_volume
            if total_volume > 0
            else 0.0
        )
        aligned_side = 1 if int(direction) > 0 else 2
        aligned = rows[sides == aligned_side]
        first = aligned[aligned["ticks"] < int(midpoint_ticks)]
        second = aligned[aligned["ticks"] >= int(midpoint_ticks)]
        first_mean = (
            float(first["volume_raw"].astype(np.float64).mean())
            if len(first)
            else 0.0
        )
        second_mean = (
            float(second["volume_raw"].astype(np.float64).mean())
            if len(second)
            else 0.0
        )
        retention = math.log(
            (second_mean + 1.0) / (first_mean + 1.0)
        )
        trade_rate = len(rows) / float(window_seconds)
        contract_rate = total_volume / float(window_seconds)
    else:
        net_favor = 0.0
        price_range = 0.0
        efficiency = 0.0
        imbalance = 0.0
        retention = 0.0
        trade_rate = 0.0
        contract_rate = 0.0

    return {
        f"PX_NetMoveFavor_ticks_{suffix}": net_favor,
        f"PX_Range_ticks_{suffix}": price_range,
        f"PX_PathEfficiencyFavor_{suffix}": efficiency,
        f"TAPE_TradeRate_{suffix}": trade_rate,
        f"TAPE_ContractRate_{suffix}": contract_rate,
        f"TAPE_DeltaImbalanceFavor_{suffix}": imbalance,
        f"TAPE_AggressorSizeLogRetention_{suffix}": retention,
    }


def trade_precursor_features(
    trades: np.ndarray,
    bursts: Sequence[LiquidityBurst],
    *,
    rth_start_ticks: int,
) -> pd.DataFrame:
    trade_ticks = contiguous_trade_ticks(trades)
    ordered = sorted(
        bursts,
        key=lambda item: (
            item.session_date,
            int(item.source_second_ticks),
            item.lb_id,
        ),
    )
    records: list[dict[str, object]] = []
    previous_cut: int | None = None
    previous_session: str | None = None
    session_ordinal = 0

    for burst in ordered:
        cut = int(burst.source_second_ticks)
        direction = int(burst.direction)
        if burst.session_date != previous_session:
            previous_cut = None
            session_ordinal = 0
        record: dict[str, object] = {
            "lb_id": burst.lb_id,
            "session_date": burst.session_date,
            "source_second_ticks": cut,
            "publish_ticks": int(burst.publish_ticks),
            "side": burst.side,
            "direction": direction,
            "BLB_Delta1s_Favor": direction * int(burst.delta_1s),
            "BLB_Delta3s_Favor": direction * int(burst.delta_3s),
            "BLB_DeltaChangeZ_Favor": (
                direction * float(burst.delta_change_zscore)
            ),
            "BLB_DeltaPercentile": float(burst.delta_percentile),
            "BLB_TradesPerSecond": int(burst.trades_per_second),
            "BLB_ContractsPerSecond": int(
                burst.contracts_per_second
            ),
            "BLB_Velocity1s_Favor": (
                direction * float(burst.velocity_1s)
            ),
            "BLB_Acceleration1s_Favor": (
                direction * float(burst.acceleration_1s)
            ),
            "CTL_RthElapsed_seconds": (
                cut - int(rth_start_ticks)
            )
            / TICKS_PER_SECOND,
            "CTL_LbOrdinalPriorCount": session_ordinal,
            "CTL_PriorLbWithin30s": int(
                previous_cut is not None
                and cut - int(previous_cut)
                <= 30 * TICKS_PER_SECOND
            ),
            "BASELINE_SUPPORT": True,
        }
        max_precursor_tick: int | None = None
        for seconds in WINDOWS_SECONDS:
            start_ticks = cut - seconds * TICKS_PER_SECOND
            rows = _window_slice(
                trades,
                trade_ticks,
                start_ticks,
                cut,
            )
            record.update(
                _window_trade_features(
                    rows,
                    direction=direction,
                    window_seconds=seconds,
                    midpoint_ticks=(
                        start_ticks
                        + seconds * TICKS_PER_SECOND // 2
                    ),
                )
            )
            if len(rows):
                observed = int(rows["ticks"][-1])
                max_precursor_tick = (
                    observed
                    if max_precursor_tick is None
                    else max(max_precursor_tick, observed)
                )
        record["MAX_PRECURSOR_TRADE_TICKS"] = (
            max_precursor_tick
            if max_precursor_tick is not None
            else math.nan
        )
        if (
            max_precursor_tick is not None
            and max_precursor_tick >= cut
        ):
            raise RuntimeError("trade precursor reached causal cut")
        records.append(record)
        previous_cut = cut
        previous_session = burst.session_date
        session_ordinal += 1
    return pd.DataFrame.from_records(records)


@dataclass(frozen=True)
class DomMoment:
    support: bool
    last_group_ticks: int | None
    spread_ticks: float
    midpoint_raw: float
    microprice_raw: float
    bid_depth: dict[int, float]
    ask_depth: dict[int, float]

    @property
    def imbalance_l10_raw(self) -> float:
        bid = float(self.bid_depth.get(10, math.nan))
        ask = float(self.ask_depth.get(10, math.nan))
        if not math.isfinite(bid) or not math.isfinite(ask):
            return math.nan
        return (bid - ask) / max(bid + ask, 1.0)

    @property
    def top10_total_depth(self) -> float:
        bid = float(self.bid_depth.get(10, math.nan))
        ask = float(self.ask_depth.get(10, math.nan))
        if not math.isfinite(bid) or not math.isfinite(ask):
            return math.nan
        return bid + ask


@dataclass(frozen=True)
class DomCumulative:
    valid_ticks: int
    fresh_ticks: int
    imbalance_l10_integral: float
    top10_depth_integral: float
    stack_raw: float
    churn_abs: float


@dataclass(frozen=True)
class DomQuery:
    cumulative: DomCumulative
    before: DomMoment
    after: DomMoment


class FeatureTop10Book:
    def __init__(self) -> None:
        self.bid_volume: dict[int, int] = {}
        self.ask_volume: dict[int, int] = {}
        self.bid_prices: list[int] = []
        self.ask_prices: list[int] = []

    @staticmethod
    def _remove(prices: list[int], price: int) -> None:
        index = bisect.bisect_left(prices, int(price))
        if index < len(prices) and prices[index] == int(price):
            prices.pop(index)

    def _side(
        self,
        side: int,
    ) -> tuple[dict[int, int], list[int]]:
        if int(side) == 0:
            return self.bid_volume, self.bid_prices
        if int(side) == 1:
            return self.ask_volume, self.ask_prices
        raise ValueError(f"invalid depth side {side}")

    def _top_prices(self, side: int, k: int = 10) -> list[int]:
        if int(side) == 0:
            return list(reversed(self.bid_prices[-int(k) :]))
        return self.ask_prices[: int(k)]

    def update_group(
        self,
        rows: np.ndarray,
    ) -> tuple[float, float]:
        before = {
            0: set(self._top_prices(0, 10)),
            1: set(self._top_prices(1, 10)),
        }
        changes: list[tuple[int, int, int]] = []
        for row in rows:
            side = int(row["side_code"])
            price = int(row["price_raw"])
            volume = int(row["volume_raw"])
            levels, prices = self._side(side)
            old = int(levels.get(price, 0))
            delta = volume - old
            changes.append((side, price, delta))
            if volume > 0:
                if price not in levels:
                    bisect.insort(prices, price)
                levels[price] = volume
            else:
                levels.pop(price, None)
                self._remove(prices, price)

        after = {
            0: set(self._top_prices(0, 10)),
            1: set(self._top_prices(1, 10)),
        }
        union = {
            side: before[side] | after[side]
            for side in (0, 1)
        }
        bid_delta = 0.0
        ask_delta = 0.0
        churn = 0.0
        for side, price, delta in changes:
            if price not in union[side]:
                continue
            if side == 0:
                bid_delta += float(delta)
            else:
                ask_delta += float(delta)
            churn += abs(float(delta))
        return bid_delta - ask_delta, churn

    def reason(
        self,
        minimum_spread: int,
        maximum_spread: int,
    ) -> str:
        if not self.bid_prices or not self.ask_prices:
            return "ONE_SIDED_BOOK"
        spread = self.ask_prices[0] - self.bid_prices[-1]
        if spread < int(minimum_spread):
            return "SPREAD_LE_0"
        if spread > int(maximum_spread):
            return "SPREAD_GT_4"
        return VALID

    def moment(
        self,
        *,
        query_ticks: int,
        last_group_ticks: int | None,
        maximum_age_ticks: int,
        minimum_spread: int,
        maximum_spread: int,
    ) -> DomMoment:
        reason = self.reason(minimum_spread, maximum_spread)
        fresh = bool(
            last_group_ticks is not None
            and int(query_ticks) - int(last_group_ticks)
            <= int(maximum_age_ticks)
        )
        level_support = (
            len(self.bid_prices) >= 10
            and len(self.ask_prices) >= 10
        )
        support = reason == VALID and fresh and level_support
        spread = (
            float(self.ask_prices[0] - self.bid_prices[-1])
            if self.bid_prices and self.ask_prices
            else math.nan
        )
        if not support:
            return DomMoment(
                support=False,
                last_group_ticks=last_group_ticks,
                spread_ticks=spread,
                midpoint_raw=math.nan,
                microprice_raw=math.nan,
                bid_depth={},
                ask_depth={},
            )

        bid_prices = self._top_prices(0, 10)
        ask_prices = self._top_prices(1, 10)
        bid_depth: dict[int, float] = {}
        ask_depth: dict[int, float] = {}
        for k in LEVEL_KS:
            bid_depth[k] = float(
                sum(self.bid_volume[price] for price in bid_prices[:k])
            )
            ask_depth[k] = float(
                sum(self.ask_volume[price] for price in ask_prices[:k])
            )
        best_bid = int(bid_prices[0])
        best_ask = int(ask_prices[0])
        bid_size = float(self.bid_volume[best_bid])
        ask_size = float(self.ask_volume[best_ask])
        microprice = (
            best_ask * bid_size + best_bid * ask_size
        ) / max(bid_size + ask_size, 1.0)
        return DomMoment(
            support=True,
            last_group_ticks=last_group_ticks,
            spread_ticks=spread,
            midpoint_raw=(best_bid + best_ask) / 2.0,
            microprice_raw=float(microprice),
            bid_depth=bid_depth,
            ask_depth=ask_depth,
        )


def _nan_dom_state() -> dict[str, float]:
    return {
        "DOM_Spread_ticks": math.nan,
        "DOM_MicropriceOffsetFavor_ticks": math.nan,
        "DOM_ImbalanceL1_Favor": math.nan,
        "DOM_ImbalanceL3_Favor": math.nan,
        "DOM_ImbalanceL5_Favor": math.nan,
        "DOM_ImbalanceL10_Favor": math.nan,
        "DOM_AheadDepthPerLbContractsL3": math.nan,
        "DOM_AheadL1ConcentrationL5": math.nan,
    }


def _dom_state_features(
    moment: DomMoment,
    *,
    direction: int,
    lb_contracts: int,
) -> dict[str, float]:
    if not moment.support:
        return _nan_dom_state()
    result: dict[str, float] = {
        "DOM_Spread_ticks": float(moment.spread_ticks),
        "DOM_MicropriceOffsetFavor_ticks": (
            int(direction)
            * (moment.microprice_raw - moment.midpoint_raw)
        ),
    }
    for k in LEVEL_KS:
        bid = float(moment.bid_depth[k])
        ask = float(moment.ask_depth[k])
        result[f"DOM_ImbalanceL{k}_Favor"] = (
            int(direction) * (bid - ask) / max(bid + ask, 1.0)
        )
    ahead = moment.ask_depth if int(direction) > 0 else moment.bid_depth
    result["DOM_AheadDepthPerLbContractsL3"] = float(
        ahead[3] / max(int(lb_contracts), 1)
    )
    result["DOM_AheadL1ConcentrationL5"] = float(
        ahead[1] / max(ahead[5], 1.0)
    )
    return result


def _nan_dom_window(seconds: int) -> dict[str, float]:
    suffix = f"pre_{int(seconds)}s"
    return {
        f"DOM_ImbalanceL10MeanFavor_{suffix}": math.nan,
        f"DOM_MicropriceDriftFavor_ticks_{suffix}": math.nan,
        (
            "DOM_ProxyDirectionalStackPullBalanceL10_"
            f"{suffix}"
        ): math.nan,
        (
            "DOM_NearChurnTurnoversPerSecondL10_"
            f"{suffix}"
        ): math.nan,
    }


def dom_precursor_features(
    depth: np.ndarray,
    effective_ticks: np.ndarray,
    bursts: Sequence[LiquidityBurst],
    *,
    load_start_ticks: int,
    maximum_age_ms: float,
    minimum_spread: int,
    maximum_spread: int,
) -> pd.DataFrame:
    if len(depth) != len(effective_ticks):
        raise ValueError("depth/effective tick length mismatch")
    if len(effective_ticks) and np.any(np.diff(effective_ticks) < 0):
        raise ValueError("effective depth timestamps are not monotonic")
    if not bursts:
        return pd.DataFrame()

    query_roles: dict[int, set[str]] = {}
    for burst in bursts:
        cut = int(burst.source_second_ticks)
        query_roles.setdefault(cut, set()).add("cut")
        for seconds in WINDOWS_SECONDS:
            query_roles.setdefault(
                cut - seconds * TICKS_PER_SECOND,
                set(),
            ).add("start")
    query_times = sorted(query_roles)
    query_pointer = 0
    queries: dict[int, DomQuery] = {}

    book = FeatureTop10Book()
    max_age_ticks = int(
        round(float(maximum_age_ms) * TICKS_PER_MILLISECOND)
    )
    last_group_ticks: int | None = None
    state_start = int(load_start_ticks)
    valid_ticks = 0
    fresh_ticks = 0
    imbalance_integral = 0.0
    depth_integral = 0.0
    stack_raw = 0.0
    churn_abs = 0.0

    def current_moment(at_ticks: int) -> DomMoment:
        return book.moment(
            query_ticks=at_ticks,
            last_group_ticks=last_group_ticks,
            maximum_age_ticks=max_age_ticks,
            minimum_spread=minimum_spread,
            maximum_spread=maximum_spread,
        )

    def advance(at_ticks: int) -> None:
        nonlocal state_start, valid_ticks, fresh_ticks
        nonlocal imbalance_integral, depth_integral
        at_ticks = int(at_ticks)
        if at_ticks < state_start:
            raise ValueError("DOM feature time moved backward")
        if at_ticks == state_start:
            return
        duration = at_ticks - state_start
        reason = book.reason(minimum_spread, maximum_spread)
        if reason == VALID and last_group_ticks is not None:
            valid_ticks += duration
            moment = current_moment(state_start)
            if moment.support:
                fresh_end = min(
                    at_ticks,
                    int(last_group_ticks) + max_age_ticks,
                )
                fresh_duration = max(fresh_end - state_start, 0)
                fresh_ticks += fresh_duration
                imbalance_integral += (
                    moment.imbalance_l10_raw * fresh_duration
                )
                depth_integral += (
                    moment.top10_total_depth * fresh_duration
                )
        state_start = at_ticks

    def cumulative() -> DomCumulative:
        return DomCumulative(
            valid_ticks=int(valid_ticks),
            fresh_ticks=int(fresh_ticks),
            imbalance_l10_integral=float(imbalance_integral),
            top10_depth_integral=float(depth_integral),
            stack_raw=float(stack_raw),
            churn_abs=float(churn_abs),
        )

    def capture_without_group(at_ticks: int) -> None:
        before = current_moment(at_ticks)
        queries[int(at_ticks)] = DomQuery(
            cumulative=cumulative(),
            before=before,
            after=before,
        )

    group_pointer = 0
    total = len(depth)
    while group_pointer < total or query_pointer < len(query_times):
        next_group = (
            int(effective_ticks[group_pointer])
            if group_pointer < total
            else None
        )
        next_query = (
            int(query_times[query_pointer])
            if query_pointer < len(query_times)
            else None
        )
        if next_group is None:
            event_ticks = int(next_query)
        elif next_query is None:
            event_ticks = int(next_group)
        else:
            event_ticks = min(int(next_group), int(next_query))

        advance(event_ticks)
        has_query = next_query == event_ticks
        has_group = next_group == event_ticks

        if has_query and not has_group:
            capture_without_group(event_ticks)
            query_pointer += 1
            continue

        if has_group:
            stop = group_pointer + 1
            while (
                stop < total
                and int(effective_ticks[stop]) == event_ticks
            ):
                stop += 1
            before = current_moment(event_ticks)
            before_cumulative = cumulative()
            delta_stack, delta_churn = book.update_group(
                depth[group_pointer:stop]
            )
            stack_raw += float(delta_stack)
            churn_abs += float(delta_churn)
            last_group_ticks = event_ticks
            after = current_moment(event_ticks)
            if has_query:
                queries[event_ticks] = DomQuery(
                    cumulative=before_cumulative,
                    before=before,
                    after=after,
                )
                query_pointer += 1
            group_pointer = stop

        if (
            query_pointer >= len(query_times)
            and group_pointer < total
            and int(effective_ticks[group_pointer])
            > max(query_times)
        ):
            break

    missing_queries = sorted(set(query_times) - set(queries))
    if missing_queries:
        raise RuntimeError(
            f"unresolved DOM feature queries: {missing_queries[:5]}"
        )

    records: list[dict[str, object]] = []
    for burst in bursts:
        cut = int(burst.source_second_ticks)
        direction = int(burst.direction)
        end_query = queries[cut]
        state = _dom_state_features(
            end_query.before,
            direction=direction,
            lb_contracts=int(burst.contracts_per_second),
        )
        record: dict[str, object] = {
            "lb_id": burst.lb_id,
            "DOM_STATE_SUPPORT": bool(end_query.before.support),
            **state,
        }
        last_depth = end_query.before.last_group_ticks
        record["MAX_PRECURSOR_DEPTH_TICKS"] = (
            int(last_depth)
            if last_depth is not None
            else math.nan
        )
        if last_depth is not None and int(last_depth) >= cut:
            raise RuntimeError("DOM state reached causal cut")

        for seconds in WINDOWS_SECONDS:
            start = cut - seconds * TICKS_PER_SECOND
            start_query = queries[start]
            required = seconds * TICKS_PER_SECOND
            fresh = (
                end_query.cumulative.fresh_ticks
                - start_query.cumulative.fresh_ticks
            )
            support = bool(
                fresh == required
                and start_query.after.support
                and end_query.before.support
            )
            record[f"DOM_W{seconds}_SUPPORT"] = support
            if not support:
                record.update(_nan_dom_window(seconds))
                continue

            imbalance_integral_delta = (
                end_query.cumulative.imbalance_l10_integral
                - start_query.cumulative.imbalance_l10_integral
            )
            depth_integral_delta = (
                end_query.cumulative.top10_depth_integral
                - start_query.cumulative.top10_depth_integral
            )
            stack_delta = (
                end_query.cumulative.stack_raw
                - start_query.cumulative.stack_raw
            )
            churn_delta = (
                end_query.cumulative.churn_abs
                - start_query.cumulative.churn_abs
            )
            suffix = f"pre_{seconds}s"
            record[
                f"DOM_ImbalanceL10MeanFavor_{suffix}"
            ] = (
                direction
                * imbalance_integral_delta
                / required
            )
            record[
                f"DOM_MicropriceDriftFavor_ticks_{suffix}"
            ] = direction * (
                end_query.before.microprice_raw
                - start_query.after.microprice_raw
            )
            record[
                (
                    "DOM_ProxyDirectionalStackPullBalanceL10_"
                    f"{suffix}"
                )
            ] = (
                direction * stack_delta / max(churn_delta, 1.0)
            )
            record[
                (
                    "DOM_NearChurnTurnoversPerSecondL10_"
                    f"{suffix}"
                )
            ] = (
                churn_delta
                * TICKS_PER_SECOND
                / max(depth_integral_delta, 1.0)
            )
        records.append(record)
    return pd.DataFrame.from_records(records)


def cluster_metadata(
    bursts: Sequence[LiquidityBurst],
    *,
    maximum_gap_seconds: int = 30,
) -> pd.DataFrame:
    ordered = sorted(
        bursts,
        key=lambda item: (
            item.session_date,
            int(item.source_second_ticks),
            item.lb_id,
        ),
    )
    rows: list[dict[str, object]] = []
    cluster = -1
    previous_session: str | None = None
    previous_cut: int | None = None
    for burst in ordered:
        cut = int(burst.source_second_ticks)
        if burst.session_date != previous_session:
            cluster = -1
            previous_cut = None
        is_new = bool(
            burst.session_date != previous_session
            or previous_cut is None
            or cut - int(previous_cut)
            > int(maximum_gap_seconds) * TICKS_PER_SECOND
        )
        if is_new:
            cluster += 1
        rows.append(
            {
                "lb_id": burst.lb_id,
                "LB_CLUSTER_ID_30S": (
                    f"{burst.session_date}_C{cluster:05d}"
                ),
            }
        )
        previous_session = burst.session_date
        previous_cut = cut
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        return frame
    sizes = frame.groupby("LB_CLUSTER_ID_30S")["lb_id"].transform(
        "size"
    )
    frame["LB_CLUSTER_SIZE_30S"] = sizes.astype(int)
    return frame


def profile_feature_frame(
    trades: np.ndarray,
    bursts: Sequence[LiquidityBurst],
    *,
    rth_start_ticks: int,
    drift_seconds: int,
    value_area_fraction: float,
    minimum_trades: int,
    minimum_elapsed_seconds: int,
) -> pd.DataFrame:
    diagnostics = profile_diagnostics(
        trades,
        contiguous_trade_ticks(trades),
        bursts,
        rth_start_ticks=rth_start_ticks,
        drift_seconds=drift_seconds,
        value_area_fraction=value_area_fraction,
    )
    if diagnostics.empty:
        return diagnostics
    profile_features = [
        "PRF_PocSignedDistance_ticks",
        "PRF_PocSide_Favor",
        "PRF_VaSignedPositionNorm",
        "PRF_InsideValueArea",
        "PRF_VaWidth_ticks",
        "PRF_PocDrift_ticks_300s",
        "PRF_PocVolumeShare",
        "PRF_ProfileEntropyNorm",
    ]
    finite = np.isfinite(
        diagnostics[profile_features].to_numpy(dtype=float)
    ).all(axis=1)
    diagnostics["PROFILE_RAW_SUPPORT"] = diagnostics[
        "profile_raw_available"
    ].astype(bool)
    diagnostics["PROFILE_F11_SUPPORT"] = (
        diagnostics["PROFILE_RAW_SUPPORT"]
        & diagnostics[
            "PRF_PocDrift_ticks_300s_available"
        ].astype(bool)
        & diagnostics["profile_trade_count"].ge(int(minimum_trades))
        & diagnostics["profile_elapsed_seconds"].ge(
            int(minimum_elapsed_seconds)
        )
        & finite
    )
    diagnostics.loc[
        ~diagnostics["PROFILE_F11_SUPPORT"],
        profile_features,
    ] = math.nan
    maximum_trade_ticks = []
    trade_ticks = contiguous_trade_ticks(trades)
    rth_start_index = int(
        np.searchsorted(trade_ticks, int(rth_start_ticks), side="left")
    )
    for burst in bursts:
        stop = int(
            np.searchsorted(
                trade_ticks,
                int(burst.source_second_ticks),
                side="left",
            )
        )
        maximum_trade_ticks.append(
            int(trade_ticks[stop - 1])
            if stop > rth_start_index
            else math.nan
        )
    diagnostics["MAX_PROFILE_TRADE_TICKS"] = maximum_trade_ticks
    return diagnostics[
        [
            "lb_id",
            "PROFILE_RAW_SUPPORT",
            "PROFILE_F11_SUPPORT",
            "MAX_PROFILE_TRADE_TICKS",
            *profile_features,
        ]
    ]


def build_feature_matrix(
    *,
    trades: np.ndarray,
    depth: np.ndarray,
    effective_depth_ticks: np.ndarray,
    bursts: Sequence[LiquidityBurst],
    rth_start_ticks: int,
    depth_load_start_ticks: int,
    config: Mapping[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    expected = validate_catalog(config)
    trade = trade_precursor_features(
        trades,
        bursts,
        rth_start_ticks=rth_start_ticks,
    )
    depth_config = config["depth"]
    dom = dom_precursor_features(
        depth,
        effective_depth_ticks,
        bursts,
        load_start_ticks=depth_load_start_ticks,
        maximum_age_ms=float(
            depth_config["max_global_group_age_ms"]
        ),
        minimum_spread=int(depth_config["min_spread_ticks"]),
        maximum_spread=int(depth_config["max_spread_ticks"]),
    )
    profile_config = config["profile"]
    profile = profile_feature_frame(
        trades,
        bursts,
        rth_start_ticks=rth_start_ticks,
        drift_seconds=int(profile_config["drift_seconds"]),
        value_area_fraction=float(
            profile_config["value_area_fraction"]
        ),
        minimum_trades=int(profile_config["min_profile_trades"]),
        minimum_elapsed_seconds=int(
            profile_config["min_profile_elapsed_seconds"]
        ),
    )
    clusters = cluster_metadata(
        bursts,
        maximum_gap_seconds=int(
            config["clusters"]["maximum_consecutive_gap_seconds"]
        ),
    )
    matrix = trade.merge(
        dom,
        on="lb_id",
        how="left",
        validate="one_to_one",
    ).merge(
        profile,
        on="lb_id",
        how="left",
        validate="one_to_one",
    ).merge(
        clusters,
        on="lb_id",
        how="left",
        validate="one_to_one",
    )
    matrix["COMBINED_W1_SUPPORT"] = (
        matrix["BASELINE_SUPPORT"].astype(bool)
        & matrix["DOM_STATE_SUPPORT"].astype(bool)
        & matrix["DOM_W1_SUPPORT"].astype(bool)
        & matrix["PROFILE_F11_SUPPORT"].astype(bool)
    )
    matrix["COMBINED_W5_SUPPORT"] = (
        matrix["BASELINE_SUPPORT"].astype(bool)
        & matrix["DOM_STATE_SUPPORT"].astype(bool)
        & matrix["DOM_W5_SUPPORT"].astype(bool)
        & matrix["PROFILE_F11_SUPPORT"].astype(bool)
    )
    matrix["COMBINED_W30_SUPPORT"] = (
        matrix["BASELINE_SUPPORT"].astype(bool)
        & matrix["DOM_STATE_SUPPORT"].astype(bool)
        & matrix["DOM_W30_SUPPORT"].astype(bool)
        & matrix["PROFILE_F11_SUPPORT"].astype(bool)
    )
    observed_features = [
        feature for feature in expected if feature in matrix.columns
    ]
    if observed_features != expected:
        missing = sorted(set(expected) - set(matrix.columns))
        raise RuntimeError(f"feature matrix missing catalog: {missing}")
    forbidden_fragments = (
        "regime",
        "continue_reached",
        "reverse_reached",
        "future",
        "out_post",
        "time_to_continue",
        "time_to_reverse",
        "max_move",
        "net_move",
        "expansion_dominance",
    )
    forbidden = [
        str(column)
        for column in matrix.columns
        if any(
            fragment in str(column).lower()
            for fragment in forbidden_fragments
        )
    ]
    if forbidden:
        raise RuntimeError(
            f"forbidden feature matrix columns: {sorted(forbidden)}"
        )
    if len(matrix) != len(bursts):
        raise RuntimeError(
            f"feature row mismatch {len(matrix)} != {len(bursts)}"
        )
    if matrix["lb_id"].nunique() != len(matrix):
        raise RuntimeError("feature matrix lb_id is not unique")

    lineage = {
        "audit_id": config["audit_id"],
        "feature_count": len(expected),
        "features": expected,
        "families": {
            str(family): list(features)
            for family, features in config[
                "feature_catalog"
            ].items()
        },
        "predictor_cut": "< source_second_ticks",
        "detector_baseline_zone": (
            "[source_second_ticks, publish_ticks]"
        ),
        "support_columns_are_predictors": False,
        "labels_opened": False,
        "outcomes_opened": False,
        "models_opened": False,
    }
    return matrix, lineage
