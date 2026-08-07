"""Book Recorder, FULL SESSION capture for the Liquidity Burst direction study.

Why this exists
---------------
The tape recordings on disk only cover 09:29 to 09:43, about fourteen minutes.
That is not a limitation of the recorder: `features/BookRecorder.cs` defaults to
09:25 to 15:35. The short window came from `05_run_book_recorder_probe.py`,
which is a probe written to answer one question, whether the DOM appears in this
replay at all, and which runs with `quick=True`.

Consequence measured today: only 181 of 2,559 labelled Liquidity Bursts fall
inside the recorded window, which is far too small to validate anything. With
n=181 the 95 percent interval of an accuracy estimate is plus or minus six to
seven points.

This runner captures whole sessions so the sample can reach roughly 2,500
events, which is the minimum for the question to be decidable.

Prerequisites in ATAS, they cannot be set from Python
-----------------------------------------------------
1. ATAS open, NOT minimised. The UIA driver cannot see a minimised window.
2. A 1 minute chart with the indicator "ATRAPADOS Book Recorder" attached.
3. In that indicator's properties:
       Ventana inicio NY = 09:25
       Ventana fin NY    = 15:35
       Grabar Tape       = true
       Grabar MBP        = true
       Grabar MBO        = true if the replay supports it, this is the only
                           source with individual order resolution
4. Do not touch the Replay X1 / X10 controls while it runs.

Usage
-----
    python -u 06_run_book_recorder_full_sessions.py --limit 5     # pilot
    python -u 06_run_book_recorder_full_sessions.py               # all dates
"""

import argparse
import importlib
import os
import time
from pathlib import Path

import replay_sync_runner_common_after_sync as replay_sync

runner = importlib.import_module("04_run_replay_featsweep_after_sync")

BOOK_FOLDER = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings"
TELEGRAM_FOLDER = (
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)


def notify(message):
    try:
        from telegram_run_summary_after_sync import send_persistent_text

        send_persistent_text(TELEGRAM_FOLDER, message)
    except Exception:
        pass


def tape_rows(date_iso):
    path = os.path.join(BOOK_FOLDER, f"tape_{date_iso}_NY.csv")
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def main():
    parser = argparse.ArgumentParser(
        description="Captura de sesiones completas con BookRecorder."
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Ultimas N fechas. 0 = todas.",
    )
    arguments = parser.parse_args()

    # Same hang fix the probe uses: resolve the Replay window by handle instead
    # of enumerating the whole desktop through UIA.
    replay_sync.get_replay_controls = runner._get_replay_controls_by_handle
    print("FIX ventana Replay por HANDLE activo.")

    dates = (
        runner.DATES_DST[-arguments.limit:]
        if arguments.limit > 0
        else runner.DATES_DST
    )
    date_iso_list = [replay_sync.date_iso_from_replay(d) for d in dates]

    before = {iso: tape_rows(iso) for iso in date_iso_list}
    already = sum(1 for value in before.values() if value > 0)

    print(f"Fechas a reproducir: {len(dates)}  ({dates[0]} -> {dates[-1]})")
    print(f"Con tape previo: {already}")
    print(f"Salida: {BOOK_FOLDER}")
    print("\nATAS debe estar ABIERTO y NO minimizado, con el Book Recorder")
    print("adjunto y su ventana fijada en 09:25 a 15:35.\n")

    # quick=False is the whole point: the probe used quick=True, which is what
    # truncated every recording to the first minutes of the session.
    run_plan = replay_sync.build_run_plan(quick=False, x1_only=False, x10_only=True)

    output = Path(BOOK_FOLDER) / "_full_sessions"
    output.mkdir(parents=True, exist_ok=True)

    notify(
        "VT BOOK RECORDER | INICIO CAPTURA SESION COMPLETA\n\n"
        f"Fechas: {len(dates)}\n"
        f"Ventana: 09:25 a 15:35 NY, sesion entera\n"
        "Objetivo: pasar de 181 a ~2500 bursts con tape.\n"
        "No tocar el foco de ATAS ni los controles de Replay."
    )

    started = time.time()
    print("INICIANDO REPLAY. No tocar el foco de ATAS.\n")
    replay_sync.run_replay_period(
        date_iso_list,
        output_folder=output,
        run_plan=run_plan,
        report_prefix="bookrec_full",
        force=True,
        step=False,
    )

    after = {iso: tape_rows(iso) for iso in date_iso_list}
    gained = sum(1 for iso in date_iso_list if after[iso] > before[iso])
    total_rows = sum(after.values())
    elapsed = (time.time() - started) / 60.0

    summary = (
        "VT BOOK RECORDER | CAPTURA TERMINADA\n\n"
        f"Fechas procesadas: {len(dates)}\n"
        f"Fechas con tape nuevo o ampliado: {gained}\n"
        f"Filas de tape totales: {total_rows}\n"
        f"Tiempo: {elapsed:.1f} min"
    )
    print(summary)
    notify(summary)


if __name__ == "__main__":
    main()
