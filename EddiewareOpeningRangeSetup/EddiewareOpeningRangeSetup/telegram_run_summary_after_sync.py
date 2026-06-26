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
            print(
                f"Telegram limpieza masiva: fallo el lote "
                f"{start // TELEGRAM_DELETE_BATCH_SIZE + 1} "
                f"({len(batch)} IDs): {description}. Probando uno por uno..."
            )

            for message_id in batch:
                try:
                    single_ok, single_description = _delete_message(
                        credentials[0],
                        credentials[1],
                        message_id,
                    )
                except Exception as exc:
                    single_ok, single_description = False, str(exc)

                if single_ok:
                    processed += 1
                else:
                    failed += 1
                    print(
                        "Telegram limpieza individual: no se pudo borrar "
                        f"ID {message_id}: {single_description}"
                    )

    os.makedirs(results_folder, exist_ok=True)
    with open(message_ids_path, "w", encoding="utf-8"):
        pass
    with open(sent_dates_path, "w", encoding="utf-8"):
        pass

    print(
        f"Telegram limpieza masiva terminada: {processed} IDs procesados, "
        f"{failed} IDs en {failed_batches} lotes fallidos. "
        "Telegram omite mensajes inexistentes o no borrables. "
        "Historial de la corrida reiniciado."
    )
    return failed == 0


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
):
    """Manda un mensaje de progreso detallado: fase, avance, ETA y meta previa."""
    credentials = _read_credentials(results_folder)
    if credentials is None:
        return False

    pct = (done / total * 100) if total else 0
    header = "Etapa terminada" if final else "Progreso"
    lines = [
        f"EW Opening Range | {header} ({run_label})",
        f"Fase: ETAPA {stage_index:02d}/{stage_total:02d} - {stage_label}",
    ]
    if stage_period:
        lines.append(f"Rango: {stage_period}")
    lines.append(
        f"Progreso: {done}/{total} ({pct:.0f}%) | "
        f"PASS {passed} | FAIL {failed} | saltadas {skipped}"
    )
    if not final:
        if avg_seconds:
            lines.append(
                f"ETA etapa: {_format_eta(eta_seconds)} "
                f"(prom {avg_seconds:.0f} s/fecha x {remaining} fechas)"
            )
        else:
            lines.append(f"ETA etapa: {_format_eta(eta_seconds)}")
    if global_target:
        missing = max(global_target - (global_done or 0), 0)
        lines.append(
            f"Meta previa: {global_done}/{global_target} sesiones "
            f"(faltan {missing})"
        )

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
