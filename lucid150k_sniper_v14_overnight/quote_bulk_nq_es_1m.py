"""Free cost quote for one bulk NQ+ES 1-minute request."""

from pathlib import Path

import databento as db

KEY_PATH = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
    r"\databento_api_key.txt"
)

client = db.Historical(KEY_PATH.read_text(encoding="utf-8").strip())
cost = float(
    client.metadata.get_cost(
        dataset="GLBX.MDP3",
        symbols=["NQ.c.0", "ES.c.0"],
        schema="ohlcv-1m",
        start="2022-04-24T22:00:00Z",
        end="2026-06-30T13:30:00Z",
        stype_in="continuous",
    )
)
print(f"BULK_QUOTE_USD={cost:.6f}")
