"""
Runner: replay de las 502 fechas descargadas de DataBento.

Estrategia:
  - 10 fechas de validacion (primeras cronologicamente): X1 + X10 con sync check
  - Resto (~470 fechas): solo X10 (resultados rapidos sin sync check)

No genera Excel. Usa los CSVs que escribe el Score Exporter directamente.

Stop automatico: si < MIN_TRADES_IN_WINDOW trades en TRADE_WINDOW sesiones consecutivas
se detiene y avisa por Telegram para re-analisis.

Uso:
  python 04_run_replay_all_databento_after_sync.py
  python 04_run_replay_all_databento_after_sync.py --prepare-only
  python 04_run_replay_all_databento_after_sync.py --force
  python 04_run_replay_all_databento_after_sync.py --x10-only
  python 04_run_replay_all_databento_after_sync.py --x1x10-count 80
  python 04_run_replay_all_databento_after_sync.py --step
"""

import argparse
import csv
import ctypes
import math
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import replay_sync_runner_common_after_sync as replay_sync
import telegram_run_summary_after_sync as telegram
import time_zones_atas

DATABENTO_RAW_DIR = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn"
)

RESULTS_BASE   = replay_sync.RESULTS_FOLDER
OUTPUT_ROOT    = RESULTS_BASE / "visual_tests" / "04_databento_runs"
X1X10_DIR      = OUTPUT_ROOT / "x1x10_validation"
X10_ONLY_DIR   = OUTPUT_ROOT / "x10_bulk"
EDGE_NAUTILUS  = RESULTS_BASE / "visual_tests" / "orb_nq_databento_edge_nautilus"

DEFAULT_X1X10_COUNT  = 10
CHALLENGE_TARGET     = 9000.0
PNL_LOG              = str(RESULTS_BASE / "strategy_tester_trades.csv")

BATCH_SIZE           = 10    # fechas por lote antes de chequear condicion de stop
TRADE_WINDOW         = 30    # ventana rolling en sesiones
MIN_TRADES_IN_WINDOW = 4     # menos que esto en TRADE_WINDOW sesiones -> stop


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

class _SleepBlocker:
    def __enter__(self):
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
            print("Anti-suspension activo.")
        return self

    def __exit__(self, *_):
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            print("Anti-suspension liberado.")


def _market_closed(year: int) -> set:
    from datetime import date as _d
    def _nth(yr, mo, wd, n):
        d = _d(yr, mo, 1)
        d += timedelta((wd - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    def _last(yr, mo, wd):
        import calendar
        last = calendar.monthrange(yr, mo)[1]
        d = _d(yr, mo, last)
        return d - timedelta((d.weekday() - wd) % 7)
    def _obs(d):
        if d.weekday() == 5: return d - timedelta(1)
        if d.weekday() == 6: return d + timedelta(1)
        return d
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19*a + b - d - g + 15) % 30; i = c // 4; k = c % 4
    l = (32 + 2*e + 2*i - h - k) % 7; m = (a + 11*h + 22*l) // 451
    mo2 = (h + l - 7*m + 114) // 31; dy2 = ((h + l - 7*m + 114) % 31) + 1
    easter = date(year, mo2, dy2)
    raw = [
        _obs(date(year, 1, 1)),
        _nth(year, 1, 0, 3),
        _nth(year, 2, 0, 3),
        easter - timedelta(2),
        _last(year, 5, 0),
        _obs(date(year, 6, 19)),
        _obs(date(year, 7, 4)),
        _nth(year, 9, 0, 1),
        _nth(year, 11, 3, 4),
        _obs(date(year, 12, 25)),
    ]
    extra = {date(2025, 1, 9)}
    return set(raw) | extra


def load_databento_dates() -> list[str]:
    if not DATABENTO_RAW_DIR.exists():
        sys.exit(f"ERROR: raw_dbn no encontrado en {DATABENTO_RAW_DIR}")

    closed_cache: dict[int, set] = {}
    dates = []
    for entry in sorted(DATABENTO_RAW_DIR.iterdir()):
        name = entry.name
        if not entry.is_dir() or len(name) != 10:
            continue
        try:
            d = date.fromisoformat(name)
        except ValueError:
            continue
        if d.weekday() >= 5:
            continue
        yr = d.year
        if yr not in closed_cache:
            closed_cache[yr] = _market_closed(yr)
        if d in closed_cache[yr]:
            continue
        dates.append(name)

    return sorted(dates)


def split_dates(all_dates: list[str], x1x10_count: int) -> tuple[list[str], list[str]]:
    return all_dates[:x1x10_count], all_dates[x1x10_count:]


# ---------------------------------------------------------------------------
# Trade count check (condicion de stop)
# ---------------------------------------------------------------------------

_NO_TRADE_VALS = {"", "NO_TRADE", "TIME_OVER", "OPEN", "HOLYDAY NO DATA"}


def _count_trades_in_window(output_dirs: list[Path], last_n: int) -> tuple[int, int]:
    """
    Lee los ultimos `last_n` CSVs de resultado de score_trade_result_*_NY.csv
    en output_dirs. Retorna (trades_tomados, total_csvs_encontrados).
    """
    all_csvs: list[Path] = []
    for d in output_dirs:
        if d.exists():
            all_csvs.extend(d.glob("score_trade_result_*_NY.csv"))
    all_csvs.sort(key=lambda p: p.name)
    window = all_csvs[-last_n:]

    trades = 0
    for csv_path in window:
        try:
            with open(csv_path, encoding="utf-8-sig", newline="") as fh:
                row = next(csv.DictReader(fh), None)
            if row is None:
                continue
            val = (row.get("result TP SL BE") or row.get("RESULT") or "").strip().upper()
            if val not in _NO_TRADE_VALS:
                trades += 1
        except Exception:
            pass
    return trades, len(window)


def _check_trade_frequency(processed: int) -> tuple[bool, int, int]:
    """
    Retorna (debe_parar, trades_en_ventana, tamano_ventana).
    Solo activa despues de TRADE_WINDOW sesiones procesadas.
    """
    if processed < TRADE_WINDOW:
        return False, 0, 0
    trades, window_size = _count_trades_in_window([X1X10_DIR, X10_ONLY_DIR], TRADE_WINDOW)
    must_stop = window_size >= TRADE_WINDOW and trades < MIN_TRADES_IN_WINDOW
    return must_stop, trades, window_size


# ---------------------------------------------------------------------------
# Runner por lotes con stop check
# ---------------------------------------------------------------------------

def _fmt_eta(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _run_batched(
    dates: list[str],
    output_folder: Path,
    run_plan,
    args,
    stage_index: int,
    stage_total: int,
    stage_label: str,
    processed_before: int,
    global_total: int,
) -> tuple[bool, list, bool, int]:
    """
    Corre `dates` en lotes de BATCH_SIZE.
    Muestra ETA en terminal y Telegram despues de cada lote.
    Chequea condicion de stop por frecuencia de trades.
    Retorna (passed_all, failures, stopped_early, total_processed).
    """
    failures_all  = []
    passed_all    = True
    processed     = processed_before
    stage_done    = 0
    stage_total_n = len(dates)
    t_stage_start = time.monotonic()
    secs_per_date_history: list[float] = []

    # Pre-group dates by UTC offset so TZ change fires at the transition boundary,
    # never mid-batch. Each element: (tz_offset, [dates]).
    from itertools import groupby as _groupby
    tz_groups: list[tuple[int, list[str]]] = []
    for _tz, _g in _groupby(dates, key=lambda d: time_zones_atas.get_utc_offset(date.fromisoformat(d))):
        tz_groups.append((_tz, list(_g)))

    # Rebuild flat batch list preserving TZ boundary awareness
    batches: list[tuple[int, list[str]]] = []
    for tz_offset, tz_dates in tz_groups:
        for i in range(0, len(tz_dates), BATCH_SIZE):
            batches.append((tz_offset, tz_dates[i : i + BATCH_SIZE]))

    _last_tz: int | None = None

    for tz_offset, batch in batches:
        batch_start = batch[0]
        batch_end   = batch[-1]
        t_batch_0   = time.monotonic()

        if tz_offset != _last_tz and not args.compare_only:
            label = "EDT (UTC-4)" if tz_offset == -4 else "EST (UTC-5)"
            print(f"\n  [TZ] Cambiando a {label} antes de {batch_start}")
            try:
                time_zones_atas.ensure_atas_timezone(tz_offset)
            except NotImplementedError:
                print(f"  [TZ] time_zones_atas.ensure_atas_timezone no implementado — saltar cambio")
            _last_tz = tz_offset

        passed, failures = replay_sync.run_replay_period(
            batch,
            output_folder=output_folder,
            run_plan=run_plan,
            report_prefix=f"databento_{stage_label.lower().replace(' ', '_')}",
            force=args.force,
            step=args.step,
            compare_only=args.compare_only,
            replay_to_time=replay_sync.DEFAULT_REPLAY_TO_TIME,
            progress_meta={
                "stage_index": stage_index,
                "stage_total": stage_total,
                "stage_label": stage_label,
                "stage_period": f"{batch_start} -> {batch_end}",
                "global_target": global_total,
                "session_roots": [X1X10_DIR, X10_ONLY_DIR],
                "run_label": "DataBento 502",
                "pnl_log_path": PNL_LOG,
            },
        )
        failures_all.extend(failures)
        passed_all  = passed_all and passed
        processed  += len(batch)
        stage_done += len(batch)

        # ETA
        elapsed_batch = time.monotonic() - t_batch_0
        secs_per_date_history.append(elapsed_batch / len(batch))
        avg_spd       = sum(secs_per_date_history) / len(secs_per_date_history)
        stage_left    = stage_total_n - stage_done
        eta_stage_s   = avg_spd * stage_left
        elapsed_total = time.monotonic() - t_stage_start
        pct           = stage_done / stage_total_n * 100

        # Trade frequency check
        must_stop, trades, window_size = _check_trade_frequency(processed)

        # Terminal line
        print(
            f"  [{stage_label}] {stage_done}/{stage_total_n} ({pct:.0f}%) | "
            f"avg {avg_spd:.0f}s/fecha | ETA etapa: {_fmt_eta(eta_stage_s)} | "
            f"elapsed: {_fmt_eta(elapsed_total)} | "
            f"trades/{window_size}sess: {trades if window_size else '---'}"
        )

        # Telegram solo en milestones 25/50/75%
        pct_prev = (stage_done - len(batch)) / stage_total_n * 100
        if any(pct_prev < m <= pct for m in (25, 50, 75)):
            equity = telegram.get_current_equity(PNL_LOG)
            eq_line = f"\nEquity: ${equity:,.0f}" if equity is not None else ""
            trade_line = f"\nTrades/{window_size}s: {trades}" if window_size else ""
            telegram.send_text(
                RESULTS_BASE,
                f"EW ORB NQ | {stage_label} — {pct:.0f}%\n"
                f"{stage_done}/{stage_total_n} fechas{eq_line}\n"
                f"ETA: {_fmt_eta(eta_stage_s)} | Elapsed: {_fmt_eta(elapsed_total)}"
                f"{trade_line}",
            )

        if must_stop:
            equity = telegram.get_current_equity(PNL_LOG)
            eq_str = f" | Equity: ${equity:,.0f}" if equity is not None else ""
            msg = (
                f"STOP: solo {trades}/{window_size} trades "
                f"en {TRADE_WINDOW} sesiones (mín={MIN_TRADES_IN_WINDOW}){eq_str}"
            )
            print(f"\n*** {msg} ***\n")
            telegram.send_text(RESULTS_BASE, f"EW ORB NQ | {msg}")
            telegram.send_equity_chart(
                RESULTS_BASE, PNL_LOG, target=CHALLENGE_TARGET,
                caption=f"Stop por frecuencia baja — {processed} sesiones corridas",
            )
            return passed_all, failures_all, True, processed

    return passed_all, failures_all, False, processed


def _save_equity_summary(n_dates: int) -> None:
    """Genera PNG equity curve, lo embebe en Excel y lo manda a Telegram."""
    EDGE_NAUTILUS.mkdir(parents=True, exist_ok=True)
    chart_path = telegram.build_equity_chart(PNL_LOG, target=CHALLENGE_TARGET)
    if chart_path is None:
        print("Equity summary: sin datos o matplotlib no disponible.")
        return

    import shutil
    dest_png = EDGE_NAUTILUS / "equity_curve_final.png"
    shutil.copy(chart_path, dest_png)
    try:
        os.unlink(chart_path)
    except OSError:
        pass

    try:
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as XLImage
        wb = Workbook()
        ws = wb.active
        ws.title = "Equity Curve"
        ws.column_dimensions["A"].width = 90
        ws.row_dimensions[1].height = 300
        ws.add_image(XLImage(str(dest_png)), "A1")
        xlsx_path = EDGE_NAUTILUS / "equity_curve_final.xlsx"
        wb.save(str(xlsx_path))
        print(f"Equity Excel: {xlsx_path}")
    except Exception as exc:
        print(f"Equity Excel fallo: {exc}")

    equity = telegram.get_current_equity(PNL_LOG)
    eq_str = f" | Equity: ${equity:,.0f}" if equity is not None else ""
    telegram.send_photo(
        RESULTS_BASE,
        str(dest_png),
        caption=f"EW ORB NQ | Equity final — {n_dates} fechas{eq_str}",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Replay de 502 fechas DataBento: 60 X1+X10, resto X10."
    )
    p.add_argument("--prepare-only",   action="store_true")
    p.add_argument("--compare-only",   action="store_true")
    p.add_argument("--force",          action="store_true")
    p.add_argument("--step",           action="store_true")
    p.add_argument("--x10-only",       action="store_true",
                   help="Salta la fase X1+X10, solo corre X10 en todas.")
    p.add_argument("--x1x10-only",     action="store_true",
                   help="Solo corre la fase de validacion X1+X10.")
    p.add_argument("--x1x10-count",    type=int, default=DEFAULT_X1X10_COUNT,
                   help=f"Cuantas fechas validan con X1+X10 (default {DEFAULT_X1X10_COUNT}).")
    return p.parse_args()


def main():
    args = parse_args()

    all_dates = load_databento_dates()
    if not all_dates:
        print("ERROR: no se encontraron fechas en raw_dbn.")
        return 1

    validation_dates, bulk_dates = split_dates(all_dates, args.x1x10_count)

    run_plan_x1x10 = replay_sync.build_run_plan(quick=True)
    run_plan_x10   = replay_sync.build_run_plan(x10_only=True)

    today_ny     = datetime.now(ZoneInfo("America/New_York")).date()
    last_allowed = today_ny - timedelta(days=1)
    validation_dates = [d for d in validation_dates if date.fromisoformat(d) <= last_allowed]
    bulk_dates       = [d for d in bulk_dates       if date.fromisoformat(d) <= last_allowed]

    print(f"\nDATAS DATABENTO: {len(all_dates)} total")
    print(f"  Fase 1 validacion X1+X10 : {len(validation_dates)} fechas")
    print(f"  Fase 2 bulk X10 only     : {len(bulk_dates)} fechas")
    print(f"  Rango: {all_dates[0]} -> {all_dates[-1]}")
    print(f"  Ultima permitida: {last_allowed}")
    print(f"  Stop si < {MIN_TRADES_IN_WINDOW} trades en {TRADE_WINDOW} sesiones (check cada {BATCH_SIZE} fechas)")

    if args.prepare_only:
        print("\nPREPARE-ONLY. No se inicio Replay.")
        return 0

    eta_x1x10 = math.ceil(len(validation_dates) * (replay_sync.X1_TIMEOUT_SECONDS + replay_sync.X10_TIMEOUT_SECONDS) / 60)
    eta_x10   = math.ceil(len(bulk_dates) * replay_sync.X10_TIMEOUT_SECONDS / 60)
    print(f"\n  ETA maximo fase 1: ~{eta_x1x10//60}h {eta_x1x10%60}m")
    print(f"  ETA maximo fase 2: ~{eta_x10//60}h {eta_x10%60}m")
    print(f"  ETA total maximo : ~{(eta_x1x10+eta_x10)//60}h {(eta_x1x10+eta_x10)%60}m")

    if not args.compare_only:
        telegram.clear_telegram_before_run(RESULTS_BASE)

    failures_all = []
    passed_all   = True
    total_processed = 0

    with _SleepBlocker():
        # --- FASE 1: X1 + X10 ---
        if validation_dates and not args.x10_only:
            X1X10_DIR.mkdir(parents=True, exist_ok=True)
            print(f"\n=== FASE 1: {len(validation_dates)} fechas X1+X10 ===")
            passed, failures, stopped, total_processed = _run_batched(
                validation_dates, X1X10_DIR, run_plan_x1x10, args,
                stage_index=1, stage_total=2,
                stage_label="DataBento X1+X10",
                processed_before=0,
                global_total=len(validation_dates) + len(bulk_dates),
            )
            passed_all = passed_all and passed
            failures_all.extend(failures)
            print(f"Fase 1 {'STOP' if stopped else ('PASS' if passed else 'FAIL')} | {len(failures)} errores")
            telegram.check_and_notify_challenge(RESULTS_BASE, PNL_LOG, CHALLENGE_TARGET)
            if not stopped:
                telegram.send_equity_chart(
                    RESULTS_BASE, PNL_LOG, target=CHALLENGE_TARGET,
                    caption=f"Fase 1 X1+X10 completada — {len(validation_dates)} fechas",
                )
            if stopped or args.x1x10_only:
                _report_end(failures_all, X1X10_DIR)
                return 1 if stopped else (0 if passed_all else 1)

        # --- FASE 2: X10 solo ---
        if bulk_dates and not args.x1x10_only:
            X10_ONLY_DIR.mkdir(parents=True, exist_ok=True)
            if not args.compare_only:
                telegram.clear_telegram_before_run(RESULTS_BASE)
            print(f"\n=== FASE 2: {len(bulk_dates)} fechas X10 only ===")
            passed, failures, stopped, total_processed = _run_batched(
                bulk_dates, X10_ONLY_DIR, run_plan_x10, args,
                stage_index=2, stage_total=2,
                stage_label="DataBento X10 bulk",
                processed_before=total_processed,
                global_total=len(validation_dates) + len(bulk_dates),
            )
            passed_all = passed_all and passed
            failures_all.extend(failures)
            print(f"Fase 2 {'STOP' if stopped else ('PASS' if passed else 'FAIL')} | {len(failures)} errores")
            telegram.check_and_notify_challenge(RESULTS_BASE, PNL_LOG, CHALLENGE_TARGET)
            if not stopped:
                telegram.send_equity_chart(
                    RESULTS_BASE, PNL_LOG, target=CHALLENGE_TARGET,
                    caption=f"Fase 2 X10 bulk completada — {len(bulk_dates)} fechas",
                )

    _report_end(failures_all, OUTPUT_ROOT)
    _save_equity_summary(len(validation_dates) + len(bulk_dates))
    return 0 if (passed_all and not stopped) else 1


def _report_end(failures, output_folder):
    if failures:
        print(f"\nFECHAS CON ERROR ({len(failures)}):")
        for d, run, reason in failures[:20]:
            print(f"  {d} {run}: {reason}")
        if len(failures) > 20:
            print(f"  ... y {len(failures)-20} mas.")
    else:
        print("\nSin errores.")
    print(f"Resultados en: {output_folder}")


if __name__ == "__main__":
    raise SystemExit(main())
