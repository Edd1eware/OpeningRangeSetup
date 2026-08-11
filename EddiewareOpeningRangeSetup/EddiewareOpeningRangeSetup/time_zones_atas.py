"""
Cambia el timezone de CME en ATAS mediante pywinauto.

ATAS no aplica el nuevo Time Zone si el boton verde de encendido de Replay
permanece activo. La secuencia es:
  1. detener la reproduccion y pulsar el boton verde para apagar Replay;
  2. abrir Settings > Time Zones desde la ventana principal;
  3. desactivar "Detect time automatically";
  4. buscar CME y asignarle UTC-4 (EDT) o UTC-5 (EST);
  5. aplicar el cambio y volver a encender/restaurar Replay.

Llamado automaticamente por 04_run_replay_all_databento_after_sync.py
cuando detecta una transicion EDT (UTC-4) <-> EST (UTC-5).

Funciones publicas:
    get_utc_offset(session_date) -> int   # -4 o -5
    ensure_atas_timezone(offset: int)     # cambia CME y deja Replay abierto
"""

from __future__ import annotations

import time
from datetime import date, datetime
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")

SUPPORTED_OFFSETS = {-4, -5}
ATAS_TITLE_RE = r"^ATAS\b.*"
TIME_ZONE_DIALOG_TITLE = "Change Time Zone"
UI_TIMEOUT_SECONDS = 15
REPLAY_POWER_TIMEOUT_SECONDS = 60


def get_utc_offset(session_date: date) -> int:
    """Retorna -4 (EDT) o -5 (EST) para la fecha dada."""
    dt = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        12,
        tzinfo=ET,
    )
    delta = dt.utcoffset()
    if delta is None:
        raise RuntimeError(f"No pude calcular el UTC offset de {session_date}")
    return int(delta.total_seconds() / 3600)


def _wait_until(predicate, description: str, timeout: float = UI_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except Exception as exc:  # UIA puede fallar mientras ATAS redibuja.
            last_error = exc
        time.sleep(0.2)

    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"Timeout esperando {description}{detail}")


def _find_main_window(desktop):
    candidates = desktop.windows(title_re=ATAS_TITLE_RE, visible_only=True)
    if not candidates:
        raise RuntimeError("No encontre la ventana principal de ATAS abierta.")
    # Conserva un WindowSpecification: a diferencia del wrapper directo,
    # expone child_window() para resolver controles que ATAS vuelve a crear.
    return desktop.window(handle=candidates[0].handle)


def _find_replay_window(desktop):
    candidates = desktop.windows(title_re=r".*Replay.*", visible_only=True)
    return next(
        (
            window
            for window in candidates
            if window.window_text().strip().lower().startswith("replay")
        ),
        None,
    )


def _replay_power_button(replay):
    """Retorna (boton, 'on'|'off') para el icono verde de Replay."""
    for button in replay.descendants(control_type="Button"):
        text = button.window_text().strip().lower()
        if text == "the replay is on":
            return button, "on"
        if text == "the replay is off":
            return button, "off"
    raise RuntimeError("No encontre el boton de encendido de la ventana Replay.")


def _power_off_replay(desktop) -> None:
    """Pulsa el icono verde; no cierra Replay ni desmarca el ribbon principal."""
    replay = _find_replay_window(desktop)
    if replay is None:
        raise RuntimeError("No encontre la ventana Replay abierta.")
    # Las ventanas WPF de ATAS pueden estar en (-32000, -32000) aun cuando
    # pywinauto no las reporta como minimizadas. restore() corrige ambos casos.
    replay.restore()
    _wait_until(
        lambda: replay.rectangle().left > -10000 and replay.rectangle().top > -10000,
        "que la ventana Replay quede visible",
    )
    _, state = _replay_power_button(replay)
    if state == "off":
        return

    replay.set_focus()
    button, _ = _replay_power_button(replay)
    button.invoke()
    _wait_until(
        lambda: _replay_power_button(replay)[1] == "off",
        "que el icono verde apague Replay",
        timeout=REPLAY_POWER_TIMEOUT_SECONDS,
    )


def _power_on_and_restore_replay(desktop) -> None:
    """Enciende el icono de Replay y espera a que termine Loading modules."""
    replay = _find_replay_window(desktop)
    if replay is None:
        raise RuntimeError("La ventana Replay desaparecio durante el cambio de TZ.")
    replay.restore()
    replay.set_focus()
    button, state = _replay_power_button(replay)
    if state == "off":
        button.invoke()

    _wait_until(
        lambda: (
            _replay_power_button(replay)[1] == "on"
            and "playback is stopped" in replay.window_text().lower()
        ),
        "que Replay encienda y termine de cargar sus modulos",
        timeout=REPLAY_POWER_TIMEOUT_SECONDS,
    )
    replay.restore()
    _wait_until(
        lambda: replay.rectangle().left > -10000 and replay.rectangle().top > -10000,
        "que la ventana Replay quede visible",
    )


def _settings_button(main):
    """Encuentra el engrane por su arbol UIA, sin usar su posicion."""
    for button in main.descendants(control_type="Button"):
        if button.element_info.automation_id != "PART_Button":
            continue
        parent = button.parent()
        if (
            parent.element_info.control_type == "DataItem"
            and not parent.element_info.automation_id
        ):
            return button
    raise RuntimeError("No encontre el engrane Settings del panel principal de ATAS.")


def _find_dialog_handle() -> int | None:
    import win32gui

    found = []

    def visit(handle, _):
        if (
            win32gui.IsWindowVisible(handle)
            and win32gui.GetWindowText(handle) == TIME_ZONE_DIALOG_TITLE
        ):
            found.append(handle)

    win32gui.EnumWindows(visit, None)
    return found[0] if found else None


def _open_time_zone_dialog(desktop, main):
    existing = _find_dialog_handle()
    if existing:
        return desktop.window(handle=existing)

    main.set_focus()
    _settings_button(main).click_input()
    item = _wait_until(
        lambda: (
            candidate.wrapper_object()
            if (candidate := main.child_window(
                title="Time Zones",
                control_type="Button",
            )).exists(timeout=0.1)
            else None
        ),
        "el menu Settings > Time Zones",
    )
    item.click_input()

    handle = _wait_until(
        _find_dialog_handle,
        f"el dialogo {TIME_ZONE_DIALOG_TITLE!r}",
    )
    return desktop.window(handle=handle)


def _dialog_button(dialog, title: str):
    return _wait_until(
        lambda: dialog.child_window(
            title=title,
            control_type="Button",
        ).wrapper_object(),
        f"el boton {title!r} de Change Time Zone",
    )


def _focus_cme_timezone_editor(cancel_button) -> None:
    """Llega a Search y a CME solo por orden de foco, sin coordenadas."""
    from pywinauto import keyboard

    cancel_button.set_focus()
    # Desde Cancel: Tab 1 = By Exchange, Tab 2 = Search.
    keyboard.send_keys("{TAB 2}^aCME")
    time.sleep(0.35)
    # Desde Search: Tab 1 = fila CME, Tab 2 = editor Time Zone.
    keyboard.send_keys("{TAB 2}")
    time.sleep(0.15)


def _set_cme_offset(cancel_button, offset: int) -> None:
    import pyperclip
    from pywinauto import keyboard

    # Una sola entrada al grid. ATAS 8 deja de aceptar SetFocus de UIA cuando
    # DevExpress toma el foco, por lo que no intentamos volver a Cancel.
    _focus_cme_timezone_editor(cancel_button)
    keyboard.send_keys(f"^a{offset}{{ENTER}}")
    time.sleep(0.3)

    # Enter devuelve el foco a la celda; F2 reabre su editor para verificar.
    sentinel = "__ATAS_TZ_COPY_FAILED__"
    pyperclip.copy(sentinel)
    keyboard.send_keys("{F2}^a^c")
    time.sleep(0.2)
    actual = pyperclip.paste().strip()
    keyboard.send_keys("{ESC}")
    if actual != str(offset):
        raise RuntimeError(
            f"ATAS no acepto UTC{offset} para CME; el editor reporta {actual!r}."
        )


def _apply_or_cancel(dialog, apply_button, cancel_button) -> None:
    import win32gui

    button = apply_button
    if not apply_button.is_enabled():
        # Ya tenia exactamente el valor pedido y la deteccion automatica apagada.
        button = cancel_button

    handle = dialog.handle
    win32gui.SetForegroundWindow(handle)
    # El wrapper fue detectado por title/control_type antes de entrar al grid.
    # click_input calcula su posicion actual; no hay coordenadas guardadas.
    button.click_input()
    _wait_until(
        lambda: not win32gui.IsWindow(handle),
        "que ATAS cierre Change Time Zone",
    )


def ensure_atas_timezone(offset: int) -> None:
    """
    Configura CME en `offset` (-4 EDT o -5 EST) y deja Replay listo.

    La funcion siempre verifica el valor dentro del editor de CME. Si ocurre un
    error, intenta restaurar Replay antes de propagarlo para no dejar ATAS a
    mitad de la secuencia.
    """
    if offset not in SUPPORTED_OFFSETS:
        raise ValueError(f"Offset no soportado: {offset}. Usa -4 (EDT) o -5 (EST).")

    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    main = _find_main_window(desktop)
    replay = _find_replay_window(desktop)
    if replay is None:
        raise RuntimeError("No encontre la ventana Replay abierta.")

    current_offsets = {
        text.window_text().strip()
        for text in replay.descendants(control_type="Text")
        if text.window_text().strip() in {"UTC-4", "UTC-5"}
    }
    requested_label = f"UTC{offset}"
    _, power_state = _replay_power_button(replay)
    if current_offsets == {requested_label}:
        if power_state == "off":
            _power_on_and_restore_replay(desktop)
        print(f"  [TZ] Replay ya muestra {requested_label}; no se cambia ni se apaga.")
        return

    dialog = None
    cancel_button = None
    operation_error = None

    print(f"  [TZ] CME -> UTC{offset}: apagando el icono verde de Replay...")
    try:
        _power_off_replay(desktop)
        print("  [TZ] Abriendo Settings > Time Zones y buscando CME...")
        dialog = _open_time_zone_dialog(desktop, main)
        # Se guardan antes de entrar al Grid: ATAS 8 puede dejar de responder a
        # nuevas consultas UIA mientras el editor DevExpress tiene el foco.
        cancel_button = _dialog_button(dialog, "Cancel")
        apply_button = _dialog_button(dialog, "Apply")
        _set_cme_offset(cancel_button, offset)
        _apply_or_cancel(dialog, apply_button, cancel_button)
        dialog = None
        print(f"  [TZ] CME confirmado en UTC{offset}.")
    except Exception as exc:
        operation_error = exc
        if dialog is not None and cancel_button is not None:
            try:
                cancel_button.click_input()
            except Exception:
                pass
    finally:
        try:
            _power_on_and_restore_replay(desktop)
            print("  [TZ] Icono de Replay encendido; modulos cargados.")
        except Exception as restore_error:
            if operation_error is None:
                operation_error = restore_error
            else:
                operation_error = RuntimeError(
                    f"{operation_error}; ademas no pude restaurar Replay: "
                    f"{restore_error}"
                )

    if operation_error is not None:
        raise operation_error
