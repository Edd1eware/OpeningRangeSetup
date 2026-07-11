import csv
import math
import re
from datetime import datetime
from pathlib import Path

import numpy as np


BASE_DIR = Path(__file__).resolve().parent
RUN_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1")
OUT_DIR = BASE_DIR / "outputs" / f"edge_optimization_fast_{datetime.now():%Y%m%d_%H%M%S}"

TP_GRID = np.array([20, 30, 40, 50, 60, 80, 100, 120, 150, 200], dtype=float)
SL_GRID = np.array([20, 30, 40, 50, 60, 70, 80, 100], dtype=float)
TICK_VALUE = 5.0
MC_SIMS = 10_000
MC_SEED = 20260711
LOW_CONTRACTS = 1
MID_CONTRACTS = 3
HIGH_CONTRACTS = 4
LUCID_TARGET = 9000.0
LUCID_DD = 4500.0


def fnum(v, default=np.nan):
    text = str(v or "").strip()
    if not text or text.upper() in {"OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return default
    try:
        return float(text.replace("+", ""))
    except ValueError:
        return default


def result_ticks(v):
    text = str(v or "").strip().upper()
    if text == "BE":
        return 0.0
    if text in {"", "OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return 0.0
    return fnum(text, 0.0)


def load_rows():
    rows = []
    event_count = 0
    for path in sorted(RUN_DIR.glob("score_trade_result_*_NY.csv")):
        event_count += 1
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            row = next(csv.DictReader(fh), {})
        date_text = row.get("fecha") or re.search(r"(\d{4}-\d{2}-\d{2})", path.name).group(1)
        is_trade = bool(str(row.get("Side") or "").strip() and str(row.get("Entry_price") or "").strip())
        if not is_trade:
            continue
        rows.append(
            {
                "date": date_text,
                "month": date_text[:7],
                "year": int(date_text[:4]),
                "side": str(row.get("Side") or "").strip(),
                "speed": str(row.get("Speed_Profile") or "Unknown").strip() or "Unknown",
                "cvd": str(row.get("Cvd_Pullback_Label") or "Unknown").strip() or "Unknown",
                "score": fnum(row.get("score total")),
                "or_range": fnum(row.get("range")),
                "mfe": fnum(row.get("MFE_ticks")),
                "mae": fnum(row.get("MAE_ticks")),
                "actual": result_ticks(row.get("result TP SL BE")),
                "range_ok": str(row.get("Range_OK") or "").upper() == "TRUE",
                "body_ok": str(row.get("Body_OK") or "").upper() == "TRUE",
                "volume_ok": str(row.get("Volume_OK") or "").upper() == "TRUE",
                "delta_ok": str(row.get("Delta_OK") or "").upper() == "TRUE",
                "vwap_ok": str(row.get("VWAP_OK") or "").upper() == "TRUE",
                "speed_ok": str(row.get("Speed_OK") or "").upper() == "TRUE",
                "volume_increasing": str(row.get("Volume_Increasing") or "").upper() == "TRUE",
                "delta_with_side": str(row.get("Delta_With_Side") or "").upper() == "TRUE",
                "price_accepted": str(row.get("Price_Accepted_After_Imbalance") or "").upper() == "TRUE",
                "price_rejected": str(row.get("Price_Rejected_After_Imbalance") or "").upper() == "TRUE",
                "aplus_structure": str(row.get("APlus_Structure") or "").upper() == "TRUE",
                "aplus_absorption": str(row.get("APlus_Absorption") or "").upper() == "TRUE",
                "aplus_speed": str(row.get("APlus_Speed") or "").upper() == "TRUE",
            }
        )
    return event_count, rows


def arrays(rows):
    data = {}
    for key in rows[0]:
        data[key] = np.array([r[key] for r in rows])
    q1, q2 = np.nanquantile(data["or_range"].astype(float), [1 / 3, 2 / 3])
    data["or_regime"] = np.where(data["or_range"].astype(float) <= q1, "OR_small", np.where(data["or_range"].astype(float) >= q2, "OR_large", "OR_mid"))
    data["vol_regime"] = np.where(data["or_range"].astype(float) <= q1, "Low_vol", np.where(data["or_range"].astype(float) >= q2, "High_vol", "Mid_vol"))
    return data


def max_dd(x):
    x = np.asarray(x, dtype=float)
    curve = np.cumsum(x)
    peaks = np.maximum.accumulate(np.r_[0.0, curve])[:-1]
    return float(np.max(peaks - curve)) if len(x) else 0.0


def streaks(x):
    mw = ml = cw = cl = 0
    for v in x:
        if v > 0:
            cw += 1
            cl = 0
        elif v < 0:
            cl += 1
            cw = 0
        else:
            cw = cl = 0
        mw = max(mw, cw)
        ml = max(ml, cl)
    return mw, ml


def pf(x):
    x = np.asarray(x, dtype=float)
    gw = x[x > 0].sum()
    gl = -x[x < 0].sum()
    return float(gw / gl) if gl > 0 else (math.inf if gw > 0 else math.nan)


def summary(x, mfe=None, mae=None):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return dict(trades=0, wr=np.nan, pf=np.nan, expectancy=np.nan, profit=0.0, dd=0.0)
    wins = x[x > 0]
    losses = x[x < 0]
    mw, ml = streaks(x)
    avg_loss = -losses.mean() if len(losses) else np.nan
    return {
        "trades": int(len(x)),
        "wr": float((x > 0).mean() * 100),
        "pf": pf(x),
        "expectancy": float(x.mean()),
        "profit": float(x.sum()),
        "dd": max_dd(x),
        "avg_mfe": float(np.nanmean(mfe)) if mfe is not None and len(mfe) else np.nan,
        "avg_mae": float(np.nanmean(mae)) if mae is not None and len(mae) else np.nan,
        "avg_rr": float(wins.mean() / avg_loss) if len(wins) and avg_loss and not np.isnan(avg_loss) else np.nan,
        "std": float(x.std(ddof=1)) if len(x) > 1 else np.nan,
        "max_w_streak": mw,
        "max_l_streak": ml,
    }


def monthly(rows, mask, result):
    out = []
    months = sorted(set(rows["month"][mask]))
    for m in months:
        mm = mask & (rows["month"] == m)
        s = summary(result[mm], rows["mfe"][mm], rows["mae"][mm])
        out.append({"month": m, **s})
    return out


def robust_stats(rows, mask, result):
    m = monthly(rows, mask, result)
    pf_vals = np.array([r["pf"] for r in m if np.isfinite(r["pf"])], dtype=float)
    exp_vals = np.array([r["expectancy"] for r in m if np.isfinite(r["expectancy"])], dtype=float)
    wr_vals = np.array([r["wr"] for r in m if np.isfinite(r["wr"])], dtype=float)
    tr_vals = np.array([r["trades"] for r in m], dtype=float)
    bad = sum(1 for r in m if np.isfinite(r["pf"]) and r["pf"] < 1)
    return {
        "active_months": len(m),
        "monthly_pf_median": float(np.median(pf_vals)) if len(pf_vals) else np.nan,
        "monthly_pf_cv": float(pf_vals.std(ddof=1) / pf_vals.mean()) if len(pf_vals) > 1 and pf_vals.mean() else np.nan,
        "monthly_exp_cv": float(exp_vals.std(ddof=1) / abs(exp_vals.mean())) if len(exp_vals) > 1 and exp_vals.mean() else np.nan,
        "monthly_wr_cv": float(wr_vals.std(ddof=1) / wr_vals.mean()) if len(wr_vals) > 1 and wr_vals.mean() else np.nan,
        "monthly_trades_cv": float(tr_vals.std(ddof=1) / tr_vals.mean()) if len(tr_vals) > 1 and tr_vals.mean() else np.nan,
        "bad_months_pf_lt_1": bad,
    }


def simulate_tp_sl(rows, mask, tp, sl):
    mfe = rows["mfe"].astype(float)
    mae = rows["mae"].astype(float)
    actual = rows["actual"].astype(float)
    res = np.clip(actual, -sl, tp)
    both = (mfe >= tp) & (mae >= sl)
    hit_tp = (mfe >= tp) & ~both
    hit_sl = (mae >= sl) | both
    res = res.copy()
    res[hit_tp] = tp
    res[hit_sl] = -sl
    return res


def candidate_masks(rows):
    n = len(rows["actual"])
    out = [("ALL_TRADES", np.ones(n, dtype=bool))]
    for key in ["side", "speed", "cvd", "or_regime", "vol_regime"]:
        for value in sorted(set(rows[key])):
            out.append((f"{key}={value}", rows[key] == value))
    for th in sorted(set(rows["score"][~np.isnan(rows["score"].astype(float))])):
        out.append((f"score>={th:g}", rows["score"].astype(float) >= th))
    for pct in [10, 20, 30, 40, 50]:
        cutoff = np.nanquantile(rows["score"].astype(float), 1 - pct / 100)
        out.append((f"top_score_{pct}pct(score>={cutoff:.2f})", rows["score"].astype(float) >= cutoff))
    for pct in [20, 33, 50, 67, 80]:
        cutoff_hi = np.nanquantile(rows["or_range"].astype(float), pct / 100)
        out.append((f"range>={cutoff_hi:.0f}", rows["or_range"].astype(float) >= cutoff_hi))
        out.append((f"range<={cutoff_hi:.0f}", rows["or_range"].astype(float) <= cutoff_hi))
    for key in [
        "range_ok", "body_ok", "volume_ok", "delta_ok", "vwap_ok", "speed_ok",
        "volume_increasing", "delta_with_side", "price_accepted", "price_rejected",
        "aplus_structure", "aplus_absorption", "aplus_speed",
    ]:
        out.append((f"{key}=TRUE", rows[key].astype(bool)))
        out.append((f"{key}=FALSE", ~rows[key].astype(bool)))
    for side in sorted(set(rows["side"])):
        for th in [6, 7, 8]:
            out.append((f"side={side} AND score>={th}", (rows["side"] == side) & (rows["score"].astype(float) >= th)))
    for regime in sorted(set(rows["or_regime"])):
        for th in [6, 7, 8]:
            out.append((f"regime={regime} AND score>={th}", (rows["or_regime"] == regime) & (rows["score"].astype(float) >= th)))
    dedup = {}
    for name, mask in out:
        key = mask.tobytes()
        if key not in dedup:
            dedup[key] = (name, mask)
    return list(dedup.values())


def eval_candidate(rows, name, mask, result, tp="", sl=""):
    count = int(mask.sum())
    if count == 0:
        return None
    s = summary(result[mask], rows["mfe"][mask], rows["mae"][mask])
    train = mask & (rows["year"].astype(int) <= 2024)
    test = mask & (rows["year"].astype(int) >= 2025)
    st = summary(result[train])
    so = summary(result[test])
    rb = robust_stats(rows, mask, result)
    if s["trades"] == 0:
        return None
    pf_cap = min(s["pf"], 5.0) if np.isfinite(s["pf"]) else 5.0
    penalty = 1.0 + (rb["monthly_exp_cv"] if np.isfinite(rb["monthly_exp_cv"]) else 0.0)
    penalty += rb["bad_months_pf_lt_1"] / max(rb["active_months"], 1)
    score = max(s["expectancy"], -100) * math.sqrt(max(s["trades"], 1)) * max(pf_cap, 0) / penalty
    return {
        "setup": f"{name} | TP={tp} SL={sl}" if tp else f"{name} | actual",
        "filter": name,
        "tp": tp,
        "sl": sl,
        "trades": s["trades"],
        "wr": s["wr"],
        "pf": s["pf"],
        "expectancy": s["expectancy"],
        "profit": s["profit"],
        "dd": s["dd"],
        "avg_mfe": s["avg_mfe"],
        "avg_mae": s["avg_mae"],
        "avg_rr": s["avg_rr"],
        "std": s["std"],
        "test_trades": so["trades"],
        "test_pf": so["pf"],
        "test_exp": so["expectancy"],
        "train_trades": st["trades"],
        "train_pf": st["pf"],
        "train_exp": st["expectancy"],
        **rb,
        "robust_score": score,
    }


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fmt(v, d=2):
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    try:
        if np.isnan(v):
            return ""
        if np.isinf(v):
            return "inf"
        return f"{float(v):.{d}f}"
    except Exception:
        return str(v).replace("|", "\\|")


def md_table(rows, cols, limit=None):
    rows = rows[:limit] if limit else rows
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(fmt(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def block_boot(rng, x, n, block=8):
    out = []
    while len(out) < n:
        i = int(rng.integers(0, len(x)))
        out.extend(x[i:min(i + block, len(x))])
    return np.asarray(out[:n], dtype=float)


def monte_carlo(x, sims=MC_SIMS, horizon=None):
    rng = np.random.default_rng(MC_SEED)
    horizon = horizon or len(x)
    dds, finals, maxls = [], [], []
    probs = {3: 0, 5: 0, 8: 0, 10: 0}
    for _ in range(sims):
        seq = block_boot(rng, x, horizon)
        dds.append(max_dd(seq))
        finals.append(seq.sum())
        _, ml = streaks(seq)
        maxls.append(ml)
        for k in probs:
            probs[k] += int(ml >= k)
    return {
        "sims": sims,
        "horizon_trades": horizon,
        "final_mean": float(np.mean(finals)),
        "dd_mean": float(np.mean(dds)),
        "dd_95": float(np.quantile(dds, 0.95)),
        "dd_99": float(np.quantile(dds, 0.99)),
        "loss_streak_mean": float(np.mean(maxls)),
        **{f"p_loss_streak_{k}": probs[k] / sims * 100 for k in probs},
    }


def lucid_dynamic(pnl_usd, trades_per_month):
    rng = np.random.default_rng(MC_SEED + 3)
    horizon = int(round(trades_per_month * 3))
    passed = busted = timeout = 0
    pass_days, dds = [], []
    for _ in range(MC_SIMS):
        seq = block_boot(rng, pnl_usd, horizon)
        eq = peak = maxdd = 0.0
        status = "timeout"
        for i, pnl in enumerate(seq, 1):
            eq += pnl
            peak = max(peak, eq)
            maxdd = max(maxdd, peak - eq)
            if peak - eq >= LUCID_DD:
                status = "bust"
                break
            if eq >= LUCID_TARGET:
                status = "pass"
                pass_days.append(i)
                break
        passed += status == "pass"
        busted += status == "bust"
        timeout += status == "timeout"
        dds.append(maxdd)
    return {
        "pass_pct_3mo": passed / MC_SIMS * 100,
        "bust_pct_3mo": busted / MC_SIMS * 100,
        "timeout_pct_3mo": timeout / MC_SIMS * 100,
        "avg_trades_to_pass": float(np.mean(pass_days)) if pass_days else np.nan,
        "dd_95_usd": float(np.quantile(dds, 0.95)),
    }


def sizing_rules(rows, mask, result):
    out = []
    score = rows["score"].astype(float)
    for high_pct in [10, 20, 30, 40]:
        for low_pct in [10, 20, 30, 40]:
            high_cut = np.nanquantile(score[mask], 1 - high_pct / 100)
            low_cut = np.nanquantile(score[mask], low_pct / 100)
            contracts = np.full(len(result), MID_CONTRACTS, dtype=float)
            contracts[score >= high_cut] = HIGH_CONTRACTS
            contracts[score <= low_cut] = LOW_CONTRACTS
            pnl = result * contracts * TICK_VALUE
            sm = summary(pnl[mask])
            test = mask & (rows["year"].astype(int) >= 2025)
            st = summary(pnl[test])
            out.append({
                "rule": f"top {high_pct}% -> 4c | mid -> 3c | bottom {low_pct}% -> 1c",
                "high_cut": high_cut,
                "low_cut": low_cut,
                "trades": sm["trades"],
                "profit_usd": sm["profit"],
                "expectancy_usd": sm["expectancy"],
                "dd_usd": sm["dd"],
                "pf": sm["pf"],
                "test_expectancy_usd": st["expectancy"],
                "test_dd_usd": st["dd"],
                "avg_contracts": float(np.mean(contracts[mask])),
                "c1": int(np.sum((contracts == LOW_CONTRACTS) & mask)),
                "c3": int(np.sum((contracts == MID_CONTRACTS) & mask)),
                "c4": int(np.sum((contracts == HIGH_CONTRACTS) & mask)),
                "risk_score": st["expectancy"] * math.sqrt(max(st["trades"], 1)) / max(st["dd"], 1.0),
            })
    return sorted(out, key=lambda r: (r["risk_score"], r["test_expectancy_usd"], r["expectancy_usd"]), reverse=True)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    event_count, loaded = load_rows()
    rows = arrays(loaded)
    masks = candidate_masks(rows)
    actual = rows["actual"].astype(float)
    all_rows = []
    for name, mask in masks:
        if mask.sum() >= 20:
            all_rows.append(eval_candidate(rows, name, mask, actual))
    pruned = [(n, m) for n, m in masks if m.sum() >= 50]
    for name, mask in pruned:
        for tp in TP_GRID:
            for sl in SL_GRID:
                sim = simulate_tp_sl(rows, mask, tp, sl)
                row = eval_candidate(rows, name, mask, sim, int(tp), int(sl))
                if row and row["trades"] >= 50:
                    all_rows.append(row)
    all_rows = [r for r in all_rows if r]
    robust = [
        r for r in all_rows
        if r["trades"] >= 80 and r["active_months"] >= 18 and r["test_trades"] >= 20
        and r["expectancy"] > 0 and r["test_exp"] > 0
    ]
    robust.sort(key=lambda r: (r["robust_score"], r["test_exp"], r["trades"]), reverse=True)
    all_rows.sort(key=lambda r: (r["expectancy"], r["pf"] if np.isfinite(r["pf"]) else 999, r["trades"]), reverse=True)
    best = robust[0] if robust else all_rows[0]
    best_mask = dict(masks)[best["filter"]]
    best_result = simulate_tp_sl(rows, best_mask, float(best["tp"]), float(best["sl"])) if best["tp"] != "" else actual
    best_summary = summary(best_result[best_mask], rows["mfe"][best_mask], rows["mae"][best_mask])
    monthly_best = monthly(rows, best_mask, best_result)
    sizing = sizing_rules(rows, best_mask, best_result)
    best_size = sizing[0]
    score = rows["score"].astype(float)
    contracts = np.full(len(best_result), MID_CONTRACTS, dtype=float)
    contracts[score >= best_size["high_cut"]] = HIGH_CONTRACTS
    contracts[score <= best_size["low_cut"]] = LOW_CONTRACTS
    pnl_usd = best_result * contracts * TICK_VALUE
    sized_summary = summary(pnl_usd[best_mask])
    trades_per_month = best_summary["trades"] / max(len(set(rows["month"][best_mask])), 1)
    mc_ticks = monte_carlo(best_result[best_mask])
    mc_usd = monte_carlo(pnl_usd[best_mask])
    lucid = lucid_dynamic(pnl_usd[best_mask], trades_per_month)

    write_csv(OUT_DIR / "all_candidates.csv", all_rows)
    write_csv(OUT_DIR / "robust_candidates.csv", robust)
    write_csv(OUT_DIR / "best_monthly.csv", monthly_best)
    write_csv(OUT_DIR / "score_sizing_1_3_4.csv", sizing)

    cols = ["setup", "trades", "wr", "pf", "expectancy", "profit", "dd", "test_pf", "test_exp", "active_months", "monthly_pf_median", "bad_months_pf_lt_1", "robust_score"]
    report = [
        "# Edge Optimization Fast Report",
        f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Source: `{RUN_DIR}`",
        f"Events/files: {event_count}. Executed trades optimized: {len(loaded)}. No-entry/TIME_OVER excluded from TP/SL optimization: {event_count - len(loaded)}.",
        "",
        "## Recommended Robust Candidate",
        f"`{best['setup']}`",
        md_table([{**best_summary}], ["trades", "wr", "pf", "expectancy", "profit", "dd", "avg_mfe", "avg_mae", "avg_rr", "std", "max_w_streak", "max_l_streak"]),
        "",
        "## Dynamic Contracts Requested: likely=4, middle=3, less likely=1",
        f"Selected sizing: `{best_size['rule']}`. High score cutoff `{best_size['high_cut']:.2f}`, low score cutoff `{best_size['low_cut']:.2f}`.",
        md_table([{**sized_summary}], ["trades", "wr", "pf", "expectancy", "profit", "dd", "std", "max_w_streak", "max_l_streak"]),
        md_table(sizing[:10], ["rule", "high_cut", "low_cut", "trades", "profit_usd", "expectancy_usd", "dd_usd", "pf", "test_expectancy_usd", "test_dd_usd", "avg_contracts", "c1", "c3", "c4", "risk_score"]),
        "",
        "## Top Robust Candidates",
        md_table(robust[:20], cols),
        "",
        "## Top Naive Candidates (Overfit Risk)",
        md_table(all_rows[:20], cols),
        "",
        "## Monte Carlo",
        "Ticks, fixed result distribution:",
        md_table([mc_ticks], ["sims", "horizon_trades", "final_mean", "dd_mean", "dd_95", "dd_99", "loss_streak_mean", "p_loss_streak_3", "p_loss_streak_5", "p_loss_streak_8", "p_loss_streak_10"]),
        "USD, dynamic 1/3/4 contracts:",
        md_table([mc_usd], ["sims", "horizon_trades", "final_mean", "dd_mean", "dd_95", "dd_99", "loss_streak_mean", "p_loss_streak_3", "p_loss_streak_5", "p_loss_streak_8", "p_loss_streak_10"]),
        "",
        "## Lucid 150k, Dynamic 1/3/4 Sizing",
        md_table([lucid], ["pass_pct_3mo", "bust_pct_3mo", "timeout_pct_3mo", "avg_trades_to_pass", "dd_95_usd"]),
        "",
        "## Notes",
        "- TP/SL simulation uses observed MFE/MAE. If both TP and SL are reachable, SL wins. This is conservative.",
        "- Dynamic sizing uses `score total` as the probability proxy. It does not use future MFE/MAE.",
        "- Profile-shape buckets P/b/D/Trend/Tree are not optimized because the v11 files do not populate reliable profile-shape labels.",
    ]
    (OUT_DIR / "README.md").write_text("\n\n".join(report), encoding="utf-8")
    print(OUT_DIR / "README.md")
    print(best["setup"])
    print(best_size["rule"])


if __name__ == "__main__":
    main()
