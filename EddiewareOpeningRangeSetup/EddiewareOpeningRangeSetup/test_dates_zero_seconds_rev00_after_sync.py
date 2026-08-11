import os
import sys
import time
from datetime import datetime

import visual_replay_test_common_after_sync as replay_common
from visual_replay_test_common_after_sync import (
    discover_trade_rows,
    read_csv_rows,
    timeline_path,
    to_float,
)


def get_replay_controls_rev00():
    """Localiza los DateEdit FROM y TO sin depender del orden de UI Automation."""
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    candidates = desktop.windows(title_re=".*Replay.*", visible_only=True)
    if not candidates:
        raise RuntimeError("Abre una ventana Replay visible en ATAS.")

    replay = candidates[0]
    replay.set_focus()
    edits = replay.descendants(control_type="Edit")
    buttons = replay.descendants(control_type="Button")

    # ATAS expone cada fecha dos veces: DateEdit + TextBox interno.
    # La versión anterior tomaba edits[0] y edits[1], ambos pertenecientes a FROM.
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

    if from_box is None or to_box is None:
        raise RuntimeError("No encontré los campos FROM/TO del Replay.")

    start_button = next(
        (button for button in buttons if "start" in button.window_text().lower()),
        None,
    )
    stop_button = next(
        (button for button in buttons if "stop" in button.window_text().lower()),
        None,
    )
    if start_button is None:
        raise RuntimeError("No encontré el botón Start del Replay.")

    return replay, from_box, to_box, start_button, stop_button


def control_value(control):
    try:
        return control.get_value()
    except Exception:
        return control.window_text()


def paste_text_rev00(control, value):
    import pyperclip

    control.set_focus()
    control.type_keys("^a")
    pyperclip.copy(value)
    control.type_keys("^v")
    control.type_keys("{TAB}")


def configure_replay_range_rev00(from_box, to_box, date_replay):
    paste_text_rev00(from_box, f"{date_replay} 09:30 a. m.")
    paste_text_rev00(to_box, f"{date_replay} 09:41 a. m.")
    time.sleep(0.5)

    actual_from = control_value(from_box)
    actual_to = control_value(to_box)
    if (
        date_replay not in actual_from
        or "09:30" not in actual_from
        or date_replay not in actual_to
        or "09:41" not in actual_to
    ):
        raise RuntimeError(
            "ATAS no aceptó el rango del Replay. "
            f"FROM={actual_from!r}, TO={actual_to!r}"
        )

    print(f"Replay configurado: FROM {actual_from} | TO {actual_to}")


def find_candidates():
    candidates = []

    for trade in discover_trade_rows():
        date_iso = trade["fecha"]
        path = timeline_path(date_iso)
        if not path.exists():
            continue

        timeline = read_csv_rows(path)
        if not timeline:
            continue

        duration_seconds = to_float(timeline[-1].get("Seconds_From_Entry"))
        if duration_seconds is None or duration_seconds >= 1:
            continue

        candidates.append(
            {
                "Fecha": date_iso,
                "Entrada_NY": trade.get("EntryTime_NY", ""),
                "Salida_NY": trade.get("ExitTime_NY", ""),
                "Duracion_timeline_ms": round(duration_seconds * 1000, 3),
                "Lado": trade.get("Side", ""),
                "Resultado_exportado": trade.get("Result_Label", ""),
                "Entry": trade.get("Entry_price", ""),
                "SL": trade.get("SL_price", ""),
                "TP": trade.get("TP_price", ""),
            }
        )

    return candidates


def run_visual_dates_rev00():
    rows = find_candidates()
    if not rows:
        print("No se encontraron fechas candidatas.")
        return

    workbook_path = replay_common.create_visual_workbook(
        "test_dates_zero_seconds_rev00",
        rows,
        [
            "Duración subsegundo válida",
            "Duración incorrecta",
            "Movimiento ocurrió pero no pude cronometrar",
            "Datos no cargaron",
        ],
        (
            "Valida trades cuya duración medida fue menor a un segundo. La nueva DLL "
            "exporta EntryTime_NY_Milliseconds, ExitTime_NY_Milliseconds y "
            "Trade_Duration_Milliseconds. Esta revisión corrige la selección de los "
            "campos FROM/TO del Replay."
        ),
    )
    print(f"Excel de validación: {workbook_path}")

    if "--prepare-only" in sys.argv:
        return

    os.startfile(workbook_path)
    print("Configura Replay en X1 antes de comenzar.")

    for index, row in enumerate(rows, 1):
        date_iso = row["Fecha"]
        date_value = datetime.strptime(date_iso, "%Y-%m-%d")
        date_replay = date_value.strftime("%d/%m/%Y")
        saved = replay_common.backup_artifacts(date_iso)

        try:
            input(
                f"\n[{index}/{len(rows)}] {date_iso}. "
                "Presiona ENTER para configurar e iniciar Replay..."
            )
            replay_common.write_target_date(date_iso)
            (
                replay,
                from_box,
                to_box,
                start_button,
                stop_button,
            ) = get_replay_controls_rev00()
            configure_replay_range_rev00(from_box, to_box, date_replay)
            time.sleep(1)
            replay.set_focus()
            start_button.click_input()
            input(
                "Observa ATAS, llena Resultado_visual_que_vi en el Excel "
                "y presiona ENTER para detener y continuar..."
            )
            replay_common.stop_replay(stop_button)
        finally:
            replay_common.restore_artifacts(saved)

    print(f"\nPrueba terminada. Guarda tus observaciones en:\n{workbook_path}")


run_visual_dates_rev00()
