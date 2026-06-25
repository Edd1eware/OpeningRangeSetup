import csv
import re
import shutil
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

EXPECTED_EXPORTER_VERSION = "score-exporter-2026-06-23-v11-canonical-sync-guards"
EXPECTED_TIMELINE_VERSION = "dynamic-timeline-2026-06-23-v11-canonical-sync-guards"

TERMINAL_RESULTS = {
    "TP",
    "SL",
    "EXIT",
    "BE",
    "TIME_OVER",
    "NO_TRADE",
    "HOLYDAY NO DATA",
}

# Campos que definen la operativa (lo que afecta WR/PF y los filtros de entrada).
# La sincronia X1/X10 se valida SOLO sobre estos. La telemetria de gestion
# dinamica (CVD, alarmas, trailing, MAE/MFE, velocidad, volumen) depende del
# sample-rate del timeline y difiere entre velocidades sin cambiar el trade ni
# su resultado, asi que no debe tumbar la sincronia.
OPERATIVA_COMPARISON_FIELDS = [
    "Side",
    "Signal_Source",
    "Entry_price",
    "SL_price",
    "TP_price",
    "SL_ticks",
    "TP_ticks",
    "Result_Label",
    "Exit_price",
    "result TP SL BE",
    "score total",
]

DEFAULT_REPLAY_FROM_TIME = "09:30"
DEFAULT_REPLAY_TO_TIME = "09:50"
POLL_SECONDS = 0.05
X1_TIMEOUT_SECONDS = 20 * 60
X10_TIMEOUT_SECONDS = 5 * 60
# Auto-retry del arranque de Replay: 3 intentos de 50 s para confirmar que el
# Replay realmente inició. Si tras los 3 no arranca, se salta a la siguiente fecha.
REPLAY_START_RETRY_ATTEMPTS = 3
REPLAY_START_DETECT_SECONDS = 50
REPLAY_SPEED_CLICK_RATIOS = {
    "X1": (0.20, "1x"),
    "X10": (0.40, "10x"),
}


def date_iso_from_replay(date_ddmmyyyy):
    return datetime.strptime(date_ddmmyyyy, "%d/%m/%Y").strftime("%Y-%m-%d")


def date_replay_from_iso(date_iso):
    return datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def result_path(date_iso):
    return RESULTS_FOLDER / f"score_trade_result_{date_iso}_NY.csv"


def timeline_path(date_iso):
    return TIMELINE_FOLDER / f"dynamic_timeline_{date_iso}_NY.csv"


def sync_signal_path(date_iso):
    return SYNC_SIGNAL_FOLDER / f"score_trade_signal_snapshot_{date_iso}_NY.json"


def sync_result_path(date_iso):
    return SYNC_RESULT_FOLDER / f"score_trade_result_snapshot_{date_iso}_NY.json"


def destination_result_path(output_folder, date_iso, run_name):
    return output_folder / run_name / result_path(date_iso).name


def destination_timeline_path(output_folder, date_iso, run_name):
    return output_folder / run_name / timeline_path(date_iso).name


def read_csv_row(path):
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            return next(csv.DictReader(handle), None)
    except (OSError, PermissionError, csv.Error):
        return None


def row_has_expected_version(row):
    return str((row or {}).get("Exporter_VERSION") or "").strip() == EXPECTED_EXPORTER_VERSION


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


def is_terminal_result(path, started_at=None, require_expected_version=True):
    if not path.exists():
        return False

    if started_at is not None:
        try:
            if path.stat().st_mtime < started_at:
                return False
        except OSError:
            return False

    row = read_csv_row(path)
    if not row_has_terminal_result(row):
        return False

    if not require_expected_version:
        return True

    label = str(row.get("Result_Label") or row.get("RESULT") or "").strip().upper()
    if label == "HOLYDAY NO DATA":
        return True

    return row_has_expected_version(row)


def is_saved_run_complete(output_folder, date_iso, run_name):
    return is_terminal_result(
        destination_result_path(output_folder, date_iso, run_name),
        require_expected_version=True,
    )


def describe_saved_run(output_folder, date_iso, run_name):
    row = read_csv_row(destination_result_path(output_folder, date_iso, run_name)) or {}
    return (
        f"Entry={row.get('Entry_price', '')} | "
        f"Resultado={row.get('Result_Label', '')} | "
        f"Version={row.get('Exporter_VERSION', '')}"
    )


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
        raise RuntimeError("No encontré el botón Play de Replay.")

    return replay, from_box, to_box, start_button, stop_button


def get_replay_speed_text(replay):
    speed_values = []
    for text in replay.descendants(control_type="Text"):
        value = text.window_text().strip()
        if re.fullmatch(r"\d+(?:\.\d+)?x", value):
            speed_values.append(value)

    return speed_values[-1] if speed_values else ""


def set_replay_speed(speed_label, wait_seconds=90):
    target = REPLAY_SPEED_CLICK_RATIOS.get(speed_label.upper())
    if target is None:
        print(f"WARNING: velocidad Replay no soportada por automatización: {speed_label}")
        return False

    ratio, expected_text = target
    started_at = time.time()
    last_warning = ""

    while time.time() - started_at <= wait_seconds:
        try:
            replay, _, _, _, _ = get_replay_controls()
            sliders = replay.descendants(control_type="Slider")
            if not sliders:
                last_warning = "no encontré el slider de velocidad del Replay"
                time.sleep(2)
                continue

            slider = sliders[0]
            rect = slider.rectangle()
            y = max(1, (rect.bottom - rect.top) // 2)
            candidate_ratios = [
                ratio,
                max(0.0, ratio - 0.02),
                min(1.0, ratio + 0.02),
                max(0.0, ratio - 0.04),
                min(1.0, ratio + 0.04),
            ]

            for candidate_ratio in candidate_ratios:
                x = int((rect.right - rect.left) * candidate_ratio)
                slider.click_input(coords=(x, y))
                time.sleep(0.35)
                actual_text = get_replay_speed_text(replay)
                if actual_text == expected_text:
                    print(f"Replay configurado automáticamente en {actual_text}.")
                    return True

            actual_text = get_replay_speed_text(replay)
            last_warning = (
                f"no pude confirmar Replay {expected_text}; "
                f"ATAS reporta {actual_text or 'velocidad desconocida'}"
            )
        except Exception as exc:
            last_warning = str(exc)

        print(
            f"Esperando poder configurar Replay {expected_text}: {last_warning}",
            flush=True,
        )
        time.sleep(2)

    print(f"WARNING: no pude configurar Replay {expected_text}: {last_warning}")
    return False


def control_value(control):
    try:
        return str(control.get_value())
    except Exception:
        try:
            return str(control.window_text())
        except Exception:
            return ""


def paste_text(control, value):
    try:
        control.set_focus()
    except Exception:
        pass

    control.click_input()
    time.sleep(0.15)

    # ATAS DateEdit sometimes leaves focus inside a nested text box. Using both
    # keyboard replacement and ValuePattern makes the date change deterministic.
    for _ in range(2):
        control.type_keys("^a", set_foreground=False)
        time.sleep(0.05)

    pyperclip.copy(value)
    time.sleep(0.05)
    control.type_keys("^v", set_foreground=False)
    time.sleep(0.1)

    try:
        control.iface_value.SetValue(value)
        time.sleep(0.1)
    except Exception:
        pass

    control.type_keys("{TAB}", set_foreground=False)
    time.sleep(0.35)


def refresh_replay_date_controls():
    _, from_box, to_box, _, _ = get_replay_controls()
    return from_box, to_box


def configure_replay_range(
    from_box,
    to_box,
    date_iso,
    replay_from_time=DEFAULT_REPLAY_FROM_TIME,
    replay_to_time=DEFAULT_REPLAY_TO_TIME,
):
    date_replay = date_replay_from_iso(date_iso)
    expected_from = f"{date_replay} {replay_from_time} a. m."
    expected_to = f"{date_replay} {replay_to_time} a. m."
    actual_from = ""
    actual_to = ""

    for attempt in range(1, 4):
        if attempt > 1:
            try:
                from_box, to_box = refresh_replay_date_controls()
            except Exception:
                pass

        paste_text(from_box, expected_from)
        actual_from = control_value(from_box)

        paste_text(to_box, expected_to)
        time.sleep(0.5)
        actual_to = control_value(to_box)

        from_ok = date_replay in actual_from and replay_from_time in actual_from
        to_ok = date_replay in actual_to and replay_to_time in actual_to
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
        if is_terminal_result(path, started_at, require_expected_version=True):
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
                "\rEsperando CSV terminal v11: "
                f"{format_elapsed(elapsed)} / resta {format_elapsed(remaining)}",
                end="",
                flush=True,
            )
            last_second = second

        time.sleep(POLL_SECONDS)


def save_file_state(path, backup_path):
    if not path.exists():
        return None

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return path, backup_path


def restore_file_state(saved):
    if not saved:
        return

    destination, backup = saved
    if backup.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, destination)


def copy_with_retry(source, destination, attempts=5):
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(attempts):
        try:
            shutil.copy2(source, destination)
            return
        except (OSError, PermissionError):
            if attempt == attempts - 1:
                raise
            time.sleep(0.2)


def write_runtime_markers(date_iso):
    EXPORT_FOLDER.mkdir(parents=True, exist_ok=True)
    TARGET_FILE.write_text(date_iso, encoding="utf-8")


def restore_saved_run_to_global(output_folder, date_iso, run_name):
    saved_result = destination_result_path(output_folder, date_iso, run_name)
    saved_timeline = destination_timeline_path(output_folder, date_iso, run_name)

    if saved_result.exists():
        copy_with_retry(saved_result, result_path(date_iso))
    if saved_timeline.exists():
        copy_with_retry(saved_timeline, timeline_path(date_iso))


def replay_is_playing(start_button, stop_button):
    # ATAS deshabilita Play y habilita Stop mientras el Replay corre.
    try:
        if start_button is not None and not start_button.is_enabled():
            return True
    except Exception:
        pass
    try:
        if stop_button is not None and stop_button.is_enabled():
            return True
    except Exception:
        pass
    return False


def replay_produced_output(source_result, source_timeline, started_at):
    # El exporter escribe CSV/timeline en cuanto el Replay produce datos.
    for path in (source_result, source_timeline):
        try:
            if path.exists() and path.stat().st_mtime >= started_at:
                return True
        except OSError:
            pass
    return False


def start_replay_with_retries(
    source_result,
    source_timeline,
    from_box,
    to_box,
    date_iso,
    replay_from_time,
    replay_to_time,
    start_button,
    stop_button,
):
    for attempt in range(1, REPLAY_START_RETRY_ATTEMPTS + 1):
        if attempt > 1:
            # Reinicio limpio: re-tomar controles y re-configurar el rango antes
            # de volver a darle Play.
            try:
                from_box, to_box = refresh_replay_date_controls()
                configure_replay_range(
                    from_box,
                    to_box,
                    date_iso,
                    replay_from_time=replay_from_time,
                    replay_to_time=replay_to_time,
                )
                _, _, _, start_button, stop_button = get_replay_controls()
            except Exception as exc:
                print(f"No pude re-preparar Replay (intento {attempt}): {exc}")

        started_at = time.time()
        REPLAY_STARTED_FILE.write_text(str(started_at), encoding="utf-8")
        try:
            start_button.click_input()
        except Exception as exc:
            print(
                f"No pude dar Play (intento {attempt}/{REPLAY_START_RETRY_ATTEMPTS}): {exc}"
            )

        detect_started = time.time()
        last_second = -1
        while time.time() - detect_started < REPLAY_START_DETECT_SECONDS:
            if replay_is_playing(start_button, stop_button) or replay_produced_output(
                source_result, source_timeline, started_at
            ):
                print(
                    f"\rReplay iniciado (intento {attempt}/{REPLAY_START_RETRY_ATTEMPTS})."
                    + " " * 30
                )
                return started_at

            second = int(time.time() - detect_started)
            if second != last_second:
                print(
                    f"\rDetectando inicio de Replay {attempt}/{REPLAY_START_RETRY_ATTEMPTS}: "
                    f"{second:02d}/{REPLAY_START_DETECT_SECONDS}s",
                    end="",
                    flush=True,
                )
                last_second = second
            time.sleep(POLL_SECONDS)

        print(
            f"\rReplay no inició en {REPLAY_START_DETECT_SECONDS}s "
            f"(intento {attempt}/{REPLAY_START_RETRY_ATTEMPTS})." + " " * 20
        )
        click_stop(stop_button)

    return None


def run_one_date(
    date_iso,
    run_name,
    timeout_seconds,
    output_folder,
    force=False,
    replay_from_time=DEFAULT_REPLAY_FROM_TIME,
    replay_to_time=DEFAULT_REPLAY_TO_TIME,
    keep_global_result=True,
):
    source_result = result_path(date_iso)
    source_timeline = timeline_path(date_iso)
    destination_result = destination_result_path(output_folder, date_iso, run_name)
    destination_timeline = destination_timeline_path(output_folder, date_iso, run_name)

    can_skip = not force and is_saved_run_complete(output_folder, date_iso, run_name)
    if can_skip and run_name.startswith("X1_") and not sync_result_path(date_iso).exists():
        can_skip = False

    if can_skip:
        print(
            f"Saltado: {run_name} {date_iso} ya guardado | "
            f"{describe_saved_run(output_folder, date_iso, run_name)}"
        )
        if keep_global_result:
            restore_saved_run_to_global(output_folder, date_iso, run_name)
        return True, "SKIPPED"

    destination_result.unlink(missing_ok=True)
    destination_timeline.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="replay_sync_runner_backup_") as temp:
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
            configure_replay_range(
                from_box,
                to_box,
                date_iso,
                replay_from_time=replay_from_time,
                replay_to_time=replay_to_time,
            )
            replay.set_focus()
            time.sleep(0.5)

            print(f"Iniciando {run_name} para {date_iso}...")
            started_at = start_replay_with_retries(
                source_result,
                source_timeline,
                from_box,
                to_box,
                date_iso,
                replay_from_time,
                replay_to_time,
                start_button,
                stop_button,
            )
            if started_at is None:
                print(
                    f"Replay no arrancó tras {REPLAY_START_RETRY_ATTEMPTS} intentos; "
                    f"salto {run_name} {date_iso}."
                )
                if keep_global_result:
                    restore_file_state(saved_result)
                    restore_file_state(saved_timeline)
                return False, "REPLAY_NOT_STARTED"

            completed = wait_for_terminal_result(
                source_result,
                started_at,
                timeout_seconds,
                stop_button,
            )
            if not completed or not source_result.exists():
                if keep_global_result:
                    restore_file_state(saved_result)
                    restore_file_state(saved_timeline)
                return False, "TIMEOUT_OR_NO_CSV"

            copy_with_retry(source_result, destination_result)
            if source_timeline.exists():
                copy_with_retry(source_timeline, destination_timeline)

            row = read_csv_row(destination_result) or {}
            print(
                f"Guardado: {run_name} {date_iso} | "
                f"Entry={row.get('Entry_price', '')} | "
                f"Resultado={row.get('Result_Label', '')} | "
                f"Version={row.get('Exporter_VERSION', '')}"
            )
            click_stop(stop_button)
            return True, ""
        finally:
            click_stop()
            if not keep_global_result:
                restore_file_state(saved_result)
                restore_file_state(saved_timeline)


def normalize(value):
    return str(value or "").strip()


def comparison_fields_for(baseline, compared):
    fields = []
    for row in (baseline, compared):
        if not row:
            continue
        for field in row.keys():
            if field not in fields:
                fields.append(field)
    return fields


def build_comparison_report(output_folder, date_iso_list, run_plan, report_prefix):
    output_folder.mkdir(parents=True, exist_ok=True)
    report_path = output_folder / f"{report_prefix}_comparacion.csv"
    summary_path = output_folder / f"{report_prefix}_resumen.txt"
    baseline_name = "X1_R1"
    compared_names = [name for name, _, _ in run_plan if name != baseline_name]
    report_rows = []
    passed = 0
    failed = 0

    for date_iso in date_iso_list:
        baseline_path = destination_result_path(output_folder, date_iso, baseline_name)
        baseline = read_csv_row(baseline_path)

        for compared_name in compared_names:
            compared_path = destination_result_path(output_folder, date_iso, compared_name)
            compared = read_csv_row(compared_path)

            if baseline is None or compared is None:
                differences = ["MISSING_CSV"]
                comparison_fields = []
            else:
                # El reporte sigue volcando la fila completa para inspeccion,
                # pero el PASS/FAIL se decide solo sobre la operativa.
                comparison_fields = comparison_fields_for(baseline, compared)
                operativa_fields = [
                    field
                    for field in OPERATIVA_COMPARISON_FIELDS
                    if field in baseline or field in compared
                ]
                differences = [
                    field
                    for field in operativa_fields
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
                row[f"{field}_X1"] = normalize(baseline.get(field)) if baseline else ""
                row[f"{field}_COMPARADA"] = normalize(compared.get(field)) if compared else ""
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
        "TEST DE SINCRONICIDAD REPLAY X1/X10",
        "Modo comparacion: operativa (side/entry/SL/TP/exit/result/score)",
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


def build_run_plan(quick=True, x1_only=False, x10_only=False):
    if x1_only and x10_only:
        raise ValueError("No uses --x1-only y --x10-only al mismo tiempo.")

    if x1_only:
        return [("X1_R1", "X1", X1_TIMEOUT_SECONDS)]

    x10_repetitions = 1 if quick else 3
    x10_runs = [
        (f"X10_R{index}", "X10", X10_TIMEOUT_SECONDS)
        for index in range(1, x10_repetitions + 1)
    ]

    if x10_only:
        return x10_runs

    return [("X1_R1", "X1", X1_TIMEOUT_SECONDS), *x10_runs]


def run_replay_period(
    date_iso_list,
    output_folder,
    run_plan,
    report_prefix,
    force=False,
    step=False,
    compare_only=False,
    replay_from_time=DEFAULT_REPLAY_FROM_TIME,
    replay_to_time=DEFAULT_REPLAY_TO_TIME,
):
    output_folder.mkdir(parents=True, exist_ok=True)

    if compare_only:
        passed = build_comparison_report(output_folder, date_iso_list, run_plan, report_prefix)
        return passed, []

    failures = []
    previous_speed = None

    with tempfile.TemporaryDirectory(prefix="replay_sync_runner_global_") as temp:
        backup_folder = Path(temp)
        saved_target = save_file_state(TARGET_FILE, backup_folder / "target")
        saved_marker = save_file_state(REPLAY_STARTED_FILE, backup_folder / "marker")

        try:
            for run_name, speed_label, timeout_seconds in run_plan:
                if speed_label != previous_speed:
                    print(f"\nConfigurando Replay en {speed_label}...")
                    if not set_replay_speed(speed_label):
                        input(
                            f"Configura manualmente Replay en {speed_label}. "
                            "Confirma que ATAS cargó la DLL v11 nueva y presiona ENTER..."
                        )
                    previous_speed = speed_label
                else:
                    print(f"\nComenzando repetición {run_name} en {speed_label}.")

                for index, date_iso in enumerate(date_iso_list, 1):
                    print(
                        f"\n[{run_name} {index}/{len(date_iso_list)}] "
                        f"{date_iso}."
                    )
                    if step:
                        input("Presiona ENTER para iniciar...")

                    try:
                        ok, reason = run_one_date(
                            date_iso,
                            run_name,
                            timeout_seconds,
                            output_folder,
                            force=force,
                            replay_from_time=replay_from_time,
                            replay_to_time=replay_to_time,
                            keep_global_result=True,
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

    comparable = any(name != "X1_R1" for name, _, _ in run_plan)
    passed = True
    if comparable:
        passed = build_comparison_report(output_folder, date_iso_list, run_plan, report_prefix)

    return passed, failures
