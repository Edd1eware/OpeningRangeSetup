"""Endurance runner: recorre todas las fechas DST desde START_DATE en Replay X10.

Solo días hábiles (Lun-Vie), solo durante horario verano NY (EDT = UTC-4),
excluye feriados CME/USA calculados para cada año.
Skippea fechas que ya tienen score_trade_result en disco -> reanudable.
Diseñado para correrse toda la noche sin interacción.

Uso:
  python replay_dst_full_history_x10_endurance.py
  python replay_dst_full_history_x10_endurance.py --from 2023-01-01
  python replay_dst_full_history_x10_endurance.py --dry-run
  python replay_dst_full_history_x10_endurance.py --pending   # solo imprime pendientes
"""

import argparse
import csv
import math
from datetime import date, timedelta
from pathlib import Path

import replay_sync_runner_common_after_sync as rs
import telegram_run_summary_after_sync as telegram

START_DATE     = date(2022, 6, 21)
RESULTS_BASE   = rs.RESULTS_FOLDER          # el Exporter escribe score_trade_result aqui
ENDURANCE_DIR  = rs.RESULTS_FOLDER / "endurance"   # metadata/logs del runner
RUN_PLAN       = [("X10_R1", "X10", rs.X10_TIMEOUT_SECONDS)]


# ---------------------------------------------------------------------------
# Feriados CME/USA
# ---------------------------------------------------------------------------

def _easter(year: int) -> date:
    """Algoritmo de Butcher para Pascua gregoriana."""
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
    """n-ésimo weekday (0=Lun … 6=Dom) del mes. n negativo = desde el final."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta((weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    else:
        import calendar
        last = calendar.monthrange(year, month)[1]
        d = date(year, month, last)
        d -= timedelta((d.weekday() - weekday) % 7)
        return d + timedelta(weeks=n + 1)


def _observed(d: date) -> date:
    """Traslada feriado que cae sábado al viernes, domingo al lunes."""
    if d.weekday() == 5:   # sábado -> viernes
        return d - timedelta(1)
    if d.weekday() == 6:   # domingo -> lunes
        return d + timedelta(1)
    return d


def cme_holidays(year: int) -> set:
    """Feriados CME NQ para un año dado."""
    easter = _easter(year)
    raw = [
        date(year, 1, 1),                              # New Year's Day
        _nth_weekday(year, 1, 0, 3),                   # MLK (3er lunes enero)
        _nth_weekday(year, 2, 0, 3),                   # Presidents Day (3er lunes febrero)
        easter - timedelta(2),                          # Good Friday
        _nth_weekday(year, 5, 0, -1),                  # Memorial Day (último lunes mayo)
        date(year, 6, 19),                             # Juneteenth (desde 2022)
        date(year, 7, 4),                              # Independence Day
        _nth_weekday(year, 9, 0, 1),                   # Labor Day (1er lunes septiembre)
        _nth_weekday(year, 11, 3, 4),                  # Thanksgiving (4to jueves noviembre)
        date(year, 12, 25),                            # Christmas
    ]
    holidays = set()
    for h in raw:
        if year < 2022 and h == date(year, 6, 19):
            continue  # Juneteenth solo desde 2022
        holidays.add(_observed(h))
    return holidays


# ---------------------------------------------------------------------------
# Filtro DST (EDT: 2do domingo de marzo -> 1er domingo de noviembre)
# ---------------------------------------------------------------------------

def is_dst(d: date) -> bool:
    dst_start = _nth_weekday(d.year, 3, 6, 2)   # 2do domingo de marzo
    dst_end   = _nth_weekday(d.year, 11, 6, 1)  # 1er domingo de noviembre
    return dst_start <= d < dst_end


# ---------------------------------------------------------------------------
# Generador de fechas elegibles
# ---------------------------------------------------------------------------

def eligible_dates(from_date: date, to_date: date) -> list:
    holidays_cache = {}
    out = []
    d = from_date
    while d <= to_date:
        year = d.year
        if year not in holidays_cache:
            holidays_cache[year] = cme_holidays(year)
        if (d.weekday() < 5                 # lunes-viernes
                and is_dst(d)               # horario verano NY
                and d not in holidays_cache[year]):
            out.append(d.isoformat())
        d += timedelta(1)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", default=None,
                        help="Fecha inicio YYYY-MM-DD (default: 2022-06-21)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra fechas sin correr.")
    parser.add_argument("--pending", action="store_true",
                        help="Muestra cuantas fechas faltan sin correr.")
    args = parser.parse_args()

    from_date = date.fromisoformat(args.from_date) if args.from_date else START_DATE
    to_date   = date.today()

    all_dates = eligible_dates(from_date, to_date)

    ENDURANCE_DIR.mkdir(parents=True, exist_ok=True)

    # Fechas que ya tienen resultado en disco (Exporter escribe en RESULTS_BASE).
    # Minimo 80 bytes: descarta archivos vacios/corruptos por crash durante escritura.
    done = {
        f.stem.replace("score_trade_result_", "").replace("_NY", "")
        for f in RESULTS_BASE.glob("score_trade_result_*_NY.csv")
        if f.stat().st_size >= 80
    }

    pending = [d for d in all_dates if d not in done]

    print(f"Rango     : {from_date} -> {to_date}")
    print(f"Elegibles : {len(all_dates)} (DST, Lun-Vie, sin feriados CME)")
    print(f"Ya en disco: {len(done)} | Pendientes: {len(pending)}")

    if args.dry_run or args.pending:
        for d in pending:
            print(" ", d)
        return 0

    if not pending:
        print("Nada pendiente. Todas las fechas ya tienen resultado.")
        return 0

    # Estimar duración (X10 timeout por fecha)
    eta_min = math.ceil(len(pending) * rs.X10_TIMEOUT_SECONDS / 60)
    eta_h   = eta_min // 60
    eta_m   = eta_min % 60
    print(f"ETA máximo: ~{eta_h}h {eta_m}m (a {rs.X10_TIMEOUT_SECONDS}s/fecha)")

    telegram.send_text(
        RESULTS_BASE,
        f"EW OR | Endurance DST iniciado\n"
        f"{len(pending)} fechas pendientes | ETA max {eta_h}h {eta_m}m\n"
        f"Rango: {from_date} -> {to_date}",
    )

    failures = []
    for i, date_str in enumerate(pending, 1):
        progress = f"{date_str} ({i}/{len(pending)})"
        try:
            _, date_failures = rs.run_replay_period(
                [date_str],
                output_folder=ENDURANCE_DIR,
                run_plan=RUN_PLAN,
                report_prefix="endurance_x10",
                force=False,               # no re-corre si ya existe
                replay_to_time=rs.DEFAULT_REPLAY_TO_TIME,
                progress_meta={
                    "stage_index": i,
                    "stage_total": len(pending),
                    "stage_label": "Endurance DST X10",
                    "stage_period": progress,
                    "global_target": None,
                    "session_roots": None,
                    "run_label": "endurance",
                    "pnl_log_path": None,
                },
            )
            failures.extend(date_failures)
        except KeyboardInterrupt:
            telegram.send_text(RESULTS_BASE,
                               f"EW OR | Endurance CANCELADO en {progress}")
            raise
        except Exception as exc:
            failures.append((date_str, "X10_R1", str(exc)))
            print(f"  ERROR {date_str}: {exc} — continuando...")

        # Progreso cada 10 fechas
        if i % 10 == 0 or i == len(pending):
            done_now = sum(
                1 for d in all_dates
                if (RESULTS_BASE / f"score_trade_result_{d}_NY.csv").exists()
            )
            pct = done_now / len(all_dates) * 100
            remaining = len(pending) - i
            eta_rem   = math.ceil(remaining * rs.X10_TIMEOUT_SECONDS / 60)
            print(f"[{i}/{len(pending)}] {pct:.0f}% completado | "
                  f"faltan ~{eta_rem}m | errores: {len(failures)}")

    fail_n = len(failures)
    done_final = sum(
        1 for d in all_dates
        if (RESULTS_BASE / f"score_trade_result_{d}_NY.csv").exists()
    )

    msg = [
        "EW OR | Endurance DST TERMINADO",
        f"Procesadas: {len(pending)} | En disco: {done_final}/{len(all_dates)} ({done_final/len(all_dates)*100:.0f}%)",
        f"Errores: {fail_n}",
    ]
    if failures:
        msg.append("Fechas con error:")
        msg += [f"  {d} {run}: {reason}" for d, run, reason in failures[:15]]
        if fail_n > 15:
            msg.append(f"  ... y {fail_n - 15} mas.")
        msg.append("Relanza el script para reintentar los errores.")
    telegram.send_text(RESULTS_BASE, "\n".join(msg))

    print("\n".join(msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
