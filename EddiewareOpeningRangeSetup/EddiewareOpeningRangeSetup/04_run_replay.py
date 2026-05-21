from pywinauto import Desktop
import time
import pyperclip
import os

# =========================================================
# CONFIG
# =========================================================

DATES = [

    "10/02/2023",

    "13/02/2023",
    "14/02/2023",
    "15/02/2023",
    "16/02/2023",
    "17/02/2023",

    "20/02/2023",
    "21/02/2023",
    "22/02/2023",
    "23/02/2023",
    "24/02/2023",

    "27/02/2023",
    "28/02/2023",

    # =========================
    # EST — MARZO 2023
    # =========================

    "01/03/2023",
    "02/03/2023",
    "03/03/2023",

    "06/03/2023",
    "07/03/2023",
    "08/03/2023",
    "09/03/2023",
    "10/03/2023",
]

WAIT_SECONDS = 120

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