"""
Book Recorder probe — corre el replay de N fechas y reporta si el DOM/libro (MBP)
está disponible en TU replay. Reúsa el motor del featsweep runner (incluye el fix
del cuelgue por HANDLE); NO reescribe el control de Replay.

Requisitos en el chart (1m) antes de correr:
  - "ATRAPADOS Book Recorder"  (graba mbo/mbp/tape por fecha)
  - (opcional) el exporter, para que run_replay_period avance de fecha por resultado.

Uso:
  python -u 05_run_book_recorder_probe.py            # 1 fecha (la última DST)
  python -u 05_run_book_recorder_probe.py --limit 3  # 3 fechas

Lectura: por cada fecha imprime mbp_rows. Si mbp_rows > 0 => el depth SÍ está en el
replay => el overlay naranja "DOM Levels" pinta en replay. Si 0 => solo en vivo.
"""
import argparse
import importlib
import os
from pathlib import Path

import replay_sync_runner_common_after_sync as replay_sync

# Reúsa constantes / fechas / fix-HANDLE del runner de producción (nombre empieza con
# dígito => import por string, no con `import`).
runner = importlib.import_module("04_run_replay_featsweep_after_sync")

BOOK_FOLDER = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings"


def read_book_status(date_iso):
    path = os.path.join(BOOK_FOLDER, f"bookrec_status_{date_iso}.txt")
    if not os.path.exists(path):
        return None
    out = {}
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="Probe: ¿hay DOM/MBP en el replay?")
    ap.add_argument("--limit", type=int, default=1, help="Últimas N fechas DST (default 1).")
    args = ap.parse_args()

    # Fix cuelgue: ventana Replay por HANDLE (evita enumerar todo el desktop UIA).
    replay_sync.get_replay_controls = runner._get_replay_controls_by_handle
    print("FIX ventana Replay por HANDLE activo.")

    dates = runner.DATES_DST[-args.limit:] if args.limit > 0 else runner.DATES_DST
    date_iso_list = [replay_sync.date_iso_from_replay(d) for d in dates]
    print(f"Fechas a reproducir ({len(dates)}): {dates[0]} -> {dates[-1]}")
    print(f"Salida BookRecorder: {BOOK_FOLDER}")

    run_plan = replay_sync.build_run_plan(quick=True, x1_only=False, x10_only=True)

    out_folder = Path(BOOK_FOLDER) / "_probe_runs"
    out_folder.mkdir(parents=True, exist_ok=True)

    print("\nINICIANDO REPLAY (probe BookRecorder). No tocar el foco de ATAS.\n")
    replay_sync.run_replay_period(
        date_iso_list,
        output_folder=out_folder,
        run_plan=run_plan,
        report_prefix="bookrec_probe",
        force=True,
        step=False,
        compare_only=False,
        replay_to_time=runner.REPLAY_END_TIME,
    )

    print("\n=== RESULTADO PROBE DOM/MBP ===")
    print(f"{'fecha':12} {'mbp_rows':>9} {'mbo_rows':>9} {'tape_rows':>10}  veredicto")
    any_mbp = False
    for date_iso in date_iso_list:
        st = read_book_status(date_iso)
        if st is None:
            print(f"{date_iso:12} {'--':>9} {'--':>9} {'--':>10}  SIN status (¿BookRecorder en el chart?)")
            continue
        mbp = int(st.get("mbp_rows", "0") or 0)
        mbo = int(st.get("mbo_rows", "0") or 0)
        tape = int(st.get("tape_rows", "0") or 0)
        verdict = "DOM EN REPLAY (pinta naranja)" if mbp > 0 else "sin libro (solo live)"
        if mbp > 0:
            any_mbp = True
        print(f"{date_iso:12} {mbp:>9} {mbo:>9} {tape:>10}  {verdict}")

    print("\nCONCLUSION:", "el DOM/MBP SÍ está en tu replay -> el overlay naranja pinta en replay."
          if any_mbp else
          "no hay MBP en el replay -> el overlay naranja solo se verá operando en vivo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
