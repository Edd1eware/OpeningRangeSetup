#!/usr/bin/env python3
"""Features de order flow (MBP+tape) por evento LVN — ventanas CAUSALES (2026-07-10).

Ventanas por evento (barras de 1 min; timestamps de barra = inicio):
  PRE : [touch-120s, touch)            — aproximación
  ZONE: [touch, entry_bar_start+60s)   — información disponible al cierre de la barra de
                                          confirmación (momento real de la decisión)
Eventos sin confirmación (UNRESOLVED) → features de ZONE en NaN (no hay entrada que filtrar).

Grupos: liquidez/profundidad (MBP), consumo/agresión (tape), refill (MBP), cancelación-proxy
(MBP sin tape en el nivel), velocidad (tape), absorción-proxy (tape+precio).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from progress import track  # progress bar obligatoria (regla global)

BOOK_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings")
BAND_TICKS = 10  # banda ±10 ticks (2.5 pts) alrededor del precio del LVN
TICK = 0.25


def _seconds(series: pd.Series) -> np.ndarray:
    parts = series.str.split(":", expand=True)
    hours = pd.to_numeric(parts[0], errors="coerce")
    minutes = pd.to_numeric(parts[1], errors="coerce")
    seconds = pd.to_numeric(parts[2] if 2 in parts.columns else np.nan, errors="coerce")
    return (hours * 3600 + minutes * 60 + seconds).to_numpy(dtype=float)


def _event_seconds(timestamp: str) -> float:
    clock = timestamp[11:19] if "T" in timestamp else timestamp[11:19]
    h, m, s = clock.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _tape_features(tape: pd.DataFrame, start: float, end: float, lvn: float, prefix: str) -> dict[str, float]:
    window = tape.loc[(tape["sec"] >= start) & (tape["sec"] < end)]
    out: dict[str, float] = {}
    duration = max(end - start, 1e-9)
    if window.empty:
        for name in ("buy_vol", "sell_vol", "delta", "total_vol", "vol_per_s", "trades_per_s",
                     "ticks_per_s", "absorption_proxy", "delta_per_s"):
            out[f"{prefix}_{name}"] = math.nan
        return out
    buy = float(window.loc[window["direction"].astype(str).str.upper().isin(["UP", "BUY", "B", "1"]), "volume"].sum())
    sell = float(window.loc[window["direction"].astype(str).str.upper().isin(["DOWN", "SELL", "S", "-1"]), "volume"].sum())
    total = float(window["volume"].sum())
    prices = window["price"].to_numpy(dtype=float)
    tick_moves = float(np.abs(np.diff(prices)).sum() / TICK) if len(prices) > 1 else 0.0
    at_lvn = window.loc[(window["price"] - lvn).abs() <= 2 * TICK + 1e-9]
    price_range_ticks = (prices.max() - prices.min()) / TICK if len(prices) else math.nan
    out[f"{prefix}_buy_vol"] = buy
    out[f"{prefix}_sell_vol"] = sell
    out[f"{prefix}_delta"] = buy - sell
    out[f"{prefix}_total_vol"] = total
    out[f"{prefix}_vol_per_s"] = total / duration
    out[f"{prefix}_delta_per_s"] = (buy - sell) / duration
    out[f"{prefix}_trades_per_s"] = len(window) / duration
    out[f"{prefix}_ticks_per_s"] = tick_moves / duration
    # Absorción-proxy: volumen ejecutado pegado al LVN mientras el precio no se desplaza.
    out[f"{prefix}_absorption_proxy"] = float(at_lvn["volume"].sum()) / max(price_range_ticks, 1.0)
    return out


def _mbp_features(mbp: pd.DataFrame, tape: pd.DataFrame, start: float, end: float, lvn: float) -> dict[str, float]:
    band_low, band_high = lvn - BAND_TICKS * TICK, lvn + BAND_TICKS * TICK
    window = mbp.loc[(mbp["sec"] >= start) & (mbp["sec"] < end)
                     & (mbp["price"] >= band_low) & (mbp["price"] <= band_high)]
    out: dict[str, float] = {}
    names = ("resting_bid_mean", "resting_ask_mean", "liq_added", "liq_removed",
             "refill_count", "refill_ratio", "cancel_proxy_ratio", "depth_levels_emptied")
    if window.empty:
        for name in names:
            out[f"zone_{name}"] = math.nan
        return out
    bid_side = window["side"].astype(str).str.upper().str.startswith("B")
    out["zone_resting_bid_mean"] = float(window.loc[bid_side, "volume"].mean())
    out["zone_resting_ask_mean"] = float(window.loc[~bid_side, "volume"].mean())

    executed_prices = set()
    tape_window = tape.loc[(tape["sec"] >= start) & (tape["sec"] < end)]
    if not tape_window.empty:
        executed_prices = set(np.round(tape_window["price"].to_numpy(dtype=float) / TICK).astype(int))

    added = removed = removed_no_trade = refills = 0.0
    emptied: set[tuple[str, int]] = set()
    for (side, price), level in window.groupby(["side", "price"], sort=False):
        volumes = level.sort_values("sec")["volume"].to_numpy(dtype=float)
        deltas = np.diff(volumes)
        level_removed = float(-deltas[deltas < 0].sum())
        level_added = float(deltas[deltas > 0].sum())
        added += level_added
        removed += level_removed
        price_bin = int(round(float(price) / TICK))
        if level_removed > 0 and price_bin not in executed_prices:
            removed_no_trade += level_removed
        # refill: caída seguida de reposición >=50% de lo caído
        drop = 0.0
        for change in deltas:
            if change < 0:
                drop += -change
            elif change > 0 and drop > 0 and change >= 0.5 * drop:
                refills += 1
                drop = 0.0
        if volumes.min() <= 0:
            emptied.add((str(side), price_bin))
    out["zone_liq_added"] = added
    out["zone_liq_removed"] = removed
    out["zone_refill_count"] = refills
    out["zone_refill_ratio"] = added / removed if removed > 0 else math.nan
    out["zone_cancel_proxy_ratio"] = removed_no_trade / removed if removed > 0 else math.nan
    out["zone_depth_levels_emptied"] = float(len(emptied))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", required=True, help="CSV consolidado de LVN_Events")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    bank = pd.read_csv(args.bank)
    covered = {p.name[5:15] for p in BOOK_DIR.glob("tape_*.csv")}
    events = bank.loc[bank["date"].isin(covered)].copy()
    print(f"eventos en fechas con grabaciones: {len(events)} de {len(bank)}")

    rows = []
    for date_iso, day_events in track(list(events.groupby("date")), label="Order flow por fecha"):
        tape_path = BOOK_DIR / f"tape_{date_iso}_NY.csv"
        mbp_path = BOOK_DIR / f"mbp_{date_iso}_NY.csv"
        if not tape_path.exists():
            continue
        tape = pd.read_csv(tape_path)
        tape["sec"] = _seconds(tape["time_ny"].astype(str))
        tape["price"] = pd.to_numeric(tape["price"], errors="coerce")
        tape["volume"] = pd.to_numeric(tape["volume"], errors="coerce")
        tape = tape.dropna(subset=["sec", "price", "volume"])
        if tape.empty or str(tape["time_ny"].max()) < "09:39":
            continue  # grabación vieja que no cubre la ventana de retest
        mbp = pd.read_csv(mbp_path) if mbp_path.exists() else pd.DataFrame(columns=["time_ny", "side", "price", "volume"])
        if len(mbp):
            mbp["sec"] = _seconds(mbp["time_ny"].astype(str))
            mbp["price"] = pd.to_numeric(mbp["price"], errors="coerce")
            mbp["volume"] = pd.to_numeric(mbp["volume"], errors="coerce")
            mbp = mbp.dropna(subset=["sec", "price", "volume"])
        for _, event in day_events.iterrows():
            touch = _event_seconds(str(event["retest_time_et"]))
            entry_raw = event.get("entry_time_et")
            resolved = isinstance(entry_raw, str) and len(entry_raw) >= 19
            entry_close = _event_seconds(entry_raw) + 60.0 if resolved else math.nan
            lvn = float(event["lvn_price"])
            row: dict[str, object] = {"event_id": event["event_id"]}
            row.update(_tape_features(tape, touch - 120.0, touch, lvn, "pre"))
            if resolved:
                row.update(_tape_features(tape, touch, entry_close, lvn, "zone"))
                if len(mbp):
                    row.update(_mbp_features(mbp, tape, touch, entry_close, lvn))
                row["flow_speed_ratio"] = (
                    row.get("zone_vol_per_s", math.nan) / row["pre_vol_per_s"]
                    if row.get("pre_vol_per_s") else math.nan
                )
            rows.append(row)
    flow = pd.DataFrame(rows)
    merged = events.merge(flow, on="event_id", how="inner")
    merged.to_csv(args.output, index=False)
    flow_cols = [c for c in flow.columns if c != "event_id"]
    print(f"eventos con flujo: {len(merged)} | features de flujo: {len(flow_cols)}")
    print(f"salida: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
