"""V2 continuous defense-acceptance score extractor.

Implements the frozen convergent preregistration
(V2_PREREGISTRO_CONVERGENTE.md, SHA-256 22f9cadf...) whose normative base is
CODEX_V2_PROPOSAL.md (SHA-256 9131b8ad...).

Outcome-blind by construction: no MFE/MAE/TP/SL/PnL, no AMD labels, no mapping.
Book/packet semantics are copied from the frozen audited pipeline
(human_blind_v1_pipeline.py): F_LAST atomic packets, A/M/C/R mutations,
aligned_trade convention, canonical tick orientation.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

F_LAST = 128
TICK_SIZE = 0.25
WINDOW_SECONDS = 5.0
DURABLE_H = 0.250
REFILL_WINDOW = 0.100
LEVEL_WEIGHTS = (1.0, 0.5, 0.25)
NEUTRAL_BAND = 0.15

UNBOUNDED = {"K2": 1.0, "K3": 0.25, "B1": 0.25, "B2": 0.25, "B3": 0.25,
             "B5": 0.10, "F2": 0.25}  # component -> frozen floor
BOUNDED = ("K1", "K4", "K5", "K6", "B4", "F1")
K_COMPONENTS = ("K1", "K2", "K3", "K4", "K5", "K6")
B_COMPONENTS = ("B1", "B2", "B3", "B4", "B5")
F_COMPONENTS = ("F1", "F2")
ALL_COMPONENTS = K_COMPONENTS + B_COMPONENTS + F_COMPONENTS


# ---------------------------------------------------------------- book engine

def normalize_mbo(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    result = frame.copy()
    for field_name in ("ts_recv", "ts_event"):
        result[field_name] = pd.to_datetime(
            result[field_name], utc=True, errors="raise", format="mixed"
        )
    for field_name in ("sequence", "order_id", "flags", "instrument_id"):
        result[field_name] = pd.to_numeric(result[field_name], errors="raise")
    result["price"] = pd.to_numeric(result["price"], errors="coerce")
    result["size"] = pd.to_numeric(result["size"], errors="raise")
    result["action"] = result["action"].astype(str)
    result["side"] = result["side"].astype(str)
    return result


def update_level(levels: dict, side: str, price: float, delta: float) -> None:
    key = (side, price)
    value = levels.get(key, 0.0) + delta
    if value <= 1e-9:
        levels.pop(key, None)
    else:
        levels[key] = value


def best_price(levels: dict, side: str) -> float:
    prices = [p for (s, p), q in levels.items()
              if s == side and q > 0 and math.isfinite(p)]
    if not prices:
        return math.nan
    return min(prices) if side == "A" else max(prices)


def aligned_trade(side: str, burst_side: str) -> bool | None:
    if side not in {"A", "B"}:
        return None
    return (burst_side == "BUY" and side == "B") or (
        burst_side == "SELL" and side == "A"
    )


def logical_packets(frame: pd.DataFrame, start_record: int,
                    cutoff: pd.Timestamp, window_seconds: float):
    """Atomic F_LAST packets with close ts_recv in [cutoff, cutoff+window)."""
    end = cutoff + pd.Timedelta(seconds=window_seconds)
    packets, packet = [], []
    excluded_records = 0
    for item in frame.iloc[int(start_record):].itertuples(index=False):
        packet.append(item)
        if not bool(int(item.flags) & F_LAST):
            continue
        close_recv = max(value.ts_recv for value in packet)
        if close_recv < cutoff:
            raise ValueError("Confirmed prefix ended before cutoff")
        if close_recv >= end:
            excluded_records += len(packet)
            break
        packets.append((close_recv, packet))
        packet = []
    return packets, excluded_records


# ---------------------------------------------------------------- case inputs

@dataclass
class CaseInputs:
    burst_id: str
    fecha: str
    burst_side: str            # BUY / SELL
    state: dict                # order_id -> (side, price, size) at t0
    packets: list              # [(t_seconds, [records])] applied atomically
    hard_fail: str | None = None


@dataclass
class PathPoint:
    t: float
    x: float                   # canonical trailing displacement in ticks (nan invalid)
    mu: float                  # depth centroid over L0:L2 (nan if depth 0/invalid)
    g: float                   # cumulative (V+ - V-)/Q0


def load_case(row: pd.Series, permute_p4: bool = False) -> CaseInputs:
    state_frame = pd.read_parquet(Path(row["state_cache_path"]))
    state = {
        int(item.order_id): (str(item.side), float(item.price), float(item.size))
        for item in state_frame.itertuples(index=False)
    }
    cutoff_value = row["strict_feature_cutoff_utc_exclusive"]
    if pd.isna(cutoff_value) or not str(cutoff_value).strip():
        cutoff_value = row["decision_utc"]
    cutoff = pd.to_datetime(cutoff_value, utc=True)

    import databento as db
    outcome = normalize_mbo(
        db.DBNStore.from_file(Path(row["outcome_path"])).to_df()
    )
    start_record = int(row["pre_overlap_records"])
    if permute_p4:
        # P4: transport-order robustness. Tag each post-overlap record with its
        # original packet id (F_LAST boundaries in arrival order) and intra
        # index, deterministically permute all rows by SHA-256 of message
        # identity, then regroup by (packet, sequence/intra) restoring the
        # original packetization. A faithful pipeline round-trips exactly.
        post = outcome.iloc[start_record:].reset_index(drop=True)
        packet_id = np.empty(len(post), dtype=np.int64)
        intra = np.empty(len(post), dtype=np.int64)
        pid = 0
        j = 0
        for i, item in enumerate(post.itertuples(index=False)):
            packet_id[i] = pid
            intra[i] = j
            j += 1
            if bool(int(item.flags) & F_LAST):
                pid += 1
                j = 0
        post = post.assign(_pid=packet_id, _intra=intra)

        def msg_key(item) -> str:
            raw = (f"{int(item.sequence)}|{int(item.order_id)}|"
                   f"{int(item.ts_event.value)}|{item.action}|{item.side}|"
                   f"{item.price}|{item.size}")
            return hashlib.sha256(raw.encode()).hexdigest()

        keys = [msg_key(item) for item in post.itertuples(index=False)]
        post = post.iloc[np.argsort(np.array(keys), kind="stable")]
        post = post.sort_values(["_pid", "_intra"], kind="stable").reset_index(
            drop=True).drop(columns=["_pid", "_intra"])
        outcome = post
        start_record = 0
    packets, _ = logical_packets(
        outcome, start_record, cutoff, WINDOW_SECONDS
    )
    timed = [
        (max(0.0, (close - cutoff).total_seconds()), packet)
        for close, packet in packets
    ]
    return CaseInputs(
        burst_id=str(row["BurstId"]),
        fecha=str(row["fecha"]),
        burst_side=str(row["burst_side"]).upper(),
        state=state,
        packets=timed,
    )


# ------------------------------------------------------------- perturbations

def quantize_times_1ms(case: CaseInputs) -> CaseInputs:
    """P1: quantize packet apply times to 1 ms, round-half-to-even."""
    packets = []
    for t, packet in case.packets:
        packets.append((float(np.round(t * 1000.0) / 1000.0), packet))
    return CaseInputs(case.burst_id, case.fecha, case.burst_side,
                      dict(case.state), packets, case.hard_fail)


def mirror_case(case: CaseInputs) -> CaseInputs:
    """MIRROR: BUY<->SELL with prices reflected around a pivot on the grid.

    Reflection p -> 2*pivot - p with pivot on the tick grid keeps all prices
    on-grid, swaps sides A<->B, and flips the attack direction. All canonical
    quantities must be bit-identical after re-extraction.
    """
    prices = [p for (_s, p, _q) in case.state.values() if math.isfinite(p)]
    pivot = round(min(prices) / TICK_SIZE) * TICK_SIZE if prices else 0.0

    def flip_side(side: str) -> str:
        return {"A": "B", "B": "A"}.get(side, side)

    state = {
        oid: (flip_side(s), 2.0 * pivot - p, q)
        for oid, (s, p, q) in case.state.items()
    }

    class Rec:
        __slots__ = ("ts_recv", "ts_event", "action", "side", "price",
                     "size", "order_id", "flags", "sequence")

        def __init__(self, src):
            self.ts_recv = src.ts_recv
            self.ts_event = src.ts_event
            self.action = src.action
            self.side = flip_side(str(src.side))
            self.price = (2.0 * pivot - float(src.price)
                          if pd.notna(src.price) else float("nan"))
            self.size = src.size
            self.order_id = src.order_id
            self.flags = src.flags
            self.sequence = src.sequence

    packets = [(t, [Rec(v) for v in packet]) for t, packet in case.packets]
    flipped = "SELL" if case.burst_side == "BUY" else "BUY"
    return CaseInputs(case.burst_id, case.fecha, flipped, state, packets,
                      case.hard_fail)


# ------------------------------------------------------------------ extractor

@dataclass
class RawResult:
    burst_id: str
    fecha: str
    burst_side: str
    r: dict = field(default_factory=dict)      # component -> raw value or nan
    usable: dict = field(default_factory=dict)  # component -> bool
    q: dict = field(default_factory=dict)      # component -> coverage [0,1]
    hard_fail: str | None = None
    diagnostics: dict = field(default_factory=dict)


def _segments(points: list[PathPoint], t_end: float):
    """Yield (t_start, t_end, point) piecewise-constant segments."""
    for i, pt in enumerate(points):
        stop = points[i + 1].t if i + 1 < len(points) else t_end
        if stop > pt.t:
            yield pt.t, stop, pt


def _round_half_even(value: float, step: float) -> float:
    return float(np.round(value / step) * step)


def extract_raw(case: CaseInputs, grid_ms: int | None = None,
                grid_phase_ms: float = 0.0,
                p5_round: bool = False) -> RawResult:
    """Compute the 13 raw components r_j and coverages q_j for one case.

    grid_ms: if set (P2/P3), path integrals/runs use a left-continuous grid of
    that step with the given phase; event counts/quantities stay exact.
    p5_round: P5 innocuous rounding of raw outputs before normalization.
    """
    out = RawResult(case.burst_id, case.fecha, case.burst_side)
    sigma = 1.0 if case.burst_side == "BUY" else -1.0
    attacked_side = "A" if case.burst_side == "BUY" else "B"   # defender side
    trailing_side = "B" if case.burst_side == "BUY" else "A"

    # --- initial book
    state = {k: v for k, v in case.state.items()}
    levels: dict = {}
    for side, price, size in state.values():
        update_level(levels, side, price, size)
    l0 = best_price(levels, attacked_side)
    q0 = float(levels.get((attacked_side, l0), 0.0))
    lk_prices = [l0 + sigma * k * TICK_SIZE for k in range(3)]
    qk0 = [float(levels.get((attacked_side, p), 0.0)) for p in lk_prices]
    q_l = sum(w * q for w, q in zip(LEVEL_WEIGHTS, qk0))
    if not math.isfinite(l0) or q0 <= 0 or q_l <= 0:
        out.hard_fail = "INVALID_L0_Q0"
        return out

    initial_ids = {
        oid: (state[oid][1], state[oid][2],
              int(round((sigma * (state[oid][1] - l0) / TICK_SIZE))))
        for oid in state
        if state[oid][0] == attacked_side
        and any(math.isclose(state[oid][1], p, abs_tol=1e-9) for p in lk_prices)
    }

    def x_now() -> float:
        p_tr = best_price(levels, trailing_side)
        if not math.isfinite(p_tr):
            return math.nan
        return sigma * (p_tr - l0) / TICK_SIZE

    def mu_now() -> float:
        depths = [float(levels.get((attacked_side, p), 0.0)) for p in lk_prices]
        total = sum(depths)
        if total <= 0:
            return math.nan
        return sum(k * d for k, d in enumerate(depths)) / total

    # --- walk packets, build path + event aggregates
    points = [PathPoint(0.0, x_now(), mu_now(), 0.0)]
    e_l0 = 0.0
    v_plus = 0.0
    v_minus = 0.0
    refill_neg = 0.0                 # sum q_m*(1-l_m/0.1)
    refill_matched_qty = 0.0
    deficits: list[list[float]] = []  # [t_fill, remaining_qty]
    cancels_k = [0.0, 0.0, 0.0]
    adds_k = [0.0, 0.0, 0.0]
    unknown_rows = 0

    def level_index(price: float) -> int | None:
        for k, p in enumerate(lk_prices):
            if math.isclose(price, p, abs_tol=1e-9):
                return k
        return None

    for t_apply, packet in case.packets:
        aggressors_by_event: dict[int, set[int]] = {}
        for value in packet:
            if str(value.action) == "T" and int(value.order_id) != 0:
                aggressors_by_event.setdefault(
                    int(value.ts_event.value), set()
                ).add(int(value.order_id))

        # executions are not cancellations: net the F quantity of each
        # defender order out of the C/M size reductions of the same packet
        fills_pkt: dict[int, float] = {}
        for value in packet:
            if (str(value.action) == "F"
                    and str(value.side) == attacked_side
                    and int(value.order_id) not in aggressors_by_event.get(
                        int(value.ts_event.value), set())):
                fills_pkt[int(value.order_id)] = (
                    fills_pkt.get(int(value.order_id), 0.0)
                    + float(value.size))

        def net_cancel(order_id: int, reduction: float) -> float:
            executed = min(reduction, fills_pkt.get(order_id, 0.0))
            if executed > 0:
                fills_pkt[order_id] -= executed
            return reduction - executed

        for value in packet:
            action = str(value.action)
            price = float(value.price) if pd.notna(value.price) else math.nan
            size = float(value.size)
            side = str(value.side)

            if action == "T" and math.isfinite(price):
                alignment = aligned_trade(side, case.burst_side)
                if alignment is True:
                    v_plus += size
                elif alignment is False:
                    v_minus += size
                continue
            if action == "F":
                if (side == attacked_side
                        and math.isclose(price, l0, abs_tol=1e-9)
                        and int(value.order_id) not in aggressors_by_event.get(
                            int(value.ts_event.value), set())):
                    e_l0 += size
                    deficits.append([t_apply, size])
                continue
            if action == "N":
                continue

            order_id = int(value.order_id)
            if action == "R":
                state.clear()
                levels.clear()
                continue
            if action == "A":
                old = state.get(order_id)
                if old is not None:
                    update_level(levels, old[0], old[1], -old[2])
                state[order_id] = (side, price, size)
                update_level(levels, side, price, size)
                if side == attacked_side:
                    k = level_index(price)
                    if k is not None:
                        add_qty = size
                        if k == 0:
                            matched = _match_refill(
                                deficits, t_apply, add_qty)
                            for q_m, l_m in matched:
                                refill_neg += q_m * (1.0 - l_m / REFILL_WINDOW)
                                refill_matched_qty += q_m
                                add_qty -= q_m
                        adds_k[k] += max(add_qty, 0.0)
                continue
            if action == "M":
                old = state.get(order_id)
                if old is None:
                    unknown_rows += 1
                else:
                    update_level(levels, old[0], old[1], -old[2])
                    if old[0] == attacked_side:
                        k_old = level_index(old[1])
                        same_price = math.isclose(old[1], price, abs_tol=1e-9)
                        if k_old is not None and (not same_price
                                                  or side != old[0]):
                            cancels_k[k_old] += net_cancel(order_id, old[2])
                        elif k_old is not None and same_price:
                            delta = size - old[2]
                            if delta < 0:
                                cancels_k[k_old] += net_cancel(order_id, -delta)
                state[order_id] = (side, price, size)
                update_level(levels, side, price, size)
                if side == attacked_side:
                    k_new = level_index(price)
                    if k_new is not None:
                        prev = old if old is not None else None
                        same_price = (prev is not None
                                      and math.isclose(prev[1], price,
                                                       abs_tol=1e-9)
                                      and prev[0] == side)
                        if same_price:
                            delta = size - prev[2]
                            if delta > 0:
                                add_qty = delta
                                if k_new == 0:
                                    matched = _match_refill(
                                        deficits, t_apply, add_qty)
                                    for q_m, l_m in matched:
                                        refill_neg += q_m * (
                                            1.0 - l_m / REFILL_WINDOW)
                                        refill_matched_qty += q_m
                                        add_qty -= q_m
                                adds_k[k_new] += max(add_qty, 0.0)
                        else:
                            add_qty = size
                            if k_new == 0:
                                matched = _match_refill(
                                    deficits, t_apply, add_qty)
                                for q_m, l_m in matched:
                                    refill_neg += q_m * (
                                        1.0 - l_m / REFILL_WINDOW)
                                    refill_matched_qty += q_m
                                    add_qty -= q_m
                            adds_k[k_new] += max(add_qty, 0.0)
                continue
            if action == "C":
                old = state.get(order_id)
                if old is None:
                    unknown_rows += 1
                    continue
                removed = min(size, old[2])
                update_level(levels, old[0], old[1], -removed)
                if old[0] == attacked_side:
                    k = level_index(old[1])
                    if k is not None:
                        cancels_k[k] += net_cancel(order_id, removed)
                remaining = old[2] - removed
                if remaining <= 0:
                    state.pop(order_id, None)
                else:
                    state[order_id] = (old[0], old[1], remaining)

        g = (v_plus - v_minus) / q0
        points.append(PathPoint(t_apply, x_now(), mu_now(), g))

    out.diagnostics["unknown_rows"] = unknown_rows
    out.diagnostics["n_packets"] = len(case.packets)

    # --- optional grid resampling for path quantities (P2/P3)
    if grid_ms is not None:
        step = grid_ms / 1000.0
        phase = grid_phase_ms / 1000.0
        grid_times = np.arange(phase, WINDOW_SECONDS, step)
        if phase > 0:
            grid_times = np.concatenate(([0.0], grid_times))
        times = np.array([p.t for p in points])
        idx = np.searchsorted(times, grid_times, side="right") - 1
        idx = np.clip(idx, 0, len(points) - 1)
        points = [PathPoint(float(gt), points[i].x, points[i].mu, points[i].g)
                  for gt, i in zip(grid_times, idx)]

    # --- path analysis over valid intervals
    seg = list(_segments(points, WINDOW_SECONDS))
    t_valid = sum(b - a for a, b, p in seg if math.isfinite(p.x))
    if t_valid <= 0:
        out.hard_fail = "NO_VALID_PATH"
        return out

    acc_t = sum(b - a for a, b, p in seg
                if math.isfinite(p.x) and p.x >= 1.0)
    def_t = sum(b - a for a, b, p in seg
                if math.isfinite(p.x) and p.x <= 0.0)
    area = sum((b - a) * p.x for a, b, p in seg if math.isfinite(p.x))

    # terminal state: last segment reaching t1 must be valid
    last = seg[-1][2]
    terminal_valid = math.isfinite(last.x) and seg[-1][1] >= WINDOW_SECONDS - 1e-12
    x_terminal = last.x if terminal_valid else math.nan
    s_t = 0.0
    if terminal_valid:
        s_t = 1.0 if x_terminal >= 1.0 else -1.0

    # runs of A-state for K4 (gaps break runs)
    runs: list[tuple[float, float, bool]] = []   # (start, stop, is_accept)
    for a, b, p in seg:
        if not math.isfinite(p.x):
            runs.append((a, b, None))
            continue
        is_a = p.x >= 1.0
        if runs and runs[-1][2] is is_a and abs(runs[-1][1] - a) < 1e-12:
            runs[-1] = (runs[-1][0], b, is_a)
        else:
            runs.append((a, b, is_a))
    tau_a = None
    for a, b, is_a in runs:
        if is_a is True and (b - a) >= DURABLE_H:
            tau_a = a
            break
    n_cross = 0
    prev_state = None
    for a, b, is_a in runs:
        if is_a is None:
            prev_state = None
            continue
        if prev_state is not None and is_a != prev_state:
            n_cross += 1
        prev_state = is_a
    # runs already merges adjacent same-state segments, so the last run is the
    # final contiguous valid run of the terminal state reaching t1
    ell_t = 0.0
    if terminal_valid and runs and runs[-1][2] is not None \
            and runs[-1][2] == (x_terminal >= 1.0):
        ell_t = runs[-1][1] - runs[-1][0]

    # B5 slope over Omega_mu
    mu_seg = [(a, b, p.mu) for a, b, p in seg if math.isfinite(p.mu)]
    t_mu = sum(b - a for a, b, _ in mu_seg)
    beta_mu = math.nan
    if t_mu > 0:
        t_bar = sum((b * b - a * a) / 2.0 for a, b, _ in mu_seg) / t_mu
        mu_bar = sum((b - a) * m for a, b, m in mu_seg) / t_mu
        s_tt = sum(((b - t_bar) ** 3 - (a - t_bar) ** 3) / 3.0
                   for a, b, _ in mu_seg)
        s_tm = sum((m - mu_bar) * ((b - t_bar) ** 2 - (a - t_bar) ** 2) / 2.0
                   for a, b, m in mu_seg)
        beta_mu = s_tm / s_tt if s_tt > 0 else math.nan

    # F2 integral of G
    g_area = sum((b - a) * p.g for a, b, p in seg if math.isfinite(p.x))

    # --- raw components
    r = out.r
    r["K1"] = (acc_t - def_t) / t_valid
    r["K2"] = x_terminal
    r["K3"] = area / t_valid
    r["K4"] = (1.0 - tau_a / (WINDOW_SECONDS - DURABLE_H)) \
        if tau_a is not None else -1.0
    r["K5"] = s_t * (ell_t / WINDOW_SECONDS) if terminal_valid else math.nan
    r["K6"] = (s_t / (1.0 + n_cross)) if terminal_valid else math.nan
    r["B1"] = e_l0 / q0
    r["B2"] = -refill_neg / q0
    r["B3"] = sum(w * (c - a) for w, c, a
                  in zip(LEVEL_WEIGHTS, cancels_k, adds_k)) / q_l
    surv = 0.0
    for oid, (price0, size0, k) in initial_ids.items():
        cur = state.get(oid)
        if cur is not None and cur[0] == attacked_side \
                and math.isclose(cur[1], price0, abs_tol=1e-9):
            surv += LEVEL_WEIGHTS[k] * min(size0, cur[2])
    r["B4"] = -surv / q_l
    r["B5"] = beta_mu
    total_v = v_plus + v_minus
    r["F1"] = (v_plus - v_minus) / total_v if total_v > 0 else 0.0
    r["F2"] = g_area / t_valid

    if p5_round:
        r["K2"] = _round_half_even(r["K2"], 0.01) if math.isfinite(r["K2"]) else r["K2"]
        r["K3"] = _round_half_even(r["K3"], 0.01) if math.isfinite(r["K3"]) else r["K3"]
        for key in ("K1", "K4", "K5", "K6", "B1", "B2", "B3", "B4", "F1", "F2"):
            if math.isfinite(r[key]):
                r[key] = _round_half_even(r[key], 1e-4)
        if math.isfinite(r["B5"]):
            r["B5"] = _round_half_even(r["B5"], 1e-3)

    # --- usability + coverage
    cov_path = t_valid / WINDOW_SECONDS
    events_ok = 1.0   # handoff integrity gates already PASS (hard fails above)
    q = out.q
    q["K1"] = cov_path
    q["K2"] = cov_path if terminal_valid else 0.0
    q["K3"] = cov_path
    q["K4"] = cov_path
    q["K5"] = cov_path if terminal_valid else 0.0
    q["K6"] = cov_path if terminal_valid else 0.0
    q["B1"] = events_ok
    q["B2"] = events_ok
    q["B3"] = events_ok
    q["B4"] = events_ok
    q["B5"] = (t_mu / WINDOW_SECONDS)
    q["F1"] = events_ok
    q["F2"] = cov_path
    for comp in ALL_COMPONENTS:
        out.usable[comp] = bool(math.isfinite(r[comp]) and q[comp] > 0.0)
    return out


def _match_refill(deficits: list[list[float]], t_add: float,
                  add_qty: float) -> list[tuple[float, float]]:
    """FIFO match of an add at L0 against open fill deficits (<=100 ms old)."""
    matched: list[tuple[float, float]] = []
    remaining = add_qty
    for entry in deficits:
        if remaining <= 0:
            break
        t_fill, open_qty = entry
        latency = t_add - t_fill
        if open_qty <= 0 or latency <= 0 or latency > REFILL_WINDOW:
            continue
        take = min(open_qty, remaining)
        entry[1] = open_qty - take
        remaining -= take
        matched.append((take, latency))
    return matched


# ---------------------------------------------------------------- scoring

def compute_scales(raw_results: list[RawResult],
                   discovery_years: set[int]) -> dict:
    """s_j = max(p75|r|, floor) using discovery inputs only (outcome-blind)."""
    scales = {}
    for comp, floor in UNBOUNDED.items():
        values = [abs(res.r[comp]) for res in raw_results
                  if int(res.fecha[:4]) in discovery_years
                  and res.hard_fail is None
                  and res.usable.get(comp)
                  and math.isfinite(res.r[comp])]
        if len(values) < 20:
            scales[comp] = {"s": floor, "n": len(values), "floor_only": True}
        else:
            d = float(np.percentile(np.array(values), 75))
            scales[comp] = {"s": max(d, floor), "n": len(values),
                            "floor_only": False}
    return scales


def score_case(res: RawResult, scales: dict) -> dict:
    row: dict[str, Any] = {
        "BurstId": res.burst_id, "fecha": res.fecha,
        "burst_side": res.burst_side, "hard_fail": res.hard_fail or "",
    }
    if res.hard_fail is not None:
        row.update({"S": math.nan, "Q": 0.0, "evaluable": False})
        return row
    u = {}
    for comp in ALL_COMPONENTS:
        if not res.usable[comp]:
            u[comp] = math.nan
            continue
        value = res.r[comp]
        if comp in UNBOUNDED:
            value = math.tanh(value / scales[comp]["s"])
        u[comp] = float(np.clip(value, -1.0, 1.0))
    blocks = {}
    for name, comps in (("K", K_COMPONENTS), ("B", B_COMPONENTS),
                        ("F", F_COMPONENTS)):
        vals = [u[c] for c in comps if math.isfinite(u[c])]
        blocks[name] = float(np.mean(vals)) if vals else math.nan
    q_blocks = {
        "K": float(np.mean([res.q[c] for c in K_COMPONENTS])),
        "B": float(np.mean([res.q[c] for c in B_COMPONENTS])),
        "F": float(np.mean([res.q[c] for c in F_COMPONENTS])),
    }
    q_total = float(np.mean(list(q_blocks.values())))
    usable_k = sum(res.usable[c] for c in K_COMPONENTS)
    usable_b = sum(res.usable[c] for c in B_COMPONENTS)
    usable_f = sum(res.usable[c] for c in F_COMPONENTS)
    required = all(res.usable[c] for c in ("K1", "K2", "K3", "K5", "F1"))
    evaluable = (
        q_total >= 0.90
        and all(q_blocks[b] >= 0.80 for b in q_blocks)
        and required
        and usable_k >= 5 and usable_b >= 4 and usable_f == 2
        and all(math.isfinite(blocks[b]) for b in blocks)
    )
    s_score = (float(np.mean([blocks["K"], blocks["B"], blocks["F"]]))
               if evaluable else math.nan)
    row.update({
        "S": s_score, "Q": q_total, "evaluable": bool(evaluable),
        "Q_K": q_blocks["K"], "Q_B": q_blocks["B"], "Q_F": q_blocks["F"],
        "S_K": blocks["K"], "S_B": blocks["B"], "S_F": blocks["F"],
    })
    for comp in ALL_COMPONENTS:
        row[f"r_{comp}"] = res.r.get(comp, math.nan)
        row[f"u_{comp}"] = u.get(comp, math.nan)
        row[f"q_{comp}"] = res.q.get(comp, math.nan)
    return row


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
