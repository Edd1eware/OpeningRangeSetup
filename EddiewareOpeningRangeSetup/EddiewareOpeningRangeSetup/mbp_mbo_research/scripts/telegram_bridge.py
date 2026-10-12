"""Telegram -> Claude Code bridge: your text messages become prompts.

You send a message to your bot, this process feeds it to `claude -p` inside the
project directory, and the reply comes back to the same chat. Context carries
over between messages, so it behaves like the terminal session.

    python -u scripts/telegram_bridge.py

SECURITY - READ THIS ONCE
-------------------------
This turns any message your bot receives into a command that can read and write
files on this machine. Three guards are in place:

1. SENDER LOCK. Only the user id in the credentials file is answered. Anything
   else is logged and dropped, never executed. Group chats are refused unless
   their id is the allowed one.
2. TOOL ALLOWLIST. Claude runs with `--permission-mode acceptEdits` and an
   explicit tool allowlist, not with permissions bypassed. Pass --bypass to
   remove that, and the process says so loudly at startup.
3. SPEND LOCK. A message that looks like it would download Databento data is
   refused unless it carries the token `#gasto-ok`. Databento bills per request;
   a careless "bajame 5 anios" is real money. The guard is a regex here AND an
   instruction in the appended system prompt, so both layers have to fail.

None of this makes a leaked bot token harmless. If the token leaks, revoke it
with @BotFather and put the new one in the credentials file.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
CRED_CANDIDATES = [
    PROJECT / "credentials" / "telegram_credentials.txt",
    Path.home() / "Desktop" / "Performance" / "telegram_process_files"
    / "telegram_credentials.txt",
]
STATE = PROJECT / "credentials" / ".telegram_offset"
API = "https://api.telegram.org/bot{token}/{method}"
TG_LIMIT = 3900          # Telegram caps a message at 4096 characters

SPEND_PATTERN = re.compile(
    r"\b(descarg|baja|bajar|download|02_download|get_range|databento)\w*\b",
    re.IGNORECASE)
SPEND_TOKEN = "#gasto-ok"

ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Glob", "Grep", "TodoWrite",
    "Bash(python *)", "Bash(python3 *)", "Bash(py *)",
    "Bash(ls *)", "Bash(cat *)", "Bash(head *)", "Bash(tail *)",
    "Bash(grep *)", "Bash(wc *)", "Bash(find *)", "Bash(du *)",
]

SYSTEM_APPEND = (
    "You are answering through a Telegram bridge, so replies are read on a "
    "phone: keep them short and put numbers in small tables. "
    "NEVER run any Databento download (scripts/02_download.py, "
    "timeseries.get_range, or anything that bills the account) unless the "
    "user's message literally contains the text '#gasto-ok'. Without that "
    "token, say what it would cost and ask for confirmation instead. "
    "The research rules stand: do not lie, do not overfit, do not lookahead."
)


def load_credentials() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    for path in CRED_CANDIDATES:
        if token and chat:
            break
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = (p.strip() for p in line.split("=", 1))
            if k == "token" and not token:
                token = v
            elif k == "chat_id" and not chat:
                chat = v
    if not token or not chat:
        raise SystemExit(
            "no Telegram credentials. Put token= and chat_id= in "
            f"{CRED_CANDIDATES[0]} or set TELEGRAM_BOT_TOKEN / "
            "TELEGRAM_CHAT_ID.")
    return token, chat


def call(token: str, method: str, **params) -> dict:
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=60) as r:
            return json.loads(r.read())
    except Exception as exc:                      # keep the loop alive
        print(f"[telegram] {method} failed: {exc}", flush=True)
        return {}


def send(token: str, chat: str, text: str) -> None:
    """Send a reply, split into Telegram-sized chunks, as preformatted text."""
    text = text.strip() or "(sin salida)"
    for i in range(0, len(text), TG_LIMIT):
        chunk = text[i:i + TG_LIMIT]
        call(token, "sendMessage", chat_id=chat,
             text=f"<pre>{html.escape(chunk)}</pre>", parse_mode="HTML")


def read_offset() -> int:
    try:
        return int(STATE.read_text().strip())
    except Exception:
        return 0


def write_offset(v: int) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(str(v))
    except Exception:
        pass


def run_claude(prompt: str, fresh: bool, bypass: bool, model: str | None) -> str:
    cmd = ["claude", "-p", prompt,
           "--append-system-prompt", SYSTEM_APPEND]
    if bypass:
        cmd += ["--permission-mode", "bypassPermissions"]
    else:
        cmd += ["--permission-mode", "acceptEdits",
                "--allowedTools", *ALLOWED_TOOLS]
    if model:
        cmd += ["--model", model]
    if not fresh:
        cmd.append("--continue")
    try:
        r = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True,
                           timeout=3600, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "se paso de una hora y lo corte. Divide la tarea en pasos."
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        err = (r.stderr or "").strip()[-1500:]
        # a --continue with no prior session fails: retry once, fresh
        if not fresh and ("No conversation" in err or "no conversation" in err):
            return run_claude(prompt, True, bypass, model)
        return f"claude salio con codigo {r.returncode}\n{err or out}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bypass", action="store_true",
                    help="run Claude with permissions bypassed instead of the "
                         "tool allowlist. Wider blast radius; your call.")
    ap.add_argument("--model", default=None)
    ap.add_argument("--poll", type=int, default=30, help="long-poll seconds")
    a = ap.parse_args()

    token, allowed = load_credentials()
    print(f"puente Telegram activo. chat permitido: {allowed}")
    print(f"directorio: {PROJECT}")
    print(f"permisos: {'BYPASS (todo permitido)' if a.bypass else 'allowlist de herramientas'}")
    if a.bypass:
        print("  AVISO: con --bypass cualquier mensaje de ese chat puede hacer "
              "cualquier cosa en esta maquina.")
    print(f"gasto: un mensaje que pida descargar datos necesita '{SPEND_TOKEN}'")
    print("comandos: /nueva (conversacion limpia), /ping, /ayuda\n", flush=True)

    offset = read_offset()
    fresh_next = False
    send(token, allowed, "Puente activo. Mandame instrucciones.\n"
                         "/nueva para empezar conversacion limpia\n"
                         f"para descargas agrega {SPEND_TOKEN}")

    while True:
        res = call(token, "getUpdates", offset=offset, timeout=a.poll)
        for upd in res.get("result", []):
            offset = max(offset, upd.get("update_id", 0) + 1)
            write_offset(offset)
            msg = upd.get("message") or upd.get("edited_message") or {}
            text = (msg.get("text") or "").strip()
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            from_id = str((msg.get("from") or {}).get("id", ""))
            if not text:
                continue
            if chat_id != allowed and from_id != allowed:
                print(f"[rechazado] chat={chat_id} from={from_id}: {text[:60]!r}",
                      flush=True)
                continue

            low = text.lower()
            if low in ("/ping", "ping"):
                send(token, allowed, "vivo")
                continue
            if low in ("/ayuda", "/help"):
                send(token, allowed,
                     "Mandame cualquier instruccion y la ejecuto en el proyecto.\n"
                     "/nueva  conversacion limpia\n"
                     "/ping   comprobar que estoy vivo\n"
                     f"{SPEND_TOKEN}  autoriza una descarga de Databento")
                continue
            if low in ("/nueva", "/new", "/reset"):
                fresh_next = True
                send(token, allowed, "listo, el siguiente mensaje empieza limpio")
                continue
            if SPEND_PATTERN.search(text) and SPEND_TOKEN not in text:
                send(token, allowed,
                     "Eso parece una descarga de Databento, que cuesta dinero.\n"
                     f"Si lo quieres, reenvia el mensaje agregando {SPEND_TOKEN}.")
                print(f"[gasto bloqueado] {text[:80]!r}", flush=True)
                continue

            print(f"[prompt] {text[:100]!r}", flush=True)
            call(token, "sendChatAction", chat_id=allowed, action="typing")
            t0 = time.time()
            reply = run_claude(text, fresh_next, a.bypass, a.model)
            fresh_next = False
            print(f"[listo] {time.time()-t0:.0f}s, {len(reply)} chars", flush=True)
            send(token, allowed, reply)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\npuente detenido")
