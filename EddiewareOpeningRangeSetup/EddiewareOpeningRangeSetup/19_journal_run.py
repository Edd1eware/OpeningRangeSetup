"""Journal visual de las operaciones reales: recorre las fechas en el Replay de
ATAS y guarda una captura del grafico por entrada historica.

Implementa la secuencia documentada en
mbp_mbo_research/notes_md_claude/2026-10-12_03_SECUENCIA_DEL_REPLAY_DE_ATAS.md

Lo critico, por orden de cuanto costo descubrirlo:

1. El panel de fechas es una VENTANA APARTE titulada "Select Date", fuera del
   rect del Replay. Hay que ponerla topmost ella y pulsar su boton "Select":
   sin eso el rango no se aplica y Play no hace nada.
2. Los campos StartEdit/EndEdit se escriben en el CONTENEDOR y se verifican en
   su hijo PART_Editor; leer el contenedor devuelve el valor del otro campo.
3. El estado se lee en el titulo: corriendo = ni "paused" ni "stopped".
4. invoke() por UIA no dispara estos botones WPF; hace falta clic real.
5. El rango debe empezar en 09:30, borde de sesion; 09:25 lo rechaza.

Usa 19_frame_chart.py para ajustar el encuadre a los niveles de cada entrada.
Exige trade_n/cursor_n/timestamp_utc del indicador y conserva un manifiesto con
los hashes de CSV, fila y PNG. Un archivo manual sin manifiesto no se da por validado.

Uso:
    python -u 19_journal_run.py                  # todas las fechas pendientes
    python -u 19_journal_run.py 2026-05-11       # una
    python -u 19_journal_run.py --from 2026-05-20
    python -u 19_journal_run.py --trade 7        # una entrada concreta
    python -u 19_journal_run.py --dry-run        # plan sin tocar ATAS
    python -u 19_journal_run.py --redo           # nuevas versiones, conserva las anteriores
    python -u 19_journal_run.py --by session     # solo primera entrada de cada fecha
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


def load_ui_dependencies():
    """No se carga ni conecta UI durante --help, --dry-run o las pruebas puras."""
    global windll, pyperclip, win32con, win32gui, win32ui, Image, Application, mouse
    from ctypes import windll
    import pyperclip
    import win32con
    import win32gui
    import win32ui
    from PIL import Image
    from pywinauto import Application, mouse

TRADES_CSV = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\lucid_real_trades.csv")
CURSOR_FILE = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\inside_control_current.txt")
SHOTS = Path(r"C:\Users\k_99_\Desktop\Imagenes_Diario_de_trading")

REPLAY_FROM, REPLAY_TO = "09:30", "09:50"
SPEED = "10x"
SPEED_MENU_Y = {"0.1x": 177, "0.3x": 200, "0.5x": 223, "1x": 246,
                "5x": 268, "10x": 291, "100x": 314, "1000x": 338}
PLAY_TIMEOUT = 420
# El replay se considera listo cuando los datos pasan de esta hora: la entrada
# mas tardia es 09:38 y la operacion mas larga dura ~2.5 min.
REPLAY_READY_AT = "09:45"
# Si reproduce pero los datos no avanzan en este tiempo, el replay esta atascado
# y solo se destraba reiniciando ATAS.
STALL_SECONDS = 60.0
# Tras el replay la vista queda en el premercado; estos giros de rueda sobre el
# eje de tiempo la adelantan hasta la sesion cash. El premercado no tiene nada
# que ver con el setup.
TIME_SCROLL_STEPS = 8


def date_field_matches(value: str, session: str, clock: str) -> bool:
    """La hora sola no demuestra que ATAS haya cambiado tambien la fecha."""
    want = datetime.strptime(f"{session} {clock}", "%Y-%m-%d %H:%M")
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})", value)
    if match is None:
        return False
    day, month, year, hour, minute = map(int, match.groups())
    if re.search(r"p\.?\s*m\.?", value, re.I) and hour < 12:
        hour += 12
    if re.search(r"a\.?\s*m\.?", value, re.I) and hour == 12:
        hour = 0
    return (year, month, day, hour, minute) == (want.year, want.month, want.day, want.hour, want.minute)


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row_fingerprint(trade: dict) -> str:
    return hashlib.sha256(json.dumps(trade, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def capture_key(trade: dict) -> str:
    return f"{trade['session']}/trade-{int(trade['n']):03d}"


def append_event(path: Path, event: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"recorded_utc": datetime.now(timezone.utc).isoformat(), **event}
    prefix = ""
    if path.exists() and path.stat().st_size:
        with path.open("rb") as existing:
            existing.seek(-1, os.SEEK_END)
            if existing.read(1) != b"\n":
                prefix = "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(prefix + json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_manifest(path: Path) -> list[dict]:
    """Una ultima linea interrumpida no invalida las capturas previas."""
    if not path.exists():
        return []
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
        except json.JSONDecodeError:
            print(f"Aviso: registro incompleto/ilegible {path.name}:{number}; no se usa para reanudar.")
    return events


def verified_capture(trade: dict, events: list[dict], feed_sha256: str) -> dict | None:
    """No basta un PNG de la misma fecha: identidad, fuente y contenido deben coincidir."""
    for event in reversed(events):
        if (event.get("status") != "captured" or event.get("key") != capture_key(trade)
                or event.get("feed_sha256") != feed_sha256
                or event.get("row_sha256") != row_fingerprint(trade)):
            continue
        path = Path(event.get("path", ""))
        try:
            if path.is_file() and sha256_file(path) == event.get("image_sha256"):
                return event
        except OSError:
            pass
    return None


def capture_path(shots: Path, trade: dict, by: str = "trade") -> Path:
    """--redo conserva todas las versiones; tampoco reemplaza capturas manuales."""
    if by == "session":
        stem = trade["session"]
    else:
        stem = f"{trade['session']}_trade{int(trade['n']):03d}_{trade['entry_clock'][:8].replace(':', '')}"
    candidate = shots / f"{stem}.png"
    version = 2
    while candidate.exists():
        candidate = shots / f"{stem}_v{version:03d}.png"
        version += 1
    return candidate


def write_cursor(trade: dict) -> int:
    """Cambio atomico: el indicador nunca lee un indice vacio a medio escribir."""
    CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CURSOR_FILE.with_name(CURSOR_FILE.name + f".{os.getpid()}.tmp")
    temporary.write_text(str(int(trade["n"])), encoding="utf-8")
    os.replace(temporary, CURSOR_FILE)
    return time.time_ns()


def state_validation(session: str, trade: dict, state: dict, *, now: datetime | None = None,
                     feed_sha256: str | None = None) -> tuple[bool, str]:
    if state.get("session") != session:
        return False, f"el grafico muestra {state.get('session') or 'otra sesion'}"
    if str(state.get("trade_n", "")) != str(int(trade["n"])):
        return False, f"trade_n {state.get('trade_n', 'ausente')} != {trade['n']}"
    if str(state.get("cursor_n", "")) != str(int(trade["n"])):
        return False, "el indicador no confirma el cursor solicitado"
    if feed_sha256 is not None and str(state.get("csv_sha256", "")).lower() != feed_sha256.lower():
        return False, "la version del CSV cargada en ATAS no coincide con la fuente"
    try:
        published = datetime.fromisoformat(state["timestamp_utc"].replace("Z", "+00:00"))
        if published.tzinfo is None:
            return False, "timestamp_utc no indica zona horaria"
        age = ((now or datetime.now(timezone.utc)) - published).total_seconds()
        if not -2 <= age <= 12:
            return False, f"estado sin actualizar ({age:.1f} s)"
        top, bottom = Decimal(state["top"]), Decimal(state["bottom"])
        low, high = min(top, bottom), max(top, bottom)
        if not low.is_finite() or not high.is_finite() or high <= low:
            return False, "rango vertical invalido"
        reconstructed = state.get("bracket_source", "").startswith("reconstructed")
        for key in ("entry", "exit", "stop", "target", "or_low", "or_high"):
            wanted = Decimal(trade.get(key, "0") or "0")
            actual = Decimal(state.get(key, "0") or "0")
            if not wanted.is_finite() or not actual.is_finite():
                return False, f"{key} no es finito"
            tolerance = Decimal("1.25") if key.startswith("or_") else Decimal("0.011")
            may_reconstruct = (key in ("stop", "target") and reconstructed) or (key.startswith("or_") and wanted == 0)
            if not may_reconstruct and abs(wanted - actual) > tolerance:
                return False, f"{key} no coincide con la fuente"
            if actual > 0 and not low <= actual <= high:
                return False, f"{key} fuera de pantalla"
        if Decimal(trade["entry"]) <= 0:
            return False, "falta el precio de entrada"
        if reconstructed:
            entry, stop, target = (Decimal(state.get(k, "0") or "0") for k in ("entry", "stop", "target"))
            if (stop > 0) != (target > 0):
                return False, "bracket reconstruido incompleto"
            if stop > 0:
                direction = int(trade.get("dir", "1" if stop < entry else "-1"))
                if direction * (entry - stop) <= 0 or direction * (target - entry) <= 0:
                    return False, "bracket reconstruido en direccion incorrecta"
                if abs(abs(entry - stop) - abs(target - entry)) > Decimal("0.021"):
                    return False, "bracket reconstruido no es 1:1"
        first = datetime.strptime(state["first_time"], "%Y-%m-%d %H:%M")
        last = datetime.strptime(state["last_time"], "%Y-%m-%d %H:%M")
        opened = datetime.strptime(f"{session} {trade['entry_clock'][:8]}", "%Y-%m-%d %H:%M:%S").replace(second=0)
        closed = datetime.strptime(f"{session} {trade['exit_clock'][:8]}", "%Y-%m-%d %H:%M:%S").replace(second=0)
        if not first <= opened <= closed <= last:
            return False, "entrada o salida no esta en las velas visibles"
        for flag in ("entry_bar_visible", "exit_bar_visible"):
            if flag in state and str(state[flag]).lower() not in ("true", "1"):
                return False, f"{flag}: vela fuera de pantalla"
    except (KeyError, ValueError, ArithmeticError) as exc:
        return False, f"estado incompleto/invalido: {exc}"
    return True, "identidad, fuente, frescura y niveles comprobados"


def wait_for_trade(trade: dict, cursor_written_ns: int, timeout: float = 12,
                   feed_sha256: str | None = None) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_view()
        try:
            fresh_file = VIEW_STATE.stat().st_mtime_ns >= cursor_written_ns
        except OSError:
            fresh_file = False
        if (fresh_file and state.get("session") == trade["session"]
                and state.get("trade_n") == str(int(trade["n"]))
                and state.get("cursor_n") == str(int(trade["n"]))
                and (feed_sha256 is None or str(state.get("csv_sha256", "")).lower() == feed_sha256.lower())):
            return state
        time.sleep(0.35)
    raise RuntimeError(f"el indicador no publico la operacion #{trade['n']} despues de cambiar cursor")


def replay_end(trades: list[dict]) -> str:
    latest = max(datetime.strptime(t["exit_clock"][:8], "%H:%M:%S") for t in trades)
    end = max(latest + timedelta(minutes=2), datetime.strptime(REPLAY_TO, "%H:%M"))
    if end.hour >= 12:
        raise ValueError("este runner usa rango de manana; la salida requiere un rango diferente")
    return end.strftime("%H:%M")


def desired_price_range(state: dict) -> float:
    """El encuadre incluye la salida real aunque no exista un SL/TP documentado."""
    levels = [float(state.get(k, "0") or "0") for k in ("or_low", "or_high", "entry", "exit", "stop", "target")]
    levels = [v for v in levels if math.isfinite(v) and v > 0]
    needed = (max(levels) - min(levels)) * 1.18 if levels else 0
    opening = max(0, float(state.get("or_high", "0")) - float(state.get("or_low", "0")))
    return max(needed, opening * 2.73)


def find_window(pred):
    found = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and pred(win32gui.GetWindowText(hwnd)):
            found.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


def topmost(hwnd):
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    time.sleep(0.4)


def untopmost(hwnd):
    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)


class Ui:
    def __init__(self):
        self.app = Application(backend="uia")

    def window(self, hwnd):
        win = self.app.connect(handle=hwnd).window(handle=hwnd)
        win.wrapper_object()
        return win

    def buttons(self, hwnd) -> dict:
        return {
            (b.element_info.automation_id or b.window_text().strip()): b
            for b in self.window(hwnd).descendants(control_type="Button")
        }

    def click(self, control) -> bool:
        """Clic real: invoke() por UIA no dispara estos botones."""
        try:
            point = control.rectangle().mid_point()
            mouse.click(coords=(point.x, point.y))
            time.sleep(1.1)
            return True
        except Exception as exc:
            print(f"   no pude pulsar: {exc}")
            return False

    def press(self, hwnd, key) -> bool:
        control = self.buttons(hwnd).get(key)
        if control is None:
            print(f"   no encuentro el boton {key}")
            return False
        return self.click(control)


class Replay:
    def __init__(self, ui: Ui):
        self.ui = ui
        self.hwnd = find_window(lambda t: t.lower().startswith("replay"))
        if self.hwnd is None:
            raise SystemExit("No hay ventana Replay visible.")

    def title(self) -> str:
        return win32gui.GetWindowText(self.hwnd).lower()

    def is_playing(self) -> bool:
        t = self.title()
        return "history playback" in t and "paused" not in t and "stopped" not in t

    def ensure_stopped(self) -> bool:
        if not self.is_playing():
            return True
        topmost(self.hwnd)
        self.ui.press(self.hwnd, "PlayButton")
        deadline = time.time() + 30
        while time.time() < deadline:
            if not self.is_playing():
                time.sleep(0.8)
                return True
            time.sleep(1.0)
        return False

    # ------------------------------------------- modulo y modo del replay

    def texts(self) -> list[str]:
        return [t.window_text() for t in self.ui.window(self.hwnd).descendants(control_type="Text")]

    def select_module(self) -> bool:
        """Volver a elegir el modulo del grafico.

        Hace falta en CADA cambio de fecha: si no, el replay corre pero el
        grafico se queda con los datos del dia anterior. El clic sobre el lienzo
        no sirve; hay que usar el chevron, cuyo desplegable es un popup que no
        aparece en el arbol UIA, asi que se pulsa por posicion relativa.
        """
        topmost(self.hwnd)

        # Si ya hay modulo, NO tocarlo: abrir el desplegable sobre un modulo ya
        # elegido lo DESELECCIONA y deja el replay inservible. Solo hay que
        # actuar cuando la linea de estado pide modulo; "Select module" aparece
        # siempre como etiqueta del boton, asi que no sirve para decidir.
        status = " ".join(self.texts()).lower()
        needs_module = ("click the module" in status
                        or 'press "select module"' in status
                        or "press “select module”" in status)
        if not needs_module:
            return True

        buttons = self.ui.buttons(self.hwnd)

        # Dos estados distintos y faciles de confundir:
        #   "Click the module you want to replay"  -> espera un clic en el lienzo,
        #        que con clics sinteticos NO funciona. Hay que salir pulsando
        #        "Select module" otra vez.
        #   "Press \"Select module\" to select..." -> aqui el chevron SI abre la lista.
        if "click the module" in " ".join(self.texts()).lower():
            toggle = buttons.get("Select module")
            if toggle is not None:
                self.ui.click(toggle)
                time.sleep(0.8)

        chevron = buttons.get("ModuleMenuButton")
        if chevron is None:
            return False

        rect = chevron.rectangle()
        mouse.click(coords=(rect.mid_point().x, rect.mid_point().y))
        time.sleep(1.5)
        # El desplegable es un popup fuera del arbol UIA: posicion relativa al chevron.
        mouse.click(coords=(rect.left + 50, rect.bottom + 16))
        time.sleep(2.0)

        joined = " ".join(self.texts()).lower()
        if "click the module" in joined or 'press "select module"' in joined:
            print("   no quedo seleccionado el modulo")
            return False
        return True

    def ensure_mode_date(self) -> bool:
        """Elegir el modulo deja el modo en 'Select Bar', que no tiene fechas."""
        if any(t.strip() == "Select Date" for t in self.texts()):
            return True

        topmost(self.hwnd)
        chevron = self.ui.buttons(self.hwnd).get("ModeMenuButton")
        if chevron is None:
            return False

        rect = chevron.rectangle()
        mouse.click(coords=(rect.mid_point().x, rect.mid_point().y))
        time.sleep(1.3)
        # Menu: Select Bar / Select Period / Select Date / Templates
        mouse.click(coords=(rect.left + 64, rect.bottom + 59))
        time.sleep(1.8)

        if not any(t.strip() == "Select Date" for t in self.texts()):
            print("   no pude poner el modo en Select Date")
            return False
        return True

    def speed_button(self):
        for b in self.ui.window(self.hwnd).descendants(control_type="Button"):
            if re.match(r"^\d+(\.\d+)?x$", b.window_text().strip()):
                return b
        return None

    def set_speed(self) -> bool:
        button = self.speed_button()
        if button is None:
            return False
        if button.window_text().strip() == SPEED:
            return True

        topmost(self.hwnd)
        point = button.rectangle().mid_point()
        mouse.click(coords=(point.x, point.y))
        time.sleep(1.1)
        mouse.click(coords=(point.x, SPEED_MENU_Y[SPEED]))
        time.sleep(1.1)

        button = self.speed_button()
        now = button.window_text().strip() if button else "?"
        if now != SPEED:
            print(f"   la velocidad quedo en {now}")
            return False
        return True

    # -------------------------------------------------- rango de fechas

    def _dialog(self):
        return find_window(lambda t: t == "Select Date")

    def _field(self, dlg, automation_id):
        return next(
            e for e in self.ui.window(dlg).descendants(control_type="Edit")
            if e.element_info.automation_id == automation_id
        )

    def _value(self, dlg, automation_id) -> str:
        """Leer el hijo PART_Editor; el contenedor devuelve el valor del otro campo."""
        try:
            inner = self._field(dlg, automation_id).descendants(control_type="Edit")[0]
            try:
                return str(inner.get_value())
            except Exception:
                return inner.window_text()
        except Exception:
            return ""

    def _set_field(self, dlg, automation_id, value, expect) -> bool:
        for _ in range(3):
            try:
                control = self._field(dlg, automation_id)
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
            if date_field_matches(self._value(dlg, automation_id), *expect):
                return True
        return False

    def set_range(self, session: str, replay_to: str = REPLAY_TO) -> bool:
        year, month, day = session.split("-")
        stamp = f"{day}/{month}/{year}"

        topmost(self.hwnd)
        dlg = self._dialog()
        if dlg is None:
            self.ui.press(self.hwnd, "Select Date")
            time.sleep(1.5)
            dlg = self._dialog()
        if dlg is None:
            print("   no se abrio la ventana Select Date")
            return False

        topmost(dlg)
        time.sleep(0.6)

        # Los dos campos comparten editor interno. Hace falta sacar el foco del
        # primero antes de escribir el segundo, o el valor del segundo no entra.
        def commit():
            left, top, right, _ = win32gui.GetWindowRect(dlg)
            mouse.click(coords=((left + right) // 2, top + 14))
            time.sleep(0.5)

        commit()
        ok_start = self._set_field(dlg, "StartEdit", f"{stamp} {REPLAY_FROM} a. m.", (session, REPLAY_FROM))
        commit()
        ok_end = self._set_field(dlg, "EndEdit", f"{stamp} {replay_to} a. m.", (session, replay_to))
        commit()

        # Reverificar: el commit puede revertir un campo mal escrito.
        if ok_start and not date_field_matches(self._value(dlg, "StartEdit"), session, REPLAY_FROM):
            ok_start = self._set_field(dlg, "StartEdit", f"{stamp} {REPLAY_FROM} a. m.", (session, REPLAY_FROM))
            commit()

        ok_start = ok_start and date_field_matches(self._value(dlg, "StartEdit"), session, REPLAY_FROM)
        ok_end = ok_end and date_field_matches(self._value(dlg, "EndEdit"), session, replay_to)
        if not (ok_start and ok_end):
            print(f"   ATAS no acepto el rango: "
                  f"{self._value(dlg,'StartEdit')!r} / {self._value(dlg,'EndEdit')!r}")
            return False

        print(f"   rango {self._value(dlg,'StartEdit')} -> {self._value(dlg,'EndEdit')}")

        # EL paso que lo hace todo: confirmar dentro de la ventana Select Date.
        if not self.ui.press(dlg, "Select"):
            return False
        time.sleep(1.5)

        if self._dialog() is not None:
            print("   la ventana Select Date sigue abierta: el rango NO se aplico")
            return False
        return True

    # --------------------------------------------------------- reproducir

    def pause(self):
        if self.is_playing():
            topmost(self.hwnd)
            self.ui.press(self.hwnd, "PlayButton")
            time.sleep(1.0)

    def play_and_wait(self, session: str = "") -> bool:
        """Reproducir hasta que el dia este completo y la operacion sea visible.

        El replay **no se detiene al llegar al final del rango: se reinicia en
        bucle**. Medido: llega a 09:49 y a los pocos segundos vuelve a 09:30.
        Por eso esperar el estado "stopped" no sirve y hay que vigilar los datos
        que publica el indicador, pausando en cuanto estan completos.
        """
        topmost(self.hwnd)
        if not self.ui.press(self.hwnd, "PlayButton"):
            return False

        deadline = time.monotonic() + PLAY_TIMEOUT
        best = ""
        last_progress = time.monotonic()

        while time.monotonic() < deadline:
            state = read_view()
            available = state.get("last_available_time", "")
            if available and (not session or state.get("session") == session):
                clock = available.split(" ")[-1]
                if best and clock < best:
                    break                      # dio la vuelta
                if clock > best:
                    best = clock
                    last_progress = time.monotonic()
                if (clock >= REPLAY_READY_AT
                        and state.get("entry_bar_visible") == "True"
                        and state.get("exit_bar_visible") == "True"):
                    self.pause()
                    print(f"   datos hasta {available}, entrada y salida visibles")
                    return True

            # Atasco conocido: el replay dice reproducir pero los datos no se
            # mueven. No se arregla desde la ventana; hay que reiniciar ATAS.
            if self.is_playing() and time.monotonic() - last_progress > STALL_SECONDS:
                self.pause()
                print(f"   REPLAY ATASCADO en {best or 'el inicio'}: reproduce pero no "
                      f"avanza en {STALL_SECONDS:.0f}s. Hay que reiniciar ATAS.")
                return False

            time.sleep(2.0)

        self.pause()
        print(f"   no llego a {REPLAY_READY_AT} con la operacion visible "
              f"(maximo {best or 'nada'})")
        return False


VIEW_STATE = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\inside_control_view.txt")

# La vista debe empezar en la apertura: el premercado no tiene nada que ver con
# el setup, y la entrada mas tardia de todas es a las 09:38.
WANT_FIRST_MINUTE = (9 * 60 + 29, 9 * 60 + 31)


def read_view() -> dict:
    for _ in range(6):
        try:
            state = {}
            for line in VIEW_STATE.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    state[key.strip()] = value.strip()
            if "first_time" in state:
                return state
        except Exception:
            pass
        time.sleep(0.25)
    return {}


def time_goal(state: dict, session: str, trade: dict | None = None) -> dict:
    """Objetivo temporal por fecha completa, incluyendo OR y toda la operacion."""
    opening = datetime.strptime(f"{session} 09:30", "%Y-%m-%d %H:%M")
    required_end = opening + timedelta(minutes=1)
    if trade:
        for key in ("entry_clock", "exit_clock"):
            stamp = datetime.strptime(f"{session} {trade[key][:8]}", "%Y-%m-%d %H:%M:%S").replace(second=0)
            required_end = max(required_end, stamp + timedelta(minutes=1))
    first = datetime.strptime(state["first_time"], "%Y-%m-%d %H:%M")
    last = datetime.strptime(state["last_time"], "%Y-%m-%d %H:%M")
    if last < first:
        raise ValueError("intervalo visible invertido")
    if last - first < required_end - opening:
        raise ValueError("ventana temporal demasiado estrecha para OR, entrada y salida; ampliar manualmente la escala temporal")
    done = opening - timedelta(minutes=3) <= first <= opening and last >= required_end
    target_first = opening - timedelta(minutes=1)
    return {"done": done, "minutes_to_move": (target_first - first).total_seconds() / 60,
            "first": first, "last": last, "required_end": required_end}


def frame_time(session: str, max_steps: int = 24, *, trade: dict | None = None,
               layout: dict | None = None, chart: int | None = None, geometry_module=None) -> bool:
    """Corrige tiempo por realimentacion; mide cuanto desplaza la rueda en esta vista."""
    if geometry_module is None or layout is None or chart is None:
        print("   falta geometria calibrada del eje temporal; no se desplaza a ciegas")
        return False
    minutes_per_notch = None
    for _ in range(max_steps):
        state = read_view()
        if state.get("session") and state["session"] != session:
            print(f"   el grafico muestra {state['session']}, no {session}")
            return False
        try:
            goal = time_goal(state, session, trade)
            client = win32gui.GetClientRect(chart)
            geometry = geometry_module.screen_geometry(state, win32gui.ClientToScreen(chart, (0, 0)),
                                                        (client[2], client[3]), layout)
        except (KeyError, ValueError) as exc:
            print(f"   no se encuadra el tiempo: {exc}")
            return False
        if goal["done"]:
            print(f"   vista {state['first_time']} -> {state.get('last_time')} "
                  f"({state.get('bars')} velas, {state.get('range')} pts)")
            return True
        advance = goal["minutes_to_move"] > 0
        direction = layout["wheel_forward_direction"] * (1 if advance else -1)
        steps = 1 if minutes_per_notch is None else max(1, min(6, round(abs(goal["minutes_to_move"]) / minutes_per_notch)))
        mouse.scroll(coords=geometry["time_axis"], wheel_dist=direction * steps)
        time.sleep(0.8)
        try:
            after = time_goal(read_view(), session, trade)
        except (ValueError, KeyError) as exc:
            print(f"   no se pudo medir el desplazamiento temporal: {exc}")
            return False
        shifted = (after["first"] - goal["first"]).total_seconds() / 60
        if shifted == 0 or shifted * (1 if advance else -1) <= 0:
            print("   la rueda no desplazo tiempo en la direccion calibrada; revisar eje/layout")
            return False
        minutes_per_notch = abs(shifted) / steps
    print("   no convergio el encuadre temporal; no se guarda captura")
    return False


def validate(session: str, image: Image.Image, trade: dict | None = None,
             state: dict | None = None, *, feed_sha256: str | None = None) -> tuple[bool, str]:
    """Comprueba identidad/niveles visibles y una heuristica de texto footprint.

    La densidad no prueba por si sola los numeros del footprint: la inspeccion
    visual sigue siendo necesaria. Un bracket desconocido puede quedar en cero.
    """
    state = state or read_view()
    if not state:
        return False, "el indicador no publica estado"

    if trade is not None:
        ok, reason = state_validation(session, trade, state, feed_sha256=feed_sha256)
        if not ok:
            return ok, reason
    elif state.get("session") != session:
        return False, f"el grafico muestra {state.get('session') or 'otra sesion'}"

    try:
        top, bottom = float(state["top"]), float(state["bottom"])
        entry, stop, target = (float(state[k]) for k in ("entry", "stop", "target"))
    except (KeyError, ValueError):
        return False, "faltan niveles en el estado"

    if entry <= 0 or not all(math.isfinite(v) for v in (top, bottom, entry, stop, target)):
        return False, "la operacion no tiene entrada valida"

    low, high = min(bottom, top), max(bottom, top)
    fuera = [name for name, value in (("entrada", entry), ("SL", stop), ("TP", target))
             if value > 0 and not low <= value <= high]
    if fuera:
        return False, "fuera de pantalla: " + ", ".join(fuera)

    # El precio puede estar en pantalla y aun asi faltar la vela: el replay se
    # reinicia en bucle y, si la captura cae tras la vuelta, la operacion todavia
    # no ha ocurrido.
    sin_vela = [name for name, key in (("entrada", "entry_bar_visible"),
                                       ("salida", "exit_bar_visible"))
                if state.get(key) != "True"]
    if sin_vela:
        return False, "vela no visible: " + ", ".join(sin_vela)

    # El footprint son muchos numeros claros sobre fondo oscuro. Sin el, el area
    # del grafico tiene muy pocos pixeles de texto.
    width, height = image.size
    if width < 640 or height < 400:
        return False, "captura demasiado pequena o ventana minimizada"
    pane = image.crop((40, 40, int(width * 0.82), int(height * 0.60))).convert("L")
    light = sum(1 for value in pane.getdata() if value > 150)
    density = light / float(pane.size[0] * pane.size[1])
    if density < 0.012:
        return False, f"sin footprint legible (densidad {density:.4f})"

    return True, f"ok (densidad {density:.4f})"


def grab(chart_hwnd: int) -> Image.Image:
    left, top, right, bottom = win32gui.GetWindowRect(chart_hwnd)
    width, height = right - left, bottom - top

    window_dc = win32gui.GetWindowDC(chart_hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(window_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)
    try:
        if not windll.user32.PrintWindow(chart_hwnd, save_dc.GetSafeHdc(), 2):
            raise RuntimeError("PrintWindow no genero una captura valida")
        info = bitmap.GetInfo()
        image = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                                 bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
        return image.copy()
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(chart_hwnd, window_dc)


def arguments(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Recorrido historico Lucid; solo Replay y capturas, sin ordenes.")
    parser.add_argument("dates", nargs="*", help="Fechas YYYY-MM-DD (por defecto todas las pendientes)")
    parser.add_argument("--from", dest="from_session", help="Reanudar desde una fecha inclusive")
    parser.add_argument("--trade", type=int, action="append", help="Indice n del CSV; puede repetirse")
    parser.add_argument("--by", choices=("trade", "session"), default="trade",
                        help="trade captura todas las entradas; session solo la primera de cada fecha")
    parser.add_argument("--redo", action="store_true", help="Nueva version; conserva capturas anteriores")
    parser.add_argument("--dry-run", action="store_true", help="Lista plan y cobertura sin cargar ni controlar ATAS")
    parser.add_argument("--trades", type=Path, default=TRADES_CSV)
    parser.add_argument("--shots", type=Path, default=SHOTS)
    parser.add_argument("--cursor", type=Path, default=CURSOR_FILE)
    parser.add_argument("--view", type=Path, default=VIEW_STATE)
    parser.add_argument("--manifest", type=Path, help="Por defecto <shots>/journal_manifest.jsonl")
    parser.add_argument("--layout", type=Path, default=VIEW_STATE.with_name("journal_layout_calibration.json"),
                        help="Geometria y gestos comprobados visualmente en ATAS")
    parser.add_argument("--speed", choices=tuple(SPEED_MENU_Y), default=SPEED,
                        help="Velocidad de Replay; se comprueba el texto del boton despues de elegirla")
    args = parser.parse_args(argv)
    for date in [*args.dates, *([args.from_session] if args.from_session else [])]:
        try:
            if datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d") != date:
                raise ValueError()
        except ValueError:
            parser.error(f"fecha invalida: {date!r}; usa YYYY-MM-DD")
    return args


def plan_rows(rows: list[dict], args, events: list[dict], feed_sha256: str) -> tuple[list[dict], int]:
    selected = []
    seen_numbers = set()
    for trade in rows:
        number = int(trade["n"])
        if number in seen_numbers:
            raise ValueError(f"indice n duplicado en CSV: {number}")
        seen_numbers.add(number)
        datetime.strptime(trade["session"], "%Y-%m-%d")
        for clock in ("entry_clock", "exit_clock"):
            datetime.strptime(trade[clock][:8], "%H:%M:%S")
        if args.dates and trade["session"] not in args.dates:
            continue
        if args.from_session and trade["session"] < args.from_session:
            continue
        if args.trade and number not in args.trade:
            continue
        selected.append(trade)
    if args.trade and set(args.trade) - seen_numbers:
        raise ValueError(f"indices no presentes: {sorted(set(args.trade) - seen_numbers)}")
    if args.dates and set(args.dates) - {r["session"] for r in rows}:
        raise ValueError(f"fechas sin operaciones: {sorted(set(args.dates) - {r['session'] for r in rows})}")
    selected.sort(key=lambda t: (t["session"], t["entry_clock"], int(t["n"])))
    if args.by == "session":
        first_per_day = {}
        for trade in selected:
            first_per_day.setdefault(trade["session"], trade)
        selected = list(first_per_day.values())
    pending = [t for t in selected if args.redo or not verified_capture(t, events, feed_sha256)]
    return pending, len(selected) - len(pending)


def main(argv: list[str] | None = None) -> int:
    global CURSOR_FILE, VIEW_STATE, SPEED
    args = arguments(argv)
    CURSOR_FILE, VIEW_STATE, SPEED = args.cursor, args.view, args.speed
    raw_source = args.trades.read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw_source.decode("utf-8-sig")), delimiter=";"))
    feed_sha256 = hashlib.sha256(raw_source).hexdigest()
    manifest = args.manifest or args.shots / "journal_manifest.jsonl"
    events = read_manifest(manifest)
    pending, skipped = plan_rows(rows, args, events, feed_sha256)
    sessions = sorted({t["session"] for t in pending})
    print(f"Fuente {args.trades} | SHA256 {feed_sha256}")
    print(f"{len(rows)} entradas fuente | {len(pending)} pendientes | {skipped} capturas verificadas | {len(sessions)} fechas")
    for trade in pending:
        print(f"  #{int(trade['n']):03d} {trade['session']} {trade['entry_clock']} -> "
              f"{capture_path(args.shots, trade, args.by).name}")
    if args.dry_run or not pending:
        return 0

    load_ui_dependencies()
    # Reusar la convergencia de precio ya existente; no se ejecuta durante dry-run.
    import importlib.util
    spec = importlib.util.spec_from_file_location("journal_price_frame", Path(__file__).with_name("19_frame_chart.py"))
    framing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(framing)
    framing.VIEW_STATE = VIEW_STATE
    framing.target_range = desired_price_range
    try:
        layout = framing.load_calibration(args.layout)
    except ValueError as exc:
        print(f"No se inicia el recorrido: {exc}")
        return 2
    ui = Ui()
    atas = find_window(lambda t: t.startswith("ATAS - "))
    if atas and win32gui.GetWindowRect(atas)[0] < -1000:
        win32gui.ShowWindow(atas, win32con.SW_RESTORE)
        time.sleep(1.5)
    chart = find_window(lambda t: "Chart" in t and "ATAS" not in t)
    if chart is None:
        raise SystemExit("No encontre la ventana del grafico.")
    replay = Replay(ui)
    print(f"Replay {replay.hwnd} | grafico {chart} | {len(sessions)} fechas\n")

    done, failed = [], []
    for session in sessions:
        trades = [t for t in pending if t["session"] == session]
        session_rows = [t for t in rows if t["session"] == session]
        print(f"{session}: {len(trades)} entradas pendientes")
        try:
            if sha256_file(args.trades) != feed_sha256:
                raise RuntimeError("el CSV cambio durante el recorrido; reanuda con la fuente estable")
            write_cursor(trades[0])
            for check, reason in ((replay.ensure_stopped, "no pude detener el replay anterior"),
                                  (replay.select_module, "no se selecciono el modulo"),
                                  (replay.ensure_mode_date, "no se puso Select Date"),
                                  (replay.set_speed, "no se confirmo la velocidad")):
                if not check():
                    raise RuntimeError(reason)
            if not replay.set_range(session, replay_end(session_rows)):
                raise RuntimeError("no se aplico el rango con fecha y hora verificadas")
            if not replay.play_and_wait(session):
                raise RuntimeError("el replay no arranco o no termino")
            time.sleep(4)
            untopmost(replay.hwnd)
            win32gui.SetWindowPos(chart, win32con.HWND_TOP, 0, 0, 0, 0,
                                 win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
            time.sleep(1)
        except Exception as exc:
            for trade in trades:
                reason = str(exc)
                append_event(manifest, {"status": "failed", "key": capture_key(trade), "reason": reason,
                                      "feed_sha256": feed_sha256, "row_sha256": row_fingerprint(trade)})
                failed.append((capture_key(trade), reason))
            continue

        for trade in trades:
            key = capture_key(trade)
            base = {"key": key, "feed_sha256": feed_sha256, "row_sha256": row_fingerprint(trade),
                    "source": str(args.trades.resolve()), "trade": trade}
            append_event(manifest, {**base, "status": "started"})
            try:
                if sha256_file(args.trades) != feed_sha256:
                    raise RuntimeError("el CSV cambio durante el recorrido")
                cursor_at = write_cursor(trade)
                wait_for_trade(trade, cursor_at, feed_sha256=feed_sha256)
                if not frame_time(session, trade=trade, layout=layout, chart=chart, geometry_module=framing):
                    raise RuntimeError("no se logro encuadrar la apertura")
                try:
                    framed = framing.frame(layout=layout)
                except SystemExit as exc:
                    raise RuntimeError(f"no se pudo leer el estado para encuadrar: {exc}") from exc
                if not framed:
                    raise RuntimeError("no convergio el encuadre de precio")
                before = read_view()
                ok, reason = state_validation(session, trade, before, feed_sha256=feed_sha256)
                if not ok:
                    raise RuntimeError(reason)
                image = grab(chart)
                after = read_view()
                ok, reason = validate(session, image, trade, after, feed_sha256=feed_sha256)
                if not ok:
                    raise RuntimeError(reason)
                keys = ("session", "trade_n", "cursor_n", "top", "bottom", "first_time", "last_time",
                        "entry", "exit", "stop", "target", "or_low", "or_high", "bracket_source", "csv_sha256", "csv_path")
                if any(before.get(k) != after.get(k) for k in keys):
                    raise RuntimeError("la vista cambio durante la captura; reintentar")
                path = capture_path(args.shots, trade, args.by)
                path.parent.mkdir(parents=True, exist_ok=True)
                # xb impide una sobrescritura aun si aparece el archivo despues del plan.
                with path.open("xb") as stream:
                    image.save(stream, format="PNG")
                    stream.flush()
                    os.fsync(stream.fileno())
                append_event(manifest, {**base, "status": "captured", "path": str(path.resolve()),
                                      "image_sha256": sha256_file(path), "image_bytes": path.stat().st_size,
                                      "view": after, "validation": reason, "mode": args.by})
                print(f"  #{trade['n']} guardada {path.name} ({path.stat().st_size:,} bytes), {reason}")
                done.append(key)
            except Exception as exc:
                reason = str(exc)
                append_event(manifest, {**base, "status": "failed", "reason": reason})
                print(f"  #{trade['n']} NO guardada: {reason}")
                failed.append((key, reason))
    print(f"Capturas nuevas verificadas: {len(done)} | fallos: {len(failed)} | manifiesto: {manifest}")
    for key, reason in failed:
        print(f"  fallo {key}: {reason}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
