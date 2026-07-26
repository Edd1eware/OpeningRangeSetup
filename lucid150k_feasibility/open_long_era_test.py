"""
Kill test for the single cell that survived the drift census.

The census found LONG at the session's first bar with stop 60 / target 120
showing +9.73 ticks of net EV on DEV. That cell was the maximum of 400, with
t = 2.24, which is what the maximum of 400 draws looks like under the null. So
this is not treated as a candidate, it is treated as something to falsify.

Two independent ways to kill it:
  1. era test  - does it hold in 2024 and in 2025-2026, out of the DEV era?
  2. stability - do the neighbouring brackets behave, or is it a knife edge?

A real structural bias should survive both. A mined maximum should not.
"""

import numpy as np

CACHE = "nq_1s_cache.npz"
COST_TICKS = 4

ERAS = {
    "DEV 2022": ("2022-04-25", "2022-12-31"),
    "DEV 2023": ("2023-01-01", "2023-12-31"),
    "2024":     ("2024-01-01", "2024-12-31"),
    "2025":     ("2025-01-01", "2025-12-31"),
    "2026":     ("2026-01-01", "2026-12-31"),
}


def trade(close, high, low, i, direction, s, tgt):
    entry = close[i]
    if direction > 0:
        sl_hit, tp_hit = low[i + 1:] <= entry - s, high[i + 1:] >= entry + tgt
    else:
        sl_hit, tp_hit = high[i + 1:] >= entry + s, low[i + 1:] <= entry - tgt
    j_sl = int(np.argmax(sl_hit)) if sl_hit.any() else 10**9
    j_tp = int(np.argmax(tp_hit)) if tp_hit.any() else 10**9
    if j_sl == 10**9 and j_tp == 10**9:
        return int(direction * (close[-1] - entry)) - COST_TICKS
    return (-s - COST_TICKS) if j_sl <= j_tp else (tgt - COST_TICKS)


def stats(pnls):
    a = np.array(pnls, dtype=float)
    gl = -a[a < 0].sum()
    return dict(n=len(a), wr=a.__gt__(0).mean(), ev=a.mean(),
                pf=(a[a > 0].sum() / gl) if gl > 0 else float("nan"),
                t=a.mean() / (a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else 0.0)


def main():
    z = np.load(CACHE, allow_pickle=True)
    days = z["days"].astype(str)
    offsets = z["offsets"]
    close, high, low = z["close"], z["high"], z["low"]

    def sessions(a_, b_):
        out = []
        for i in np.flatnonzero((days >= a_) & (days <= b_)):
            a, b = offsets[i], offsets[i + 1]
            out.append((close[a:b], high[a:b], low[a:b]))
        return out

    print("=== ERA TEST: LONG at first bar, stop 60 / target 120 ===")
    print(f"{'era':>10} {'n':>4} {'WR':>7} {'EVnet':>8} {'PF':>6} {'t':>6}")
    for name, (a_, b_) in ERAS.items():
        ss = sessions(a_, b_)
        if not ss:
            continue
        pnls = [trade(c, h, l, 0, 1, 60, 120) for c, h, l in ss if len(c) > 100]
        s = stats(pnls)
        print(f"{name:>10} {s['n']:>4} {s['wr']:>7.3f} {s['ev']:>8.2f} "
              f"{s['pf']:>6.3f} {s['t']:>6.2f}")

    print("\n=== PARAMETER STABILITY on DEV (LONG at first bar) ===")
    dev = sessions("2022-04-25", "2023-12-31")
    print(f"{'stop':>5} {'target':>7} {'RR':>5} {'WR':>7} {'EVnet':>8} {'PF':>6} {'t':>6}")
    for s_ in (20, 30, 40, 50, 60, 80):
        for rr in (1.0, 1.5, 2.0, 3.0):
            tgt = int(round(s_ * rr))
            pnls = [trade(c, h, l, 0, 1, s_, tgt) for c, h, l in dev if len(c) > 100]
            st = stats(pnls)
            print(f"{s_:>5} {tgt:>7} {rr:>5.1f} {st['wr']:>7.3f} {st['ev']:>8.2f} "
                  f"{st['pf']:>6.3f} {st['t']:>6.2f}")

    print("\n=== SHORT at first bar, same brackets, DEV (sign check) ===")
    for s_ in (40, 60):
        for rr in (1.0, 2.0):
            tgt = int(round(s_ * rr))
            pnls = [trade(c, h, l, 0, -1, s_, tgt) for c, h, l in dev if len(c) > 100]
            st = stats(pnls)
            print(f"stop {s_:>3} target {tgt:>3}  WR {st['wr']:.3f} "
                  f"EV {st['ev']:+.2f} PF {st['pf']:.3f} t {st['t']:+.2f}")


if __name__ == "__main__":
    main()
