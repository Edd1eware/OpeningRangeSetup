from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RESULTS_FOLDER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)


def read_credentials(path: Path) -> tuple[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()
    token = values.get("token", "")
    chat_id = values.get("chat_id", "")
    if not token or not chat_id:
        raise RuntimeError("telegram_credentials.txt no contiene token y chat_id")
    return token, chat_id


def sorted_hours(values: dict[str, int]) -> str:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{hour} ({count})" for hour, count in ordered) or "sin casos"


def build_message(summary: dict[str, object]) -> str:
    confirmed_leaders = summary["confirmed_leaders"]
    cfd_hours = summary["confirmed_cfd_leads_by_hour_ny"]
    atas_hours = summary["confirmed_atas_leads_by_hour_ny"]
    return "\n".join(
        [
            "TERMINÓ LA FASE DE DISEÑO — ATAS L2 vs CFD",
            "",
            "Backtest estructural DST | julio 2026 | 09:30–16:00 NY",
            (
                f"Cobertura: {summary['sessions_observed']} sesiones, "
                f"{summary['common_minutes_observed']} velas M1 comunes."
            ),
            (
                f"Liderazgos comprobados: {summary['confirmed_events']} "
                f"({summary['confirmed_events_per_session']} por sesión; "
                f"~{summary['estimated_confirmed_events_per_21_sessions']} por 21 sesiones)."
            ),
            (
                f"CFD lideró {confirmed_leaders.get('CFD MT5', 0)} veces; "
                f"ATAS L2 lideró {confirmed_leaders.get('ATAS L2', 0)} veces."
            ),
            f"Horas CFD más frecuentes (NY): {sorted_hours(cfd_hours)}.",
            f"Horas ATAS más frecuentes (NY): {sorted_hours(atas_hours)}.",
            (
                f"Retraso hasta la réplica: media {summary['response_delay_mean_m1']} "
                f"y mediana {summary['response_delay_median_m1']} velas M1."
            ),
            "",
            "Prueba visual 6-ago: CFD pivote inferior 14:37 NY; señal estructural 14:40; ATAS confirmó 14:42 (CFD adelantó 5 min).",
            "",
            "Regla: no decide un simple delay. Exige pivote 2x2, swing >=5 ATR, reacción >=1.5 ATR, nivel equivalente ajustado por escala y 3 velas sin estructura equivalente en el otro mercado.",
            (
                f"Se observaron {summary['events']} señales tempranas; "
                f"{summary['confirmed_events']} fueron replicadas por el rezagado en <=8 min."
            ),
            "Las alertas en vivo serán un solo Telegram con captura conjunta y el líder claramente indicado.",
        ]
    )


def send_message(token: str, chat_id: str, message: str) -> int:
    data = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rechazó el resumen: {payload.get('description', 'error')}")
    return int(payload["result"]["message_id"])


def send_document(token: str, chat_id: str, path: Path, caption: str = "") -> int:
    boundary = f"----CodexTelegram{secrets.token_hex(12)}"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode(),
    ]
    if caption:
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode(
                "utf-8"
            )
        )
    chunks.extend(
        [
            (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"document\"; filename=\"{path.name}\"\r\n"
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8"),
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = Request(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rechazó {path.name}: {payload.get('description', 'error')}")
    return int(payload["result"]["message_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--message-file", type=Path)
    parser.add_argument("--document", type=Path, action="append", default=[])
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    if args.message_file:
        message = args.message_file.read_text(encoding="utf-8").strip()
    elif args.summary:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        message = build_message(summary)
    else:
        parser.error("indica --summary o --message-file")
    if not args.send:
        print(message)
        for document in args.document:
            print(f"DOCUMENT {document}")
        return 0
    token, chat_id = read_credentials(RESULTS_FOLDER / "telegram_credentials.txt")
    message_id = send_message(token, chat_id, message)
    print(f"TELEGRAM_SENT message_id={message_id}")
    for document in args.document:
        document_id = send_document(token, chat_id, document)
        print(f"TELEGRAM_DOCUMENT_SENT message_id={document_id} file={document.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
