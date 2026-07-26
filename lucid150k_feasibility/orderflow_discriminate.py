"""
Two questions the first order-flow pass left open.

1) Era stability. On DEV the long-side outcome is monotone decreasing in the
   opening delta ratio: heavy sell flow at the open precedes an up move. Does
   that ordering survive in 2024 and 2025-26, or is it another 2023 artifact
   like the open-long cell?

2) Attribution. Delta and the price move over the same three minutes are highly
   collinear. If the price move alone carries the information, then this is not
   an order-flow edge at all and the tape adds nothing. The test is to bucket by
   price move first and ask whether delta still separates outcomes inside the
   bucket.

Nothing here selects a threshold. It only reports whether the ordering is
stable, because an unstable ordering makes any threshold meaningless.
"""

import numpy as np
import pandas as pd

from orderflow_open_test import outcome_table, era

BRACKETS = [(40, 2.0), (60, 2.0)]
QUANTILES = 5


def qtable(df, feature, outcome, label):
    print(f"\n--- {label}: {outcome} by {feature} quintile, per era ---")
    print(f"{'era':>10} " + " ".join(f"q{i}".rjust(9) for i in range(5)))
    # quintile edges are taken from DEV only, then applied to later eras, so the
    # later eras are scored with bins that could not have seen them
    dev = df[df["era"] == "DEV 22-23"]
    edges = np.unique(np.quantile(dev[feature], np.linspace(0, 1, QUANTILES + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    df = df.copy()
    df["q"] = pd.cut(df[feature], edges, labels=False, include_lowest=True)

    for e in ["DEV 22-23", "2024", "2025-26"]:
        sub = df[df["era"] == e]
        cells = []
        for q in range(len(edges)-1):
            g = sub[sub["q"] == q]
            cells.append(f"{g[outcome].mean():>6.1f}/{len(g):<2d}" if len(g) >= 8
                         else f"{'-':>9}")
        print(f"{e:>10} " + " ".join(f"{c:>9}" for c in cells))


def main():
    feat = pd.read_csv("OF_FEATURES.csv")
    for s, rr in BRACKETS:
        df = outcome_table(feat, s, rr)
        df["era"] = df["day"].map(era)
        # contract-roll prints leave a handful of absurd tape moves; drop them
        df = df.dropna(subset=["tape_move", "delta_ratio"])
        df = df[df["tape_move"].abs() < 400].reset_index(drop=True)
        print(f"\n================ bracket {s}/{int(s*rr)} ================")
        qtable(df, "delta_ratio", "long_pnl", f"stop{s} rr{rr}")
        qtable(df, "tape_move", "long_pnl", f"stop{s} rr{rr}")

        # attribution: inside each tape_move tercile, does delta still separate?
        dev = df[df["era"] == "DEV 22-23"]
        m_edges = np.quantile(dev["tape_move"], [0, 1 / 3, 2 / 3, 1])
        m_edges[0], m_edges[-1] = -np.inf, np.inf
        df["m3"] = pd.cut(df["tape_move"], m_edges, labels=False, include_lowest=True)
        d_med = dev["delta_ratio"].median()
        print(f"\n--- attribution: long EV split by delta within tape_move terciles ---")
        print(f"{'era':>10} {'move tercile':>13} {'n':>4} {'delta<med':>10} "
              f"{'delta>med':>10} {'gap':>7}")
        for e in ["DEV 22-23", "2024", "2025-26"]:
            for m in range(3):
                g = df[(df["era"] == e) & (df["m3"] == m)]
                lo = g[g["delta_ratio"] <= d_med]["long_pnl"]
                hi = g[g["delta_ratio"] > d_med]["long_pnl"]
                if len(lo) < 6 or len(hi) < 6:
                    continue
                print(f"{e:>10} {m:>13} {len(g):>4} {lo.mean():>10.2f} "
                      f"{hi.mean():>10.2f} {lo.mean()-hi.mean():>7.2f}")


if __name__ == "__main__":
    main()
