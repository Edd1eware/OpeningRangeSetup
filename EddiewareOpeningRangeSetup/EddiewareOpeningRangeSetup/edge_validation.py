"""Causal, time-aware validation of the ORB fade edge."""

from __future__ import annotations

import math
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent
OUT = BASE / "outputs" / "edge_validation_20260630"
SCRATCH = Path(
    r"C:\Users\k_99_\AppData\Local\Temp\claude"
    r"\C--Users-k-99--Desktop\59a5d941-0bcb-4a83-9f25-1c27f99384b9\scratchpad"
)
WIDE_PATH = SCRATCH / "fade_wide_matrix.pkl"
FULL_PATH = SCRATCH / "full_mbo.pkl"
TICK_LABELS = OUT / "tick_labels_127.csv"
FULL_TICK_LABELS = OUT / "tick_labels_486.csv"

# Exclude "stacked": its builder sees the rest of the breakout minute.
CAUSAL_FEATURES = [
    "orsz", "prev_orsz", "gap",
    "iceberg", "pulling", "stacking", "aggr_max", "sweeps", "absorb_sz",
    "cancel_bid_pct", "cancel_ask_pct", "lifetime_ms", "repeated",
    "aggr_imb", "or_vol",
    "va", "dvwap", "delta", "cvd", "mtps", "tps", "topbook", "oratr",
    "secs", "poc", "imbedge", "dmatch", "sprint", "dva", "voledge", "ortrend",
]


@dataclass(frozen=True)
class Condition:
    feature: str
    op: str
    threshold: float

    def mask(self, frame: pd.DataFrame) -> np.ndarray:
        values = frame[self.feature].to_numpy(dtype=float)
        return values <= self.threshold if self.op == "<=" else values >= self.threshold

    def text(self) -> str:
        return f"{self.feature}{self.op}{self.threshold:.6g}"


def wilson(wins: int, n: int, alpha: float = 0.05, tests: int = 1) -> tuple[float, float]:
    if n == 0:
        return math.nan, math.nan
    z = NormalDist().inv_cdf(1 - alpha / (2 * max(1, tests)))
    p = wins / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return center - half, center + half


def metrics(y, name: str = "") -> dict:
    values = np.asarray(y, dtype=int)
    n = len(values)
    wins = int(values.sum())
    losses = n - wins
    wr = wins / n if n else math.nan
    lo, hi = wilson(wins, n)
    pf = wins / losses if losses else math.inf
    return dict(
        rule=name, n=n, wins=wins, losses=losses, wr=wr, pf=pf,
        ci95_low=lo, ci95_high=hi,
        ev_ticks=30 * (2 * wr - 1) if n else math.nan,
        pf_after_2t=(wins * 28 / (losses * 32)) if losses else math.inf,
    )


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, int, int, int]:
    with WIDE_PATH.open("rb") as handle:
        wide = pd.DataFrame(pickle.load(handle))
    with FULL_PATH.open("rb") as handle:
        full = pd.DataFrame(pickle.load(handle))
    wide = wide.sort_values("date").reset_index(drop=True)
    full = full.sort_values("date").reset_index(drop=True)

    exact = pd.read_csv(TICK_LABELS, dtype={"date": str})
    if exact["y_tick"].isna().any():
        bad = exact.loc[exact["y_tick"].isna(), ["date", "status"]]
        raise RuntimeError(f"Missing exact labels:\n{bad.to_string(index=False)}")
    exact["y_tick"] = exact["y_tick"].astype(int)
    wide = wide.merge(exact[["date", "y_1s", "y_tick", "agrees"]], on="date", how="left")
    if wide["y_tick"].isna().any():
        raise RuntimeError("Tick labels do not cover the complete wide matrix")
    mismatches = int((wide["y"] != wide["y_tick"]).sum())
    wide["y_original_1s"] = wide["y"]
    wide["y"] = wide["y_tick"].astype(int)

    exact_full = pd.read_csv(FULL_TICK_LABELS, dtype={"date": str})
    if exact_full[["y_fade_tick", "y_cont_tick"]].isna().any().any():
        raise RuntimeError("Exact full-universe labels contain missing outcomes")
    full = full.merge(
        exact_full[["date", "y_fade_tick", "y_cont_tick"]], on="date", how="left"
    )
    fade_mismatches = int((full["y_fade"] != full["y_fade_tick"]).sum())
    cont_mismatches = int((full["y_cont"] != full["y_cont_tick"]).sum())
    full["y_fade"] = full["y_fade_tick"].astype(int)
    full["y_cont"] = full["y_cont_tick"].astype(int)
    return wide, full, mismatches, fade_mismatches, cont_mismatches


def fixed_rule_masks(w: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        "DOWN + prev>=140": np.ones(len(w), dtype=bool),
        "OR>=185": w["orsz"].to_numpy() >= 185,
        "OR>=185 + gap<0": (w["orsz"].to_numpy() >= 185) & (w["gap"].to_numpy() < 0),
        "dva<=14": w["dva"].to_numpy() <= 14,
        "imbedge<=0 + dva<=14": (w["imbedge"].to_numpy() <= 0) & (w["dva"].to_numpy() <= 14),
        "cancel_bid>=0.99 + dva<=14": (
            (w["cancel_bid_pct"].to_numpy() >= 0.99) & (w["dva"].to_numpy() <= 14)
        ),
        "absorb_sz<=23 + dva<=14": (
            (w["absorb_sz"].to_numpy() <= 23) & (w["dva"].to_numpy() <= 14)
        ),
        "OR>=185 + gap<0 + dva<=14": (
            (w["orsz"].to_numpy() >= 185)
            & (w["gap"].to_numpy() < 0)
            & (w["dva"].to_numpy() <= 14)
        ),
    }


def make_conditions(train: pd.DataFrame) -> list[Condition]:
    result = []
    for feature in CAUSAL_FEATURES:
        series = pd.to_numeric(train[feature], errors="coerce").dropna()
        if series.nunique() <= 1:
            continue
        thresholds = np.unique(series.quantile([0.20, 0.35, 0.50, 0.65, 0.80]).to_numpy(dtype=float))
        for threshold in thresholds:
            result += [
                Condition(feature, "<=", float(threshold)),
                Condition(feature, ">=", float(threshold)),
            ]
    return result


def selection_score(y: np.ndarray) -> tuple[float, float, int]:
    wins = int(y.sum())
    low, _ = wilson(wins, len(y))
    return low, wins / len(y), len(y)


def select_rule(train: pd.DataFrame, max_terms: int) -> tuple[list[Condition], dict]:
    conditions = make_conditions(train)
    min_n = max(15, math.ceil(0.25 * len(train)))
    y = train["y"].to_numpy(dtype=int)
    masks = [condition.mask(train) for condition in conditions]

    best_terms = []
    best_y = y
    best_score = selection_score(y)
    tested = 1

    for i, condition in enumerate(conditions):
        selected = y[masks[i]]
        if len(selected) < min_n:
            continue
        tested += 1
        score = selection_score(selected)
        if score > best_score:
            best_terms, best_y, best_score = [condition], selected, score

    if max_terms >= 2:
        for i, left in enumerate(conditions):
            for j in range(i + 1, len(conditions)):
                right = conditions[j]
                if left.feature == right.feature:
                    continue
                selected = y[masks[i] & masks[j]]
                if len(selected) < min_n:
                    continue
                tested += 1
                score = selection_score(selected)
                if score > best_score:
                    best_terms, best_y, best_score = [left, right], selected, score

    desc = "ALL" if not best_terms else " & ".join(term.text() for term in best_terms)
    return best_terms, dict(
        selected_rule=desc,
        train_n=len(best_y),
        train_wr=float(best_y.mean()),
        train_wilson_low=best_score[0],
        candidates_tested=tested,
    )


def nested_walkforward(w: pd.DataFrame, max_terms: int) -> tuple[pd.DataFrame, np.ndarray]:
    boundaries = np.linspace(42, len(w), 6).round().astype(int)
    rows, all_test_y = [], []
    for fold, (train_end, test_end) in enumerate(zip(boundaries[:-1], boundaries[1:]), start=1):
        train = w.iloc[:train_end]
        test = w.iloc[train_end:test_end]
        terms, info = select_rule(train, max_terms=max_terms)
        mask = np.ones(len(test), dtype=bool)
        for term in terms:
            mask &= term.mask(test)
        test_y = test.loc[mask, "y"].to_numpy(dtype=int)
        all_test_y.extend(test_y.tolist())
        result = metrics(test_y)
        rows.append(dict(
            fold=fold,
            train_end=w.iloc[train_end - 1]["date"],
            test_start=test.iloc[0]["date"],
            test_end=test.iloc[-1]["date"],
            **info,
            test_n=result["n"],
            test_wins=result["wins"],
            test_wr=result["wr"],
            test_pf=result["pf"],
        ))
    return pd.DataFrame(rows), np.asarray(all_test_y, dtype=int)


def router_walkforward(full: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    f = full.dropna(subset=["prev_orsz", "gap"]).copy().reset_index(drop=True)
    f["or_bin"] = pd.cut(
        f["orsz"], [-np.inf, 140, 185, np.inf],
        right=False, labels=["low", "mid", "wide"],
    )
    f["prev_bin"] = np.where(f["prev_orsz"] >= 140, "wide", "low")
    f["gap_bin"] = np.where(f["gap"] < 0, "neg", "pos")
    keys = ["dir", "or_bin", "prev_bin", "gap_bin"]
    boundaries = np.linspace(180, len(f), 6).round().astype(int)

    rows, oos = [], []
    for fold, (train_end, test_end) in enumerate(zip(boundaries[:-1], boundaries[1:]), start=1):
        train = f.iloc[:train_end]
        test = f.iloc[train_end:test_end]
        policies = {}
        for cell, group in train.groupby(keys, observed=True):
            choices = []
            for action, label in [("FADE", "y_fade"), ("CONT", "y_cont")]:
                y = group[label].to_numpy(dtype=int)
                low, _ = wilson(int(y.sum()), len(y))
                choices.append((low, float(y.mean()), len(y), action, label))
            best = max(choices)
            if best[2] >= 12 and best[0] > 0.50:
                policies[cell] = (best[3], best[4])

        fold_y = []
        for _, row in test.iterrows():
            cell = tuple(row[key] for key in keys)
            policy = policies.get(cell)
            if policy is not None:
                fold_y.append(int(row[policy[1]]))
        oos.extend(fold_y)
        m = metrics(fold_y)
        rows.append(dict(
            fold=fold,
            train_end=train.iloc[-1]["date"],
            test_start=test.iloc[0]["date"],
            test_end=test.iloc[-1]["date"],
            policies=len(policies),
            test_sessions=len(test),
            trades=m["n"],
            wins=m["wins"],
            wr=m["wr"],
            pf=m["pf"],
        ))
    return pd.DataFrame(rows), np.asarray(oos, dtype=int)


def router_topk_walkforward(full: pd.DataFrame, top_k: int = 4) -> tuple[pd.DataFrame, np.ndarray]:
    """Select exactly the top K regime cells from each expanding train only."""
    f = full.dropna(subset=["prev_orsz", "gap"]).copy().reset_index(drop=True)
    f["or_bin"] = pd.cut(
        f["orsz"], [-np.inf, 140, 185, np.inf],
        right=False, labels=["low", "mid", "wide"],
    )
    f["prev_bin"] = np.where(f["prev_orsz"] >= 140, "wide", "low")
    f["gap_bin"] = np.where(f["gap"] < 0, "neg", "pos")
    keys = ["dir", "or_bin", "prev_bin", "gap_bin"]
    boundaries = np.linspace(180, len(f), 6).round().astype(int)
    rows, oos = [], []
    for fold, (train_end, test_end) in enumerate(zip(boundaries[:-1], boundaries[1:]), start=1):
        train, test = f.iloc[:train_end], f.iloc[train_end:test_end]
        candidates = []
        for cell, group in train.groupby(keys, observed=True):
            if len(group) < 8:
                continue
            actions = []
            for action, label in [("FADE", "y_fade"), ("CONT", "y_cont")]:
                y = group[label].to_numpy(dtype=int)
                low, _ = wilson(int(y.sum()), len(y))
                actions.append((low, float(y.mean()), len(y), action, label))
            best = max(actions)
            candidates.append((best[0], best[1], best[2], cell, best[3], best[4]))
        chosen = sorted(candidates, reverse=True)[:top_k]
        policies = {item[3]: (item[4], item[5]) for item in chosen}
        fold_y = []
        for _, row in test.iterrows():
            cell = tuple(row[key] for key in keys)
            policy = policies.get(cell)
            if policy:
                fold_y.append(int(row[policy[1]]))
        oos.extend(fold_y)
        m = metrics(fold_y)
        policy_text = "; ".join(
            f"{'/'.join(map(str, item[3]))}:{item[4]}" for item in chosen
        )
        rows.append(dict(
            fold=fold, train_end=train.iloc[-1]["date"],
            test_start=test.iloc[0]["date"], test_end=test.iloc[-1]["date"],
            selected_policies=policy_text, test_sessions=len(test),
            trades=m["n"], wins=m["wins"], wr=m["wr"], pf=m["pf"],
        ))
    return pd.DataFrame(rows), np.asarray(oos, dtype=int)


def full_regime_tables(full: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    f = full.dropna(subset=["prev_orsz", "gap"]).copy().reset_index(drop=True)
    f["or_bin"] = pd.cut(
        f["orsz"], [-np.inf, 140, 185, np.inf],
        right=False, labels=["low", "mid", "wide"],
    )
    f["prev_bin"] = np.where(f["prev_orsz"] >= 140, "wide", "low")
    f["gap_bin"] = np.where(f["gap"] < 0, "neg", "pos")
    keys = ["dir", "or_bin", "prev_bin", "gap_bin"]
    rows = []
    for cell, group in f.groupby(keys, observed=True):
        for action, label in [("FADE", "y_fade"), ("CONT", "y_cont")]:
            rows.append(dict(zip(keys, cell)) | dict(action=action) | metrics(group[label]))
    cells = pd.DataFrame(rows).sort_values(["wr", "n"], ascending=[False, False])

    # Static router reported in the prior memo, now evaluated with exact labels.
    selections = []
    a = f[(f["dir"] == "DOWN") & (f["prev_orsz"] >= 140)]
    selections.extend(a["y_fade"].astype(int).tolist())
    b = f[(f["dir"] == "UP") & (f["orsz"] >= 140) & (f["orsz"] < 185) & (f["prev_orsz"] >= 140)]
    selections.extend(b["y_cont"].astype(int).tolist())
    c = f[(f["dir"] == "UP") & (f["orsz"] < 140) & (f["prev_orsz"] < 140)]
    selections.extend(c["y_cont"].astype(int).tolist())
    top4 = []
    branches = [
        ((f["dir"] == "UP") & (f["orsz"] >= 140) & (f["orsz"] < 185) & (f["prev_orsz"] >= 140) & (f["gap"] >= 0), "y_cont"),
        ((f["dir"] == "DOWN") & (f["orsz"] < 140) & (f["prev_orsz"] >= 140) & (f["gap"] >= 0), "y_fade"),
        ((f["dir"] == "UP") & (f["orsz"] < 140) & (f["prev_orsz"] < 140) & (f["gap"] < 0), "y_cont"),
        ((f["dir"] == "DOWN") & (f["orsz"] >= 185) & (f["prev_orsz"] >= 140) & (f["gap"] < 0), "y_fade"),
    ]
    for mask, label in branches:
        top4.extend(f.loc[mask, label].astype(int).tolist())
    return cells, metrics(selections, "memo static router"), metrics(top4, "top4 static router")


def fmt_pct(value: float) -> str:
    return "—" if not np.isfinite(value) else f"{100 * value:.1f}%"


def fmt_num(value: float) -> str:
    return "∞" if value == math.inf else ("—" if not np.isfinite(value) else f"{value:.2f}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    w, full, mismatches, full_fade_mismatches, full_cont_mismatches = load_data()
    masks = fixed_rule_masks(w)

    cut = int(0.70 * len(w))
    fixed_rows = []
    for name, mask in masks.items():
        row = metrics(w.loc[mask, "y"], name)
        train = metrics(w.loc[mask & (np.arange(len(w)) < cut), "y"])
        test = metrics(w.loc[mask & (np.arange(len(w)) >= cut), "y"])
        row |= dict(
            train_n=train["n"], train_wr=train["wr"], train_pf=train["pf"],
            test_n=test["n"], test_wr=test["wr"], test_pf=test["pf"],
        )
        fixed_rows.append(row)
    fixed = pd.DataFrame(fixed_rows)
    fixed["wilson_low_9730_tests"] = [
        wilson(int(row.wins), int(row.n), tests=9730)[0] for row in fixed.itertuples()
    ]
    fixed.to_csv(OUT / "fixed_rules.csv", index=False)

    by_year = []
    for name, mask in masks.items():
        selected = w.loc[mask].assign(year=lambda x: x["date"].str[:4])
        for year, group in selected.groupby("year"):
            by_year.append(dict(year=year, **metrics(group["y"], name)))
    pd.DataFrame(by_year).to_csv(OUT / "fixed_rules_by_year.csv", index=False)

    wf_single, y_single = nested_walkforward(w, max_terms=1)
    wf_pair, y_pair = nested_walkforward(w, max_terms=2)
    wf_single.to_csv(OUT / "nested_walkforward_single.csv", index=False)
    wf_pair.to_csv(OUT / "nested_walkforward_pair.csv", index=False)

    router, y_router = router_walkforward(full)
    router.to_csv(OUT / "nested_router.csv", index=False)
    router_top4, y_router_top4 = router_topk_walkforward(full, top_k=4)
    router_top4.to_csv(OUT / "nested_router_top4.csv", index=False)
    cells, static_router, static_top4 = full_regime_tables(full)
    cells.to_csv(OUT / "full_regime_cells.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for name in [
        "DOWN + prev>=140", "OR>=185", "OR>=185 + gap<0",
        "dva<=14", "imbedge<=0 + dva<=14",
    ]:
        selected = w.loc[masks[name], ["date", "y"]]
        pnl = np.where(selected["y"].to_numpy() == 1, 30, -30).cumsum()
        ax.plot(pd.to_datetime(selected["date"]), pnl, marker=".", linewidth=1.5, label=name)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set(
        title="ORB fade — cumulative gross ticks (exact MBO labels)",
        ylabel="Gross ticks",
        xlabel="Date",
    )
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "equity_fixed_rules.png", dpi=160)
    plt.close(fig)

    table_lines = []
    for row in fixed.itertuples():
        table_lines.append(
            f"| {row.rule} | {row.wins}-{row.losses} | {fmt_pct(row.wr)} | "
            f"{fmt_num(row.pf)} | {fmt_pct(row.ci95_low)}–{fmt_pct(row.ci95_high)} | "
            f"{fmt_num(row.pf_after_2t)} | {row.test_n} / {fmt_pct(row.test_wr)} / {fmt_num(row.test_pf)} |"
        )
    ms = metrics(y_single)
    mp = metrics(y_pair)
    mr = metrics(y_router)
    mrt = metrics(y_router_top4)

    report = f"""# Validación del edge ORB — 30/06/2026

## Veredicto

- Relabel exacto MBO vs etiqueta 1 segundo: **{mismatches} discrepancias de 127**.
- Universo completo: **{full_fade_mismatches} discrepancias fade y {full_cont_mismatches} cont de 486**.
- **No quedó un edge confirmado para desplegar** después de corregir labels y usar selección temporal.
- Mejor candidato para un holdout futuro: **OR>=185 & gap<0**, siempre dentro de DOWN + prev>=140.
- stacked_levels fue excluida por lookahead dentro del minuto del breakout.

## Reglas fijas — TP30/SL30

| Regla | W-L | WR | PF bruto | IC95% WR | PF con 2 ticks de fricción | test 30%: n / WR / PF |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(table_lines)}

Con TP=SL, PF bruto es exactamente WR/(1-WR). Maximizar WR y PF es el mismo objetivo;
la defensa contra resultados ficticios es exigir n suficiente, estabilidad temporal y selección
sólo con pasado.

## Selección walk-forward anidada

| Selector | W-L | WR | PF | n |
|---|---:|---:|---:|---:|
| 1 condición | {ms['wins']}-{ms['losses']} | {fmt_pct(ms['wr'])} | {fmt_num(ms['pf'])} | {ms['n']} |
| hasta 2 condiciones | {mp['wins']}-{mp['losses']} | {fmt_pct(mp['wr'])} | {fmt_num(mp['pf'])} | {mp['n']} |
| router 486 sesiones | {mr['wins']}-{mr['losses']} | {fmt_pct(mr['wr'])} | {fmt_num(mr['pf'])} | {mr['n']} |
| router top-4 celdas, nested OOS | {mrt['wins']}-{mrt['losses']} | {fmt_pct(mrt['wr'])} | {fmt_num(mrt['pf'])} | {mrt['n']} |
| router estático del memo (IS) | {static_router['wins']}-{static_router['losses']} | {fmt_pct(static_router['wr'])} | {fmt_num(static_router['pf'])} | {static_router['n']} |
| top-4 celdas observado (IS) | {static_top4['wins']}-{static_top4['losses']} | {fmt_pct(static_top4['wr'])} | {fmt_num(static_top4['pf'])} | {static_top4['n']} |

Los CSV por fold muestran qué regla eligió cada train. El selector cambia de regla casi cada fold;
el router top-4 observado luce 71.9% in-sample, pero su proceso nested OOS cae a 54.8%.

## Lectura operativa

1. **Máximo observado:** OR>=185 + gap<0 + dva<=14 = 81.2% / PF 4.33 / n16. No desplegable.
2. **Máximo observado con n>=40:** cancel_bid>=0.99 + dva<=14 = 72.0% / PF 2.57 / n50,
   pero en el último 30% cae a 57.1% / PF 1.33.
3. **Candidato menos frágil:** OR>=185 + gap<0 = 70.4% / PF 2.38 / n27; necesita datos nuevos.
4. gap no es gap overnight: es el cambio del punto medio del OR actual respecto al OR previo.
5. Congelar el candidato y paper-tradear sin recalibrar. Con 40 trades futuros se puede reabrir
   el veredicto; antes de eso, tratarlo como hipótesis, no como edge confirmado.
"""
    (OUT / "edge_validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nArtifacts: {OUT}")


if __name__ == "__main__":
    main()
