"""Reemplaza avisos terminales de la DLL activa por mensajes con ETA global.

La DLL ya cargada no puede leer el nuevo archivo ETA hasta reiniciar ATAS. Este
monitor reserva las fechas aún pendientes para evitar el aviso legado y envía el
mismo resultado desde el CSV terminal, agregando el tiempo restante completo.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import replay_sync_runner_common_after_sync as replay_sync
from post_run_born_bad_coordinator import OUTPUT_FOLDER, RESULTS_FOLDER, _all_dates
from telegram_run_summary_after_sync import send_text
from windows_run_awake import process_is_active


SENT_DATES_FILE = RESULTS_FOLDER / "telegram_sent_dates.txt"
RESERVED_DATES_FILE = RESULTS_FOLDER / "telegram_eta_reserved_dates.txt"
ETA_SENT_DATES_FILE = RESULTS_FOLDER / "telegram_eta_terminal_sent_dates.txt"
BALANCE_FILE = RESULTS_FOLDER / "telegram_balance.json"
CONTRACTS = 6
TICK_VALUE_USD = 5.0
STARTING_BALANCE = 150000.0
POST_REPLAY_ANALYSIS_SECONDS = 15 * 60


def _read_lines(path: Path) -> set[str]:
    try:
        return {line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()}
    except (FileNotFoundError, OSError, UnicodeError):
        return set()


def _append_lines(path: Path, values: list[str]) -> None:
    if not values:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for value in values:
            handle.write(value + "\n")


def _read_row(date_iso: str) -> dict[str, str] | None:
    path = OUTPUT_FOLDER / "X10_R1" / f"score_trade_result_{date_iso}_NY.csv"
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return next(csv.DictReader(handle), None)
    except (FileNotFoundError, OSError, UnicodeError, csv.Error):
        return None


def _current_missing(all_dates: list[str]) -> set[str]:
    return {
        date_iso
        for date_iso in all_dates
        if not replay_sync.is_saved_run_complete(OUTPUT_FOLDER, date_iso, "X10_R1")
    }


def _number(value, default=0.0) -> float:
    try:
        return float(str(value or "").replace("+", ""))
    except (TypeError, ValueError):
        return default


def _balance() -> float:
    try:
        values = json.loads(BALANCE_FILE.read_text(encoding="utf-8-sig"))
        return STARTING_BALANCE + sum(float(value) for value in values.values())
    except (FileNotFoundError, OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return STARTING_BALANCE


def _format_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _message(date_iso: str, row: dict[str, str], remaining: int, eta: float) -> str:
    timer = (
        f"Tiempo restante corrida completa: {_format_eta(eta)} | "
        f"Pendientes X10: {remaining}"
    )
    result = str(row.get("Result_Label", "")).strip().upper()
    if result in {"TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        label = "TIME OVER" if result == "TIME_OVER" else result
        return (
            f"OR ABSORTION TEST | {date_iso}\n{label}\n"
            f"Balance: ${_balance():,.0f}\n{timer}"
        )

    ticks = _number(row.get("result TP SL BE"))
    pnl = ticks * TICK_VALUE_USD * CONTRACTS
    side = row.get("Side", "")
    entry_time = row.get("EntryTime_NY", "")
    initial_tp = row.get("Initial_TP_ticks") or row.get("TP_ticks", "")
    initial_sl = row.get("Initial_SL_ticks") or row.get("SL_ticks", "")
    initial_rr = row.get("Initial_RR", "")
    final_tp = row.get("Final_TP_ticks") or row.get("TP_ticks", "")
    final_sl = row.get("Final_SL_ticks") or row.get("SL_ticks", "")
    exit_reason = row.get("Exit_Reason") or result
    return "\n".join(
        [
            f"OR ABSORTION TEST | {date_iso}",
            f"{side} | {entry_time} NY",
            f"Plan inicial: TP {initial_tp} | SL {initial_sl} | RR {initial_rr}",
            f"Bracket final: TP {final_tp} | SL {final_sl}",
            f"Salida: {exit_reason} {ticks:+g} ticks",
            f"MAE: {row.get('MAE_ticks', '')} ticks | MFE: {row.get('MFE_ticks', '')} ticks",
            f"PnL: ${pnl:+,.0f} | {CONTRACTS}c",
            f"Balance: ${_balance():,.0f}",
            f"Duración: {row.get('Trade_Duration', '')}",
            timer,
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-pid", type=int, required=True)
    parser.add_argument("--runner-log", type=Path, required=True)
    parser.add_argument("--initial-missing", type=int, required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--from-date", default="")
    parser.add_argument("--to-date", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_dates = [
        date_iso
        for date_iso in _all_dates()
        if (not args.from_date or date_iso >= args.from_date)
        and (not args.to_date or date_iso <= args.to_date)
    ]
    current_missing = _current_missing(all_dates)
    reserved = _read_lines(RESERVED_DATES_FILE) | current_missing
    already_reserved = _read_lines(SENT_DATES_FILE)
    new_reservations = sorted(reserved - already_reserved)
    _append_lines(SENT_DATES_FILE, new_reservations)
    _append_lines(RESERVED_DATES_FILE, sorted(current_missing - _read_lines(RESERVED_DATES_FILE)))
    sent = _read_lines(ETA_SENT_DATES_FILE)
    started_at = args.runner_log.stat().st_ctime
    print(
        f"TERMINAL_ETA_MONITOR_READY reserved={len(reserved)} new={len(new_reservations)}",
        flush=True,
    )

    while process_is_active(args.runner_pid) or any(date not in sent for date in reserved):
        missing_now = _current_missing(all_dates)
        completed_count = max(0, args.initial_missing - len(missing_now))
        elapsed = max(1.0, time.time() - started_at)
        avg_seconds = elapsed / completed_count if completed_count else 97.0
        eta = len(missing_now) * avg_seconds + POST_REPLAY_ANALYSIS_SECONDS
        completed_unsent = sorted(
            date for date in reserved if date not in missing_now and date not in sent
        )
        for date_iso in completed_unsent:
            row = _read_row(date_iso)
            if row is None:
                continue
            if send_text(RESULTS_FOLDER, _message(date_iso, row, len(missing_now), eta)):
                _append_lines(ETA_SENT_DATES_FILE, [date_iso])
                sent.add(date_iso)
                print(
                    f"ETA_TERMINAL_SENT date={date_iso} remaining={len(missing_now)} "
                    f"eta={_format_eta(eta)}",
                    flush=True,
                )
        if not process_is_active(args.runner_pid) and not completed_unsent:
            break
        time.sleep(max(0.1, args.poll_seconds))
    print("TERMINAL_ETA_MONITOR_EXIT", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
