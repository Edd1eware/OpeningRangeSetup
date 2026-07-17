import argparse
import csv
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pyperclip
from pywinauto import Desktop


EXPORT_FOLDER = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator")
RESULTS_FOLDER = EXPORT_FOLDER / "trade_results_score"
TIMELINE_FOLDER = RESULTS_FOLDER / "dynamic_management_timeline"
SYNC_SIGNAL_FOLDER = RESULTS_FOLDER / "replay_sync_signals"
SYNC_RESULT_FOLDER = RESULTS_FOLDER / "replay_sync_results"
TARGET_FILE = EXPORT_FOLDER / "target_trade_result_date.txt"
REPLAY_STARTED_FILE = EXPORT_FOLDER / "replay_trade_result_started_at.txt"
OUTPUT_FOLDER = RESULTS_FOLDER / "visual_tests" / "test_fechas_conflictivas_runs"
EXPECTED_EXPORTER_VERSION = "score-exporter-2026-06-23-v11-canonical-sync-guards"

REPLAY_FROM_TIME = "09:30"
REPLAY_TO_TIME = "09:41"
POLL_SECONDS = 0.05
X1_TIMEOUT_SECONDS = 15 * 60
X10_TIMEOUT_SECONDS = 3 * 60

CONFLICTING_DATES = [
    "2025-07-16",
    "2025-03-14",
    "2025-03-26",
    "2025-04-17",
    "2025-05-12",
    "2025-05-21",
    "2025-06-23",
]

COMPARISON_FIELDS = [
    "Exporter_VERSION",
    "EntryTime_NY_Milliseconds",
    "EntryBar",
    "Entry_price",
    "Side",
    "Signal_Source",
    "BreakOut_SPEED",
    "BreakOut_TICKS_PER_SEC",
    "Speed_Elapsed_SECONDS",
    "Speed_Timing_Source",
    "SL_price",
    "TP_price",
    "SL_ticks",
    "TP_ticks",
    "Result_Label",
    "ExitTime_NY_Milliseconds",
    "Exit_price",
    "result TP SL BE",
    "TP_And_SL_Hit_Same_Update",
]
STRICT_COMPARE_FULL_CSV = True

TERMINAL_RESULTS = {
    "TP",
    "SL",
    "EXIT",
    "BE",
    "TIME_OVER",
    "NO_TRADE",
    "HOLYDAY NO DATA",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Repite fechas conflictivas exclusivamente en Historia X10 y genera "
            "un reporte automático de reproducibilidad."
        )
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Ejecuta dos repeticiones X10, en lugar de tres.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Valida configuración y muestra el plan sin iniciar ATAS Replay.",
    )
    parser.add_argument(
        "--compare-only",
        action="store_true",
        help="Regenera el reporte usando corridas ya guardadas.",
    )
    parser.add_argument(
        "--step",
        action="store_true",
        help="Pide ENTER antes de cada fecha. Por defecto las fechas avanzan automáticamente.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignora corridas ya guardadas y vuelve a correr todas las fechas.",
    )
    return parser.parse_args()


def result_path(date_iso):
    return RESULTS_FOLDER / f"score_trade_result_{date_iso}_NY.csv"


def timeline_path(date_iso):
    return TIMELINE_FOLDER / f"dynamic_timeline_{date_iso}_NY.csv"


def sync_signal_path(date_iso):
    return SYNC_SIGNAL_FOLDER / f"score_trade_signal_snapshot_{date_iso}_NY.json"


def sync_result_path(date_iso):
    return SYNC_RESULT_FOLDER / f"score_trade_result_snapshot_{date_iso}_NY.json"


def destination_result_path(date_iso, run_name):
    return OUTPUT_FOLDER / run_name / result_path(date_iso).name


def destination_timeline_path(date_iso, run_name):
    return OUTPUT_FOLDER / run_name / timeline_path(date_iso).name


def read_csv_row(path):
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            return next(csv.DictReader(handle), None)
    except (OSError, PermissionError, csv.Error):
        return None


def row_has_terminal_result(row):
    if not row:
        return False

    label = str(row.get("Result_Label") or row.get("RESULT") or "").strip().upper()
    if label in {"", "OPEN"}:
        return False

    if label in TERMINAL_RESULTS:
        return True

    value = str(row.get("result TP SL BE") or row.get("RESULT") or "").strip().upper()
    if value in {"", "OPEN", "0", "+0", "-0", "0.0", "+0.0", "-0.0"}:
        return False

    try:
        return float(value.replace("+", "")) != 0
    except ValueError:
        return False


def is_saved_run_complete(date_iso, run_name):
    row = read_csv_row(destination_result_path(date_iso, run_name))
    if not row_has_terminal_result(row):
        return False

    version = str(row.get("Exporter_VERSION") or "").strip()
    return version == EXPECTED_EXPORTER_VERSION


def describe_saved_run(date_iso, run_name):
    row = read_csv_row(destination_result_path(date_iso, run_name)) or {}
    return (
        f"Entry={row.get('Entry_price', '')} | "
        f"Resultado={row.get('Result_Label', '')} | "
        f"Version={row.get('Exporter_VERSION', '')}"
    )


def is_terminal_result(path, started_at):
    if not path.exists():
        return False

    try:
        if path.stat().st_mtime < started_at:
            return False
    except OSError:
        return False

    return row_has_terminal_result(read_csv_row(path))


def format_elapsed(seconds):
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{seconds:02d}"


def get_replay_controls():
    candidates = Desktop(backend="uia").windows(
        title_re=".*Replay.*",
        visible_only=True,
    )
    candidates = [
        window
        for window in candidates
        if window.rectangle().left > -10000 and window.rectangle().top > -10000
    ]
    if not candidates:
        raise RuntimeError("Abre y deja visible la ventana Replay de ATAS.")

    replay = next(
        (
            window
            for window in candidates
            if window.window_text().lower().startswith("replay")
        ),
        candidates[0],
    )
    replay.set_focus()
    edits = replay.descendants(control_type="Edit")
    buttons = replay.descendants(control_type="Button")

    date_edits = [
        edit
        for edit in edits
        if edit.element_info.class_name == "DateEdit"
    ]
    from_box = next(
        (
            edit
            for edit in date_edits
            if edit.element_info.name.strip().lower().startswith("from")
        ),
        None,
    )
    to_box = next(
        (
            edit
            for edit in date_edits
            if edit.element_info.name.strip().lower().startswith("to")
        ),
        None,
    )
    start_button = next(
        (
            button
            for button in buttons
            if button.element_info.automation_id == "PlayButton"
        ),
        None,
    )
    if start_button is None:
        start_button = next(
            (
                button
                for button in buttons
                if button.window_text().strip().lower() in {"start", "play", "iniciar"}
            ),
            None,
        )
    stop_button = next(
        (
            button
            for button in buttons
            if button.window_text().strip().lower() in {"stop", "detener"}
        ),
        None,
    )
    if stop_button is None and start_button is not None:
        play_rect = start_button.rectangle()
        stop_candidates = []
        for button in buttons:
            if button == start_button:
                continue
            rect = button.rectangle()
            same_row = abs(rect.top - play_rect.top) <= 8
            immediately_right = 0 <= rect.left - play_rect.right <= 20
            visible_size = rect.width() > 10 and rect.height() > 10
            if same_row and immediately_right and visible_size:
                stop_candidates.append(button)
        if stop_candidates:
            stop_button = min(
                stop_candidates,
                key=lambda button: button.rectangle().left,
            )

    if from_box is None or to_box is None:
        raise RuntimeError("No encontré los campos FROM/TO de Replay.")
    if start_button is None:
        raise RuntimeError(
            "No encontré el botón Play de Replay "
            "(AutomationId=PlayButton)."
        )

    return replay, from_box, to_box, start_button, stop_button


def control_value(control):
    try:
        return control.get_value()
    except Exception:
        return control.window_text()


def paste_text(control, value):
    control.click_input()
    time.sleep(0.15)
    control.type_keys("^a")
    time.sleep(0.1)
    pyperclip.copy(value)
    control.type_keys("^v")
    control.type_keys("{TAB}")
    time.sleep(0.25)


def configure_replay_range(from_box, to_box, date_iso):
    date_replay = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    expected_from = f"{date_replay} {REPLAY_FROM_TIME} a. m."
    expected_to = f"{date_replay} {REPLAY_TO_TIME} a. m."
    actual_from = ""
    actual_to = ""

    for attempt in range(1, 4):
        paste_text(from_box, expected_from)
        paste_text(to_box, expected_to)
        time.sleep(0.5)
        actual_from = control_value(from_box)
        actual_to = control_value(to_box)

        from_ok = date_replay in actual_from and REPLAY_FROM_TIME in actual_from
        to_ok = date_replay in actual_to and REPLAY_TO_TIME in actual_to
        if from_ok and to_ok and actual_from != actual_to:
            break

        print(
            f"ATAS no confirmó el rango (intento {attempt}/3). "
            f"FROM={actual_from!r}, TO={actual_to!r}"
        )
        time.sleep(0.75)
    else:
        raise RuntimeError(
            "ATAS no aceptó el rango solicitado después de 3 intentos. "
            f"FROM={actual_from!r}, TO={actual_to!r}"
        )

    print(f"Rango: FROM {actual_from} | TO {actual_to}")


def click_stop(stop_button=None):
    def try_click(button):
        if button is None:
            return False
        try:
            button.click_input()
            time.sleep(0.35)
            return True
        except Exception:
            try:
                button.click()
                time.sleep(0.35)
                return True
            except Exception:
                return False

    if try_click(stop_button):
        return

    try:
        _, _, _, _, refreshed_stop = get_replay_controls()
        try_click(refreshed_stop)
    except Exception:
        pass


def wait_for_terminal_result(path, started_at, timeout_seconds, stop_button):
    wait_started = time.time()
    last_second = -1

    while True:
        if is_terminal_result(path, started_at):
            print("\rResultado terminal detectado." + " " * 60)
            time.sleep(0.4)
            return True

        elapsed = time.time() - wait_started
        if elapsed >= timeout_seconds:
            print("\rTimeout esperando resultado." + " " * 60)
            click_stop(stop_button)
            return False

        second = int(elapsed)
        if second != last_second:
            remaining = timeout_seconds - elapsed
            print(
                "\rEsperando CSV terminal: "
                f"{format_elapsed(elapsed)} / resta {format_elapsed(remaining)}",
                end="",
                flush=True,
            )
            last_second = second

        time.sleep(POLL_SECONDS)


def write_runtime_markers(date_iso):
    EXPORT_FOLDER.mkdir(parents=True, exist_ok=True)
    TARGET_FILE.write_text(date_iso, encoding="utf-8")
    REPLAY_STARTED_FILE.write_text(str(time.time()), encoding="utf-8")


def save_file_state(path, backup_folder):
    existed = path.exists()
    backup = backup_folder / path.name
    if existed:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    return path, backup, existed


def restore_file_state(saved):
    path, backup, existed = saved
    if existed and backup.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, path)
    elif not existed and path.exists():
        path.unlink()


def copy_with_retry(source, destination, attempts=10):
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(attempts):
        try:
            shutil.copy2(source, destination)
            return
        except (OSError, PermissionError):
            if attempt == attempts - 1:
                raise
            time.sleep(0.2)


def run_one_date(date_iso, run_name, timeout_seconds, force=False):
    if run_name == "X1" or run_name.startswith("X1_"):
        raise ValueError("Replay X1: DESHABILITADO. Usa Historia X10 únicamente.")
    source_result = result_path(date_iso)
    source_timeline = timeline_path(date_iso)
    destination_result = destination_result_path(date_iso, run_name)
    destination_timeline = destination_timeline_path(date_iso, run_name)

    if not force and is_saved_run_complete(date_iso, run_name):
        print(f"Saltado: {run_name} {date_iso} ya guardado | {describe_saved_run(date_iso, run_name)}")
        return True, "SKIPPED"

    destination_result.unlink(missing_ok=True)
    destination_timeline.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="conflictivas_backup_") as temp:
        backup_folder = Path(temp)
        saved_result = save_file_state(source_result, backup_folder / "result")
        saved_timeline = save_file_state(source_timeline, backup_folder / "timeline")

        try:
            source_result.unlink(missing_ok=True)
            source_timeline.unlink(missing_ok=True)
            if run_name.startswith("X1_"):
                sync_signal_path(date_iso).unlink(missing_ok=True)
                sync_result_path(date_iso).unlink(missing_ok=True)
            write_runtime_markers(date_iso)

            replay, from_box, to_box, start_button, stop_button = get_replay_controls()
            configure_replay_range(from_box, to_box, date_iso)
            replay.set_focus()
            time.sleep(0.5)

            started_at = time.time()
            REPLAY_STARTED_FILE.write_text(str(started_at), encoding="utf-8")
            print(f"Iniciando {run_name} para {date_iso}...")
            start_button.click_input()

            completed = wait_for_terminal_result(
                source_result,
                started_at,
                timeout_seconds,
                stop_button,
            )
            if not completed or not source_result.exists():
                return False, "TIMEOUT_OR_NO_CSV"

            copy_with_retry(source_result, destination_result)
            if source_timeline.exists():
                copy_with_retry(source_timeline, destination_timeline)

            row = read_csv_row(destination_result) or {}
            print(
                f"Guardado: {run_name} {date_iso} | "
                f"Entry={row.get('Entry_price', '')} | "
                f"Resultado={row.get('Result_Label', '')}"
            )
            click_stop(stop_button)
            return True, ""
        finally:
            click_stop()
            restore_file_state(saved_result)
            restore_file_state(saved_timeline)


def normalize(value):
    return str(value or "").strip()


def comparison_fields_for(baseline, compared):
    if STRICT_COMPARE_FULL_CSV and (baseline or compared):
        fields = []
        for row in (baseline, compared):
            if not row:
                continue
            for field in row.keys():
                if field not in fields:
                    fields.append(field)
        return fields

    return COMPARISON_FIELDS


def build_comparison_report(run_plan):
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_FOLDER / "test_fechas_conflictivas_comparacion.csv"
    summary_path = OUTPUT_FOLDER / "test_fechas_conflictivas_resumen.txt"
    baseline_name = "X10_R1"
    compared_names = [name for name, _, _ in run_plan if name != baseline_name]
    report_rows = []
    passed = 0
    failed = 0

    for date_iso in CONFLICTING_DATES:
        baseline_path = OUTPUT_FOLDER / baseline_name / result_path(date_iso).name
        baseline = read_csv_row(baseline_path)

        for compared_name in compared_names:
            compared_path = OUTPUT_FOLDER / compared_name / result_path(date_iso).name
            compared = read_csv_row(compared_path)

            if baseline is None or compared is None:
                differences = ["MISSING_CSV"]
                comparison_fields = COMPARISON_FIELDS
            else:
                comparison_fields = comparison_fields_for(baseline, compared)
                differences = [
                    field
                    for field in comparison_fields
                    if normalize(baseline.get(field)) != normalize(compared.get(field))
                ]

            status = "PASS" if not differences else "FAIL"
            if status == "PASS":
                passed += 1
            else:
                failed += 1

            row = {
                "Fecha": date_iso,
                "Baseline": baseline_name,
                "Comparada": compared_name,
                "Estado": status,
                "Campos_Diferentes": "|".join(differences),
            }
            for field in comparison_fields:
                row[f"{field}_BASELINE_X10"] = (
                    normalize(baseline.get(field)) if baseline else ""
                )
                row[f"{field}_COMPARADA"] = (
                    normalize(compared.get(field)) if compared else ""
                )
            report_rows.append(row)

    headers = list(report_rows[0].keys()) if report_rows else [
        "Fecha",
        "Baseline",
        "Comparada",
        "Estado",
        "Campos_Diferentes",
    ]
    with open(report_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(report_rows)

    overall = "PASS" if failed == 0 and report_rows else "FAIL"
    summary_lines = [
        "TEST DE REPRODUCIBILIDAD HISTORIA X10",
        "Modo comparacion: CSV terminal completo",
        f"Estado general: {overall}",
        f"Comparaciones PASS: {passed}",
        f"Comparaciones FAIL: {failed}",
        "",
    ]
    for row in report_rows:
        summary_lines.append(
            f"{row['Fecha']} {row['Baseline']} vs {row['Comparada']}: "
            f"{row['Estado']}"
            + (
                f" ({row['Campos_Diferentes']})"
                if row["Campos_Diferentes"]
                else ""
            )
        )
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("\n" + "\n".join(summary_lines[:5]))
    print(f"Reporte CSV: {report_path}")
    print(f"Resumen: {summary_path}")
    return overall == "PASS"


def save_global_file(path, backup_folder):
    return save_file_state(path, backup_folder)


def print_plan(run_plan):
    print("\nFechas conflictivas:")
    for date_iso in CONFLICTING_DATES:
        print(f"  - {date_iso}")
    print("\nPlan:")
    for run_name, speed_label, _ in run_plan:
        print(f"  - {run_name}: Replay {speed_label}")
    print(f"\nResultados de prueba: {OUTPUT_FOLDER}")


def main():
    args = parse_args()
    x10_repetitions = 2 if args.quick else 3
    run_plan = [
        (f"X10_R{index}", "X10", X10_TIMEOUT_SECONDS)
        for index in range(1, x10_repetitions + 1)
    ]
    print("Modo: Historia X10 únicamente")
    print("Replay X1: DESHABILITADO")
    print_plan(run_plan)
    print(f"\nVersion esperada DLL/exporter: {EXPECTED_EXPORTER_VERSION}")
    if args.force:
        print("Modo: FORCE, se vuelven a correr fechas aunque ya tengan CSV guardado.")
    else:
        print("Modo: RESUME, se saltan fechas ya guardadas con CSV terminal válido.")

    if args.prepare_only:
        print("\nPREPARE-ONLY correcto. No se inició Replay.")
        return 0

    if args.compare_only:
        return 0 if build_comparison_report(run_plan) else 1

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    failures = []

    with tempfile.TemporaryDirectory(prefix="conflictivas_global_") as temp:
        backup_folder = Path(temp)
        saved_target = save_global_file(TARGET_FILE, backup_folder / "target")
        saved_marker = save_global_file(REPLAY_STARTED_FILE, backup_folder / "marker")

        try:
            previous_speed = None
            for run_name, speed_label, timeout_seconds in run_plan:
                if speed_label != previous_speed:
                    input(
                        f"\nConfigura manualmente Replay en {speed_label}. "
                        "Confirma que ATAS cargó la DLL nueva y presiona ENTER..."
                    )
                    previous_speed = speed_label
                else:
                    print(f"\nComenzando repetición {run_name} en {speed_label}.")

                for index, date_iso in enumerate(CONFLICTING_DATES, 1):
                    print(
                        f"\n[{run_name} {index}/{len(CONFLICTING_DATES)}] "
                        f"{date_iso}."
                    )
                    if args.step:
                        input("Presiona ENTER para iniciar...")
                    try:
                        ok, reason = run_one_date(
                            date_iso,
                            run_name,
                            timeout_seconds,
                            force=args.force,
                        )
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        ok, reason = False, str(exc)
                        print(f"ERROR: {date_iso} {run_name}: {exc}")

                    if not ok:
                        failures.append((date_iso, run_name, reason))
        finally:
            click_stop()
            restore_file_state(saved_target)
            restore_file_state(saved_marker)

    passed = build_comparison_report(run_plan)
    if failures:
        print("\nCorridas con error:")
        for date_iso, run_name, reason in failures:
            print(f"  - {date_iso} {run_name}: {reason}")

    return 0 if passed and not failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        click_stop()
        print("\nPrueba cancelada por el usuario. Se restauraron los archivos originales.")
        raise SystemExit(130)
