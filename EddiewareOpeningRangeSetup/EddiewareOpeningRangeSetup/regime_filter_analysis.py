from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Sequence

import duckdb


DB = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR"
    r"\Nautilus_OR\data\orb_features.duckdb"
)

# Lucid $150k assumptions supplied with the problem.
TP = 60
SL = 30
TP_SLIP = 1
SL_SLIP = 1
TRAIL = 30
TRAIL_SLIP = 5
COMM = 9.0
TARGET = 9_000.0
MAX_DD = 4_500.0
WINDOW_DAYS = 49

FOMC_DATES = {
    date.fromisoformat(x)
    for x in {
        "2024-07-31",
        "2024-09-18",
        "2024-11-07",
        "2024-12-18",
        "2025-01-29",
        "2025-03-19",
        "2025-05-07",
        "2025-06-18",
        "2025-07-30",
        "2025-09-17",
        "2025-10-29",
        "2025-12-10",
        "2026-01-28",
        "2026-03-18",
        "2026-05-06",
        "2026-06-17",
    }
}

# Dates in the supplied benchmark, retained exactly for reproducibility.
JH_2025_BENCHMARK = {
    date.fromisoformat(x)
    for x in {
        "2025-08-18",
        "2025-08-19",
        "2025-08-20",
        "2025-08-21",
        "2025-08-22",
    }
}

# A reproducible calendar rule must be applied in every year, not only to the
# year that contained the observed drawdown. These are the Mon-Fri weeks that
# contained the official 2024 and 2025 symposium dates.
JH_EVENT_WEEKS = {
    date(2024, 8, 19) + timedelta(days=i) for i in range(5)
} | JH_2025_BENCHMARK


@dataclass(frozen=True)
class Trade:
    session_date: date
    direction: str
    hit: bool
    dist_vwap_ticks: float
    sign_match: bool
    or_trend: float
    or_size_ticks: int
    single_print_pct: float
    peak: int


@dataclass(frozen=True)
class Event:
    trade: Trade
    pnl: float
    contracts: int = 3


def load_trades() -> list[Trade]:
    con = duckdb.connect(str(DB), read_only=True)
    rows = con.execute(
        """
        SELECT ev.session_date, ev.direction, ev.hit_target,
               ev.dist_vwap_ticks, ev.or_delta_sign_match,
               ev.or_trend, ev.or_size_ticks, ev.single_print_pct,
               COALESCE(rs.runner_ticks, 0) peak
        FROM edge_view ev
        LEFT JOIN runner_stats rs USING (session_date, direction)
        WHERE ev.va_width_ticks <= 125
        ORDER BY ev.session_date
        """
    ).fetchall()
    con.close()
    return [Trade(*r) for r in rows]


def pnl_for_contracts(hit: bool, peak: int, contracts: int) -> float:
    """1 contract exits at TP; any additional contracts use the supplied runner."""
    if contracts <= 0:
        return 0.0
    if not hit:
        return -contracts * ((SL + SL_SLIP) * 5 + COMM)
    extension = max(0, peak - (TRAIL + TRAIL_SLIP))
    tp_contract = (TP - TP_SLIP) * 5 - COMM
    runner_contract = ((TP - TP_SLIP) + extension) * 5 - COMM
    return tp_contract + (contracts - 1) * runner_contract


def events_from_trades(trades: Iterable[Trade], contracts: int = 3) -> list[Event]:
    return [Event(t, pnl_for_contracts(t.hit, t.peak, contracts), contracts) for t in trades]


def window_summary(events: Sequence[Event]) -> dict[str, float | int]:
    passed = blown = neither = 0
    max_sl_all = 0
    for start in range(len(events)):
        start_date = events[start].trade.session_date
        window = [
            e
            for e in events[start:]
            if (e.trade.session_date - start_date).days <= WINDOW_DAYS
        ]
        if len(window) < 3:
            continue
        equity = peak_equity = 0.0
        p = b = False
        cur_sl = 0
        for event in window:
            equity += event.pnl
            peak_equity = max(peak_equity, equity)
            dd = peak_equity - equity
            if event.pnl < 0:
                cur_sl += 1
                max_sl_all = max(max_sl_all, cur_sl)
            elif event.pnl > 0:
                cur_sl = 0
            if dd >= MAX_DD and not p and not b:
                b = True
            if equity >= TARGET and not p and not b:
                p = True
        if p:
            passed += 1
        elif b:
            blown += 1
        else:
            neither += 1
    total = passed + blown + neither
    return {
        "passed": passed,
        "blown": blown,
        "neither": neither,
        "windows": total,
        "pass_pct": 100 * passed / total if total else 0.0,
        "blow_pct": 100 * blown / total if total else 0.0,
        "max_sl": max_sl_all,
    }


def strategy_summary(name: str, events: Sequence[Event], base: Sequence[Trade]) -> dict:
    ws = window_summary(events)
    elapsed_weeks = (base[-1].session_date - base[0].session_date).days / 7
    wins = sum(e.trade.hit for e in events)
    return {
        "name": name,
        "n": len(events),
        "wr": 100 * wins / len(events) if events else 0.0,
        **ws,
        "total_pnl": sum(e.pnl for e in events),
        "ev_week": sum(e.pnl for e in events) / elapsed_weeks,
    }


def rolling_wr_filter(trades: Sequence[Trade], n: int, threshold: float) -> list[Trade]:
    """Current decision uses only the previous n raw setup outcomes (shadow signals)."""
    kept: list[Trade] = []
    history: list[bool] = []
    for trade in trades:
        enabled = len(history) < n or sum(history[-n:]) / n >= threshold
        if enabled:
            kept.append(trade)
        history.append(trade.hit)
    return kept


def rolling_wr_hysteresis_filter(
    trades: Sequence[Trade],
    lookback: int = 12,
    pause_at_wins: int = 1,
    resume_at_wins: int = 3,
) -> list[Trade]:
    """
    Pause before the current signal when the PRIOR lookback raw setup outcomes
    contain at most pause_at_wins TPs. Resume only after the prior rolling window
    contains at least resume_at_wins TPs. Shadow outcomes always update history.
    """
    kept: list[Trade] = []
    history: list[bool] = []
    enabled = True
    for trade in trades:
        if len(history) >= lookback:
            wins = sum(history[-lookback:])
            if enabled and wins <= pause_at_wins:
                enabled = False
            elif not enabled and wins >= resume_at_wins:
                enabled = True
        if enabled:
            kept.append(trade)
        history.append(trade.hit)
    return kept


def shadow_recovery_filter(
    trades: Sequence[Trade], loss_trigger: int, min_pause_days: int = 0
) -> list[Trade]:
    """
    Trade until K consecutive raw setup losses. Then paper-trade until both the
    minimum calendar pause has elapsed and a shadow setup wins. The recovery win
    is necessarily skipped; trading resumes at the next signal.
    """
    kept: list[Trade] = []
    streak = 0
    paused = False
    pause_started: date | None = None
    for trade in trades:
        if paused:
            assert pause_started is not None
            elapsed = (trade.session_date - pause_started).days
            if elapsed >= min_pause_days and trade.hit:
                paused = False
                streak = 0
            continue
        kept.append(trade)
        if trade.hit:
            streak = 0
        else:
            streak += 1
            if streak >= loss_trigger:
                paused = True
                pause_started = trade.session_date
    return kept


def fixed_signal_cooldown_filter(
    trades: Sequence[Trade], loss_trigger: int, skip_signals: int
) -> list[Trade]:
    """After K traded losses, skip a fixed number of subsequent raw setup signals."""
    kept: list[Trade] = []
    streak = 0
    remaining = 0
    for trade in trades:
        if remaining:
            remaining -= 1
            continue
        kept.append(trade)
        if trade.hit:
            streak = 0
        else:
            streak += 1
            if streak >= loss_trigger:
                remaining = skip_signals
                streak = 0
    return kept


def adaptive_streak_events(trades: Sequence[Trade]) -> list[Event]:
    """3c normally; after one raw SL use 2c; after >=2 raw SL use 1c; TP resets."""
    events: list[Event] = []
    streak = 0
    for trade in trades:
        contracts = max(1, 3 - streak)
        events.append(Event(trade, pnl_for_contracts(trade.hit, trade.peak, contracts), contracts))
        streak = 0 if trade.hit else streak + 1
    return events


def risk_governor_window_summary(
    trades: Sequence[Trade], reserve: float = 0.0
) -> dict[str, float | int]:
    """
    Challenge-local sizing. Before every entry choose the largest size (0..3)
    whose modelled SL remains strictly below MAX_DD-reserve.
    """
    passed = blown = neither = 0
    max_sl_all = 0
    executed = 0
    summed_window_pnl = 0.0
    for start in range(len(trades)):
        start_date = trades[start].session_date
        window = [
            t for t in trades[start:] if (t.session_date - start_date).days <= WINDOW_DAYS
        ]
        if len(window) < 3:
            continue
        equity = peak_equity = 0.0
        p = b = False
        cur_sl = 0
        for trade in window:
            dd = peak_equity - equity
            one_contract_loss = -pnl_for_contracts(False, 0, 1)
            available = MAX_DD - reserve - dd
            contracts = min(3, max(0, int((available - 1e-9) // one_contract_loss)))
            if contracts == 0:
                continue
            executed += 1
            pnl = pnl_for_contracts(trade.hit, trade.peak, contracts)
            equity += pnl
            peak_equity = max(peak_equity, equity)
            new_dd = peak_equity - equity
            if pnl < 0:
                cur_sl += 1
                max_sl_all = max(max_sl_all, cur_sl)
            else:
                cur_sl = 0
            if new_dd >= MAX_DD and not p and not b:
                b = True
            if equity >= TARGET and not p and not b:
                p = True
        if p:
            passed += 1
        elif b:
            blown += 1
        else:
            neither += 1
        summed_window_pnl += equity
    total = passed + blown + neither
    return {
        "passed": passed,
        "blown": blown,
        "neither": neither,
        "windows": total,
        "pass_pct": 100 * passed / total if total else 0.0,
        "blow_pct": 100 * blown / total if total else 0.0,
        "max_sl": max_sl_all,
        "mean_executions_per_window": executed / total if total else 0.0,
        "mean_window_ev_week": summed_window_pnl / total / 7 if total else 0.0,
    }


def fmt(rows: Sequence[dict], columns: Sequence[str]) -> str:
    widths = {
        c: max(len(c), *(len(_fmt_value(r.get(c))) for r in rows)) for c in columns
    }
    lines = ["  ".join(c.ljust(widths[c]) for c in columns)]
    lines.append("  ".join("-" * widths[c] for c in columns))
    for row in rows:
        lines.append(
            "  ".join(_fmt_value(row.get(c)).ljust(widths[c]) for c in columns)
        )
    return "\n".join(lines)


def _fmt_value(value) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def main() -> None:
    trades = load_trades()
    base_events = events_from_trades(trades)
    key_rows: list[dict] = [strategy_summary("BASE", base_events, trades)]

    fomc = [t for t in trades if t.session_date not in FOMC_DATES]
    jh = [t for t in trades if t.session_date not in JH_2025_BENCHMARK]
    jh_universal = [t for t in trades if t.session_date not in JH_EVENT_WEEKS]
    calendar = [
        t
        for t in trades
        if t.session_date not in FOMC_DATES
        and t.session_date not in JH_2025_BENCHMARK
    ]
    key_rows.extend(
        [
            strategy_summary("FOMC", events_from_trades(fomc), trades),
            strategy_summary("JH_2025", events_from_trades(jh), trades),
            strategy_summary("JH_all_years", events_from_trades(jh_universal), trades),
            strategy_summary("FOMC+JH", events_from_trades(calendar), trades),
        ]
    )

    specified_a = []
    for n in (5, 10):
        for threshold in (0.25, 0.33):
            filtered = rolling_wr_filter(trades, n, threshold)
            row = strategy_summary(
                f"A_N{n}_X{threshold:.2f}", events_from_trades(filtered), trades
            )
            specified_a.append(row)
            key_rows.append(row)

    grid_a: list[dict] = []
    for n in range(3, 31):
        for threshold_pct in range(10, 51):
            filtered = rolling_wr_filter(trades, n, threshold_pct / 100)
            row = strategy_summary(
                f"A_N{n}_X{threshold_pct}", events_from_trades(filtered), trades
            )
            row["N"] = n
            row["X"] = threshold_pct
            grid_a.append(row)
    valid_a = [
        r
        for r in grid_a
        if r["blown"] == 0 and r["pass_pct"] >= 80 and r["n"] >= 200
    ]
    valid_a.sort(key=lambda r: (-r["n"], -r["pass_pct"], -r["ev_week"]))

    adaptive = strategy_summary("C_3-2-1", adaptive_streak_events(trades), trades)
    key_rows.append(adaptive)

    hysteresis = rolling_wr_hysteresis_filter(trades)
    key_rows.append(
        strategy_summary("A_N12_1-3_hysteresis", events_from_trades(hysteresis), trades)
    )
    hysteresis_dates = {t.session_date for t in hysteresis}
    e_benchmark = [
        t
        for t in trades
        if t.session_date in hysteresis_dates
        and t.session_date not in FOMC_DATES
        and t.session_date not in JH_2025_BENCHMARK
    ]
    e_universal = [
        t
        for t in trades
        if t.session_date in hysteresis_dates
        and t.session_date not in FOMC_DATES
        and t.session_date not in JH_EVENT_WEEKS
    ]
    key_rows.extend(
        [
            strategy_summary(
                "E_benchmark+hysteresis", events_from_trades(e_benchmark), trades
            ),
            strategy_summary(
                "E_universal+hysteresis", events_from_trades(e_universal), trades
            ),
        ]
    )

    d_rows: list[dict] = []
    for trigger in range(2, 6):
        for pause_days in (0, 3, 5):
            filtered = shadow_recovery_filter(trades, trigger, pause_days)
            row = strategy_summary(
                f"D_shadow_K{trigger}_D{pause_days}",
                events_from_trades(filtered),
                trades,
            )
            row["K"] = trigger
            row["D"] = pause_days
            row["mode"] = "shadow"
            d_rows.append(row)
        for skip in range(1, 11):
            filtered = fixed_signal_cooldown_filter(trades, trigger, skip)
            row = strategy_summary(
                f"D_fixed_K{trigger}_S{skip}", events_from_trades(filtered), trades
            )
            row["K"] = trigger
            row["D"] = skip
            row["mode"] = "signals"
            d_rows.append(row)
    valid_d = [
        r
        for r in d_rows
        if r["blown"] == 0 and r["pass_pct"] >= 80 and r["n"] >= 200
    ]
    valid_d.sort(key=lambda r: (-r["n"], -r["pass_pct"], -r["ev_week"]))
    for wanted in ("D_shadow_K3_D0", "D_shadow_K3_D3", "D_shadow_K3_D5"):
        key_rows.append(next(r for r in d_rows if r["name"] == wanted))
    if valid_d:
        best_d = valid_d[0]
        if best_d["name"] not in {r["name"] for r in key_rows}:
            key_rows.append(best_d)

    # E: calendar layer plus the most trade-preserving valid A candidate.
    if valid_a:
        best_a = valid_a[0]
        rolling_kept = {
            t.session_date
            for t in rolling_wr_filter(trades, int(best_a["N"]), best_a["X"] / 100)
        }
        combined = [
            t
            for t in trades
            if t.session_date in rolling_kept
            and t.session_date not in FOMC_DATES
            and t.session_date not in JH_2025_BENCHMARK
        ]
        key_rows.append(
            strategy_summary(
                f"E_calendar+N{best_a['N']}_X{best_a['X']}",
                events_from_trades(combined),
                trades,
            )
        )

    print("\nKEY RESULTS")
    print(
        fmt(
            key_rows,
            [
                "name",
                "n",
                "wr",
                "windows",
                "pass_pct",
                "blow_pct",
                "max_sl",
                "ev_week",
            ],
        )
    )
    print(f"\nVALID A CONFIGS: {len(valid_a)}")
    if valid_a:
        print(
            fmt(
                valid_a[:20],
                ["name", "N", "X", "n", "wr", "pass_pct", "blow_pct", "max_sl", "ev_week"],
            )
        )
    print(f"\nVALID D CONFIGS: {len(valid_d)}")
    if valid_d:
        print(
            fmt(
                valid_d[:20],
                ["name", "mode", "K", "D", "n", "wr", "pass_pct", "blow_pct", "max_sl", "ev_week"],
            )
        )

    print("\nRISK GOVERNOR (challenge-local)")
    governor_rows = []
    for reserve in (0.0, 164.0, 300.0, 492.0):
        row = {"reserve": reserve, **risk_governor_window_summary(trades, reserve)}
        governor_rows.append(row)
    print(
        fmt(
            governor_rows,
            [
                "reserve",
                "windows",
                "pass_pct",
                "blow_pct",
                "max_sl",
                "mean_executions_per_window",
                "mean_window_ev_week",
            ],
        )
    )


if __name__ == "__main__":
    main()
