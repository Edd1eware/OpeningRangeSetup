import csv
import json
import os
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen


TELEGRAM_MESSAGE_IDS_FILE = "telegram_message_ids.txt"
TELEGRAM_SENT_DATES_FILE = "telegram_sent_dates.txt"
TELEGRAM_DELETE_BATCH_SIZE = 100


def _parse_result_ticks(value):
    if value in (None, "", "OPEN", "NO_TRADE", "TIME_OVER", "HOLYDAY NO DATA"):
        return None

    normalized = str(value).strip().upper()
    if normalized == "BE":
        return 0.0

    try:
        return float(normalized.replace("+", ""))
    except ValueError:
        return None


def _read_credentials(results_folder):
    path = os.path.join(results_folder, "telegram_credentials.txt")
    if not os.path.exists(path):
        return None

    credentials = {}
    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            credentials[key.strip().lower()] = value.strip()

    token = credentials.get("token")
    chat_id = credentials.get("chat_id")
    return (token, chat_id) if token and chat_id else None


def _expected_result_path(results_folder, date):
    day, month, year = date.split("/")
    return os.path.join(
        results_folder,
        f"score_trade_result_{year}-{month}-{day}_NY.csv",
    )


def _collect_results(results_folder, dates):
    results = []

    for date in dates:
        path = _expected_result_path(results_folder, date)
        if not os.path.exists(path):
            continue

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as file:
                row = next(csv.DictReader(file), None)
        except (OSError, csv.Error):
            continue

        if not row:
            continue

        ticks = _parse_result_ticks(row.get("result TP SL BE") or row.get("RESULT"))
        if ticks is not None:
            results.append(ticks)

    return results


def _send_message(token, chat_id, message):
    body = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        method="POST",
    )

    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("ok"):
        return None

    return payload.get("result", {}).get("message_id")


def _delete_messages(token, chat_id, message_ids):
    if not message_ids:
        return True, ""

    body = urlencode(
        {
            "chat_id": chat_id,
            "message_ids": json.dumps(message_ids),
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/deleteMessages",
        data=body,
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            description = payload.get("description", str(exc))
        except Exception:
            description = str(exc)
        return False, description

    return bool(payload.get("ok")), payload.get("description", "")


def _delete_message(token, chat_id, message_id):
    body = urlencode(
        {
            "chat_id": chat_id,
            "message_id": message_id,
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/deleteMessage",
        data=body,
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            description = payload.get("description", str(exc))
        except Exception:
            description = str(exc)
        return False, description

    return bool(payload.get("ok")), payload.get("description", "")


def clear_telegram_before_run(results_folder):
    """Borra en lotes los mensajes registrados por corridas anteriores."""
    credentials = _read_credentials(results_folder)
    if credentials is None:
        print("Telegram limpieza inicial: faltan credenciales.")
        return False

    message_ids_path = os.path.join(results_folder, TELEGRAM_MESSAGE_IDS_FILE)
    sent_dates_path = os.path.join(results_folder, TELEGRAM_SENT_DATES_FILE)

    message_ids = []
    if os.path.exists(message_ids_path):
        with open(message_ids_path, "r", encoding="utf-8") as file:
            for raw_line in file:
                value = raw_line.strip()
                if value.isdigit():
                    message_ids.append(int(value))

    unique_message_ids = list(dict.fromkeys(message_ids))
    processed = 0
    failed = 0
    failed_batches = 0

    for start in range(0, len(unique_message_ids), TELEGRAM_DELETE_BATCH_SIZE):
        batch = unique_message_ids[start : start + TELEGRAM_DELETE_BATCH_SIZE]
        try:
            ok, description = _delete_messages(
                credentials[0],
                credentials[1],
                batch,
            )
        except Exception as exc:
            ok, description = False, str(exc)

        if ok:
            processed += len(batch)
        else:
            failed_batches += 1

            # Reintenta uno por uno en silencio: los <48h se borran; los >48h no
            # los puede borrar la Bot API en chat privado. No se imprime por
            # mensaje; al final se reporta el total en una sola linea.
            for message_id in batch:
                try:
                    single_ok, _ = _delete_message(
                        credentials[0],
                        credentials[1],
                        message_id,
                    )
                except Exception:
                    single_ok = False

                if single_ok:
                    processed += 1
                else:
                    failed += 1

    os.makedirs(results_folder, exist_ok=True)
    with open(message_ids_path, "w", encoding="utf-8"):
        pass
    with open(sent_dates_path, "w", encoding="utf-8"):
        pass

    # Una sola linea de resumen. Los no borrables (>48h en chat privado, limite
    # de la Bot API) se cuentan en `failed` pero NO detienen la corrida.
    print(
        f"Telegram limpieza: {processed} borrados, {failed} no borrables "
        "(>48h, limite Bot API). Historial reiniciado; la corrida continua."
    )
    return failed == 0


def send_photo(results_folder, photo_path, caption=""):
    """Manda una imagen (gráfico) a Telegram via sendPhoto (multipart)."""
    credentials = _read_credentials(results_folder)
    if credentials is None:
        return False
    token, chat_id = credentials
    boundary = "----EWBoundaryK99OpeningRange"
    with open(photo_path, "rb") as handle:
        photo = handle.read()

    def field(name, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode("utf-8")

    body = field("chat_id", chat_id)
    if caption:
        body += field("caption", caption[:1024])
    body += (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="photo"; filename="chart.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("utf-8")
    body += photo + f"\r\n--{boundary}--\r\n".encode("utf-8")

    request = Request(
        f"https://api.telegram.org/bot{token}/sendPhoto", data=body, method="POST"
    )
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            print(f"Telegram sendPhoto no ok: {payload.get('description')}")
            return False
        mid = payload.get("result", {}).get("message_id")
        if mid:
            with open(
                os.path.join(results_folder, TELEGRAM_MESSAGE_IDS_FILE),
                "a", encoding="utf-8",
            ) as file:
                file.write(f"{mid}\n")
        return True
    except Exception as exc:
        print(f"WARNING: no pude enviar foto Telegram: {exc}")
        return False


def send_text(results_folder, message):
    """Manda un mensaje de texto libre a Telegram (alertas, avisos puntuales)."""
    credentials = _read_credentials(results_folder)
    if credentials is None:
        return False
    try:
        message_id = _send_message(credentials[0], credentials[1], message)
        if message_id is None:
            return False
        with open(
            os.path.join(results_folder, TELEGRAM_MESSAGE_IDS_FILE),
            "a",
            encoding="utf-8",
        ) as file:
            file.write(f"{message_id}\n")
        return True
    except Exception as exc:
        print(f"WARNING: no pude enviar alerta Telegram: {exc}")
        return False


def _format_eta(seconds):
    if seconds is None or seconds <= 0:
        return "N/A"

    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"~{hours}h {minutes:02d}m"
    if minutes > 0:
        return f"~{minutes}m"
    return "~<1m"


def send_progress_update(
    results_folder,
    *,
    stage_index,
    stage_total,
    stage_label,
    stage_period="",
    done,
    total,
    passed,
    failed,
    skipped,
    eta_seconds=None,
    avg_seconds=None,
    remaining=0,
    global_done=None,
    global_target=None,
    run_label="Replay",
    final=False,
    start=False,
    goal=False,
    global_synced=None,
):
    """Manda un mensaje de progreso. El avance que importa es el TOTAL hacia la
    meta (sesiones sincronizadas X1==X10), no el parcial por etapa."""
    credentials = _read_credentials(results_folder)
    if credentials is None:
        return False

    synced = global_synced if global_synced is not None else (global_done or 0)

    if goal:
        message = "\n".join(
            [
                f"EW Opening Range | META ALCANZADA - Fase 1 ({run_label})",
                f"{synced}/{global_target} sesiones sincronizadas X1==X10. "
                "Replay detenido.",
                "Fase 1 completa -> pasar a Fase 2 (definir estrategia).",
            ]
        )
        try:
            message_id = _send_message(credentials[0], credentials[1], message)
            if message_id is None:
                return False
            with open(
                os.path.join(results_folder, TELEGRAM_MESSAGE_IDS_FILE),
                "a",
                encoding="utf-8",
            ) as file:
                file.write(f"{message_id}\n")
            return True
        except Exception as exc:
            print(f"WARNING: no pude enviar meta Telegram: {exc}")
            return False

    if start:
        header = "Etapa iniciada"
    elif final:
        header = "Etapa terminada"
    else:
        header = "Progreso"
    lines = [
        f"EW Opening Range | {header} ({run_label})",
        f"Fase: ETAPA {stage_index:02d}/{stage_total:02d} - {stage_label}",
    ]
    # Progreso TOTAL hacia la meta (sincronizadas X1==X10), no parcial por etapa.
    if global_target:
        missing = max(global_target - synced, 0)
        lines.append(
            f"Progreso total: {synced}/{global_target} sincronizadas X1==X10 "
            f"(faltan {missing})"
        )
    if global_done is not None:
        lines.append(f"Recolectadas X1: {global_done}")
    if not final and not start:
        if avg_seconds:
            lines.append(
                f"ETA etapa: {_format_eta(eta_seconds)} "
                f"(prom {avg_seconds:.0f} s/fecha x {remaining} fechas)"
            )
        else:
            lines.append(f"ETA etapa: {_format_eta(eta_seconds)}")

    message = "\n".join(lines)
    try:
        message_id = _send_message(credentials[0], credentials[1], message)
        if message_id is None:
            return False

        with open(
            os.path.join(results_folder, TELEGRAM_MESSAGE_IDS_FILE),
            "a",
            encoding="utf-8",
        ) as file:
            file.write(f"{message_id}\n")
        return True
    except Exception as exc:
        print(f"WARNING: no pude enviar progreso Telegram: {exc}")
        return False


def send_run_summary(results_folder, dates, failed_dates=None, run_label="Replay"):
    credentials = _read_credentials(results_folder)
    if credentials is None:
        print("Telegram resumen: faltan credenciales.")
        return False

    results = _collect_results(results_folder, dates)
    wins = [ticks for ticks in results if ticks > 0]
    losses = [ticks for ticks in results if ticks < 0]
    break_evens = [ticks for ticks in results if ticks == 0]
    decided = len(wins) + len(losses)
    win_rate = (len(wins) / decided * 100) if decided else None
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else ("INF" if gross_profit > 0 else None)
    )
    net_ticks = sum(results)
    failed_count = len(failed_dates or [])

    win_rate_text = f"{win_rate:.2f}%" if win_rate is not None else "N/A"
    if isinstance(profit_factor, float):
        profit_factor_text = f"{profit_factor:.2f}"
    else:
        profit_factor_text = profit_factor or "N/A"

    message = "\n".join(
        [
            f"EW Opening Range | Corrida terminada ({run_label})",
            f"Win rate: {win_rate_text}",
            f"Profit factor: {profit_factor_text}",
            f"Wins: {len(wins)} | Losses: {len(losses)} | BE: {len(break_evens)}",
            f"Net ticks: {net_ticks:+.0f}",
            f"Resultados: {len(results)}/{len(dates)} | Errores: {failed_count}",
        ]
    )
    if failed_dates:
        error_lines = [
            f"- {date}: {reason}"
            for date, reason in failed_dates[:10]
        ]
        remaining_errors = failed_count - len(error_lines)
        message += "\n\nErrores:\n" + "\n".join(error_lines)
        if remaining_errors > 0:
            message += f"\n... y {remaining_errors} más."

    try:
        message_id = _send_message(credentials[0], credentials[1], message)
        if message_id is None:
            print("Telegram resumen: la API no confirmo el mensaje.")
            return False

        with open(
            os.path.join(results_folder, TELEGRAM_MESSAGE_IDS_FILE),
            "a",
            encoding="utf-8",
        ) as file:
            file.write(f"{message_id}\n")

        print("Telegram resumen enviado.")
        return True
    except Exception as exc:
        print(f"WARNING: no pude enviar resumen Telegram: {exc}")
        return False
