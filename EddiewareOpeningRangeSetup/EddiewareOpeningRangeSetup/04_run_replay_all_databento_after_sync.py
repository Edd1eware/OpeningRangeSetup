"""
Runner: replay de las 502 fechas descargadas de DataBento.

Estrategia:
  - 60 fechas de validacion (primeras cronologicamente): X1 + X10 con sync check
  - Resto (~440 fechas): solo X10 (resultados rapidos sin sync check)

No genera Excel. Usa los CSVs que escribe el Score Exporter directamente.

Uso:
  python 04_run_replay_all_databento_after_sync.py
  python 04_run_replay_all_databento_after_sync.py --prepare-only
  python 04_run_replay_all_databento_after_sync.py --force
  python 04_run_replay_all_databento_after_sync.py --x10-only   # salta fase X1/X10
  python 04_run_replay_all_databento_after_sync.py --x1x10-count 80
  python 04_run_replay_all_databento_after_sync.py --step
"""

import argparse
import ctypes
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import replay_sync_runner_common_after_sync as replay_sync
import telegram_run_summary_after_sync as telegram

DATABENTO_RAW_DIR = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn"
)

RESULTS_BASE   = replay_sync.RESULTS_FOLDER
OUTPUT_ROOT    = RESULTS_BASE / "visual_tests" / "04_databento_runs"
X1X10_DIR      = OUTPUT_ROOT / "x1x10_validation"
X10_ONLY_DIR   = OUTPUT_ROOT / "x10_bulk"

DEFAULT_X1X10_COUNT  = 60     # primeras N fechas con sync X1+X10
CHALLENGE_TARGET     = 9000.0
PNL_LOG              = str(RESULTS_BASE / "strategy_tester_trades.csv")


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
    extra = {date(2025, 1, 9)}  # national day of mourning
    return set(raw) | extra


def load_databento_dates() -> list[str]:
    """Lee los subdirectorios YYYY-MM-DD de raw_dbn como la lista de fechas."""
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
    validation = all_dates[:x1x10_count]
    bulk       = all_dates[x1x10_count:]
    return validation, bulk


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

    run_plan_x1x10 = replay_sync.build_run_plan(quick=True)        # X1 + X10
    run_plan_x10   = replay_sync.build_run_plan(x10_only=True)     # solo X10

    today_ny       = datetime.now(ZoneInfo("America/New_York")).date()
    last_allowed   = today_ny - timedelta(days=1)
    validation_dates = [d for d in validation_dates if date.fromisoformat(d) <= last_allowed]
    bulk_dates       = [d for d in bulk_dates       if date.fromisoformat(d) <= last_allowed]

    print(f"\nDATAS DATABENTO: {len(all_dates)} total")
    print(f"  Fase 1 validacion X1+X10 : {len(validation_dates)} fechas")
    print(f"  Fase 2 bulk X10 only     : {len(bulk_dates)} fechas")
    print(f"  Rango: {all_dates[0]} -> {all_dates[-1]}")
    print(f"  Ultima permitida: {last_allowed}")

    if args.prepare_only:
        print("\nPREPARE-ONLY. No se inicio Replay.")
        return 0

    # ETA estimado
    eta_x1x10 = math.ceil(len(validation_dates) * (replay_sync.X1_TIMEOUT_SECONDS + replay_sync.X10_TIMEOUT_SECONDS) / 60)
    eta_x10   = math.ceil(len(bulk_dates) * replay_sync.X10_TIMEOUT_SECONDS / 60)
    print(f"\n  ETA maximo fase 1: ~{eta_x1x10//60}h {eta_x1x10%60}m")
    print(f"  ETA maximo fase 2: ~{eta_x10//60}h {eta_x10%60}m")
    print(f"  ETA total maximo : ~{(eta_x1x10+eta_x10)//60}h {(eta_x1x10+eta_x10)%60}m")

    if not args.compare_only:
        telegram.clear_telegram_before_run(RESULTS_BASE)

    failures_all = []
    passed_all   = True

    with _SleepBlocker():
        # --- FASE 1: X1 + X10 (validacion de sincronicidad) ---
        if validation_dates and not args.x10_only:
            X1X10_DIR.mkdir(parents=True, exist_ok=True)
            print(f"\n=== FASE 1: {len(validation_dates)} fechas X1+X10 ===")
            passed, failures = replay_sync.run_replay_period(
                validation_dates,
                output_folder=X1X10_DIR,
                run_plan=run_plan_x1x10,
                report_prefix="databento_x1x10",
                force=args.force,
                step=args.step,
                compare_only=args.compare_only,
                replay_to_time=replay_sync.DEFAULT_REPLAY_TO_TIME,
                progress_meta={
                    "stage_index": 1,
                    "stage_total": 2,
                    "stage_label": "DataBento X1+X10",
                    "stage_period": f"{validation_dates[0]} -> {validation_dates[-1]}",
                    "global_target": len(all_dates),
                    "session_roots": [X1X10_DIR, X10_ONLY_DIR],
                    "run_label": "DataBento 502",
                    "pnl_log_path": PNL_LOG,
                },
            )
            passed_all = passed_all and passed
            failures_all.extend(failures)
            print(f"Fase 1 {'PASS' if passed else 'FAIL'} | {len(failures)} errores")
            telegram.check_and_notify_challenge(RESULTS_BASE, PNL_LOG, CHALLENGE_TARGET)
            telegram.send_equity_chart(
                RESULTS_BASE, PNL_LOG, target=CHALLENGE_TARGET,
                caption=f"Fase 1 X1+X10 completada — {len(validation_dates)} fechas",
            )

            if args.x1x10_only:
                _report_end(failures_all, X1X10_DIR)
                return 0 if passed_all else 1

        # --- FASE 2: X10 solo (bulk historico) ---
        if bulk_dates and not args.x1x10_only:
            X10_ONLY_DIR.mkdir(parents=True, exist_ok=True)
            print(f"\n=== FASE 2: {len(bulk_dates)} fechas X10 only ===")
            passed, failures = replay_sync.run_replay_period(
                bulk_dates,
                output_folder=X10_ONLY_DIR,
                run_plan=run_plan_x10,
                report_prefix="databento_x10_bulk",
                force=args.force,
                step=args.step,
                compare_only=args.compare_only,
                replay_to_time=replay_sync.DEFAULT_REPLAY_TO_TIME,
                progress_meta={
                    "stage_index": 2,
                    "stage_total": 2,
                    "stage_label": "DataBento X10 bulk",
                    "stage_period": f"{bulk_dates[0]} -> {bulk_dates[-1]}",
                    "global_target": len(all_dates),
                    "session_roots": [X1X10_DIR, X10_ONLY_DIR],
                    "run_label": "DataBento 502",
                    "pnl_log_path": PNL_LOG,
                },
            )
            passed_all = passed_all and passed
            failures_all.extend(failures)
            print(f"Fase 2 {'PASS' if passed else 'FAIL'} | {len(failures)} errores")
            telegram.check_and_notify_challenge(RESULTS_BASE, PNL_LOG, CHALLENGE_TARGET)
            telegram.send_equity_chart(
                RESULTS_BASE, PNL_LOG, target=CHALLENGE_TARGET,
                caption=f"Fase 2 X10 bulk completada — {len(bulk_dates)} fechas",
            )

    _report_end(failures_all, OUTPUT_ROOT)
    return 0 if passed_all else 1


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
