from pywinauto import Desktop
import os
import time
import pyperclip

# =========================================================
# CONFIG
# =========================================================

# Fechas en horario DST de Nueva York 2025.
# DST 2025 empieza el domingo 09/03/2025; la primera sesion regular
# a probar es el lunes 10/03/2025. Ultima sesion DST: 31/10/2025.
# Formato requerido por el panel Replay de ATAS: dd/mm/yyyy.
DATES_DST = [
    "10/03/2025",
    "11/03/2025",
    "12/03/2025",
    "13/03/2025",
    "14/03/2025",
    "17/03/2025",
    "18/03/2025",
    "19/03/2025",
    "20/03/2025",
    "21/03/2025",
    "24/03/2025",
    "25/03/2025",
    "26/03/2025",
    "27/03/2025",
    "28/03/2025",
    "31/03/2025",
    "01/04/2025",
    "02/04/2025",
    "03/04/2025",
    "04/04/2025",
    "07/04/2025",
    "08/04/2025",
    "09/04/2025",
    "10/04/2025",
    "11/04/2025",
    "14/04/2025",
    "15/04/2025",
    "16/04/2025",
    "17/04/2025",
    "18/04/2025",
    "21/04/2025",
    "22/04/2025",
    "23/04/2025",
    "24/04/2025",
    "25/04/2025",
    "28/04/2025",
    "29/04/2025",
    "30/04/2025",
    "01/05/2025",
    "02/05/2025",
    "05/05/2025",
    "06/05/2025",
    "07/05/2025",
    "08/05/2025",
    "09/05/2025",
    "12/05/2025",
    "13/05/2025",
    "14/05/2025",
    "15/05/2025",
    "16/05/2025",
    "19/05/2025",
    "20/05/2025",
    "21/05/2025",
    "22/05/2025",
    "23/05/2025",
    "26/05/2025",
    "27/05/2025",
    "28/05/2025",
    "29/05/2025",
    "30/05/2025",
    "02/06/2025",
    "03/06/2025",
    "04/06/2025",
    "05/06/2025",
    "06/06/2025",
    "09/06/2025",
    "10/06/2025",
    "11/06/2025",
    "12/06/2025",
    "13/06/2025",
    "16/06/2025",
    "17/06/2025",
    "18/06/2025",
    "19/06/2025",
    "20/06/2025",
    "23/06/2025",
    "24/06/2025",
    "25/06/2025",
    "26/06/2025",
    "27/06/2025",
    "30/06/2025",
    "01/07/2025",
    "02/07/2025",
    "03/07/2025",
    "04/07/2025",
    "07/07/2025",
    "08/07/2025",
    "09/07/2025",
    "10/07/2025",
    "11/07/2025",
    "14/07/2025",
    "15/07/2025",
    "16/07/2025",
    "17/07/2025",
    "18/07/2025",
    "21/07/2025",
    "22/07/2025",
    "23/07/2025",
    "24/07/2025",
    "25/07/2025",
    "28/07/2025",
    "29/07/2025",
    "30/07/2025",
    "31/07/2025",
    "01/08/2025",
    "04/08/2025",
    "05/08/2025",
    "06/08/2025",
    "07/08/2025",
    "08/08/2025",
    "11/08/2025",
    "12/08/2025",
    "13/08/2025",
    "14/08/2025",
    "15/08/2025",
    "18/08/2025",
    "19/08/2025",
    "20/08/2025",
    "21/08/2025",
    "22/08/2025",
    "25/08/2025",
    "26/08/2025",
    "27/08/2025",
    "28/08/2025",
    "29/08/2025",
    "01/09/2025",
    "02/09/2025",
    "03/09/2025",
    "04/09/2025",
    "05/09/2025",
    "08/09/2025",
    "09/09/2025",
    "10/09/2025",
    "11/09/2025",
    "12/09/2025",
    "15/09/2025",
    "16/09/2025",
    "17/09/2025",
    "18/09/2025",
    "19/09/2025",
    "22/09/2025",
    "23/09/2025",
    "24/09/2025",
    "25/09/2025",
    "26/09/2025",
    "29/09/2025",
    "30/09/2025",
    "01/10/2025",
    "02/10/2025",
    "03/10/2025",
    "06/10/2025",
    "07/10/2025",
    "08/10/2025",
    "09/10/2025",
    "10/10/2025",
    "13/10/2025",
    "14/10/2025",
    "15/10/2025",
    "16/10/2025",
    "17/10/2025",
    "20/10/2025",
    "21/10/2025",
    "22/10/2025",
    "23/10/2025",
    "24/10/2025",
    "27/10/2025",
    "28/10/2025",
    "29/10/2025",
    "30/10/2025",
    "31/10/2025",
]

WAIT_SECONDS = 120

EXPORT_FOLDER = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
RESULTS_FOLDER = os.path.join(EXPORT_FOLDER, "trade_results_score")
TARGET_FILE = os.path.join(EXPORT_FOLDER, "target_trade_result_date.txt")


# =========================================================
# FUNCIONES
# =========================================================

def write_target_date(date_ddmmyyyy):
    dd, mm, yyyy = date_ddmmyyyy.split("/")
    target = f"{yyyy}-{mm}-{dd}"

    os.makedirs(EXPORT_FOLDER, exist_ok=True)
    os.makedirs(RESULTS_FOLDER, exist_ok=True)

    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        f.write(target)

    print(f"Fecha objetivo escrita para ATAS: {target}")


def get_replay():
    desktop = Desktop(backend="uia")
    candidates = desktop.windows(title_re=".*Replay.*", visible_only=True)

    if not candidates:
        raise RuntimeError("No encontre ninguna ventana Replay visible. Abre Replay en ATAS antes de correr el script.")

    print(f"Ventanas Replay encontradas: {len(candidates)}")

    for w in candidates:
        try:
            if w.is_visible() and w.is_enabled():
                print("Usando Replay:", w.window_text())
                w.set_focus()
                time.sleep(1)
                return w
        except Exception:
            pass

    replay = candidates[0]
    replay.set_focus()
    time.sleep(1)
    return replay


def paste_text(control, value):
    control.click_input()
    time.sleep(0.3)

    control.type_keys("^a")
    time.sleep(0.3)

    pyperclip.copy(value)
    time.sleep(0.3)

    control.type_keys("^v")
    time.sleep(0.8)


def get_controls():
    replay = get_replay()

    edits = replay.descendants(control_type="Edit")
    buttons = replay.descendants(control_type="Button")

    from_box = edits[0]
    to_box = edits[2]

    start_button = None
    stop_button = None

    for b in buttons:
        txt = b.window_text()

        if txt == "Start":
            start_button = b

        if txt == "Stop":
            stop_button = b

    return replay, from_box, to_box, start_button, stop_button


def expected_result_path(date_ddmmyyyy):
    dd, mm, yyyy = date_ddmmyyyy.split("/")

    return os.path.join(
        RESULTS_FOLDER,
        f"score_trade_result_{yyyy}-{mm}-{dd}_NY.csv"
    )


def print_result_file(path):
    if not os.path.exists(path):
        print("WARNING: no encontre archivo esperado:")
        print(path)
        return

    size_kb = round(os.path.getsize(path) / 1024, 2)
    print(f"OK EXPORTADO: {path}")
    print(f"Tamano: {size_kb} KB")

    with open(path, "r", encoding="utf-8") as f:
        print(f.read().strip())


# =========================================================
# LOOP PRINCIPAL
# =========================================================

print("\nINICIANDO REPLAY DST PARA SCORE TRADE RESULTS\n")

for date in DATES_DST:
    print("\n" + "=" * 70)
    print(f"PROCESANDO {date}")
    print("=" * 70)

    write_target_date(date)
    time.sleep(1)

    from_value = f"{date} 09:30 a. m."
    to_value = f"{date} 10:35 a. m."

    replay, from_box, to_box, start_button, stop_button = get_controls()

    paste_text(from_box, from_value)
    paste_text(to_box, to_value)

    print("Fechas configuradas:")
    print(f"FROM: {from_value}")
    print(f"TO:   {to_value}")

    time.sleep(2)

    replay, from_box, to_box, start_button, stop_button = get_controls()

    if start_button is None:
        raise RuntimeError("No se encontro boton Start")

    print("Iniciando replay...")
    start_button.click_input()

    print(f"Esperando {WAIT_SECONDS} segundos...")
    time.sleep(WAIT_SECONDS)

    replay, from_box, to_box, start_button, stop_button = get_controls()

    if stop_button is not None:
        print("Deteniendo replay...")
        stop_button.click_input()
    else:
        print("No encontre boton Stop; probablemente el replay ya termino.")

    time.sleep(5)

    print_result_file(expected_result_path(date))

    print("Pausa antes del siguiente dia...")
    time.sleep(10)

print("\nTERMINO LA PRUEBA DST.\n")
