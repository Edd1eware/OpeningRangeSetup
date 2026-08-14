from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import atas_mt5_pivot_backtest as structural


@dataclass(frozen=True)
class Trade:
    session_date_ny: str
    signal_time_ny: str
    fill_time_ny: str
    exit_time_ny: str
    side: str
    pivot_kind: str
    entry: float
    stop: float
    target: float
    risk_points: float
    target_rr: float
    result: str
    realized_r: float
    confirmed_structure_after_signal: bool


def build_events_and_sessions(
    cache: Path,
    terminal: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    broker_calendar: str = "us",
) -> tuple[
    dict[str, list[structural.Bar]],
    dict[datetime, structural.Bar],
    list[structural.Event],
    dict[str, object],
]:
    atas_sessions = structural.load_atas_bars(None, cache, start, end)
    mt5_bars = structural.load_mt5_bars(
        terminal, symbol, start, end, broker_calendar=broker_calendar
    )
    alignment = structural.diagnose_alignment(atas_sessions, mt5_bars)
    per_session = structural.diagnose_alignment_by_session(atas_sessions, mt5_bars)
    alignment["by_session"] = per_session
    print(json.dumps({"alignment": alignment}, indent=2, ensure_ascii=False))
    if not per_session["all_sessions_aligned"]:
        raise SystemExit(
            f"ABORTADO: {per_session['sessions_misaligned']} sesiones no alinean en shift 0."
        )
    session_start = datetime.strptime("09:30", "%H:%M").time()
    session_end = datetime.strptime("16:00", "%H:%M").time()
    usable_sessions: dict[str, list[structural.Bar]] = {}
    events: list[structural.Event] = []

    for day, raw_atas in sorted(atas_sessions.items()):
        common_times = {
            item.time_ny
            for item in raw_atas
            if session_start <= item.time_ny.time() <= session_end
        }.intersection(mt5_bars)
        if len(common_times) < 100:
            continue
        atas = [item for item in raw_atas if item.time_ny in common_times]
        cfd = [mt5_bars[item.time_ny] for item in atas]
        usable_sessions[day] = atas
        atas_pivots = structural.detect_pivots(
            atas,
            "ATAS L2",
            swing_lookback=20,
            minimum_swing_atr=0.50,
            minimum_reaction_atr=0.25,
        )
        cfd_pivots = structural.detect_pivots(
            cfd,
            "CFD MT5",
            swing_lookback=20,
            minimum_swing_atr=0.50,
            minimum_reaction_atr=0.25,
        )
        events.extend(
            structural.detect_lead_events(
                atas_pivots,
                cfd_pivots,
                atas,
                cfd,
                common_times,
                minimum_swing_atr=5.0,
                minimum_reaction_atr=1.5,
            )
        )
    return usable_sessions, mt5_bars, events, alignment


def simulate_target(
    atas_sessions: dict[str, list[structural.Bar]],
    mt5_bars: dict[datetime, structural.Bar],
    events: list[structural.Event],
    target_rr: float,
    *,
    stop_atr: float = 1.0,
    max_total_delay_minutes: int = 8,
    max_holding_minutes: int = 30,
    require_lagger_approach: bool = False,
    minimum_lagger_approach_atr: float = 0.25,
) -> tuple[list[Trade], dict[str, int]]:
    trades: list[Trade] = []
    diagnostics = {
        "cfd_signals": 0,
        "unfilled": 0,
        "overlap_skipped": 0,
        "invalid": 0,
        "lagger_not_approaching": 0,
    }
    unavailable_until: datetime | None = None

    for event in sorted(events, key=lambda item: item.detection_time_ny):
        if event.leader != "CFD MT5":
            continue
        diagnostics["cfd_signals"] += 1
        signal_time = datetime.fromisoformat(event.detection_time_ny)
        leader_time = datetime.fromisoformat(event.leader_time_ny)
        if unavailable_until is not None and signal_time <= unavailable_until:
            diagnostics["overlap_skipped"] += 1
            continue

        session = atas_sessions.get(event.session_date_ny, [])
        time_to_index = {bar.time_ny: index for index, bar in enumerate(session)}
        leader_index = time_to_index.get(leader_time)
        signal_index = time_to_index.get(signal_time)
        cfd_at_leader = mt5_bars.get(leader_time)
        if leader_index is None or signal_index is None or cfd_at_leader is None:
            diagnostics["invalid"] += 1
            continue

        atas_at_leader = session[leader_index]
        # Additive basis frozen at the pivot minute, matching the documented rule.
        # The leader here is always the CFD, so the NQ level is the CFD pivot plus
        # the NQ-minus-CFD basis of that same minute.
        mapped_entry = event.leader_price + (atas_at_leader.close - cfd_at_leader.close)
        atr = structural.atr_at(session, signal_index)
        if not math.isfinite(mapped_entry) or atr <= 0:
            diagnostics["invalid"] += 1
            continue

        side = "LONG" if event.pivot_kind == "INFERIOR" else "SHORT"
        if require_lagger_approach:
            if signal_index < 3:
                diagnostics["invalid"] += 1
                continue
            approach = session[signal_index - 3 : signal_index + 1]
            close_moves = [
                approach[index].close - approach[index - 1].close
                for index in range(1, len(approach))
            ]
            if side == "LONG":
                toward_count = sum(move < 0 for move in close_moves)
                net_toward = approach[0].close - approach[-1].close
                entry_still_ahead = mapped_entry < approach[-1].low
            else:
                toward_count = sum(move > 0 for move in close_moves)
                net_toward = approach[-1].close - approach[0].close
                entry_still_ahead = mapped_entry > approach[-1].high
            if (
                toward_count < 2
                or net_toward < minimum_lagger_approach_atr * atr
                or not entry_still_ahead
            ):
                diagnostics["lagger_not_approaching"] += 1
                continue

        order_end = leader_time + timedelta(minutes=max_total_delay_minutes)
        fill_index: int | None = None
        for index in range(signal_index + 1, len(session)):
            bar = session[index]
            if bar.time_ny > order_end:
                break
            touched = bar.low <= mapped_entry if side == "LONG" else bar.high >= mapped_entry
            if touched:
                fill_index = index
                break

        if fill_index is None:
            diagnostics["unfilled"] += 1
            unavailable_until = order_end
            continue

        risk = atr * stop_atr
        stop = mapped_entry - risk if side == "LONG" else mapped_entry + risk
        target = mapped_entry + target_rr * risk if side == "LONG" else mapped_entry - target_rr * risk
        exit_deadline = session[fill_index].time_ny + timedelta(minutes=max_holding_minutes)
        exit_index = fill_index
        result = "TIME_EXIT"
        realized_r = 0.0

        for index in range(fill_index, len(session)):
            bar = session[index]
            if bar.time_ny > exit_deadline:
                break
            stop_hit = bar.low <= stop if side == "LONG" else bar.high >= stop
            target_hit = bar.high >= target if side == "LONG" else bar.low <= target
            exit_index = index
            if stop_hit:  # conservador cuando stop y target aparecen en la misma vela
                result = "LOSS"
                realized_r = -1.0
                break
            if target_hit:
                result = "WIN"
                realized_r = target_rr
                break
        else:
            exit_index = len(session) - 1

        if result == "TIME_EXIT":
            last_allowed = min(
                range(fill_index, len(session)),
                key=lambda index: abs((session[index].time_ny - exit_deadline).total_seconds()),
            )
            exit_index = last_allowed
            exit_price = session[exit_index].close
            pnl_points = exit_price - mapped_entry if side == "LONG" else mapped_entry - exit_price
            realized_r = max(-1.0, min(target_rr, pnl_points / risk))
            if realized_r > 0:
                result = "TIME_WIN"
            elif realized_r < 0:
                result = "TIME_LOSS"
            else:
                result = "BREAKEVEN"

        confirmed = event.lagger_confirmed_within_window
        trade = Trade(
            session_date_ny=event.session_date_ny,
            signal_time_ny=event.detection_time_ny,
            fill_time_ny=session[fill_index].time_ny.isoformat(),
            exit_time_ny=session[exit_index].time_ny.isoformat(),
            side=side,
            pivot_kind=event.pivot_kind,
            entry=round(mapped_entry, 4),
            stop=round(stop, 4),
            target=round(target, 4),
            risk_points=round(risk, 4),
            target_rr=target_rr,
            result=result,
            realized_r=round(realized_r, 6),
            confirmed_structure_after_signal=confirmed,
        )
        trades.append(trade)
        unavailable_until = session[exit_index].time_ny

    return trades, diagnostics


def metrics(trades: list[Trade], diagnostics: dict[str, int]) -> dict[str, object]:
    outcomes = [trade.realized_r for trade in trades]
    positives = [value for value in outcomes if value > 0]
    negatives = [value for value in outcomes if value < 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    wins = len(positives)
    losses = len(negatives)
    payoff = (
        statistics.fmean(positives) / abs(statistics.fmean(negatives))
        if positives and negatives
        else 0.0
    )
    return {
        **diagnostics,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "breakeven": len(trades) - wins - losses,
        "win_rate_pct": round(100 * wins / len(trades), 2) if trades else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "average_realized_r": round(statistics.fmean(outcomes), 4) if outcomes else 0.0,
        "average_win_r": round(statistics.fmean(positives), 4) if positives else 0.0,
        "average_loss_r": round(statistics.fmean(negatives), 4) if negatives else 0.0,
        "average_payoff_rr": round(payoff, 3),
        "net_r": round(sum(outcomes), 3),
        "confirmed_trades": sum(trade.confirmed_structure_after_signal for trade in trades),
    }


def simulate_confirmed_reversal(
    atas_sessions: dict[str, list[structural.Bar]],
    events: list[structural.Event],
    target_rr: float,
    *,
    stop_atr: float = 1.0,
    max_holding_minutes: int = 30,
) -> tuple[list[Trade], dict[str, int]]:
    trades: list[Trade] = []
    diagnostics = {
        "cfd_signals": sum(event.leader == "CFD MT5" for event in events),
        "unfilled": 0,
        "overlap_skipped": 0,
        "invalid": 0,
    }
    unavailable_until: datetime | None = None

    for event in sorted(events, key=lambda item: item.lagger_time_ny or "9999"):
        if event.leader != "CFD MT5" or not event.lagger_confirmed_within_window:
            continue
        pivot_time = datetime.fromisoformat(event.lagger_time_ny)
        structure_known_time = pivot_time + timedelta(minutes=2)
        session = atas_sessions.get(event.session_date_ny, [])
        time_to_index = {bar.time_ny: index for index, bar in enumerate(session)}
        known_index = time_to_index.get(structure_known_time)
        if known_index is None or known_index + 1 >= len(session):
            diagnostics["invalid"] += 1
            continue
        entry_index = known_index + 1
        entry_time = session[entry_index].time_ny
        if unavailable_until is not None and entry_time <= unavailable_until:
            diagnostics["overlap_skipped"] += 1
            continue

        entry = session[entry_index].open
        atr = structural.atr_at(session, known_index)
        if atr <= 0:
            diagnostics["invalid"] += 1
            continue
        side = "LONG" if event.pivot_kind == "INFERIOR" else "SHORT"
        risk = atr * stop_atr
        stop = entry - risk if side == "LONG" else entry + risk
        target = entry + target_rr * risk if side == "LONG" else entry - target_rr * risk
        exit_deadline = entry_time + timedelta(minutes=max_holding_minutes)
        exit_index = entry_index
        result = "TIME_EXIT"
        realized_r = 0.0

        for index in range(entry_index, len(session)):
            bar = session[index]
            if bar.time_ny > exit_deadline:
                break
            exit_index = index
            stop_hit = bar.low <= stop if side == "LONG" else bar.high >= stop
            target_hit = bar.high >= target if side == "LONG" else bar.low <= target
            if stop_hit:
                result = "LOSS"
                realized_r = -1.0
                break
            if target_hit:
                result = "WIN"
                realized_r = target_rr
                break

        if result == "TIME_EXIT":
            eligible = [
                index
                for index in range(entry_index, len(session))
                if session[index].time_ny <= exit_deadline
            ]
            exit_index = eligible[-1] if eligible else entry_index
            exit_price = session[exit_index].close
            pnl_points = exit_price - entry if side == "LONG" else entry - exit_price
            realized_r = max(-1.0, min(target_rr, pnl_points / risk))
            result = "TIME_WIN" if realized_r > 0 else "TIME_LOSS" if realized_r < 0 else "BREAKEVEN"

        trades.append(
            Trade(
                session_date_ny=event.session_date_ny,
                signal_time_ny=structure_known_time.isoformat(),
                fill_time_ny=entry_time.isoformat(),
                exit_time_ny=session[exit_index].time_ny.isoformat(),
                side=side,
                pivot_kind=event.pivot_kind,
                entry=round(entry, 4),
                stop=round(stop, 4),
                target=round(target, 4),
                risk_points=round(risk, 4),
                target_rr=target_rr,
                result=result,
                realized_r=round(realized_r, 6),
                confirmed_structure_after_signal=True,
            )
        )
        unavailable_until = session[exit_index].time_ny

    return trades, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atas-cache", type=Path, required=True)
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--symbol", default="USTEC")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--targets",
        default="1.0,1.5,2.0,2.5,3.0",
        help="Comma-separated RR targets (example: 1.5,3,4,5).",
    )
    parser.add_argument(
        "--hours",
        default="",
        help="Comma-separated NY hours of the detection minute to keep (example: 13,14,15). "
             "Empty keeps every hour. Pivots and ATR are still computed on the full session, "
             "so this filters signals rather than changing the experiment.",
    )
    parser.add_argument(
        "--broker-calendar",
        default="us",
        help='Broker clock: "us" (UTC+2/+3 switching with New York) or an IANA zone.',
    )
    args = parser.parse_args()

    targets = sorted({float(value.strip()) for value in args.targets.split(",") if value.strip()})
    if not targets or any(value <= 0 for value in targets):
        parser.error("--targets must contain one or more positive RR values")

    start = datetime.fromisoformat(args.start).replace(tzinfo=structural.NY)
    end = datetime.fromisoformat(args.end).replace(tzinfo=structural.NY)
    sessions, mt5_bars, events, alignment = build_events_and_sessions(
        args.atas_cache,
        args.terminal,
        args.symbol,
        start,
        end,
        args.broker_calendar,
    )
    hours = {int(v.strip()) for v in args.hours.split(",") if v.strip()}
    if hours:
        before = len(events)
        events = [e for e in events if e.occurrence_hour_ny in hours]
        print(f"[filtro] horas NY {sorted(hours)}: {len(events)} de {before} eventos", flush=True)

    report: dict[str, object] = {
        "period_start_ny": start.isoformat(),
        "hours_filter_ny": sorted(hours) if hours else "todas",
        "period_end_ny": end.isoformat(),
        "sessions": len(sessions),
        "dates": sorted(sessions),
        "mapping": "additive_basis_frozen_at_pivot_minute",
        "broker_calendar": args.broker_calendar,
        "alignment": alignment,
        "method": "CFD structure known at +3 M1; ATAS must still approach for 3 bars (2/3 closes, >=0.25 ATR, entry not touched); mapped ATAS limit until +8 M1; stop 1 ATR; 30m horizon; conservative same-bar",
        "targets": {},
        "raw_candidate_method": "CFD signal at +3 M1 without requiring ATAS to be moving toward the mapped pivot",
        "raw_candidate_targets": {},
        "confirmed_entry_method": "Only confirmed CFD->ATAS pivots; enter next M1 after ATAS 2x2 confirmation; stop 1 ATR; 30m horizon",
        "confirmed_entry_targets": {},
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for target_rr in targets:
        target_key = f"{target_rr:.1f}R"
        raw_trades, raw_diagnostics = simulate_target(
            sessions,
            mt5_bars,
            events,
            target_rr,
        )
        report["raw_candidate_targets"][target_key] = metrics(
            raw_trades,
            raw_diagnostics,
        )
        (args.output / f"raw_trades_{target_rr:.1f}R.json").write_text(
            json.dumps(
                [asdict(trade) for trade in raw_trades],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        trades, diagnostics = simulate_target(
            sessions,
            mt5_bars,
            events,
            target_rr,
            require_lagger_approach=True,
        )
        report["targets"][target_key] = metrics(trades, diagnostics)
        trade_path = args.output / f"trades_{target_rr:.1f}R.json"
        trade_path.write_text(
            json.dumps([asdict(trade) for trade in trades], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        confirmed_trades, confirmed_diagnostics = simulate_confirmed_reversal(
            sessions,
            events,
            target_rr,
        )
        report["confirmed_entry_targets"][target_key] = metrics(
            confirmed_trades,
            confirmed_diagnostics,
        )
        (args.output / f"confirmed_trades_{target_rr:.1f}R.json").write_text(
            json.dumps(
                [asdict(trade) for trade in confirmed_trades],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    (args.output / "trade_metrics.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
