"""Do the surviving conditions ADD, and does the strongest one hold up by decade?

Script 48 ran ten pre-registered conditions on three instruments. Honest
accounting of that is thirty tests, so Bonferroni puts the bar at 0.0017, and
only three cells clear it, all on ^GSPC where sixty-four years of history give
the most power: the Santa window, the session after a one-sigma UP day, and the
turn of the month.

Two questions remain, and both can be answered on the same free data.

FIRST, do the calendar condition and the short-term one ADD? The geometry says
the only thing that matters is the drift, so a combination with a larger drift
is worth proportionally more. There is a motivated reason to expect addition
here: the turn of the month is a FLOW story -- money arriving on a schedule --
while "after two down days" is a PRICE story. Flows that arrive on a schedule
into a market that has just fallen should push harder than flows into a market
that has just risen. That is a prediction with a direction, and it is the same
prediction the prior-MONTH test rejected in note 06; testing it on short-term
weakness instead is a different question, not a second bite at the same one.

SECOND, does the strongest condition survive decade by decade? An effect that
was real until 1999 is not tradeable now, and the pooled sixty-four-year number
cannot tell the difference.

Both are reported with the combination's own placebo, and the combination is
labelled exploratory, because nobody declared it before the scan.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as C


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = _load("sc48", "48_drift_condition_scan.py")
SYMBOLS = ("^GSPC", "^NDX", "NQ=F")


def block(d, mask, label, rows, sym, base_mask=None):
    a = d.loc[mask, "r_oc"].dropna().to_numpy()
    b = d.loc[~mask, "r_oc"].dropna().to_numpy()
    if len(a) < 50:
        print(f"  {label:38} n {len(a):5}  too few")
        return None
    t, p = stats.ttest_ind(a, b, equal_var=False)
    sg = a.std(ddof=1)
    plac = np.roll(mask, 5)
    pa = d.loc[plac, "r_oc"].dropna().to_numpy()
    _, pp = stats.ttest_ind(pa, b, equal_var=False)
    se = sg / np.sqrt(len(a))
    print(f"  {label:38} n {len(a):5} drift {a.mean():+.4f}%  sigma {sg:.4f}%  "
          f"mu/sig2 {a.mean()/sg**2:>7.4f}  t {t:+.2f}  p {p:.4f}  "
          f"WR {(a>0).mean():.4f}  CI [{a.mean()-1.96*se:+.4f},{a.mean()+1.96*se:+.4f}]  "
          f"plac p {pp:.4f}")
    rows.append(dict(symbol=sym, scope=label, n=len(a), drift_pct=float(a.mean()),
                     sigma_pct=float(sg), mu_over_sig2=float(a.mean() / sg ** 2),
                     t=float(t), p=float(p), wr=float((a > 0).mean()),
                     placebo_p=float(pp)))
    return a


def main():
    rows = []
    for sym in SYMBOLS:
        try:
            d, cond = SC.build(SC.fetch(sym))
        except Exception as exc:
            print(f"{sym}: {exc}")
            continue
        tom = cond["C1 turn of month +1..+3"]
        two_dn = cond["C10 after two down days"]
        one_dn = cond["C2 after -1 sigma day"]
        cap = cond["C9 after a capitulation close"]

        print(f"\n################ {sym}  {len(d)} sessions ################")
        print("  --- the parts ---")
        block(d, tom, "C1 turn of month alone", rows, sym)
        block(d, two_dn, "C10 after two down days alone", rows, sym)
        print("  --- the combination, exploratory ---")
        block(d, tom & two_dn, "C1 AND C10", rows, sym)
        block(d, tom & ~two_dn, "C1 but NOT C10", rows, sym)
        block(d, tom & one_dn, "C1 AND after -1 sigma", rows, sym)
        block(d, tom & cap, "C1 AND capitulation", rows, sym)

        print("  --- turn of month by decade ---")
        for dec, g in d.groupby("decade"):
            x = g.loc[tom[d.index.isin(g.index)], "r_oc"].dropna().to_numpy() \
                if False else g.loc[g.index.isin(d.index[tom]), "r_oc"].dropna().to_numpy()
            if len(x) < 40:
                continue
            se = x.std(ddof=1) / np.sqrt(len(x))
            print(f"    {int(dec)}  n {len(x):4}  drift {x.mean():+.4f}%  "
                  f"t {x.mean()/se:+.2f}  WR {(x>0).mean():.4f}")

    res = pd.DataFrame(rows)
    res.to_csv(C.DATA / "reports" / "condition_combination.csv", index=False)

    print("\n=== does the combination beat its parts? ===")
    for sym, g in res.groupby("symbol"):
        def get(s):
            r = g[g.scope == s]
            return r.iloc[0] if len(r) else None
        a, b, c = get("C1 turn of month alone"), get("C10 after two down days alone"), get("C1 AND C10")
        if a is None or c is None:
            continue
        print(f"  {sym:7} C1 {a.drift_pct:+.4f}%  "
              f"C10 {b.drift_pct:+.4f}%  " if b is not None else f"  {sym:7} C1 {a.drift_pct:+.4f}%  ",
              end="")
        print(f"C1&C10 {c.drift_pct:+.4f}% (n={int(c.n)}, p={c.p:.4f}, "
              f"plac {c.placebo_p:.4f})")
    print(f"\nwrote {C.DATA / 'reports' / 'condition_combination.csv'}")


if __name__ == "__main__":
    main()
