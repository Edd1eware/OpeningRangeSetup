"""Encuadra el grafico de ATAS para el journaling, en lazo cerrado.

La escala **no** puede ser fija: depende del tamano del rango de apertura, que
cambia cada sesion. De la captura de referencia del usuario se saca la
proporcion:

    OR 31012.50 - 31050.00  ->  37.50 puntos
    eje de precio visible    ->  102.50 puntos
    factor                   ->  2.73 x el rango del OR

Ademas el encuadre tiene que contener siempre el OR completo y las tres lineas
de la operacion (entrada, SL y TP), asi que el objetivo se calcula como el mayor
entre esa proporcion y lo que ocupan esos niveles mas un margen.

ATAS no expone el eje de precio por API. Lo que si se puede es:
  - leer lo que el grafico muestra, porque el indicador
    19_Inside_Control_Trade_Navigator lo publica en inside_control_view.txt;
  - cambiarlo arrastrando la barra de precio.

Con esas dos piezas se itera hasta converger.

Uso:
    python -u 19_frame_chart.py            # encuadra la sesion que este abierta
    python -u 19_frame_chart.py --show     # solo imprime el estado actual
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

VIEW_STATE = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\inside_control_view.txt")
CALIBRATION_PATH = VIEW_STATE.with_name("journal_layout_calibration.json")


def load_ui_dependencies():
    global win32con, win32gui, mouse, keyboard
    import win32con
    import win32gui
    from pywinauto import mouse, keyboard

# Proporcion medida en la captura de referencia del usuario.
OR_RANGE_FACTOR = 2.73
# Margen sobre los niveles de la operacion, en fraccion del rango necesario.
LEVEL_MARGIN = 0.18
# Tolerancia de convergencia: +-12% del objetivo ya es indistinguible a ojo.
TOLERANCE = 0.12
MAX_STEPS = 14


def read_state() -> dict:
    """El indicador reescribe el archivo cada ~0.4 s; un read puede pillarlo a medias."""
    for _ in range(6):
        try:
            text = VIEW_STATE.read_text(encoding="utf-8")
            state = {}
            for line in text.splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    state[key.strip()] = value.strip()
            if "range" in state:
                return state
        except Exception:
            pass
        time.sleep(0.25)
    raise SystemExit(
        f"No pude leer {VIEW_STATE}.\n"
        "Comprueba que 19_Inside_Control_Trade_Navigator este en el grafico."
    )


def as_float(state: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(state.get(key, default))
    except (ValueError, TypeError):
        return default


def price_levels(state: dict) -> list[float]:
    return [v for v in (as_float(state, k) for k in ("or_high", "or_low", "entry", "exit", "stop", "target"))
            if math.isfinite(v) and v > 0]


def target_range(state: dict) -> float:
    """Rango de precio que deberia verse, en puntos."""
    or_high, or_low = as_float(state, "or_high"), as_float(state, "or_low")
    entry, stop, target = (as_float(state, k) for k in ("entry", "stop", "target"))

    levels = price_levels(state)
    if not levels:
        return 0.0

    # Lo que hay que contener si o si, con margen.
    needed = (max(levels) - min(levels)) * (1 + LEVEL_MARGIN)

    # Lo que pide la proporcion del ejemplo.
    proportional = (or_high - or_low) * OR_RANGE_FACTOR if or_high > or_low else 0.0

    return max(needed, proportional)


def load_calibration(path: Path | None = None) -> dict:
    path = path or CALIBRATION_PATH
    try:
        layout = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"falta calibracion visual validada en {path}: {exc}") from exc
    if layout.get("verified") is not True or not str(layout.get("evidence", "")).strip():
        raise ValueError("la calibracion requiere verified=true y evidence de la observacion visual")
    keys = ["plot_offset_x", "plot_offset_y", "price_axis_offset_x"]
    keys.append("time_axis_bottom_offset" if "time_axis_bottom_offset" in layout else "time_axis_offset_y")
    for key in keys:
        value = layout.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"falta geometria calibrada: {key}")
    if layout.get("wheel_forward_direction") not in (-1, 1):
        raise ValueError("wheel_forward_direction debe indicar la direccion observada (-1 o 1)")
    return layout


def screen_geometry(state: dict, client_origin: tuple[int, int], client_size: tuple[int, int], layout: dict) -> dict:
    """Transforma coordenadas del contenedor a pantalla; nunca supone ancho de trading panel."""
    width, height = client_size
    if width <= 0 or height <= 0:
        raise ValueError("ventana minimizada/sin area cliente")
    left = as_float(state, "region_left")
    right, top, bottom = (as_float(state, k, float("nan")) for k in ("region_right", "region_top", "region_bottom"))
    if not all(math.isfinite(v) for v in (left, right, top, bottom)) or right - left < 100 or bottom - top < 100:
        raise ValueError("el indicador no publica una region valida")
    ox, oy = layout["plot_offset_x"], layout["plot_offset_y"]
    axis_x = ox + right + layout["price_axis_offset_x"]
    axis_y = oy + (top + bottom) / 2
    time_x = ox + (left + right) / 2
    time_y = (height - layout["time_axis_bottom_offset"] if "time_axis_bottom_offset" in layout
              else oy + bottom + layout["time_axis_offset_y"])
    plot = (ox + left, oy + top, ox + right, oy + bottom)
    if not (0 <= plot[0] < plot[2] <= width and 0 <= plot[1] < plot[3] <= height
            and 0 <= axis_x < width and 0 <= axis_y < height and 0 <= time_x < width and 0 <= time_y < height):
        raise ValueError("calibracion fuera del area cliente actual; revisar geometria antes de arrastrar")
    cx, cy = client_origin
    return {"price_axis": (round(cx + axis_x), round(cy + axis_y)),
            "time_axis": (round(cx + time_x), round(cy + time_y)),
            "plot_center": (round(cx + (plot[0] + plot[2]) / 2), round(cy + (plot[1] + plot[3]) / 2)),
            "plot_top": round(cy + plot[1]), "plot_bottom": round(cy + plot[3])}


def vertical_goal(state: dict) -> dict:
    levels = price_levels(state)
    if not levels:
        raise ValueError("no hay niveles historicos para encuadrar")
    wanted = target_range(state)
    if wanted <= 0:
        raise ValueError("los niveles no definen un rango de precio")
    return {"range": wanted, "center": (min(levels) + max(levels)) / 2,
            "min": min(levels), "max": max(levels)}


def vertical_status(state: dict, goal: dict) -> dict:
    top, bottom = as_float(state, "top", float("nan")), as_float(state, "bottom", float("nan"))
    if not math.isfinite(top) or not math.isfinite(bottom) or top <= bottom:
        raise ValueError("rango vertical publicado invalido")
    current, center = top - bottom, (top + bottom) / 2
    margin = current * 0.02
    contains = bottom + margin <= goal["min"] and goal["max"] <= top - margin
    return {"range": current, "center": center, "ratio": current / goal["range"],
            "center_error": goal["center"] - center, "contains": contains,
            "scale_ok": abs(current / goal["range"] - 1) <= TOLERANCE,
            "center_ok": abs(goal["center"] - center) <= current * 0.08}


def chart_hwnd() -> int:
    found = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "Chart" in title and "ATAS" not in title:
                found.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    if not found:
        raise SystemExit("No encontre la ventana del grafico.")
    return found[0]


def window_geometry(hwnd: int, state: dict, layout: dict) -> dict:
    client = win32gui.GetClientRect(hwnd)
    return screen_geometry(state, win32gui.ClientToScreen(hwnd, (0, 0)), (client[2], client[3]), layout)


def drag_point(geometry: dict, location: str, pixels: int, *, button="left", modifier=None) -> int:
    point = geometry[location]
    end_y = max(geometry["plot_top"] + 20, min(geometry["plot_bottom"] - 20, point[1] + pixels))
    moved = end_y - point[1]
    if moved == 0:
        raise ValueError("no hay espacio vertical para el gesto calibrado")
    modifiers = {"shift": "VK_SHIFT", "ctrl": "VK_CONTROL", "alt": "VK_MENU"}
    if modifier not in (None, *modifiers):
        raise ValueError("modificador de pan no compatible")
    if modifier:
        keyboard.send_keys("{" + modifiers[modifier] + " down}")
    try:
        mouse.press(button=button, coords=point)
        try:
            for index in range(1, 9):
                mouse.move(coords=(point[0], round(point[1] + moved * index / 8)))
                time.sleep(0.06)
        finally:
            mouse.release(button=button, coords=(point[0], end_y))
    finally:
        if modifier:
            keyboard.send_keys("{" + modifiers[modifier] + " up}")
    time.sleep(0.7)
    return moved


def drag_price_axis(hwnd: int, pixels: int, state: dict | None = None, layout: dict | None = None):
    """Zoom por el eje comprobado; posicion relativa al contenedor publicado."""
    state, layout = state or read_state(), layout or load_calibration()
    return drag_point(window_geometry(hwnd, state, layout), "price_axis", pixels)


def frame(verbose: bool = True, layout: dict | None = None) -> bool:
    load_ui_dependencies()
    try:
        layout = layout or load_calibration()
    except ValueError as exc:
        print(f"No se encuadra: {exc}")
        return False
    hwnd = chart_hwnd()
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
    )
    time.sleep(0.6)

    state = read_state()
    try:
        goal = vertical_goal(state)
        window_geometry(hwnd, state, layout)
    except ValueError as exc:
        print(f"No se encuadra: {exc}")
        return False
    wanted = goal["range"]
    or_size = as_float(state, "or_high") - as_float(state, "or_low")
    if verbose:
        print(f"sesion {state.get('session','?')} | OR {or_size:.2f} pts "
              f"-> rango objetivo {wanted:.1f} pts")

    pan_gain = None
    for step in range(1, MAX_STEPS + 1):
        state = read_state()
        try:
            status = vertical_status(state, goal)
            geometry = window_geometry(hwnd, state, layout)
        except ValueError as exc:
            print(f"  no se encuadra: {exc}")
            return False
        current, ratio = status["range"], status["ratio"]
        if status["scale_ok"] and status["center_ok"] and status["contains"]:
            print(f"  encuadrado y centrado en {step - 1} pasos: {current:.1f} pts visibles "
                  f"({state.get('bars')} velas, {state.get('first_time')} -> {state.get('last_time')})")
            return True
        if not status["scale_ok"]:
            pixels = max(5, int(170 * min(abs(ratio - 1), 1))) * (-1 if ratio > 1 else 1)
            if verbose:
                print(f"  paso {step}: zoom {current:.1f} pts (x{ratio:.2f}), gesto {pixels:+d} px")
            drag_price_axis(hwnd, pixels, state, layout)
            after = vertical_status(read_state(), goal)
            if (after["range"] - current) * pixels <= 0:
                print("  el gesto no produjo el zoom esperado; revisar calibracion, no se guarda captura")
                return False
            continue
        pan = layout.get("pan")
        if not isinstance(pan, dict) or pan.get("verified") is not True:
            print("  rango correcto pero niveles descentrados; falta gesto de pan vertical comprobado en calibracion")
            return False
        if pan.get("location") not in ("price_axis", "plot_center") or pan.get("button") not in ("left", "middle", "right"):
            print("  gesto de pan invalido; no se arrastra")
            return False
        direction = pan.get("positive_pixels_raise_price")
        if direction not in (-1, 1):
            print("  falta direccion de pan comprobada")
            return False
        if pan_gain is None:
            pixels = 12 * (1 if status["center_error"] * direction > 0 else -1)
        else:
            pixels = max(-180, min(180, round(status["center_error"] / pan_gain)))
            if abs(pixels) < 3:
                pixels = 3 if pixels >= 0 else -3
        if verbose:
            print(f"  paso {step}: centro {status['center']:.2f} -> {goal['center']:.2f}, pan {pixels:+d} px")
        moved = drag_point(geometry, pan["location"], pixels, button=pan["button"], modifier=pan.get("modifier"))
        after = vertical_status(read_state(), goal)
        gain = (after["center"] - status["center"]) / moved
        if abs(after["range"] / current - 1) > 0.03 or abs(gain) < 0.000001 or gain * direction <= 0:
            print("  el gesto no fue un pan vertical con escala estable; revisar calibracion")
            return False
        pan_gain = gain

    state = read_state()
    print(f"  no convergio; quedo en {as_float(state,'range'):.1f} pts "
          f"frente a {wanted:.1f} objetivo")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Encuadre ATAS en lazo cerrado con geometria calibrada")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--calibration", type=Path, default=CALIBRATION_PATH)
    args = parser.parse_args()
    if args.show:
        state = read_state()
        for key, value in state.items():
            print(f"{key:12} {value}")
        print(f"\nobjetivo     {target_range(state):.1f}")
        return 0

    try:
        layout = load_calibration(args.calibration)
    except ValueError as exc:
        print(exc)
        return 1
    return 0 if frame(layout=layout) else 1


if __name__ == "__main__":
    sys.exit(main())
