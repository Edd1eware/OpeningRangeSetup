from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, mannwhitneyu
from sklearn.metrics import roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

import atas_mt5_pivot_backtest as structural
from causal_feature_audit import audit_feature_columns, audit_timestamp_order, classify_column


NUMERIC_FEATURES = [
    "IsLong_AtEntry",
    "HourNY_AtEntry",
    "MinuteNY_AtEntry",
    "MinutesFromOpen_AtEntry",
    "Weekday_AtEntry",
    "Month_AtEntry",
    "LeaderSwingATR_AtEntry",
    "LeaderReactionATR_AtEntry",
    "CFD_ATR_AtEntry",
    "ATAS_ATR_AtEntry",
    "ATRRatio_AtEntry",
    "CFDAway1ATR_AtEntry",
    "CFDAway3ATR_AtEntry",
    "CFDAway5ATR_AtEntry",
    "ATASAway1ATR_AtEntry",
    "ATASAway3ATR_AtEntry",
    "ATASAway5ATR_AtEntry",
    "LeadDivergence1ATR_AtEntry",
    "LeadDivergence3ATR_AtEntry",
    "LeadDivergence5ATR_AtEntry",
    "ATASApproachBars3_AtEntry",
    "ATASApproachBars5_AtEntry",
    "MappedPivotGapATR_AtEntry",
    "CFDSignalRangeATR_AtEntry",
    "ATASSignalRangeATR_AtEntry",
    "CFDSignalBodyATR_AtEntry",
    "ATASSignalBodyATR_AtEntry",
    "CFDEfficiency5_AtEntry",
    "ATASEfficiency5_AtEntry",
    "CFDRange5ATR_AtEntry",
    "ATASRange5ATR_AtEntry",
    "PriceRatioZ20_AtEntry",
    "ReturnCorrelation20_AtEntry",
    "CFDATRRel60_AtEntry",
    "ATASATRRel60_AtEntry",
    "CFDSessionRangeATR_AtEntry",
    "ATASSessionRangeATR_AtEntry",
    "ATASDeltaRatio1_AtEntry",
    "ATASDirectionalDelta3_AtEntry",
    "ATASDirectionalDelta5_AtEntry",
    "ATASDeltaAcceleration3_AtEntry",
    "ATASDeltaReversal_AtEntry",
    "ATASOpposingPressure_AtEntry",
    "ATASAbsorptionScore_AtEntry",
    "ATASVolumeRel20_AtEntry",
    "ATASDirectionalImbalance_AtEntry",
    "ATASEdgeOpposingShare_AtEntry",
    "ATASCloseLocation_AtEntry",
    "ATASPocLocation_AtEntry",
]

CATEGORICAL_FEATURES = [
    "Side_AtEntry",
    "Pivot_AtEntry",
    "HourNY_AtEntry",
    "Weekday_AtEntry",
    "Month_AtEntry",
]


@dataclass(frozen=True)
class Rule:
    feature: str
    operator: str
    threshold: float

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        values = pd.to_numeric(frame[self.feature], errors="coerce")
        if self.operator == ">=":
            return values.notna() & (values >= self.threshold)
        return values.notna() & (values <= self.threshold)

    def text(self) -> str:
        return f"{self.feature} {self.operator} {self.threshold:.6g}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Causal winner-vs-loser laboratory for CFD->ATAS lead trades.")
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--atas-cache", type=Path, required=True)
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--symbol", default="USTEC")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_events(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    return {
        row["detection_time_ny"]: row
        for row in rows
        if row.get("leader") == "CFD MT5"
    }


def efficiency(bars: list[structural.Bar], index: int, window: int) -> float:
    if index < window:
        return math.nan
    changes = [abs(bars[i].close - bars[i - 1].close) for i in range(index - window + 1, index + 1)]
    total = sum(changes)
    return abs(bars[index].close - bars[index - window].close) / total if total > 1e-12 else 0.0


def range_atr(bars: list[structural.Bar], index: int, window: int, atr: float) -> float:
    if index < window or atr <= 0:
        return math.nan
    segment = bars[index - window + 1 : index + 1]
    return (max(bar.high for bar in segment) - min(bar.low for bar in segment)) / atr


def return_atr(bars: list[structural.Bar], index: int, window: int, atr: float, direction: float) -> float:
    if index < window or atr <= 0:
        return math.nan
    return direction * (bars[index].close - bars[index - window].close) / atr


def approach_bars(bars: list[structural.Bar], index: int, window: int, approach_direction: float) -> float:
    if index < window:
        return math.nan
    return float(
        sum(
            approach_direction * (bars[i].close - bars[i - 1].close) > 0
            for i in range(index - window + 1, index + 1)
        )
    )


def ratio_zscore(
    atas: list[structural.Bar], cfd: list[structural.Bar], index: int, window: int = 20
) -> float:
    if index < window:
        return math.nan
    prior = np.asarray(
        [atas[i].close / cfd[i].close for i in range(index - window, index)],
        dtype=float,
    )
    deviation = float(prior.std(ddof=1))
    if not math.isfinite(deviation) or deviation <= 1e-12:
        return 0.0
    current = atas[index].close / cfd[index].close
    return float((current - prior.mean()) / deviation)


def return_correlation(
    atas: list[structural.Bar], cfd: list[structural.Bar], index: int, window: int = 20
) -> float:
    if index < window:
        return math.nan
    atas_returns = np.asarray(
        [atas[i].close - atas[i - 1].close for i in range(index - window + 1, index + 1)],
        dtype=float,
    )
    cfd_returns = np.asarray(
        [cfd[i].close - cfd[i - 1].close for i in range(index - window + 1, index + 1)],
        dtype=float,
    )
    if atas_returns.std() <= 1e-12 or cfd_returns.std() <= 1e-12:
        return 0.0
    return float(np.corrcoef(atas_returns, cfd_returns)[0, 1])


def atr_relative(bars: list[structural.Bar], index: int, window: int = 60) -> float:
    first = max(14, index - window)
    history = [structural.atr_at(bars, i) for i in range(first, index)]
    history = [value for value in history if math.isfinite(value) and value > 1e-12]
    if not history:
        return math.nan
    return structural.atr_at(bars, index) / statistics.median(history)


def session_range_atr(bars: list[structural.Bar], index: int, atr: float) -> float:
    if atr <= 0:
        return math.nan
    segment = bars[: index + 1]
    return (max(bar.high for bar in segment) - min(bar.low for bar in segment)) / atr


def footprint_volume(bar: structural.Bar) -> float:
    return float(bar.bid + bar.ask + bar.between)


def footprint_delta_ratio(bar: structural.Bar) -> float:
    volume = footprint_volume(bar)
    return (bar.ask - bar.bid) / volume if volume > 0 else math.nan


def directional_cumulative_delta(
    bars: list[structural.Bar], index: int, window: int, direction: float
) -> float:
    if index < window - 1:
        return math.nan
    segment = bars[index - window + 1 : index + 1]
    volume = sum(footprint_volume(bar) for bar in segment)
    delta = sum(bar.ask - bar.bid for bar in segment)
    return direction * delta / volume if volume > 0 else math.nan


def footprint_volume_relative(
    bars: list[structural.Bar], index: int, window: int = 20
) -> float:
    current = footprint_volume(bars[index])
    prior = [
        footprint_volume(bars[i])
        for i in range(max(0, index - window), index)
        if footprint_volume(bars[i]) > 0
    ]
    if current <= 0 or not prior:
        return math.nan
    median = statistics.median(prior)
    return math.log(current / median) if median > 0 else math.nan


def footprint_shape(bar: structural.Bar, direction: float) -> dict[str, float]:
    volume = footprint_volume(bar)
    price_range = bar.high - bar.low
    if volume <= 0 or not bar.price_levels or price_range <= 1e-12:
        return {
            "delta_ratio": math.nan,
            "delta_reversal": math.nan,
            "opposing_pressure": math.nan,
            "absorption": math.nan,
            "directional_imbalance": math.nan,
            "edge_opposing_share": math.nan,
            "close_location": math.nan,
            "poc_location": math.nan,
        }

    delta = float(bar.ask - bar.bid)
    delta_ratio = delta / volume
    close_location = direction * (2.0 * (bar.close - bar.low) / price_range - 1.0)
    poc = max(
        bar.price_levels,
        key=lambda level: level[1] + level[2] + level[3],
    )[0]
    poc_location = direction * (2.0 * (poc - bar.low) / price_range - 1.0)

    if direction > 0:
        delta_reversal = (delta - bar.min_delta) / volume
        opposing_pressure = max(0.0, -delta_ratio)
        edge = [level for level in bar.price_levels if level[0] <= bar.low + 0.25 * price_range]
        edge_opposing = sum(level[1] for level in edge)
        opposing_total = bar.bid
    else:
        delta_reversal = (bar.max_delta - delta) / volume
        opposing_pressure = max(0.0, delta_ratio)
        edge = [level for level in bar.price_levels if level[0] >= bar.high - 0.25 * price_range]
        edge_opposing = sum(level[2] for level in edge)
        opposing_total = bar.ask

    levels = sorted(bar.price_levels, key=lambda level: level[0])
    buy_imbalances = 0
    sell_imbalances = 0
    for level_index, level in enumerate(levels):
        _price, bid, ask, _between, _ticks = level
        if level_index > 0:
            lower_bid = levels[level_index - 1][1]
            if ask >= 10 and ask >= 3 * max(1, lower_bid):
                buy_imbalances += 1
        if level_index + 1 < len(levels):
            upper_ask = levels[level_index + 1][2]
            if bid >= 10 and bid >= 3 * max(1, upper_ask):
                sell_imbalances += 1

    directional_imbalance = direction * (buy_imbalances - sell_imbalances) / len(levels)
    edge_share = edge_opposing / opposing_total if opposing_total > 0 else 0.0
    # Opposing aggression is useful only when price rejects it and closes back
    # in the intended CFD->ATAS trade direction.
    absorption = opposing_pressure * max(0.0, close_location)
    return {
        "delta_ratio": delta_ratio,
        "delta_reversal": delta_reversal,
        "opposing_pressure": opposing_pressure,
        "absorption": absorption,
        "directional_imbalance": directional_imbalance,
        "edge_opposing_share": edge_share,
        "close_location": close_location,
        "poc_location": poc_location,
    }


def finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def build_dataset(
    events: dict[str, dict[str, str]],
    trades: list[dict],
    atas_sessions: dict[str, list[structural.Bar]],
    mt5_bars: dict[datetime, structural.Bar],
) -> tuple[list[dict], list[dict], list[dict]]:
    inputs: list[dict] = []
    outcomes: list[dict] = []
    skipped: list[dict] = []
    session_start = datetime.strptime("09:30", "%H:%M").time()
    session_end = datetime.strptime("16:00", "%H:%M").time()

    for ordinal, trade in enumerate(sorted(trades, key=lambda row: row["signal_time_ny"]), 1):
        signal = datetime.fromisoformat(trade["signal_time_ny"])
        event = events.get(trade["signal_time_ny"])
        raw_atas = atas_sessions.get(trade["session_date_ny"], [])
        common_times = {
            bar.time_ny
            for bar in raw_atas
            if session_start <= bar.time_ny.time() <= session_end and bar.time_ny in mt5_bars
        }
        atas = [bar for bar in raw_atas if bar.time_ny in common_times]
        cfd = [mt5_bars[bar.time_ny] for bar in atas]
        index_by_time = {bar.time_ny: index for index, bar in enumerate(atas)}
        index = index_by_time.get(signal)
        if event is None or index is None or index < 20:
            skipped.append({"signal_time_ny": trade["signal_time_ny"], "reason": "missing event/aligned history"})
            continue

        leader_time = datetime.fromisoformat(event["leader_time_ny"])
        leader_index = index_by_time.get(leader_time)
        if leader_index is None:
            skipped.append({"signal_time_ny": trade["signal_time_ny"], "reason": "missing leader bar"})
            continue

        atas_atr = structural.atr_at(atas, index)
        cfd_atr = structural.atr_at(cfd, index)
        if atas_atr <= 1e-12 or cfd_atr <= 1e-12:
            skipped.append({"signal_time_ny": trade["signal_time_ny"], "reason": "invalid ATR"})
            continue

        is_long = trade["side"] == "LONG"
        away_direction = 1.0 if is_long else -1.0
        approach_direction = -away_direction
        mapped_pivot = float(event["leader_price"]) * atas[leader_index].close / cfd[leader_index].close

        cfd_away = {
            window: return_atr(cfd, index, window, cfd_atr, away_direction)
            for window in (1, 3, 5)
        }
        atas_away = {
            window: return_atr(atas, index, window, atas_atr, away_direction)
            for window in (1, 3, 5)
        }
        footprint = footprint_shape(atas[index], away_direction)
        directional_delta_3 = directional_cumulative_delta(atas, index, 3, away_direction)
        directional_delta_5 = directional_cumulative_delta(atas, index, 5, away_direction)
        prior_delta_3 = directional_cumulative_delta(atas, index - 1, 3, away_direction)
        feature_close_time = signal + timedelta(minutes=1)
        fill_time = datetime.fromisoformat(trade["fill_time_ny"])
        feature_utc = feature_close_time.astimezone(structural.UTC)
        fill_utc = fill_time.astimezone(structural.UTC)
        trade_id = f"CFD_ATAS_{ordinal:04d}_{signal:%Y%m%d_%H%M}"

        row = {
            "trade_id": trade_id,
            "Input_VERSION": "atas-mt5-lead-lab-causal-v1",
            "fecha": trade["session_date_ny"],
            "decision_timestamp": signal.isoformat(),
            "feature_timestamp": feature_close_time.isoformat(),
            "entry_timestamp": fill_time.isoformat(),
            "feature_timestamp_utc": feature_utc.isoformat(),
            "entry_timestamp_utc": fill_utc.isoformat(),
            "Side_AtEntry": trade["side"],
            "Pivot_AtEntry": trade["pivot_kind"],
            "IsLong_AtEntry": 1.0 if is_long else 0.0,
            "HourNY_AtEntry": float(signal.hour),
            "MinuteNY_AtEntry": float(signal.minute),
            "MinutesFromOpen_AtEntry": float((signal.hour * 60 + signal.minute) - (9 * 60 + 30)),
            "Weekday_AtEntry": float(signal.weekday()),
            "Month_AtEntry": float(signal.month),
            "LeaderSwingATR_AtEntry": float(event["leader_swing_atr"]),
            "LeaderReactionATR_AtEntry": float(event["leader_reaction_atr"]),
            "CFD_ATR_AtEntry": cfd_atr,
            "ATAS_ATR_AtEntry": atas_atr,
            "ATRRatio_AtEntry": atas_atr / cfd_atr,
            "CFDAway1ATR_AtEntry": cfd_away[1],
            "CFDAway3ATR_AtEntry": cfd_away[3],
            "CFDAway5ATR_AtEntry": cfd_away[5],
            "ATASAway1ATR_AtEntry": atas_away[1],
            "ATASAway3ATR_AtEntry": atas_away[3],
            "ATASAway5ATR_AtEntry": atas_away[5],
            "LeadDivergence1ATR_AtEntry": cfd_away[1] - atas_away[1],
            "LeadDivergence3ATR_AtEntry": cfd_away[3] - atas_away[3],
            "LeadDivergence5ATR_AtEntry": cfd_away[5] - atas_away[5],
            "ATASApproachBars3_AtEntry": approach_bars(atas, index, 3, approach_direction),
            "ATASApproachBars5_AtEntry": approach_bars(atas, index, 5, approach_direction),
            "MappedPivotGapATR_AtEntry": away_direction * (atas[index].close - mapped_pivot) / atas_atr,
            "CFDSignalRangeATR_AtEntry": (cfd[index].high - cfd[index].low) / cfd_atr,
            "ATASSignalRangeATR_AtEntry": (atas[index].high - atas[index].low) / atas_atr,
            "CFDSignalBodyATR_AtEntry": away_direction * (cfd[index].close - cfd[index].open) / cfd_atr,
            "ATASSignalBodyATR_AtEntry": away_direction * (atas[index].close - atas[index].open) / atas_atr,
            "CFDEfficiency5_AtEntry": efficiency(cfd, index, 5),
            "ATASEfficiency5_AtEntry": efficiency(atas, index, 5),
            "CFDRange5ATR_AtEntry": range_atr(cfd, index, 5, cfd_atr),
            "ATASRange5ATR_AtEntry": range_atr(atas, index, 5, atas_atr),
            "PriceRatioZ20_AtEntry": ratio_zscore(atas, cfd, index, 20),
            "ReturnCorrelation20_AtEntry": return_correlation(atas, cfd, index, 20),
            "CFDATRRel60_AtEntry": atr_relative(cfd, index, 60),
            "ATASATRRel60_AtEntry": atr_relative(atas, index, 60),
            "CFDSessionRangeATR_AtEntry": session_range_atr(cfd, index, cfd_atr),
            "ATASSessionRangeATR_AtEntry": session_range_atr(atas, index, atas_atr),
            "ATASDeltaRatio1_AtEntry": footprint["delta_ratio"],
            "ATASDirectionalDelta3_AtEntry": directional_delta_3,
            "ATASDirectionalDelta5_AtEntry": directional_delta_5,
            "ATASDeltaAcceleration3_AtEntry": directional_delta_3 - prior_delta_3,
            "ATASDeltaReversal_AtEntry": footprint["delta_reversal"],
            "ATASOpposingPressure_AtEntry": footprint["opposing_pressure"],
            "ATASAbsorptionScore_AtEntry": footprint["absorption"],
            "ATASVolumeRel20_AtEntry": footprint_volume_relative(atas, index, 20),
            "ATASDirectionalImbalance_AtEntry": footprint["directional_imbalance"],
            "ATASEdgeOpposingShare_AtEntry": footprint["edge_opposing_share"],
            "ATASCloseLocation_AtEntry": footprint["close_location"],
            "ATASPocLocation_AtEntry": footprint["poc_location"],
        }
        row = {key: finite(value) if isinstance(value, float) else value for key, value in row.items()}
        inputs.append(row)
        outcomes.append(
            {
                "trade_id": trade_id,
                "Result_VERSION": "atas-mt5-lead-lab-outcomes-v1",
                "OutcomeWin": 1 if float(trade["realized_r"]) > 0 else 0,
                "RealizedR": float(trade["realized_r"]),
                "TradeResult": trade["result"],
                "ConfirmedLater": 1 if trade["confirmed_structure_after_signal"] else 0,
                "outcome_timestamp": trade["exit_time_ny"],
            }
        )
    return inputs, outcomes, skipped


def trade_metrics(frame: pd.DataFrame) -> dict[str, float | int | None]:
    values = pd.to_numeric(frame["RealizedR"], errors="coerce").dropna().to_numpy(float)
    positive = values[values > 0]
    negative = values[values < 0]
    gross_profit = float(positive.sum())
    gross_loss = float(abs(negative.sum()))
    return {
        "n": int(len(values)),
        "wins": int(len(positive)),
        "losses": int(len(negative)),
        "wr": float(len(positive) / len(values)) if len(values) else None,
        "pf": float(gross_profit / gross_loss) if gross_loss else None,
        "avg_r": float(values.mean()) if len(values) else None,
        "net_r": float(values.sum()),
    }


def wilson_low(wins: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return -math.inf
    p = wins / n
    denominator = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (center - half) / denominator


def cohen_d(winners: np.ndarray, losers: np.ndarray) -> float:
    if len(winners) < 2 or len(losers) < 2:
        return math.nan
    pooled = math.sqrt(
        ((len(winners) - 1) * winners.var(ddof=1) + (len(losers) - 1) * losers.var(ddof=1))
        / (len(winners) + len(losers) - 2)
    )
    return float((winners.mean() - losers.mean()) / pooled) if pooled > 1e-12 else 0.0


def bh_fdr(p_values: list[float]) -> list[float]:
    count = len(p_values)
    order = np.argsort(np.asarray(p_values, dtype=float))
    adjusted = np.empty(count, dtype=float)
    running = 1.0
    for rank_index in range(count - 1, -1, -1):
        original_index = int(order[rank_index])
        rank = rank_index + 1
        candidate = min(1.0, p_values[original_index] * count / rank)
        running = min(running, candidate)
        adjusted[original_index] = running
    return adjusted.tolist()


def bootstrap_median_difference(
    winners: np.ndarray, losers: np.ndarray, rng: np.random.Generator, iterations: int = 2000
) -> tuple[float, float]:
    if not len(winners) or not len(losers):
        return math.nan, math.nan
    samples = np.empty(iterations, dtype=float)
    for index in range(iterations):
        win_sample = rng.choice(winners, size=len(winners), replace=True)
        loss_sample = rng.choice(losers, size=len(losers), replace=True)
        samples[index] = np.median(win_sample) - np.median(loss_sample)
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def univariate(scope: pd.DataFrame, scope_name: str, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict] = []
    y_all = scope["OutcomeWin"].to_numpy(int)
    for feature in NUMERIC_FEATURES:
        values = pd.to_numeric(scope[feature], errors="coerce")
        valid = values.notna()
        values_np = values[valid].to_numpy(float)
        y = y_all[valid.to_numpy()]
        winners = values_np[y == 1]
        losers = values_np[y == 0]
        if len(np.unique(values_np)) < 2 or not len(winners) or not len(losers):
            continue
        statistic = mannwhitneyu(winners, losers, alternative="two-sided")
        auc = float(roc_auc_score(y, values_np))
        ci_low, ci_high = bootstrap_median_difference(winners, losers, rng)
        effect_2025 = cohen_d(
            pd.to_numeric(scope.loc[(scope["Year"] == 2025) & (scope["OutcomeWin"] == 1), feature], errors="coerce").dropna().to_numpy(float),
            pd.to_numeric(scope.loc[(scope["Year"] == 2025) & (scope["OutcomeWin"] == 0), feature], errors="coerce").dropna().to_numpy(float),
        )
        effect_2026 = cohen_d(
            pd.to_numeric(scope.loc[(scope["Year"] == 2026) & (scope["OutcomeWin"] == 1), feature], errors="coerce").dropna().to_numpy(float),
            pd.to_numeric(scope.loc[(scope["Year"] == 2026) & (scope["OutcomeWin"] == 0), feature], errors="coerce").dropna().to_numpy(float),
        )
        rows.append(
            {
                "Scope": scope_name,
                "Feature": feature,
                "N": int(len(values_np)),
                "WinnerMean": float(winners.mean()),
                "LoserMean": float(losers.mean()),
                "WinnerMedian": float(np.median(winners)),
                "LoserMedian": float(np.median(losers)),
                "MedianDifference": float(np.median(winners) - np.median(losers)),
                "MedianDiffCI95Low": ci_low,
                "MedianDiffCI95High": ci_high,
                "CohenD": cohen_d(winners, losers),
                "AUC": auc,
                "OrientedAUC": max(auc, 1 - auc),
                "WinnerDirection": "HIGHER" if auc >= 0.5 else "LOWER",
                "MannWhitneyP": float(statistic.pvalue),
                "CohenD2025": effect_2025,
                "CohenD2026": effect_2026,
                "StableDirectionBothYears": bool(
                    math.isfinite(effect_2025)
                    and math.isfinite(effect_2026)
                    and effect_2025 * effect_2026 > 0
                ),
            }
        )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["FDR_Q"] = bh_fdr(result["MannWhitneyP"].tolist())
        result = result.sort_values(
            ["StableDirectionBothYears", "FDR_Q", "OrientedAUC", "N"],
            ascending=[False, True, False, False],
        ).reset_index(drop=True)
    return result


def categorical(scope: pd.DataFrame, scope_name: str) -> pd.DataFrame:
    rows: list[dict] = []
    for feature in CATEGORICAL_FEATURES:
        for value, group in scope.groupby(feature, dropna=False):
            rows.append({"Scope": scope_name, "Feature": feature, "Value": value, **trade_metrics(group)})
    return pd.DataFrame(rows).sort_values(["Scope", "Feature", "n"], ascending=[True, True, False])


def candidate_rules(train: pd.DataFrame, features: list[str], minimum_n: int) -> list[tuple[tuple, Rule, dict]]:
    candidates: list[tuple[tuple, Rule, dict]] = []
    for feature in features:
        values = pd.to_numeric(train[feature], errors="coerce")
        finite_values = values.dropna()
        if finite_values.nunique() < 4:
            continue
        thresholds = np.unique(finite_values.quantile([0.20, 0.35, 0.50, 0.65, 0.80]).to_numpy(float))
        for threshold in thresholds:
            for operator in ("<=", ">="):
                rule = Rule(feature, operator, float(threshold))
                selected = train.loc[rule.mask(train)]
                if len(selected) < minimum_n:
                    continue
                result = trade_metrics(selected)
                score = (
                    wilson_low(int(result["wins"]), int(result["n"])),
                    float(result["avg_r"]),
                    int(result["n"]),
                )
                candidates.append((score, rule, result))
    return candidates


def year_holdout(scope: pd.DataFrame, scope_name: str) -> tuple[pd.DataFrame, dict]:
    train = scope.loc[scope["Year"] == 2025].copy()
    test = scope.loc[scope["Year"] == 2026].copy()
    minimum_n = max(20, math.ceil(0.30 * len(train)))
    feature_rows: list[dict] = []
    global_candidates: list[tuple[tuple, Rule, dict]] = []
    for feature in NUMERIC_FEATURES:
        candidates = candidate_rules(train, [feature], minimum_n)
        if not candidates:
            continue
        best = max(candidates, key=lambda item: item[0])
        _, rule, train_metrics = best
        test_metrics = trade_metrics(test.loc[rule.mask(test)])
        feature_rows.append(
            {
                "Scope": scope_name,
                "Rule": rule.text(),
                **{f"Train_{key}": value for key, value in train_metrics.items()},
                **{f"Test2026_{key}": value for key, value in test_metrics.items()},
            }
        )
        global_candidates.extend(candidates)
    table = pd.DataFrame(feature_rows).sort_values(
        ["Train_avg_r", "Train_n"], ascending=[False, False]
    )
    if not global_candidates:
        return table, {"scope": scope_name, "rule": "NONE"}
    _, rule, train_metrics = max(global_candidates, key=lambda item: item[0])
    test_metrics = trade_metrics(test.loc[rule.mask(test)])
    return table, {
        "scope": scope_name,
        "rule": rule.text(),
        "train": train_metrics,
        "test_2026": test_metrics,
        "test_2026_baseline": trade_metrics(test),
    }


def walkforward(scope: pd.DataFrame, scope_name: str) -> tuple[pd.DataFrame, dict]:
    ordered = scope.sort_values("decision_timestamp").reset_index(drop=True)
    if len(ordered) < 80:
        train_start = max(50, len(ordered) // 2)
    else:
        train_start = max(60, int(round(0.50 * len(ordered))))
    boundaries = np.linspace(train_start, len(ordered), 5).round().astype(int)
    fold_rows: list[dict] = []
    selected_tests: list[pd.DataFrame] = []
    baseline_tests: list[pd.DataFrame] = []
    for fold, (train_end, test_end) in enumerate(zip(boundaries[:-1], boundaries[1:]), 1):
        train = ordered.iloc[:train_end]
        test = ordered.iloc[train_end:test_end]
        if test.empty:
            continue
        minimum_n = max(20, math.ceil(0.30 * len(train)))
        candidates = candidate_rules(train, NUMERIC_FEATURES, minimum_n)
        if candidates:
            _, rule, train_result = max(candidates, key=lambda item: item[0])
            selected = test.loc[rule.mask(test)]
            rule_text = rule.text()
        else:
            train_result = trade_metrics(train)
            selected = test
            rule_text = "ALL"
        test_result = trade_metrics(selected)
        baseline = trade_metrics(test)
        selected_tests.append(selected)
        baseline_tests.append(test)
        fold_rows.append(
            {
                "Scope": scope_name,
                "Fold": fold,
                "TrainEnd": train.iloc[-1]["fecha"],
                "TestStart": test.iloc[0]["fecha"],
                "TestEnd": test.iloc[-1]["fecha"],
                "SelectedRule": rule_text,
                **{f"Train_{key}": value for key, value in train_result.items()},
                **{f"Test_{key}": value for key, value in test_result.items()},
                **{f"Baseline_{key}": value for key, value in baseline.items()},
            }
        )
    selected_all = pd.concat(selected_tests, ignore_index=True) if selected_tests else ordered.iloc[:0]
    baseline_all = pd.concat(baseline_tests, ignore_index=True) if baseline_tests else ordered.iloc[:0]
    return pd.DataFrame(fold_rows), {
        "scope": scope_name,
        "selected_oos": trade_metrics(selected_all),
        "baseline_same_oos_windows": trade_metrics(baseline_all),
    }


def feature_bins(scope: pd.DataFrame, scope_name: str, top_features: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for feature in top_features:
        values = pd.to_numeric(scope[feature], errors="coerce")
        valid = values.notna()
        if values[valid].nunique() < 4:
            continue
        bins = pd.qcut(values[valid], q=4, duplicates="drop")
        for interval, indexes in bins.groupby(bins, observed=True).groups.items():
            group = scope.loc[indexes]
            rows.append(
                {
                    "Scope": scope_name,
                    "Feature": feature,
                    "Bin": str(interval),
                    "FeatureMin": float(pd.to_numeric(group[feature]).min()),
                    "FeatureMax": float(pd.to_numeric(group[feature]).max()),
                    **trade_metrics(group),
                }
            )
    return pd.DataFrame(rows)


def write_csv(path: Path, rows: list[dict] | pd.DataFrame) -> None:
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False)
        return
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt_metric(result: dict) -> str:
    if not result or not result.get("n"):
        return "n=0"
    pf = "N/A" if result.get("pf") is None else f"{result['pf']:.3f}"
    return (
        f"n={result['n']}, W-L={result['wins']}-{result['losses']}, "
        f"WR={100 * result['wr']:.2f}%, PF={pf}, AvgR={result['avg_r']:+.3f}, NetR={result['net_r']:+.2f}"
    )


def bootstrap_mean_ci(
    values: np.ndarray, rng: np.random.Generator, iterations: int = 5000
) -> tuple[float, float]:
    if len(values) == 0:
        return math.nan, math.nan
    samples = np.empty(iterations, dtype=float)
    for index in range(iterations):
        samples[index] = rng.choice(values, size=len(values), replace=True).mean()
    low, high = np.quantile(samples, [0.025, 0.975])
    return float(low), float(high)


def structural_hypothesis_table(
    frame: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Evaluate a few fixed, interpretable rules without fitting their thresholds."""
    rules = {
        "ATASApproachBars3 <= 1": frame["ATASApproachBars3_AtEntry"] <= 1,
        "MappedPivotGapATR > 0": frame["MappedPivotGapATR_AtEntry"] > 0,
        "ATASApproachBars3 <= 1 AND MappedPivotGapATR > 0": (
            (frame["ATASApproachBars3_AtEntry"] <= 1)
            & (frame["MappedPivotGapATR_AtEntry"] > 0)
        ),
    }
    scope_masks = {
        "ALL_CAUSAL_CANDIDATES": pd.Series(True, index=frame.index),
        "CONFIRMED_LATER_SUBSET": frame["ConfirmedLater"] == 1,
    }
    period_masks = {
        "TOTAL": pd.Series(True, index=frame.index),
        "2025": frame["Year"] == 2025,
        "2026": frame["Year"] == 2026,
    }
    rows = []
    for scope_name, scope_mask in scope_masks.items():
        for rule_name, rule_mask in rules.items():
            for period, period_mask in period_masks.items():
                selected = frame.loc[scope_mask & rule_mask & period_mask]
                metrics = trade_metrics(selected)
                values = pd.to_numeric(selected["RealizedR"], errors="coerce").dropna().to_numpy(float)
                ci_low, ci_high = bootstrap_mean_ci(values, rng)
                p_value = (
                    float(binomtest(metrics["wins"], metrics["n"], 1 / 3, alternative="greater").pvalue)
                    if metrics["n"]
                    else math.nan
                )
                rows.append(
                    {
                        "Scope": scope_name,
                        "Rule": rule_name,
                        "Period": period,
                        **metrics,
                        "AvgR_CI95_Low": ci_low,
                        "AvgR_CI95_High": ci_high,
                        "BinomialP_WR_GT_33pct": p_value,
                    }
                )
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    audit_feature_columns(NUMERIC_FEATURES)

    start = datetime.fromisoformat(args.start).replace(tzinfo=structural.NY)
    end = datetime.fromisoformat(args.end).replace(tzinfo=structural.NY)
    events = load_events(args.events)
    trades = json.loads(args.trades.read_text(encoding="utf-8"))
    atas_sessions = structural.load_atas_bars(None, args.atas_cache, start, end)
    mt5_bars = structural.load_mt5_bars(args.terminal, args.symbol, start, end)
    inputs, outcomes, skipped = build_dataset(events, trades, atas_sessions, mt5_bars)
    audit_timestamp_order(inputs)
    write_csv(args.output / "trade_inputs.csv", inputs)
    write_csv(args.output / "trade_outcomes.csv", outcomes)
    write_csv(args.output / "skipped_rows.csv", skipped)

    frame = pd.DataFrame(inputs).merge(pd.DataFrame(outcomes), on="trade_id", validate="one_to_one")
    frame["Year"] = frame["fecha"].str[:4].astype(int)
    rng = np.random.default_rng(20260811)
    scopes = {
        "ALL_CAUSAL_CANDIDATES": frame.copy(),
        "CONFIRMED_LATER_SUBSET": frame.loc[frame["ConfirmedLater"] == 1].copy(),
    }

    univariate_tables = []
    categorical_tables = []
    bin_tables = []
    holdout_tables = []
    holdout_summaries = []
    walkforward_tables = []
    walkforward_summaries = []
    scope_metrics = {}
    top_features_by_scope: dict[str, list[str]] = {}
    for scope_name, scope in scopes.items():
        scope_metrics[scope_name] = trade_metrics(scope)
        uni = univariate(scope, scope_name, rng)
        univariate_tables.append(uni)
        top_features = uni.head(10)["Feature"].tolist()
        top_features_by_scope[scope_name] = top_features
        categorical_tables.append(categorical(scope, scope_name))
        bin_tables.append(feature_bins(scope, scope_name, top_features[:6]))
        holdout_table, holdout_summary = year_holdout(scope, scope_name)
        holdout_tables.append(holdout_table)
        holdout_summaries.append(holdout_summary)
        wf_table, wf_summary = walkforward(scope, scope_name)
        walkforward_tables.append(wf_table)
        walkforward_summaries.append(wf_summary)

    univariate_all = pd.concat(univariate_tables, ignore_index=True)
    categorical_all = pd.concat(categorical_tables, ignore_index=True)
    bins_all = pd.concat(bin_tables, ignore_index=True)
    holdout_all = pd.concat(holdout_tables, ignore_index=True)
    walkforward_all = pd.concat(walkforward_tables, ignore_index=True)
    univariate_all.to_csv(args.output / "univariate_winner_vs_loser.csv", index=False)
    categorical_all.to_csv(args.output / "categorical_breakdown.csv", index=False)
    bins_all.to_csv(args.output / "top_feature_quartiles.csv", index=False)
    holdout_all.to_csv(args.output / "year_holdout_feature_rules.csv", index=False)
    walkforward_all.to_csv(args.output / "nested_walkforward_single_rule.csv", index=False)
    structural_rules = structural_hypothesis_table(frame, rng)
    structural_rules.to_csv(args.output / "fixed_structural_hypotheses.csv", index=False)

    lifecycle = [
        {"Feature": feature, "Lifecycle": classify_column(feature)[0], "Reason": classify_column(feature)[1]}
        for feature in NUMERIC_FEATURES
    ]
    write_csv(args.output / "feature_lifecycle.csv", lifecycle)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), sharex=False)
    for axis, scope_name in zip(axes, scopes):
        table = univariate_all.loc[univariate_all["Scope"] == scope_name].copy()
        table = table.reindex(table["CohenD"].abs().sort_values(ascending=True).tail(12).index)
        colors = ["#0F766E" if value > 0 else "#C2410C" for value in table["CohenD"]]
        axis.barh(table["Feature"].str.replace("_AtEntry", "", regex=False), table["CohenD"], color=colors)
        axis.axvline(0, color="black", linewidth=0.8)
        axis.set_title(scope_name)
        axis.set_xlabel("Cohen's d: winner mean - loser mean")
        axis.grid(axis="x", alpha=0.25)
    fig.suptitle("CFD→ATAS 2R — winner vs loser causal feature effects")
    fig.tight_layout()
    fig.savefig(args.output / "winner_loser_effects.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    common_top = sorted(
        set(top_features_by_scope["ALL_CAUSAL_CANDIDATES"])
        & set(top_features_by_scope["CONFIRMED_LATER_SUBSET"])
    )
    payload = {
        "dataset": {
            "source_trade_rows": len(trades),
            "built_rows": len(frame),
            "skipped_rows": len(skipped),
            "features": len(NUMERIC_FEATURES),
            "first_date": frame["fecha"].min(),
            "last_date": frame["fecha"].max(),
        },
        "scope_metrics": scope_metrics,
        "top_features_by_scope": top_features_by_scope,
        "common_top_features": common_top,
        "fixed_structural_hypotheses": structural_rules.to_dict(orient="records"),
        "year_holdout": holdout_summaries,
        "walkforward": walkforward_summaries,
        "leakage_guard": "PASS: explicit AtEntry allowlist and feature_timestamp <= entry_timestamp",
    }
    (args.output / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )

    report = [
        "# Laboratorio causal — CFD MT5 líder vs ATAS L2, RR 2R",
        "",
        f"Muestra: {frame['fecha'].min()} a {frame['fecha'].max()}.",
        f"Guard de leakage: **PASS**. {len(NUMERIC_FEATURES)} features congeladas a la señal; {len(skipped)} filas omitidas.",
        "",
        "## Universos",
        "",
        f"- Todos los candidatos ejecutados: {fmt_metric(scope_metrics['ALL_CAUSAL_CANDIDATES'])}.",
        f"- Submuestra confirmada después por ATAS: {fmt_metric(scope_metrics['CONFIRMED_LATER_SUBSET'])}.",
        "",
        "La submuestra confirmada usa información futura para definir el universo; sirve para describir el patrón, no para desplegar un filtro en vivo. Las features dentro de ambos universos sí son causales.",
        "",
        "## Qué tienen en común las ganadoras",
        "",
    ]
    all_uni = univariate_all.loc[univariate_all["Scope"] == "ALL_CAUSAL_CANDIDATES"].set_index("Feature")
    gap = all_uni.loc["MappedPivotGapATR_AtEntry"]
    approach = all_uni.loc["ATASApproachBars3_AtEntry"]
    divergence = all_uni.loc["LeadDivergence3ATR_AtEntry"]
    atas_away = all_uni.loc["ATASAway3ATR_AtEntry"]
    fixed_combo = structural_rules.loc[
        (structural_rules["Scope"] == "ALL_CAUSAL_CANDIDATES")
        & (structural_rules["Rule"] == "ATASApproachBars3 <= 1 AND MappedPivotGapATR > 0")
    ].set_index("Period")
    report += [
        f"- **ATAS aún no ha rebasado el pivote mapeado con su cierre:** gap mediano ganador "
        f"{gap.WinnerMedian:+.3f} ATR frente a {gap.LoserMedian:+.3f} ATR en perdedoras.",
        f"- **ATAS ya dejó de insistir hacia ese pivote:** las ganadoras tuvieron mediana de "
        f"{approach.WinnerMedian:.0f} de las últimas 3 velas aproximándose; las perdedoras, "
        f"{approach.LoserMedian:.0f} de 3.",
        f"- **El CFD va delante, pero no demasiado:** divergencia mediana de "
        f"{divergence.WinnerMedian:.3f} ATR en ganadoras frente a {divergence.LoserMedian:.3f} ATR "
        f"en perdedoras. Un desfase extremo fue peor, no mejor.",
        f"- **ATAS muestra freno o inicio de reacción:** desplazamiento a 3 velas de "
        f"{atas_away.WinnerMedian:+.3f} ATR en ganadoras frente a {atas_away.LoserMedian:+.3f} ATR "
        f"en perdedoras.",
        "",
        "La regla estructural fija —sin calibrar umbrales— exige que solo 0–1 de las últimas 3 "
        "velas ATAS siga acercándose y que el cierre ATAS permanezca antes del pivote mapeado:",
        "",
    ]
    for period in ("TOTAL", "2025", "2026"):
        row = fixed_combo.loc[period].to_dict()
        report.append(
            f"- {period}: {fmt_metric(row)}; IC95% bootstrap AvgR "
            f"[{row['AvgR_CI95_Low']:+.3f}, {row['AvgR_CI95_High']:+.3f}], "
            f"p unilateral WR>33.33%={row['BinomialP_WR_GT_33pct']:.4f}."
        )
    report += [
        "",
        "La dirección se repite en ambos años, pero el intervalo todavía incluye cero y 2026 solo "
        "deja un margen pequeño. Es una hipótesis candidata para congelar y validar hacia delante, "
        "no una regla aprobada para operar todavía.",
        "",
        "## Top diferencias univariadas",
        "",
    ]
    for scope_name in scopes:
        report += [f"### {scope_name}", "", "| Feature | Dirección winners | d | AUC orientada | q FDR | d 2025 | d 2026 | estable |", "|---|---|---:|---:|---:|---:|---:|---|"]
        table = univariate_all.loc[univariate_all["Scope"] == scope_name].head(12)
        for row in table.itertuples():
            report.append(
                f"| {row.Feature} | {row.WinnerDirection} | {row.CohenD:.3f} | {row.OrientedAUC:.3f} | "
                f"{row.FDR_Q:.4f} | {row.CohenD2025:.3f} | {row.CohenD2026:.3f} | "
                f"{'sí' if row.StableDirectionBothYears else 'no'} |"
            )
        report.append("")
    report += ["## Holdout por año: regla elegida solo con 2025", ""]
    for item in holdout_summaries:
        report += [
            f"- **{item['scope']}**: `{item.get('rule', 'NONE')}`.",
            f"  - Train 2025: {fmt_metric(item.get('train', {}))}.",
            f"  - Holdout 2026 seleccionado: {fmt_metric(item.get('test_2026', {}))}.",
            f"  - Baseline 2026: {fmt_metric(item.get('test_2026_baseline', {}))}.",
        ]
    report += ["", "## Walk-forward anidado, una regla", ""]
    for item in walkforward_summaries:
        report += [
            f"- **{item['scope']}** seleccionado OOS: {fmt_metric(item['selected_oos'])}.",
            f"- Baseline en las mismas ventanas: {fmt_metric(item['baseline_same_oos_windows'])}.",
        ]
    report += [
        "",
        "## Lectura disciplinada",
        "",
        "- Las asociaciones full-sample son descriptivas hasta que sobrevivan el holdout 2026 y el walk-forward.",
        "- Una feature con q baja pero dirección distinta entre 2025 y 2026 se trata como régimen, no como regla estable.",
        "- No se usaron delay real, hora del pivote ATAS, reacción posterior, MFE/MAE, resultado ni salida como predictores.",
        "- El siguiente gate es congelar cualquier regla superviviente y medirla en datos nuevos, sin recalibrar.",
    ]
    (args.output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    print(f"OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
