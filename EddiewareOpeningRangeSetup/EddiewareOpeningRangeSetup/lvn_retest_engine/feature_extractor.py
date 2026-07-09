from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from .config import ResearchConfig
from .profile_builder import Profile, window_mask
from .statistics import linear_slope, safe_div


def _first_valid(series: pd.Series) -> float:
    valid = series.dropna()
    return float(valid.iloc[0]) if not valid.empty else math.nan


def _last_valid(series: pd.Series) -> float:
    valid = series.dropna()
    return float(valid.iloc[-1]) if not valid.empty else math.nan


def build_time_slices(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    work = frame.sort_values(["timestamp", "sequence"], kind="stable").copy()
    work["row_high"] = work["high"].where(work["high"].notna(), work["price"])
    work["row_low"] = work["low"].where(work["low"].notna(), work["price"])
    work["row_open"] = work["open"].where(work["open"].notna(), work["price"])
    work["row_close"] = work["close"].where(work["close"].notna(), work["price"])
    work["price_volume"] = work["price"] * work["volume"]
    slices = work.groupby("timestamp", sort=True).agg(
        open=("row_open", _first_valid),
        high=("row_high", "max"),
        low=("row_low", "min"),
        close=("row_close", _last_valid),
        volume=("volume", "sum"),
        bid_volume=("bid_volume", "sum"),
        ask_volume=("ask_volume", "sum"),
        price_volume=("price_volume", "sum"),
        row_count=("price", "size"),
        granularity=("input_granularity", "first"),
    ).reset_index()
    slices["delta"] = slices["ask_volume"] - slices["bid_volume"]
    slices["slice_vwap"] = slices["price_volume"] / slices["volume"].replace(0, np.nan)
    differences = slices["timestamp"].diff().dt.total_seconds()
    positive = differences[differences > 0]
    resolution = float(positive.median()) if not positive.empty else 0.0
    slices.attrs["resolution_seconds"] = resolution
    slices.attrs["granularity"] = "FOOTPRINT_BAR" if (slices["granularity"] == "FOOTPRINT_BAR").any() else "TICK"
    return slices


def build_daily_market_context(data: pd.DataFrame, config: ResearchConfig) -> pd.DataFrame:
    daily_rows: list[dict[str, object]] = []
    for session_date, frame in data.groupby("session_date", sort=True):
        rth = frame.loc[window_mask(frame, config.lvn_profile_start, config.rth_end)]
        slices = build_time_slices(rth)
        if slices.empty:
            continue
        last_timestamp = slices.iloc[-1]["timestamp"]
        last_seconds = last_timestamp.hour * 3600 + last_timestamp.minute * 60 + last_timestamp.second
        required_seconds = config.rth_end.hour * 3600 + config.rth_end.minute * 60 + config.rth_end.second - 60
        rth_complete = last_seconds >= required_seconds
        daily_rows.append({
            "session_date": session_date,
            "daily_open": float(slices.iloc[0]["open"]),
            "daily_high": float(slices["high"].max()),
            "daily_low": float(slices["low"].min()),
            "daily_close": float(slices.iloc[-1]["close"]) if rth_complete else math.nan,
            "daily_rth_complete": rth_complete,
        })
    if not daily_rows:
        return pd.DataFrame()
    daily = pd.DataFrame(daily_rows).sort_values("session_date").reset_index(drop=True)
    daily["previous_rth_close"] = daily["daily_close"].shift(1)
    previous = daily["previous_rth_close"]
    daily["true_range"] = np.maximum.reduce([
        daily["daily_high"] - daily["daily_low"],
        (daily["daily_high"] - previous).abs(),
        (daily["daily_low"] - previous).abs(),
    ])
    daily.loc[~daily["daily_rth_complete"], "true_range"] = np.nan
    # Shift one full session: current-day ATR never sees the current day's future range.
    daily["atr"] = daily["true_range"].shift(1).rolling(config.atr_period, min_periods=1).mean()
    daily["gap_points"] = daily["daily_open"] - daily["previous_rth_close"]
    return daily


def session_features(
    session_frame: pd.DataFrame,
    context_profile: Profile,
    minute_profile: Profile,
    daily_context_row: dict[str, object] | None,
    config: ResearchConfig,
) -> dict[str, object]:
    minute_rows = session_frame.loc[window_mask(session_frame, config.lvn_profile_start, config.lvn_profile_end)]
    context_rows = session_frame.loc[window_mask(session_frame, config.context_profile_start, config.context_profile_end)]
    minute_slices = build_time_slices(minute_rows)
    context_slices = build_time_slices(context_rows)
    open_price = float(minute_slices.iloc[0]["open"]) if not minute_slices.empty else math.nan
    or_high = float(minute_slices["high"].max()) if not minute_slices.empty else math.nan
    or_low = float(minute_slices["low"].min()) if not minute_slices.empty else math.nan
    or_volume = float(minute_rows["volume"].sum()) if not minute_rows.empty else 0.0
    or_delta = float((minute_rows["ask_volume"] - minute_rows["bid_volume"]).sum()) if not minute_rows.empty else 0.0
    or_vwap = safe_div(float((minute_rows["price"] * minute_rows["volume"]).sum()), or_volume)
    premarket_high = float(context_slices["high"].max()) if not context_slices.empty else math.nan
    premarket_low = float(context_slices["low"].min()) if not context_slices.empty else math.nan
    val = float(context_profile.metrics.get("val", math.nan))
    vah = float(context_profile.metrics.get("vah", math.nan))
    poc = float(context_profile.metrics.get("poc", math.nan))
    if math.isnan(open_price) or math.isnan(val) or math.isnan(vah):
        open_vs_value = "UNKNOWN"
    elif open_price > vah:
        open_vs_value = "ABOVE_VAH"
    elif open_price < val:
        open_vs_value = "BELOW_VAL"
    else:
        open_vs_value = "INSIDE_VALUE"
    if math.isnan(open_price) or math.isnan(poc):
        open_vs_poc = "UNKNOWN"
    else:
        open_vs_poc = "ABOVE_POC" if open_price > poc else "BELOW_POC" if open_price < poc else "AT_POC"

    features: dict[str, object] = {
        "rth_open": open_price,
        "open_vs_context_value": open_vs_value,
        "open_vs_context_poc": open_vs_poc,
        "premarket_high": premarket_high,
        "premarket_low": premarket_low,
        "premarket_range_ticks": safe_div(premarket_high - premarket_low, config.tick_size),
        "or_high": or_high,
        "or_low": or_low,
        "or_width_ticks": safe_div(or_high - or_low, config.tick_size),
        "or_delta": or_delta,
        "or_volume": or_volume,
        "or_vwap": or_vwap,
        "minute_profile_poc": minute_profile.metrics.get("poc", math.nan),
    }
    if daily_context_row:
        previous_close = float(daily_context_row.get("previous_rth_close", math.nan))
        atr = float(daily_context_row.get("atr", math.nan))
        features.update({
            "previous_rth_close": previous_close,
            "gap_points": daily_context_row.get("gap_points", math.nan),
            "gap_ticks": safe_div(float(daily_context_row.get("gap_points", math.nan)), config.tick_size),
            "gap_available": math.isfinite(previous_close),
            "atr_points": atr,
            "atr_ticks": safe_div(atr, config.tick_size),
            "atr_available": math.isfinite(atr),
        })
    return features


def cumulative_vwap_and_slopes(
    session_frame: pd.DataFrame,
    event_time: pd.Timestamp,
    config: ResearchConfig,
) -> dict[str, float]:
    causal = session_frame.loc[
        window_mask(session_frame, config.lvn_profile_start, config.retest_end)
        & (session_frame["timestamp"] <= event_time)
    ]
    if causal.empty:
        return {"vwap": math.nan, "vwap_slope": math.nan, "ema": math.nan, "ema_slope": math.nan, "realized_volatility": math.nan}
    slices = build_time_slices(causal)
    causal_volume = float(causal["volume"].sum())
    vwap = safe_div(float((causal["price"] * causal["volume"]).sum()), causal_volume)
    slice_vwap = (slices["price_volume"].cumsum() / slices["volume"].cumsum().replace(0, np.nan)).dropna()
    vwap_slope = linear_slope(slice_vwap.tail(5).to_numpy(dtype=float)) / config.tick_size if len(slice_vwap) >= 2 else 0.0
    closes = slices["close"].astype(float)
    ema_series = closes.ewm(span=config.ema_span, adjust=False).mean()
    ema = float(ema_series.iloc[-1])
    ema_slope = linear_slope(ema_series.tail(5).to_numpy(dtype=float)) / config.tick_size if len(ema_series) >= 2 else 0.0
    returns = closes.pct_change().dropna()
    realized = float(returns.std(ddof=0) * math.sqrt(len(returns))) if not returns.empty else 0.0
    return {
        "vwap": vwap,
        "vwap_slope_ticks": vwap_slope,
        "ema": ema,
        "ema_slope_ticks": ema_slope,
        "realized_volatility": realized,
    }
