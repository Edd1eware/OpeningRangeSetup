import csv
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score")
RUN_DIR = RESULTS_DIR / "visual_tests" / "04_run_replay_score_trade_results_dst_2025_2026_runs" / "X10_R1"
OUT_DIR = BASE_DIR / "outputs" / f"edge_optimization_report_{datetime.now():%Y%m%d_%H%M%S}"

TICK_VALUE_USD = 5.0
LUCID_150K_TARGET = 9000.0
LUCID_150K_DD = 4500.0
MC_SIMS = 10_000
MC_SEED = 20260711

TP_GRID = [20, 30, 40, 50, 60, 80, 100, 120, 150, 200]
SL_GRID = [20, 30, 40, 50, 60, 70, 80, 100]
SIZING_HIGH_PCTS = [10, 20, 30, 40]
SIZING_LOW_PCTS = [10, 20, 30, 40]
LOW_CONTRACTS = 1
MID_CONTRACTS = 3
HIGH_CONTRACTS = 4


def to_float(value, default=np.nan):
    text = str(value or "").strip()
    if not text or text.upper() in {"OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return default
    try:
        return float(text.replace("+", ""))
    except ValueError:
        return default


def parse_ticks(value):
    text = str(value or "").strip().upper()
    if text == "BE":
        return 0.0
    if text in {"", "OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return 0.0
    return to_float(text, 0.0)


def max_drawdown(series):
    arr = np.asarray(series, dtype=float)
    if arr.size == 0:
        return 0.0
    curve = np.cumsum(arr)
    peaks = np.maximum.accumulate(np.r_[0.0, curve])[:-1]
    return float(np.max(peaks - curve))


def streaks(series):
    max_w = max_l = cur_w = cur_l = 0
    for value in series:
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


def profit_factor(series):
    arr = np.asarray(series, dtype=float)
    gross_win = arr[arr > 0].sum()
    gross_loss = -arr[arr < 0].sum()
    if gross_loss == 0:
        return np.inf if gross_win > 0 else np.nan
    return float(gross_win / gross_loss)


def summarize(df, result_col="opt_ticks"):
    if df.empty:
        return {
            "trades": 0,
            "wr": np.nan,
            "pf": np.nan,
            "expectancy": np.nan,
            "profit": 0.0,
            "dd": 0.0,
            "avg_mfe": np.nan,
            "avg_mae": np.nan,
            "avg_rr": np.nan,
            "std": np.nan,
            "max_w_streak": 0,
            "max_l_streak": 0,
        }
    s = df[result_col].astype(float)
    wins = s[s > 0]
    losses = s[s < 0]
    avg_win = wins.mean() if len(wins) else np.nan
    avg_loss = -losses.mean() if len(losses) else np.nan
    max_w, max_l = streaks(s)
    return {
        "trades": int(len(s)),
        "wr": float((s > 0).mean() * 100.0),
        "pf": profit_factor(s),
        "expectancy": float(s.mean()),
        "profit": float(s.sum()),
        "dd": max_drawdown(s),
        "avg_mfe": float(df["MFE_ticks_num"].mean()) if "MFE_ticks_num" in df else np.nan,
        "avg_mae": float(df["MAE_ticks_num"].mean()) if "MAE_ticks_num" in df else np.nan,
        "avg_rr": float(avg_win / avg_loss) if avg_loss and not math.isnan(avg_loss) else np.nan,
        "std": float(s.std(ddof=1)) if len(s) > 1 else np.nan,
        "max_w_streak": max_w,
        "max_l_streak": max_l,
    }


def summarize_usd(df, result_col="pnl_usd"):
    tmp = df.copy()
    tmp["__result_usd__"] = tmp[result_col]
    m = summarize(tmp, "__result_usd__")
    m["expectancy_usd"] = m.pop("expectancy")
    m["profit_usd"] = m.pop("profit")
    m["dd_usd"] = m.pop("dd")
    m["std_usd"] = m.pop("std")
    return m


def fmt(value, digits=2):
    if value is None:
        return ""
    try:
        if math.isnan(value):
            return ""
        if math.isinf(value):
            return "inf"
    except TypeError:
        pass
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def md_table(rows, columns, digits=2, max_rows=None):
    data = rows[:max_rows] if max_rows else rows
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in data:
        out.append("| " + " | ".join(fmt(row.get(c, ""), digits) for c in columns) + " |")
    return "\n".join(out)


def load_results():
    rows = []
    for path in sorted(RUN_DIR.glob("score_trade_result_*_NY.csv")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        date_iso = match.group(1) if match else ""
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            row = next(csv.DictReader(handle), {})
        row["source_path"] = str(path)
        row["date"] = pd.to_datetime(row.get("fecha") or date_iso)
        row["month"] = row["date"].strftime("%Y-%m")
        row["year"] = row["date"].year
        row["actual_ticks"] = parse_ticks(row.get("result TP SL BE") or row.get("RESULT"))
        row["is_trade"] = bool(str(row.get("Side") or "").strip() and str(row.get("Entry_price") or "").strip())
        for col in [
            "score total",
            "range",
            "Body",
            "Volume_entry",
            "Delta_entry",
            "BreakOut_TICKS_PER_SEC",
            "SL_ticks",
            "TP_ticks",
            "MAE_ticks",
            "MFE_ticks",
            "Cvd_Excelente_Pct",
            "Imbalance_Count",
            "Execution_Side_Imbalance_Count",
            "Volume_Increasing_Pct_During_Trade",
            "Trade_Duration_Milliseconds",
        ]:
            row[col + "_num"] = to_float(row.get(col))
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["result_label"] = df["Result_Label"].fillna("").astype(str)
    df["side"] = df["Side"].fillna("").astype(str)
    df["speed_profile"] = df["Speed_Profile"].fillna("").replace("", "Unknown")
    df["cvd_label"] = df["Cvd_Pullback_Label"].fillna("").replace("", "Unknown")
    df["score"] = df["score total_num"]
    df["or_range"] = df["range_num"]
    df["MFE_ticks_num"] = df["MFE_ticks_num"]
    df["MAE_ticks_num"] = df["MAE_ticks_num"]
    return df


def add_regimes(trades):
    q1, q2 = trades["or_range"].quantile([1 / 3, 2 / 3])
    trades = trades.copy()
    trades["or_regime"] = np.select(
        [trades["or_range"] <= q1, trades["or_range"] >= q2],
        ["OR_small", "OR_large"],
        default="OR_mid",
    )
    trades["vol_regime"] = np.select(
        [trades["or_range"] <= q1, trades["or_range"] >= q2],
        ["Low_vol", "High_vol"],
        default="Mid_vol",
    )
    # Profile shape is not populated in the v11 result files. Keep it explicit.
    trades["profile_shape"] = "Unknown"
    return trades


@dataclass
class Candidate:
    name: str
    mask: pd.Series


def build_filter_candidates(trades):
    candidates = [Candidate("ALL_TRADES", pd.Series(True, index=trades.index))]

    for side in sorted(x for x in trades["side"].dropna().unique() if x):
        candidates.append(Candidate(f"side={side}", trades["side"] == side))

    for speed in sorted(trades["speed_profile"].dropna().unique()):
        candidates.append(Candidate(f"speed={speed}", trades["speed_profile"] == speed))

    for label in sorted(trades["cvd_label"].dropna().unique()):
        candidates.append(Candidate(f"cvd={label}", trades["cvd_label"] == label))

    for regime in sorted(trades["or_regime"].unique()):
        candidates.append(Candidate(f"regime={regime}", trades["or_regime"] == regime))

    for regime in sorted(trades["vol_regime"].unique()):
        candidates.append(Candidate(f"vol={regime}", trades["vol_regime"] == regime))

    for threshold in sorted(x for x in trades["score"].dropna().unique()):
        candidates.append(Candidate(f"score>={threshold:g}", trades["score"] >= threshold))

    for pct in [10, 20, 30, 40, 50, 60, 70]:
        cutoff = trades["score"].quantile(1 - pct / 100.0)
        candidates.append(Candidate(f"top_score_{pct}pct(score>={cutoff:.2f})", trades["score"] >= cutoff))

    for q in [0.2, 0.33, 0.5, 0.67, 0.8]:
        lo = trades["or_range"].quantile(q)
        hi = trades["or_range"].quantile(1 - q)
        candidates.append(Candidate(f"range>={lo:.0f}", trades["or_range"] >= lo))
        candidates.append(Candidate(f"range<={hi:.0f}", trades["or_range"] <= hi))

    bool_cols = [
        "Range_OK",
        "Body_OK",
        "Volume_OK",
        "Delta_OK",
        "VWAP_OK",
        "Speed_OK",
        "Volume_Increasing",
        "Delta_With_Side",
        "Price_Accepted_After_Imbalance",
        "Price_Rejected_After_Imbalance",
        "APlus_Structure",
        "APlus_Absorption",
        "APlus_Speed",
        "APlus_Speed_Setup_Confirmed",
        "TP_And_SL_Hit_Same_Update",
    ]
    for col in bool_cols:
        if col in trades:
            values = trades[col].fillna("").astype(str).str.upper()
            candidates.append(Candidate(f"{col}=TRUE", values == "TRUE"))
            candidates.append(Candidate(f"{col}=FALSE", values == "FALSE"))

    # Conservative two-factor candidates only, to avoid combinatorial overfit.
    score_levels = [6, 7, 8]
    for side in sorted(x for x in trades["side"].dropna().unique() if x):
        for score in score_levels:
            candidates.append(Candidate(f"side={side} AND score>={score}", (trades["side"] == side) & (trades["score"] >= score)))
    for regime in sorted(trades["or_regime"].unique()):
        for score in score_levels:
            candidates.append(Candidate(f"regime={regime} AND score>={score}", (trades["or_regime"] == regime) & (trades["score"] >= score)))
    for speed in sorted(trades["speed_profile"].dropna().unique()):
        for score in score_levels:
            candidates.append(Candidate(f"speed={speed} AND score>={score}", (trades["speed_profile"] == speed) & (trades["score"] >= score)))

    dedup = {}
    for cand in candidates:
        key = tuple(cand.mask.fillna(False).astype(bool).to_numpy().tolist())
        if key not in dedup:
            dedup[key] = cand
    return list(dedup.values())


def simulate_tp_sl(df, tp, sl):
    mfe = df["MFE_ticks_num"].to_numpy(dtype=float)
    mae = df["MAE_ticks_num"].to_numpy(dtype=float)
    actual = df["actual_ticks"].to_numpy(dtype=float)
    both = (mfe >= tp) & (mae >= sl)
    hit_tp = (mfe >= tp) & ~both
    hit_sl = (mae >= sl) | both
    result = np.clip(actual, -sl, tp)
    result[hit_tp] = tp
    result[hit_sl] = -sl
    return result


def monthly_metrics(df, result_col="opt_ticks"):
    rows = []
    for month, g in df.groupby("month", sort=True):
        m = summarize(g, result_col)
        rows.append(
            {
                "month": month,
                "trades": m["trades"],
                "wr": m["wr"],
                "pf": m["pf"],
                "expectancy": m["expectancy"],
                "dd": m["dd"],
                "profit": m["profit"],
            }
        )
    return pd.DataFrame(rows)


def robust_stats(df, result_col="opt_ticks"):
    m = monthly_metrics(df, result_col)
    years = []
    for year, g in df.groupby("year", sort=True):
        s = summarize(g, result_col)
        years.append({"year": int(year), **s})
    y = pd.DataFrame(years)
    pf_vals = m["pf"].replace([np.inf, -np.inf], np.nan).dropna()
    exp_vals = m["expectancy"].dropna()
    trade_vals = m["trades"].dropna()
    wr_vals = m["wr"].dropna()
    return {
        "active_months": int((m["trades"] > 0).sum()),
        "monthly_pf_median": float(pf_vals.median()) if len(pf_vals) else np.nan,
        "monthly_pf_mean": float(pf_vals.mean()) if len(pf_vals) else np.nan,
        "monthly_pf_cv": float(pf_vals.std(ddof=1) / pf_vals.mean()) if len(pf_vals) > 1 and pf_vals.mean() else np.nan,
        "monthly_exp_mean": float(exp_vals.mean()) if len(exp_vals) else np.nan,
        "monthly_exp_cv": float(exp_vals.std(ddof=1) / abs(exp_vals.mean())) if len(exp_vals) > 1 and exp_vals.mean() else np.nan,
        "monthly_wr_cv": float(wr_vals.std(ddof=1) / wr_vals.mean()) if len(wr_vals) > 1 and wr_vals.mean() else np.nan,
        "monthly_trades_cv": float(trade_vals.std(ddof=1) / trade_vals.mean()) if len(trade_vals) > 1 and trade_vals.mean() else np.nan,
        "bad_months_pf_lt_1": int((m["pf"] < 1).sum()),
        "min_year_exp": float(y["expectancy"].min()) if not y.empty else np.nan,
        "min_year_pf": float(y["pf"].replace([np.inf, -np.inf], np.nan).min()) if not y.empty else np.nan,
        "year_count": int(len(y)),
    }


def apply_score_sizing(df, high_pct, low_pct):
    out = df.copy()
    high_cut = out["score"].quantile(1 - high_pct / 100.0)
    low_cut = out["score"].quantile(low_pct / 100.0)
    out["contracts"] = MID_CONTRACTS
    out.loc[out["score"] >= high_cut, "contracts"] = HIGH_CONTRACTS
    out.loc[out["score"] <= low_cut, "contracts"] = LOW_CONTRACTS
    out["pnl_usd"] = out["opt_ticks"] * out["contracts"] * TICK_VALUE_USD
    out["sizing_bucket"] = np.select(
        [out["score"] >= high_cut, out["score"] <= low_cut],
        [f"top_{high_pct}%_4c", f"bottom_{low_pct}%_1c"],
        default=f"middle_{MID_CONTRACTS}c",
    )
    return out, high_cut, low_cut


def evaluate_sizing_rules(df):
    rows = []
    for high_pct in SIZING_HIGH_PCTS:
        for low_pct in SIZING_LOW_PCTS:
            sized, high_cut, low_cut = apply_score_sizing(df, high_pct, low_pct)
            train = sized[sized["year"] <= 2024]
            test = sized[sized["year"] >= 2025]
            all_m = summarize_usd(sized, "pnl_usd")
            train_m = summarize_usd(train, "pnl_usd")
            test_m = summarize_usd(test, "pnl_usd")
            rows.append(
                {
                    "sizing_rule": f"top {high_pct}% -> {HIGH_CONTRACTS}c | middle -> {MID_CONTRACTS}c | bottom {low_pct}% -> {LOW_CONTRACTS}c",
                    "high_pct": high_pct,
                    "low_pct": low_pct,
                    "high_score_cutoff": high_cut,
                    "low_score_cutoff": low_cut,
                    "trades": all_m["trades"],
                    "profit_usd": all_m["profit_usd"],
                    "expectancy_usd": all_m["expectancy_usd"],
                    "dd_usd": all_m["dd_usd"],
                    "pf": all_m["pf"],
                    "wr": all_m["wr"],
                    "test_profit_usd": test_m["profit_usd"],
                    "test_expectancy_usd": test_m["expectancy_usd"],
                    "test_dd_usd": test_m["dd_usd"],
                    "test_pf": test_m["pf"],
                    "train_expectancy_usd": train_m["expectancy_usd"],
                    "contracts_avg": float(sized["contracts"].mean()),
                    "contracts_1_count": int((sized["contracts"] == LOW_CONTRACTS).sum()),
                    "contracts_mid_count": int((sized["contracts"] == MID_CONTRACTS).sum()),
                    "contracts_4_count": int((sized["contracts"] == HIGH_CONTRACTS).sum()),
                    "risk_score": (
                        test_m["expectancy_usd"]
                        * math.sqrt(max(test_m["trades"], 1))
                        / max(test_m["dd_usd"], 1.0)
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["risk_score", "test_expectancy_usd", "expectancy_usd"],
        ascending=False,
    )


def evaluate_candidate(trades, cand, tp=None, sl=None):
    subset = trades[cand.mask.fillna(False).astype(bool)].copy()
    if subset.empty:
        return None, subset
    if tp is not None and sl is not None:
        subset["opt_ticks"] = simulate_tp_sl(subset, tp, sl)
        setup = f"{cand.name} | TP={tp} SL={sl}"
    else:
        subset["opt_ticks"] = subset["actual_ticks"]
        setup = f"{cand.name} | actual"

    all_m = summarize(subset, "opt_ticks")
    train = subset[subset["year"] <= 2024]
    test = subset[subset["year"] >= 2025]
    train_m = summarize(train, "opt_ticks")
    test_m = summarize(test, "opt_ticks")
    rb = robust_stats(subset, "opt_ticks")
    pf_cap = min(all_m["pf"], 5.0) if not math.isinf(all_m["pf"]) else 5.0
    stability_penalty = 1.0
    if rb["monthly_exp_cv"] and not math.isnan(rb["monthly_exp_cv"]):
        stability_penalty += max(0.0, rb["monthly_exp_cv"])
    if rb["bad_months_pf_lt_1"]:
        stability_penalty += rb["bad_months_pf_lt_1"] / max(rb["active_months"], 1)
    robust_score = (
        max(all_m["expectancy"], -100.0)
        * math.sqrt(max(all_m["trades"], 1))
        * max(pf_cap, 0.0)
        / stability_penalty
    )
    row = {
        "setup": setup,
        "filter": cand.name,
        "tp": tp if tp is not None else "",
        "sl": sl if sl is not None else "",
        "rr": (tp / sl) if tp and sl else "",
        "trades": all_m["trades"],
        "wr": all_m["wr"],
        "pf": all_m["pf"],
        "expectancy": all_m["expectancy"],
        "profit": all_m["profit"],
        "dd": all_m["dd"],
        "avg_mfe": all_m["avg_mfe"],
        "avg_mae": all_m["avg_mae"],
        "avg_rr": all_m["avg_rr"],
        "std": all_m["std"],
        "train_trades": train_m["trades"],
        "train_pf": train_m["pf"],
        "train_exp": train_m["expectancy"],
        "test_trades": test_m["trades"],
        "test_pf": test_m["pf"],
        "test_exp": test_m["expectancy"],
        "active_months": rb["active_months"],
        "monthly_pf_median": rb["monthly_pf_median"],
        "monthly_pf_cv": rb["monthly_pf_cv"],
        "monthly_exp_cv": rb["monthly_exp_cv"],
        "bad_months_pf_lt_1": rb["bad_months_pf_lt_1"],
        "min_year_exp": rb["min_year_exp"],
        "min_year_pf": rb["min_year_pf"],
        "robust_score": robust_score,
    }
    return row, subset


def draw_block_bootstrap(rng, series, n, block=8):
    out = []
    series = np.asarray(series, dtype=float)
    while len(out) < n:
        i = int(rng.integers(0, len(series)))
        out.extend(series[i : min(i + block, len(series))])
    return np.asarray(out[:n], dtype=float)


def monte_carlo(series, sims=MC_SIMS, horizon=None):
    rng = np.random.default_rng(MC_SEED)
    series = np.asarray(series, dtype=float)
    horizon = horizon or len(series)
    dds = []
    finals = []
    max_losses = []
    p_streak = {3: 0, 5: 0, 8: 0, 10: 0}
    for _ in range(sims):
        seq = draw_block_bootstrap(rng, series, horizon)
        dds.append(max_drawdown(seq))
        finals.append(seq.sum())
        _, max_l = streaks(seq)
        max_losses.append(max_l)
        for k in p_streak:
            if max_l >= k:
                p_streak[k] += 1
    return {
        "sims": sims,
        "horizon_trades": horizon,
        "final_mean": float(np.mean(finals)),
        "dd_mean": float(np.mean(dds)),
        "dd_95": float(np.quantile(dds, 0.95)),
        "dd_99": float(np.quantile(dds, 0.99)),
        "loss_streak_mean": float(np.mean(max_losses)),
        **{f"p_loss_streak_{k}": p_streak[k] / sims * 100.0 for k in p_streak},
    }


def lucid_mc(series, trades_per_month, sims=MC_SIMS):
    rng = np.random.default_rng(MC_SEED + 7)
    horizon = max(1, int(round(trades_per_month * 3)))
    out = []
    for contracts in range(1, 11):
        passed = busted = timeout = 0
        days_to_pass = []
        max_dds = []
        for _ in range(sims):
            seq_ticks = draw_block_bootstrap(rng, series, horizon)
            seq_usd = seq_ticks * TICK_VALUE_USD * contracts
            eq = peak = 0.0
            status = "timeout"
            maxdd = 0.0
            for i, pnl in enumerate(seq_usd, 1):
                eq += pnl
                peak = max(peak, eq)
                maxdd = max(maxdd, peak - eq)
                if peak - eq >= LUCID_150K_DD:
                    status = "bust"
                    break
                if eq >= LUCID_150K_TARGET:
                    status = "pass"
                    days_to_pass.append(i)
                    break
            if status == "pass":
                passed += 1
            elif status == "bust":
                busted += 1
            else:
                timeout += 1
            max_dds.append(maxdd)
        out.append(
            {
                "contracts": contracts,
                "pass_pct_3mo": passed / sims * 100.0,
                "bust_pct_3mo": busted / sims * 100.0,
                "timeout_pct_3mo": timeout / sims * 100.0,
                "avg_trades_to_pass": float(np.mean(days_to_pass)) if days_to_pass else np.nan,
                "dd_95_usd": float(np.quantile(max_dds, 0.95)),
                "score": (passed - busted) / sims * 100.0,
            }
        )
    return pd.DataFrame(out)


def lucid_mc_usd(series_usd, trades_per_month, sims=MC_SIMS):
    rng = np.random.default_rng(MC_SEED + 17)
    horizon = max(1, int(round(trades_per_month * 3)))
    passed = busted = timeout = 0
    days_to_pass = []
    max_dds = []
    for _ in range(sims):
        seq_usd = draw_block_bootstrap(rng, series_usd, horizon)
        eq = peak = 0.0
        status = "timeout"
        maxdd = 0.0
        for i, pnl in enumerate(seq_usd, 1):
            eq += pnl
            peak = max(peak, eq)
            maxdd = max(maxdd, peak - eq)
            if peak - eq >= LUCID_150K_DD:
                status = "bust"
                break
            if eq >= LUCID_150K_TARGET:
                status = "pass"
                days_to_pass.append(i)
                break
        if status == "pass":
            passed += 1
        elif status == "bust":
            busted += 1
        else:
            timeout += 1
        max_dds.append(maxdd)
    return pd.DataFrame(
        [
            {
                "sizing": "score dynamic 1/3/4",
                "pass_pct_3mo": passed / sims * 100.0,
                "bust_pct_3mo": busted / sims * 100.0,
                "timeout_pct_3mo": timeout / sims * 100.0,
                "avg_trades_to_pass": float(np.mean(days_to_pass)) if days_to_pass else np.nan,
                "dd_95_usd": float(np.quantile(max_dds, 0.95)),
            }
        ]
    )


def contribution_risk(df):
    monthly = monthly_metrics(df, "opt_ticks")
    total = df["opt_ticks"].sum()
    if total <= 0:
        return np.nan, ""
    monthly["contribution"] = monthly["profit"] / total * 100.0
    top = monthly.sort_values("contribution", ascending=False).head(1)
    return float(top["contribution"].iloc[0]), str(top["month"].iloc[0])


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_events = load_results()
    trades = all_events[all_events["is_trade"]].copy()
    trades = add_regimes(trades)
    trades["opt_ticks"] = trades["actual_ticks"]

    candidates = build_filter_candidates(trades)
    candidates_by_name = {cand.name: cand for cand in candidates}

    rows = []
    for cand in candidates:
        row, subset = evaluate_candidate(trades, cand)
        if row and row["trades"] >= 20:
            rows.append(row)

    # TP/SL search on a pruned set of filters to reduce overfit/noise.
    pruned = []
    for cand in candidates:
        n = int(cand.mask.fillna(False).sum())
        if n >= 50:
            pruned.append(cand)
    for cand in pruned:
        for tp in TP_GRID:
            for sl in SL_GRID:
                row, subset = evaluate_candidate(trades, cand, tp, sl)
                if row and row["trades"] >= 50:
                    rows.append(row)

    opt = pd.DataFrame(rows)
    finite_pf = opt["pf"].replace([np.inf, -np.inf], np.nan)
    opt["pf_sort"] = finite_pf.fillna(999)
    robust = opt[
        (opt["trades"] >= 80)
        & (opt["active_months"] >= 18)
        & (opt["test_trades"] >= 20)
        & (opt["test_exp"] > 0)
        & (opt["expectancy"] > 0)
    ].copy()
    robust = robust.sort_values(["robust_score", "test_exp", "trades"], ascending=False)
    opt_sorted = opt.sort_values(["expectancy", "pf_sort", "trades"], ascending=False)

    baseline = trades.copy()
    baseline["opt_ticks"] = baseline["actual_ticks"]
    baseline_metrics = summarize(baseline, "opt_ticks")

    best_row = robust.iloc[0] if not robust.empty else opt_sorted.iloc[0]
    best_setup = best_row["setup"]
    best_cand = candidates_by_name[best_row["filter"]]
    best = trades[best_cand.mask.fillna(False).astype(bool)].copy()
    has_tp_sl = (
        pd.notna(best_row["tp"])
        and pd.notna(best_row["sl"])
        and str(best_row["tp"]).strip() != ""
        and str(best_row["sl"]).strip() != ""
    )
    if has_tp_sl:
        best["opt_ticks"] = simulate_tp_sl(best, int(best_row["tp"]), int(best_row["sl"]))
    else:
        best["opt_ticks"] = best["actual_ticks"]
    best_metrics = summarize(best, "opt_ticks")
    top_contrib, top_month = contribution_risk(best)

    opt.drop(columns=["pf_sort"]).to_csv(OUT_DIR / "all_candidates.csv", index=False)
    robust.drop(columns=["pf_sort"], errors="ignore").to_csv(OUT_DIR / "robust_candidates.csv", index=False)
    monthly_metrics(best, "opt_ticks").to_csv(OUT_DIR / "best_monthly.csv", index=False)

    years = []
    for year, g in best.groupby("year", sort=True):
        years.append({"year": int(year), **summarize(g, "opt_ticks")})
    pd.DataFrame(years).to_csv(OUT_DIR / "best_yearly.csv", index=False)

    mc = monte_carlo(best["opt_ticks"].to_numpy(), MC_SIMS)
    trades_per_month = best_metrics["trades"] / max(best["month"].nunique(), 1)
    lucid = lucid_mc(best["opt_ticks"].to_numpy(), trades_per_month, MC_SIMS)
    lucid.to_csv(OUT_DIR / "lucid_150k_mc.csv", index=False)

    sizing_rules = evaluate_sizing_rules(best)
    sizing_rules.to_csv(OUT_DIR / "score_sizing_1_3_4_rules.csv", index=False)
    best_sizing_rule = sizing_rules.iloc[0]
    sized_best, high_cut, low_cut = apply_score_sizing(
        best,
        int(best_sizing_rule["high_pct"]),
        int(best_sizing_rule["low_pct"]),
    )
    sized_best.to_csv(OUT_DIR / "best_candidate_sized_trades.csv", index=False)
    sized_metrics = summarize_usd(sized_best, "pnl_usd")
    sized_mc = monte_carlo(sized_best["pnl_usd"].to_numpy(), MC_SIMS)
    sized_lucid = lucid_mc_usd(sized_best["pnl_usd"].to_numpy(), trades_per_month, MC_SIMS)
    sized_lucid.to_csv(OUT_DIR / "lucid_150k_dynamic_sizing_mc.csv", index=False)

    ranking_rows = []
    for pct in [10, 20, 30, 40, 50]:
        cutoff = trades["score"].quantile(1 - pct / 100.0)
        g = trades[trades["score"] >= cutoff].copy()
        g["opt_ticks"] = g["actual_ticks"]
        ranking_rows.append({"bucket": f"Top {pct}%", "score_cutoff": cutoff, **summarize(g, "opt_ticks")})
    g = trades[trades["score"] < trades["score"].quantile(0.5)].copy()
    g["opt_ticks"] = g["actual_ticks"]
    ranking_rows.append({"bucket": "Bottom 50%", "score_cutoff": "", **summarize(g, "opt_ticks")})
    pd.DataFrame(ranking_rows).to_csv(OUT_DIR / "ranking_quality_actual.csv", index=False)

    target_rows = []
    for target in [20, 40, 60, 80, 100, 120, 150, 200]:
        target_rows.append(
            {
                "target_ticks": target,
                "pct_reached_by_observed_path": float((trades["MFE_ticks_num"] >= target).mean() * 100.0),
            }
        )
    pd.DataFrame(target_rows).to_csv(OUT_DIR / "target_reach_distribution.csv", index=False)

    stop_rows = []
    for stop in [20, 30, 40, 50, 60, 70, 80, 100]:
        stop_rows.append(
            {
                "stop_ticks": stop,
                "pct_survived_observed_path": float((trades["MAE_ticks_num"] < stop).mean() * 100.0),
            }
        )
    pd.DataFrame(stop_rows).to_csv(OUT_DIR / "stop_survival_distribution.csv", index=False)

    cols_main = [
        "setup",
        "trades",
        "wr",
        "pf",
        "expectancy",
        "profit",
        "dd",
        "test_pf",
        "test_exp",
        "active_months",
        "monthly_pf_median",
        "bad_months_pf_lt_1",
        "min_year_exp",
        "robust_score",
    ]
    best_rows = robust.head(20).replace([np.inf, -np.inf], np.nan).to_dict("records")
    naive_rows = opt_sorted.head(20).replace([np.inf, -np.inf], np.nan).to_dict("records")
    lucid_rows = lucid.sort_values("score", ascending=False).head(10).replace([np.inf, -np.inf], np.nan).to_dict("records")
    sizing_rows = sizing_rules.head(10).replace([np.inf, -np.inf], np.nan).to_dict("records")
    sized_lucid_rows = sized_lucid.replace([np.inf, -np.inf], np.nan).to_dict("records")

    report = []
    report.append("# Edge Optimization Report\n")
    report.append(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    report.append(f"Source: `{RUN_DIR}`\n")
    report.append(
        f"Raw X10 result files: {len(all_events)}. Executed trades used for optimization: {len(trades)}. "
        f"TIME_OVER/no-entry events excluded from trade optimization: {len(all_events) - len(trades)}.\n"
    )
    report.append("Simulation rule for alternative TP/SL: conservative path proxy from observed MFE/MAE. If both target and stop are reachable in one trade, stop is counted first. If neither is reached, observed terminal ticks are clipped to TP/SL. This is deliberately pessimistic and not a tick-by-tick re-run.\n")

    report.append("## Baseline Actual\n")
    report.append(md_table([{**baseline_metrics}], ["trades", "wr", "pf", "expectancy", "profit", "dd", "avg_mfe", "avg_mae", "avg_rr", "std", "max_w_streak", "max_l_streak"]))
    report.append("\n")

    report.append("## Recommended Robust Candidate\n")
    report.append(f"Setup: `{best_setup}`\n")
    report.append(md_table([{**best_metrics, "top_month_contribution_pct": top_contrib, "top_month": top_month}], ["trades", "wr", "pf", "expectancy", "profit", "dd", "avg_mfe", "avg_mae", "avg_rr", "std", "max_w_streak", "max_l_streak", "top_month_contribution_pct", "top_month"]))
    report.append("\n")

    report.append("## Top Robust Candidates\n")
    report.append(md_table(best_rows, cols_main, max_rows=20))
    report.append("\n")

    report.append("## Top Naive Candidates (Higher Overfit Risk)\n")
    report.append(md_table(naive_rows, cols_main, max_rows=20))
    report.append("\n")

    report.append("## Lucid 150k Monte Carlo For Recommended Candidate\n")
    report.append(f"3-month horizon uses observed frequency: {trades_per_month:.2f} trades/month -> {int(round(trades_per_month * 3))} trades per simulation.\n")
    report.append(md_table(lucid_rows, ["contracts", "pass_pct_3mo", "bust_pct_3mo", "timeout_pct_3mo", "avg_trades_to_pass", "dd_95_usd", "score"], max_rows=10))
    report.append("\n")

    report.append("## Score-Based Dynamic Sizing 1/3/4\n")
    report.append(
        f"Requested sizing layer: likely trades -> {HIGH_CONTRACTS} contracts, "
        f"least likely trades -> {LOW_CONTRACTS} contract. Middle bucket kept at {MID_CONTRACTS} contracts.\n"
    )
    report.append(
        f"Selected rule: `{best_sizing_rule['sizing_rule']}`. "
        f"High score cutoff = {high_cut:.2f}; low score cutoff = {low_cut:.2f}.\n"
    )
    report.append(md_table([{**sized_metrics}], ["trades", "wr", "pf", "expectancy_usd", "profit_usd", "dd_usd", "avg_mfe", "avg_mae", "avg_rr", "std_usd", "max_w_streak", "max_l_streak"]))
    report.append("\n")
    report.append("Top sizing threshold rules:\n")
    report.append(md_table(sizing_rows, ["sizing_rule", "high_score_cutoff", "low_score_cutoff", "trades", "profit_usd", "expectancy_usd", "dd_usd", "pf", "test_expectancy_usd", "test_dd_usd", "contracts_avg", "contracts_1_count", "contracts_mid_count", "contracts_4_count", "risk_score"], max_rows=10))
    report.append("\n")
    report.append("Lucid 150k with dynamic sizing distribution:\n")
    report.append(md_table(sized_lucid_rows, ["sizing", "pass_pct_3mo", "bust_pct_3mo", "timeout_pct_3mo", "avg_trades_to_pass", "dd_95_usd"], max_rows=10))
    report.append("\n")

    report.append("## Monte Carlo Drawdown For Recommended Candidate\n")
    report.append(md_table([mc], ["sims", "horizon_trades", "final_mean", "dd_mean", "dd_95", "dd_99", "loss_streak_mean", "p_loss_streak_3", "p_loss_streak_5", "p_loss_streak_8", "p_loss_streak_10"]))
    report.append("\n")
    report.append("## Monte Carlo Drawdown With Dynamic Sizing 1/3/4\n")
    report.append(md_table([sized_mc], ["sims", "horizon_trades", "final_mean", "dd_mean", "dd_95", "dd_99", "loss_streak_mean", "p_loss_streak_3", "p_loss_streak_5", "p_loss_streak_8", "p_loss_streak_10"]))
    report.append("\n")

    report.append("## Interpretation\n")
    report.append("- Use `Top Robust Candidates` for decision-making. `Top Naive Candidates` is included to expose what pure curve-fitting would prefer.\n")
    report.append("- A candidate is only considered robust if it has at least 80 trades, at least 18 active months, at least 20 trades in 2025-2026, positive total expectancy, and positive 2025-2026 expectancy.\n")
    report.append("- If a naive candidate has very high PF but low active months/trades, treat it as overfit until replayed out-of-sample.\n")
    report.append("- Profile-shape optimization (P/b/D/Trend/Tree) was not performed because v11 CSVs do not populate a reliable profile-shape column for all trades.\n")

    (OUT_DIR / "README.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Report written: {OUT_DIR / 'README.md'}")
    print(f"Recommended setup: {best_setup}")


if __name__ == "__main__":
    main()
