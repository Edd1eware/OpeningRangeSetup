from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from .config import ResearchConfig
from .feature_extractor import build_time_slices, cumulative_vwap_and_slopes
from .profile_builder import Profile, window_mask
from .statistics import first_touch_result, safe_div


def _tick_path(frame: pd.DataFrame) -> pd.DataFrame:
    path = frame.sort_values(["timestamp", "sequence"], kind="stable").copy()
    path["open"] = path["price"]
    path["high"] = path["price"]
    path["low"] = path["price"]
    path["close"] = path["price"]
    path["row_count"] = 1
    path["granularity"] = "TICK"
    return path


def _path_for_detection(session_frame: pd.DataFrame, config: ResearchConfig) -> tuple[pd.DataFrame, str, float]:
    relevant = session_frame.loc[
        window_mask(session_frame, config.lvn_profile_start, config.retest_end)
    ].copy()
    if relevant.empty:
        return pd.DataFrame(), "UNKNOWN", 0.0
    if (relevant["input_granularity"] == "TICK").all():
        return _tick_path(relevant), "TICK", 0.0
    slices = build_time_slices(relevant)
    return slices, "BAR_UNORDERED", float(slices.attrs.get("resolution_seconds", 0.0))


def _approach(path: pd.DataFrame, start_position: int, low_edge: float, high_edge: float) -> tuple[str, str, float, pd.Timestamp | None]:
    for position in range(start_position - 1, -1, -1):
        price = float(path.iloc[position]["close"])
        if price > high_edge:
            return "FROM_ABOVE", "LONG", price, path.iloc[position]["timestamp"]
        if price < low_edge:
            return "FROM_BELOW", "SHORT", price, path.iloc[position]["timestamp"]
    return "UNKNOWN", "UNKNOWN", math.nan, None


def _resolve_interaction(
    retest_path: pd.DataFrame,
    start_position: int,
    approach: str,
    zone_low: float,
    zone_high: float,
    precision: str,
    config: ResearchConfig,
) -> dict[str, object]:
    # Value acceptance/rejection at the LVN zone: acceptance = price traverses the
    # whole zone (continuation), rejection = price stalls and returns (reversal).
    # Direction is only assigned once the close confirms one of the two, so the
    # outcome never uses information from before its own trigger.
    unresolved: dict[str, object] = {
        "lvn_interaction": "UNKNOWN_APPROACH" if approach == "UNKNOWN" else "UNRESOLVED",
        "trade_logic": "NONE",
        "resolved_side": "UNKNOWN",
        "entry_price": math.nan,
        "resolution_time": None,
        "resolution_sequence": None,
    }
    if approach not in ("FROM_ABOVE", "FROM_BELOW"):
        return unresolved
    confirm = config.resolution_confirm_ticks * config.tick_size
    accept_below = zone_low - confirm - 1e-9
    accept_above = zone_high + confirm + 1e-9
    for cursor in range(start_position, len(retest_path)):
        close = float(retest_path.iloc[cursor]["close"])
        if approach == "FROM_ABOVE":
            accepted, rejected = close < accept_below, close > accept_above
        else:
            accepted, rejected = close > accept_above, close < accept_below
        if not accepted and not rejected:
            continue
        row = retest_path.iloc[cursor]
        if accepted:
            side = "SHORT" if approach == "FROM_ABOVE" else "LONG"
        else:
            side = "LONG" if approach == "FROM_ABOVE" else "SHORT"
        return {
            "lvn_interaction": "ACCEPTANCE" if accepted else "REJECTION",
            "trade_logic": "CONTINUATION" if accepted else "REVERSAL",
            "resolved_side": side,
            "entry_price": close,
            "resolution_time": row["timestamp"],
            "resolution_sequence": int(row["sequence"]) if precision == "TICK" and "sequence" in row else None,
        }
    return unresolved


def _imbalance_metrics(rows: pd.DataFrame, lvn_price: float, config: ResearchConfig) -> dict[str, object]:
    if rows.empty or float(rows["bid_volume"].sum() + rows["ask_volume"].sum()) <= 0:
        return {"imbalance_available": False, "buy_imbalance_count": math.nan, "sell_imbalance_count": math.nan}
    work = rows.copy()
    work["price_bin"] = np.rint(work["price"] / config.tick_size).astype(int)
    center_bin = int(round(lvn_price / config.tick_size))
    buy_count = sell_count = 0
    for _, timestamp_rows in work.groupby("timestamp", sort=False):
        matrix = timestamp_rows.groupby("price_bin").agg(bid=("bid_volume", "sum"), ask=("ask_volume", "sum"))
        for price_bin in range(center_bin - config.imbalance_neighbor_levels, center_bin + config.imbalance_neighbor_levels + 1):
            bid = float(matrix.at[price_bin, "bid"]) if price_bin in matrix.index else 0.0
            ask = float(matrix.at[price_bin, "ask"]) if price_bin in matrix.index else 0.0
            lower_bid = float(matrix.at[price_bin - 1, "bid"]) if price_bin - 1 in matrix.index else 0.0
            upper_ask = float(matrix.at[price_bin + 1, "ask"]) if price_bin + 1 in matrix.index else 0.0
            if lower_bid >= config.imbalance_min_compare_volume and ask >= lower_bid * config.imbalance_ratio:
                buy_count += 1
            if upper_ask >= config.imbalance_min_compare_volume and bid >= upper_ask * config.imbalance_ratio:
                sell_count += 1
    return {
        "imbalance_available": True,
        "buy_imbalance_count": buy_count,
        "sell_imbalance_count": sell_count,
        "net_imbalance_count": buy_count - sell_count,
    }


def _order_flow_metrics(
    session_frame: pd.DataFrame,
    event_start: pd.Timestamp,
    event_end: pd.Timestamp,
    lvn_price: float,
    config: ResearchConfig,
    precision: str,
) -> dict[str, object]:
    episode = session_frame.loc[
        (session_frame["timestamp"] >= event_start) & (session_frame["timestamp"] <= event_end)
    ]
    tolerance = config.retest_tolerance_ticks * config.tick_size + 1e-9
    at_lvn = episode.loc[(episode["price"] - lvn_price).abs() <= tolerance]
    local_bid = float(at_lvn["bid_volume"].sum())
    local_ask = float(at_lvn["ask_volume"].sum())
    explicit_big_available = bool(episode["is_big_trade"].notna().any() or episode["big_trade_volume"].notna().any())
    big_trade_available = precision == "TICK" or explicit_big_available
    if big_trade_available:
        explicit_flags = episode["is_big_trade"].fillna(0) > 0
        size_flags = (episode["volume"] >= config.big_trade_min_size) if precision == "TICK" else pd.Series(False, index=episode.index)
        big_rows = episode.loc[explicit_flags | size_flags]
        big_count: float = float(len(big_rows))
        big_volume: float = float(big_rows["big_trade_volume"].fillna(big_rows["volume"]).sum())
    else:
        big_count = big_volume = math.nan
    iceberg_available = bool(episode["iceberg"].notna().any())
    absorption_available = bool(episode["absorption"].notna().any())
    result: dict[str, object] = {
        "lvn_retest_volume": float(at_lvn["volume"].sum()),
        "lvn_retest_bid_volume": local_bid,
        "lvn_retest_ask_volume": local_ask,
        "lvn_retest_delta": local_ask - local_bid,
        "total_retest_volume": float(episode["volume"].sum()),
        "big_trade_available": big_trade_available,
        "big_trade_count": big_count,
        "big_trade_volume": big_volume,
        "iceberg_available": iceberg_available,
        "iceberg_count": float(episode["iceberg"].fillna(0).sum()) if iceberg_available else math.nan,
        "absorption_available": absorption_available,
        "absorption_count": float(episode["absorption"].fillna(0).sum()) if absorption_available else math.nan,
    }
    # Aggression confirmation (speed + flow rate) over the retest episode. Bars are
    # 1-minute footprints, so BAR granularity assumes 60s per distinct timestamp.
    per_bar = episode.groupby("timestamp", sort=False).agg(
        trades=("bar_trades", "first"), vol=("volume", "sum"),
        bid=("bid_volume", "sum"), ask=("ask_volume", "sum"))
    if precision == "TICK":
        # Sub-second touch episodes carry no measurable rate; floor at 1 second.
        duration = max(float((event_end - event_start).total_seconds()), 1.0)
    else:
        duration = max(60.0 * len(per_bar), 1e-9)
    trades_available = bool(per_bar["trades"].notna().any())
    result.update({
        "tape_speed_trades_per_second": float(per_bar["trades"].fillna(0).sum()) / duration if trades_available else math.nan,
        "aggression_volume_per_second": float(per_bar["vol"].sum()) / duration,
        "aggression_delta_per_second": float(per_bar["ask"].sum() - per_bar["bid"].sum()) / duration,
    })
    # Delta and delta-change of the touch bar vs the prior bar (both closed by the
    # time the event is evaluated; footprint bars are only known at their close).
    bar_deltas = (
        session_frame.loc[session_frame["timestamp"] <= event_start]
        .groupby("timestamp", sort=True)
        .agg(bid=("bid_volume", "sum"), ask=("ask_volume", "sum"))
    )
    if len(bar_deltas):
        deltas = bar_deltas["ask"] - bar_deltas["bid"]
        delta_touch = float(deltas.iloc[-1])
        delta_prev = float(deltas.iloc[-2]) if len(deltas) > 1 else math.nan
        delta_change = delta_touch - delta_prev if math.isfinite(delta_prev) else math.nan
    else:
        delta_touch = delta_prev = delta_change = math.nan
    result.update({
        "delta_touch_bar": delta_touch,
        "delta_prev_bar": delta_prev,
        "delta_change_touch_bar": delta_change,
    })
    result.update(_imbalance_metrics(episode, lvn_price, config))
    return result


def _outcome_path(
    session_frame: pd.DataFrame,
    event_time: pd.Timestamp,
    event_sequence: int | None,
    precision: str,
    config: ResearchConfig,
) -> tuple[pd.DataFrame, str]:
    until_end = session_frame.loc[window_mask(session_frame, config.retest_start, config.retest_end)].copy()
    if precision == "TICK":
        if event_sequence is None:
            future = until_end.loc[until_end["timestamp"] >= event_time]
        else:
            future = until_end.loc[
                (until_end["timestamp"] > event_time)
                | ((until_end["timestamp"] == event_time) & (until_end["sequence"] >= event_sequence))
            ]
        return _tick_path(future), "EXACT_TICK_SEQUENCE"
    slices = build_time_slices(until_end)
    # A footprint bar does not reveal whether its high/low happened before or after the touch.
    # Starting at the next slice avoids manufacturing intrabar ordering.
    return slices.loc[slices["timestamp"] > event_time].copy(), "NEXT_BAR_CAUSAL_CONSERVATIVE"


def _measure_outcome(
    session_frame: pd.DataFrame,
    event_time: pd.Timestamp,
    event_sequence: int | None,
    reference_price: float,
    expected_side: str,
    precision: str,
    config: ResearchConfig,
) -> dict[str, object]:
    path, policy = _outcome_path(session_frame, event_time, event_sequence, precision, config)
    base: dict[str, object] = {"outcome_start_policy": policy, "outcome_path_rows": len(path)}
    if path.empty:
        base.update({"max_up_ticks": math.nan, "max_down_ticks": math.nan, "mfe_ticks": math.nan, "mae_ticks": math.nan})
        for target in (20, 40, 60, 80):
            base.update({
                f"hit_plus_{target}": False,
                f"hit_minus_{target}": False,
                f"tp_sl_{target}_{target}_result": "NO_PATH",
                f"realized_r_{target}_{target}": math.nan,
                f"exit_price_{target}_{target}": math.nan,
                f"exit_time_et_{target}_{target}": None,
                f"trade_duration_seconds_{target}_{target}": math.nan,
            })
        return base

    elapsed = (path["timestamp"] - event_time).dt.total_seconds().to_numpy(dtype=float)
    if precision == "TICK":
        elapsed = elapsed + np.arange(len(elapsed), dtype=float) * 1e-9
    up = (path["high"].to_numpy(dtype=float) - reference_price) / config.tick_size
    down = (reference_price - path["low"].to_numpy(dtype=float)) / config.tick_size
    max_up, max_down = float(np.nanmax(up)), float(np.nanmax(down))
    base.update({
        "max_up_ticks": max_up,
        "max_down_ticks": max_down,
        "time_to_max_up_seconds": float(elapsed[int(np.nanargmax(up))]),
        "time_to_max_down_seconds": float(elapsed[int(np.nanargmax(down))]),
    })
    if expected_side == "LONG":
        favorable, adverse = up, down
        final_directional = (float(path.iloc[-1]["close"]) - reference_price) / config.tick_size
    elif expected_side == "SHORT":
        favorable, adverse = down, up
        final_directional = (reference_price - float(path.iloc[-1]["close"])) / config.tick_size
    else:
        favorable = adverse = np.full(len(path), np.nan)
        final_directional = math.nan

    if expected_side == "UNKNOWN":
        base.update({
            "mfe_ticks": math.nan, "mae_ticks": math.nan,
            "time_to_mfe_seconds": math.nan, "time_to_mae_seconds": math.nan,
            "mfe_mae_ratio": math.nan, "mae_before_mfe_ticks": math.nan,
            "max_pullback_before_mfe_ticks": math.nan, "rr_max_achievable": math.nan,
        })
    else:
        mfe, mae = float(np.nanmax(favorable)), float(np.nanmax(adverse))
        mfe_position = int(np.nanargmax(favorable))
        # Adverse excursion that had to be survived BEFORE price printed its max
        # extension: this bounds the SL a winner actually required.
        mae_before_mfe = float(np.nanmax(adverse[: mfe_position + 1]))
        # Largest retracement from the running favorable peak on the way to the MFE:
        # the pullback depth a runner-style management had to tolerate.
        running_peak = np.maximum.accumulate(favorable[: mfe_position + 1])
        max_pullback = float(np.nanmax(running_peak - favorable[: mfe_position + 1]))
        base.update({
            "mfe_ticks": mfe,
            "mae_ticks": mae,
            "time_to_mfe_seconds": float(elapsed[mfe_position]),
            "time_to_mae_seconds": float(elapsed[int(np.nanargmax(adverse))]),
            "mfe_mae_ratio": safe_div(mfe, mae),
            "mae_before_mfe_ticks": mae_before_mfe,
            "max_pullback_before_mfe_ticks": max_pullback,
            # Floor the risk at 1 tick: a winner with zero adverse excursion still
            # cannot be traded with less than 1 tick of stop.
            "rr_max_achievable": safe_div(mfe, max(mae_before_mfe, 1.0)),
        })
    direction_sign = 1.0 if expected_side == "LONG" else -1.0 if expected_side == "SHORT" else math.nan
    for target in (20, 40, 60, 80):
        base[f"hit_plus_{target}"] = bool(max_up >= target)
        base[f"hit_minus_{target}"] = bool(max_down >= target)
        exit_price = exit_time = math.nan
        duration = float(elapsed[-1])
        if expected_side == "UNKNOWN":
            result, realized_r = "UNKNOWN_DIRECTION", math.nan
        else:
            result, touch_elapsed, touch_index = first_touch_result(elapsed, favorable, adverse, target)
            if result == "TP":
                realized_r = 1.0
                exit_price = reference_price + direction_sign * target * config.tick_size
                exit_time = path.iloc[touch_index]["timestamp"]
                duration = touch_elapsed
            elif result == "SL":
                realized_r = -1.0
                exit_price = reference_price - direction_sign * target * config.tick_size
                exit_time = path.iloc[touch_index]["timestamp"]
                duration = touch_elapsed
            elif result == "AMBIGUOUS":
                # Both TP and SL crossed in the same unordered bar: time is known,
                # the resolved price is not — never guess which one hit first.
                realized_r = math.nan
                exit_time = path.iloc[touch_index]["timestamp"]
                duration = touch_elapsed
            else:
                result = "TIME_EXIT"
                realized_r = float(np.clip(final_directional / target, -1.0, 1.0))
                exit_price = float(path.iloc[-1]["close"])
                exit_time = path.iloc[-1]["timestamp"]
        base[f"tp_sl_{target}_{target}_result"] = result
        base[f"realized_r_{target}_{target}"] = realized_r
        base[f"exit_price_{target}_{target}"] = exit_price
        base[f"exit_time_et_{target}_{target}"] = exit_time.isoformat() if isinstance(exit_time, pd.Timestamp) else None
        base[f"trade_duration_seconds_{target}_{target}"] = duration
    return base


def detect_retests(
    session_frame: pd.DataFrame,
    session_date: date,
    minute_profile: Profile,
    context_profile: Profile,
    session_context: dict[str, object],
    config: ResearchConfig,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    path, precision, resolution = _path_for_detection(session_frame, config)
    if path.empty:
        return [], [{"debug_type": "RETEST", "status": "REJECTED", "reason": "NO_RETEST_WINDOW_DATA"}]
    path = path.reset_index(drop=True)
    path["_path_position"] = np.arange(len(path), dtype=int)
    retest_path = path.loc[window_mask(path, config.retest_start, config.retest_end)].reset_index(drop=True)
    if retest_path.empty:
        return [], [{"debug_type": "RETEST", "status": "REJECTED", "reason": "NO_RETEST_WINDOW_DATA"}]
    events: list[dict[str, object]] = []
    debug: list[dict[str, object]] = []
    tolerance = config.retest_tolerance_ticks * config.tick_size
    rearm_distance = (config.retest_tolerance_ticks + config.retest_rearm_ticks) * config.tick_size
    rth_open = float(session_context.get("rth_open", math.nan))

    for lvn in minute_profile.lvns:
        level = float(lvn["price"])
        zone_low = float(lvn.get("low_price", level)) - tolerance
        zone_high = float(lvn.get("high_price", level)) + tolerance
        touched = (retest_path["low"] <= level + tolerance + 1e-9) & (retest_path["high"] >= level - tolerance - 1e-9)
        position = 0
        retest_number = 0
        while position < len(retest_path):
            candidates = np.flatnonzero(touched.to_numpy()[position:])
            if candidates.size == 0:
                break
            start_position = position + int(candidates[0])
            start_row = retest_path.iloc[start_position]
            full_path_position = int(start_row["_path_position"])
            approach, approach_hypothetical_side, prior_price, prior_time = _approach(path, full_path_position, zone_low, zone_high)
            interaction = _resolve_interaction(retest_path, start_position, approach, zone_low, zone_high, precision, config)
            expected_side = str(interaction["resolved_side"])
            end_position = start_position
            rearm_position = len(retest_path)
            for cursor in range(start_position + 1, len(retest_path)):
                row = retest_path.iloc[cursor]
                row_touched = bool(touched.iloc[cursor])
                if row_touched:
                    end_position = cursor
                far_outside = float(row["close"]) > level + rearm_distance or float(row["close"]) < level - rearm_distance
                if far_outside:
                    rearm_position = cursor
                    break
            retest_number += 1
            event_time = start_row["timestamp"]
            event_end = retest_path.iloc[end_position]["timestamp"]
            dwell = max(0.0, float((event_end - event_time).total_seconds()))
            if precision != "TICK" and resolution > 0:
                dwell += resolution
            seconds_from_0931 = (
                event_time.hour * 3600 + event_time.minute * 60 + event_time.second + event_time.microsecond / 1e6
                - (config.retest_start.hour * 3600 + config.retest_start.minute * 60 + config.retest_start.second)
            )
            prior_move_ticks = safe_div(prior_price - rth_open, config.tick_size)
            prior_direction = "UP" if prior_move_ticks > 0 else "DOWN" if prior_move_ticks < 0 else "FLAT"
            event_sequence = int(start_row["sequence"]) if precision == "TICK" and "sequence" in start_row else None
            causal = cumulative_vwap_and_slopes(session_frame, event_time, config)
            approach_speed = safe_div(
                abs(prior_price - level) / config.tick_size,
                float((event_time - prior_time).total_seconds()) if prior_time is not None else math.nan,
            )
            resolution_time = interaction["resolution_time"]
            entry_price = float(interaction["entry_price"])
            seconds_touch_to_entry = (
                float((resolution_time - event_time).total_seconds()) if resolution_time is not None else math.nan
            )
            zone_speed = safe_div(
                safe_div(abs(entry_price - level), config.tick_size),
                seconds_touch_to_entry,
            )
            event: dict[str, object] = {
                "date": session_date.isoformat(),
                "symbol": str(session_frame["symbol"].iloc[0]) if not session_frame.empty else config.symbol,
                "event_id": f"{session_date:%Y%m%d}_{lvn['lvn_id']}_R{retest_number:02d}",
                "lvn_id": lvn["lvn_id"],
                "lvn_price": level,
                "retest_number": retest_number,
                "retest_time_et": event_time.isoformat(),
                "retest_end_time_et": event_end.isoformat(),
                "seconds_from_0931": seconds_from_0931,
                "approach": approach,
                "approach_hypothetical_side": approach_hypothetical_side,
                "lvn_interaction": interaction["lvn_interaction"],
                "trade_logic": interaction["trade_logic"],
                "expected_reaction_side": expected_side,
                "lvn_zone_low": zone_low,
                "lvn_zone_high": zone_high,
                "entry_price": entry_price,
                "entry_time_et": resolution_time.isoformat() if resolution_time is not None else None,
                "seconds_touch_to_entry": seconds_touch_to_entry,
                "entry_distance_from_lvn_ticks": safe_div(abs(entry_price - level), config.tick_size),
                "zone_speed_ticks_per_second": zone_speed,
                "deceleration_ratio": safe_div(zone_speed, approach_speed),
                "prior_movement_direction": prior_direction,
                "prior_price": prior_price,
                "prior_move_from_open_ticks": prior_move_ticks,
                "distance_traveled_to_lvn_ticks": safe_div(abs(prior_price - level), config.tick_size),
                "time_inside_lvn_zone_seconds": dwell,
                "timing_precision": precision,
                "source_resolution_seconds": resolution,
                "lvn_depth": lvn.get("depth"),
                "lvn_width_ticks": lvn.get("width_ticks"),
                "lvn_volume": lvn.get("volume"),
                "context_profile_shape": context_profile.shape.get("profile_shape", "unknown"),
                "context_shape_confidence": context_profile.shape.get("shape_confidence_score", math.nan),
                "minute_profile_shape": minute_profile.shape.get("profile_shape", "unknown"),
                "minute_shape_confidence": minute_profile.shape.get("shape_confidence_score", math.nan),
                "distance_to_context_poc_ticks": safe_div(level - float(context_profile.metrics.get("poc", math.nan)), config.tick_size),
                "distance_to_context_vah_ticks": safe_div(level - float(context_profile.metrics.get("vah", math.nan)), config.tick_size),
                "distance_to_context_val_ticks": safe_div(level - float(context_profile.metrics.get("val", math.nan)), config.tick_size),
                "distance_to_minute_poc_ticks": safe_div(level - float(minute_profile.metrics.get("poc", math.nan)), config.tick_size),
                "distance_to_open_ticks": safe_div(level - rth_open, config.tick_size),
                "distance_to_or_high_ticks": safe_div(level - float(session_context.get("or_high", math.nan)), config.tick_size),
                "distance_to_or_low_ticks": safe_div(level - float(session_context.get("or_low", math.nan)), config.tick_size),
                "open_vs_context_value": session_context.get("open_vs_context_value"),
                "open_vs_context_poc": session_context.get("open_vs_context_poc"),
                "vwap": causal["vwap"],
                "distance_to_vwap_ticks": safe_div(level - causal["vwap"], config.tick_size),
                "vwap_slope_ticks": causal["vwap_slope_ticks"],
                "ema": causal["ema"],
                "distance_to_ema_ticks": safe_div(level - causal["ema"], config.tick_size),
                "ema_slope_ticks": causal["ema_slope_ticks"],
                "realized_volatility": causal["realized_volatility"],
                "approach_speed_ticks_per_second": approach_speed,
            }
            for shape_name in ("D", "P", "b", "double", "trend_up", "trend_down", "unknown"):
                event[f"context_prob_{shape_name}"] = context_profile.shape.get(f"prob_{shape_name}", math.nan)
                event[f"minute_prob_{shape_name}"] = minute_profile.shape.get(f"prob_{shape_name}", math.nan)
            # Profile Feature Engine (usuario 2026-07-09): momentos/estructura del perfil
            # contextual y del minuto como features del EVENTO, para que CatBoost pueda
            # rankear qué separa los días buenos de los malos.
            for metric in ("skewness", "kurtosis_excess", "entropy", "profile_width_ticks",
                           "value_area_width_ticks", "upper_volume_share", "lower_volume_share",
                           "poc_position", "center_of_mass_position", "max_level_volume_share",
                           "volume_slope", "total_volume", "delta"):
                event[f"ctx_{metric}"] = context_profile.metrics.get(metric, math.nan)
                event[f"min_{metric}"] = minute_profile.metrics.get(metric, math.nan)
            for shape_metric in ("distribution_count", "double_mode_separation", "double_valley_depth"):
                event[f"ctx_{shape_metric}"] = context_profile.shape.get(shape_metric, math.nan)
            event["ctx_hvn_count"] = len(context_profile.hvns)
            event["ctx_lvn_count"] = len(context_profile.lvns)
            event["minute_lvn_count"] = len(minute_profile.lvns)
            main_hvn = max(context_profile.hvns, key=lambda node: float(node.get("volume", 0)), default=None)
            event["ctx_hvn_dominance"] = float(main_hvn["prominence"]) if main_hvn and "prominence" in main_hvn else math.nan
            event["distance_to_main_hvn_ticks"] = (
                safe_div(level - float(main_hvn["price"]), config.tick_size) if main_hvn else math.nan
            )
            ctx_poc = float(context_profile.metrics.get("poc", math.nan))
            ctx_vah = float(context_profile.metrics.get("vah", math.nan))
            ctx_val = float(context_profile.metrics.get("val", math.nan))
            event["open_to_ctx_poc_ticks"] = safe_div(rth_open - ctx_poc, config.tick_size)
            event["open_to_ctx_vah_ticks"] = safe_div(rth_open - ctx_vah, config.tick_size)
            event["open_to_ctx_val_ticks"] = safe_div(rth_open - ctx_val, config.tick_size)
            event["day_of_week"] = session_date.weekday()
            event.update(session_context)
            event.update(_order_flow_metrics(session_frame, event_time, event_end, level, config, precision))
            # Versión CAUSAL de la agresión: ventana touch -> confirmación de entrada.
            # Las métricas de episodio completo (arriba) pueden incluir flujo POSTERIOR a la
            # entrada y solo sirven para descripción, nunca como feature de modelo (leak).
            causal_end = resolution_time if resolution_time is not None else event_time
            causal_flow = _order_flow_metrics(session_frame, event_time, causal_end, level, config, precision)
            event.update({
                "pre_entry_volume_per_second": causal_flow.get("aggression_volume_per_second", math.nan),
                "pre_entry_delta_per_second": causal_flow.get("aggression_delta_per_second", math.nan),
                "pre_entry_tape_speed": causal_flow.get("tape_speed_trades_per_second", math.nan),
                "pre_entry_lvn_delta": causal_flow.get("lvn_retest_delta", math.nan),
                "pre_entry_lvn_volume": causal_flow.get("lvn_retest_volume", math.nan),
            })
            if expected_side in ("LONG", "SHORT"):
                # Outcome starts at the acceptance/rejection confirmation and is
                # measured from the confirmation price, never from the touch.
                event.update(_measure_outcome(
                    session_frame,
                    resolution_time,
                    interaction["resolution_sequence"],
                    entry_price,
                    expected_side,
                    precision,
                    config,
                ))
            else:
                event.update(_measure_outcome(session_frame, event_time, event_sequence, level, expected_side, precision, config))
            events.append(event)
            position = rearm_position
        if retest_number == 0:
            debug.append({
                "debug_type": "RETEST",
                "date": session_date.isoformat(),
                "lvn_id": lvn["lvn_id"],
                "lvn_price": level,
                "status": "NO_RETEST",
                "reason": "PRICE_DID_NOT_TOUCH_LVN_IN_RETEST_WINDOW",
            })
    return events, debug
