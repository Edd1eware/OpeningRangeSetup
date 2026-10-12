"""Shared tape primitives for the markout / order-flow studies.

Extracted verbatim from 17_markout_study.py so that scripts 17 and 18 run the
SAME implementation instead of two copies that can drift apart.

The aggressor convention is fixed here once: sign == +1 is the BUY aggressor
(side 'B', lifts the ask), sign == -1 is the SELL aggressor (side 'A', hits the
bid), sign == 0 is a print whose side the venue did not report -- kept in the
PRICE PATH, excluded from every signed-volume feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NS = 1_000_000_000

GRID_S = 15            # decision every 15 s, Codex's proposed grid
FEAT_S = 15            # imbalance measured over the trailing 15 s
DELAYS_S = (0.0, 0.5, 2.0)        # entry reference delay after the decision
HORIZONS_S = (15, 30, 60)         # markout horizon after the entry reference
REFS = ("print", "mid")           # entry/exit reference price estimator

WIN_FROM_S = 0.0                  # 09:30:00
WIN_TO_S = 60 * 60.0              # 10:30:00, where the tape ends

IS_SESSIONS = 100                 # first 100 sessions freeze everything
TAIL_Q = 0.90                     # |imb| tail cutoff, computed on IS only
N_BOOT = 2000
SEED = 20261012
COSTS = (1.8, 2.8, 3.8)           # 1.8 optimistic; Codex's stress scenarios


# --------------------------------------------------------------------------
# per-session tape view
# --------------------------------------------------------------------------
class SessionTape:
    """Arrays for one session, with the lookups the study needs."""

    def __init__(self, g: pd.DataFrame, open_ns: int):
        self.ts = g["ts_ns"].to_numpy()
        self.px = g["px_t"].to_numpy().astype("float64")
        sign = g["sign"].to_numpy().astype("int64")
        size = g["size"].to_numpy().astype("int64")
        self.open_ns = open_ns

        # signed volume cumsums, with sign == 0 (side not reported) excluded
        # from the FEATURE but still present in self.px for the price path
        self.cum_buy = np.concatenate([[0], np.cumsum(np.where(sign > 0, size, 0))])
        self.cum_sell = np.concatenate([[0], np.cumsum(np.where(sign < 0, size, 0))])

        n = len(self.ts)
        ar = np.arange(n)
        # index of the most recent buy / sell print at or before each position
        self.last_buy = np.maximum.accumulate(np.where(sign > 0, ar, -1))
        self.last_sell = np.maximum.accumulate(np.where(sign < 0, ar, -1))
        self.sign = sign

    def idx_at(self, t_ns: np.ndarray) -> np.ndarray:
        """First print at or after each instant. n means 'past the tape'.

        Use this for EXECUTION references (the earliest print you could have
        traded at). Never use it to build a FEATURE: it reaches forward.
        """
        return np.searchsorted(self.ts, t_ns, side="left")

    def idx_before(self, t_ns: np.ndarray) -> np.ndarray:
        """Last print STRICTLY BEFORE each instant. -1 means 'nothing yet'.

        This is the only correct index for a feature measured as of an instant.
        Codex found a real lookahead defect in 18_absorption_drive.py, which
        built the displacement feature from idx_at (first print at or AFTER the
        decision time) while the docstring claimed the feature used only
        pre-decision information. The wait for that print was a median of 25 ms
        but a p99 of 629 ms and a maximum of 6.52 s, and correcting it changed
        122 absorption and 109 drive selection flags out of 35,250 decisions.
        """
        return np.searchsorted(self.ts, t_ns, side="left") - 1

    def price(self, idx: np.ndarray, ref: str) -> np.ndarray:
        """Reference price at the given print indices, in ticks."""
        n = len(self.ts)
        ok = (idx >= 0) & (idx < n)
        out = np.full(len(idx), np.nan)
        i = idx[ok]
        if ref == "print":
            out[ok] = self.px[i]
            return out
        # mid proxy: average of the most recent buy-side and sell-side prints,
        # using information up to and including the print at i
        lb = self.last_buy[i]
        ls = self.last_sell[i]
        both = (lb >= 0) & (ls >= 0)
        vals = np.full(len(i), np.nan)
        vals[both] = (self.px[lb[both]] + self.px[ls[both]]) / 2.0
        # one side has not traded yet: fall back to the print itself
        vals[~both] = self.px[i[~both]]
        out[ok] = vals
        return out

    def imbalance(self, t0_ns: np.ndarray, t1_ns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Normalised signed aggressor imbalance over [t0, t1), and total vol."""
        a = np.searchsorted(self.ts, t0_ns, side="left")
        b = np.searchsorted(self.ts, t1_ns, side="left")
        buy = self.cum_buy[b] - self.cum_buy[a]
        sell = self.cum_sell[b] - self.cum_sell[a]
        tot = buy + sell
        imb = np.where(tot > 0, (buy - sell) / np.maximum(tot, 1), np.nan)
        return imb, tot

    def terminal_sign(self, t_ns: np.ndarray) -> np.ndarray:
        """Aggressor sign of the LAST print strictly before each instant.
        This is the q that drives the bounce artifact."""
        i = np.searchsorted(self.ts, t_ns, side="left") - 1
        out = np.zeros(len(i), dtype="int64")
        ok = i >= 0
        out[ok] = self.sign[i[ok]]
        return out


