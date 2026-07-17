"""Reanuda Historia X10 sin clic fisico y se detiene en el primer fallo.

Este adaptador no cambia la logica de Replay ni la estrategia. Sustituye solo el
transporte de UI durante una reanudacion: DateEdit usa ValuePattern, Stop usa
InvokePattern y Play queda a cargo de ``replay_start_ui_supervisor.py``. Cualquier
intento inesperado de mover el puntero falla de inmediato.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

from pywinauto.controls.uiawrapper import UIAWrapper

import replay_sync_runner_common_after_sync as replay_sync
from telegram_run_summary_after_sync import send_text
from windows_run_awake import prevent_sleep


BASE_DIR = Path(__file__).resolve().parent
RUNNER_PATH = BASE_DIR / "04_run_replay_score_trade_results_dst_2025_2026_after_sync.py"
RESULTS_FOLDER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)
TARGET_FILE = RESULTS_FOLDER.parent / "target_trade_result_date.txt"


class ResumeAbort(BaseException):
    """Corta la iteracion externa; no la captura ``except Exception`` del runner."""

    def __init__(self, date_iso: str, reason: str):
        self.date_iso = date_iso
        self.reason = reason
        super().__init__(f"{date_iso}: {reason}")


def _safe_paste_text(control, value: str) -> None:
    """Escribe un DateEdit con UIA ValuePattern, sin mouse ni teclado fisico."""

    value_iface = getattr(control, "iface_value", None)
    if value_iface is None:
        raise RuntimeError("DateEdit no expone UIA ValuePattern; no se movera el mouse.")
    value_iface.SetValue(value)
    time.sleep(0.15)


def _no_physical_click(self, *args, **kwargs):
    """Convierte botones a Invoke y bloquea cualquier otro clic fisico."""

    control_type = str(getattr(self.element_info, "control_type", ""))
    automation_id = str(getattr(self.element_info, "automation_id", ""))
    name = str(getattr(self.element_info, "name", ""))

    # El PlayButton interno no se invoca aqui. El supervisor externo espera el
    # marcador del runner y pulsa el Start visible mediante InvokePattern.
    if control_type == "Button" and automation_id == "PlayButton":
        return self
    if control_type == "Button":
        self.invoke()
        return self

    raise RuntimeError(
        "Clic fisico bloqueado durante reanudacion X10: "
        f"control={control_type or '?'} automation_id={automation_id!r} name={name!r}"
    )


def _install_runtime_guards() -> None:
    replay_sync.paste_text = _safe_paste_text
    UIAWrapper.click_input = _no_physical_click

    original_run_one_date = replay_sync.run_one_date

    def fail_fast_run_one_date(date_iso, *args, **kwargs):
        try:
            ok, reason = original_run_one_date(date_iso, *args, **kwargs)
        except ResumeAbort:
            raise
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise ResumeAbort(date_iso, f"{type(exc).__name__}: {exc}") from exc
        if not ok:
            raise ResumeAbort(date_iso, reason or "RUN_ONE_DATE_FAILED")
        return ok, reason

    replay_sync.run_one_date = fail_fast_run_one_date


def _load_runner():
    spec = importlib.util.spec_from_file_location("resume_x10_numbered_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar runner: {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    _install_runtime_guards()
    runner = _load_runner()
    print(
        "RESUME_GUARDS_ACTIVE: Historia X10 | UIA Value/Invoke | "
        "mouse fisico bloqueado | fail-fast habilitado",
        flush=True,
    )
    with prevent_sleep():
        print("KEEP_AWAKE_ACTIVE: sistema y pantalla protegidos durante la corrida", flush=True)
        try:
            return int(runner.main() or 0)
        except ResumeAbort as exc:
            TARGET_FILE.write_text(exc.date_iso, encoding="utf-8")
            message = (
                "OR ABSORTION TEST | REANUDACION X10 DETENIDA\n"
                f"Fecha: {exc.date_iso}\n"
                f"Motivo: {exc.reason}\n"
                "No se avanzo a otra fecha. Balance, resultados y Telegram fueron preservados.\n"
                "Timer etapa: DETENIDA"
            )
            print(message, flush=True)
            try:
                send_text(RESULTS_FOLDER, message)
            except Exception as telegram_exc:
                print(f"WARNING: no pude enviar alerta Telegram: {telegram_exc}", flush=True)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
