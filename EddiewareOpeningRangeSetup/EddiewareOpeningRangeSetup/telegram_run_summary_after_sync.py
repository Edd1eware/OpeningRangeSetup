import csv
import io
import json
import os
import re
import tempfile
from pathlib import Path
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


def _parse_number(value):
    try:
        text = str(value or "").strip().replace("+", "")
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def _parse_bool(value):
    return str(value or "").strip().upper() in {"TRUE", "1", "YES", "SI"}


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


def compute_run_stats(run_root, allowed_dates=None, run_names=None):
    """Stats acumuladas de la corrida leyendo score_trade_result_*_NY.csv bajo
    run_root. Solo acepta carpetas X10_* directas o anidadas.

    Retorna dict con: trades, winrate, pf, tp_ticks, sl_ticks,
    max_consec_wins, max_consec_losses. None si no hay trades cerrados.
    BE (0 ticks) no cuenta como win ni loss y corta ambas rachas.
    """
    root = Path(run_root)
    if not root.exists():
        return None

    if allowed_dates is not None:
        allowed_dates = set(allowed_dates)
    if run_names is not None:
        run_names = set(run_names)

    rows_by_date = {}
    for csv_path in sorted(root.rglob("score_trade_result_*_NY.csv")):
        parent = csv_path.parent.name
        if not parent.startswith("X10_"):
            continue
        if run_names is not None and parent not in run_names:
            continue
        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
                row = next(iter(csv.DictReader(fh)), None)
        except Exception:
            continue
        if not row:
            continue
        match = re.search(r"(\d{4}-\d{2}-\d{2})", csv_path.name)
        date_key = match.group(1) if match else str(row.get("fecha") or "").strip() or csv_path.name
        if allowed_dates is not None and date_key not in allowed_dates:
            continue
        rows_by_date[date_key] = row

    ticks_by_date = []
    time_over_count = 0
    tp_ticks = sl_ticks = None
    initial_brackets = {}
    initial_rr_values = []
    target_modification_reasons = {}
    dynamic_target_moves = 0
    for date_key in sorted(rows_by_date):
        row = rows_by_date[date_key]
        result_ticks = _parse_result_ticks(row.get("result TP SL BE"))
        if result_ticks is None:
            if str(row.get("Result_Label") or "").strip().upper() == "TIME_OVER":
                time_over_count += 1
            continue
        ticks_by_date.append(result_ticks)
        initial_tp = _parse_number(row.get("Initial_TP_ticks"))
        initial_sl = _parse_number(row.get("Initial_SL_ticks"))
        initial_rr = _parse_number(row.get("Initial_RR"))
        if initial_tp is not None and initial_sl is not None:
            bracket = (initial_tp, initial_sl)
            initial_brackets[bracket] = initial_brackets.get(bracket, 0) + 1
            tp_ticks = initial_tp
            sl_ticks = initial_sl
        if initial_rr is not None:
            initial_rr_values.append(initial_rr)
        if _parse_bool(row.get("Target_Was_Moved")):
            dynamic_target_moves += 1
            reason = str(row.get("Target_Modification_Reason") or "NO_REGISTRADO").strip()
            target_modification_reasons[reason] = target_modification_reasons.get(reason, 0) + 1

    if not ticks_by_date:
        if not rows_by_date:
            return None
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "break_evens": 0,
            "winrate": None,
            "pf": None,
            "profit_ticks": 0.0,
            "expectancy_ticks": 0.0,
            "average_win_ticks": None,
            "average_loss_ticks": None,
            "time_over": time_over_count,
            "tp_ticks": None,
            "sl_ticks": None,
            "initial_brackets": {},
            "min_initial_rr": None,
            "dynamic_target_moves": 0,
            "target_modification_reasons": {},
            "max_consec_wins": 0,
            "max_consec_losses": 0,
        }

    wins = [t for t in ticks_by_date if t > 0]
    losses = [t for t in ticks_by_date if t < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)

    max_consec_wins = max_consec_losses = 0
    run_wins = run_losses = 0
    for t in ticks_by_date:
        if t > 0:
            run_wins += 1
            run_losses = 0
        elif t < 0:
            run_losses += 1
            run_wins = 0
        else:  # BE corta ambas rachas
            run_wins = run_losses = 0
        max_consec_wins = max(max_consec_wins, run_wins)
        max_consec_losses = max(max_consec_losses, run_losses)

    return {
        "trades": len(ticks_by_date),
        "wins": len(wins),
        "losses": len(losses),
        "break_evens": len([t for t in ticks_by_date if t == 0]),
        "winrate": 100.0 * len(wins) / len(ticks_by_date),
        "pf": (gross_win / gross_loss) if gross_loss > 0 else None,
        "profit_ticks": sum(ticks_by_date),
        "expectancy_ticks": sum(ticks_by_date) / len(ticks_by_date),
        "average_win_ticks": (sum(wins) / len(wins)) if wins else None,
        "average_loss_ticks": (sum(losses) / len(losses)) if losses else None,
        "time_over": time_over_count,
        "tp_ticks": tp_ticks,
        "sl_ticks": sl_ticks,
        "initial_brackets": initial_brackets,
        "min_initial_rr": min(initial_rr_values) if initial_rr_values else None,
        "dynamic_target_moves": dynamic_target_moves,
        "target_modification_reasons": target_modification_reasons,
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
    }


def collect_daily_metrics(run_root, allowed_dates=None, run_names=None):
    """Devuelve una fila diaria X10 con MAE/MFE y WR/PF acumulados.

    El reporte es deliberadamente read-only: no interviene en Replay ni en la
    seleccion/ejecucion de trades. Solo lee Historia X10.
    """
    root = Path(run_root)
    allowed = set(allowed_dates) if allowed_dates is not None else None
    names = set(run_names) if run_names is not None else None
    rows_by_date = {}
    for csv_path in sorted(root.rglob("score_trade_result_*_NY.csv")):
        parent = csv_path.parent.name
        if not parent.startswith("X10_"):
            continue
        if names is not None and parent not in names:
            continue
        match = re.search(r"(\d{4}-\d{2}-\d{2})", csv_path.name)
        if not match:
            continue
        date_key = match.group(1)
        if allowed is not None and date_key not in allowed:
            continue
        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
                row = next(iter(csv.DictReader(fh)), None)
        except Exception:
            continue
        if not row:
            continue
        rows_by_date[date_key] = row

    daily = []
    decided_ticks = []
    month_counts = {}
    for date_key in sorted(rows_by_date):
        row = rows_by_date[date_key]
        ticks = _parse_result_ticks(row.get("result TP SL BE"))
        month = date_key[:7]
        if ticks is not None:
            decided_ticks.append(ticks)
            month_counts[month] = month_counts.get(month, 0) + 1
        wins = [value for value in decided_ticks if value > 0]
        losses = [value for value in decided_ticks if value < 0]
        gross_loss = -sum(losses)
        daily.append({
            "date": date_key,
            "result": str(row.get("Result_Label") or "N/A").strip() or "N/A",
            "ticks": ticks,
            "mae": _parse_number(row.get("MAE_ticks")),
            "mfe": _parse_number(row.get("MFE_ticks")),
            "initial_sl_ticks": _parse_number(row.get("Initial_SL_ticks")),
            "initial_tp_ticks": _parse_number(row.get("Initial_TP_ticks")),
            "initial_rr": _parse_number(row.get("Initial_RR")),
            "final_sl_ticks": _parse_number(row.get("Final_SL_ticks")),
            "final_tp_ticks": _parse_number(row.get("Final_TP_ticks")),
            "stop_was_moved": _parse_bool(row.get("Stop_Was_Moved")),
            "target_was_moved": _parse_bool(row.get("Target_Was_Moved")),
            "target_modification_reason": str(row.get("Target_Modification_Reason") or "").strip(),
            "exit_reason": str(row.get("Exit_Reason") or row.get("Result_Label") or "N/A").strip(),
            "wr": (100.0 * len(wins) / len(decided_ticks)) if decided_ticks else None,
            "pf": (sum(wins) / gross_loss) if gross_loss > 0 else (float("inf") if wins else None),
            "month": month,
            "month_trades": month_counts.get(month, 0),
        })
    return daily


def _send_daily_metrics_report(results_folder, credentials, daily):
    """Envia el detalle fecha por fecha en bloques seguros para Telegram."""
    if not daily:
        return
    chunks = []
    current = ["OR ABSORTION TEST | RESULTADOS POR FECHA"]
    for item in daily:
        mae = "N/A" if item["mae"] is None else f'{item["mae"]:.1f}'
        mfe = "N/A" if item["mfe"] is None else f'{item["mfe"]:.1f}'
        wr = "N/A" if item["wr"] is None else f'{item["wr"]:.1f}%'
        pf_value = item["pf"]
        pf = "N/A" if pf_value is None else ("INF" if pf_value == float("inf") else f"{pf_value:.2f}")
        ticks = "N/A" if item["ticks"] is None else f'{item["ticks"]:+.0f}t'
        initial_tp = "N/A" if item["initial_tp_ticks"] is None else f'{item["initial_tp_ticks"]:.0f}'
        initial_sl = "N/A" if item["initial_sl_ticks"] is None else f'{item["initial_sl_ticks"]:.0f}'
        initial_rr = "N/A" if item["initial_rr"] is None else f'{item["initial_rr"]:.2f}'
        management = ""
        if item["target_was_moved"]:
            final_tp = "N/A" if item["final_tp_ticks"] is None else f'{item["final_tp_ticks"]:.0f}'
            reason = item["target_modification_reason"] or "NO_REGISTRADO"
            management = f" | TP dinámico {initial_tp}->{final_tp} ({reason})"
        if item["stop_was_moved"]:
            final_sl = "N/A" if item["final_sl_ticks"] is None else f'{item["final_sl_ticks"]:.0f}'
            management += f" | SL dinámico {initial_sl}->{final_sl}"
        line = (
            f'{item["date"]} | TPi {initial_tp} SLi {initial_sl} RRi {initial_rr}{management} | '
            f'{item["exit_reason"]} {ticks} | MAE {mae} | MFE {mfe} | '
            f'WR {wr} | PF {pf} | Trades {item["month"]}: {item["month_trades"]}'
        )
        if sum(len(value) + 1 for value in current) + len(line) > 3800:
            chunks.append("\n".join(current))
            current = ["OR ABSORTION TEST | RESULTADOS POR FECHA (cont.)"]
        current.append(line)
    chunks.append("\n".join(current))
    for message in chunks:
        message_id = _send_message(credentials[0], credentials[1], message)
        if message_id is not None:
            with open(os.path.join(results_folder, TELEGRAM_MESSAGE_IDS_FILE), "a", encoding="utf-8") as fh:
                fh.write(f"{message_id}\n")


def simulate_lucidpro_150k(daily, contracts=6, tick_value=5.0):
    """Simula las reglas publicadas para LucidPro Eval 150k.

    MLL: trailing EOD de $4,500, bloqueado en $150,100 despues de cerrar por
    encima de $154,600. DLL $2,700 es soft breach. El MAE aproxima el peor
    equity intradia de cada trade, por lo que el chequeo es mas conservador
    que usar solamente el PnL cerrado.
    """
    start = 150000.0
    target = 159000.0
    equity = start
    peak_eod = start
    mll_floor = start - 4500.0
    locked = False
    dll_hits = []
    breach = None
    pass_date = None
    trading_days = 0
    for item in daily:
        if item["ticks"] is None:
            continue
        trading_days += 1
        pnl = item["ticks"] * tick_value * contracts
        mae_usd = (item["mae"] or 0.0) * tick_value * contracts
        worst_intraday = equity - mae_usd
        if worst_intraday <= mll_floor and breach is None:
            breach = (item["date"], worst_intraday, mll_floor)
            break
        if pnl <= -2700.0:
            dll_hits.append(item["date"])
        equity += pnl
        peak_eod = max(peak_eod, equity)
        if peak_eod > 154600.0:
            locked = True
            mll_floor = 150100.0
        elif not locked:
            mll_floor = peak_eod - 4500.0
        if equity >= target and pass_date is None:
            pass_date = item["date"]
            break
    return {
        "status": "BREACH" if breach else ("PASS" if pass_date else "NO PASS"),
        "equity": equity,
        "pnl": equity - start,
        "mll_floor": mll_floor,
        "breach": breach,
        "pass_date": pass_date,
        "dll_hits": dll_hits,
        "trading_days": trading_days,
        "contracts": contracts,
    }


def _format_stats_line(stats):
    pf = stats.get("pf")
    pf_text = f"{pf:.2f}" if pf is not None else "inf"
    expectancy = stats.get("expectancy_ticks")
    profit = stats.get("profit_ticks")
    suffix = ""
    if expectancy is not None and profit is not None:
        suffix = f" | Exp {expectancy:+.2f} ticks | Net {profit:+.0f} ticks"
    brackets = stats.get("initial_brackets") or {}
    bracket_text = ", ".join(
        f"TP{tp:g}/SL{sl:g} x{count}"
        for (tp, sl), count in sorted(brackets.items())
    ) or "N/A"
    min_rr = stats.get("min_initial_rr")
    rr_text = "N/A" if min_rr is None else f"{min_rr:.2f}"
    avg_win = stats.get("average_win_ticks")
    avg_loss = stats.get("average_loss_ticks")
    average_text = (
        f" | AvgWin {avg_win:+.2f} | AvgLoss {avg_loss:+.2f}"
        if avg_win is not None and avg_loss is not None else ""
    )
    return (
        f"WR {stats['winrate']:.0f}% | PF {pf_text} | "
        f"Plan inicial [{bracket_text}] | RR mínimo {rr_text} | "
        f"racha max ganadas {stats['max_consec_wins']} | "
        f"racha max perdidas {stats['max_consec_losses']} | "
        f"n={stats['trades']} trades"
        f"{suffix}{average_text}"
    )


def _date_iso_from_ddmmyyyy(date_text):
    day, month, year = date_text.split("/")
    return f"{year}-{month}-{day}"


def _find_replay_run_root(results_folder):
    """Encuentra la carpeta de corrida que contiene Historia X10."""
    root = Path(results_folder)
    direct_has_runs = any(
        child.is_dir() and child.name.startswith("X10_")
        for child in root.iterdir()
    ) if root.exists() else False
    if direct_has_runs:
        return root

    candidates = [
        root / "visual_tests" / "04_run_replay_score_trade_results_dst_2025_2026_runs",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return root


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


def _format_global_timer(eta_seconds, final=False):
    if final:
        return "00:00:00"
    if eta_seconds is None:
        return "CALCULANDO"
    seconds = max(0, int(eta_seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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
    pnl_usd=None,
    contracts=None,
    stats=None,
    hypothesis_status=None,
):
    """Manda un mensaje de progreso de Historia X10 únicamente."""
    credentials = _read_credentials(results_folder)
    if credentials is None:
        return False

    synced = global_synced if global_synced is not None else (global_done or 0)

    if goal:
        message = "\n".join(
            [
                f"OR ABSORTION TEST | META ALCANZADA ({run_label})",
                f"{synced}/{global_target} sesiones Historia X10 completas. Replay detenido.",
                "Replay X1: DESHABILITADO",
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
        f"OR ABSORTION TEST | {header} ({run_label})",
        "Modo: Historia X10 únicamente",
        "Replay X1: DESHABILITADO",
        f"Fase: ETAPA {stage_index:02d}/{stage_total:02d} - {stage_label}",
    ]
    if stage_period:
        lines.append(f"Periodo: {stage_period}")
    # Avance de la etapa actual (fechas completas, no pasadas internas X1/X10).
    if total:
        lines.append(f"Etapa: {done}/{total} fechas completas")
        lines.append(
            "Corridas de esta ejecucion: "
            f"OK {passed} | fallas {failed} | saltadas {skipped}"
        )
    # Stats acumuladas de la corrida (WR/PF/TP/SL/rachas).
    if stats:
        lines.append(_format_stats_line(stats))
    if hypothesis_status:
        lines.append(str(hypothesis_status))
    # Progreso TOTAL hacia la meta (sincronizadas X1==X10), no parcial por etapa.
    if global_target:
        missing = max(global_target - synced, 0)
        lines.append(
            f"Progreso total: {synced}/{global_target} sesiones X10 completas "
            f"(faltan {missing})"
        )
    if global_done is not None:
        lines.append(f"Recolectadas X10: {global_done}")
    if pnl_usd is not None:
        line = f"PnL acumulado: ${pnl_usd:,.0f}"
        if contracts:
            line += f" | {contracts} contratos"
        lines.append(line)
    lines.append(
        f"Tiempo restante corrida: {_format_global_timer(eta_seconds, final=final)}"
        + (f" ({remaining} corridas pendientes)" if remaining and remaining > 0 else "")
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


def _load_pnl_rows(pnl_log_path):
    """Lee rows del CSV de trades. Retorna lista de dicts."""
    try:
        p = Path(pnl_log_path)
        if not p.exists():
            return []
        with open(p, "r", encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def get_current_equity(pnl_log_path):
    """Lee el último challenge_equity del CSV. Retorna float o None."""
    rows = _load_pnl_rows(pnl_log_path)
    if not rows:
        return None
    last = rows[-1]
    try:
        return float(last.get("challenge_equity") or last.get("equity") or "")
    except (ValueError, TypeError):
        return None


def build_equity_chart(pnl_log_path, target=9000.0, output_path=None):
    """Genera PNG de equity curve. Retorna path o None si matplotlib no disponible."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    rows = _load_pnl_rows(pnl_log_path)
    if not rows:
        return None

    equities = []
    dates_lbl = []
    for r in rows:
        raw = r.get("challenge_equity") or r.get("equity") or ""
        try:
            equities.append(float(raw))
            dates_lbl.append(r.get("date", "")[:10])
        except (ValueError, TypeError):
            pass

    if not equities:
        return None

    xs = list(range(len(equities)))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, equities, color="#00BFFF", linewidth=1.5, label="Equity")
    ax.axhline(y=0, color="#555", linewidth=0.8, linestyle="--")
    ax.axhline(y=target, color="#00FF88", linewidth=1.0, linestyle="--", label=f"Target ${target:,.0f}")
    ax.axhline(y=-4500, color="#FF4444", linewidth=1.0, linestyle="--", label="MaxDD -$4,500")
    ax.fill_between(xs, equities, 0, where=[e >= 0 for e in equities], alpha=0.15, color="#00BFFF")
    ax.fill_between(xs, equities, 0, where=[e < 0 for e in equities], alpha=0.15, color="#FF4444")

    if len(dates_lbl) >= 2:
        tick_step = max(1, len(xs) // 8)
        tick_xs = xs[::tick_step]
        ax.set_xticks(tick_xs)
        ax.set_xticklabels([dates_lbl[i] for i in tick_xs], rotation=30, ha="right", fontsize=7)

    last_eq = equities[-1]
    peak = max(equities)
    dd = max(0.0, peak - last_eq)
    ax.set_title(
        f"Equity Curve — ${last_eq:+,.0f} | DD ${dd:,.0f} | {len(equities)} trades",
        fontsize=10,
    )
    ax.set_ylabel("PnL ($)")
    ax.legend(fontsize=8)
    ax.set_facecolor("#111111")
    fig.patch.set_facecolor("#1a1a1a")
    ax.tick_params(colors="#cccccc")
    ax.yaxis.label.set_color("#cccccc")
    ax.title.set_color("#ffffff")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444444")
    plt.tight_layout()

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        output_path = tmp.name
        tmp.close()

    fig.savefig(output_path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def send_equity_chart(results_folder, pnl_log_path, target=9000.0, caption=""):
    """Genera y envia equity curve chart a Telegram."""
    chart_path = build_equity_chart(pnl_log_path, target=target)
    if chart_path is None:
        print("Telegram chart: sin datos o matplotlib no instalado.")
        return False
    try:
        ok = send_photo(results_folder, chart_path, caption=caption)
    finally:
        try:
            os.unlink(chart_path)
        except OSError:
            pass
    return ok


def send_challenge_passed(results_folder, equity, target=9000.0, account_label="$150k"):
    """Envia aviso de cuenta pasada. Idempotente via flag file."""
    flag = Path(results_folder) / "telegram_challenge_passed.flag"
    if flag.exists():
        return True

    msg = "\n".join([
        f"EW Opening Range | CHALLENGE PASADO ({account_label})",
        f"Equity: ${equity:,.0f}  (Target: ${target:,.0f})",
        "Ya pasaste la cuenta! Retira / siguiente challenge.",
    ])
    ok = send_text(results_folder, msg)
    if ok:
        flag.touch()
    return ok


def check_and_notify_challenge(results_folder, pnl_log_path, target=9000.0, account_label="$150k"):
    """Lee equity del CSV; si >= target envia aviso + equity chart."""
    rows = _load_pnl_rows(pnl_log_path)
    if not rows:
        return
    last = rows[-1]
    try:
        equity = float(last.get("challenge_equity") or last.get("equity") or "0")
    except (ValueError, TypeError):
        return
    if equity >= target:
        send_challenge_passed(results_folder, equity, target, account_label)
        send_equity_chart(
            results_folder,
            pnl_log_path,
            target=target,
            caption=f"Equity curve al pasar la cuenta — {len(rows)} trades",
        )


def send_run_summary(results_folder, dates, failed_dates=None, run_label="Replay"):
    credentials = _read_credentials(results_folder)
    if credentials is None:
        print("Telegram resumen: faltan credenciales.")
        return False

    run_root = _find_replay_run_root(results_folder)
    allowed_dates = [_date_iso_from_ddmmyyyy(d) for d in dates]
    run_stats = compute_run_stats(
        run_root,
        allowed_dates=allowed_dates,
        run_names={"X10_R1"},
    )
    daily_metrics = collect_daily_metrics(
        run_root,
        allowed_dates=allowed_dates,
        run_names={"X10_R1"},
    )

    if run_stats:
        win_rate = run_stats["winrate"]
        profit_factor = run_stats["pf"] if run_stats["pf"] is not None else "INF"
        net_ticks = run_stats["profit_ticks"]
        wins_count = run_stats["wins"]
        losses_count = run_stats["losses"]
        break_evens_count = run_stats["break_evens"]
        results_count = run_stats["trades"]
        time_over_count = run_stats.get("time_over", 0)
    else:
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
        wins_count = len(wins)
        losses_count = len(losses)
        break_evens_count = len(break_evens)
        results_count = len(results)
        time_over_count = 0

    failed_count = len(failed_dates or [])

    win_rate_text = f"{win_rate:.2f}%" if win_rate is not None else "N/A"
    if isinstance(profit_factor, float):
        profit_factor_text = f"{profit_factor:.2f}"
    else:
        profit_factor_text = profit_factor or "N/A"

    monthly_lines = []
    for month in sorted({item["month"] for item in daily_metrics}):
        month_rows = [item for item in daily_metrics if item["month"] == month and item["ticks"] is not None]
        month_ticks = [item["ticks"] for item in month_rows]
        month_wins = [value for value in month_ticks if value > 0]
        month_losses = [value for value in month_ticks if value < 0]
        month_pf = sum(month_wins) / -sum(month_losses) if month_losses else (float("inf") if month_wins else None)
        month_wr = 100.0 * len(month_wins) / len(month_ticks) if month_ticks else None
        pf_text = "N/A" if month_pf is None else ("INF" if month_pf == float("inf") else f"{month_pf:.2f}")
        wr_text = "N/A" if month_wr is None else f"{month_wr:.1f}%"
        monthly_lines.append(f"{month}: {len(month_ticks)} trades | WR {wr_text} | PF {pf_text} | Net {sum(month_ticks):+.0f}t")

    tick_value = 5.0
    contracts = 6
    starting_balance = 150000.0
    final_equity = starting_balance + net_ticks * tick_value * contracts
    lucid = simulate_lucidpro_150k(daily_metrics, contracts=contracts, tick_value=tick_value)
    maes = [item["mae"] for item in daily_metrics if item["mae"] is not None]
    mfes = [item["mfe"] for item in daily_metrics if item["mfe"] is not None]
    expectancy = (net_ticks / results_count) if results_count else 0.0
    average_win = run_stats.get("average_win_ticks") if run_stats else None
    average_loss = run_stats.get("average_loss_ticks") if run_stats else None
    bracket_counts = run_stats.get("initial_brackets", {}) if run_stats else {}
    bracket_text = ", ".join(
        f"TP {tp:g}/SL {sl:g} (x{count})"
        for (tp, sl), count in sorted(bracket_counts.items())
    ) or "N/A"
    min_initial_rr = run_stats.get("min_initial_rr") if run_stats else None
    rr_text = "N/A" if min_initial_rr is None else f"{min_initial_rr:.2f}"
    dynamic_target_moves = run_stats.get("dynamic_target_moves", 0) if run_stats else 0
    target_reasons = run_stats.get("target_modification_reasons", {}) if run_stats else {}
    target_reason_text = ", ".join(
        f"{reason} (x{count})" for reason, count in sorted(target_reasons.items())
    ) or "ninguna"
    message = "\n".join(
        [
            f"OR ABSORTION TEST | Corrida terminada ({run_label})",
            "Modo: Historia X10 únicamente",
            "Replay X1: DESHABILITADO",
            "Resumen CRUDO X10:",
            f"Plan inicial: {bracket_text}",
            f"RR inicial mínimo: {rr_text}",
            f"Targets modificados dinámicamente: {dynamic_target_moves} | {target_reason_text}",
            f"WR: {win_rate_text}",
            f"PF: {profit_factor_text}",
            f"Expectancy: {expectancy:+.2f} ticks/trade",
            f"Average Win: {(average_win if average_win is not None else 0):+.2f} ticks",
            f"Average Loss: {(average_loss if average_loss is not None else 0):+.2f} ticks",
            f"Wins: {wins_count} | Losses: {losses_count} | BE: {break_evens_count}",
            f"Net ticks: {net_ticks:+.0f}",
            f"Trades: {results_count} | TIME_OVER: {time_over_count}",
            f"MAE prom/max: {(sum(maes)/len(maes)) if maes else 0:.2f}/{max(maes) if maes else 0:.2f} ticks",
            f"MFE prom/max: {(sum(mfes)/len(mfes)) if mfes else 0:.2f}/{max(mfes) if mfes else 0:.2f} ticks",
            f"Cuenta 150k: ${starting_balance:,.0f} -> ${final_equity:,.0f} | PnL ${final_equity-starting_balance:+,.0f}",
            f"LucidPro 150k: {lucid['status']} | equity ${lucid['equity']:,.0f} | MLL ${lucid['mll_floor']:,.0f}",
            f"Objetivo $9,000 | MLL $4,500 EOD | DLL $2,700 | {contracts}/10 minis | dias {lucid['trading_days']}",
            f"Fechas esperadas: {len(dates)} | Errores: {failed_count}",
            f"Fuente: {run_root}",
        ]
    )
    if monthly_lines:
        message += "\n\nTrades por mes:\n" + "\n".join(monthly_lines)
    if lucid["pass_date"]:
        message += f"\n\nPASS alcanzado: {lucid['pass_date']}"
    if lucid["breach"]:
        date_key, worst_equity, floor = lucid["breach"]
        message += f"\n\nBREACH MLL: {date_key} | peor equity ${worst_equity:,.0f} <= ${floor:,.0f}"
    if lucid["dll_hits"]:
        message += "\nDLL soft hits: " + ", ".join(lucid["dll_hits"])
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
        _send_daily_metrics_report(results_folder, credentials, daily_metrics)
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
