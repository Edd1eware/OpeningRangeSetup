"""Recorre en el Replay de ATAS las fechas de las operaciones reales de la cuenta
Lucid, deja que el indicador 19_Inside_Control_Trade_Navigator las pinte y guarda
una captura del grafico por fecha.

Las capturas van a C:\\Users\\k_99_\\Desktop\\Imagenes_Diario_de_trading con el
nombre de la fecha del replay.

Uso:
    python -u 19_paint_real_trades.py                # todas las fechas
    python -u 19_paint_real_trades.py 2026-05-08     # solo una
    python -u 19_paint_real_trades.py --from 2026-05-20

Requiere ATAS abierto, el Replay con el modulo del grafico ya seleccionado y el
indicador agregado al grafico NQ M1.
"""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import pyperclip
import win32con
import win32gui
import win32ui
from ctypes import windll
from PIL import Image
from pywinauto import Application
from pywinauto.mouse import click as mouse_click

TRADES_CSV = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\lucid_real_trades.csv")
CURSOR_FILE = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\inside_control_current.txt")
SHOTS = Path(r"C:\Users\k_99_\Desktop\Imagenes_Diario_de_trading")

# El replay avanza minuto a minuto y rechaza un inicio que no sea borde de
# sesion: 09:25 da error. 09:30-09:50 arranca en la apertura y cubre todas las
# entradas (09:31-09:39) y sus salidas.
REPLAY_FROM = "09:30"
REPLAY_TO = "09:50"

# Coordenadas del menu de velocidad: el desplegable es un popup propio que no
# aparece en el arbol UIA de la ventana, asi que se elige por posicion.
SPEED_BUTTON = (355, 148)
SPEED_OPTIONS = {
    "0.1x": 177, "0.3x": 200, "0.5x": 223, "1x": 246,
    "5x": 268, "10x": 291, "100x": 314, "1000x": 338,
}
REPLAY_SPEED = "10x"

PLAY_TIMEOUT_SECONDS = 600


# ------------------------------------------------------------------- ventanas


def find_window(predicate) -> int | None:
    found = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and predicate(win32gui.GetWindowText(hwnd)):
            found.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


def ensure_atas_restored():
    """Un ATAS minimizado deja de renderizar sus paneles y el Replay solo expone
    los botones Restore/Close, sin campos de fecha."""
    hwnd = find_window(lambda t: t.startswith("ATAS - "))
    if hwnd is None:
        raise SystemExit("No encontre la ventana principal de ATAS.")
    left, top, right, _ = win32gui.GetWindowRect(hwnd)
    if left < -1000 or top < -1000:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(1.5)
    return hwnd


def screenshot(hwnd: int, path: Path):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top

    window_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(window_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)
    try:
        windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
        info = bitmap.GetInfo()
        image = Image.frombuffer(
            "RGB", (info["bmWidth"], info["bmHeight"]),
            bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)


# -------------------------------------------------------------------- replay


class Replay:
    def __init__(self):
        self.hwnd = find_window(lambda t: t.lower().startswith("replay"))
        if self.hwnd is None:
            raise SystemExit("No hay ventana Replay visible.")
        self.app = Application(backend="uia").connect(handle=self.hwnd)
        self.bring_to_front()

    def bring_to_front(self):
        """El Replay flota pero puede quedar DETRAS de la ventana principal de
        ATAS. Si eso pasa, un click_input por coordenadas aterriza en el panel
        que este encima. Dejarlo topmost evita el problema."""
        win32gui.SetWindowPos(
            self.hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
        )
        time.sleep(0.5)

    @staticmethod
    def _press(control, label: str) -> bool:
        """Clic real de raton en el centro del control. invoke() por UIA NO
        dispara estos botones WPF: devuelve sin error y no pasa nada (se vio con
        Select, PlayButton y el selector de velocidad)."""
        try:
            point = control.rectangle().mid_point()
            mouse_click(coords=(point.x, point.y))
            return True
        except Exception:
            try:
                control.invoke()
                return True
            except Exception as exc:
                print(f"   no pude pulsar {label}: {exc}")
                return False

    def _window(self):
        window = self.app.window(handle=self.hwnd)
        window.wrapper_object()
        return window

    def buttons(self) -> dict:
        return {
            (b.element_info.automation_id or b.window_text().strip()): b
            for b in self._window().descendants(control_type="Button")
        }

    def edits(self) -> dict:
        return {
            (e.element_info.automation_id or ""): e
            for e in self._window().descendants(control_type="Edit")
        }

    def status(self) -> str:
        texts = [t.window_text() for t in self._window().descendants(control_type="Text")]
        return " | ".join(t for t in texts if t.strip())

    @staticmethod
    def _value(control) -> str:
        try:
            return str(control.get_value())
        except Exception:
            return str(control.window_text())

    @staticmethod
    def _paste(control, value: str):
        # El teclado es lo que realmente aplica: SetValue sobre este DateEdit
        # devuelve sin error pero deja el valor anterior. Con la ventana ya
        # topmost, el click aterriza en el campo correcto.
        control.click_input()
        time.sleep(0.25)
        control.type_keys("^a", set_foreground=False)
        time.sleep(0.1)
        pyperclip.copy(value)
        time.sleep(0.1)
        control.type_keys("^v", set_foreground=False)
        time.sleep(0.35)
        try:
            control.iface_value.SetValue(value)
        except Exception:
            pass
        time.sleep(0.2)

    def is_playing(self) -> bool:
        title = win32gui.GetWindowText(self.hwnd).lower()
        return "paused" not in title and "stopped" not in title

    def ensure_stopped(self) -> bool:
        """ATAS no deja cambiar el rango mientras el replay corre, y el dialogo
        Select Date simplemente no abre."""
        if not self.is_playing():
            return True

        self.bring_to_front()
        button = self.buttons().get("PlayButton")
        if button is not None:
            self._press(button, "Pausa")

        deadline = time.time() + 30
        while time.time() < deadline:
            if not self.is_playing():
                time.sleep(0.8)
                return True
            time.sleep(1.0)

        print("   no pude detener el replay en curso")
        return False

    def _field(self, automation_id: str):
        """El contenedor DateEdit. Se vuelve a buscar en cada uso: el arbol UIA
        se invalida despues de cada escritura."""
        return next(
            e for e in self._window().descendants(control_type="Edit")
            if e.element_info.automation_id == automation_id
        )

    def _field_value(self, automation_id: str) -> str:
        """Leer el PART_Editor hijo. Leer el contenedor MIENTE: devuelve el texto
        del otro campo y hace creer que el rango quedo bien cuando no."""
        try:
            inner = self._field(automation_id).descendants(control_type="Edit")[0]
            try:
                return str(inner.get_value())
            except Exception:
                return inner.window_text()
        except Exception:
            return ""

    def _set_field(self, automation_id: str, value: str, expect: str) -> bool:
        """Escribir en el CONTENEDOR y verificar en el hijo. Escribir directo en
        el hijo no aplica el valor; pulsar ENTER cierra el panel."""
        for _ in range(3):
            try:
                control = self._field(automation_id)
            except StopIteration:
                return False

            control.click_input()
            time.sleep(0.2)
            control.type_keys("^a", set_foreground=False)
            time.sleep(0.08)
            pyperclip.copy(value)
            time.sleep(0.08)
            control.type_keys("^v", set_foreground=False)
            time.sleep(0.45)

            if expect in self._field_value(automation_id):
                return True
        return False

    def set_date(self, date_iso: str) -> bool:
        """Abre el dialogo Select Date, escribe el rango y confirma.

        El formato es el corto de Windows en espanol: DD/MM/YYYY hh:mm a. m.
        Los dos campos comparten un unico editor interno, asi que hay que
        verificar cada uno por separado y reintentar.
        """
        year, month, day = date_iso.split("-")
        stamp = f"{day}/{month}/{year}"
        want_start = f"{stamp} {REPLAY_FROM} a. m."
        want_end = f"{stamp} {REPLAY_TO} a. m."

        for attempt in range(1, 4):
            buttons = self.buttons()
            if "Select Date" not in buttons:
                print("   no encuentro el boton Select Date")
                return False
            self.bring_to_front()
            if not self._press(buttons["Select Date"], "Select Date"):
                return False
            time.sleep(1.5)

            edits = self.edits()
            if "StartEdit" not in edits or "EndEdit" not in edits:
                print(f"   el dialogo no mostro los campos (intento {attempt}/3)")
                time.sleep(0.8)
                continue

            start_ok = self._set_field("StartEdit", want_start, REPLAY_FROM)
            end_ok = self._set_field("EndEdit", want_end, REPLAY_TO)
            got_start, got_end = self._field_value("StartEdit"), self._field_value("EndEdit")
            ok = start_ok and end_ok

            if ok:
                select = self.buttons().get("Select")
                if select is None:
                    print("   no encuentro el boton Select")
                    return False
                if not self._press(select, "Select"):
                    return False
                time.sleep(1.5)
                print(f"   rango {got_start} -> {got_end}")
                return True

            print(f"   ATAS no acepto el rango (intento {attempt}/3): "
                  f"{got_start!r} / {got_end!r}")
            cancel = self.buttons().get("Cancel")
            if cancel is not None:
                self._press(cancel, "Cancel")
                time.sleep(0.8)

        return False

    def set_speed(self, label: str = REPLAY_SPEED) -> bool:
        current = self.speed_label()
        if current == label:
            return True

        self.bring_to_front()
        button = self.speed_button()
        if button is None:
            print("   no encuentro el boton de velocidad")
            return False
        point = button.rectangle().mid_point()
        mouse_click(coords=(point.x, point.y))
        time.sleep(1.2)
        mouse_click(coords=(point.x, SPEED_OPTIONS[label]))
        time.sleep(1.2)

        now = self.speed_label()
        if now != label:
            print(f"   no pude fijar la velocidad en {label} (quedo en {now})")
            return False
        return True

    SPEED_RE = re.compile(r"^\d+(\.\d+)?x$")

    def speed_button(self):
        """El boton de velocidad lleva como texto la velocidad actual. Buscarlo
        por indice falla: al abrirse el panel de fecha se agregan botones
        (Cancel, Select, los Clear) y el indice se recorre."""
        for b in self._window().descendants(control_type="Button"):
            if self.SPEED_RE.match(b.window_text().strip()):
                return b
        return None

    def speed_label(self) -> str:
        button = self.speed_button()
        return button.window_text().strip() if button is not None else ""

    def play(self) -> bool:
        button = self.buttons().get("PlayButton")
        if button is None:
            print("   no encuentro PlayButton")
            return False
        self.bring_to_front()
        if not self._press(button, "Play"):
            return False
        time.sleep(1.5)
        return True

    # Tres estados posibles en el titulo de la ventana:
    #   corriendo -> "Replay - History playback..."
    #   pausado   -> "Replay - The history playback is paused"
    #   detenido  -> "Replay - The playback is stopped"
    # "history playback" aparece en los dos primeros, asi que no sirve para
    # distinguirlos: se detecta por ausencia de "paused" y de "stopped".

    def wait_until_stopped(self, timeout=PLAY_TIMEOUT_SECONDS) -> bool:
        """El titulo de la ventana dice el estado: 'Replay - History playback...'
        mientras corre y 'Replay - The playback is stopped' al terminar.

        Hay que esperar PRIMERO a que entre en reproduccion. Si se vigila solo la
        palabra 'stopped', el titulo todavia sin cambiar al arrancar se confunde
        con el final y la captura sale a mitad del replay.
        """
        deadline = time.time() + timeout

        started = False
        start_deadline = time.time() + 90   # "Loading modules..." puede tardar
        while time.time() < start_deadline:
            if self.is_playing():
                started = True
                break
            time.sleep(0.5)

        if not started:
            print("   el replay nunca entro en reproduccion")
            return False

        while time.time() < deadline:
            if not self.is_playing():
                return True
            time.sleep(2.0)

        print("   timeout esperando el final del replay")
        return False


# ---------------------------------------------------------------------- main


def load_rows() -> list[dict]:
    with TRADES_CSV.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def main() -> int:
    rows = load_rows()
    sessions = sorted({r["session"] for r in rows})

    args = [a for a in sys.argv[1:]]
    if args and args[0] == "--from":
        sessions = [s for s in sessions if s >= args[1]]
    elif args:
        sessions = [s for s in sessions if s in args]

    if not sessions:
        print("No hay fechas que recorrer.")
        return 2

    ensure_atas_restored()
    chart = find_window(lambda t: "Chart" in t and "ATAS" not in t)
    if chart is None:
        raise SystemExit("No encontre la ventana del grafico.")

    replay = Replay()
    print(f"Replay hwnd {replay.hwnd} | grafico hwnd {chart}")
    print(f"Capturas -> {SHOTS}")
    print(f"{len(sessions)} fechas: {sessions[0]} -> {sessions[-1]}\n")

    done, failed = [], []
    for i, session in enumerate(sessions, start=1):
        trades = [r for r in rows if r["session"] == session]
        detail = ", ".join(
            f"#{t['n']} {'L' if t['dir'] == '1' else 'C'} {t['entry_clock'][:8]} "
            f"{t['result']} {float(t['net_ticks']):+.0f}t"
            for t in trades
        )
        print(f"[{i}/{len(sessions)}] {session}  ({len(trades)} op: {detail})")

        # El indicador resalta en su panel la operacion que marque el cursor.
        try:
            CURSOR_FILE.write_text(trades[0]["n"], encoding="utf-8")
        except Exception:
            pass

        if not replay.ensure_stopped():
            failed.append((session, "el replay anterior no se detuvo"))
            continue

        replay.set_speed()

        if not replay.set_date(session):
            failed.append((session, "no acepto la fecha"))
            continue

        if not replay.play():
            failed.append((session, "no pude pulsar Play"))
            continue

        finished = replay.wait_until_stopped()
        time.sleep(2.0)

        path = SHOTS / f"{session}.png"
        screenshot(chart, path)
        size = path.stat().st_size if path.exists() else 0
        print(f"   {'termino' if finished else 'TIMEOUT'} | captura {path.name} ({size:,} bytes)\n")
        done.append(session)

    print("=" * 60)
    print(f"capturas guardadas: {len(done)}")
    for session, reason in failed:
        print(f"  fallo {session}: {reason}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
