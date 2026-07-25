"""Gate A1 (synthetic ordering) + MIRROR unit gate for the V2 extractor.

Deterministic synthetic sequences of known behaviour (pure absorption, pure
breakout, flat noise). No real market data, no outcomes. Scales for scoring
use frozen floors only (discovery scales do not exist yet at this stage).

Gate (frozen in V2_PREREGISTRO_CONVERGENTE.md, amendment A1):
  - S(breakout) > S(noise) > S(absorption) in 10/10 triplets;
  - S(absorption) < -0.15 and S(breakout) > +0.15 in >= 8/10;
  - MIRROR: |S_mirror - S| <= 1e-12 and |Q_mirror - Q| <= 1e-12 for all.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import pandas as pd

from v2_extractor import (
    ALL_COMPONENTS, CaseInputs, RawResult, UNBOUNDED, TICK_SIZE,
    extract_raw, mirror_case, score_case,
)

L0 = 100.00
T0 = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")


@dataclass
class Rec:
    action: str
    side: str
    price: float
    size: float
    order_id: int
    ts_event: pd.Timestamp
    ts_recv: pd.Timestamp
    flags: int = 0
    sequence: int = 0


def _rec(action, side, price, size, order_id, t):
    ts = T0 + pd.Timedelta(seconds=t)
    return Rec(action, side, price, size, order_id, ts, ts)


def _base_state():
    # BUY orientation: defenders are asks (A) at/above L0, trailing bids (B).
    return {
        1: ("A", L0, 50.0),
        2: ("A", L0 + TICK_SIZE, 40.0),
        3: ("A", L0 + 2 * TICK_SIZE, 30.0),
        4: ("A", L0 + 8 * TICK_SIZE, 60.0),
        5: ("B", L0 - TICK_SIZE, 45.0),
        6: ("B", L0 - 2 * TICK_SIZE, 35.0),
    }


def make_breakout(i: int) -> CaseInputs:
    """Depletion of L0/L1 defenders, sustained displacement, migration."""
    d = 0.02 * i
    q1 = 20.0 + i
    packets = []
    t = 0.20 + d
    # aggression consumes part of L0 ask; T aligned + F + C reflect depletion
    packets.append((t, [
        _rec("T", "B", L0, q1, 0, t),
        _rec("F", "A", L0, q1, 1, t),
        _rec("C", "A", L0, q1, 1, t),
    ]))
    t = 0.60 + d
    packets.append((t, [
        _rec("T", "B", L0, 50.0 - q1, 0, t),
        _rec("F", "A", L0, 50.0 - q1, 1, t),
        _rec("C", "A", L0, 50.0 - q1, 1, t),
        _rec("A", "B", L0, 25.0, 101, t),          # bid claims L0 -> x=0
    ]))
    t = 1.00 + d
    packets.append((t, [
        _rec("C", "A", L0 + TICK_SIZE, 25.0, 2, t),  # defender retreat
        _rec("A", "B", L0 + TICK_SIZE, 20.0, 102, t),  # x = 1 acceptance
    ]))
    t = 1.60 + d
    packets.append((t, [
        _rec("T", "B", L0 + TICK_SIZE, 15.0 - 0.2 * i, 0, t),
        _rec("F", "A", L0 + TICK_SIZE, 15.0 - 0.2 * i, 2, t),
        _rec("C", "A", L0 + TICK_SIZE, 15.0 - 0.2 * i, 2, t),
        _rec("A", "B", L0 + 2 * TICK_SIZE, 18.0, 103, t),  # x = 2, hold
    ]))
    return CaseInputs(f"SYN_BRK_{i:02d}", "2022-01-01", "BUY",
                      _base_state(), packets)


def make_absorption(i: int) -> CaseInputs:
    """Aggression fully absorbed: fills refilled fast, queue survives intact,
    price never accepts (x stays <=0), dominant late counterflow."""
    d = 0.02 * i
    q1 = 12.0 + i
    packets = []
    # aggressor lifts L0 ask, defender immediately refills same level
    t = 0.20 + d
    packets.append((t, [
        _rec("T", "B", L0, q1, 0, t),
        _rec("F", "A", L0, q1, 1, t),
        _rec("M", "A", L0, 50.0 - q1, 1, t),
    ]))
    t = 0.24 + d                                    # fast refill (<100 ms)
    packets.append((t, [_rec("A", "A", L0, q1, 201, t)]))
    t = 0.80 + d
    packets.append((t, [
        _rec("T", "B", L0, q1, 0, t),
        _rec("F", "A", L0, q1, 201, t),
        _rec("M", "A", L0, 50.0 - q1, 1, t),
    ]))
    t = 0.84 + d
    packets.append((t, [_rec("A", "A", L0, q1, 202, t)]))
    # trailing bid never claims acceptance; strong counterflow late
    t = 1.80 + d
    packets.append((t, [_rec("T", "A", L0 - TICK_SIZE, 40.0 + i, 0, t)]))
    t = 3.20 + d
    packets.append((t, [_rec("T", "A", L0 - TICK_SIZE, 40.0 + i, 0, t)]))
    t = 4.40 + d
    packets.append((t, [_rec("A", "A", L0 + TICK_SIZE, 8.0, 203, t)]))
    return CaseInputs(f"SYN_ABS_{i:02d}", "2022-01-01", "BUY",
                      _base_state(), packets)


def make_noise(i: int) -> CaseInputs:
    """Balanced/ambiguous: queue churns (low survival), price oscillates
    across L0, no fills and no net tape. Score should sit near zero."""
    d = 0.03 * i
    packets = []
    # churn L0 defender: cancel original id, re-add new id (survival lost,
    # B3 cancel~add balanced)
    t = 0.30 + d
    packets.append((t, [
        _rec("C", "A", L0, 50.0, 1, t),
        _rec("A", "A", L0, 50.0, 401, t),
        _rec("A", "B", L0 + TICK_SIZE, 20.0, 101, t),   # accept x=+1
    ]))
    t = 1.30 + d
    packets.append((t, [_rec("C", "B", L0 + TICK_SIZE, 20.0, 101, t)]))  # x=-1
    t = 2.30 + d
    packets.append((t, [
        _rec("C", "A", L0 + TICK_SIZE, 40.0, 2, t),
        _rec("A", "A", L0 + TICK_SIZE, 40.0, 402, t),
        _rec("A", "B", L0 + TICK_SIZE, 20.0, 102, t),   # accept x=+1
    ]))
    t = 3.30 + d
    packets.append((t, [_rec("C", "B", L0 + TICK_SIZE, 20.0, 102, t)]))  # x=-1
    t = 4.10 + d
    packets.append((t, [_rec("A", "B", L0 + TICK_SIZE, 20.0, 103, t)]))  # x=+1
    return CaseInputs(f"SYN_NOI_{i:02d}", "2022-01-01", "BUY",
                      _base_state(), packets)


def floor_scales() -> dict:
    return {comp: {"s": floor, "n": 0, "floor_only": True}
            for comp, floor in UNBOUNDED.items()}


def run_gate() -> dict:
    scales = floor_scales()
    result = {"triplets": [], "mirror_max_dS": 0.0, "mirror_max_dQ": 0.0}
    order_ok = 0
    band_ok = 0
    for i in range(10):
        rows = {}
        for kind, maker in (("breakout", make_breakout),
                            ("absorption", make_absorption),
                            ("noise", make_noise)):
            case = maker(i)
            raw = extract_raw(case)
            row = score_case(raw, scales)
            if not row["evaluable"]:
                raise AssertionError(
                    f"Synthetic case {case.burst_id} not evaluable: "
                    f"{raw.hard_fail} q={raw.q}"
                )
            rows[kind] = row
            mirrored = extract_raw(mirror_case(case))
            mrow = score_case(mirrored, scales)
            d_s = abs(mrow["S"] - row["S"])
            d_q = abs(mrow["Q"] - row["Q"])
            result["mirror_max_dS"] = max(result["mirror_max_dS"], d_s)
            result["mirror_max_dQ"] = max(result["mirror_max_dQ"], d_q)
        s_b, s_n, s_a = (rows["breakout"]["S"], rows["noise"]["S"],
                         rows["absorption"]["S"])
        ordered = s_b > s_n > s_a
        in_band = (s_a < -0.15) and (s_b > 0.15)
        order_ok += int(ordered)
        band_ok += int(in_band)
        result["triplets"].append({
            "i": i, "S_breakout": s_b, "S_noise": s_n, "S_absorption": s_a,
            "ordered": ordered, "band": in_band,
        })
    result["order_pass"] = order_ok == 10
    result["band_pass"] = band_ok >= 8
    result["mirror_pass"] = (result["mirror_max_dS"] <= 1e-12
                             and result["mirror_max_dQ"] <= 1e-12)
    result["GATE_A1"] = ("PASS" if (result["order_pass"]
                                    and result["band_pass"]
                                    and result["mirror_pass"]) else "FAIL")
    return result


if __name__ == "__main__":
    outcome = run_gate()
    print(json.dumps(outcome, indent=2))
