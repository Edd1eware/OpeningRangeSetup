"""Send a report to Telegram: text from stdin or a file, chunked to fit.

    python scripts/notify_telegram.py --title "regla completa" --file report.txt
    some_command | python scripts/notify_telegram.py --title "salida"

Only sends. It never polls for updates, so it cannot fight with the ATAS
notifier or with telegram_bridge.py over the same bot token - Telegram only
rejects concurrent *pollers*.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from telegram_bridge import load_credentials  # same credential resolution

API = "https://api.telegram.org/bot{token}/sendMessage"
LIMIT = 3800


def send(token: str, chat: str, text: str) -> bool:
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": f"<pre>{html.escape(text)}</pre>",
        "parse_mode": "HTML",
    }).encode()
    with urllib.request.urlopen(API.format(token=token), data=data,
                                timeout=60) as r:
        return bool(json.loads(r.read()).get("ok"))


def chunks(text: str, limit: int = LIMIT) -> list[str]:
    """Split on line boundaries so tables do not break mid-row."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > limit and cur:
            out.append(cur)
            cur = ""
        cur += line
    if cur:
        out.append(cur)
    return out or [""]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="")
    ap.add_argument("--file", type=Path, default=None)
    a = ap.parse_args()

    body = (a.file.read_text(encoding="utf-8", errors="replace")
            if a.file else sys.stdin.read())
    if a.title:
        body = f"== {a.title} ==\n\n{body}"
    token, chat = load_credentials()
    parts = chunks(body)
    for i, part in enumerate(parts, 1):
        tag = f"\n[{i}/{len(parts)}]" if len(parts) > 1 else ""
        if not send(token, chat, part + tag):
            print(f"fallo al enviar la parte {i}", file=sys.stderr)
            return 1
    print(f"enviado a Telegram en {len(parts)} mensaje(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
