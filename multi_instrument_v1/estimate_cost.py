"""Free cost estimate for YM + RTY ohlcv-1s, matching the existing NQ/ES setup."""

from __future__ import annotations

import json
from pathlib import Path

import databento as db
import pandas as pd

BASE = Path(__file__).resolve().parent
NQ_ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
               r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2")
KEY = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
           r"\databento_api_key.txt")
DATASET, SCHEMA, STYPE = "GLBX.MDP3", "ohlcv-1s", "continuous"
UTC_START, UTC_END = "13:00", "21:05"
INSTRUMENTS = {"YM": "YM.c.0", "RTY": "RTY.c.0"}


def main() -> int:
    days = sorted(p.name for p in NQ_ROOT.iterdir() if p.is_dir())
    print(f"dias a cotizar: {len(days)}  ({days[0]} .. {days[-1]})")
    client = db.Historical(KEY.read_text(encoding="utf-8").strip())
    out = {}
    for inst, sym in INSTRUMENTS.items():
        # quote the whole range in one call (cheap, single metadata request)
        start = f"{days[0]}T{UTC_START}:00Z"
        end = f"{days[-1]}T{UTC_END}:00Z"
        cost = float(client.metadata.get_cost(
            dataset=DATASET, symbols=[sym], schema=SCHEMA,
            start=start, end=end, stype_in=STYPE))
        out[inst] = {"symbol": sym, "cost_usd_rango_completo": round(cost, 4)}
        print(f"{inst:4s} {sym:8s} rango completo: ${cost:.4f}")
    total = sum(v["cost_usd_rango_completo"] for v in out.values())
    out["TOTAL_USD"] = round(total, 4)
    out["nota"] = ("cotizacion del rango continuo completo; la descarga real "
                   "se hace por dia y solo la ventana 13:00-21:05Z")
    print(f"\nTOTAL estimado: ${total:.4f}")
    (BASE / "COST_ESTIMATE.json").write_text(json.dumps(out, indent=2),
                                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
