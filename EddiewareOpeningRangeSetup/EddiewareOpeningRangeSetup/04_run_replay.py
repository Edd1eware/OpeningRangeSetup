from pywinauto import Desktop
import time
import pyperclip
import os

# =========================================================
# CONFIG
# =========================================================

DATES = [

    # =========================
    # DST — MARZO 2023
    # =========================

    "13/03/2023",
    "14/03/2023",
    "15/03/2023",
    "16/03/2023",
    "17/03/2023",

    "20/03/2023",
    "21/03/2023",
    "22/03/2023",
    "23/03/2023",
    "24/03/2023",

    "27/03/2023",
    "28/03/2023",
    "29/03/2023",
    "30/03/2023",
    "31/03/2023",

    # =========================
    # DST — ABRIL 2023
    # =========================

    "03/04/2023",
    "04/04/2023",
    "05/04/2023",
    "06/04/2023",
    "07/04/2023",

    "10/04/2023",
    "11/04/2023",
    "12/04/2023",
    "13/04/2023",
    "14/04/2023",

    "17/04/2023",
    "18/04/2023",
    "19/04/2023",
    "20/04/2023",
    "21/04/2023",

    "24/04/2023",
    "25/04/2023",
    "26/04/2023",
    "27/04/2023",
    "28/04/2023",

    # =========================
    # DST — MAYO 2023
    # =========================

    "01/05/2023",
    "02/05/2023",
    "03/05/2023",
    "04/05/2023",
    "05/05/2023",

    "08/05/2023",
    "09/05/2023",
    "10/05/2023",
    "11/05/2023",
    "12/05/2023",

    "15/05/2023",
    "16/05/2023",
    "17/05/2023",
    "18/05/2023",
    "19/05/2023",

    "22/05/2023",
    "23/05/2023",
    "24/05/2023",
    "25/05/2023",
    "26/05/2023",

    "29/05/2023",
    "30/05/2023",
    "31/05/2023",

    # =========================
    # DST — JUNIO 2023
    # =========================

    "01/06/2023",
    "02/06/2023",

    "05/06/2023",
    "06/06/2023",
    "07/06/2023",
    "08/06/2023",
    "09/06/2023",

    "12/06/2023",
    "13/06/2023",
    "14/06/2023",
    "15/06/2023",
    "16/06/2023",

    "19/06/2023",
    "20/06/2023",
    "21/06/2023",
    "22/06/2023",
    "23/06/2023",

    "26/06/2023",
    "27/06/2023",
    "28/06/2023",
    "29/06/2023",
    "30/06/2023",

    # =========================
    # DST — JULIO 2023
    # =========================

    "03/07/2023",
    "04/07/2023",
    "05/07/2023",
    "06/07/2023",
    "07/07/2023",

    "10/07/2023",
    "11/07/2023",
    "12/07/2023",
    "13/07/2023",
    "14/07/2023",

    "17/07/2023",
    "18/07/2023",
    "19/07/2023",
    "20/07/2023",
    "21/07/2023",

    "24/07/2023",
    "25/07/2023",
    "26/07/2023",
    "27/07/2023",
    "28/07/2023",

    "31/07/2023",

    # =========================
    # DST — AGOSTO 2023
    # =========================

    "01/08/2023",
    "02/08/2023",
    "03/08/2023",
    "04/08/2023",

    "07/08/2023",
    "08/08/2023",
    "09/08/2023",
    "10/08/2023",
    "11/08/2023",

    "14/08/2023",
    "15/08/2023",
    "16/08/2023",
    "17/08/2023",
    "18/08/2023",

    "21/08/2023",
    "22/08/2023",
    "23/08/2023",
    "24/08/2023",
    "25/08/2023",

    "28/08/2023",
    "29/08/2023",
    "30/08/2023",
    "31/08/2023",

    # =========================
    # DST — SEPTIEMBRE 2023
    # =========================

    "01/09/2023",

    "04/09/2023",
    "05/09/2023",
    "06/09/2023",
    "07/09/2023",
    "08/09/2023",

    "11/09/2023",
    "12/09/2023",
    "13/09/2023",
    "14/09/2023",
    "15/09/2023",

    "18/09/2023",
    "19/09/2023",
    "20/09/2023",
    "21/09/2023",
    "22/09/2023",

    "25/09/2023",
    "26/09/2023",
    "27/09/2023",
    "28/09/2023",
    "29/09/2023",

    # =========================
    # DST — OCTUBRE 2023
    # =========================

    "02/10/2023",
    "03/10/2023",
    "04/10/2023",
    "05/10/2023",
    "06/10/2023",

    "09/10/2023",
    "10/10/2023",
    "11/10/2023",
    "12/10/2023",
    "13/10/2023",

    "16/10/2023",
    "17/10/2023",
    "18/10/2023",
    "19/10/2023",
    "20/10/2023",

    "23/10/2023",
    "24/10/2023",
    "25/10/2023",
    "26/10/2023",
    "27/10/2023",

    "30/10/2023",
    "31/10/2023",

    # =========================
    # DST — NOVIEMBRE 2023
    # =========================

    "01/11/2023",
    "02/11/2023",
    "03/11/2023",
]

WAIT_SECONDS = 50

EXPORT_FOLDER = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"

TARGET_FILE = os.path.join(EXPORT_FOLDER, "target_date.txt")

# =========================================================
# FUNCIONES
# =========================================================

def write_target_date(date_ddmmyyyy):
    dd, mm, yyyy = date_ddmmyyyy.split("/")
    target = f"{yyyy}-{mm}-{dd}"

    os.makedirs(EXPORT_FOLDER, exist_ok=True)

    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        f.write(target)

    print(f"Fecha objetivo escrita para ATAS: {target}")


def get_replay():
    desktop = Desktop(backend="uia")

    candidates = desktop.windows(title_re=".*Replay.*", visible_only=True)

    if not candidates:
        raise RuntimeError("No encontré ninguna ventana Replay visible. Abre Replay en ATAS antes de correr el script.")

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

    candidates = app.windows(title_re=".*Replay.*", top_level_only=True)

    if not candidates:
        raise RuntimeError("No encontré ninguna ventana Replay abierta.")

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

    # fallback: usar la primera si ninguna pasó filtros
    replay = candidates[0]
    print("Usando Replay fallback:", replay.window_text())
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


def expected_csv_path(date_ddmmyyyy):
    dd, mm, yyyy = date_ddmmyyyy.split("/")
    return os.path.join(
        EXPORT_FOLDER,
        f"footprint_atas_{yyyy}-{mm}-{dd}_0930_1030_NY.csv"
    )


# =========================================================
# LOOP PRINCIPAL
# =========================================================

print("\nINICIANDO AUTOMATIZACION ATAS REPLAY\n")

for date in DATES:

    print("\n" + "=" * 70)
    print(f"PROCESANDO {date}")
    print("=" * 70)

    # 1. Escribir fecha objetivo para que C# solo exporte ese día
    write_target_date(date)

    # Pequeña pausa para que ATAS/C# pueda leer el txt
    time.sleep(1)

    from_value = f"{date} 09:30 a. m."
    to_value = f"{date} 10:35 a. m."

    # 2. Obtener controles frescos
    replay, from_box, to_box, start_button, stop_button = get_controls()

    # 3. Cambiar fechas
    paste_text(from_box, from_value)
    paste_text(to_box, to_value)

    print("Fechas configuradas:")
    print(f"FROM: {from_value}")
    print(f"TO:   {to_value}")

    time.sleep(2)

    # 4. Releer controles antes de Start
    replay, from_box, to_box, start_button, stop_button = get_controls()

    if start_button is None:
        raise Exception("No se encontró botón Start")

    # 5. Start
    print("Iniciando replay...")
    start_button.click_input()

    # 6. Esperar sesión completa
    print(f"Esperando {WAIT_SECONDS} segundos...")
    time.sleep(WAIT_SECONDS)

    # 7. Stop
    replay, from_box, to_box, start_button, stop_button = get_controls()

    if stop_button is not None:
        print("Deteniendo replay...")
        stop_button.click_input()
    else:
        print("No encontré botón Stop; probablemente el replay ya terminó.")

    time.sleep(5)

    # 8. Verificar CSV
    expected_file = expected_csv_path(date)

    if os.path.exists(expected_file):
        size_kb = round(os.path.getsize(expected_file) / 1024, 2)
        print(f"OK EXPORTADO: {expected_file}")
        print(f"Tamaño: {size_kb} KB")
    else:
        print(f"WARNING: no encontré archivo esperado:")
        print(expected_file)

    print("Pausa antes del siguiente día...")
    time.sleep(10)

print("\nTERMINÓ LA SEMANA DE PRUEBA.\n")