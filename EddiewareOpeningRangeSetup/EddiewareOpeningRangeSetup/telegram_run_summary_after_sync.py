import csv
import io
import json
import os
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
    pnl_usd=None,
    contracts=None,
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
    if pnl_usd is not None:
        line = f"PnL acumulado: ${pnl_usd:,.0f}"
        if contracts:
            line += f" | {contracts} contratos"
        lines.append(line)
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
