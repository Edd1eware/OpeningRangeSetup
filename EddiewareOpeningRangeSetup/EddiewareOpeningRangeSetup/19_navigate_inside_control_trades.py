"""Driver del navegador de los 35 trades del control `apertura dentro del OR`.

Mueve el Replay de ATAS de una sesion a otra y le avisa al indicador
19_Inside_Control_Trade_Navigator cual es el trade activo, escribiendo su numero
en un archivo que el indicador lee y resalta en el panel.

Uso:
    python -u 19_navigate_inside_control_trades.py

Comandos dentro del navegador:
    Enter / n   siguiente trade
    p           trade anterior
    <numero>    saltar al trade N (1..35)
    tp / sl     siguiente trade con ese resultado
    l           listar los 35 trades
    r           pulsar Play en el Replay
    s           pulsar Stop en el Replay
    q           salir

Requisitos: ATAS abierto con la ventana Replay visible. El CSV lo genera
mbp_mbo_research/scripts/build_inside_control_navigator.py.

La ventana Replay se envuelve por HANDLE (win32) en lugar de enumerar el
escritorio con Desktop.windows(): esa enumeracion UIA se cuelga cuando hay
aplicaciones pesadas abiertas.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import pyperclip
import win32gui
from pywinauto import Application

EXPORT_FOLDER = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator")
TRADES_CSV = EXPORT_FOLDER / "inside_control_trades.csv"
CURSOR_FILE = EXPORT_FOLDER / "inside_control_current.txt"

# Wide enough to show the pre-market context, the opening range and every exit
# (the longest trade of the run lasts about 13 minutes).
REPLAY_FROM_TIME = "09:25"
REPLAY_TO_TIME = "10:30"


# ---------------------------------------------------------------- trade loading


def load_trades() -> list[dict]:
    if not TRADES_CSV.exists():
        raise SystemExit(
            f"No existe {TRADES_CSV}.\n"
            "Generalo con: python -u mbp_mbo_research/scripts/build_inside_control_navigator.py"
        )

    with TRADES_CSV.open(encoding="utf-8") as fh:
        trades = list(csv.DictReader(fh, delimiter=";"))

    trades.sort(key=lambda t: t["session"])
    return trades


def date_replay_from_iso(date_iso: str) -> str:
    year, month, day = date_iso.split("-")
    return f"{month}/{day}/{year}"


# ------------------------------------------------------------- replay controls


def find_replay_hwnd() -> int:
    hwnds: list[int] = []

    def _collect(hwnd, _):
        if (win32gui.IsWindowVisible(hwnd)
                and win32gui.GetWindowText(hwnd).lower().startswith("replay")):
            hwnds.append(hwnd)

    win32gui.EnumWindows(_collect, None)
    if not hwnds:
        raise SystemExit("No hay ventana 'Replay' visible. Abrela en ATAS y vuelve a correr.")
    return hwnds[0]


class ReplayWindow:
    def __init__(self):
        self.hwnd = find_replay_hwnd()
        app = Application(backend="uia").connect(handle=self.hwnd)
        self.window = app.window(handle=self.hwnd)
        self.window.wrapper_object()
        self._bind_controls()

    def _bind_controls(self):
        edits = self.window.descendants(control_type="Edit")
        buttons = self.window.descendants(control_type="Button")

        # ATAS 8.0 names the range fields by automation id (StartEdit / EndEdit) and
        # gives them class TextEdit. Older builds exposed class DateEdit named
        # "From"/"To", which is what the legacy runner looks for, so try both.
        def by_auto_id(wanted: str):
            return next(
                (e for e in edits
                 if (e.element_info.automation_id or "").strip().lower() == wanted),
                None,
            )

        def by_name(prefix: str):
            return next(
                (e for e in edits
                 if e.element_info.class_name == "DateEdit"
                 and (e.element_info.name or "").strip().lower().startswith(prefix)),
                None,
            )

        self.from_box = by_auto_id("startedit") or by_name("from")
        self.to_box = by_auto_id("endedit") or by_name("to")
        self.play = next(
            (b for b in buttons if b.element_info.automation_id == "PlayButton"), None
        )
        if self.play is None:
            self.play = next(
                (b for b in buttons
                 if b.window_text().strip().lower() in {"start", "play", "iniciar"}),
                None,
            )
        self.stop = next(
            (b for b in buttons if b.window_text().strip().lower() in {"stop", "detener"}),
            None,
        )

        if self.from_box is None or self.to_box is None:
            raise SystemExit("No encontre los campos FROM/TO de la ventana Replay.")

    def focus(self):
        try:
            self.window.set_focus()
        except Exception:
            pass

    @staticmethod
    def _value(control) -> str:
        try:
            return str(control.get_value())
        except Exception:
            try:
                return str(control.window_text())
            except Exception:
                return ""

    @staticmethod
    def _paste(control, value: str):
        """Same sequence the production runner uses: ATAS DateEdit needs both the
        keyboard replacement and the ValuePattern to accept a new date."""
        try:
            control.set_focus()
        except Exception:
            pass

        control.click_input()
        time.sleep(0.15)

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

    def set_range(self, date_iso: str) -> bool:
        date_replay = date_replay_from_iso(date_iso)
        want_from = f"{date_replay} {REPLAY_FROM_TIME} a. m."
        want_to = f"{date_replay} {REPLAY_TO_TIME} a. m."

        self.focus()

        for attempt in range(1, 4):
            if attempt > 1:
                self._bind_controls()

            self._paste(self.from_box, want_from)
            got_from = self._value(self.from_box)

            self._paste(self.to_box, want_to)
            time.sleep(0.5)
            got_to = self._value(self.to_box)

            ok = (date_replay in got_from and REPLAY_FROM_TIME in got_from
                  and date_replay in got_to and REPLAY_TO_TIME in got_to
                  and got_from != got_to)
            if ok:
                print(f"  Replay: FROM {got_from} | TO {got_to}")
                return True

            print(f"  ATAS no confirmo el rango (intento {attempt}/3): "
                  f"FROM={got_from!r} TO={got_to!r}")
            time.sleep(0.75)

        return False

    def click(self, button, label: str):
        if button is None:
            print(f"  No encontre el boton {label}.")
            return
        try:
            button.click_input()
            print(f"  {label} pulsado.")
        except Exception as exc:
            print(f"  No pude pulsar {label}: {exc}")


# ------------------------------------------------------------------- rendering


def write_cursor(trade: dict):
    try:
        CURSOR_FILE.write_text(str(trade["n"]), encoding="utf-8")
    except Exception as exc:
        print(f"  No pude escribir {CURSOR_FILE}: {exc}")


def describe(trade: dict, total: int):
    side = "COMPRA" if trade["dir"] == "1" else "VENTA"
    net_ticks = float(trade["net_ticks"])
    sign = "+" if net_ticks > 0 else ""

    print()
    print("=" * 74)
    print(f"TRADE {trade['n']}/{total}   {trade['session']}   {side}   vela {trade['minute']}")
    print("=" * 74)
    print(f"  OR            {trade['or_low']} - {trade['or_high']}")
    print(f"  Entrada       {trade['entry']}  a las {trade['entry_clock']} NY")
    print(f"  Stop          {trade['stop']}      ({trade['risk_ticks']} ticks de riesgo)")
    print(f"  Target        {trade['target']}")
    print(f"  Resultado     {trade['result']}  {sign}{net_ticks:.1f} ticks  "
          f"{float(trade['net_r']):+.2f} R  {float(trade['net_usd']):+.0f} USD con 1 NQ")
    print(f"  Salida        {trade['exit']} a las {trade['exit_clock']} NY "
          f"({float(trade['duration_s']):.1f} s)")
    print(f"  MAE/MFE       {trade['mae']} / {trade['mfe']} ticks")
    print(f"  Footprint     {trade['source']}")
    for row in trade["imb_rows"].split("|"):
        lo, hi, vol, ref, ratio = row.split(":")
        shown = "inf" if float(ratio) >= 999 else ratio
        print(f"  Imbalance     {lo}-{hi}   {vol} x {ref}   ratio {shown}")
    if trade["warn"]:
        print(f"  ADVERTENCIA   {trade['warn'].replace(',', ', ')}")


def print_list(trades: list[dict], current: int):
    print()
    print(f"{'':2} {'#':>2}  {'sesion':10} {'vela':5} {'d':1} {'res':3} {'ticks':>7} {'R':>7}")
    for i, t in enumerate(trades):
        mark = ">" if i == current else " "
        print(f"{mark:2} {t['n']:>2}  {t['session']:10} {t['minute']:5} "
              f"{'L' if t['dir'] == '1' else 'C':1} {t['result']:3} "
              f"{float(t['net_ticks']):>7.1f} {float(t['net_r']):>7.2f}")

    wins = sum(1 for t in trades if float(t["net_ticks"]) > 0)
    usd = sum(float(t["net_usd"]) for t in trades)
    r = sum(float(t["net_r"]) for t in trades)
    print(f"\n  {len(trades)} trades | WR {wins / len(trades):.2%} | "
          f"neto {usd:+,.0f} USD con 1 NQ | {r:+.2f} R")
    if usd > 0 and r < 0:
        print("  Gana en dinero con 1 contrato pero pierde por unidad de riesgo: "
              "el PF monetario viene de los stops grandes, no de direccion.")


# ------------------------------------------------------------------------ main


def main() -> int:
    trades = load_trades()
    total = len(trades)
    print(f"Cargados {total} trades desde {TRADES_CSV}")

    try:
        replay = ReplayWindow()
        print(f"Ventana Replay conectada (hwnd {replay.hwnd}).")
    except SystemExit as exc:
        print(exc)
        print("Puedes seguir navegando la lista, pero no movere el Replay.")
        replay = None

    index = 0

    def go(new_index: int):
        nonlocal index
        index = max(0, min(new_index, total - 1))
        trade = trades[index]
        describe(trade, total)
        write_cursor(trade)
        if replay is not None:
            if not replay.set_range(trade["session"]):
                print("  Ajusta la fecha a mano; ATAS rechazo el rango 3 veces.")

    go(0)

    print("\nComandos: Enter/n siguiente | p anterior | <numero> saltar | "
          "tp | sl | l listar | r play | s stop | q salir")

    while True:
        try:
            raw = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if raw in {"q", "quit", "salir"}:
            return 0
        if raw in {"", "n", "next"}:
            if index >= total - 1:
                print("  Ya estas en el ultimo trade.")
                continue
            go(index + 1)
        elif raw in {"p", "prev", "anterior"}:
            if index <= 0:
                print("  Ya estas en el primero.")
                continue
            go(index - 1)
        elif raw in {"tp", "sl"}:
            wanted = raw.upper()
            nxt = next((i for i in range(index + 1, total)
                        if trades[i]["result"] == wanted), None)
            if nxt is None:
                print(f"  No hay mas trades con resultado {wanted} despues de este.")
                continue
            go(nxt)
        elif raw in {"l", "list", "lista"}:
            print_list(trades, index)
        elif raw in {"r", "play"}:
            if replay is not None:
                replay.focus()
                replay.click(replay.play, "Play")
        elif raw in {"s", "stop"}:
            if replay is not None:
                replay.focus()
                replay.click(replay.stop, "Stop")
        elif raw.isdigit():
            n = int(raw)
            if not 1 <= n <= total:
                print(f"  Fuera de rango: usa 1..{total}.")
                continue
            go(n - 1)
        else:
            print("  Comando desconocido.")


if __name__ == "__main__":
    sys.exit(main())
