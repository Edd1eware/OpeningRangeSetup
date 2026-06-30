"""Recorre fechas en Replay X10 con el Execution Manager (strategy) ACTIVO.

El exporter publica la senal A+ Speed -> la ChartStrategy entra y gestiona. Este
runner solo MANEJA el Replay (configura rango, Play, espera, Stop) reusando el
motor existente. Los trades reales los coloca la estrategia en ATAS.

Requisitos antes de correr:
  1. ATAS abierto, chart con: Exporter + Visual + Strategy en "Started".
  2. Replay visible y al frente. Manos fuera del mouse/teclado.

Uso:
  python 06_run_strategy_replay.py              # solo las fechas A+ Speed (39, donde opera)
  python 06_run_strategy_replay.py --all        # todas las sesiones sincronizadas
  python 06_run_strategy_replay.py --databento-all  # mismas fechas del runner 04, Strategy real
  python 06_run_strategy_replay.py --dates 2026-05-15 2026-06-23
"""

import argparse
import atexit
import csv
import datetime as dt
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import replay_sync_runner_common_after_sync as rs
import telegram_run_summary_after_sync as telegram
import time_zones_atas

LADDER_ROOT = (
    rs.RESULTS_FOLDER / "visual_tests" / "sync_ladder_runs" / "sync_v11_ladder_001_resume"
)
OUTPUT = rs.RESULTS_FOLDER / "visual_tests" / "strategy_tester_results"
OPER = rs.OPERATIVA_COMPARISON_FIELDS
SESSION_STATUS = OUTPUT / "strategy_session_status.txt"
EXECUTION_TELEGRAM_FLAG = rs.RESULTS_FOLDER / "execution_manager_telegram_mode.flag"
DATABENTO_RAW_DIR = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn"
)


def _row(path):
    try:
        return next(csv.DictReader(open(path, encoding="utf-8-sig")), None)
    except Exception:
        return None


def synced_dates(aplus_only):
    """Fechas sincronizadas (X1==X10). Si aplus_only, solo las A+ Speed."""
    out = []
    for x1 in LADDER_ROOT.glob("*/X1_R1/score_trade_result_*_NY.csv"):
        d = re.search(r"(\d{4}-\d{2}-\d{2})", x1.name).group(1)
        if d in out:
            continue
        x10 = x1.parent.parent / "X10_R1" / x1.name
        if not x10.exists():
            continue
        r1, r10 = _row(x1), _row(x10)
        if not r1 or not r10:
            continue
        if not all(str(r1.get(f, "") or "").strip() == str(r10.get(f, "") or "").strip() for f in OPER):
            continue
        if aplus_only and str(r10.get("APlus_Speed", "")).strip().upper() != "TRUE":
            continue
        out.append(d)
    return sorted(set(out))


def _market_closed(year):
    def _nth(yr, mo, wd, n):
        d = date(yr, mo, 1)
        d += timedelta((wd - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)

    def _last(yr, mo, wd):
        import calendar
        d = date(yr, mo, calendar.monthrange(yr, mo)[1])
        return d - timedelta((d.weekday() - wd) % 7)

    def _observed(d):
        if d.weekday() == 5:
            return d - timedelta(days=1)
        if d.weekday() == 6:
            return d + timedelta(days=1)
        return d

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    good_friday = date(year, month, day) - timedelta(days=2)

    return {
        _observed(date(year, 1, 1)),
        _nth(year, 1, 0, 3),
        _nth(year, 2, 0, 3),
        good_friday,
        _last(year, 5, 0),
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth(year, 9, 0, 1),
        _nth(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
        date(2025, 1, 9),
    }


def databento_dates():
    """Same eligible DataBento sessions used by runner 04, for real Strategy validation."""
    if not DATABENTO_RAW_DIR.exists():
        raise FileNotFoundError(f"raw_dbn no encontrado: {DATABENTO_RAW_DIR}")

    closed = {}
    out = []
    for folder in sorted(DATABENTO_RAW_DIR.iterdir()):
        if not folder.is_dir():
            continue
        try:
            session = date.fromisoformat(folder.name)
        except ValueError:
            continue
        if session.weekday() >= 5:
            continue
        closed.setdefault(session.year, _market_closed(session.year))
        if session in closed[session.year]:
            continue
        out.append(folder.name)
    return out


def _wait_for_strategy_terminal(date_iso, started_at, timeout_seconds, _stop_button):
    """Wait for the real ExecutionManager, not merely the exporter CSV."""
    terminal = {
        "COMPLETE",
        "NO_SIGNAL",
        "SKIPPED_NOT_APLUS",
        "SKIPPED_REGIME",
        "SKIPPED_GOVERNOR",
    }
    deadline = started_at + timeout_seconds
    while time.time() < deadline:
        try:
            if SESSION_STATUS.exists() and SESSION_STATUS.stat().st_mtime >= started_at:
                parts = SESSION_STATUS.read_text(encoding="utf-8-sig").strip().split(",")
                if len(parts) >= 2 and parts[0] == date_iso and parts[1] in terminal:
                    print(f"ExecutionManager terminal: {date_iso} -> {parts[1]}")
                    return True, ""
        except OSError:
            pass
        time.sleep(0.25)
    return False, "STRATEGY_TERMINAL_TIMEOUT"


def _enable_execution_manager_telegram_mode():
    """Suppress exporter TP/SL Telegram while this Strategy runner is alive."""
    EXECUTION_TELEGRAM_FLAG.write_text(str(os.getpid()), encoding="ascii")

    def cleanup():
        try:
            if EXECUTION_TELEGRAM_FLAG.exists():
                current = EXECUTION_TELEGRAM_FLAG.read_text(encoding="ascii").strip()
                if current == str(os.getpid()):
                    EXECUTION_TELEGRAM_FLAG.unlink()
        except OSError:
            pass

    atexit.register(cleanup)
    return cleanup


def _load_strategy_rows(trades_log):
    if not trades_log.exists():
        return []
    try:
        with open(trades_log, encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []


def _operation_pnls(rows):
    """Aggregate split legs into one operation per session for WR/trade counts."""
    out = {}
    for row in rows:
        session = row.get("fecha") or ""
        if not session:
            continue
        try:
            pnl = float(row.get("pnl_usd") or 0)
        except (TypeError, ValueError):
            pnl = 0.0
        out[session] = out.get(session, 0.0) + pnl
    return out


def _format_remaining_hhmm(seconds):
    """Real wall-clock time remaining, rounded up to the next minute."""
    total_minutes = max(0, int((seconds + 59) // 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _eta_line(started_monotonic, processed, total):
    """ETA based on actual wall-clock time consumed by this run."""
    if processed <= 0:
        return f"Progreso: 0/{total} | tiempo restante calculando..."
    elapsed = max(0.0, time.monotonic() - started_monotonic)
    remaining = (elapsed / processed) * max(0, total - processed)
    return f"Progreso: {processed}/{total} | tiempo restante {_format_remaining_hhmm(remaining)}"


def _send_strategy_trade_message(date_iso, rows_before, trades_log, eta_line=""):
    rows = _load_strategy_rows(trades_log)
    new_rows = [r for r in rows[rows_before:] if (r.get("fecha") or "") == date_iso]
    if not new_rows:
        try:
            status_parts = SESSION_STATUS.read_text(encoding="utf-8-sig").strip().split(",")
        except OSError:
            status_parts = []
        if len(status_parts) >= 2 and status_parts[1] in {
            "NO_SIGNAL",
            "SKIPPED_NOT_APLUS",
            "SKIPPED_REGIME",
            "SKIPPED_GOVERNOR",
        }:
            reason = {
                "NO_SIGNAL": "Sin señal válida",
                "SKIPPED_NOT_APLUS": "No A+ Speed",
                "SKIPPED_REGIME": "Régimen pausado",
                "SKIPPED_GOVERNOR": "Risk Governor",
            }[status_parts[1]]
            telegram.send_text(
                rs.RESULTS_FOLDER,
                f"EW ORB NQ | ExecutionManager\n{date_iso}\n"
                f"{status_parts[1]} | {reason}"
                + (f"\n{eta_line}" if eta_line else ""),
            )
            return True
        return False

    def number(row, key):
        try:
            return float(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    def money(value):
        return f"+${value:,.0f}" if value >= 0 else f"-${abs(value):,.0f}"

    operation_pnl = sum(number(r, "pnl_usd") for r in new_rows)
    cumulative_pnl = sum(number(r, "pnl_usd") for r in rows)
    balance = telegram.INITIAL_BALANCE + cumulative_pnl
    side = new_rows[0].get("side") or ""
    total_contracts = sum(int(number(r, "contratos")) for r in new_rows)

    lines = [
        "EW ORB NQ | ExecutionManager",
        date_iso,
        f"{side} | {total_contracts} contratos",
    ]
    for row in new_rows:
        reason = (row.get("exit_motivo") or "CLOSE").upper()
        label = {
            "TP_SPLIT": "TP fijo",
            "RUNNER_CLOSE": "Runner",
            "CLOSE": "SL/Cierre",
        }.get(reason, reason.replace("_", " ").title())
        contracts = int(number(row, "contratos"))
        ticks = number(row, "ticks")
        pnl = number(row, "pnl_usd")
        lines.append(
            f"{label}: {contracts}c | {ticks:+.0f}t | {money(pnl)}"
        )
    lines.extend([
        f"PnL operación: {money(operation_pnl)}",
        f"Balance: ${balance:,.0f}",
    ])
    if eta_line:
        lines.append(eta_line)
    telegram.send_text(rs.RESULTS_FOLDER, "\n".join(lines))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Todas las sesiones (no solo A+ Speed).")
    parser.add_argument(
        "--databento-all",
        action="store_true",
        help="Todas las fechas DataBento del runner 04, pero validando el ExecutionManager real.",
    )
    parser.add_argument("--dates", nargs="*", help="Fechas especificas YYYY-MM-DD.")
    parser.add_argument("--prepare-only", action="store_true", help="Muestra las fechas sin correr.")
    args = parser.parse_args()

    if args.dates:
        dates = sorted(set(args.dates))
    elif args.databento_all:
        dates = databento_dates()
    else:
        dates = synced_dates(aplus_only=not args.all)

    print(f"Fechas a recorrer en Replay X10 (estrategia activa): {len(dates)}")
    for d in dates:
        print(" ", d)
    if args.prepare_only:
        print("\nPREPARE-ONLY. No se inicio Replay.")
        return 0

    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Solo X10 (la estrategia opera en X10). force=True -> re-corre cada fecha.
    run_plan = [("X10_R1", "X10", rs.X10_TIMEOUT_SECONDS)]
    # progress_meta -> Telegram con ETA exacto por fecha (mediana de la X10 medida)
    # y alerta de error si fallan varias seguidas. Sin meta de 500 (no aplica).
    trades_log = OUTPUT / "strategy_tester_trades.csv"
    # Reset del log: force=True re-corre todas las fechas y la strategy APPENDEA,
    # asi que se respalda/limpia el log para que el PnL no se duplique.
    if trades_log.exists():
        backup = trades_log.with_name(
            f"strategy_tester_trades_prev_{int(trades_log.stat().st_mtime)}.csv"
        )
        trades_log.replace(backup)
        print(f"Log previo respaldado: {backup.name}")

    cleanup_telegram_mode = _enable_execution_manager_telegram_mode()
    telegram.set_bot_name(rs.RESULTS_FOLDER, "EW ORB NQ")
    telegram.clear_telegram_before_run(rs.RESULTS_FOLDER)

    telegram.send_text(
        rs.RESULTS_FOLDER,
        "EW ORB NQ | ExecutionManager iniciado\n"
        f"{len(dates)} fechas en Replay X10 con la estrategia activa.\n"
        "Telegram mostrará operaciones reales 3+2, NO_SIGNAL y skips de los filtros.\n"
        "El tiempo restante real se calculará después de la primera fecha.",
    )

    sig_file = rs.RESULTS_FOLDER / "pending_strategy_signal.txt"

    def _print_date_summary(date_str, idx, total, eta_line=""):
        rows = []
        if trades_log.exists():
            try:
                rows = list(csv.DictReader(open(trades_log, encoding="utf-8-sig")))
            except Exception:
                pass
        sig_status = ""
        if sig_file.exists():
            try:
                sig_status = sig_file.read_text().strip().split(",")[-1]
            except Exception:
                pass
        operations = _operation_pnls(rows)
        wins   = sum(1 for pnl in operations.values() if pnl > 0)
        losses = sum(1 for pnl in operations.values() if pnl < 0)
        total_pnl = sum(float(r.get("pnl_usd") or 0) for r in rows)
        wr = f"{wins/(wins+losses)*100:.0f}%" if (wins+losses) else "N/A"
        print(
            f"[{idx:>2}/{total}] {date_str} | "
            f"signal={sig_status or 'N/A':<8} | "
            f"trades={len(operations):>2} | wins={wins} losses={losses} WR={wr} | "
            f"PnL=${total_pnl:,.0f}"
        )
        if eta_line:
            print(f"           {eta_line}")

    failures = []
    last_tz = None
    run_started_monotonic = time.monotonic()
    for i, date in enumerate(dates, 1):
        try:
            rows_before = len(_load_strategy_rows(trades_log))
            session = dt.date.fromisoformat(date)
            tz_offset = time_zones_atas.get_utc_offset(session)
            if tz_offset != last_tz:
                print(f"Configurando CME en UTC{tz_offset} antes de {date}...")
                time_zones_atas.ensure_atas_timezone(tz_offset)
                last_tz = tz_offset

            SESSION_STATUS.unlink(missing_ok=True)
            # Clear any leftover signal from a previous date. The exporter writes a
            # fresh PENDING during this run; a stale PENDING from an earlier session
            # would otherwise linger on disk (e.g. an unconsumed neighbor date) and
            # confuse the handshake / per-date summary.
            sig_file.unlink(missing_ok=True)

            _, date_failures = rs.run_replay_period(
                [date],
                output_folder=OUTPUT,
                run_plan=run_plan,
                report_prefix="strategy_replay_test",
                force=True,
                replay_to_time=rs.DEFAULT_REPLAY_TO_TIME,
                post_result_waiter=_wait_for_strategy_terminal,
                progress_meta=None,
            )
            failures.extend(date_failures)
        except KeyboardInterrupt:
            telegram.send_text(rs.RESULTS_FOLDER, "EW ORB NQ | Recorrido cancelado (Ctrl+C).")
            _print_date_summary(date, i, len(dates), _eta_line(run_started_monotonic, i - 1, len(dates)))
            raise
        except Exception as exc:
            telegram.send_text(
                rs.RESULTS_FOLDER,
                "EW ORB NQ | ERROR FATAL\n"
                f"{exc}\nREINICIA ATAS/Replay, ventana al frente, y relanza el runner.",
            )
            _print_date_summary(date, i, len(dates), _eta_line(run_started_monotonic, i - 1, len(dates)))
            raise
        eta_line = _eta_line(run_started_monotonic, i, len(dates))
        sent_result = _send_strategy_trade_message(date, rows_before, trades_log, eta_line)
        _print_date_summary(date, i, len(dates), eta_line)

        if not sent_result and (i == 1 or i % 10 == 0) and i < len(dates):
            current_rows = _load_strategy_rows(trades_log)
            cumulative = sum(float(r.get("pnl_usd") or 0) for r in current_rows)
            telegram.send_text(
                rs.RESULTS_FOLDER,
                "EW ORB NQ | ExecutionManager\n"
                f"{eta_line}\n"
                f"Balance: ${telegram.INITIAL_BALANCE + cumulative:,.0f}",
            )

    # Never synthesize Strategy trades from the exporter. That would validate the
    # fixed TP/SL pipeline instead of the ExecutionManager we are testing.
    if not trades_log.exists() or trades_log.stat().st_size < 50:
        msg = (
            "ERROR: ExecutionManager no produjo strategy_tester_trades.csv. "
            "No se usarán resultados del exporter como sustituto. Verifica que la "
            "Strategy esté agregada al chart, Started y con la DLL actual."
        )
        print(f"\n{msg}")
        telegram.send_text(rs.RESULTS_FOLDER, f"EW Opening Range | {msg}")
        return 2

    fail_n = len(failures)
    # PnL real + contratos del log de la estrategia.
    pnl_line = ""
    if trades_log.exists():
        try:
            log_rows = list(csv.DictReader(open(trades_log, encoding="utf-8-sig")))
            if log_rows:
                total_pnl = sum(float(r.get("pnl_usd") or 0) for r in log_rows)
                operations = _operation_pnls(log_rows)
                last_date = log_rows[-1].get("fecha") or ""
                contracts = sum(
                    int(float(r.get("contratos") or 0))
                    for r in log_rows if (r.get("fecha") or "") == last_date
                )
                wins = sum(1 for pnl in operations.values() if pnl > 0)
                losses = sum(1 for pnl in operations.values() if pnl < 0)
                wr = wins / (wins + losses) * 100 if (wins + losses) else 0
                pnl_line = (
                    f"Trades estrategia: {len(operations)} | {contracts} contratos | "
                    f"WR {wr:.0f}% | PnL TOTAL ${total_pnl:,.0f}"
                )
        except Exception:
            pass
    msg = [
        "EW ORB NQ | ExecutionManager terminado",
        f"Fechas: {len(dates)} | con problemas: {fail_n}",
    ]
    if pnl_line:
        msg.append(pnl_line)
    if fail_n:
        msg.append("Fechas con error (re-corre solo esas relanzando):")
        msg += [f"- {d} {run}: {reason}" for d, run, reason in failures[:10]]
        if fail_n > 10:
            msg.append(f"... y {fail_n - 10} mas.")
        msg.append("Si muchas fallaron juntas: reinicia el Replay/ATAS.")
    msg.append("Revisa el P&L / trades de la estrategia en ATAS.")
    telegram.send_text(rs.RESULTS_FOLDER, "\n".join(msg))
    cleanup_telegram_mode()

    print("\nRecorrido terminado. Revisa el P&L / trades de la estrategia en ATAS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
