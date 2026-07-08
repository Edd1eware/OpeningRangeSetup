"""Recorre fechas en Replay X10 con el Execution Manager (strategy) ACTIVO.

El exporter publica la senal A+ Speed -> la ChartStrategy entra y gestiona. Este
runner solo MANEJA el Replay (configura rango, Play, espera, Stop) reusando el
motor existente. Los trades reales los coloca la estrategia en ATAS.

Requisitos antes de correr:
  1. ATAS abierto, chart con: Exporter + Visual + Strategy en "Started".
  2. Replay visible y al frente. Manos fuera del mouse/teclado.

Uso:
  python 06_run_strategy_replay.py              # solo las fechas A+ Speed (39, donde opera)
  python 06_run_strategy_replay.py --all        # todas las sesiones sincronizadas
  python 06_run_strategy_replay.py --dates 2026-05-15 2026-06-23
"""

import argparse
import csv
import re
import time
from pathlib import Path

import replay_sync_runner_common_after_sync as rs
import telegram_run_summary_after_sync as telegram
import atas_process_guard
from progress import ProgressBar

LADDER_ROOT = (
    rs.RESULTS_FOLDER / "visual_tests" / "sync_ladder_runs" / "sync_v11_ladder_001_resume"
)
OUTPUT = rs.RESULTS_FOLDER / "visual_tests" / "strategy_tester_results"
OPER = rs.OPERATIVA_COMPARISON_FIELDS


def _row(path):
    try:
        return next(csv.DictReader(open(path, encoding="utf-8-sig")), None)
    except Exception:
        return None


# Canal en disco Exporter->Strategy. Mismo path que StrategySignalFile.cs.
SIGNAL_FILE = rs.RESULTS_FOLDER / "pending_strategy_signal.txt"
MIN_RANGE_SIGNAL = 140  # FROZEN EXECUTION FILTER (mismo universo que opera la strategy)


def prewrite_signal(date_str):
    """Pre-escribe pending_strategy_signal.txt desde el score CSV canonico ANTES
    del replay. Mata la race Exporter/Strategy: cuando la strategy abre su ventana
    09:30-09:40, la senal PENDING ya esta en disco (no depende del timing del
    exporter dentro del replay). El exporter la re-escribe igual (mismo PENDING) y
    _enteredToday evita doble entrada. Formato: date,side,entry,sl,isAPlus,bar,PENDING.
    Devuelve True si escribio una senal valida (fecha con trade en el universo)."""
    # La raiz es mutable: run_one_date mueve/restaura esos CSV durante cada replay.
    # Para un recorrido largo, leer primero el X10 congelado del ladder canonico.
    canonical = sorted(
        LADDER_ROOT.glob(f"*/X10_R1/score_trade_result_{date_str}_NY.csv")
    )
    src = (canonical[0] if canonical else
           rs.RESULTS_FOLDER / f"score_trade_result_{date_str}_NY.csv")
    r = _row(src)
    if not r:
        return False
    try:
        if int(float(r.get("range", 0) or 0)) < MIN_RANGE_SIGNAL:
            return False  # fuera del universo congelado -> no-trade, no pre-escribe
        side = (r.get("Side") or "").strip()
        entry = (r.get("Entry_price") or "").strip()
        if not side or not entry:
            return False
        sl = (r.get("SL_price") or entry).strip() or entry
        is_aplus = "1" if str(r.get("APlus_Speed", "")).strip().upper() == "TRUE" else "0"
        bar = (r.get("EntryBar") or "0").strip() or "0"
        line = f"{date_str},{side},{entry},{sl},{is_aplus},{bar},PENDING"
        SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        SIGNAL_FILE.write_text(line, encoding="utf-8")
        print(f"Signal pre-escrita: {line}")
        return True
    except Exception as exc:
        print(f"prewrite_signal({date_str}) fallo: {exc}")
        return False


def synced_dates(aplus_only):
    """Fechas sincronizadas (X1==X10). Si aplus_only, solo las A+ Speed."""
    out = []
    for x1 in LADDER_ROOT.glob("*/X1_R1/score_trade_result_*_NY.csv"):
        d = re.search(r"(\d{4}-\d{2}-\d{2})", x1.name).group(1)
        if d in out:
            continue
        x10 = x1.parent.parent / "X10_R1" / x1.name
        if not x10.exists():
            continue
        r1, r10 = _row(x1), _row(x10)
        if not r1 or not r10:
            continue
        if not all(str(r1.get(f, "") or "").strip() == str(r10.get(f, "") or "").strip() for f in OPER):
            continue
        if aplus_only and str(r10.get("APlus_Speed", "")).strip().upper() != "TRUE":
            continue
        out.append(d)
    return sorted(set(out))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Todas las sesiones (no solo A+ Speed).")
    parser.add_argument("--dates", nargs="*", help="Fechas especificas YYYY-MM-DD.")
    parser.add_argument("--prepare-only", action="store_true", help="Muestra las fechas sin correr.")
    parser.add_argument("--keep-state", action="store_true",
                        help="NO borra los state files de la strategy (challenge/kill-switch/regime). "
                             "Por defecto se borran para una validacion desde cuenta limpia.")
    parser.add_argument("--kill-orphans", action="store_true",
                        help="Mata instancias ATAS pesadas SIN ventana (huerfanas de sesiones "
                             "previas) antes de correr. Sin este flag solo detecta y avisa. "
                             "Nunca mata una instancia con ventana ni los helpers ligeros.")
    parser.add_argument("--from-date", help="Filtra desde YYYY-MM-DD (inclusive).")
    parser.add_argument("--to-date", help="Filtra hasta YYYY-MM-DD (inclusive).")
    args = parser.parse_args()

    # Preflight de procesos: multiples instancias ATAS pesadas => Exporter/Strategy
    # duplicados peleando por pending_strategy_signal.txt => race y trades fantasma.
    # Por seguridad (el motor de replay podria ser un proceso pesado sin ventana de
    # TU instancia) solo mata con --kill-orphans; por default reporta.
    killed = atas_process_guard.cleanup_orphan_atas(dry_run=not args.kill_orphans)
    if not args.kill_orphans and not killed:
        # dry_run ya reporto; si detecto >1 pesada avisa como bloqueo suave.
        pass

    if args.dates:
        dates = sorted(set(args.dates))
    else:
        dates = synced_dates(aplus_only=not args.all)
    if args.from_date:
        dates = [d for d in dates if d >= args.from_date]
    if args.to_date:
        dates = [d for d in dates if d <= args.to_date]

    print(f"Fechas a recorrer en Replay X10 (estrategia activa): {len(dates)}")
    for d in dates:
        print(" ", d)
    if args.prepare_only:
        print("\nPREPARE-ONLY. No se inicio Replay.")
        return 0

    OUTPUT.mkdir(parents=True, exist_ok=True)

    # Reset de estado de la strategy: challenge_equity/killswitch/regime son solo
    # archivos-espejo en OUTPUT (== TraderLogDir del 02_C). Si quedan viejos entre
    # corridas, el kill-switch arranca con equity/tier/peak contaminados y la
    # validacion no parte de cuenta limpia (ej. regime_state PAUSADO stale).
    # Se borran por defecto; --keep-state los conserva.
    if not args.keep_state:
        for name in ("challenge_equity.txt", "killswitch_state.txt", "regime_state.txt"):
            f = OUTPUT / name
            if f.exists():
                f.unlink()
                print(f"State reseteado: {name} borrado (cuenta limpia).")
        print("NOTA: ResetChallengeState debe estar OFF para acumular equity entre "
              "fechas. El primer reload carga estos archivos ausentes como cuenta limpia.")
        # Balance Telegram desde CERO: sin este borrado, fechas de corridas previas
        # (o muertas a medias) quedan en el JSON y el balance del primer mensaje sale
        # distinto de TelegramStartingBalance ($150k). El exporter lo repuebla por fecha.
        balance_file = rs.RESULTS_FOLDER / "telegram_balance.json"
        if balance_file.exists():
            balance_file.unlink()
            print("telegram_balance.json borrado (balance arranca en $150k).")
        # Borra TODO el historial del bot en el chat antes de arrancar (los >48h
        # no los puede borrar la Bot API; se reportan y la corrida continua).
        telegram.clear_telegram_before_run(rs.RESULTS_FOLDER)

    # Solo X10 (la estrategia opera en X10). force=True -> re-corre cada fecha.
    run_plan = [("X10_R1", "X10", rs.X10_TIMEOUT_SECONDS)]
    # progress_meta -> Telegram con ETA exacto por fecha (mediana de la X10 medida)
    # y alerta de error si fallan varias seguidas. Sin meta de 500 (no aplica).
    trades_log = OUTPUT / "strategy_tester_trades.csv"
    # Reset del log: force=True re-corre todas las fechas y la strategy APPENDEA,
    # asi que se respalda/limpia el log para que el PnL no se duplique.
    if trades_log.exists():
        backup = trades_log.with_name(
            f"strategy_tester_trades_prev_{int(trades_log.stat().st_mtime)}.csv"
        )
        trades_log.replace(backup)
        print(f"Log previo respaldado: {backup.name}")

    # Resetear fechas enviadas por Telegram para que el indicador re-envie por cada trade.
    sent_dates_file = rs.RESULTS_FOLDER / "telegram_sent_dates.txt"
    if sent_dates_file.exists():
        sent_dates_file.unlink()
        print("telegram_sent_dates.txt reseteado (indicador C# re-enviara Telegram por trade).")

    progress_meta = {
        "stage_index": 1,
        "stage_total": 1,
        "stage_label": "Strategy A+Speed replay",
        "stage_period": f"{dates[0]} -> {dates[-1]}" if dates else "",
        "global_target": None,
        "session_roots": None,
        "run_label": "Execution Manager",
        "pnl_log_path": str(trades_log),   # PnL$ + contratos reales en Telegram
    }

    telegram.send_text(
        rs.RESULTS_FOLDER,
        "EW Opening Range | Execution Manager - inicio del recorrido\n"
        f"{len(dates)} fechas en Replay X10 con la estrategia activa.\n"
        "Recibiras ETA por fecha. Si algo se atora, te avisare para reiniciar.",
    )

    sig_file = rs.RESULTS_FOLDER / "pending_strategy_signal.txt"

    def _print_date_summary(date_str, idx, total):
        rows = []
        if trades_log.exists():
            try:
                rows = list(csv.DictReader(open(trades_log, encoding="utf-8-sig")))
            except Exception:
                pass
        sig_status = ""
        if sig_file.exists():
            try:
                sig_status = sig_file.read_text().strip().split(",")[-1]
            except Exception:
                pass
        wins   = sum(1 for r in rows if float(r.get("pnl_usd") or 0) > 0)
        losses = sum(1 for r in rows if float(r.get("pnl_usd") or 0) < 0)
        total_pnl = sum(float(r.get("pnl_usd") or 0) for r in rows)
        contracts = rows[-1].get("contratos") if rows else None
        wr = f"{wins/(wins+losses)*100:.0f}%" if (wins+losses) else "N/A"
        print(
            f"[{idx:>2}/{total}] {date_str} | "
            f"signal={sig_status or 'N/A':<8} | "
            f"trades={len(rows):>2} | wins={wins} losses={losses} WR={wr} | "
            f"PnL=${total_pnl:,.0f}"
        )
        return wins, losses, total_pnl, contracts

    failures = []
    # Progreso GLOBAL hacia Telegram: como run_replay_period corre UNA fecha por
    # llamada, su ETA por-etapa no sirve para el total. Aqui se mide el recorrido
    # completo (transcurrido / fechas hechas x fechas restantes) y se manda barra+ETA.
    total_dates = len(dates)
    run_start = time.time()
    # Barra GLOBAL en consola (stderr): 10 bloques + % + min restantes del recorrido
    # completo. La barra interna de run_replay_period corre con total=1 (una fecha
    # por llamada) y no refleja el avance real.
    bar = ProgressBar(total_dates, label="Recorrido strategy")
    consecutive_fail = 0
    fail_alert_sent = False
    fail_streak = getattr(rs, "REPLAY_FAIL_ALERT_STREAK", 3)
    for i, date in enumerate(dates, 1):
        # Pre-escribe la senal canonica en disco para matar la race Exporter/Strategy.
        expects_strategy_trade = prewrite_signal(date)

        def strategy_trade_closed():
            if not expects_strategy_trade:
                return True
            if not trades_log.exists():
                return False
            try:
                rows = list(csv.DictReader(open(trades_log, encoding="utf-8-sig")))
                return any((r.get("fecha") or "").strip() == date for r in rows)
            except Exception:
                return False

        try:
            _, date_failures = rs.run_replay_period(
                [date],
                output_folder=OUTPUT,
                run_plan=run_plan,
                report_prefix="strategy_replay_test",
                force=True,
                # 09:55 (no 09:50): la strategy hace hardClose a 09:50; se necesitan barras
                # DESPUES para que curPos->0 y dispare OnTradeClosed (log rico + state real).
                # Solo afecta el replay de la strategy, no el canonico DST congelado.
                replay_to_time="09:55",
                # No detener al TP/SL del exporter si la strategy sigue abierta.
                # Para una fecha operable exige tambien su fila rica en el trader-log.
                completion_predicate=strategy_trade_closed,
                # Sin progress_meta: el progreso/ETA GLOBAL se manda aqui abajo, no
                # el parcial de UNA fecha (que siempre daria remaining=0, ETA N/A).
            )
            failures.extend(date_failures)
        except KeyboardInterrupt:
            telegram.send_text(rs.RESULTS_FOLDER, "EW Opening Range | Recorrido CANCELADO (Ctrl+C).")
            _print_date_summary(date, i, len(dates))
            raise
        except Exception as exc:
            telegram.send_text(
                rs.RESULTS_FOLDER,
                "EW Opening Range | ERROR FATAL en el recorrido\n"
                f"{exc}\nREINICIA ATAS/Replay, ventana al frente, y relanza el runner.",
            )
            _print_date_summary(date, i, len(dates))
            raise

        # Alerta de fechas fallidas seguidas (foco perdido / Replay atorado): avisa
        # UNA sola vez para reiniciar ATAS/Replay. Antes lo hacia progress_meta.
        if date_failures:
            consecutive_fail += 1
        else:
            consecutive_fail = 0
        if consecutive_fail >= fail_streak and not fail_alert_sent:
            fail_alert_sent = True
            telegram.send_text(
                rs.RESULTS_FOLDER,
                "EW Opening Range | ERROR EN REPLAY\n"
                f"{consecutive_fail} fechas seguidas fallaron (ultima: {date}).\n"
                "Probable foco perdido o Replay atorado. REINICIA el Replay/ATAS, "
                "trae la ventana al frente y relanza el runner (reanuda los huecos).",
            )

        wins, losses, total_pnl, contracts = _print_date_summary(date, i, len(dates))
        bar.update(i)

        # Progreso GLOBAL + ETA a Telegram (barra 10 bloques, %, balance, restante).
        elapsed = time.time() - run_start
        eta_seconds = (elapsed / i) * (total_dates - i) if i else None
        telegram.send_overall_progress(
            rs.RESULTS_FOLDER,
            done=i,
            total=total_dates,
            date=date,
            elapsed_seconds=elapsed,
            eta_seconds=eta_seconds,
            pnl_usd=total_pnl,
            contracts=contracts,
            wins=wins,
            losses=losses,
        )

    # Nunca fabricar trades desde el score CSV: ese fallback ocultaba una strategy
    # detenida y producia un header corto falso. El unico resultado valido aqui es
    # el log rico escrito por 02_C (challenge_equity/challenge_dd/etc.).

    fail_n = len(failures)
    # PnL real + contratos del log de la estrategia.
    pnl_line = ""
    if trades_log.exists():
        try:
            log_rows = list(csv.DictReader(open(trades_log, encoding="utf-8-sig")))
            if log_rows:
                total_pnl = sum(float(r.get("pnl_usd") or 0) for r in log_rows)
                contracts = log_rows[-1].get("contratos")
                wins = sum(1 for r in log_rows if float(r.get("pnl_usd") or 0) > 0)
                losses = sum(1 for r in log_rows if float(r.get("pnl_usd") or 0) < 0)
                wr = wins / (wins + losses) * 100 if (wins + losses) else 0
                pnl_line = (
                    f"Trades estrategia: {len(log_rows)} | {contracts} contratos | "
                    f"WR {wr:.0f}% | PnL TOTAL ${total_pnl:,.0f}"
                )
        except Exception:
            pass
    msg = [
        "EW Opening Range | Execution Manager - recorrido TERMINADO",
        f"Fechas: {len(dates)} | con problemas: {fail_n}",
    ]
    if pnl_line:
        msg.append(pnl_line)
    if fail_n:
        msg.append("Fechas con error (re-corre solo esas relanzando):")
        msg += [f"- {d} {run}: {reason}" for d, run, reason in failures[:10]]
        if fail_n > 10:
            msg.append(f"... y {fail_n - 10} mas.")
        msg.append("Si muchas fallaron juntas: reinicia el Replay/ATAS.")
    msg.append("Revisa el P&L / trades de la estrategia en ATAS.")
    telegram.send_text(rs.RESULTS_FOLDER, "\n".join(msg))

    print("\nRecorrido terminado. Revisa el P&L / trades de la estrategia en ATAS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
