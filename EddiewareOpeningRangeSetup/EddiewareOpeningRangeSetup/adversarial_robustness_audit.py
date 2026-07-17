import csv
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RUN_DIR = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
    r"\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1"
)
RUN_LOG = BASE_DIR / "dst_2022_2026_reset_run_20260711_093203.log"
OUT_DIR = BASE_DIR / "outputs" / f"adversarial_audit_{datetime.now():%Y%m%d_%H%M%S}"

TP = 100.0
SL = 40.0
TICK_VALUE = 5.0
MC_SEED = 20260712
PERMUTATIONS = 300

TP_GRID = np.array([20, 30, 40, 50, 60, 80, 100, 120, 150, 200], dtype=float)
SL_GRID = np.array([20, 30, 40, 50, 60, 70, 80, 100], dtype=float)


def fnum(value, default=np.nan):
    if value is None:
        return default
    text = str(value).strip().replace("$", "").replace(",", "")
    if text.startswith("+"):
        text = text[1:]
    if not text or text.upper() in {"OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def result_ticks(row):
    direct = fnum(row.get("result TP SL BE"))
    if not math.isnan(direct):
        return direct
    label = str(row.get("Result_Label") or "").strip().upper()
    if label == "BE":
        return 0.0
    if label == "TP":
        return abs(fnum(row.get("TP_ticks"), 0.0))
    if label == "SL":
        return -abs(fnum(row.get("SL_ticks"), 0.0))
    return np.nan


def max_dd(values):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return 0.0
    curve = np.cumsum(values)
    peak = np.maximum.accumulate(np.r_[0.0, curve])[:-1]
    return float(np.max(peak - curve))


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


def profit_factor(values):
    values = np.asarray(values, dtype=float)
    gross_win = values[values > 0].sum()
    gross_loss = -values[values < 0].sum()
    if gross_loss == 0:
        return math.inf if gross_win > 0 else math.nan
    return float(gross_win / gross_loss)


def summarize(values, months=None):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {
            "trades": 0,
            "wr": np.nan,
            "pf": np.nan,
            "expectancy": np.nan,
            "profit": 0.0,
            "dd": 0.0,
            "std": np.nan,
            "max_w_streak": 0,
            "max_l_streak": 0,
            "avg_win": np.nan,
            "avg_loss": np.nan,
            "avg_rr": np.nan,
            "months": 0,
            "trades_per_month": np.nan,
        }
    wins = values[values > 0]
    losses = values[values < 0]
    max_w, max_l = streaks(values)
    month_count = len(set(months)) if months is not None else 0
    avg_loss_abs = -losses.mean() if len(losses) else np.nan
    return {
        "trades": int(len(values)),
        "wr": float((values > 0).mean() * 100),
        "pf": profit_factor(values),
        "expectancy": float(values.mean()),
        "profit": float(values.sum()),
        "dd": max_dd(values),
        "std": float(values.std(ddof=1)) if len(values) > 1 else np.nan,
        "max_w_streak": max_w,
        "max_l_streak": max_l,
        "avg_win": float(wins.mean()) if len(wins) else np.nan,
        "avg_loss": float(losses.mean()) if len(losses) else np.nan,
        "avg_rr": float(wins.mean() / avg_loss_abs) if len(wins) and avg_loss_abs > 0 else np.nan,
        "months": month_count,
        "trades_per_month": float(len(values) / month_count) if month_count else np.nan,
    }


def simulate_tp_sl(actual, mfe, mae, tp=TP, sl=SL):
    if tp < sl:
        raise ValueError(f"CONFIG_INVALID_RR: initial TP {tp} < initial SL {sl}")
    actual = np.asarray(actual, dtype=float)
    mfe = np.asarray(mfe, dtype=float)
    mae = np.asarray(mae, dtype=float)
    result = np.clip(actual, -sl, tp)
    both = (mfe >= tp) & (mae >= sl)
    hit_tp = (mfe >= tp) & ~both
    hit_sl = (mae >= sl) | both
    result = result.copy()
    result[hit_tp] = tp
    result[hit_sl] = -sl
    result[~np.isfinite(actual) | ~np.isfinite(mfe) | ~np.isfinite(mae)] = np.nan
    return result


def read_one_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle), {})
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    row["source_file"] = path.name
    row["source_date"] = match.group(1) if match else ""
    return row


def load_dataset():
    rows = [read_one_csv(path) for path in sorted(RUN_DIR.glob("score_trade_result_*_NY.csv"))]
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"No CSV files found in {RUN_DIR}")
    df["fecha"] = df.get("fecha", "").fillna("").astype(str)
    df.loc[df["fecha"].eq(""), "fecha"] = df.loc[df["fecha"].eq(""), "source_date"]
    df["date"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df["year"] = df["date"].dt.year
    for col in [
        "Entry_price",
        "Exit_price",
        "MFE_ticks",
        "MAE_ticks",
        "TP_ticks",
        "SL_ticks",
        "score total",
        "range",
        "Cvd_Excelente_Count",
        "Cvd_Normal_Count",
        "Cvd_Advertencia_Count",
        "Cvd_Riesgo_Reversion_Count",
        "Cvd_Total_Samples",
        "Cvd_Excelente_Pct",
    ]:
        df[col + "__num"] = df[col].map(fnum) if col in df.columns else np.nan
    df["actual_ticks"] = df.apply(result_ticks, axis=1)
    df["is_trade"] = (
        df.get("Side", "").fillna("").astype(str).str.strip().ne("")
        & np.isfinite(df["Entry_price__num"])
    )
    df["result_label_norm"] = df.get("Result_Label", "").fillna("").astype(str).str.upper().str.strip()
    return df


def planned_dates_from_log():
    if not RUN_LOG.exists():
        return []
    text = RUN_LOG.read_text(encoding="utf-8", errors="ignore")
    return re.findall(r"\[X10_R1\s+\d+/\d+\]\s+(\d{4}-\d{2}-\d{2})", text)


def monthly_table(df, mask, result):
    out = []
    work = df.loc[mask, ["month"]].copy()
    work["result"] = result[mask.to_numpy() if hasattr(mask, "to_numpy") else mask]
    for month, group in work.groupby("month", sort=True):
        s = summarize(group["result"].to_numpy())
        out.append({"month": month, **s})
    return pd.DataFrame(out)


def year_table(df, mask, result):
    out = []
    work = df.loc[mask, ["year"]].copy()
    work["result"] = result[mask.to_numpy() if hasattr(mask, "to_numpy") else mask]
    for year, group in work.groupby("year", sort=True):
        s = summarize(group["result"].to_numpy())
        out.append({"year": int(year), **s})
    return pd.DataFrame(out)


def label_metrics(df, result, label_col):
    out = []
    for label, group in df[df["is_trade"]].groupby(label_col, dropna=False, sort=True):
        idx = group.index.to_numpy()
        s = summarize(result[idx], group["month"].to_numpy())
        out.append({label_col: str(label), **s})
    return pd.DataFrame(out).sort_values(["trades", label_col], ascending=[False, True])


def score_bucket_metrics(df, mask, result):
    work = df.loc[mask, ["score total__num", "month"]].copy()
    work["result"] = result[mask.to_numpy() if hasattr(mask, "to_numpy") else mask]
    work = work[np.isfinite(work["score total__num"])]
    out = []
    scores = work["score total__num"].to_numpy()
    for pct in [10, 20, 30, 40, 50]:
        cutoff = np.nanquantile(scores, 1 - pct / 100)
        sub = work[work["score total__num"] >= cutoff]
        out.append({"bucket": f"top_{pct}pct", "cutoff": cutoff, **summarize(sub["result"].to_numpy(), sub["month"].to_numpy())})
    cutoff = np.nanquantile(scores, 0.50)
    sub = work[work["score total__num"] <= cutoff]
    out.append({"bucket": "bottom_50pct", "cutoff": cutoff, **summarize(sub["result"].to_numpy(), sub["month"].to_numpy())})
    for score, sub in work.groupby("score total__num", sort=True):
        out.append({"bucket": f"score={score:g}", "cutoff": score, **summarize(sub["result"].to_numpy(), sub["month"].to_numpy())})
    return pd.DataFrame(out)


def dynamic_sizing_audit(df, mask, result):
    work = df.loc[mask, ["score total__num", "date", "year"]].copy()
    work["result"] = result[mask.to_numpy() if hasattr(mask, "to_numpy") else mask]
    score = work["score total__num"].to_numpy(dtype=float)
    rows = []

    def apply_sizing(name, high_cut, low_cut, submask=None):
        submask = np.ones(len(work), dtype=bool) if submask is None else submask
        contracts = np.full(len(work), 3.0)
        contracts[score >= high_cut] = 4.0
        contracts[score <= low_cut] = 1.0
        pnl = work["result"].to_numpy(dtype=float) * contracts * TICK_VALUE
        sm = summarize(pnl[submask])
        rows.append({
            "rule": name,
            "high_cut": high_cut,
            "low_cut": low_cut,
            "avg_contracts": float(np.nanmean(contracts[submask])),
            "c1": int(np.sum((contracts == 1) & submask)),
            "c3": int(np.sum((contracts == 3) & submask)),
            "c4": int(np.sum((contracts == 4) & submask)),
            **sm,
        })
        return contracts, pnl

    high_all = np.nanquantile(score, 0.90)
    low_all = np.nanquantile(score, 0.30)
    apply_sizing("full_sample_top10_bottom30", high_all, low_all)

    train = work["year"].to_numpy() <= 2024
    test = work["year"].to_numpy() >= 2025
    high_train = np.nanquantile(score[train], 0.90)
    low_train = np.nanquantile(score[train], 0.30)
    apply_sizing("train_2022_2024_cutoffs_on_train", high_train, low_train, train)
    apply_sizing("train_2022_2024_cutoffs_on_2025_2026", high_train, low_train, test)

    wf_pnl = np.full(len(work), np.nan)
    for year in sorted(work["year"].dropna().unique()):
        year = int(year)
        prior = work["year"].to_numpy() < year
        current = work["year"].to_numpy() == year
        if not prior.any() or not current.any():
            continue
        high = np.nanquantile(score[prior], 0.90)
        low = np.nanquantile(score[prior], 0.30)
        contracts = np.full(len(work), 3.0)
        contracts[score >= high] = 4.0
        contracts[score <= low] = 1.0
        wf_pnl[current] = work["result"].to_numpy(dtype=float)[current] * contracts[current] * TICK_VALUE
    sm = summarize(wf_pnl[np.isfinite(wf_pnl)])
    rows.append({
        "rule": "expanding_walkforward_prior_year_cutoffs",
        "high_cut": np.nan,
        "low_cut": np.nan,
        "avg_contracts": np.nan,
        "c1": np.nan,
        "c3": np.nan,
        "c4": np.nan,
        **sm,
    })
    return pd.DataFrame(rows)


def robust_stats_for_mask(df, mask, result):
    monthly = monthly_table(df, pd.Series(mask, index=df.index), result)
    if monthly.empty:
        return {
            "active_months": 0,
            "monthly_pf_median": np.nan,
            "monthly_exp_cv": np.nan,
            "bad_months_pf_lt_1": 0,
        }
    pf_vals = monthly["pf"].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    exp_vals = monthly["expectancy"].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    bad = int((monthly["pf"].replace([np.inf, -np.inf], np.nan) < 1).sum())
    exp_cv = float(np.nanstd(exp_vals, ddof=1) / abs(np.nanmean(exp_vals))) if len(exp_vals) > 1 and np.nanmean(exp_vals) else np.nan
    return {
        "active_months": int(len(monthly)),
        "monthly_pf_median": float(np.nanmedian(pf_vals)) if len(pf_vals) else np.nan,
        "monthly_exp_cv": exp_cv,
        "bad_months_pf_lt_1": bad,
    }


def candidate_masks(df):
    work = df[df["is_trade"]].copy()
    n = len(work)
    masks = [("ALL_TRADES", np.ones(n, dtype=bool))]
    score = work["score total__num"].to_numpy(float)
    or_range = work["range__num"].to_numpy(float)
    q1, q2 = np.nanquantile(or_range, [1 / 3, 2 / 3])
    work["or_regime"] = np.where(or_range <= q1, "OR_small", np.where(or_range >= q2, "OR_large", "OR_mid"))
    work["vol_regime"] = np.where(or_range <= q1, "Low_vol", np.where(or_range >= q2, "High_vol", "Mid_vol"))
    for key in ["Side", "Speed_Profile", "Cvd_Pullback_Label", "or_regime", "vol_regime"]:
        for value in sorted(work[key].fillna("Unknown").astype(str).unique()):
            masks.append((f"{key}={value}", work[key].fillna("Unknown").astype(str).to_numpy() == value))
    for th in sorted(set(score[np.isfinite(score)])):
        masks.append((f"score>={th:g}", score >= th))
    for pct in [10, 20, 30, 40, 50]:
        cutoff = np.nanquantile(score, 1 - pct / 100)
        masks.append((f"top_score_{pct}pct(score>={cutoff:.2f})", score >= cutoff))
    for pct in [20, 33, 50, 67, 80]:
        cutoff = np.nanquantile(or_range, pct / 100)
        masks.append((f"range>={cutoff:.0f}", or_range >= cutoff))
        masks.append((f"range<={cutoff:.0f}", or_range <= cutoff))
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
    ]
    for key in bool_cols:
        val = work.get(key, "").fillna("").astype(str).str.upper().eq("TRUE").to_numpy()
        masks.append((f"{key}=TRUE", val))
        masks.append((f"{key}=FALSE", ~val))
    for side in sorted(work["Side"].fillna("").astype(str).unique()):
        for th in [6, 7, 8]:
            masks.append((f"side={side} AND score>={th}", (work["Side"].fillna("").astype(str).to_numpy() == side) & (score >= th)))
    for regime in sorted(work["or_regime"].unique()):
        for th in [6, 7, 8]:
            masks.append((f"regime={regime} AND score>={th}", (work["or_regime"].to_numpy() == regime) & (score >= th)))
    dedup = {}
    for name, mask in masks:
        key = mask.tobytes()
        if key not in dedup:
            dedup[key] = (name, mask)
    return work, list(dedup.values())


def candidate_score(values, months, years, mask):
    values = np.asarray(values, dtype=float)
    if mask.sum() == 0:
        return None
    s = summarize(values[mask])
    train = mask & (years <= 2024)
    test = mask & (years >= 2025)
    st = summarize(values[train])
    so = summarize(values[test])
    active_months = len(set(months[mask]))
    if s["trades"] == 0:
        return None
    month_df = pd.DataFrame({"month": months[mask], "value": values[mask]})
    month_exp = month_df.groupby("month")["value"].mean().to_numpy()
    month_pf = month_df.groupby("month")["value"].apply(lambda x: profit_factor(x.to_numpy())).replace([np.inf, -np.inf], np.nan)
    bad_months = int((month_pf < 1).sum())
    exp_cv = float(np.nanstd(month_exp, ddof=1) / abs(np.nanmean(month_exp))) if len(month_exp) > 1 and np.nanmean(month_exp) else np.nan
    pf_cap = min(s["pf"], 5.0) if np.isfinite(s["pf"]) else 5.0
    penalty = 1.0 + (exp_cv if np.isfinite(exp_cv) else 0.0) + bad_months / max(active_months, 1)
    robust_score = max(s["expectancy"], -100) * math.sqrt(max(s["trades"], 1)) * max(pf_cap, 0) / penalty
    return {
        **s,
        "train_trades": st["trades"],
        "train_pf": st["pf"],
        "train_exp": st["expectancy"],
        "test_trades": so["trades"],
        "test_pf": so["pf"],
        "test_exp": so["expectancy"],
        "active_months": active_months,
        "monthly_exp_cv": exp_cv,
        "bad_months_pf_lt_1": bad_months,
        "robust_score": robust_score,
    }


def search_best_candidate(work, masks, actual, mfe, mae):
    months = work["month"].to_numpy()
    years = work["year"].to_numpy(dtype=float)
    rows = []
    for name, mask in masks:
        if mask.sum() >= 20:
            score = candidate_score(actual, months, years, mask)
            if score:
                rows.append({"filter": name, "tp": "actual", "sl": "actual", **score})
        if mask.sum() < 50:
            continue
        for tp in TP_GRID:
            for sl in SL_GRID:
                if tp < sl:
                    continue
                sim = simulate_tp_sl(actual, mfe, mae, tp, sl)
                score = candidate_score(sim, months, years, mask)
                if not score or score["trades"] < 50:
                    continue
                rows.append({"filter": name, "tp": int(tp), "sl": int(sl), **score})
    all_rows = pd.DataFrame(rows)
    if all_rows.empty:
        return None, all_rows
    robust = all_rows[
        (all_rows["trades"] >= 80)
        & (all_rows["active_months"] >= 18)
        & (all_rows["test_trades"] >= 20)
        & (all_rows["expectancy"] > 0)
        & (all_rows["test_exp"] > 0)
    ].copy()
    if robust.empty:
        return all_rows.sort_values(["expectancy", "pf", "trades"], ascending=False).iloc[0].to_dict(), all_rows
    best = robust.sort_values(["robust_score", "test_exp", "trades"], ascending=False).iloc[0].to_dict()
    return best, all_rows


def summary_fast(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    wins = values[values > 0]
    losses = values[values < 0]
    return {
        "trades": int(len(values)),
        "wr": float((values > 0).mean() * 100),
        "pf": profit_factor(values),
        "expectancy": float(values.mean()),
        "profit": float(values.sum()),
        "dd": max_dd(values),
        "max_w_streak": streaks(values)[0],
        "max_l_streak": streaks(values)[1],
    }


def candidate_score_fast(values, month_codes, years, mask):
    selected = values[mask]
    s = summary_fast(selected)
    if not s:
        return None

    train = mask & (years <= 2024)
    test = mask & (years >= 2025)
    st = summary_fast(values[train]) or {"trades": 0, "pf": np.nan, "expectancy": np.nan}
    so = summary_fast(values[test]) or {"trades": 0, "pf": np.nan, "expectancy": np.nan}

    selected_months = month_codes[mask]
    unique_months = np.unique(selected_months)
    exp_vals = []
    bad_months = 0
    for month_code in unique_months:
        month_values = selected[selected_months == month_code]
        if len(month_values) == 0:
            continue
        exp_vals.append(float(np.mean(month_values)))
        month_pf = profit_factor(month_values)
        if np.isfinite(month_pf) and month_pf < 1:
            bad_months += 1

    exp_vals = np.asarray(exp_vals, dtype=float)
    exp_mean = float(np.nanmean(exp_vals)) if len(exp_vals) else np.nan
    exp_cv = (
        float(np.nanstd(exp_vals, ddof=1) / abs(exp_mean))
        if len(exp_vals) > 1 and exp_mean
        else np.nan
    )
    active_months = int(len(unique_months))
    pf_cap = min(s["pf"], 5.0) if np.isfinite(s["pf"]) else 5.0
    penalty = 1.0 + (exp_cv if np.isfinite(exp_cv) else 0.0) + bad_months / max(active_months, 1)
    robust_score = max(s["expectancy"], -100) * math.sqrt(max(s["trades"], 1)) * max(pf_cap, 0) / penalty
    return {
        **s,
        "train_trades": st["trades"],
        "train_pf": st["pf"],
        "train_exp": st["expectancy"],
        "test_trades": so["trades"],
        "test_pf": so["pf"],
        "test_exp": so["expectancy"],
        "active_months": active_months,
        "monthly_exp_cv": exp_cv,
        "bad_months_pf_lt_1": bad_months,
        "robust_score": robust_score,
    }


def candidate_score_perm(values, month_codes, month_count, years, mask):
    selected = values[mask]
    finite = np.isfinite(selected)
    if not finite.all():
        selected = selected[finite]
        selected_months = month_codes[mask][finite]
        selected_years = years[mask][finite]
    else:
        selected_months = month_codes[mask]
        selected_years = years[mask]

    trades = int(len(selected))
    if trades == 0:
        return None

    wins = selected[selected > 0]
    losses = selected[selected < 0]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    pf_value = gross_win / gross_loss if gross_loss > 0 else (math.inf if gross_win > 0 else math.nan)
    expectancy = float(selected.mean())
    wr = float((selected > 0).mean() * 100)

    train_values = selected[selected_years <= 2024]
    test_values = selected[selected_years >= 2025]
    test_trades = int(len(test_values))
    train_trades = int(len(train_values))
    train_exp = float(train_values.mean()) if train_trades else np.nan
    test_exp = float(test_values.mean()) if test_trades else np.nan
    train_pf = profit_factor(train_values) if train_trades else np.nan
    test_pf = profit_factor(test_values) if test_trades else np.nan

    counts = np.bincount(selected_months, minlength=month_count)
    sums = np.bincount(selected_months, weights=selected, minlength=month_count)
    positive_sums = np.bincount(selected_months, weights=np.where(selected > 0, selected, 0.0), minlength=month_count)
    negative_sums = np.bincount(selected_months, weights=np.where(selected < 0, -selected, 0.0), minlength=month_count)
    active = counts > 0
    active_months = int(active.sum())
    monthly_exp = sums[active] / counts[active]
    monthly_pf = np.full(month_count, np.nan)
    finite_loss = negative_sums > 0
    monthly_pf[finite_loss] = positive_sums[finite_loss] / negative_sums[finite_loss]
    monthly_pf[(negative_sums == 0) & (positive_sums > 0)] = math.inf
    bad_months = int(np.sum(np.isfinite(monthly_pf) & (monthly_pf < 1)))

    exp_mean = float(np.nanmean(monthly_exp)) if len(monthly_exp) else np.nan
    exp_cv = (
        float(np.nanstd(monthly_exp, ddof=1) / abs(exp_mean))
        if len(monthly_exp) > 1 and exp_mean
        else np.nan
    )
    pf_cap = min(pf_value, 5.0) if np.isfinite(pf_value) else 5.0
    penalty = 1.0 + (exp_cv if np.isfinite(exp_cv) else 0.0) + bad_months / max(active_months, 1)
    robust_score = max(expectancy, -100) * math.sqrt(max(trades, 1)) * max(pf_cap, 0) / penalty
    return {
        "trades": trades,
        "wr": wr,
        "pf": pf_value,
        "expectancy": expectancy,
        "profit": float(selected.sum()),
        "train_trades": train_trades,
        "train_pf": train_pf,
        "train_exp": train_exp,
        "test_trades": test_trades,
        "test_pf": test_pf,
        "test_exp": test_exp,
        "active_months": active_months,
        "monthly_exp_cv": exp_cv,
        "bad_months_pf_lt_1": bad_months,
        "robust_score": robust_score,
    }


def search_best_candidate_fast(work, masks, actual, mfe, mae):
    month_codes = pd.factorize(work["month"])[0]
    month_count = int(month_codes.max() + 1)
    years = work["year"].to_numpy(dtype=float)
    simulated = {
        (int(tp), int(sl)): simulate_tp_sl(actual, mfe, mae, tp, sl)
        for tp in TP_GRID
        for sl in SL_GRID
        if tp >= sl
    }
    best = None

    def maybe_take(candidate):
        nonlocal best
        if (
            candidate["trades"] < 80
            or candidate["active_months"] < 18
            or candidate["test_trades"] < 20
            or candidate["expectancy"] <= 0
            or candidate["test_exp"] <= 0
        ):
            return
        key = (candidate["robust_score"], candidate["test_exp"], candidate["trades"])
        best_key = (
            best["robust_score"],
            best["test_exp"],
            best["trades"],
        ) if best else (-np.inf, -np.inf, -np.inf)
        if key > best_key:
            best = candidate

    for name, mask in masks:
        count = int(mask.sum())
        if count >= 20:
            score = candidate_score_perm(actual, month_codes, month_count, years, mask)
            if score:
                maybe_take({"filter": name, "tp": "actual", "sl": "actual", **score})
        if count < 50:
            continue
        for (tp, sl), result in simulated.items():
            score = candidate_score_perm(result, month_codes, month_count, years, mask)
            if score:
                maybe_take({"filter": name, "tp": tp, "sl": sl, **score})

    return best


def permutation_mining_audit(work, masks, observed_best):
    rng = np.random.default_rng(MC_SEED)
    actual = work["actual_ticks"].to_numpy(float)
    mfe = work["MFE_ticks__num"].to_numpy(float)
    mae = work["MAE_ticks__num"].to_numpy(float)
    outcomes = np.column_stack([actual, mfe, mae])
    rows = []
    start = time.time()
    for i in range(PERMUTATIONS):
        if i % 10 == 0:
            elapsed = time.time() - start
            print(f"[permutation] {i}/{PERMUTATIONS} elapsed={elapsed:.1f}s", flush=True)
        perm = rng.permutation(len(work))
        shuffled = outcomes[perm]
        best = search_best_candidate_fast(work, masks, shuffled[:, 0], shuffled[:, 1], shuffled[:, 2])
        if best:
            rows.append({
                "iteration": i,
                "filter": best["filter"],
                "tp": best["tp"],
                "sl": best["sl"],
                "trades": best["trades"],
                "wr": best["wr"],
                "pf": best["pf"],
                "expectancy": best["expectancy"],
                "test_exp": best["test_exp"],
                "robust_score": best["robust_score"],
            })
    perm = pd.DataFrame(rows)
    if perm.empty:
        return perm, {}
    summary = {
        "permutations": int(len(perm)),
        "p_best_pf_ge_observed": float((perm["pf"] >= observed_best["pf"]).mean() * 100),
        "p_best_exp_ge_observed": float((perm["expectancy"] >= observed_best["expectancy"]).mean() * 100),
        "p_best_score_ge_observed": float((perm["robust_score"] >= observed_best["robust_score"]).mean() * 100),
        "perm_best_pf_p95": float(perm["pf"].quantile(0.95)),
        "perm_best_exp_p95": float(perm["expectancy"].quantile(0.95)),
        "perm_best_score_p95": float(perm["robust_score"].quantile(0.95)),
    }
    return perm, summary


def fmt(value, digits=2):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
        if math.isinf(float(value)):
            return "inf"
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def md_table(df, columns, limit=None):
    if df is None or df.empty:
        return "_sin filas_"
    view = df.loc[:, [c for c in columns if c in df.columns]].copy()
    if limit:
        view = view.head(limit)
    lines = ["| " + " | ".join(view.columns) + " |", "| " + " | ".join(["---"] * len(view.columns)) + " |"]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(fmt(row[c]) if isinstance(row[c], (int, float, np.number)) else str(row[c]).replace("|", "\\|") for c in view.columns) + " |")
    return "\n".join(lines)


def to_json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        value = float(obj)
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
    return obj


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_dataset()
    trade_df = df[df["is_trade"]].copy()

    actual = df["actual_ticks"].to_numpy(float)
    mfe = df["MFE_ticks__num"].to_numpy(float)
    mae = df["MAE_ticks__num"].to_numpy(float)
    sim = simulate_tp_sl(actual, mfe, mae, TP, SL)
    raw_mask = df["is_trade"]
    current_mask = raw_mask & df.get("Cvd_Pullback_Label", "").fillna("").astype(str).eq("Excelente")
    non_current_mask = raw_mask & ~current_mask

    planned = planned_dates_from_log()
    csv_dates = set(df["source_date"].astype(str))
    planned_unique = sorted(set(planned))
    missing_planned = sorted(set(planned_unique) - csv_dates)
    duplicate_dates = sorted(df["source_date"][df["source_date"].duplicated()].unique())
    date_mismatch = df[df["source_date"].astype(str) != df["fecha"].astype(str)][["source_file", "source_date", "fecha"]]

    key_results = pd.DataFrame([
        {"case": "raw_actual_all_trades", **summarize(actual[raw_mask], df.loc[raw_mask, "month"].to_numpy())},
        {"case": "no_cvd_filter_TP100_SL40", **summarize(sim[raw_mask], df.loc[raw_mask, "month"].to_numpy())},
        {"case": "current_reported_final_CVD_Excelente_TP100_SL40", **summarize(sim[current_mask], df.loc[current_mask, "month"].to_numpy())},
        {"case": "excluded_non_Excelente_TP100_SL40", **summarize(sim[non_current_mask], df.loc[non_current_mask, "month"].to_numpy())},
    ])

    monthly_current = monthly_table(df, current_mask, sim)
    yearly_current = year_table(df, current_mask, sim)
    monthly_no_cvd = monthly_table(df, raw_mask, sim)
    cvd_label = label_metrics(df, sim, "Cvd_Pullback_Label")
    cvd_worst = label_metrics(df, sim, "Cvd_Worst_Label")
    score_buckets = score_bucket_metrics(df, current_mask, sim)
    sizing = dynamic_sizing_audit(df, current_mask, sim)

    selected = df[current_mask].copy()
    selected_result = sim[current_mask.to_numpy()]
    selected["sim_TP100_SL40"] = selected_result
    selected["win_less_than_100"] = (selected["sim_TP100_SL40"] > 0) & (selected["sim_TP100_SL40"] < TP)
    selected["both_reachable_TP100_SL40"] = (selected["MFE_ticks__num"] >= TP) & (selected["MAE_ticks__num"] >= SL)
    selected["sl_reached"] = selected["MAE_ticks__num"] >= SL
    selected["tp_reached"] = selected["MFE_ticks__num"] >= TP
    selected["same_update_flag"] = selected.get("TP_And_SL_Hit_Same_Update", "").fillna("").astype(str).str.upper().eq("TRUE")
    selected["cvd_worst_not_excellent"] = selected.get("Cvd_Worst_Label", "").fillna("").astype(str).ne("Excelente")
    selected["dynamic_alarm"] = selected.get("Dynamic_Alarm_Triggered", "").fillna("").astype(str).str.upper().eq("TRUE")
    selected["result_bucket"] = np.select(
        [
            selected["sim_TP100_SL40"].eq(TP),
            selected["sim_TP100_SL40"].eq(-SL),
            selected["win_less_than_100"],
            selected["sim_TP100_SL40"].between(-SL + 1e-9, -1e-9),
            selected["sim_TP100_SL40"].eq(0),
        ],
        ["+100 target", "-40 stop", "positive before +100", "negative before -40", "zero"],
        default="other",
    )
    target_bucket = selected.groupby("result_bucket")["sim_TP100_SL40"].agg(["count", "mean", "sum"]).reset_index()
    ambiguity = {
        "selected_trades": int(len(selected)),
        "wins_less_than_100": int(selected["win_less_than_100"].sum()),
        "wins_less_than_100_pct_of_selected": float(selected["win_less_than_100"].mean() * 100),
        "both_tp100_sl40_reachable_selected": int(selected["both_reachable_TP100_SL40"].sum()),
        "both_tp100_sl40_reachable_all_trades": int(((df["MFE_ticks__num"] >= TP) & (df["MAE_ticks__num"] >= SL) & raw_mask).sum()),
        "same_update_selected": int(selected["same_update_flag"].sum()),
        "same_update_all_trades": int((df.get("TP_And_SL_Hit_Same_Update", "").fillna("").astype(str).str.upper().eq("TRUE") & raw_mask).sum()),
        "selected_final_excellent_but_worst_not_excellent": int(selected["cvd_worst_not_excellent"].sum()),
        "selected_dynamic_alarm_true": int(selected["dynamic_alarm"].sum()),
        "avg_exported_tp_ticks_selected": float(selected["TP_ticks__num"].mean()),
        "avg_exported_sl_ticks_selected": float(selected["SL_ticks__num"].mean()),
    }

    work, masks = candidate_masks(df)
    obs_best, all_candidates = search_best_candidate(
        work,
        masks,
        work["actual_ticks"].to_numpy(float),
        work["MFE_ticks__num"].to_numpy(float),
        work["MAE_ticks__num"].to_numpy(float),
    )
    pruned_masks = sum(1 for _, mask in masks if mask.sum() >= 50)
    search_space = {
        "unique_masks": int(len(masks)),
        "masks_with_at_least_50_trades": int(pruned_masks),
        "tp_grid": [int(x) for x in TP_GRID],
        "sl_grid": [int(x) for x in SL_GRID],
        "tp_sl_pairs": int(len(TP_GRID) * len(SL_GRID)),
        "approx_actual_plus_tp_sl_candidates": int(len(masks) + pruned_masks * len(TP_GRID) * len(SL_GRID)),
        "observed_best": obs_best,
    }

    perm_df, perm_summary = permutation_mining_audit(work, masks, obs_best)

    integrity = {
        "csv_files": int(len(df)),
        "planned_dates_from_run_log": int(len(planned_unique)),
        "missing_planned_dates": missing_planned,
        "duplicate_source_dates": duplicate_dates,
        "date_mismatch_rows": int(len(date_mismatch)),
        "executed_trades": int(raw_mask.sum()),
        "time_over": int(df["result_label_norm"].eq("TIME_OVER").sum()),
        "result_labels": df["result_label_norm"].value_counts(dropna=False).to_dict(),
        "exporter_versions": df.get("Exporter_VERSION", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
    }

    current_summary = summarize(sim[current_mask], df.loc[current_mask, "month"].to_numpy())
    no_cvd_summary = summarize(sim[raw_mask], df.loc[raw_mask, "month"].to_numpy())
    degradation = {
        "pf_drop_when_removing_final_cvd_filter": current_summary["pf"] - no_cvd_summary["pf"],
        "wr_drop_when_removing_final_cvd_filter": current_summary["wr"] - no_cvd_summary["wr"],
        "expectancy_drop_when_removing_final_cvd_filter": current_summary["expectancy"] - no_cvd_summary["expectancy"],
    }

    for name, table in [
        ("key_results.csv", key_results),
        ("monthly_current_final_cvd.csv", monthly_current),
        ("yearly_current_final_cvd.csv", yearly_current),
        ("monthly_no_cvd_filter.csv", monthly_no_cvd),
        ("cvd_label_audit.csv", cvd_label),
        ("cvd_worst_label_audit.csv", cvd_worst),
        ("score_bucket_audit.csv", score_buckets),
        ("sizing_audit.csv", sizing),
        ("target_result_buckets.csv", target_bucket),
        ("all_candidates_replayed_search.csv", all_candidates),
        ("permutation_best_candidates.csv", perm_df),
        ("date_mismatches.csv", date_mismatch),
    ]:
        table.to_csv(OUT_DIR / name, index=False, encoding="utf-8-sig")

    examples = selected[
        selected["win_less_than_100"]
        | selected["both_reachable_TP100_SL40"]
        | selected["cvd_worst_not_excellent"]
        | selected["dynamic_alarm"]
    ].copy()
    example_cols = [
        "fecha",
        "EntryTime_NY",
        "Side",
        "score total",
        "Cvd_Pullback_Label",
        "Cvd_Worst_Label",
        "Dynamic_Alarm_Triggered",
        "Result_Label",
        "result TP SL BE",
        "MFE_ticks",
        "MAE_ticks",
        "TP_ticks",
        "SL_ticks",
        "sim_TP100_SL40",
        "result_bucket",
        "source_file",
    ]
    examples[[c for c in example_cols if c in examples.columns]].to_csv(
        OUT_DIR / "leakage_and_target_examples.csv",
        index=False,
        encoding="utf-8-sig",
    )

    audit = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_dir": str(RUN_DIR),
        "out_dir": str(OUT_DIR),
        "integrity": integrity,
        "current_summary": current_summary,
        "no_cvd_summary": no_cvd_summary,
        "degradation_without_final_cvd": degradation,
        "ambiguity": ambiguity,
        "search_space": search_space,
        "permutation_summary": perm_summary,
    }
    (OUT_DIR / "audit_summary.json").write_text(json.dumps(to_json_safe(audit), indent=2), encoding="utf-8")

    hard_findings = []
    if ambiguity["selected_final_excellent_but_worst_not_excellent"] > 0:
        hard_findings.append(
            f"{ambiguity['selected_final_excellent_but_worst_not_excellent']} trades filtrados como CVD final Excelente tuvieron peor estado CVD no Excelente durante el trade."
        )
    if ambiguity["selected_dynamic_alarm_true"] > 0:
        hard_findings.append(
            f"{ambiguity['selected_dynamic_alarm_true']} trades filtrados como CVD final Excelente dispararon alarma dinamica intratrade."
        )
    if ambiguity["wins_less_than_100"] > 0:
        hard_findings.append(
            f"{ambiguity['wins_less_than_100']} de {ambiguity['selected_trades']} trades del candidato ganan menos de +100 ticks; TP100 no es un target limpio 2.5:1."
        )
    if missing_planned:
        hard_findings.append(f"Faltan CSVs para fechas planeadas: {', '.join(missing_planned)}.")

    report = [
        "# Auditoria adversarial de robustez - Opening Range Setup",
        f"Generado: {audit['generated']}",
        f"Dataset: `{RUN_DIR}`",
        "",
        "## Veredicto corto",
        "El resultado reportado `cvd=Excelente | TP=100 SL=40` NO queda aceptado como edge causal en esta auditoria.",
        "La razon principal es que `Cvd_Pullback_Label` se exporta como estado dinamico del trade y el optimizador lo lee del CSV final. En codigo, el trade nace con CVD `Excelente`, pero el archivo final contiene el estado al cierre/rewrite posterior. Por tanto, filtrar por CVD final `Excelente` es look-ahead/leakage si se usa como condicion de entrada.",
        "",
        "## Resultados clave",
        md_table(key_results, ["case", "trades", "months", "trades_per_month", "wr", "pf", "expectancy", "profit", "dd", "max_w_streak", "max_l_streak"]),
        "",
        "## Alertas duras",
        "\n".join(f"- {x}" for x in hard_findings) if hard_findings else "- No hubo alerta dura automatica, revisar hallazgos manuales.",
        "",
        "## Integridad",
        f"- CSVs encontrados: {integrity['csv_files']}",
        f"- Fechas planeadas en log: {integrity['planned_dates_from_run_log']}",
        f"- Trades ejecutados: {integrity['executed_trades']}",
        f"- TIME_OVER: {integrity['time_over']}",
        f"- Fechas faltantes planeadas: {', '.join(missing_planned) if missing_planned else 'ninguna'}",
        f"- Fechas duplicadas: {', '.join(duplicate_dates) if duplicate_dates else 'ninguna'}",
        "",
        "## Evidencia de leakage CVD",
        "Referencias de codigo:",
        "- `ATASScoreTradeResultExporter.cs`: `CvdPullbackLabel = \"Excelente\"` al crear el trade.",
        "- `ATASScoreTradeResultExporter.cs`: `UpdateCvdPullback(...)` corre durante la vida del trade antes de reescribir el CSV.",
        "- `edge_optimization_fast.py`: el optimizador filtra con `row.get(\"Cvd_Pullback_Label\")` del CSV final.",
        "",
        md_table(cvd_label, ["Cvd_Pullback_Label", "trades", "wr", "pf", "expectancy", "profit", "dd"], limit=20),
        "",
        "Comparacion directa:",
        f"- PF con filtro CVD final Excelente: {fmt(current_summary['pf'])}",
        f"- PF sin usar CVD final: {fmt(no_cvd_summary['pf'])}",
        f"- Caida de PF al quitar la variable sospechosa: {fmt(degradation['pf_drop_when_removing_final_cvd_filter'])}",
        "",
        "## Ambiguedad del target TP100/SL40",
        md_table(target_bucket, ["result_bucket", "count", "mean", "sum"]),
        "",
        f"- Trades con TP y SL teoricamente alcanzables en la misma simulacion MFE/MAE: {ambiguity['both_tp100_sl40_reachable_selected']} seleccionados, {ambiguity['both_tp100_sl40_reachable_all_trades']} en todos los trades.",
        f"- Trades seleccionados con flag `TP_And_SL_Hit_Same_Update`: {ambiguity['same_update_selected']}.",
        f"- TP exportado promedio seleccionado: {fmt(ambiguity['avg_exported_tp_ticks_selected'])} ticks; SL exportado promedio seleccionado: {fmt(ambiguity['avg_exported_sl_ticks_selected'])} ticks.",
        "",
        "## Robustez temporal del candidato sospechoso",
        md_table(yearly_current, ["year", "trades", "wr", "pf", "expectancy", "profit", "dd", "max_w_streak", "max_l_streak"]),
        "",
        "## Ranking y sizing",
        "El sizing solicitado tambien queda bajo reserva: los cortes se calculan con toda la muestra. Ademas, por discretizacion del score, la regla top10/bottom30 casi no deja zona media.",
        md_table(sizing, ["rule", "high_cut", "low_cut", "avg_contracts", "c1", "c3", "c4", "trades", "wr", "pf", "expectancy", "profit", "dd"]),
        "",
        "## Calidad del ranking score",
        md_table(score_buckets, ["bucket", "cutoff", "trades", "wr", "pf", "expectancy", "profit", "dd"], limit=20),
        "",
        "## Riesgo de multiple testing / overfitting",
        f"- Mascaras unicas probadas: {search_space['unique_masks']}",
        f"- Mascaras con >=50 trades: {search_space['masks_with_at_least_50_trades']}",
        f"- Pares TP/SL por mascara: {search_space['tp_sl_pairs']}",
        f"- Candidatos aproximados en busqueda: {search_space['approx_actual_plus_tp_sl_candidates']}",
        "",
        "Mejor candidato observado por la misma busqueda:",
        md_table(pd.DataFrame([obs_best]), ["filter", "tp", "sl", "trades", "wr", "pf", "expectancy", "test_exp", "robust_score"]),
        "",
        "Permutacion de outcomes contra features:",
        md_table(pd.DataFrame([perm_summary]), ["permutations", "p_best_pf_ge_observed", "p_best_exp_ge_observed", "p_best_score_ge_observed", "perm_best_pf_p95", "perm_best_exp_p95", "perm_best_score_p95"]),
        "",
        "## Archivos generados",
        f"- `{OUT_DIR / 'audit_summary.json'}`",
        f"- `{OUT_DIR / 'key_results.csv'}`",
        f"- `{OUT_DIR / 'cvd_label_audit.csv'}`",
        f"- `{OUT_DIR / 'leakage_and_target_examples.csv'}`",
        f"- `{OUT_DIR / 'permutation_best_candidates.csv'}`",
    ]
    report_path = OUT_DIR / "README.md"
    report_path.write_text("\n\n".join(report), encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
