from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

import atas_mt5_pivot_backtest as structural


SEASONS = {
    2023: ("2023-03-12T00:00:00", "2023-11-05T00:00:00"),
    2024: ("2024-03-10T00:00:00", "2024-11-03T00:00:00"),
    2025: ("2025-03-09T00:00:00", "2025-11-02T00:00:00"),
    2026: ("2026-03-08T00:00:00", "2026-08-11T00:00:00"),
}

# Preregistered before the final run. These are mechanism thresholds, not an
# optimized grid: opposing aggression, a close beyond the candle midpoint and
# at least 5% of candle volume recovered from the adverse delta extreme.
TARGET_R = 3.0
COST_R = 0.05
MAX_DELAY_MINUTES = 8
MAX_HOLD_MINUTES = 30
MIN_CLOSE_REJECTION = 0.0
MIN_DELTA_REVERSAL = 0.05
MAX_RISK_ATR = 1.25
TICK_SIZE = 0.25


@dataclass(frozen=True)
class TouchTrade:
    year: int
    session_date_ny: str
    side: str
    pivot_kind: str
    leader_pivot_time_ny: str
    structural_signal_time_ny: str
    touch_time_ny: str
    entry_time_ny: str
    exit_time_ny: str
    mapped_pivot: float
    entry: float
    stop: float
    target: float
    risk_points: float
    risk_atr: float
    delta_ratio: float
    directional_delta_ratio: float
    delta_reversal: float
    close_rejection: float
    edge_opposing_share: float
    buy_imbalances: int
    sell_imbalances: int
    result: str
    gross_r: float
    realized_r_after_cost: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preregistered CFD-lead / ATAS footprint-touch 3R backtest."
    )
    parser.add_argument("--sweep-root", type=Path, required=True)
    parser.add_argument("--atas-cache", type=Path, required=True)
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--symbol", default="USTEC")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def read_events(path: Path) -> list[structural.Event]:
    result: list[structural.Event] = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("leader") != "CFD MT5":
                continue
            lagger_time = (row.get("lagger_time_ny") or "").strip()
            delay = (row.get("delay_minutes") or "").strip()
            confirmed = str(row.get("lagger_confirmed_within_window", "")).lower() in {
                "1",
                "true",
                "yes",
            }
            result.append(
                structural.Event(
                    session_date_ny=row["session_date_ny"],
                    leader=row["leader"],
                    lagger=row["lagger"],
                    pivot_kind=row["pivot_kind"],
                    leader_time_ny=row["leader_time_ny"],
                    detection_time_ny=row["detection_time_ny"],
                    lagger_time_ny=lagger_time,
                    delay_minutes=int(delay) if delay else None,
                    lagger_confirmed_within_window=confirmed,
                    leader_price=float(row["leader_price"]),
                    lagger_price=float(row.get("lagger_price") or 0),
                    leader_swing_atr=float(row["leader_swing_atr"]),
                    lagger_swing_atr=float(row.get("lagger_swing_atr") or 0),
                    leader_reaction_atr=float(row["leader_reaction_atr"]),
                    lagger_reaction_atr=float(row.get("lagger_reaction_atr") or 0),
                    occurrence_hour_ny=int(row["occurrence_hour_ny"]),
                )
            )
    return result


def volume(bar: structural.Bar) -> float:
    return float(bar.bid + bar.ask + bar.between)


def footprint_features(bar: structural.Bar, direction: float) -> dict[str, float | int]:
    total = volume(bar)
    candle_range = bar.high - bar.low
    if total <= 0 or candle_range <= 0 or not bar.price_levels:
        return {}
    delta = float(bar.ask - bar.bid)
    delta_ratio = delta / total
    close_rejection = direction * (2 * (bar.close - bar.low) / candle_range - 1)
    if direction > 0:
        delta_reversal = (delta - bar.min_delta) / total
        edge = [level for level in bar.price_levels if level[0] <= bar.low + 0.25 * candle_range]
        edge_share = sum(level[1] for level in edge) / bar.bid if bar.bid > 0 else 0.0
    else:
        delta_reversal = (bar.max_delta - delta) / total
        edge = [level for level in bar.price_levels if level[0] >= bar.high - 0.25 * candle_range]
        edge_share = sum(level[2] for level in edge) / bar.ask if bar.ask > 0 else 0.0

    levels = sorted(bar.price_levels, key=lambda level: level[0])
    buy_imbalances = sell_imbalances = 0
    for index, level in enumerate(levels):
        _price, bid, ask, _between, _ticks = level
        if index > 0 and ask >= 10 and ask >= 3 * max(1, levels[index - 1][1]):
            buy_imbalances += 1
        if index + 1 < len(levels) and bid >= 10 and bid >= 3 * max(1, levels[index + 1][2]):
            sell_imbalances += 1
    return {
        "delta_ratio": delta_ratio,
        "directional_delta_ratio": direction * delta_ratio,
        "delta_reversal": delta_reversal,
        "close_rejection": close_rejection,
        "edge_opposing_share": edge_share,
        "buy_imbalances": buy_imbalances,
        "sell_imbalances": sell_imbalances,
    }


def passes_preregistered_absorption(features: dict[str, float | int]) -> bool:
    return bool(
        features
        and float(features["directional_delta_ratio"]) <= 0
        and float(features["close_rejection"]) >= MIN_CLOSE_REJECTION
        and float(features["delta_reversal"]) >= MIN_DELTA_REVERSAL
    )


def simulate_year(
    year: int,
    events: list[structural.Event],
    sessions: dict[str, list[structural.Bar]],
    mt5: dict[datetime, structural.Bar],
) -> tuple[list[TouchTrade], dict[str, int]]:
    trades: list[TouchTrade] = []
    diagnostics = {
        "cfd_structures": 0,
        "invalid": 0,
        "no_touch": 0,
        "no_absorption": 0,
        "late_or_risk": 0,
        "overlap_skipped": 0,
    }
    unavailable_until: datetime | None = None

    for event in sorted(events, key=lambda item: item.detection_time_ny):
        diagnostics["cfd_structures"] += 1
        signal_time = datetime.fromisoformat(event.detection_time_ny)
        leader_time = datetime.fromisoformat(event.leader_time_ny)
        if unavailable_until is not None and signal_time <= unavailable_until:
            diagnostics["overlap_skipped"] += 1
            continue
        bars = sessions.get(event.session_date_ny, [])
        by_time = {bar.time_ny: index for index, bar in enumerate(bars)}
        signal_index = by_time.get(signal_time)
        leader_index = by_time.get(leader_time)
        cfd_leader = mt5.get(leader_time)
        if signal_index is None or leader_index is None or cfd_leader is None:
            diagnostics["invalid"] += 1
            continue

        # Point-for-point basis mapping is stable for NQ vs USTEC and avoids
        # scaling the pivot distance by the absolute index level.
        mapped_pivot = event.leader_price + (bars[leader_index].close - cfd_leader.close)
        direction = 1.0 if event.pivot_kind == "INFERIOR" else -1.0
        side = "LONG" if direction > 0 else "SHORT"
        deadline = leader_time + timedelta(minutes=MAX_DELAY_MINUTES)
        touch_index: int | None = None
        for index in range(signal_index + 1, len(bars)):
            bar = bars[index]
            if bar.time_ny > deadline:
                break
            touched = bar.low <= mapped_pivot if direction > 0 else bar.high >= mapped_pivot
            if touched:
                touch_index = index
                break
        if touch_index is None:
            diagnostics["no_touch"] += 1
            unavailable_until = deadline
            continue

        touch = bars[touch_index]
        features = footprint_features(touch, direction)
        if not passes_preregistered_absorption(features):
            diagnostics["no_absorption"] += 1
            continue
        entry_index = touch_index + 1
        if entry_index >= len(bars):
            diagnostics["late_or_risk"] += 1
            continue
        entry_bar = bars[entry_index]
        atr = structural.atr_at(bars, touch_index)
        entry = entry_bar.open
        stop = touch.low - TICK_SIZE if direction > 0 else touch.high + TICK_SIZE
        risk = direction * (entry - stop)
        risk_atr = risk / atr if atr > 0 else math.inf
        if (
            risk <= TICK_SIZE
            or not math.isfinite(risk_atr)
            or risk_atr > MAX_RISK_ATR
            or entry_bar.time_ny.time() >= datetime.strptime("16:00", "%H:%M").time()
        ):
            diagnostics["late_or_risk"] += 1
            continue

        target = entry + direction * TARGET_R * risk
        exit_deadline = min(
            entry_bar.time_ny + timedelta(minutes=MAX_HOLD_MINUTES),
            entry_bar.time_ny.replace(hour=16, minute=0, second=0, microsecond=0),
        )
        result = "TIME_EXIT"
        gross_r = 0.0
        exit_index = entry_index
        for index in range(entry_index, len(bars)):
            bar = bars[index]
            if bar.time_ny > exit_deadline:
                break
            exit_index = index
            stop_hit = bar.low <= stop if direction > 0 else bar.high >= stop
            target_hit = bar.high >= target if direction > 0 else bar.low <= target
            if stop_hit:  # conservative if the one-minute path is ambiguous
                result = "LOSS"
                gross_r = -1.0
                break
            if target_hit:
                result = "WIN"
                gross_r = TARGET_R
                break
        if result == "TIME_EXIT":
            eligible = [
                index
                for index in range(entry_index, len(bars))
                if bars[index].time_ny <= exit_deadline
            ]
            exit_index = eligible[-1] if eligible else entry_index
            gross_r = max(
                -1.0,
                min(TARGET_R, direction * (bars[exit_index].close - entry) / risk),
            )
            result = "TIME_WIN" if gross_r > 0 else "TIME_LOSS" if gross_r < 0 else "BREAKEVEN"
        realized = gross_r - COST_R
        trades.append(
            TouchTrade(
                year=year,
                session_date_ny=event.session_date_ny,
                side=side,
                pivot_kind=event.pivot_kind,
                leader_pivot_time_ny=event.leader_time_ny,
                structural_signal_time_ny=event.detection_time_ny,
                touch_time_ny=touch.time_ny.isoformat(),
                entry_time_ny=entry_bar.time_ny.isoformat(),
                exit_time_ny=bars[exit_index].time_ny.isoformat(),
                mapped_pivot=round(mapped_pivot, 4),
                entry=round(entry, 4),
                stop=round(stop, 4),
                target=round(target, 4),
                risk_points=round(risk, 4),
                risk_atr=round(risk_atr, 6),
                delta_ratio=round(float(features["delta_ratio"]), 8),
                directional_delta_ratio=round(float(features["directional_delta_ratio"]), 8),
                delta_reversal=round(float(features["delta_reversal"]), 8),
                close_rejection=round(float(features["close_rejection"]), 8),
                edge_opposing_share=round(float(features["edge_opposing_share"]), 8),
                buy_imbalances=int(features["buy_imbalances"]),
                sell_imbalances=int(features["sell_imbalances"]),
                result=result,
                gross_r=round(gross_r, 6),
                realized_r_after_cost=round(realized, 6),
            )
        )
        unavailable_until = bars[exit_index].time_ny
    return trades, diagnostics


def max_drawdown(values: np.ndarray) -> float:
    equity = np.concatenate([[0.0], np.cumsum(values)])
    return float((np.maximum.accumulate(equity) - equity).max())


def metrics(trades: list[TouchTrade]) -> dict[str, float | int | None]:
    values = np.asarray([trade.realized_r_after_cost for trade in trades], dtype=float)
    positive = values[values > 0]
    negative = values[values < 0]
    n = len(values)
    mean = float(values.mean()) if n else math.nan
    std = float(values.std(ddof=1)) if n > 1 else math.nan
    ci95 = 1.96 * std / math.sqrt(n) if n > 1 else math.nan
    gross_loss = abs(float(negative.sum()))
    return {
        "n": n,
        "wins": int(len(positive)),
        "losses": int(len(negative)),
        "wr": float(len(positive) / n) if n else None,
        "pf": float(positive.sum() / gross_loss) if gross_loss else None,
        "avg_r": mean if n else None,
        "avg_r_ci95_low": mean - ci95 if n > 1 else None,
        "avg_r_ci95_high": mean + ci95 if n > 1 else None,
        "net_r": float(values.sum()),
        "max_drawdown_r": max_drawdown(values) if n else None,
    }


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    all_trades: list[TouchTrade] = []
    diagnostics: dict[str, dict[str, int]] = {}
    for year, (start_text, end_text) in SEASONS.items():
        start = datetime.fromisoformat(start_text).replace(tzinfo=structural.NY)
        end = datetime.fromisoformat(end_text).replace(tzinfo=structural.NY)
        sessions = structural.load_atas_bars(None, args.atas_cache, start, end)
        mt5 = structural.load_mt5_bars(args.terminal, args.symbol, start, end)
        events = read_events(
            args.sweep_root / f"structure_{year}" / "atas_mt5_pivot_events.csv"
        )
        trades, year_diagnostics = simulate_year(year, events, sessions, mt5)
        all_trades.extend(trades)
        diagnostics[str(year)] = year_diagnostics

    frame = pd.DataFrame(asdict(trade) for trade in all_trades)
    frame.to_csv(args.output / "l2_touch_trades_3R.csv", index=False)
    periods = {
        str(year): metrics([trade for trade in all_trades if trade.year == year])
        for year in SEASONS
    }
    periods["DEVELOPMENT_2023_2025"] = metrics(
        [trade for trade in all_trades if trade.year <= 2025]
    )
    holdout = periods["2026"]
    development = periods["DEVELOPMENT_2023_2025"]
    approved = bool(
        development["n"] >= 60
        and development["avg_r_ci95_low"] is not None
        and development["avg_r_ci95_low"] > 0
        and periods["2024"]["pf"] is not None
        and periods["2024"]["pf"] >= 1.20
        and periods["2025"]["pf"] is not None
        and periods["2025"]["pf"] >= 1.20
        and holdout["n"] >= 30
        and holdout["pf"] is not None
        and holdout["pf"] >= 1.30
        and holdout["avg_r"] is not None
        and holdout["avg_r"] >= 0.15
        and holdout["avg_r_ci95_low"] is not None
        and holdout["avg_r_ci95_low"] > 0
        and holdout["max_drawdown_r"] is not None
        and holdout["max_drawdown_r"] <= 10
    )
    payload = {
        "strategy": "CFD structural pivot -> ATAS mapped-level touch -> completed-footprint absorption -> next M1 open",
        "preregistered_parameters": {
            "target_r": TARGET_R,
            "cost_r_per_trade": COST_R,
            "max_lead_delay_minutes": MAX_DELAY_MINUTES,
            "max_hold_minutes": MAX_HOLD_MINUTES,
            "opposing_directional_delta_max": 0.0,
            "minimum_close_rejection": MIN_CLOSE_REJECTION,
            "minimum_delta_reversal": MIN_DELTA_REVERSAL,
            "maximum_risk_atr": MAX_RISK_ATR,
            "stop": "one NQ tick beyond ATAS touch-candle structural extreme",
            "mapping": "point-for-point CFD/ATAS basis observed at CFD leader pivot",
        },
        "periods": periods,
        "diagnostics": diagnostics,
        "approved_for_live": approved,
        "leakage_guard": "PASS: absorption uses only the completed touch candle; entry is next M1 open",
        "multiplicity_note": "Final distinct entry-trigger hypothesis; no further 2026 tuning is permitted.",
    }
    (args.output / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# Prueba final: CFD lidera y ATAS confirma absorción al tocar el pivote",
        "",
        "Regla causal fijada antes de abrir 2026: estructura CFD, toque ATAS <=8m, delta contrario, rechazo del cierre y recuperación de delta >=5%; entrada en la siguiente apertura M1, stop detrás del extremo, TP 3R y coste 0.05R.",
        "",
    ]
    for period in ("2023", "2024", "2025", "2026", "DEVELOPMENT_2023_2025"):
        value = periods[period]
        lines.append(
            f"- {period}: n={value['n']}, W-L={value['wins']}-{value['losses']}, "
            f"WR={100 * value['wr']:.2f}%, PF={value['pf']:.3f}, AvgR={value['avg_r']:+.3f}, "
            f"IC95=[{value['avg_r_ci95_low']:+.3f}, {value['avg_r_ci95_high']:+.3f}], "
            f"NetR={value['net_r']:+.2f}, DD={value['max_drawdown_r']:.2f}R."
        )
    lines.extend(
        [
            "",
            f"Estado: **{'APROBADO PARA LIVE' if approved else 'RECHAZADO / SOLO PAPER'}**.",
            "",
            "No se permite modificar umbrales usando 2026 después de esta prueba.",
        ]
    )
    (args.output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    print(f"OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
