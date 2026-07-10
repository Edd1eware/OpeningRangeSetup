"""Recorrido causal de Market Replay para el estudio LVN del primer minuto.

NO ejecuta una estrategia ni preescribe senales. En cada fecha:
  1) Replay X10 08:29-09:42 ET.
  2) Volume_Profile_Eddieware exporta footprint CERRADO 08:30-09:40.
  3) Se valida lvn_research_done_YYYY-MM-DD.txt + CSV con datos.
  4) Al terminar, detect_lvn_retest_events.py genera Excel + CSV agregados.

Uso principal:
  python -u lvn_OR_strategy_replay.py --all \
    --from-date 2025-03-10 --to-date 2026-07-06

Requisitos:
  - ATAS abierto, Replay visible, chart NQ de 1 MINUTO.
  - Indicador Volume_Profile_Eddieware aplicado con Research Export habilitado.
  - No hace falta iniciar Execution Manager ni ninguna estrategia.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from progress import ProgressBar


ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator")
RAW_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\lvn_research_raw")
RESULTS_DIR = DATA_ROOT / "trade_results_score"
LADDER_ROOT = RESULTS_DIR / "visual_tests" / "sync_ladder_runs" / "sync_v11_ladder_001_resume"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "lvn_or_strategy_replay"
DETECTOR = ROOT / "detect_lvn_retest_events.py"
# Ventana corta por default (2026-07-08): el contexto 08:30-09:30 se lee de las
# barras históricas que ATAS ya carga al iniciar el replay; solo se replaya desde
# 09:29. Usa --replay-from 08:29 para volver a la ventana completa (paridad/debug).
# Fin en 10:00 (colchón extra sobre retest_end=09:40) para dar más margen de
# analisis manual antes de que el runner corte la captura.
REPLAY_FROM_TIME = "09:29"
REPLAY_TO_TIME = "10:00"
DEFAULT_TIMEOUT_SECONDS = 15 * 60
RAW_HEADER_REQUIRED = {"timestamp", "price", "bid_volume", "ask_volume", "volume"}
rs = None
atas_process_guard = None


def load_replay_dependencies() -> None:
    """Carga UIA solo cuando realmente se va a manejar ATAS.

    --help, --prepare-only y --report-only siguen funcionando aunque pywin32/UIA
    no esté instalado correctamente.
    """
    global rs, atas_process_guard
    if rs is not None:
        return
    try:
        import atas_process_guard as process_guard
        import replay_sync_runner_common_after_sync as replay_common
    except Exception as exc:
        raise RuntimeError(
            "No pude cargar la automatización de ATAS (pywinauto/pywin32). "
            "El runner 06 original también depende de ella. "
            f"Detalle: {type(exc).__name__}: {exc}"
        ) from exc
    rs = replay_common
    atas_process_guard = process_guard


def raw_path(date_iso: str) -> Path:
    return RAW_DIR / f"lvn_research_raw_{date_iso}_NY.csv"


def done_path(date_iso: str) -> Path:
    return RAW_DIR / f"lvn_research_done_{date_iso}.txt"


def _extract_date(path: Path) -> str | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else None


def discover_result_dates() -> list[str]:
    """Universo no-A+: toda fecha con resultado disponible, sin filtrar trades."""
    dates: set[str] = set()
    for path in RESULTS_DIR.glob("score_trade_result_*_NY.csv"):
        date_iso = _extract_date(path)
        if date_iso:
            dates.add(date_iso)
    for path in LADDER_ROOT.glob("*/X1_R1/score_trade_result_*_NY.csv"):
        date_iso = _extract_date(path)
        if date_iso:
            dates.add(date_iso)
    return sorted(dates)


def weekday_dates(start: str, end: str) -> list[str]:
    current = datetime.strptime(start, "%Y-%m-%d").date()
    finish = datetime.strptime(end, "%Y-%m-%d").date()
    dates: list[str] = []
    while current <= finish:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian computus.
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(holiday: date) -> date | None:
    # NYSE observance: Saturday -> Friday before; Sunday -> Monday after.
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def us_market_holidays(year: int) -> set[str]:
    """Feriados NYSE/CME equity index sin sesión RTH normal 09:30 ET."""
    holidays: set[date] = set()
    for fixed in (date(year, 1, 1), date(year, 6, 19), date(year, 7, 4), date(year, 12, 25)):
        observed = _observed(fixed)
        if observed is not None and observed.year == year:
            holidays.add(observed)
    holidays.add(_nth_weekday(year, 1, 0, 3))        # MLK: 3er lunes enero
    holidays.add(_nth_weekday(year, 2, 0, 3))        # Presidents: 3er lunes febrero
    holidays.add(_easter_sunday(year) - timedelta(days=2))  # Good Friday
    holidays.add(_last_weekday(year, 5, 0))          # Memorial: último lunes mayo
    holidays.add(_nth_weekday(year, 9, 0, 1))        # Labor: 1er lunes septiembre
    holidays.add(_nth_weekday(year, 11, 3, 4))       # Thanksgiving: 4o jueves noviembre
    return {value.isoformat() for value in holidays}


def filter_trading_days(dates: list[str]) -> tuple[list[str], list[str]]:
    holidays: set[str] = set()
    for year in {int(value[:4]) for value in dates}:
        holidays |= us_market_holidays(year)
    kept = [value for value in dates if value not in holidays]
    skipped = sorted(value for value in dates if value in holidays)
    return kept, skipped


def select_dates(args: argparse.Namespace) -> list[str]:
    if args.dates:
        dates = sorted(set(args.dates))
    elif args.date_source == "weekdays":
        if not args.from_date or not args.to_date:
            raise ValueError("--date-source weekdays requiere --from-date y --to-date")
        dates = weekday_dates(args.from_date, args.to_date)
    else:
        dates = discover_result_dates()
    if args.from_date:
        dates = [date_iso for date_iso in dates if date_iso >= args.from_date]
    if args.to_date:
        dates = [date_iso for date_iso in dates if date_iso <= args.to_date]
    if not args.include_holidays:
        dates, skipped = filter_trading_days(dates)
        if skipped:
            print(f"Feriados de mercado excluidos ({len(skipped)}): {', '.join(skipped)}")
    return dates


def inspect_capture(date_iso: str, started_at: float | None = None) -> dict[str, object]:
    csv_path = raw_path(date_iso)
    marker = done_path(date_iso)
    info: dict[str, object] = {
        "date": date_iso,
        "csv": str(csv_path),
        "marker": str(marker),
        "complete": False,
        "rows": 0,
        "reason": "MISSING_FILES",
    }
    if not csv_path.exists() or not marker.exists():
        return info
    if started_at is not None and (csv_path.stat().st_mtime < started_at or marker.stat().st_mtime < started_at):
        info["reason"] = "STALE_FILES"
        return info
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            if not RAW_HEADER_REQUIRED.issubset(headers):
                info["reason"] = "INVALID_HEADER"
                info["headers"] = sorted(headers)
                return info
            row_count = 0
            first_timestamp = last_timestamp = ""
            for row in reader:
                row_count += 1
                timestamp = str(row.get("timestamp", ""))
                if not first_timestamp:
                    first_timestamp = timestamp
                last_timestamp = timestamp
        context_ok = bool(first_timestamp) and first_timestamp[11:16] <= "08:35"
        info.update({
            "rows": row_count,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "context_ok": context_ok,
        })
        if row_count <= 0:
            info["reason"] = "NO_DATA_ROWS"
            return info
        marker_text = marker.read_text(encoding="utf-8-sig", errors="replace")
        if f"date={date_iso}" not in marker_text:
            info["reason"] = "INVALID_MARKER"
            return info
        info["complete"] = True
        info["reason"] = "OK"
        return info
    except Exception as exc:
        info["reason"] = f"{type(exc).__name__}: {exc}"
        return info


def clean_capture(date_iso: str) -> None:
    raw_path(date_iso).unlink(missing_ok=True)
    done_path(date_iso).unlink(missing_ok=True)


def run_capture_date(date_iso: str, timeout_seconds: int) -> tuple[bool, str, dict[str, object]]:
    if rs is None:
        raise RuntimeError("Dependencias Replay no cargadas")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    clean_capture(date_iso)
    rs.write_runtime_markers(date_iso)
    replay = from_box = to_box = start_button = stop_button = None
    try:
        replay, from_box, to_box, start_button, stop_button = rs.get_replay_controls()
        rs.configure_replay_range(
            from_box,
            to_box,
            date_iso,
            replay_from_time=REPLAY_FROM_TIME,
            replay_to_time=REPLAY_TO_TIME,
        )
        replay.set_focus()
        time.sleep(0.5)
        print(f"Iniciando captura LVN X10 {date_iso} ({REPLAY_FROM_TIME}-{REPLAY_TO_TIME})...")
        started_at = rs.start_replay_with_retries(
            raw_path(date_iso),
            done_path(date_iso),
            from_box,
            to_box,
            date_iso,
            REPLAY_FROM_TIME,
            REPLAY_TO_TIME,
            start_button,
            stop_button,
        )
        if started_at is None:
            return False, "REPLAY_NOT_STARTED", inspect_capture(date_iso)

        wait_started = time.time()
        last_second = -1
        while time.time() - wait_started < timeout_seconds:
            capture = inspect_capture(date_iso, started_at=started_at)
            if capture["complete"]:
                print(
                    f"\rCaptura completa {date_iso}: {capture['rows']} filas | "
                    f"{capture.get('first_timestamp', '')} -> {capture.get('last_timestamp', '')}" + " " * 20
                )
                time.sleep(0.4)
                rs.click_stop(stop_button)
                return True, "", capture
            elapsed = int(time.time() - wait_started)
            if elapsed != last_second:
                remaining = max(0, timeout_seconds - elapsed)
                print(
                    f"\rEsperando footprint+marker {date_iso}: "
                    f"{elapsed // 60:02d}:{elapsed % 60:02d} / resta "
                    f"{remaining // 60:02d}:{remaining % 60:02d} | {capture['reason']}",
                    end="",
                    flush=True,
                )
                last_second = elapsed
            if elapsed > 15 and not rs.replay_is_playing(start_button, stop_button):
                print()
                return False, "REPLAY_STOPPED_BEFORE_RESEARCH_MARKER", capture
            time.sleep(rs.POLL_SECONDS)
        print()
        return False, "TIMEOUT_WAITING_RESEARCH_MARKER", inspect_capture(date_iso)
    finally:
        rs.click_stop(stop_button)


def detector_command(args: argparse.Namespace, report_path: Path, report_dates: list[str]) -> list[str]:
    command = [
        sys.executable,
        str(DETECTOR),
        "--input",
        str(RAW_DIR / "lvn_research_raw_*_NY.csv"),
        "--output",
        str(report_path),
        "--symbol",
        args.symbol,
        "--tick-size",
        str(args.tick_size),
        "--lvn-neighbor-levels",
        str(args.lvn_neighbor_levels),
        "--lvn-max-percent-of-neighbors",
        str(args.lvn_max_percent_of_neighbors),
        "--min-total-volume-at-profile",
        str(args.min_total_volume_at_profile),
        "--min-lvn-volume",
        str(args.min_lvn_volume),
        "--max-lvn-volume-percent-of-poc",
        str(args.max_lvn_volume_percent_of_poc),
        "--retest-tolerance-ticks",
        str(args.retest_tolerance_ticks),
    ]
    if report_dates:
        command.extend(["--dates", *report_dates])
    return command


def default_report_path(args: argparse.Namespace, dates: list[str]) -> Path:
    start = args.from_date or (dates[0] if dates else "start")
    end = args.to_date or (dates[-1] if dates else "end")
    return DEFAULT_OUTPUT_DIR / f"lvn_retest_DST_{start}_{end}.xlsx"


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def telegram_notify(message: str) -> None:
    """Notificación best-effort; jamás rompe la captura."""
    try:
        from telegram_run_summary_after_sync import _read_credentials, _send_message

        credentials = _read_credentials(str(RESULTS_DIR))
        if credentials:
            _send_message(credentials[0], credentials[1], message)
    except Exception:
        pass


def format_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def quick_session_stats(date_iso: str) -> dict[str, object] | None:
    """LVNs/retests/shape de UNA sesión recién capturada, en memoria, sin escribir archivos."""
    try:
        from lvn_retest_engine.config import ResearchConfig
        from lvn_retest_engine.feature_extractor import session_features
        from lvn_retest_engine.hvn_detector import detect_hvns
        from lvn_retest_engine.io import read_inputs
        from lvn_retest_engine.lvn_detector import detect_lvns
        from lvn_retest_engine.profile_builder import build_profile
        from lvn_retest_engine.retest_detector import detect_retests
        from lvn_retest_engine.shape_classifier import classify_shape

        config = ResearchConfig()
        data, _, _ = read_inputs([str(raw_path(date_iso))], config)
        session_date = data["session_date"].iloc[0]
        frame = data.loc[data["session_date"] == session_date]
        context = build_profile(frame, session_date, "CONTEXT_0830_0930",
                                config.context_profile_start, config.context_profile_end, config)
        minute = build_profile(frame, session_date, "FIRST_MINUTE_0930_0931",
                               config.lvn_profile_start, config.lvn_profile_end, config)
        for profile in (context, minute):
            profile.hvns, _ = detect_hvns(profile, config)
            profile.lvns, _ = detect_lvns(profile, config)
            profile.shape = classify_shape(profile, config)
        features = session_features(frame, context, minute, None, config)
        events, _ = detect_retests(frame, session_date, minute, context, features, config)
        import math as _math
        rr_values = []
        for event in events:
            value = event.get("rr_max_achievable")
            if isinstance(value, (int, float)) and _math.isfinite(float(value)):
                rr_values.append(float(value))
        retested_ids = {str(event["lvn_id"]) for event in events}
        mfe_by_lvn: dict[str, float] = {}
        for event in events:
            value = event.get("mfe_ticks")
            if isinstance(value, (int, float)) and _math.isfinite(float(value)):
                key = str(event["lvn_id"])
                mfe_by_lvn[key] = max(mfe_by_lvn.get(key, 0.0), float(value))
        lvn_lines = []
        for node in minute.lvns[:5]:
            node_id = str(node["lvn_id"])
            mfe_text = f" MFEmax {mfe_by_lvn[node_id]:.0f}t" if node_id in mfe_by_lvn else ""
            lvn_lines.append(
                f"  LVN {float(node['price']):.2f} | ancho {node.get('width_ticks', '?')}t | "
                f"vol {float(node.get('volume', 0)):.0f} | prof {float(node.get('depth', 0)):.2f} | "
                f"{'RETEST' if node_id in retested_ids else 'sin retest'}{mfe_text}"
            )
        return {
            "lvns": len(minute.lvns),
            "retested": len(retested_ids),
            "events": len(events),
            "shape": str(context.shape.get("profile_shape", "?")),
            "interactions": "/".join(sorted({str(e["lvn_interaction"]) for e in events})) or "-",
            "rr_mean": sum(rr_values) / len(rr_values) if rr_values else None,
            "rr_max": max(rr_values) if rr_values else None,
            "rr_min": min(rr_values) if rr_values else None,
            "lvn_lines": lvn_lines,
        }
    except Exception:
        return None


def shape_breakdown(events_csv: Path) -> str:
    """Medición pura por shape (D/P/b/double/trend/unknown): frecuencia y máxima extensión.

    Sin WR/PF (decisión usuario 2026-07-09): primero medir el evento, la estrategia después.
    """
    try:
        import pandas as pd

        events = pd.read_csv(events_csv)
        if "context_profile_shape" not in events.columns:
            return "sin datos de shape"
        events["month"] = pd.to_datetime(events["date"]).dt.to_period("M")
        months = int(events["month"].nunique()) or 1
        lines = []
        for shape, cohort in events.groupby("context_profile_shape", dropna=False):
            mfe = pd.to_numeric(cohort["mfe_ticks"], errors="coerce").dropna()
            if len(mfe) == 0:
                lines.append(f"{shape}: {len(cohort)} eventos, sin MFE medible")
                continue
            lines.append(
                f"{shape}: n={len(cohort)} ({len(cohort) / months:.1f}/mes) | "
                f"MFE med {mfe.median():.0f}t prom {mfe.mean():.0f}t p90 {mfe.quantile(0.9):.0f}t max {mfe.max():.0f}t"
            )
        return "\n".join(sorted(lines))
    except Exception as exc:
        return f"shape breakdown no disponible ({type(exc).__name__})"


def bracket_winrates(events_csv: Path) -> str:
    """WR resuelto por bracket desde LVN_Events.csv, para el mensaje final."""
    try:
        import pandas as pd

        events = pd.read_csv(events_csv)
        parts = []
        for target in (20, 40, 60, 80):
            column = f"tp_sl_{target}_{target}_result"
            if column not in events.columns:
                continue
            result = events[column].astype(str)
            wins, losses = int((result == "TP").sum()), int((result == "SL").sum())
            wr = 100.0 * wins / (wins + losses) if wins + losses else float("nan")
            parts.append(f"{target}/{target}: {wins}W-{losses}L WR {wr:.0f}%")
        return " | ".join(parts) if parts else "sin brackets"
    except Exception as exc:
        return f"WR no disponible ({type(exc).__name__})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--all", action="store_true", help="Todas las fechas disponibles; no filtra A+ ni trades")
    parser.add_argument("--dates", nargs="*", help="Fechas explícitas YYYY-MM-DD")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--date-source", choices=("results", "weekdays"), default="results",
                        help="results evita fines de semana/feriados usando sesiones ya conocidas")
    parser.add_argument("--include-holidays", action="store_true",
                        help="No excluir feriados de mercado US (default: se excluyen)")
    parser.add_argument("--replay-from", default=REPLAY_FROM_TIME,
                        help="Inicio del replay HH:MM ET; 09:29 = ventana corta (contexto desde historia), 08:29 = ventana completa")
    parser.add_argument("--replay-to", default=REPLAY_TO_TIME,
                        help="Fin del replay HH:MM ET")
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=6,
                        help="Aborta la corrida tras N fechas fallidas seguidas (frontera de datos de replay o ATAS caído); 0 = nunca abortar")
    parser.add_argument("--telegram-progress-every", type=int, default=1,
                        help="Manda progreso a Telegram cada N fechas procesadas (default 1 = cada fecha); 0 = sin mensajes de progreso")
    parser.add_argument("--run", action="store_true",
                        help="Ejecuta la captura Replay; sin este flag el script solo hace preview (prepare-only)")
    parser.add_argument("--prepare-only", action="store_true",
                        help="Fuerza preview; es el comportamiento default si no pasas --run ni --report-only")
    parser.add_argument("--report-only", action="store_true", help="No abre Replay; procesa capturas existentes")
    parser.add_argument("--capture-only", action="store_true", help="Captura Replay pero no genera Excel")
    parser.add_argument("--force", action="store_true", help="Repite capturas completas existentes")
    parser.add_argument("--kill-orphans", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output", help="Ruta del reporte .xlsx")
    parser.add_argument("--raw-dir", default=str(RAW_DIR), help="Carpeta compartida con Research Export del indicador")
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--tick-size", type=float, default=0.25)
    parser.add_argument("--lvn-neighbor-levels", type=int, default=2)
    parser.add_argument("--lvn-max-percent-of-neighbors", type=float, default=0.50)
    parser.add_argument("--min-total-volume-at-profile", type=float, default=1.0)
    parser.add_argument("--min-lvn-volume", type=float, default=1.0)
    parser.add_argument("--max-lvn-volume-percent-of-poc", type=float, default=0.50)
    parser.add_argument("--retest-tolerance-ticks", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    global RAW_DIR, REPLAY_FROM_TIME, REPLAY_TO_TIME
    args = build_parser().parse_args(argv)
    RAW_DIR = Path(args.raw_dir).resolve()
    REPLAY_FROM_TIME = args.replay_from
    REPLAY_TO_TIME = args.replay_to
    dates = select_dates(args)
    if not dates and not args.report_only:
        print("ERROR: no hay fechas para recorrer.", file=sys.stderr)
        return 2
    report_path = Path(args.output).resolve() if args.output else default_report_path(args, dates).resolve()

    print(f"Fechas LVN: {len(dates)}")
    if dates:
        print(f"Rango efectivo: {dates[0]} -> {dates[-1]}")
    print(f"Raw footprint: {RAW_DIR}")
    print(f"Ventana Replay: {REPLAY_FROM_TIME}-{REPLAY_TO_TIME} ET (X10)")
    print(f"Reporte final: {report_path}")
    print("IMPORTANTE: chart NQ 1 minuto + Volume_Profile_Eddieware; strategy NO requerida.")
    prepare_only = args.prepare_only or (not args.run and not args.report_only)
    if prepare_only:
        if not args.prepare_only:
            print("Modo preview (default). Para capturar de verdad agrega --run.")
        for date_iso in dates:
            status = inspect_capture(date_iso)
            print(f"  {date_iso} | {'OK' if status['complete'] else status['reason']}")
        return 0

    successes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    started_at = datetime.now().isoformat()
    run_started = time.time()
    data_boundary_reached = False

    if not args.report_only:
        try:
            load_replay_dependencies()
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        atas_process_guard.cleanup_orphan_atas(dry_run=not args.kill_orphans)
        if not rs.set_replay_speed("X10"):
            print("ERROR: no pude fijar Replay X10. Pon Replay al frente y reintenta.", file=sys.stderr)
            return 3
        bar = ProgressBar(len(dates), label="Captura LVN OR")
        consecutive_failures = 0
        captured_rows_total = 0
        if args.telegram_progress_every > 0:
            telegram_notify(
                f"LVN captura INICIO {dates[0]} -> {dates[-1]} | {len(dates)} fechas | "
                f"ventana {REPLAY_FROM_TIME}-{REPLAY_TO_TIME} X10"
            )
        for index, date_iso in enumerate(dates, start=1):
            existing = inspect_capture(date_iso)
            if existing["complete"] and not args.force:
                skipped.append(existing)
                consecutive_failures = 0
                captured_rows_total += int(existing.get("rows", 0) or 0)
                print(f"[{index}/{len(dates)}] {date_iso} SKIP | {existing['rows']} filas")
                bar.update(index)
                continue
            date_started = time.time()
            # Hasta 3 intentos por fecha con 60s de espera: la mayoría de los FAIL son
            # hipos de UI de ATAS (rango no confirmado, foco perdido), no falta de datos.
            attempt = 0
            ok, reason, capture = False, "", {}
            for attempt in range(1, 4):
                try:
                    ok, reason, capture = run_capture_date(date_iso, args.timeout_seconds)
                except KeyboardInterrupt:
                    print("\nRecorrido cancelado por usuario.")
                    raise
                except Exception as exc:
                    ok, reason, capture = False, f"{type(exc).__name__}: {exc}", inspect_capture(date_iso)
                if ok:
                    break
                if attempt < 3:
                    print(f"  {date_iso} intento {attempt}/3 falló ({reason}); reintento en 60s...")
                    time.sleep(60)
            record = {
                **capture,
                "attempts": attempt,
                "elapsed_seconds": round(time.time() - date_started, 3),
                "reason": reason or capture.get("reason", "OK"),
            }
            (successes if ok else failures).append(record)
            if ok and record.get("context_ok") is False:
                print(f"  WARNING {date_iso}: primer row {record.get('first_timestamp')} > 08:35 — "
                      "la historia pre-replay NO trae contexto 08:30-09:30; usa --replay-from 08:29")
            print(f"[{index}/{len(dates)}] {date_iso} | {'OK' if ok else 'FAIL'} | {record['reason']}")
            bar.update(index)
            if ok:
                captured_rows_total += int(record.get("rows", 0) or 0)
            consecutive_failures = 0 if ok else consecutive_failures + 1
            if args.telegram_progress_every > 0 and (index % args.telegram_progress_every == 0 or index == len(dates)):
                elapsed_run = time.time() - run_started
                pct = 100.0 * index / len(dates)
                filled = int(round(pct / 10))
                progress_blocks = "▓" * filled + "░" * (10 - filled)
                # ETA sobre fechas realmente capturadas (los SKIP son instantáneos).
                worked = len(successes) + len(failures)
                pending = len(dates) - index
                rate = elapsed_run / worked if worked else 0.0
                eta_seconds = rate * pending
                finish_clock = (datetime.now() + timedelta(seconds=eta_seconds)).strftime("%H:%M")
                stats = quick_session_stats(date_iso) if ok else None
                rr_line = ""
                if stats and stats.get("rr_mean") is not None:
                    rr_line = (f"RR max alcanzable: prom {stats['rr_mean']:.1f} | "
                               f"max {stats['rr_max']:.1f} | min {stats['rr_min']:.1f}\n")
                lvn_detail = ("\n".join(stats["lvn_lines"]) + "\n") if stats and stats.get("lvn_lines") else ""
                stats_line = (
                    f"LVNs: {stats['lvns']} ({stats['retested']} retesteados) | "
                    f"eventos: {stats['events']} | shape ctx: {stats['shape']} | {stats['interactions']}\n"
                    f"{lvn_detail}"
                    f"{rr_line}"
                ) if stats else ""
                telegram_notify(
                    f"LVN {dates[0]} -> {dates[-1]}\n"
                    f"{progress_blocks} {pct:.1f}% ({index}/{len(dates)})\n"
                    f"Fecha: {date_iso} {'OK' if ok else 'FAIL'} ({int(record.get('rows', 0) or 0):,} filas | {record['elapsed_seconds']:.0f}s"
                    f"{f' | {attempt} intentos' if attempt > 1 else ''})\n"
                    f"{stats_line}"
                    f"OK {len(successes)} | FAIL {len(failures)} | SKIP {len(skipped)}\n"
                    f"Filas acumuladas: {captured_rows_total:,}\n"
                    f"Ritmo: {rate / 60:.1f} min/fecha\n"
                    f"ETA: {format_eta(eta_seconds)} (fin ~{finish_clock})"
                )
            if args.stop_after_consecutive_failures > 0 and consecutive_failures >= args.stop_after_consecutive_failures:
                data_boundary_reached = True
                print(f"FRONTERA DE DATOS: {consecutive_failures} fallas consecutivas hasta {date_iso}. "
                      "Replay sin datos en este rango (o ATAS caído). Abortando el resto de fechas.")
                telegram_notify(
                    f"LVN captura FRONTERA DE DATOS: {consecutive_failures} fallas seguidas hasta {date_iso}. "
                    f"Corrida abortada; ultima fecha buena: {successes[-1]['date'] if successes else 'ninguna'}"
                )
                break
    else:
        for date_iso in dates:
            capture = inspect_capture(date_iso)
            if capture["complete"]:
                skipped.append(capture)
            else:
                failures.append(capture)

    successful_dates = sorted(str(row.get("date", "")) for row in successes + skipped if row.get("date"))
    manifest = {
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "elapsed_seconds": round(time.time() - run_started, 3),
        "data_boundary_reached": bool(not args.report_only and not prepare_only and data_boundary_reached),
        "first_successful_date": successful_dates[0] if successful_dates else None,
        "last_successful_date": successful_dates[-1] if successful_dates else None,
        "requested_dates": dates,
        "successes": successes,
        "skipped": skipped,
        "failures": failures,
        "raw_dir": str(RAW_DIR),
        "report_path": str(report_path),
        "replay_window": f"{REPLAY_FROM_TIME}-{REPLAY_TO_TIME}",
        "chart_requirement": "NQ 1 MINUTE",
    }
    manifest_path = report_path.with_name(report_path.stem + "_run_manifest.json")
    write_manifest(manifest_path, manifest)
    print(f"Manifest: {manifest_path}")

    if args.capture_only:
        return 1 if failures else 0
    if not DETECTOR.exists():
        print(f"ERROR: detector no encontrado: {DETECTOR}", file=sys.stderr)
        return 4
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_dates = sorted({str(row["date"]) for row in successes + skipped})
    if not report_dates:
        print("ERROR: no hay capturas completas para generar el reporte.", file=sys.stderr)
        return 5
    command = detector_command(args, report_path, report_dates)
    print("\nGenerando reporte agregado LVN...")
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    if completed.returncode != 0:
        print(f"ERROR: detector terminó con código {completed.returncode}", file=sys.stderr)
        telegram_notify(f"LVN captura TERMINO con capturas OK, pero el reporte fallo (codigo {completed.returncode}).")
        return completed.returncode
    detector_payload: dict[str, object] = {}
    try:
        detector_payload = json.loads(completed.stdout[completed.stdout.index("{"):])
    except (ValueError, AttributeError):
        pass
    final_excel = str(detector_payload.get("excel_path", report_path))
    events_csv = Path(str(detector_payload.get("csv_dir", ""))) / "LVN_Events.csv"
    wr_text = bracket_winrates(events_csv) if events_csv.is_file() else "sin eventos"
    shapes_text = shape_breakdown(events_csv) if events_csv.is_file() else "sin eventos"
    telegram_notify(
        f"LVN captura TERMINADA {report_dates[0]} -> {report_dates[-1]}\n"
        f"fechas OK {len(successes)} SKIP {len(skipped)} FAIL {len(failures)} | "
        f"sesiones {detector_payload.get('sessions', '?')} | LVNs {detector_payload.get('lvns', '?')} | "
        f"eventos {detector_payload.get('events', '?')}\n"
        f"Brackets: {wr_text}\n"
        f"--- Por shape contextual (80/80) ---\n{shapes_text}\n"
        f"tiempo total {format_eta(time.time() - run_started)}\n{final_excel}"
    )
    print(f"\nREPORTE LISTO: {final_excel}")
    print(f"Capturas OK/reusadas: {len(successes) + len(skipped)} | fallidas: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
