#!/usr/bin/env python3
"""Preregistered V51 OR5 depth-bifurcation discovery backtest.

This program implements the frozen specification in:
contexto_codex_claude/20260726_121_PREREGISTRO_V51_OR5_DEPTH_BIFURCATION.md

It opens discovery 2022 only.  Validation 2023 and holdout 2024 require explicit
stage flags and are rejected unless the previous stage result has PASS status.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import binomtest

from atas_cache_decoder import (
    CACHE_RECORD_DTYPE,
    CacheContext,
    load_cache_window,
)


NY = ZoneInfo("America/New_York")
TICKS_PER_SECOND = 10_000_000

BRANCH_VACUUM = "VACUUM_CONTINUATION"
BRANCH_REFILL = "REFILL_ABSORPTION_FADE"
BRANCHES = (BRANCH_VACUUM, BRANCH_REFILL)

STAGE_DATES = {
    "discovery": (date(2022, 4, 4), date(2022, 12, 30)),
    "validation": (date(2023, 1, 3), date(2023, 12, 29)),
    "holdout": (date(2024, 1, 2), date(2024, 12, 31)),
}


@dataclass(frozen=True)
class BranchDecision:
    branch: str
    signal_ticks: int
    side: str
    breach_side: str
    entry_trade_index: int
    or_high_raw: int
    or_low_raw: int
    breach_price_raw: int
    extreme_price_raw: int
    directional_volume: int
    total_volume: int
    directional_share: float
    impulse_trade_count: int
    advance_ticks: int
    max_retrace_ticks: int
    spread_ticks: int
    ahead_depth_3: int
    behind_depth_3: int
    baseline_ahead_3: float
    ahead_depth_ratio: float
    behind_ahead_ratio: float
    additions_ahead_250ms: int
    additions_ratio: float
    terminal_executed_volume: int
    terminal_refill_additions_250ms: int
    terminal_refill_ratio: float
    rejection_ticks: int


@dataclass(frozen=True)
class TradeResult:
    session_date: str
    branch: str
    side: str
    breach_side: str
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    stop_price: float
    target_price: float
    exit_price: float
    exit_reason: str
    net_ticks: float
    is_win: bool
    hold_seconds: float
    or_high: float
    or_low: float
    breach_price: float
    extreme_price: float
    directional_volume: int
    total_volume: int
    directional_share: float
    impulse_trade_count: int
    advance_ticks: int
    max_retrace_ticks: int
    spread_ticks: int
    ahead_depth_3: int
    behind_depth_3: int
    baseline_ahead_3: float
    ahead_depth_ratio: float
    behind_ahead_ratio: float
    additions_ahead_250ms: int
    additions_ratio: float
    terminal_executed_volume: int
    terminal_refill_additions_250ms: int
    terminal_refill_ratio: float
    rejection_ticks: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def datetime_to_dotnet_ticks(value: datetime) -> int:
    value = value.astimezone(timezone.utc)
    ordinal_days = value.date().toordinal() - 1
    day_ticks = (
        (value.hour * 3600 + value.minute * 60 + value.second)
        * TICKS_PER_SECOND
        + value.microsecond * 10
    )
    return ordinal_days * 86400 * TICKS_PER_SECOND + day_ticks


def dotnet_ticks_iso(ticks: int) -> str:
    seconds, remainder = divmod(int(ticks), TICKS_PER_SECOND)
    return (
        datetime(1, 1, 1, tzinfo=timezone.utc)
        + timedelta(seconds=seconds, microseconds=remainder // 10)
    ).isoformat()


def business_dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def session_bounds(session_date: date) -> dict[str, int]:
    def ny_ticks(clock: time) -> int:
        return datetime_to_dotnet_ticks(
            datetime.combine(session_date, clock, tzinfo=NY)
        )

    return {
        "load_start": ny_ticks(time(9, 4, 0)),
        "or_start": ny_ticks(time(9, 30, 0)),
        "or_end": ny_ticks(time(9, 35, 0)),
        "signal_end": ny_ticks(time(10, 30, 0)),
        "load_end": ny_ticks(time(10, 46, 0)),
    }


def safe_depth_prefix(depth: np.ndarray, decision_ticks: int) -> np.ndarray:
    """Return the causal file-order prefix without stepping over future depth."""

    future = np.flatnonzero(depth["ticks"] > decision_ticks)
    end = int(future[0]) if future.size else len(depth)
    return depth[:end]


def current_book(
    depth_prefix: np.ndarray,
    decision_ticks: int,
) -> tuple[dict[int, tuple[int, int]], dict[int, tuple[int, int]]] | None:
    recent = depth_prefix[
        depth_prefix["ticks"] >= decision_ticks - 2 * TICKS_PER_SECOND
    ]
    if recent.size == 0:
        return None

    keys = (
        recent["side_code"].astype(np.int64) << 32
    ) | recent["price_raw"].astype(np.uint32).astype(np.int64)
    _, reverse_indices = np.unique(keys[::-1], return_index=True)
    last_indices = len(recent) - 1 - reverse_indices
    rows = recent[last_indices]

    bids: dict[int, tuple[int, int]] = {}
    asks: dict[int, tuple[int, int]] = {}
    for row in rows:
        price = int(row["price_raw"])
        volume = int(row["volume_raw"])
        ticks = int(row["ticks"])
        if volume <= 0:
            continue
        if int(row["side_code"]) == 0:
            bids[price] = (volume, ticks)
        else:
            asks[price] = (volume, ticks)

    if len(bids) < 5 or len(asks) < 5:
        return None
    return bids, asks


def signed_max_retrace(prices: np.ndarray, breach_side: str) -> int:
    if prices.size <= 1:
        return 0
    if breach_side == "BUY":
        running_extreme = np.maximum.accumulate(prices)
        return int(np.max(running_extreme - prices))
    running_extreme = np.minimum.accumulate(prices)
    return int(np.max(prices - running_extreme))


def level_state_features(
    depth_prefix: np.ndarray,
    decision_ticks: int,
    ahead_keys: Sequence[tuple[int, int]],
    behind_keys: Sequence[tuple[int, int]],
    terminal_key: tuple[int, int],
) -> dict[str, float | int] | None:
    all_keys = list(ahead_keys) + list(behind_keys)
    unique_keys = list(dict.fromkeys(all_keys + [terminal_key]))
    relevant = np.zeros(len(depth_prefix), dtype=bool)
    for side_code, price_raw in unique_keys:
        relevant |= (depth_prefix["side_code"] == side_code) & (
            depth_prefix["price_raw"] == price_raw
        )
    rows = depth_prefix[relevant]
    if rows.size == 0:
        return None

    window_start = decision_ticks - 32 * TICKS_PER_SECOND
    rows = rows[rows["ticks"] >= window_start]
    if rows.size == 0:
        return None

    state: dict[tuple[int, int], tuple[int, int]] = {}
    pointer = 0
    ahead_samples: list[int] = []
    sample_times = range(
        decision_ticks - 30 * TICKS_PER_SECOND,
        decision_ticks,
        TICKS_PER_SECOND,
    )
    for sample_ticks in sample_times:
        while pointer < len(rows) and int(rows[pointer]["ticks"]) <= sample_ticks:
            row = rows[pointer]
            key = (int(row["side_code"]), int(row["price_raw"]))
            state[key] = (int(row["volume_raw"]), int(row["ticks"]))
            pointer += 1

        valid = True
        ahead_sum = 0
        for key in ahead_keys:
            value = state.get(key)
            if (
                value is None
                or value[0] <= 0
                or value[1] < sample_ticks - 2 * TICKS_PER_SECOND
            ):
                valid = False
                break
            ahead_sum += value[0]
        if valid:
            ahead_samples.append(ahead_sum)

    if len(ahead_samples) < 15:
        return None

    while pointer < len(rows) and int(rows[pointer]["ticks"]) <= decision_ticks:
        row = rows[pointer]
        key = (int(row["side_code"]), int(row["price_raw"]))
        state[key] = (int(row["volume_raw"]), int(row["ticks"]))
        pointer += 1

    ahead_depth = 0
    behind_depth = 0
    for key in ahead_keys:
        value = state.get(key)
        if (
            value is None
            or value[0] <= 0
            or value[1] < decision_ticks - 2 * TICKS_PER_SECOND
        ):
            return None
        ahead_depth += value[0]
    for key in behind_keys:
        value = state.get(key)
        if (
            value is None
            or value[0] <= 0
            or value[1] < decision_ticks - 2 * TICKS_PER_SECOND
        ):
            return None
        behind_depth += value[0]

    additions_by_key: Counter[tuple[int, int]] = Counter()
    prior_volume: dict[tuple[int, int], int] = {}
    add_start = decision_ticks - 250 * 10_000
    for row in rows:
        row_ticks = int(row["ticks"])
        if row_ticks > decision_ticks:
            break
        key = (int(row["side_code"]), int(row["price_raw"]))
        new_volume = int(row["volume_raw"])
        old_volume = prior_volume.get(key)
        if old_volume is not None and row_ticks >= add_start and new_volume > old_volume:
            additions_by_key[key] += new_volume - old_volume
        prior_volume[key] = new_volume

    return {
        "ahead_depth": ahead_depth,
        "behind_depth": behind_depth,
        "baseline_ahead": float(statistics.median(ahead_samples)),
        "additions_ahead": sum(additions_by_key[key] for key in ahead_keys),
        "terminal_additions": additions_by_key[terminal_key],
        "valid_baseline_snapshots": len(ahead_samples),
    }


def find_breach(
    trades: np.ndarray,
    bounds: dict[str, int],
) -> tuple[int, str, int, int] | None:
    or_mask = (trades["ticks"] >= bounds["or_start"]) & (
        trades["ticks"] < bounds["or_end"]
    )
    or_rows = trades[or_mask]
    if len(or_rows) < 100:
        return None
    or_high = int(np.max(or_rows["price_raw"]))
    or_low = int(np.min(or_rows["price_raw"]))

    signal_indices = np.flatnonzero(
        (trades["ticks"] >= bounds["or_end"])
        & (trades["ticks"] < bounds["signal_end"])
        & (
            (trades["price_raw"] >= or_high + 4)
            | (trades["price_raw"] <= or_low - 4)
        )
    )
    if signal_indices.size == 0:
        return None
    index = int(signal_indices[0])
    side = "BUY" if int(trades[index]["price_raw"]) >= or_high + 4 else "SELL"
    return index, side, or_high, or_low


def evaluate_branches(
    trades: np.ndarray,
    depth: np.ndarray,
    breach: tuple[int, str, int, int],
) -> tuple[dict[str, BranchDecision], str]:
    breach_index, breach_side, or_high, or_low = breach
    breach_ticks = int(trades[breach_index]["ticks"])
    window_start = breach_ticks - 500 * 10_000
    start_index = int(np.searchsorted(trades["ticks"], window_start, side="left"))
    impulse = trades[start_index : breach_index + 1]
    if len(impulse) < 20:
        return {}, "COMMON_LT20_TRADES"

    direction_code = 1 if breach_side == "BUY" else 2
    directional_volume = int(
        np.sum(impulse["volume_raw"][impulse["side_code"] == direction_code])
    )
    total_volume = int(np.sum(impulse["volume_raw"]))
    directional_share = directional_volume / total_volume if total_volume else 0.0
    if directional_volume < 60:
        return {}, "COMMON_VOLUME_LT60"
    if directional_share < 0.75:
        return {}, "COMMON_SHARE_LT075"

    prices = impulse["price_raw"].astype(np.int64)
    sign = 1 if breach_side == "BUY" else -1
    advance_ticks = int(sign * (prices[-1] - prices[0]))
    max_retrace = signed_max_retrace(prices, breach_side)
    extreme_price = int(np.max(prices) if breach_side == "BUY" else np.min(prices))

    depth_prefix = safe_depth_prefix(depth, breach_ticks)
    book = current_book(depth_prefix, breach_ticks)
    if book is None:
        return {}, "COMMON_BOOK_NO_DATA"
    bids, asks = book
    best_bid = max(bids)
    best_ask = min(asks)
    spread_ticks = best_ask - best_bid
    if spread_ticks < 1 or spread_ticks > 2:
        return {}, "COMMON_SPREAD_OUTSIDE_1_2"

    if breach_side == "BUY":
        ahead_keys = [(1, best_ask + offset) for offset in range(3)]
        behind_keys = [(0, best_bid - offset) for offset in range(3)]
        terminal_key = (1, extreme_price)
    else:
        ahead_keys = [(0, best_bid - offset) for offset in range(3)]
        behind_keys = [(1, best_ask + offset) for offset in range(3)]
        terminal_key = (0, extreme_price)

    level_features = level_state_features(
        depth_prefix,
        breach_ticks,
        ahead_keys,
        behind_keys,
        terminal_key,
    )
    if level_features is None:
        return {}, "COMMON_LEVELS_OR_BASELINE_NO_DATA"

    ahead_depth = int(level_features["ahead_depth"])
    behind_depth = int(level_features["behind_depth"])
    baseline_ahead = float(level_features["baseline_ahead"])
    additions_ahead = int(level_features["additions_ahead"])
    terminal_additions = int(level_features["terminal_additions"])
    ahead_ratio = ahead_depth / baseline_ahead if baseline_ahead > 0 else math.inf
    behind_ahead_ratio = behind_depth / max(ahead_depth, 1)
    additions_ratio = additions_ahead / directional_volume
    terminal_executed = int(
        np.sum(
            impulse["volume_raw"][
                (impulse["side_code"] == direction_code)
                & (impulse["price_raw"] == extreme_price)
            ]
        )
    )
    terminal_refill_ratio = (
        terminal_additions / terminal_executed
        if terminal_executed > 0
        else math.inf
    )

    decisions: dict[str, BranchDecision] = {}
    if (
        advance_ticks >= 4
        and max_retrace <= 2
        and ahead_ratio <= 0.35
        and behind_ahead_ratio >= 2.0
        and additions_ratio <= 0.25
        and breach_index + 1 < len(trades)
    ):
        decisions[BRANCH_VACUUM] = BranchDecision(
            branch=BRANCH_VACUUM,
            signal_ticks=breach_ticks,
            side=breach_side,
            breach_side=breach_side,
            entry_trade_index=breach_index + 1,
            or_high_raw=or_high,
            or_low_raw=or_low,
            breach_price_raw=int(trades[breach_index]["price_raw"]),
            extreme_price_raw=extreme_price,
            directional_volume=directional_volume,
            total_volume=total_volume,
            directional_share=directional_share,
            impulse_trade_count=len(impulse),
            advance_ticks=advance_ticks,
            max_retrace_ticks=max_retrace,
            spread_ticks=spread_ticks,
            ahead_depth_3=ahead_depth,
            behind_depth_3=behind_depth,
            baseline_ahead_3=baseline_ahead,
            ahead_depth_ratio=ahead_ratio,
            behind_ahead_ratio=behind_ahead_ratio,
            additions_ahead_250ms=additions_ahead,
            additions_ratio=additions_ratio,
            terminal_executed_volume=terminal_executed,
            terminal_refill_additions_250ms=terminal_additions,
            terminal_refill_ratio=terminal_refill_ratio,
            rejection_ticks=0,
        )

    if (
        advance_ticks <= 2
        and ahead_ratio >= 1.50
        and terminal_executed > 0
        and terminal_refill_ratio >= 1.0
    ):
        reject_end = breach_ticks + TICKS_PER_SECOND
        post_end = int(np.searchsorted(trades["ticks"], reject_end, side="right"))
        post = trades[breach_index + 1 : post_end]
        rejection_index: int | None = None
        rejection_ticks = 0
        running_extreme = extreme_price
        for relative_index, row in enumerate(post):
            price = int(row["price_raw"])
            if breach_side == "BUY":
                running_extreme = max(running_extreme, price)
                rejection_ticks = running_extreme - price
            else:
                running_extreme = min(running_extreme, price)
                rejection_ticks = price - running_extreme
            if rejection_ticks >= 3:
                rejection_index = breach_index + 1 + relative_index
                break
        if rejection_index is not None and rejection_index + 1 < len(trades):
            fade_side = "SELL" if breach_side == "BUY" else "BUY"
            decisions[BRANCH_REFILL] = BranchDecision(
                branch=BRANCH_REFILL,
                signal_ticks=int(trades[rejection_index]["ticks"]),
                side=fade_side,
                breach_side=breach_side,
                entry_trade_index=rejection_index + 1,
                or_high_raw=or_high,
                or_low_raw=or_low,
                breach_price_raw=int(trades[breach_index]["price_raw"]),
                extreme_price_raw=running_extreme,
                directional_volume=directional_volume,
                total_volume=total_volume,
                directional_share=directional_share,
                impulse_trade_count=len(impulse),
                advance_ticks=advance_ticks,
                max_retrace_ticks=max_retrace,
                spread_ticks=spread_ticks,
                ahead_depth_3=ahead_depth,
                behind_depth_3=behind_depth,
                baseline_ahead_3=baseline_ahead,
                ahead_depth_ratio=ahead_ratio,
                behind_ahead_ratio=behind_ahead_ratio,
                additions_ahead_250ms=additions_ahead,
                additions_ratio=additions_ratio,
                terminal_executed_volume=terminal_executed,
                terminal_refill_additions_250ms=terminal_additions,
                terminal_refill_ratio=terminal_refill_ratio,
                rejection_ticks=rejection_ticks,
            )

    if decisions:
        return decisions, "SIGNAL"
    return {}, "BRANCH_GATES_FAIL"


def simulate_trade(
    session_date: date,
    context: CacheContext,
    trades: np.ndarray,
    decision: BranchDecision,
) -> TradeResult:
    entry_index = decision.entry_trade_index
    entry_row = trades[entry_index]
    direction = 1 if decision.side == "BUY" else -1
    entry_raw = int(entry_row["price_raw"]) + direction
    stop_raw = entry_raw - direction * 20
    target_raw = entry_raw + direction * 26
    entry_ticks = int(entry_row["ticks"])
    timeout_ticks = entry_ticks + 15 * 60 * TICKS_PER_SECOND

    exit_ticks = int(trades[-1]["ticks"])
    exit_raw = int(trades[-1]["price_raw"]) - direction
    exit_reason = "TIMEOUT"
    for row in trades[entry_index + 1 :]:
        row_ticks = int(row["ticks"])
        price_raw = int(row["price_raw"])
        if row_ticks > timeout_ticks:
            exit_ticks = row_ticks
            exit_raw = price_raw - direction
            exit_reason = "TIMEOUT"
            break
        if direction == 1:
            if price_raw <= stop_raw:
                exit_ticks = row_ticks
                exit_raw = stop_raw - 1
                exit_reason = "SL"
                break
            if price_raw >= target_raw:
                exit_ticks = row_ticks
                exit_raw = target_raw - 1
                exit_reason = "TP"
                break
        else:
            if price_raw >= stop_raw:
                exit_ticks = row_ticks
                exit_raw = stop_raw + 1
                exit_reason = "SL"
                break
            if price_raw <= target_raw:
                exit_ticks = row_ticks
                exit_raw = target_raw + 1
                exit_reason = "TP"
                break

    gross_ticks = direction * (exit_raw - entry_raw)
    net_ticks = gross_ticks - 0.5
    scale = context.tick_size
    return TradeResult(
        session_date=session_date.isoformat(),
        branch=decision.branch,
        side=decision.side,
        breach_side=decision.breach_side,
        signal_time_utc=dotnet_ticks_iso(decision.signal_ticks),
        entry_time_utc=dotnet_ticks_iso(entry_ticks),
        exit_time_utc=dotnet_ticks_iso(exit_ticks),
        entry_price=entry_raw * scale,
        stop_price=stop_raw * scale,
        target_price=target_raw * scale,
        exit_price=exit_raw * scale,
        exit_reason=exit_reason,
        net_ticks=net_ticks,
        is_win=net_ticks > 0,
        hold_seconds=(exit_ticks - entry_ticks) / TICKS_PER_SECOND,
        or_high=decision.or_high_raw * scale,
        or_low=decision.or_low_raw * scale,
        breach_price=decision.breach_price_raw * scale,
        extreme_price=decision.extreme_price_raw * scale,
        directional_volume=decision.directional_volume,
        total_volume=decision.total_volume,
        directional_share=decision.directional_share,
        impulse_trade_count=decision.impulse_trade_count,
        advance_ticks=decision.advance_ticks,
        max_retrace_ticks=decision.max_retrace_ticks,
        spread_ticks=decision.spread_ticks,
        ahead_depth_3=decision.ahead_depth_3,
        behind_depth_3=decision.behind_depth_3,
        baseline_ahead_3=decision.baseline_ahead_3,
        ahead_depth_ratio=decision.ahead_depth_ratio,
        behind_ahead_ratio=decision.behind_ahead_ratio,
        additions_ahead_250ms=decision.additions_ahead_250ms,
        additions_ratio=decision.additions_ratio,
        terminal_executed_volume=decision.terminal_executed_volume,
        terminal_refill_additions_250ms=decision.terminal_refill_additions_250ms,
        terminal_refill_ratio=decision.terminal_refill_ratio,
        rejection_ticks=decision.rejection_ticks,
    )


def wilson_lower(wins: int, total: int, z: float = 1.959963984540054) -> float:
    if total == 0:
        return 0.0
    p = wins / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return (centre - margin) / denominator


def basic_metrics(trades: Sequence[TradeResult], months: int) -> dict[str, object]:
    total = len(trades)
    wins = sum(t.is_win for t in trades)
    losses = total - wins
    positive = [t.net_ticks for t in trades if t.net_ticks > 0]
    negative = [t.net_ticks for t in trades if t.net_ticks < 0]
    avg_win = statistics.mean(positive) if positive else 0.0
    avg_loss = abs(statistics.mean(negative)) if negative else 0.0
    payoff = avg_win / avg_loss if avg_loss > 0 else math.inf if avg_win > 0 else 0.0
    gross_profit = sum(positive)
    gross_loss = abs(sum(negative))
    pf = gross_profit / gross_loss if gross_loss > 0 else math.inf if gross_profit > 0 else 0.0
    ev = statistics.mean([t.net_ticks for t in trades]) if trades else 0.0
    pvalue = (
        float(binomtest(wins, total, 0.5, alternative="greater").pvalue)
        if total
        else 1.0
    )
    monthly = Counter(t.session_date[:7] for t in trades)
    return {
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total if total else 0.0,
        "trades_per_month": total / months,
        "average_win_ticks": avg_win,
        "average_loss_ticks": avg_loss,
        "realized_payoff": payoff,
        "net_ticks": sum(t.net_ticks for t in trades),
        "ev_ticks": ev,
        "profit_factor": pf,
        "wilson_lower_95": wilson_lower(wins, total),
        "binomial_p_one_sided": pvalue,
        "monthly_trades": dict(sorted(monthly.items())),
        "exit_reasons": dict(sorted(Counter(t.exit_reason for t in trades).items())),
    }


def branch_metrics(
    trades: Sequence[TradeResult],
    months: int,
    adjusted_p: float,
) -> dict[str, object]:
    metrics = basic_metrics(trades, months)
    midpoint = len(trades) // 2
    h1 = basic_metrics(trades[:midpoint], months=max(1, months // 2))
    h2 = basic_metrics(trades[midpoint:], months=max(1, months - months // 2))
    gates = {
        "n_ge_36": metrics["trades"] >= 36,
        "frequency_ge_4": metrics["trades_per_month"] >= 4.0,
        "win_rate_ge_80": metrics["win_rate"] >= 0.80,
        "payoff_ge_1": metrics["realized_payoff"] >= 1.0,
        "ev_positive": metrics["ev_ticks"] > 0,
        "pf_gt_1": metrics["profit_factor"] > 1.0,
        "h1_wr_ge_75": h1["win_rate"] >= 0.75,
        "h2_wr_ge_75": h2["win_rate"] >= 0.75,
        "h1_ev_positive": h1["ev_ticks"] > 0,
        "h2_ev_positive": h2["ev_ticks"] > 0,
        "wilson_lower_ge_65": metrics["wilson_lower_95"] >= 0.65,
        "holm_p_lt_005": adjusted_p < 0.05,
    }
    return {
        **metrics,
        "holm_adjusted_p": adjusted_p,
        "h1": h1,
        "h2": h2,
        "gates": gates,
        "pass": all(gates.values()),
    }


def holm_adjusted_pvalues(raw: dict[str, float]) -> dict[str, float]:
    ordered = sorted(raw, key=raw.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, name in enumerate(ordered):
        candidate = min(1.0, raw[name] * (count - rank))
        running = max(running, candidate)
        adjusted[name] = running
    return adjusted


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def previous_stage_pass(output_root: Path, stage: str) -> bool:
    required = {"validation": "discovery", "holdout": "validation"}.get(stage)
    if required is None:
        return True
    result_path = output_root / required / "result.json"
    if not result_path.is_file():
        return False
    result = json.loads(result_path.read_text(encoding="utf-8"))
    return bool(result.get("pass"))


def run_stage(
    cache_root: Path,
    output_root: Path,
    stage: str,
    limit: int | None = None,
) -> dict[str, object]:
    start_date, end_date = STAGE_DATES[stage]
    stage_output = output_root / stage
    stage_output.mkdir(parents=True, exist_ok=True)

    trades_out: list[TradeResult] = []
    session_rows: list[dict[str, object]] = []
    rejection_counts: Counter[str] = Counter()
    expected_sessions = list(business_dates(start_date, end_date))
    if limit is not None:
        expected_sessions = expected_sessions[:limit]

    for ordinal, session_date in enumerate(expected_sessions, start=1):
        source_date = session_date - timedelta(days=1)
        source_dir = cache_root / source_date.strftime("%Y_%m_%d")
        trade_path = source_dir / "trades.dat"
        depth_path = source_dir / "marketdepth.dat"
        session_record: dict[str, object] = {
            "session_date": session_date.isoformat(),
            "source_folder": source_dir.name,
            "status": "",
            "reason": "",
            "trade_rows": 0,
            "depth_rows": 0,
            "signals": "",
        }

        if not trade_path.is_file() or not depth_path.is_file():
            session_record.update(status="EXCLUDED", reason="MISSING_SOURCE")
            rejection_counts["MISSING_SOURCE"] += 1
            session_rows.append(session_record)
            continue

        bounds = session_bounds(session_date)
        try:
            trade_context, trade_rows = load_cache_window(
                trade_path,
                start_ticks=bounds["load_start"],
                end_ticks=bounds["load_end"],
            )
            depth_context, depth_rows = load_cache_window(
                depth_path,
                start_ticks=bounds["load_start"],
                end_ticks=bounds["signal_end"] + TICKS_PER_SECOND,
            )
            if (
                not math.isclose(trade_context.tick_size, 0.25)
                or not math.isclose(depth_context.tick_size, 0.25)
                or not math.isclose(trade_context.lot_size, 1.0)
                or not math.isclose(depth_context.lot_size, 1.0)
            ):
                raise ValueError("Unexpected NQ tick/lot scale")
            if len(trade_rows) == 0 or len(depth_rows) == 0:
                raise ValueError("Empty cash-session window")
            if np.any(np.diff(trade_rows["ticks"]) < 0):
                raise ValueError("Trade timestamps are not monotonic")
        except Exception as exc:
            session_record.update(
                status="EXCLUDED",
                reason=f"INTEGRITY:{type(exc).__name__}:{exc}",
            )
            rejection_counts["INTEGRITY"] += 1
            session_rows.append(session_record)
            continue

        session_record["trade_rows"] = len(trade_rows)
        session_record["depth_rows"] = len(depth_rows)
        breach = find_breach(trade_rows, bounds)
        if breach is None:
            session_record.update(status="NO_SIGNAL", reason="NO_VALID_OR_OR_BREACH")
            rejection_counts["NO_VALID_OR_OR_BREACH"] += 1
            session_rows.append(session_record)
            continue

        decisions, reason = evaluate_branches(trade_rows, depth_rows, breach)
        rejection_counts[reason] += 1
        if not decisions:
            session_record.update(status="NO_SIGNAL", reason=reason)
            session_rows.append(session_record)
            continue

        day_trades: list[TradeResult] = []
        for branch in BRANCHES:
            decision = decisions.get(branch)
            if decision is None:
                continue
            result = simulate_trade(
                session_date,
                trade_context,
                trade_rows,
                decision,
            )
            day_trades.append(result)
            trades_out.append(result)
        session_record.update(
            status="TRADE",
            reason="SIGNAL",
            signals="|".join(t.branch for t in day_trades),
        )
        session_rows.append(session_record)

        if ordinal % 10 == 0:
            print(
                json.dumps(
                    {
                        "progress": ordinal,
                        "total": len(expected_sessions),
                        "trades": len(trades_out),
                        "last_date": session_date.isoformat(),
                    }
                ),
                flush=True,
            )

    months = (
        (end_date.year - start_date.year) * 12
        + end_date.month
        - start_date.month
        + 1
    )
    by_branch = {
        branch: [trade for trade in trades_out if trade.branch == branch]
        for branch in BRANCHES
    }
    raw_p = {
        branch: float(
            binomtest(
                sum(t.is_win for t in branch_trades),
                len(branch_trades),
                0.5,
                alternative="greater",
            ).pvalue
        )
        if branch_trades
        else 1.0
        for branch, branch_trades in by_branch.items()
    }
    adjusted_p = holm_adjusted_pvalues(raw_p)
    metrics = {
        branch: branch_metrics(branch_trades, months, adjusted_p[branch])
        for branch, branch_trades in by_branch.items()
    }
    stage_pass = any(metric["pass"] for metric in metrics.values())

    result = {
        "strategy": "V51_OR5_DEPTH_BIFURCATION",
        "stage": stage,
        "date_range": [start_date.isoformat(), end_date.isoformat()],
        "sessions_expected": len(expected_sessions),
        "sessions_processed": len(session_rows),
        "sessions_excluded": sum(r["status"] == "EXCLUDED" for r in session_rows),
        "total_trades": len(trades_out),
        "branches": metrics,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "pass": stage_pass,
        "validation_opened": stage in ("validation", "holdout"),
        "holdout_opened": stage == "holdout",
        "visual_logic_modified": False,
    }

    write_csv(stage_output / "trades.csv", [asdict(row) for row in trades_out])
    write_csv(stage_output / "sessions.csv", session_rows)
    (stage_output / "result.json").write_text(
        json.dumps(result, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    result["artifacts"] = {
        name: sha256_file(stage_output / name)
        for name in ("trades.csv", "sessions.csv", "result.json")
    }
    (stage_output / "manifest.json").write_text(
        json.dumps(result["artifacts"], indent=2),
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\AppData\Roaming\ATAS\Cache_v2\NQ@CME_Ind"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent
        / "lucid150k_visual_logic_80_v51_or5_depth_bifurcation",
    )
    parser.add_argument(
        "--stage",
        choices=tuple(STAGE_DATES),
        default="discovery",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if not args.cache_root.is_dir():
        parser.error(f"Cache root not found: {args.cache_root}")
    if args.stage != "discovery" and not previous_stage_pass(
        args.output_root, args.stage
    ):
        parser.error(
            f"{args.stage} is sealed because the previous stage has no PASS result"
        )

    result = run_stage(
        args.cache_root,
        args.output_root,
        args.stage,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
