import argparse
import csv
import json
import math
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from telegram_run_summary_after_sync import clear_telegram_before_run, send_text


PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_FOLDER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)
RUN_DIR = (
    RESULTS_FOLDER
    / "visual_tests"
    / "04_run_replay_score_trade_results_dst_2025_2026_runs"
    / "X10_R1"
)
RUN_LOG = PROJECT_DIR / "dst_2022_2026_reset_run_20260711_093203.log"
STATE_PATH = PROJECT_DIR / "lucid_monitor_state.json"

TICK_VALUE_USD = 5.0
LUCID_TARGET_USD = 9000.0
LUCID_MAX_DD_USD = 4500.0
CHECKPOINT_TRADES = 50
DEFAULT_SLEEP_SECONDS = 30
MC_SIMS = 5000
MC_SEED = 20260711


def fnum(value):
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text or text.upper() in {"OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return None
    if text.startswith("+"):
        text = text[1:]
    try:
        return float(text)
    except ValueError:
        return None


def result_ticks(row):
    value = fnum(row.get("result TP SL BE"))
    if value is not None:
        return value

    label = str(row.get("Result_Label") or "").strip().upper()
    if label == "BE":
        return 0.0
    if label == "TP":
        return abs(fnum(row.get("TP_ticks")) or 0.0)
    if label == "SL":
        return -abs(fnum(row.get("SL_ticks")) or 0.0)
    return None


def quantile(values, q):
    values = sorted(v for v in values if v is not None and not math.isnan(v))
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def load_rows():
    rows = []
    time_over = 0
    for path in sorted(RUN_DIR.glob("score_trade_result_*_NY.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle), None)
        except Exception:
            continue
        if not row:
            continue

        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        row_date = row.get("fecha") or (match.group(1) if match else "")
        label = str(row.get("Result_Label") or "").strip().upper()
        if label == "TIME_OVER":
            time_over += 1

        ticks = result_ticks(row)
        rows.append(
            {
                "date": row_date,
                "ticks": ticks,
                "cvd": str(row.get("Cvd_Pullback_Label") or "").strip(),
                "mfe": fnum(row.get("MFE_ticks")),
                "mae": fnum(row.get("MAE_ticks")),
                "score": fnum(row.get("score total")),
            }
        )
    return rows, time_over


def streaks(values):
    max_w = max_l = cur_w = cur_l = 0
    for value in values:
        if value > 0:
            cur_w += 1
            cur_l = 0
        elif value < 0:
            cur_l += 1
            cur_w = 0
        else:
            cur_w = cur_l = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)
    return max_w, max_l


def pf(values):
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_loss = -sum(losses)
    if gross_loss <= 0:
        return math.inf if sum(wins) > 0 else math.nan
    return sum(wins) / gross_loss


def max_dd(values):
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return dd


def summarize(series):
    values = [value for _, value, _ in series]
    if not values:
        return {}
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    months = sorted({date[:7] for date, _, _ in series if date})
    max_w, max_l = streaks(values)
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "months": len(months),
        "trades_per_month": len(values) / max(len(months), 1),
        "wr": len(wins) / len(values) * 100.0,
        "pf": pf(values),
        "expectancy": sum(values) / len(values),
        "profit": sum(values),
        "dd": max_dd(values),
        "max_w": max_w,
        "max_l": max_l,
    }


def raw_series(rows):
    return [
        (row["date"], row["ticks"], row)
        for row in rows
        if row["ticks"] is not None
    ]


def optimized_series(rows):
    out = []
    for row in rows:
        ticks = row["ticks"]
        mfe = row["mfe"]
        mae = row["mae"]
        if ticks is None or mfe is None or mae is None:
            continue
        if row["cvd"] != "Excelente":
            continue

        # Current robust candidate: cvd=Excelente | TP=100 | SL=40.
        if abs(mae) >= 40.0 or mae >= 40.0:
            sim = -40.0
        elif mfe >= 100.0:
            sim = 100.0
        else:
            sim = ticks
        out.append((row["date"], sim, row))
    return out


def dynamic_usd_series(series):
    scores = [row["score"] for _, _, row in series]
    high_cut = quantile(scores, 0.90)
    low_cut = quantile(scores, 0.30)
    if high_cut is None or low_cut is None:
        high_cut = low_cut = 0.0

    out = []
    counts = {1: 0, 3: 0, 4: 0}
    for date, ticks, row in series:
        score = row["score"]
        contracts = 3
        if score is not None:
            if score >= high_cut:
                contracts = 4
            elif score <= low_cut:
                contracts = 1
        counts[contracts] += 1
        out.append((date, ticks * contracts * TICK_VALUE_USD, row))
    return out, high_cut, low_cut, counts


def usd_series_for_rule(series, rule):
    label, high_pct, low_pct, high_contracts, mid_contracts, low_contracts = rule
    scores = [row["score"] for _, _, row in series]
    high_cut = quantile(scores, 1.0 - high_pct / 100.0) if high_pct > 0 else None
    low_cut = quantile(scores, low_pct / 100.0) if low_pct > 0 else None
    out = []
    counts = {}
    for date, ticks, row in series:
        score = row["score"]
        contracts = mid_contracts
        if score is not None:
            if high_cut is not None and score >= high_cut:
                contracts = high_contracts
            elif low_cut is not None and score <= low_cut:
                contracts = low_contracts
        counts[contracts] = counts.get(contracts, 0) + 1
        out.append((date, ticks * contracts * TICK_VALUE_USD, row))
    return {
        "label": label,
        "series": out,
        "high_cut": high_cut,
        "low_cut": low_cut,
        "counts": counts,
        "avg_contracts": sum(k * v for k, v in counts.items()) / max(sum(counts.values()), 1),
    }


def ladder_rules():
    # Ladder: keep the trade filter stable, increase exposure only when the
    # 6-month Lucid projection needs more expectancy. Contracts never change WR.
    return [
        ("L0 conservador: top10=4c mid=3c bottom30=1c", 10, 30, 4, 3, 1),
        ("L1 menos defensivo: top10=4c mid=3c bottom20=1c", 10, 20, 4, 3, 1),
        ("L2 base: top10=4c mid=3c bottom10=1c", 10, 10, 4, 3, 1),
        ("L3 mas agresivo: top20=4c mid=3c bottom10=1c", 20, 10, 4, 3, 1),
        ("L4 concentrado: top30=4c mid=3c bottom10=1c", 30, 10, 4, 3, 1),
        ("L5 fijo 3c", 0, 0, 3, 3, 3),
        ("L6 top20=4c resto=3c", 20, 0, 4, 3, 3),
        ("L7 top40=4c resto=3c", 40, 0, 4, 3, 3),
    ]


def choose_ladder(series, trades_per_month):
    candidates = []
    for rule in ladder_rules():
        candidate = usd_series_for_rule(series, rule)
        usd_values = [value for _, value, _ in candidate["series"]]
        lucid = lucid_monte_carlo(usd_values, trades_per_month)
        candidate["lucid"] = lucid
        candidate["score"] = (
            lucid["pass_pct"]
            - 1.5 * lucid["bust_pct"]
            + min(lucid["final_mean"] / LUCID_TARGET_USD, 2.0) * 10.0
            - max(lucid["dd_95"] - LUCID_MAX_DD_USD, 0.0) / 500.0
        )
        candidate["passes_gate"] = (
            lucid["final_mean"] >= LUCID_TARGET_USD
            and lucid["pass_pct"] >= 25.0
            and lucid["bust_pct"] <= 25.0
            and lucid["dd_95"] <= LUCID_MAX_DD_USD
        )
        candidates.append(candidate)

    gated = [c for c in candidates if c["passes_gate"]]
    if gated:
        return sorted(gated, key=lambda c: (c["avg_contracts"], -c["lucid"]["bust_pct"]))[0], candidates
    return sorted(candidates, key=lambda c: c["score"], reverse=True)[0], candidates


def block_sample(rng, values, horizon, block=8):
    sampled = []
    if not values:
        return sampled
    while len(sampled) < horizon:
        start = rng.randrange(len(values))
        sampled.extend(values[start : min(start + block, len(values))])
    return sampled[:horizon]


def lucid_monte_carlo(usd_values, trades_per_month, months=6, sims=MC_SIMS):
    if not usd_values or trades_per_month <= 0:
        return {
            "horizon_trades": 0,
            "pass_pct": 0.0,
            "bust_pct": 0.0,
            "timeout_pct": 100.0,
            "final_mean": 0.0,
            "dd_95": 0.0,
        }

    horizon = max(1, int(round(trades_per_month * months)))
    rng = random.Random(MC_SEED + len(usd_values) + horizon)
    passed = busted = timeout = 0
    finals = []
    dds = []
    for _ in range(sims):
        seq = block_sample(rng, usd_values, horizon)
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        status = "timeout"
        for pnl in seq:
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
            if max_drawdown >= LUCID_MAX_DD_USD:
                status = "bust"
                break
            if equity >= LUCID_TARGET_USD:
                status = "pass"
                break
        finals.append(equity)
        dds.append(max_drawdown)
        passed += status == "pass"
        busted += status == "bust"
        timeout += status == "timeout"

    dds_sorted = sorted(dds)
    return {
        "horizon_trades": horizon,
        "pass_pct": passed / sims * 100.0,
        "bust_pct": busted / sims * 100.0,
        "timeout_pct": timeout / sims * 100.0,
        "final_mean": sum(finals) / len(finals),
        "dd_95": dds_sorted[int(0.95 * (len(dds_sorted) - 1))],
    }


def fmt(value, digits=2, suffix="", signed=False):
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "N/A"
    if math.isinf(number):
        return "inf"
    sign = "+" if signed else ""
    return f"{number:{sign}.{digits}f}{suffix}"


def fmt_money(value, signed=False):
    sign = "+" if signed else ""
    return f"${float(value):{sign},.0f}"


def latest_progress():
    if not RUN_LOG.exists():
        return ""
    text = RUN_LOG.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r"\[X10_R1\s+(\d+)/(\d+)\]\s+(\d{4}-\d{2}-\d{2})", text)
    if not matches:
        return ""
    done, total, date_text = matches[-1]
    return f"X10_R1 {done}/{total} | fecha actual {date_text}"


def runner_alive():
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.Name -eq 'python.exe' -and "
                    "$_.CommandLine -like '*04_run_replay_score_trade_results_dst_2025_2026_after_sync.py*' } | "
                    "Select-Object -First 1 -ExpandProperty ProcessId"
                ),
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return bool(completed.stdout.strip())
    except Exception:
        return True


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def evaluate_potential(opt_stats, lucid):
    if not opt_stats:
        return "SIN_DATOS", "Aun no hay suficientes trades optimizados."

    weak_reasons = []
    if opt_stats["trades"] >= 100 and opt_stats["wr"] < 60:
        weak_reasons.append("WR optimizado < 60%")
    if opt_stats["pf"] < 1.80:
        weak_reasons.append("PF optimizado < 1.80")
    if opt_stats["expectancy"] <= 0:
        weak_reasons.append("expectancy <= 0")
    if lucid["final_mean"] < LUCID_TARGET_USD:
        weak_reasons.append("profit esperado 6m < $9k")
    if lucid["pass_pct"] < 25:
        weak_reasons.append("probabilidad de pass 6m < 25%")
    if lucid["bust_pct"] > 25:
        weak_reasons.append("riesgo de bust 6m > 25%")

    if not weak_reasons:
        return "TIENE_POTENCIAL", "Mantener corrida."
    return "DEBIL", "; ".join(weak_reasons)


def build_message(checkpoint):
    rows, time_over = load_rows()
    raw = raw_series(rows)
    opt = optimized_series(rows)
    raw_stats = summarize(raw)
    opt_stats = summarize(opt)
    ladder, ladder_candidates = choose_ladder(
        opt,
        opt_stats.get("trades_per_month", 0.0) if opt_stats else 0.0,
    )
    lucid = ladder["lucid"]
    status, reason = evaluate_potential(opt_stats, lucid)

    raw_pf = raw_stats.get("pf") if raw_stats else None
    opt_pf = opt_stats.get("pf") if opt_stats else None
    lines = [
        f"EW Opening Range | Monitor Lucid 150k ({checkpoint} trades)",
        "Telegram limpiado antes de este checkpoint.",
        latest_progress() or f"Eventos CSV: {len(rows)}",
        f"Eventos CSV: {len(rows)} | TIME_OVER: {time_over}",
        "",
        "CRUDO X10:",
        (
            f"Trades {raw_stats.get('trades', 0)} | "
            f"Trades/mes {fmt(raw_stats.get('trades_per_month'))} | "
            f"WR {fmt(raw_stats.get('wr'), suffix='%')} | "
            f"PF {fmt(raw_pf)} | "
            f"Racha W/L {raw_stats.get('max_w', 0)}/{raw_stats.get('max_l', 0)}"
        ),
        "",
        "OPTIMIZADO OBJETIVO:",
        "cvd=Excelente | TP=100 | SL=40",
        (
            f"Trades {opt_stats.get('trades', 0)} | "
            f"Trades/mes {fmt(opt_stats.get('trades_per_month'))} | "
            f"WR {fmt(opt_stats.get('wr'), suffix='%')} | "
            f"PF {fmt(opt_pf)} | "
            f"Exp {fmt(opt_stats.get('expectancy'), suffix=' ticks', signed=True)} | "
            f"Net {fmt(opt_stats.get('profit'), digits=0, suffix=' ticks', signed=True)} | "
            f"Racha W/L {opt_stats.get('max_w', 0)}/{opt_stats.get('max_l', 0)}"
        ),
        "",
        "LUCID 150K 6 MESES (sizing 1/3/4):",
        ladder["label"],
        (
            f"Pass {fmt(lucid['pass_pct'], suffix='%')} | "
            f"Bust {fmt(lucid['bust_pct'], suffix='%')} | "
            f"Profit esperado {fmt_money(lucid['final_mean'], signed=True)} | "
            f"DD95 -{fmt_money(lucid['dd_95'])} | "
            f"Horizonte {lucid['horizon_trades']} trades"
        ),
        (
            f"Cortes score: high {fmt(ladder['high_cut'])} / low {fmt(ladder['low_cut'])} | "
            f"avg {fmt(ladder['avg_contracts'])}c | "
            + " ".join(
                f"c{contracts}={count}"
                for contracts, count in sorted(ladder["counts"].items())
            )
        ),
        f"Ladder gate: {'OK' if ladder['passes_gate'] else 'AUN NO'} | candidatos {len(ladder_candidates)}",
        "",
        f"Decision: {status}",
        reason,
    ]
    if status == "DEBIL":
        lines.extend(
            [
                "",
                "Accion recomendada: optimizar partial/final antes de tocar live.",
                "Loop activo: reevalua y vuelve a escalar ladder cada 50 trades.",
                "No reinicio ATAS automaticamente mientras la corrida siga escribiendo bien.",
            ]
        )
    return "\n".join(lines), raw_stats.get("trades", 0) if raw_stats else 0


def notify_checkpoint(checkpoint):
    message, _ = build_message(checkpoint)
    clear_telegram_before_run(str(RESULTS_FOLDER))
    return send_text(str(RESULTS_FOLDER), message)


def run_daemon(sleep_seconds):
    state = load_state()
    rows, _ = load_rows()
    current_trades = len(raw_series(rows))
    if "next_checkpoint" not in state:
        state["next_checkpoint"] = ((current_trades // CHECKPOINT_TRADES) + 1) * CHECKPOINT_TRADES
        save_state(state)

    while True:
        rows, _ = load_rows()
        current_trades = len(raw_series(rows))
        next_checkpoint = int(state.get("next_checkpoint", CHECKPOINT_TRADES))
        if current_trades >= next_checkpoint:
            notify_checkpoint(next_checkpoint)
            while next_checkpoint <= current_trades:
                next_checkpoint += CHECKPOINT_TRADES
            state["next_checkpoint"] = next_checkpoint
            state["last_notified_trades"] = current_trades
            state["last_notified_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_state(state)

        if not runner_alive():
            state["runner_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_state(state)
            break
        time.sleep(sleep_seconds)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--sleep", type=int, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--clear-first", action="store_true")
    args = parser.parse_args()

    if args.once:
        message, current_trades = build_message("actual")
        if args.clear_first:
            clear_telegram_before_run(str(RESULTS_FOLDER))
        send_text(str(RESULTS_FOLDER), message)
        print(f"sent monitor summary at {current_trades}")
        return

    if args.daemon:
        run_daemon(max(5, args.sleep))
        return

    message, _ = build_message("actual")
    print(message)


if __name__ == "__main__":
    main()
