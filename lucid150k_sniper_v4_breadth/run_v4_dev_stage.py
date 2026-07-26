"""DEV-only gate for V4, used while later outcome-blind data downloads."""

from __future__ import annotations

import concurrent.futures
import json
import os

import pandas as pd

import run_v4 as study


def main() -> int:
    if study.sha256_file(study.PREREG) != study.PREREG_SHA:
        raise SystemExit("Preregistration hash mismatch")
    study.OUT.mkdir(exist_ok=True)
    nq_dates = {
        path.name for path in study.common.NQ_ROOT.iterdir()
        if path.is_dir() and "2022-04-25" <= path.name <= "2023-12-31"
    }
    es_dates = {
        path.name for path in study.common.ES_ROOT.iterdir()
        if path.is_dir() and "2022-04-25" <= path.name <= "2023-12-31"
    }
    expected = sorted(nq_dates & es_dates)
    missing = [
        date for date in expected
        if not (
            study.MULTI_ROOT
            / date
            / "ohlcv-1s"
            / "ym_rty.dbn.zst"
        ).exists()
    ]
    if missing:
        raise SystemExit(f"DEV multi coverage incomplete: {len(missing)}")

    rows = []
    errors = []
    dispositions: dict[str, int] = {}
    workers = min(4, os.cpu_count() or 1)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers
    ) as executor:
        pending = {
            executor.submit(study.process_date, date): date
            for date in expected
        }
        complete = 0
        for future in concurrent.futures.as_completed(pending):
            date = pending[future]
            complete += 1
            try:
                row, error, disposition = future.result()
                dispositions[disposition] = dispositions.get(disposition, 0) + 1
                if row is not None:
                    rows.append(row)
                if error is not None:
                    errors.append({"date": date, "error": error})
            except Exception as exc:  # noqa: BLE001
                errors.append({"date": date, "error": repr(exc)})
            if complete % 100 == 0 or complete == len(expected):
                print(
                    f"[{complete:4d}/{len(expected)}] trades={len(rows)} "
                    f"errors={len(errors)}",
                    flush=True,
                )

    trades = pd.DataFrame(rows).sort_values("date")
    trades.to_csv(study.OUT / "DEV_STAGE_TRADES.csv", index=False)
    trail = study.common.metrics(trades)
    fixed = study.common.metrics(trades, "fixed_net_R")
    difference = trail.get("ev_R", 0) - fixed.get("ev_R", 0)
    gates = {
        "D1_n_ge_40": bool(trail.get("n", 0) >= 40),
        "D2_ev_gt_008R": bool(trail.get("ev_R", -999) > 0.08),
        "D3_pf_gt_125": bool(
            trail.get("pf") is not None and trail["pf"] > 1.25
        ),
        "D4_two_positive_years": bool(trail.get("positive_years", 0) == 2),
        "D5_positive_halves_ge_60pct": bool(
            trail.get("positive_halves_pct", 0) >= 60.0
        ),
        "D6_trailing_minus_fixed_ge_minus005R": bool(
            difference >= -0.05
        ),
    }
    result = {
        "study": "LUCID150K-SNIPER-V4-BREADTH",
        "stage": "DEV_ONLY",
        "prereg_sha256": study.PREREG_SHA,
        "dates_scanned": len(expected),
        "errors": len(errors),
        "dispositions": dispositions,
        "TRAILING": trail,
        "FIXED_1R_DIAGNOSTIC": fixed,
        "trailing_minus_fixed_EV_R": round(difference, 5),
        "gates": gates,
        "PASS_DEV": all(gates.values()),
        "CONTINUE_PSEUDO_DOWNLOAD": all(gates.values()),
    }
    (study.OUT / "DEV_STAGE_RESULT.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
