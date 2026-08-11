"""Adversarial audit - independent recomputation from raw X10_R1 CSVs.

Read-only on originals. All outputs go to this folder.
Checks: lookahead (CVD label), leakage, multiple testing, concentration,
duplicates, execution feasibility (latency/slippage), ambiguous targets,
honest walk-forward of the selection process using at-entry-only features.
"""
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

RUN_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1")
REPORT_DIR = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\edge_optimization_fast_20260711_192450")
OUT_DIR = Path(__file__).resolve().parent

NAN_TOKENS = {"", "OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}


def fnum(v, default=np.nan):
    text = str(v or "").strip()
    if not text or text.upper() in NAN_TOKENS:
        return default
    try:
        return float(text.replace("+", ""))
    except ValueError:
        return default


def result_ticks(v):
    text = str(v or "").strip().upper()
    if text == "BE":
        return 0.0
    if text in NAN_TOKENS:
        return 0.0
    return fnum(text, 0.0)


def load():
    rows = []
    files = sorted(RUN_DIR.glob("score_trade_result_*_NY.csv"))
    for path in files:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            file_rows = list(reader)
        date = re.search(r"(\d{4}-\d{2}-\d{2})", path.name).group(1)
        for i, row in enumerate(file_rows):
            row["_file"] = path.name
            row["_row_index"] = i
            row["_date"] = row.get("fecha") or date
            rows.append(row)
    return files, rows


def summarize(x):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return dict(n=0, wr=np.nan, pf=np.nan, exp=np.nan, profit=0.0)
    gw = x[x > 0].sum()
    gl = -x[x < 0].sum()
    return dict(
        n=int(len(x)),
        wr=float((x > 0).mean() * 100),
        pf=float(gw / gl) if gl > 0 else math.inf,
        exp=float(x.mean()),
        profit=float(x.sum()),
    )


def sim_tp_sl(actual, mfe, mae, tp, sl):
    res = np.clip(actual, -sl, tp)
    both = (mfe >= tp) & (mae >= sl)
    hit_tp = (mfe >= tp) & ~both
    hit_sl = (mae >= sl) | both
    res = res.copy()
    res[hit_tp] = tp
    res[hit_sl] = -sl
    return res


def main():
    files, all_rows = load()
    report = {}

    # ---- 1. duplicates / event integrity ----
    multi_row_files = [r["_file"] for r in all_rows if r["_row_index"] > 0]
    date_counts = Counter(r["_date"] for r in all_rows if r["_row_index"] == 0)
    dup_dates = {d: c for d, c in date_counts.items() if c > 1}
    entry_keys = Counter(
        (r["_date"], (r.get("EntryTime_NY") or "").strip())
        for r in all_rows
        if (r.get("Side") or "").strip() and (r.get("Entry_price") or "").strip()
    )
    dup_entries = {k: c for k, c in entry_keys.items() if c > 1}
    report["integrity"] = {
        "files": len(files),
        "rows_total": len(all_rows),
        "files_with_extra_rows": len(set(multi_row_files)),
        "duplicate_dates": dup_dates,
        "duplicate_entry_keys": {f"{d} {t}": c for (d, t), c in dup_entries.items()},
    }

    # ---- executed trades only (first row per file, like the optimizer) ----
    trades = [
        r for r in all_rows
        if r["_row_index"] == 0
        and (r.get("Side") or "").strip()
        and (r.get("Entry_price") or "").strip()
    ]
    actual = np.array([result_ticks(r.get("result TP SL BE")) for r in trades])
    mfe = np.array([fnum(r.get("MFE_ticks")) for r in trades])
    mae = np.array([fnum(r.get("MAE_ticks")) for r in trades])
    cvd = np.array([(r.get("Cvd_Pullback_Label") or "Unknown").strip() for r in trades])
    result_label = np.array([(r.get("Result_Label") or "?").strip() for r in trades])
    year = np.array([int(r["_date"][:4]) for r in trades])
    month = np.array([r["_date"][:7] for r in trades])
    score = np.array([fnum(r.get("score total")) for r in trades])
    side = np.array([(r.get("Side") or "").strip() for r in trades])
    speed = np.array([(r.get("Speed_Profile") or "Unknown").strip() for r in trades])
    slip_result = np.array([fnum(r.get("Result_After_Slippage_Ticks")) for r in trades])
    subsecond = np.array([(r.get("Subsecond_Trade") or "").upper() == "TRUE" for r in trades])
    no_manage = np.array([(r.get("No_Gestionable_Por_Latencia") or "").upper() == "TRUE" for r in trades])
    same_update = np.array([(r.get("TP_And_SL_Hit_Same_Update") or "").upper() == "TRUE" for r in trades])
    dur_ms = np.array([fnum(r.get("Trade_Duration_Milliseconds")) for r in trades])

    report["counts"] = {"events": len(files), "executed_trades": len(trades)}

    # ---- 2. reproduce headline (cvd=Excelente TP100 SL40) ----
    mask = cvd == "Excelente"
    sim = sim_tp_sl(actual, mfe, mae, 100, 40)
    report["headline_reproduction"] = {
        "claimed": dict(n=342, wr=73.39, pf=3.01, exp=15.54),
        "recomputed": summarize(sim[mask]),
    }

    # ---- 3. lookahead proof: exit-time CVD label vs trade outcome ----
    xtab = defaultdict(Counter)
    for c, rl in zip(cvd, result_label):
        xtab[c][rl] += 1
    report["cvd_label_x_result"] = {c: dict(v) for c, v in xtab.items()}
    report["wr_actual_by_cvd_label"] = {
        c: summarize(actual[cvd == c]) for c in sorted(set(cvd))
    }
    # same headline sim applied to each label bucket
    report["sim100_40_by_cvd_label"] = {
        c: summarize(sim[cvd == c]) for c in sorted(set(cvd))
    }

    # ---- 4. multiple testing burden ----
    with open(REPORT_DIR / "all_candidates.csv", "r", encoding="utf-8-sig") as fh:
        n_candidates = sum(1 for _ in fh) - 1
    report["multiple_testing"] = {"setups_evaluated_in_all_candidates_csv": n_candidates}

    # ---- 5. concentration ----
    x = sim[mask]
    order = np.argsort(x)[::-1]
    total = x.sum()
    report["concentration"] = {
        "total_profit_ticks": float(total),
        "top5_trades_pct_of_profit": float(x[order[:5]].sum() / total * 100),
        "top10_trades_pct_of_profit": float(x[order[:10]].sum() / total * 100),
        "top20_trades_pct_of_profit": float(x[order[:20]].sum() / total * 100),
    }
    m_profit = defaultdict(float)
    for mm, v in zip(month[mask], x):
        m_profit[mm] += v
    m_sorted = sorted(m_profit.items(), key=lambda kv: kv[1], reverse=True)
    report["concentration"]["top3_months_pct_of_profit"] = float(
        sum(v for _, v in m_sorted[:3]) / total * 100
    )

    # ---- 6. execution feasibility ----
    report["execution"] = {
        "subsecond_trades": int(subsecond[mask].sum()),
        "no_gestionable_por_latencia": int(no_manage[mask].sum()),
        "tp_sl_same_update": int(same_update[mask].sum()),
        "duration_ms_p10_p50_p90": [
            float(np.nanpercentile(dur_ms[mask], p)) for p in (10, 50, 90)
        ],
        "exp_actual_no_slip": summarize(actual[mask]),
        "exp_actual_with_slippage_column": summarize(slip_result[mask][~np.isnan(slip_result[mask])]),
        "slippage_column_available_n": int((~np.isnan(slip_result[mask])).sum()),
    }

    # ---- 7. honest baselines (no CVD, at-entry info only) ----
    report["honest_baselines"] = {
        "all_trades_actual": summarize(actual),
        "all_trades_sim_100_40": summarize(sim),
        "score_ge_8_sim_100_40": summarize(sim[score >= 8]),
        "score_ge_9_sim_100_40": summarize(sim[score >= 9]),
    }

    # ---- 8. honest walk-forward of the SELECTION PROCESS ----
    # candidate filters restricted to at-entry information only
    bool_cols = [
        "Range_OK", "Body_OK", "Volume_OK", "Delta_OK", "VWAP_OK", "Speed_OK",
        "Volume_Increasing", "Delta_With_Side", "Price_Accepted_After_Imbalance",
        "Price_Rejected_After_Imbalance", "APlus_Structure", "APlus_Absorption",
        "APlus_Speed",
    ]
    bools = {
        c: np.array([(r.get(c) or "").upper() == "TRUE" for r in trades])
        for c in bool_cols
    }

    def entry_filters():
        out = [("ALL", np.ones(len(trades), dtype=bool))]
        for s in sorted(set(side)):
            out.append((f"side={s}", side == s))
        for s in sorted(set(speed)):
            out.append((f"speed={s}", speed == s))
        for th in [6, 7, 8, 9]:
            out.append((f"score>={th}", score >= th))
        for c, arr in bools.items():
            out.append((f"{c}=TRUE", arr))
            out.append((f"{c}=FALSE", ~arr))
        return out

    wf = []
    eval_years = [2023, 2024, 2025, 2026]
    for ey in eval_years:
        train_mask = year < ey
        test_mask = year == ey
        best_name, best_metric, best_tp, best_sl = None, -1e18, None, None
        for name, fm in entry_filters():
            tm = fm & train_mask
            if tm.sum() < 60:
                continue
            for tp in (60, 80, 100, 120):
                for sl in (30, 40, 50):
                    s = sim_tp_sl(actual, mfe, mae, tp, sl)
                    st = summarize(s[tm])
                    metric = st["exp"] * math.sqrt(st["n"])
                    if metric > best_metric:
                        best_metric = metric
                        best_name, best_tp, best_sl = name, tp, sl
        s = sim_tp_sl(actual, mfe, mae, best_tp, best_sl)
        chosen = dict(entry_filters())[best_name]
        wf.append({
            "eval_year": ey,
            "selected_on_train": f"{best_name} TP={best_tp} SL={best_sl}",
            "train": summarize(s[chosen & train_mask]),
            "oos": summarize(s[chosen & test_mask]),
        })
    report["walk_forward_at_entry_only"] = wf

    # ---- 9. also: what the lookahead filter does in walk-forward ----
    wf2 = []
    for ey in eval_years:
        test_mask = year == ey
        wf2.append({
            "eval_year": ey,
            "cvd_excelente_sim100_40_oos": summarize(sim[mask & test_mask]),
        })
    report["cvd_filter_by_year_for_reference"] = wf2

    out = OUT_DIR / "audit_results.json"

    def safe(v):
        if isinstance(v, dict):
            return {str(k): safe(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [safe(x) for x in v]
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return str(v)
        if isinstance(v, np.generic):
            return safe(v.item())
        return v

    out.write_text(json.dumps(safe(report), indent=2, ensure_ascii=False), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
