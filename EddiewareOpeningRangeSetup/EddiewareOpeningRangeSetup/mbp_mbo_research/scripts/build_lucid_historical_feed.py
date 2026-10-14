"""Export the observed Lucid executions for historical ATAS navigation.

Read-only with respect to the source XLSX. Outputs are staged in a new directory;
the active ATAS CSV and cursor are never changed by this script. A same-second
entry group is a navigation proxy, not a broker position identifier. Initial SL,
TP and risk are unknown in the workbook. A structural bracket may be reconstructed
from the last closed candle proxy and is explicitly distinguished from observed
historical orders. Without sufficient levels the bracket is left blank.

Run with the bundled Python (openpyxl), for example::

    python build_lucid_historical_feed.py --output-dir OUTPUT_DIR

The first 35 ATAS columns preserve the existing interface. ``fills`` adds the
observed partial executions: TradeId,Qty,OpenClock,OpenPrice,CloseClock,
ClosePrice,NetPnL,Commission; fills are separated by '|'. No semicolons occur
inside packed values. ``net_*`` are source-reported P&L, not a modeled fee case.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(r"C:/Users/k_99_/Documents/ChatGPT/research_edge")
DEFAULT_SOURCE = ROOT / "lucid_account_passed100k/Lucid_account_passed_columns.xlsx"
DEFAULT_OUT = WORKSPACE / "outputs/lucid_historical_feed_v1"
DEFAULT_OR = WORKSPACE / "outputs/calibrated_setup_replay_v1/candidates.csv"
DEFAULT_LEVELS = WORKSPACE / "outputs/calibrated_setup_replay_v1/levels.csv"
DEFAULT_BARS = WORKSPACE / "outputs/calibrated_setup_replay_v1/bars.csv"
DEFAULT_PREVIOUS = WORKSPACE / "outputs/passed_account_audit_v1/records.json"
DEFAULT_ACTIVE = Path(r"C:/Users/k_99_/Desktop/codding/data_footprint_generator/lucid_real_trades.csv")
TICK = Decimal("0.25")
USD_PER_POINT = Decimal("20")
USD_PER_TICK = Decimal("5")
CUTOFF = time(9, 40)
ATAS_BASE_COLUMNS = [
    "n", "session", "minute", "candle_start", "signal_close", "dir",
    "or_high", "or_low", "o", "h", "l", "c", "raw_o", "raw_h", "raw_l", "raw_c",
    "vwap", "entry", "stop", "target", "exit", "risk_ticks", "result", "net_ticks",
    "net_r", "net_usd", "mae", "mfe", "duration_s", "entry_clock", "exit_clock",
    "source", "warn", "imb_rows",
]
ATAS_EXTRA_COLUMNS = [
    "qty", "fill_count", "group_key", "instrument", "gross_usd", "source_net_usd",
    "source_commission_usd", "modeled_commission_usd", "fills", "bracket_source",
    "signal_candle_source", "entry_bar_start", "source_trade_ids", "exit_time_count",
    "grouping_source", "pnl_source", "source_sha256", "entry_price_weighted",
    "exit_price_weighted",
    "bracket_disposition", "context_source", "context_source_id",
]


def decimal(value) -> Decimal:
    return Decimal(str(value))


def plain(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def jsonable(value):
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_clock(value) -> str:
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return datetime.strptime(str(value).strip(), "%H:%M:%S").strftime("%H:%M:%S")


def read_source(path: Path) -> tuple[list[dict], dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = wb["Trades"]
        rows = sheet.iter_rows(values_only=True)
        headers = list(next(rows))
        required = {"TradeId", "Account", "Instrument", "Date", "Side", "Qty",
                    "OpenClock", "OpenPrice", "CloseClock", "ClosePrice", "Ticks",
                    "GrossPnL", "Commission", "NetPnL", "DurationSec"}
        if not required.issubset(headers):
            raise ValueError(f"Missing source columns: {required - set(headers)}")
        records = []
        for excel_row, cells in enumerate(rows, 2):
            if not any(value is not None for value in cells):
                continue
            row = dict(zip(headers, cells))
            row["Date"] = row["Date"].strftime("%Y-%m-%d")
            row["OpenClock"] = as_clock(row["OpenClock"])
            row["CloseClock"] = as_clock(row["CloseClock"])
            row["Qty"] = int(row["Qty"])
            row["TradeId"] = str(row["TradeId"])
            row["source_excel_row"] = excel_row
            records.append(row)
        metadata = {"sheet": "Trades", "range": f"A1:U{sheet.max_row}",
                    "headers": headers, "rows": len(records)}
    finally:
        wb.close()
    ids = [row["TradeId"] for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate TradeId: source cannot be joined unambiguously")
    return records, metadata


def stamp(row: dict, clock: str) -> datetime:
    return datetime.fromisoformat(f"{row['Date']}T{row[clock]}")


def validate_source(records: list[dict]) -> list[dict]:
    checks = []
    for row in records:
        if row["Side"] not in ("Long", "Short") or row["Qty"] <= 0:
            raise ValueError(f"Invalid side/quantity: {row['TradeId']}")
        direction = 1 if row["Side"] == "Long" else -1
        points = direction * (decimal(row["ClosePrice"]) - decimal(row["OpenPrice"]))
        ticks = points / TICK
        gross = points * USD_PER_POINT * row["Qty"]
        duration = (stamp(row, "CloseClock") - stamp(row, "OpenClock")).total_seconds()
        if duration < 0:
            raise ValueError("Overnight executions need explicit close dates")
        expected = {"Ticks": ticks, "GrossPnL": gross,
                    "NetPnL": gross - decimal(row["Commission"]),
                    "DurationSec": decimal(duration)}
        if "Points" in row:
            expected["Points"] = points
        for field, want in expected.items():
            if decimal(row[field]) != want:
                checks.append({"trade_id": row["TradeId"], "field": field,
                               "recorded": str(row[field]), "expected": str(want)})
    if checks:
        raise ValueError(f"Source arithmetic inconsistencies: {checks}")
    return checks


def stats(values: list[Decimal]) -> dict:
    pos = sum((v for v in values if v > 0), Decimal(0))
    neg = -sum((v for v in values if v < 0), Decimal(0))
    wins = sum(v > 0 for v in values)
    return {"count": len(values), "wins": wins, "losses": sum(v < 0 for v in values),
            "flat": sum(v == 0 for v in values),
            "wr_percent": 100 * wins / len(values) if values else None,
            "profit_factor": float(pos / neg) if neg else None,
            "positive_usd": pos, "loss_absolute_usd": neg,
            "pnl_usd": sum(values, Decimal(0))}


def selected(row: dict, whole_minute=False) -> bool:
    clock = time.fromisoformat(row["OpenClock"])
    return clock < time(9, 41) if whole_minute else clock <= CUTOFF


def build_groups(records: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in records:
        groups[(row["Account"], row["Instrument"], row["Date"],
                row["Side"], row["OpenClock"])].append(row)
    result = []
    for key, fills in sorted(groups.items(), key=lambda item: (item[0][2], item[0][4], item[0][3])):
        _, instrument, session, side, open_clock = key
        qty = sum(row["Qty"] for row in fills)
        weighted_open = sum((decimal(row["OpenPrice"]) * row["Qty"] for row in fills), Decimal(0)) / qty
        weighted_close = sum((decimal(row["ClosePrice"]) * row["Qty"] for row in fills), Decimal(0)) / qty
        gross = sum((decimal(row["GrossPnL"]) for row in fills), Decimal(0))
        net = sum((decimal(row["NetPnL"]) for row in fills), Decimal(0))
        commission = sum((decimal(row["Commission"]) for row in fills), Decimal(0))
        close_clock = max(row["CloseClock"] for row in fills)
        entry_at = datetime.fromisoformat(f"{session}T{open_clock}")
        entry_bar = entry_at.replace(second=0, microsecond=0)
        signal_proxy = entry_bar - timedelta(minutes=1)
        result.append({
            "n": len(result) + 1,
            "group_key": f"LUCID_{session.replace('-', '')}_{open_clock.replace(':', '')}_{'L' if side == 'Long' else 'S'}_{instrument}",
            "session": session, "instrument": instrument, "side": side,
            "dir": 1 if side == "Long" else -1,
            "entry_clock": open_clock, "exit_clock": close_clock,
            "entry_bar_start": entry_bar.strftime("%H:%M:%S"),
            "candle_start": signal_proxy.strftime("%H:%M:%S"),
            "signal_close": entry_bar.strftime("%H:%M:%S"),
            "signal_candle_source": "last_closed_proxy",
            "qty": qty, "fill_count": len(fills),
            "entry": weighted_open, "exit": weighted_close,
            "entry_price_weighted": weighted_open, "exit_price_weighted": weighted_close,
            "gross_usd": gross, "source_net_usd": net, "source_commission_usd": commission,
            "gross_ticks_per_contract": gross / qty / USD_PER_TICK,
            "net_ticks": net / qty / USD_PER_TICK,
            "net_usd": net, "result": "WIN" if net > 0 else "LOSS" if net < 0 else "FLAT",
            "duration_s": int((datetime.fromisoformat(f"{session}T{close_clock}") - entry_at).total_seconds()),
            "exit_time_count": len({row["CloseClock"] for row in fills}),
            "source_trade_ids": ",".join(str(row["TradeId"]) for row in fills),
            "fills": "|".join(
                ",".join(plain(row[field]) for field in (
                    "TradeId", "Qty", "OpenClock", "OpenPrice", "CloseClock", "ClosePrice", "NetPnL", "Commission"))
                for row in fills),
            "bracket_source": "unknown", "grouping_source": "entry_second_proxy_no_position_id",
            "pnl_source": "workbook_NetPnL_recorded_commission_only",
            "_fills": fills,
        })
    return result


def opening_ranges(path: Path) -> dict:
    ranges = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                pair = (decimal(row["or_high"]), decimal(row["or_low"]))
                if row["session"] in ranges and ranges[row["session"]] != pair:
                    raise ValueError(f"OR inconsistent in candidates: {row['session']}")
                ranges[row["session"]] = pair
    return ranges


def load_context(levels_path: Path, bars_path: Path) -> tuple[dict, dict]:
    levels, bars = defaultdict(list), {}
    if levels_path.exists():
        with levels_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                levels[(row["session"], row["minute"])].append(row)
    if bars_path.exists():
        with bars_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                bars[(row["session"], row["minute"])] = row
    return levels, bars


def reconstructed_bracket(group: dict, levels: dict, bars: dict) -> tuple[dict, dict]:
    """Follow the user-confirmed farthest imbalance/1:1 rule on a labeled proxy.

    This function does not infer an actual order or recalculate observed P&L.
    It also does not require the proxy to pass strategy entry filters: real fills
    remain real fills even when they disagree with the replay rule.
    """
    key = (group["session"], group["candle_start"][:5])
    source_levels = sorted(levels.get(key, []), key=lambda row: decimal(row["price_label"]))
    bar = bars.get(key)
    prices = {decimal(row["price_label"]): row for row in source_levels}
    direction = group["dir"]
    aligned = []
    for row in source_levels:
        flag = "buy_imbalance" if direction > 0 else "sell_imbalance"
        if row[flag].lower() != "true":
            continue
        label = decimal(row["price_label"])
        neighbor = prices.get(label - Decimal("1.25") if direction > 0 else label + Decimal("1.25"))
        volume = int(row["ask"] if direction > 0 else row["bid"])
        reference = int(neighbor["bid"] if direction > 0 else neighbor["ask"]) if neighbor else None
        if reference is None:
            raise ValueError(f"Imbalance flag lacks internal diagonal reference: {key} {label}")
        ratio = Decimal(volume) / reference if reference else None
        aligned.append({"label": label, "row_lo": decimal(row["row_lo"]),
                        "row_hi": decimal(row["row_hi"]), "volume": volume,
                        "reference": reference, "ratio": ratio,
                        "ratio_infinite": reference == 0, "source_id": row["source_id"],
                        "source_kind": row["source_kind"]})
    reconstructed = {"bracket_source": "unknown", "bracket_disposition": "missing_context",
                     "context_source": bar["source_kind"] if bar else "",
                     "context_source_id": bar["source_id"] if bar else ""}
    evidence = {"group_n": group["n"], "group_key": group["group_key"],
                "session": group["session"], "entry_clock": group["entry_clock"],
                "proxy_candle_start": group["candle_start"], "proxy_signal_close": group["signal_close"],
                "signal_candle_source": "last_closed_proxy", "aligned_rows": aligned,
                "actual_historical_SL_TP_verified": False,
                "rule": "long min(row_lo)-1.25; short max(row_hi)+1.25; TP 1:1 from Qty-weighted actual entry"}
    if bar:
        for source, destination in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"),
                                    ("raw_open", "raw_o"), ("raw_high", "raw_h"),
                                    ("raw_low", "raw_l"), ("raw_close", "raw_c"), ("vwap", "vwap")):
            reconstructed[destination] = decimal(bar[source]) if bar.get(source) else ""
    if source_levels:
        reconstructed["bracket_disposition"] = "no_aligned_imbalance"
    if aligned:
        stop = min(row["row_lo"] for row in aligned) - Decimal("1.25") if direction > 0 else max(row["row_hi"] for row in aligned) + Decimal("1.25")
        signed_risk = direction * (group["entry"] - stop)
        evidence["proposed_stop"] = stop
        if signed_risk <= 0:
            reconstructed["bracket_disposition"] = "reconstructed_stop_not_adverse"
        else:
            reconstructed.update({"bracket_source": "reconstructed_databento_last_closed_proxy",
                                  "bracket_disposition": "reconstructed_unverified",
                                  "stop": stop, "target": group["entry"] + direction * signed_risk,
                                  "risk_ticks": signed_risk / TICK})
        reconstructed["imb_rows"] = "|".join(
            ":".join(plain(value) for value in (row["row_lo"], row["row_hi"], row["volume"],
                                                row["reference"], row["ratio"] if row["ratio"] is not None else 0))
            for row in aligned)
    evidence.update({"reconstruction": reconstructed,
                     "infinite_ratio_packing": "ratio=0 numeric sentinel only when reference=0; evidence ratio=null and ratio_infinite=true"})
    return reconstructed, evidence


def write_csv(path: Path, columns: list[str], rows: list[dict], delimiter=",") -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, columns, delimiter=delimiter, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: plain(row.get(k)) for k in columns})


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=jsonable) + "\n", encoding="utf-8")


def prior_comparison(path: Path, current: list[dict]) -> dict:
    if not path.exists():
        return {"available": False}
    previous = json.loads(path.read_text(encoding="utf-8"))
    previous_records = previous["records"]
    old_by_id = {str(row["TradeId"]): row for row in previous_records}
    changed = []
    new = []
    compare_fields = ("Date", "Side", "Qty", "OpenClock", "OpenPrice", "CloseClock", "ClosePrice",
                      "Ticks", "GrossPnL", "Commission", "NetPnL", "Instrument")
    for row in current:
        prior = old_by_id.get(row["TradeId"])
        if prior is None:
            new.append(row["TradeId"])
            continue
        for field in compare_fields:
            left, right = row[field], prior[field]
            try:
                equal = decimal(left) == decimal(right)
            except Exception:
                equal = str(left) == str(right)
            if not equal:
                changed.append({"trade_id": row["TradeId"], "field": field,
                                "current": str(left), "prior": str(right)})
    current_ids = {row["TradeId"] for row in current}
    old_cutoffs = {}
    for label, minute in (("entry_le_09_40_00", False), ("entire_09_40_minute", True)):
        subset = [row for row in previous_records if selected(row, minute)]
        group_values = build_groups(subset)
        old_cutoffs[label] = {"fills": len(subset),
                            "entry_groups": stats([g["source_net_usd"] for g in group_values]),
                            "same_trade_ids_as_current": current_ids == {str(r["TradeId"]) for r in subset}}
    boundary = [row for row in previous_records if selected(row, True) and not selected(row)]
    return {"available": True, "prior_snapshot": str(path),
            "prior_snapshot_sha256": digest(path),
            "prior_workbook_sha256": previous.get("source_sha256"),
            "prior_rows": len(previous_records), "current_rows": len(current),
            "new_trade_ids": new, "changed_execution_fields": changed,
            "removed_trade_ids": sorted(set(old_by_id) - current_ids, key=int),
            "prior_snapshot_cutoffs_only": old_cutoffs,
            "prior_boundary_rows_not_in_current_source": boundary,
            "note": "Prior audit JSON is a retained derived snapshot; original 78-row XLSX is not available here. Source row numbering and CumPnL can differ after filtering."}


def build(args) -> dict:
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Output directory must be empty to preserve earlier runs: {out}")
    source_hash = digest(args.source)
    active_hash = digest(DEFAULT_ACTIVE) if DEFAULT_ACTIVE.exists() else None
    records, metadata = read_source(args.source)
    validate_source(records)
    included = [row for row in records if selected(row)]
    excluded = [row for row in records if not selected(row)]
    if not included:
        raise ValueError("No source executions satisfy entry <=09:40:00 NY")
    groups = build_groups(included)
    ranges = opening_ranges(args.or_source)
    levels, bars = load_context(args.levels_source, args.bars_source)
    feeds = []
    bracket_evidence = []
    for group in groups:
        warn = ["SIN_SL_TP_REGISTRADOS", "SENAL_ULTIMA_VELA_CERRADA_PROXY"]
        if group["source_commission_usd"] == 0:
            warn.append("COMISION_FUENTE_CERO")
        if group["exit_time_count"] > 1:
            warn.append(f"SALIDAS_PARCIALES_{group['exit_time_count']}")
        if group["session"] not in ranges:
            warn.append("SIN_RANGO_DE_APERTURA")
        feed = {k: "" for k in ATAS_BASE_COLUMNS + ATAS_EXTRA_COLUMNS}
        feed.update({k: v for k, v in group.items() if not k.startswith("_")})
        reconstructed, evidence = reconstructed_bracket(group, levels, bars)
        feed.update(reconstructed)
        bracket_evidence.append(evidence)
        if reconstructed["bracket_source"] != "unknown":
            warn.append("SENAL_NO_CONFIRMADA_SL_RECONSTRUIDO")
        else:
            warn.append("BRACKET_NO_RECONSTRUIDO")
        feed.update({"minute": group["candle_start"][:5], "source": "LUCID_REAL",
                     "warn": ",".join(warn), "source_sha256": source_hash})
        if group["session"] in ranges:
            feed["or_high"], feed["or_low"] = ranges[group["session"]]
        feeds.append(feed)
    group_by_fill = {r["TradeId"]: group["n"] for group in groups for r in group["_fills"]}
    exported_fills = []
    for row in records:
        exported_fills.append({**row, "group_n": group_by_fill.get(row["TradeId"], ""),
                               "included_entry_le_09_40_00": row["TradeId"] in group_by_fill,
                               "source_sha256": source_hash})
    sessions = []
    for session in sorted({g["session"] for g in groups}):
        gs = [g for g in groups if g["session"] == session]
        latest_exit = max(g["exit_clock"] for g in gs)
        end = max(datetime.fromisoformat(f"{session}T09:50:00"),
                  datetime.fromisoformat(f"{session}T{latest_exit}").replace(second=0) + timedelta(minutes=2))
        sessions.append({"session": session, "group_count": len(gs),
                         "group_ns": ",".join(str(g["n"]) for g in gs),
                         "replay_from": "09:30:00", "replay_to": end.strftime("%H:%M:%S"),
                         "first_entry": min(g["entry_clock"] for g in gs), "last_exit": latest_exit})
    metrics = stats([g["source_net_usd"] for g in groups])
    summary = {
        "schema": "lucid_historical_feed_v1", "source": str(args.source.resolve()),
        "source_sha256": source_hash, "source_sheet": metadata,
        "timezone": "America/New_York", "timezone_provenance": "direct user confirmation",
        "selection": "OpenClock <=09:40:00 NY; no lower bound; keep all subsequent exits of each included row",
        "source_rows": len(records), "included_fills": len(included), "excluded_fills": len(excluded),
        "included_source_rows": stats([decimal(r["NetPnL"]) for r in included]),
        "entry_second_groups": metrics, "sessions": len(sessions),
        "quantity_contracts": sum(g["qty"] for g in groups),
        "source_recorded_commission_usd": sum((g["source_commission_usd"] for g in groups), Decimal(0)),
        "modeled_commission_applied": False,
        "hypothetical_4usd_per_contract_only": stats([g["source_net_usd"] - Decimal(4) * g["qty"] for g in groups]),
        "bracket_source": "unknown in account; some drawn brackets reconstructed from Databento last-closed proxy; no historical SL/TP verified",
        "bracket_dispositions": dict(Counter(row["bracket_disposition"] for row in feeds)),
        "bracket_reconstructed_groups": [row["n"] for row in feeds if row["bracket_disposition"] == "reconstructed_unverified"],
        "context_files": {str(path.resolve()): digest(path) if path.exists() else None
                          for path in (args.or_source, args.levels_source, args.bars_source)},
        "signal_candle_source": "last_closed_proxy; not a user-confirmed signal candle",
        "grouping": "Account+Instrument+Date+Side+OpenClock to second; position ID unavailable",
        "partial_exit_groups": [g["n"] for g in groups if g["exit_time_count"] > 1],
        "sessions_with_multiple_entry_groups": [s for s in sessions if s["group_count"] > 1],
        "missing_or_sessions": sorted({g["session"] for g in groups} - set(ranges)),
        "arithmetic_checks": "PASS: all source point/tick/P&L/duration fields consistent",
        "source_unchanged": digest(args.source) == source_hash,
        "active_atas_csv_unchanged": (digest(DEFAULT_ACTIVE) if DEFAULT_ACTIVE.exists() else None) == active_hash,
        "active_atas_csv_sha256_before": active_hash,
        "generator_sha256": digest(Path(__file__)),
    }
    if not summary["source_unchanged"] or not summary["active_atas_csv_unchanged"]:
        raise RuntimeError("Input changed during export; do not activate these outputs")
    previous_comparison = prior_comparison(args.prior_snapshot, records)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "source_snapshot.json", {"source_sha256": source_hash, "metadata": metadata, "records": records})
    write_csv(out / "fills.csv", list(exported_fills[0]), exported_fills)
    write_csv(out / "entry_groups.csv", [k for k in groups[0] if not k.startswith("_")], groups)
    write_csv(out / "atas_trades.csv", ATAS_BASE_COLUMNS + ATAS_EXTRA_COLUMNS, feeds, ";")
    write_csv(out / "sessions.csv", list(sessions[0]), sessions)
    write_json(out / "summary.json", summary)
    write_json(out / "bracket_reconstruction_evidence.json", bracket_evidence)
    write_json(out / "prior_source_comparison.json", previous_comparison)
    # A small durable database for fast audit/joins; all exact Decimal values use
    # TEXT rather than SQLite REAL so repeating weighted means are not rounded.
    with sqlite3.connect(out / "lucid_history.sqlite") as db:
        for name, values in (("fills", exported_fills), ("entry_groups", feeds), ("sessions", sessions)):
            columns = list(values[0])
            quoted = [f'"{c}"' for c in columns]
            db.execute(f'CREATE TABLE "{name}" ({", ".join(c + " TEXT" for c in quoted)})')
            db.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in columns)})',
                           [[plain(row.get(c)) for c in columns] for row in values])
        db.execute('CREATE INDEX groups_session ON entry_groups(session)')
        db.execute('CREATE UNIQUE INDEX fills_trade_id ON fills(TradeId)')
    readme = f"""# Historial Lucid para recorrido y capturas ATAS

Fuente actual: `{args.source}`. SHA256 `{source_hash}`. Hoja `Trades`, {metadata['range']}.

Filtro: entrada **<=09:40:00 Nueva York**, sin límite inferior añadido. Se conservan Qty y todas las salidas de cada fila incluida. El XLSX y el CSV activo no se modificaron.

- {len(included)} filas de ejecuciones, {len(groups)} grupos de entrada por segundo, {len(sessions)} sesiones y {summary['quantity_contracts']} contratos.
- WR por grupo {metrics['wr_percent']:.2f}%; PF por grupo {metrics['profit_factor']:.6f}; P&L reportado ${metrics['pnl_usd']:+,.2f}.
- Comisiones registradas ${summary['source_recorded_commission_usd']:,.2f}. No se descontó ninguna comisión inventada. La simulación separada a $4/contrato aparece solo en summary.json y no alimenta ATAS.

`atas_trades.csv` conserva las 35 columnas de la interfaz y añade Qty, fills empaquetados y procedencia. `fills.csv` preserva los precios y relojes de cada TradeId; los precios promedio del grupo son ponderados por Qty y pueden no ser un tick válido. Dibujar cada ejecución desde `fills` evita confundir el promedio con un fill real.

**SL/TP iniciales, riesgo, R, MAE/MFE, vela de señal y razón de cierre no están en la cuenta.** R/MAE/MFE van vacíos. A petición del usuario se reconstruye un bracket estructural 1:1 usando los imbalances alineados de la última vela cerrada: compra min(row_lo)-1.25, venta max(row_hi)+1.25. Solo se escribe cuando el stop queda del lado adverso de la entrada real ponderada. Se etiqueta `reconstructed_databento_last_closed_proxy` y **no constituye una orden histórica verificada**. Grupos por estado: {summary['bracket_dispositions']}. Sin datos/imbalance/stop válido quedan vacíos.

WIN/LOSS describe el signo del P&L observado del grupo; no demuestra TP/SL ni depende del bracket reconstruido. `candle_start` representa la última vela cerrada antes de entrar y está etiquetada `last_closed_proxy`. `entry_bar_start` ancla la ejecución observada. El OHLC/VWAP de esa vela procede de Databento local, no del Excel. La evidencia por grupo está en bracket_reconstruction_evidence.json.

Los grupos por hora son una aproximación de navegación, sin identificador de posición del broker. Hay fechas con varias entradas y puede haber escalado/solapamiento; no se impone una sola entrada diaria para borrar ejecuciones reales.

El OR se importa de la corrida calibrada y tiene procedencia distinta de la cuenta. Sesiones sin OR local: {summary['missing_or_sessions']}.

Archivos: source_snapshot.json, fills.csv, entry_groups.csv, atas_trades.csv, sessions.csv, summary.json, lucid_history.sqlite, bracket_reconstruction_evidence.json y prior_source_comparison.json. La comparación con el snapshot anterior distingue el XLSX actual de 50 filas de la copia derivada previa de 78; no mezcla sus estadísticas.

Para activar, el orquestador debe auditar el CSV, adaptar el indicador a `fills` y copiarlo de forma atómica al feed activo. Este exportador no mueve ATAS, no compila, no envía órdenes ni altera el cursor.
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    write_json(out / "manifest.json", {"source_sha256": source_hash, "files": {
        p.name: digest(p) for p in sorted(out.iterdir()) if p.is_file()}})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--or-source", type=Path, default=DEFAULT_OR)
    parser.add_argument("--levels-source", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--bars-source", type=Path, default=DEFAULT_BARS)
    parser.add_argument("--prior-snapshot", type=Path, default=DEFAULT_PREVIOUS)
    args = parser.parse_args()
    with localcontext() as context:
        context.prec = 28
        result = build(args)
    print(json.dumps({"output_dir": str(args.output_dir.resolve()),
                      "included_fills": result["included_fills"],
                      "entry_second_groups": result["entry_second_groups"],
                      "sessions": result["sessions"], "source_sha256": result["source_sha256"]},
                     ensure_ascii=False, indent=2, default=jsonable))


if __name__ == "__main__":
    main()
