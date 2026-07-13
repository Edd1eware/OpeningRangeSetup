"""Search causal ORB feature combinations with exact MBO labels.

The search has two deliberately different views:

1. An exhaustive/beam search for one interpretable conjunction of up to three
   threshold conditions.
2. A shallow decision-tree router which may choose FADE or CONT in disjoint
   leaves.  Its honest estimate is an expanding nested walk-forward; the tree
   fitted on all rows is only a descriptive in-sample result.

TP and SL are both 30 ticks. Therefore gross PF >= 4 and WR >= 80% are the
same target. A minimum of 101 trades represents one trade per calendar week on
average over the 101-week sample.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

import duckdb
import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR")
DB_PATH = ROOT / "data" / "orb_features.duckdb"
FULL_MBO = Path(
    r"C:\Users\k_99_\AppData\Local\Temp\claude"
    r"\C--Users-k-99--Desktop\59a5d941-0bcb-4a83-9f25-1c27f99384b9"
    r"\scratchpad\full_mbo.pkl"
)
LABELS = Path(
    r"C:\Users\k_99_\Documents\Indicador ATAS"
    r"\outputs\edge_validation_20260630\tick_labels_486.csv"
)
OUT_DIR = BASE / "outputs" / "feature_combo_search_20260701"

TARGET_WR = 0.80
TARGET_PF = 4.0
TARGET_TRADES = 101
TARGET_RATE = TARGET_TRADES / 486


def wilson_low(wins: int, n: int, alpha: float = 0.05) -> float:
    if not n:
        return math.nan
    z = NormalDist().inv_cdf(1 - alpha / 2)
    p = wins / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return center - half


def metrics(correct: np.ndarray) -> dict[str, float | int]:
    y = np.asarray(correct, dtype=int)
    n = int(len(y))
    wins = int(y.sum())
    losses = n - wins
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "wr": wins / n if n else math.nan,
        "pf_gross": wins / losses if losses else math.inf,
        "pf_after_2t": wins * 28 / (losses * 32) if losses else math.inf,
        "wilson_low": wilson_low(wins, n),
    }


def load_matrix() -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    bf = con.execute("SELECT * FROM breakout_features ORDER BY session_date").fetchdf()
    of = con.execute("SELECT * FROM orderflow_features ORDER BY session_date").fetchdf()
    con.close()

    bf["date"] = pd.to_datetime(bf.pop("session_date"))
    of["date"] = pd.to_datetime(of.pop("session_date"))
    with FULL_MBO.open("rb") as handle:
        old = pd.DataFrame(pickle.load(handle))
    old["date"] = pd.to_datetime(old["date"])

    labels = pd.read_csv(LABELS)
    labels["date"] = pd.to_datetime(labels["date"])
    if labels[["y_fade_tick", "y_cont_tick"]].isna().any().any():
        raise RuntimeError("Exact MBO labels contain missing outcomes")

    base = (
        bf.merge(of, on="date", suffixes=("_bf", "_of"), validate="one_to_one")
        .merge(old, on="date", validate="one_to_one")
        .merge(labels[["date", "y_fade_tick", "y_cont_tick"]], on="date", validate="one_to_one")
        .sort_values("date")
        .reset_index(drop=True)
    )
    if not np.array_equal(base["y_cont_tick"].to_numpy(), 1 - base["y_fade_tick"].to_numpy()):
        raise RuntimeError("FADE and CONT labels are not exact complements")

    features: dict[str, pd.Series] = {}
    features["direction_up"] = base["direction_bf"].eq("UP").astype(float)
    features["prev_orsz"] = pd.to_numeric(base["prev_orsz"], errors="coerce")
    features["gap"] = pd.to_numeric(base["gap"], errors="coerce")

    # Breakout/OR features accepted as causal in the prior audit. stacked_levels
    # is excluded because its old builder observes the rest of the breakout bar.
    bf_exclude = {"breakout_ts", "stacked_levels"}
    for column in bf.columns:
        if column in {"date", "direction"} | bf_exclude:
            continue
        if pd.api.types.is_numeric_dtype(bf[column]):
            features[f"bf_{column}"] = pd.to_numeric(base[column], errors="coerce")

    # Correct causal MBO detector, accumulated only through breakout_ns.
    of_exclude = {
        "breakout_ns", "feature_end_ns", "edge_price", "direction",
        "strongest_iceberg_order_id", "strongest_iceberg_price",
        # Controls/transport artifacts are not trading signals.
        "bad_ts_records", "bad_book_records", "aggregated_book_records", "mbo_records",
        # Added after the 01/07/2026 search.  Keep this historical script on
        # its frozen 95-feature universe so the published result reproduces.
        "aggr_imbalance_acceleration", "buy_impact_ticks_per_1000",
        "delta_price_alignment", "directional_efficiency",
        "edge_break_aggr_imbalance", "edge_break_trade_volume",
        "edge_break_volume_share", "edge_close_distance_ticks",
        "edge_excursion_ticks", "edge_rejection_ticks",
        "extreme_buy_aggr_volume", "extreme_sell_aggr_volume",
        "first_quarter_aggr_imbalance", "first_quarter_net_ticks",
        "last_quarter_aggr_imbalance", "last_quarter_net_ticks",
        "max_buy_run_count", "max_buy_run_volume", "max_sell_run_count",
        "max_sell_run_volume", "open_auction_score", "open_cross_count",
        "open_drive_flow_alignment", "open_drive_price_alignment",
        "open_drive_score", "open_rejection_reverse_ticks",
        "sell_impact_ticks_per_1000", "signed_impact_ticks_per_1000",
        "trade_sign_entropy", "trade_sign_flip_rate", "trade_sign_persistence",
        "trapped_aggressor_imbalance", "trapped_buy_aggr_volume",
        "trapped_sell_aggr_volume",
        # Added from the second (Bookmap/HFT/Forthmann) library audit.
        "book_add_ask_qty", "book_add_bid_qty", "book_cancel_add_ratio",
        "book_cancel_ask_qty", "book_cancel_bid_qty", "book_flip_count",
        "book_message_rate_per_s", "breakout_exhaustion_ratio",
        "breakout_extreme_aggr_volume", "breakout_inner_aggr_volume",
        "edge_book_add_ask_qty", "edge_book_add_bid_qty",
        "edge_book_cancel_ask_qty", "edge_book_cancel_bid_qty",
        "edge_liquidity_breakout_alignment", "edge_liquidity_imbalance",
        "last_quarter_volume_ratio", "liquidity_breakout_alignment",
        "liquidity_impulse", "liquidity_impulse_imbalance",
        "max_book_messages_per_100ms", "max_trades_per_100ms",
        "spoof_like_count", "spoof_like_qty", "spoof_like_bid_qty",
        "spoof_like_ask_qty", "spoof_like_imbalance",
        "spoof_like_breakout_alignment", "sweep_breakout_alignment",
        "sweep_buy_volume", "sweep_count", "sweep_imbalance",
        "sweep_sell_volume", "sweep_volume", "trade_rate_per_s",
        "trade_sign_ema_128", "trade_sign_ema_128_alignment",
        "trade_sign_ema_32", "trade_sign_ema_32_alignment",
        "trade_sign_ema_8", "trade_sign_ema_8_alignment", "vpin_20",
    }
    for column in of.columns:
        if column in {"date"} | of_exclude:
            continue
        source = base[column]
        if pd.api.types.is_numeric_dtype(source):
            features[f"of_{column}"] = pd.to_numeric(source, errors="coerce")
    side = base["strongest_iceberg_side"].fillna("").astype(str)
    features["of_strongest_iceberg_bid"] = side.eq("B").astype(float)
    features["of_strongest_iceberg_ask"] = side.eq("A").astype(float)

    # Older 09:30-09:31 MBO features add a distinct pre-breakout window. The
    # historical aggressor sign was inverted, so expose the corrected sign.
    old_exclude = {"date", "dir", "orsz", "prev_orsz", "gap", "y_fade", "y_cont"}
    for column in old.columns:
        if column in old_exclude:
            continue
        source = pd.to_numeric(base[column], errors="coerce")
        if column == "aggr_imb":
            source = -source
            name = "mbo0931_aggr_imb_corrected"
        else:
            name = f"mbo0931_{column}"
        features[name] = source

    X = pd.DataFrame(features)
    # Remove constants and exact duplicate columns, which only multiply tests.
    X = X.loc[:, X.nunique(dropna=True) > 1]
    X = X.T.drop_duplicates().T
    y_fade = base["y_fade_tick"].to_numpy(dtype=int)
    meta = base[["date", "direction_bf"]].rename(columns={"direction_bf": "direction"}).copy()
    return meta, X, y_fade


@dataclass(frozen=True)
class Condition:
    feature: str
    op: str
    threshold: float
    mask: int

    def text(self) -> str:
        return f"{self.feature} {self.op} {self.threshold:.6g}"


def mask_to_int(mask: np.ndarray) -> int:
    result = 0
    for i in np.flatnonzero(mask):
        result |= 1 << int(i)
    return result


def make_conditions(X: pd.DataFrame) -> list[Condition]:
    result: list[Condition] = []
    seen: set[tuple[str, str, int]] = set()
    for feature in X.columns:
        values = pd.to_numeric(X[feature], errors="coerce").to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        unique = np.unique(finite)
        if len(unique) <= 1:
            continue
        if len(unique) <= 12:
            thresholds = (unique[:-1] + unique[1:]) / 2
        else:
            thresholds = np.unique(np.quantile(finite, np.arange(0.1, 1.0, 0.1)))
            if finite.min() < 0 < finite.max():
                thresholds = np.unique(np.append(thresholds, 0.0))
        for threshold in thresholds:
            for op in ("<=", ">="):
                mask = np.isfinite(values) & ((values <= threshold) if op == "<=" else (values >= threshold))
                bits = mask_to_int(mask)
                key = (feature, op, bits)
                if bits and key not in seen:
                    seen.add(key)
                    result.append(Condition(feature, op, float(threshold), bits))
    return result


def rule_stats(mask: int, correct_bits: int) -> tuple[float, int, int, float]:
    n = mask.bit_count()
    wins = (mask & correct_bits).bit_count()
    wr = wins / n if n else 0.0
    return wr, wins, n, wilson_low(wins, n)


def conjunction_search(
    X: pd.DataFrame, y_fade: np.ndarray, min_n: int, max_depth: int = 3, pair_beam: int = 2500
) -> list[dict]:
    conditions = make_conditions(X)
    all_bits = (1 << len(X)) - 1
    fade_bits = mask_to_int(y_fade == 1)
    outputs = []
    for action, correct_bits in (("FADE", fade_bits), ("CONT", all_bits ^ fade_bits)):
        best: tuple[tuple[float, float, int], int, tuple[int, ...]] | None = None
        pairs: dict[int, tuple[tuple[float, float, int], tuple[int, int]]] = {}

        def consider(mask: int, terms: tuple[int, ...]) -> None:
            nonlocal best
            n = mask.bit_count()
            if n < min_n:
                return
            wr, wins, _, low = rule_stats(mask, correct_bits)
            score = (wr, low, n)
            if best is None or score > best[0]:
                best = (score, mask, terms)

        for i, condition in enumerate(conditions):
            consider(condition.mask, (i,))

        for i, left in enumerate(conditions):
            for j in range(i + 1, len(conditions)):
                mask = left.mask & conditions[j].mask
                if mask.bit_count() < min_n:
                    continue
                consider(mask, (i, j))
                wr, wins, n, low = rule_stats(mask, correct_bits)
                score = (wr, low, n)
                previous = pairs.get(mask)
                if previous is None or score > previous[0]:
                    pairs[mask] = (score, (i, j))

        if max_depth >= 3:
            top_pairs = sorted(pairs.items(), key=lambda item: item[1][0], reverse=True)[:pair_beam]
            for pair_mask, (_, terms) in top_pairs:
                last = terms[-1]
                for k in range(last + 1, len(conditions)):
                    mask = pair_mask & conditions[k].mask
                    if mask.bit_count() >= min_n:
                        consider(mask, terms + (k,))

        if best is None:
            continue
        score, mask, terms = best
        wr, wins, n, low = rule_stats(mask, correct_bits)
        losses = n - wins
        outputs.append(
            {
                "action": action,
                "conditions": [conditions[i].text() for i in terms],
                "n": n,
                "wins": wins,
                "losses": losses,
                "wr": wr,
                "pf_gross": wins / losses if losses else math.inf,
                "pf_after_2t": wins * 28 / (losses * 32) if losses else math.inf,
                "wilson_low": low,
            }
        )
    return outputs


@dataclass
class TreeNode:
    node_id: int
    n: int
    wins: int
    prediction: int
    feature: int | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None


class SimpleTree:
    def __init__(self, max_depth: int, min_leaf: int, max_features: int | None = None):
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.max_features = max_features
        self.root: TreeNode | None = None
        self.medians: np.ndarray | None = None
        self.feature_names: list[str] = []
        self._next_id = 0

    @staticmethod
    def _gini(y: np.ndarray) -> float:
        if not len(y):
            return 0.0
        p = y.mean()
        return 2 * p * (1 - p)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "SimpleTree":
        self.feature_names = list(X.columns)
        raw = X.to_numpy(dtype=float)
        self.medians = np.nanmedian(raw, axis=0)
        self.medians = np.where(np.isfinite(self.medians), self.medians, 0.0)
        values = np.where(np.isfinite(raw), raw, self.medians)
        self._next_id = 0
        self.root = self._build(values, np.asarray(y, dtype=int), np.arange(len(y)), 0)
        return self

    def _build(self, X: np.ndarray, y: np.ndarray, idx: np.ndarray, depth: int) -> TreeNode:
        node = TreeNode(self._next_id, len(idx), int(y[idx].sum()), int(y[idx].mean() >= 0.5))
        self._next_id += 1
        if depth >= self.max_depth or len(idx) < 2 * self.min_leaf or len(np.unique(y[idx])) == 1:
            return node
        parent_impurity = self._gini(y[idx])
        best_gain = 0.0
        best: tuple[int, float, np.ndarray, np.ndarray] | None = None
        feature_indices = np.arange(X.shape[1])
        if self.max_features and self.max_features < len(feature_indices):
            # Deterministic variance ranking avoids random-seed shopping.
            variances = np.var(X[idx], axis=0)
            feature_indices = np.argsort(variances)[-self.max_features:]
        for feature in feature_indices:
            column = X[idx, feature]
            unique = np.unique(column)
            if len(unique) <= 1:
                continue
            if len(unique) <= 12:
                thresholds = (unique[:-1] + unique[1:]) / 2
            else:
                thresholds = np.unique(np.quantile(column, np.arange(0.1, 1.0, 0.1)))
            for threshold in thresholds:
                left_mask = column <= threshold
                nl = int(left_mask.sum())
                nr = len(idx) - nl
                if nl < self.min_leaf or nr < self.min_leaf:
                    continue
                li = idx[left_mask]
                ri = idx[~left_mask]
                child = (nl * self._gini(y[li]) + nr * self._gini(y[ri])) / len(idx)
                gain = parent_impurity - child
                if gain > best_gain + 1e-12:
                    best_gain = gain
                    best = feature, float(threshold), li, ri
        if best is None:
            return node
        node.feature, node.threshold, li, ri = best
        node.left = self._build(X, y, li, depth + 1)
        node.right = self._build(X, y, ri, depth + 1)
        return node

    def apply(self, X: pd.DataFrame) -> np.ndarray:
        if self.root is None or self.medians is None:
            raise RuntimeError("Tree is not fitted")
        raw = X[self.feature_names].to_numpy(dtype=float)
        values = np.where(np.isfinite(raw), raw, self.medians)
        leaves = np.empty(len(values), dtype=int)
        for i, row in enumerate(values):
            node = self.root
            while node.feature is not None:
                node = node.left if row[node.feature] <= node.threshold else node.right
                assert node is not None
            leaves[i] = node.node_id
        return leaves

    def paths(self) -> dict[int, list[str]]:
        if self.root is None:
            return {}
        result: dict[int, list[str]] = {}

        def walk(node: TreeNode, path: list[str]) -> None:
            if node.feature is None:
                result[node.node_id] = path
                return
            name = self.feature_names[node.feature]
            assert node.left is not None and node.right is not None and node.threshold is not None
            walk(node.left, path + [f"{name} <= {node.threshold:.6g}"])
            walk(node.right, path + [f"{name} > {node.threshold:.6g}"])

        walk(self.root, [])
        return result


def select_leaves(leaves: np.ndarray, y: np.ndarray, min_trades: int) -> tuple[set[int], dict[int, int], list[dict]]:
    rows = []
    predictions: dict[int, int] = {}
    for leaf in np.unique(leaves):
        mask = leaves == leaf
        n = int(mask.sum())
        fade_wins = int(y[mask].sum())
        prediction = int(fade_wins >= n - fade_wins)
        wins = max(fade_wins, n - fade_wins)
        predictions[int(leaf)] = prediction
        rows.append(
            {
                "leaf": int(leaf), "n": n, "wins": wins,
                "wr": wins / n, "wilson_low": wilson_low(wins, n),
                "action": "FADE" if prediction else "CONT",
            }
        )
    rows.sort(key=lambda row: (row["wilson_low"], row["wr"], row["n"]), reverse=True)
    selected: set[int] = set()
    total = 0
    for row in rows:
        selected.add(row["leaf"])
        total += row["n"]
        if total >= min_trades:
            break
    return selected, predictions, rows


def evaluate_tree(
    tree: SimpleTree,
    X: pd.DataFrame,
    y: np.ndarray,
    selected: set[int],
    predictions: dict[int, int],
) -> tuple[dict, np.ndarray, np.ndarray]:
    leaves = tree.apply(X)
    trade = np.array([int(leaf) in selected for leaf in leaves], dtype=bool)
    pred = np.array([predictions.get(int(leaf), 0) for leaf in leaves], dtype=int)
    correct = (pred[trade] == y[trade]).astype(int)
    return metrics(correct), trade, pred


TREE_CONFIGS = [(d, leaf) for d in (2, 3, 4, 5) for leaf in (10, 15, 20, 25, 30)]


def best_static_tree(X: pd.DataFrame, y: np.ndarray, min_trades: int) -> tuple[SimpleTree, set[int], dict[int, int], dict]:
    best = None
    for depth, min_leaf in TREE_CONFIGS:
        tree = SimpleTree(depth, min_leaf).fit(X, y)
        leaves = tree.apply(X)
        selected, predictions, leaf_rows = select_leaves(leaves, y, min_trades)
        result, trade, pred = evaluate_tree(tree, X, y, selected, predictions)
        score = (result["wr"], result["wilson_low"], -len(selected), result["n"])
        if best is None or score > best[0]:
            best = score, tree, selected, predictions, result, trade, pred, leaf_rows, (depth, min_leaf)
    assert best is not None
    _, tree, selected, predictions, result, trade, pred, leaf_rows, config = best
    result = result | {"depth": config[0], "min_leaf": config[1], "selected_leaves": len(selected)}
    return tree, selected, predictions, result | {"trade_mask": trade, "pred": pred, "leaf_rows": leaf_rows}


def choose_config_inner(X: pd.DataFrame, y: np.ndarray) -> tuple[int, int]:
    cut = max(120, int(len(X) * 0.70))
    cut = min(cut, len(X) - 40)
    train_X, val_X = X.iloc[:cut], X.iloc[cut:]
    train_y, val_y = y[:cut], y[cut:]
    best = None
    for depth, min_leaf in TREE_CONFIGS:
        if len(train_X) < 2 * min_leaf:
            continue
        tree = SimpleTree(depth, min_leaf).fit(train_X, train_y)
        leaves = tree.apply(train_X)
        minimum = max(20, math.ceil(TARGET_RATE * len(train_X)))
        selected, predictions, _ = select_leaves(leaves, train_y, minimum)
        result, _, _ = evaluate_tree(tree, val_X, val_y, selected, predictions)
        if result["n"] < max(5, math.floor(TARGET_RATE * len(val_X) * 0.5)):
            continue
        score = (result["wilson_low"], result["wr"], result["n"], -depth)
        if best is None or score > best[0]:
            best = score, (depth, min_leaf)
    return best[1] if best is not None else (2, 30)


def nested_walkforward(X: pd.DataFrame, y: np.ndarray, dates: pd.Series) -> tuple[pd.DataFrame, np.ndarray]:
    rows = []
    outcomes = []
    start = 240
    step = 40
    for test_start in range(start, len(X), step):
        test_end = min(len(X), test_start + step)
        train_X, test_X = X.iloc[:test_start], X.iloc[test_start:test_end]
        train_y, test_y = y[:test_start], y[test_start:test_end]
        depth, min_leaf = choose_config_inner(train_X, train_y)
        tree = SimpleTree(depth, min_leaf).fit(train_X, train_y)
        leaves = tree.apply(train_X)
        minimum = max(30, math.ceil(TARGET_RATE * len(train_X)))
        selected, predictions, _ = select_leaves(leaves, train_y, minimum)
        result, trade, pred = evaluate_tree(tree, test_X, test_y, selected, predictions)
        correct = (pred[trade] == test_y[trade]).astype(int)
        outcomes.extend(correct.tolist())
        rows.append(
            {
                "train_end": str(pd.Timestamp(dates.iloc[test_start - 1]).date()),
                "test_start": str(pd.Timestamp(dates.iloc[test_start]).date()),
                "test_end": str(pd.Timestamp(dates.iloc[test_end - 1]).date()),
                "depth": depth,
                "min_leaf": min_leaf,
                **result,
            }
        )
    return pd.DataFrame(rows), np.asarray(outcomes, dtype=int)


def weekly_stats(dates: pd.Series, trade: np.ndarray) -> dict:
    all_periods = pd.period_range(dates.min().to_period("W-SUN"), dates.max().to_period("W-SUN"), freq="W-SUN")
    selected = dates[trade]
    counts = selected.groupby(selected.dt.to_period("W-SUN")).size().reindex(all_periods, fill_value=0)
    return {
        "weeks": int(len(counts)),
        "trades_per_week": float(counts.mean()),
        "active_weeks": int((counts >= 1).sum()),
        "zero_weeks": int((counts == 0).sum()),
        "median": float(counts.median()),
        "max": int(counts.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-trades", type=int, default=TARGET_TRADES)
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    meta, X, y = load_matrix()
    print(f"rows={len(X)} features={X.shape[1]} min_trades={args.min_trades}")

    conjunctions = conjunction_search(X, y, args.min_trades)
    print("Best broad conjunctions:")
    for row in conjunctions:
        print(json.dumps(row, ensure_ascii=False))

    tree, selected, predictions, static = best_static_tree(X, y, args.min_trades)
    trade = static.pop("trade_mask")
    pred = static.pop("pred")
    leaf_rows = static.pop("leaf_rows")
    paths = tree.paths()
    selected_rules = []
    leaf_lookup = {row["leaf"]: row for row in leaf_rows}
    for leaf in selected:
        selected_rules.append(leaf_lookup[leaf] | {"conditions": paths[leaf]})
    selected_rules.sort(key=lambda row: (row["wilson_low"], row["wr"]), reverse=True)
    static["weekly"] = weekly_stats(meta["date"], trade)
    static["rules"] = selected_rules
    print("Static tree:", json.dumps(static, ensure_ascii=False))

    folds, oos = nested_walkforward(X, y, meta["date"])
    oos_metrics = metrics(oos)
    print("Nested OOS:", json.dumps(oos_metrics, ensure_ascii=False))
    folds.to_csv(OUT_DIR / "nested_walkforward.csv", index=False)

    payload = {
        "rows": len(X),
        "features": list(X.columns),
        "feature_count": X.shape[1],
        "target": {"wr": TARGET_WR, "pf_gross": TARGET_PF, "min_trades": args.min_trades},
        "conjunctions": conjunctions,
        "static_tree": static,
        "nested_oos": oos_metrics,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame({"date": meta["date"], "trade": trade, "prediction_fade": pred, "y_fade": y}).to_csv(
        OUT_DIR / "static_tree_trades.csv", index=False
    )
    print(f"Saved {OUT_DIR}")


if __name__ == "__main__":
    main()
