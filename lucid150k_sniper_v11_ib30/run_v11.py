"""Initial Balance 30-minute accepted breakout for V11."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
V1_ROOT = BASE.parent / "lucid150k_sniper_v1"
sys.path.insert(0, str(V1_ROOT))
import run_dev as common  # noqa: E402

OUT = BASE / "output"
PREREG = BASE / "PREREGISTRO_LUCID150K_SNIPER_V11.md"
PREREG_SHA = "3b4c4877b5454bb151862a4d9029823201bf60e898da4a7891a3b7b4da3b663b"
FAMILY = "IB30_ACCEPTED_BREAKOUT"
RISK_TICKS = 60.0
SEED = 0x7D19E4A630C25BF8
BOOTSTRAPS = 10_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_date(date: str) -> tuple[dict | None, str | None, str]:
    try:
        nq = common.load_session(common.NQ_ROOT, date)
        if nq is None:
            return None, None, "missing_data"
        ib_start = common.local_ts(date, "09:30:00")
        ib_end = common.local_ts(date, "10:00:00")
        entry_cutoff = common.local_ts(date, "11:00:00")
        exit_cutoff = common.local_ts(date, "15:55:00")
        opening = common.opening_range(nq, ib_start, ib_end)
        if opening is None:
            return None, None, "missing_ib"
        high, low = opening
        scan = nq.loc[
            (nq.index >= ib_end) & (nq.index <= entry_cutoff)
        ]
        previous_sign = 0
        previous_time = None
        count = 0
        accepted_time = None
        accepted_sign = 0
        for timestamp, bar in scan.iterrows():
            close = float(bar["close"])
            sign = (
                1 if close >= high + common.TICK
                else -1 if close <= low - common.TICK
                else 0
            )
            consecutive = (
                previous_time is not None
                and timestamp - previous_time == pd.Timedelta(seconds=1)
            )
            if sign != 0 and sign == previous_sign and consecutive:
                count += 1
            elif sign != 0:
                count = 1
            else:
                count = 0
            previous_sign = sign
            previous_time = timestamp
            if count >= 2:
                accepted_time = timestamp
                accepted_sign = sign
                break
        if accepted_time is None:
            return None, None, "no_acceptance"
        following = nq.loc[
            (nq.index > accepted_time) & (nq.index <= entry_cutoff)
        ]
        if following.empty:
            return None, None, "no_entry_bar"
        entry_time = following.index[0]
        entry = float(following.iloc[0]["open"]) + accepted_sign * common.TICK
        row = common.trade_record(
            FAMILY,
            date,
            nq,
            entry_time,
            exit_cutoff,
            accepted_sign,
            entry,
            RISK_TICKS,
        )
        row["acceptance_utc"] = accepted_time.isoformat()
        return row, None, "trade"
    except Exception as exc:  # noqa: BLE001
        return None, repr(exc), "error"


def bootstrap_ci(values: np.ndarray) -> list[float]:
    rng = np.random.default_rng(SEED)
    means = np.empty(BOOTSTRAPS, dtype=float)
    for index in range(BOOTSTRAPS):
        means[index] = rng.choice(values, size=values.size, replace=True).mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return [round(float(low), 5), round(float(high), 5)]


def main() -> int:
    if sha256_file(PREREG) != PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    OUT.mkdir(exist_ok=True)
    dates = sorted(
        path.name for path in common.NQ_ROOT.iterdir() if path.is_dir()
    )
    rows = []
    errors = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(process_date, date): date for date in dates
        }
        complete = 0
        for future in concurrent.futures.as_completed(pending):
            date = pending[future]
            complete += 1
            row, error, disposition = future.result()
            dispositions[disposition] = dispositions.get(disposition, 0) + 1
            if row is not None:
                rows.append(row)
            if error is not None:
                errors.append({"date": date, "error": error})
            if complete % 100 == 0 or complete == len(dates):
                print(
                    f"[{complete:4d}/{len(dates)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )
    trades = pd.DataFrame(rows).sort_values("date")
    trades.to_csv(OUT / "ALL_TRADES.csv", index=False)
    (OUT / "ERRORS.json").write_text(
        json.dumps(errors, indent=2), encoding="utf-8"
    )
    dev = trades[
        (trades["date"] >= "2022-04-25")
        & (trades["date"] <= "2023-12-31")
    ]
    pseudo = trades[
        (trades["date"] >= "2024-01-01")
        & (trades["date"] <= "2024-12-31")
    ]
    stress = trades[
        (trades["date"] >= "2025-01-01")
        & (trades["date"] <= "2026-06-30")
    ]
    trail = common.metrics(dev)
    fixed = common.metrics(dev, "fixed_net_R")
    frequency = trail.get("n", 0) / 21.0
    difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
    gates = {
        "D1_n_ge_120": bool(trail.get("n", 0) >= 120),
        "D2_frequency_ge_6": bool(frequency >= 6.0),
        "D3_ev_gt_008R": bool(trail.get("ev_R", -999) > 0.08),
        "D4_pf_gt_125": bool(
            trail.get("pf") is not None and trail["pf"] > 1.25
        ),
        "D5_two_positive_years": bool(trail.get("positive_years", 0) == 2),
        "D6_positive_halves_ge_60pct": bool(
            trail.get("positive_halves_pct", 0) >= 60.0
        ),
        "D7_trailing_minus_fixed_ge_minus005R": bool(
            difference >= -0.05
        ),
    }
    dev_pass = all(gates.values())
    pseudo_result = None
    authorize_holdout = False
    if dev_pass:
        metrics = common.metrics(pseudo)
        ci = bootstrap_ci(pseudo["net_R"].to_numpy(float))
        pseudo_gates = {
            "V1_n_ge_60": bool(metrics.get("n", 0) >= 60),
            "V2_ev_gt_0": bool(metrics.get("ev_R", -999) > 0),
            "V3_pf_gt_115": bool(
                metrics.get("pf") is not None and metrics["pf"] > 1.15
            ),
            "V4_ci_low_gt_minus008R": bool(ci[0] > -0.08),
        }
        authorize_holdout = all(pseudo_gates.values())
        pseudo_result = {
            "metrics": metrics,
            "bootstrap_EV_R_CI95": ci,
            "gates": pseudo_gates,
            "PASS": authorize_holdout,
        }
    result = {
        "study": "LUCID150K-SNIPER-V11-IB30",
        "prereg_sha256": PREREG_SHA,
        "dates_scanned": len(dates),
        "errors": len(errors),
        "dispositions": dispositions,
        "DEV": {
            "TRAILING": trail,
            "FIXED_1R_DIAGNOSTIC": fixed,
            "trades_per_month": round(frequency, 4),
            "trailing_minus_fixed_EV_R": round(difference, 5),
            "gates": gates,
            "PASS": dev_pass,
        },
        "PSEUDO_VAL_2024": pseudo_result,
        "STRESS_SEEN_2025_2026": common.metrics(stress),
        "AUTHORIZE_HOLDOUT_DOWNLOAD": authorize_holdout,
        "VERDICT_STAGE": (
            "PASS_TO_HOLDOUT" if authorize_holdout else "FAIL_NO_DOWNLOAD"
        ),
    }
    (OUT / "RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
