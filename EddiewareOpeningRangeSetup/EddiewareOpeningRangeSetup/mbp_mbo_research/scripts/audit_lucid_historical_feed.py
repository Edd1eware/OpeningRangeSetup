"""Independently audit the staged Lucid feed against OOXML source cells.

No imports from the feed generator, no UI, no source or feed mutation. Writes
only audit_verification.json in the staging output directory.
"""

import argparse
import csv
import hashlib
import json
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def source_rows(path):
    with zipfile.ZipFile(path) as archive:
        wb = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        sheet = next(s for s in wb.findall("s:sheets/s:sheet", NS) if s.attrib["name"] == "Trades")
        relation = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = relations[relation].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(n.itertext()) for n in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        rows = []
        for r in ET.fromstring(archive.read(target)).findall("s:sheetData/s:row", NS):
            values = {}
            for cell in r:
                column = "".join(c for c in cell.attrib["r"] if c.isalpha())
                inline, value = cell.find("s:is", NS), cell.find("s:v", NS)
                value = "".join(inline.itertext()) if inline is not None else value.text if value is not None else ""
                if cell.attrib.get("t") == "s":
                    value = shared[int(value)]
                values[column] = value
            rows.append(values)
        header = rows.pop(0)
        result = [{name: row.get(column, "") for column, name in header.items()} for row in rows]
        props = wb.find("s:workbookPr", NS)
        epoch = datetime(1904, 1, 1) if props is not None and props.attrib.get("date1904") in ("1", "true") else datetime(1899, 12, 30)
        for row in result:
            row["Date"] = (epoch + timedelta(days=int(row["Date"]))).strftime("%Y-%m-%d")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    out = args.output_dir
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    source = Path(summary["source"])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    rows = source_rows(source)
    by_id = {r["TradeId"]: r for r in rows if r["OpenClock"] <= "09:40:00"}
    with (out / "atas_trades.csv").open(encoding="utf-8", newline="") as stream:
        groups = list(csv.DictReader(stream, delimiter=";"))
    all_ids, checks = [], Counter()
    decimal_fields = {1: "Qty", 3: "OpenPrice", 5: "ClosePrice", 6: "NetPnL", 7: "Commission"}
    for group in groups:
        fills = []
        for packed in group["fills"].split("|"):
            values = packed.split(",")
            assert len(values) == 8, (group["n"], "packed_length")
            row = by_id[values[0]]
            assert values[2] == row["OpenClock"]
            assert values[4] == row["CloseClock"]
            for index, field in decimal_fields.items():
                assert Decimal(values[index]) == Decimal(row[field]), (group["n"], values[0], field)
            fills.append(row)
            all_ids.append(values[0])
            checks["exact_execution_rows"] += 1
        qty = sum(int(r["Qty"]) for r in fills)
        net = sum(Decimal(r["NetPnL"]) for r in fills)
        gross = sum(Decimal(r["GrossPnL"]) for r in fills)
        entry = sum(Decimal(r["OpenPrice"]) * int(r["Qty"]) for r in fills) / qty
        exit_price = sum(Decimal(r["ClosePrice"]) * int(r["Qty"]) for r in fills) / qty
        assert Decimal(group["entry"]) == entry
        assert Decimal(group["exit"]) == exit_price
        assert Decimal(group["qty"]) == qty
        assert Decimal(group["net_usd"]) == net
        assert Decimal(group["gross_usd"]) == gross
        assert Decimal(group["net_ticks"]) == net / qty / Decimal(5)
        assert int(group["fill_count"]) == len(fills)
        assert group["result"] == ("WIN" if net > 0 else "LOSS" if net < 0 else "FLAT")
        assert group["modeled_commission_usd"] == ""
        assert group["net_r"] == ""
        assert group["mae"] == "" and group["mfe"] == ""
        entry_bar = datetime.strptime(group["entry_clock"], "%H:%M:%S").replace(second=0)
        assert group["entry_bar_start"] == entry_bar.strftime("%H:%M:%S")
        assert group["signal_close"] == entry_bar.strftime("%H:%M:%S")
        assert group["candle_start"] == (entry_bar - timedelta(minutes=1)).strftime("%H:%M:%S")
        assert group["signal_candle_source"] == "last_closed_proxy"
        if group["bracket_source"] == "unknown":
            assert not group["stop"] and not group["target"] and not group["risk_ticks"]
        else:
            assert group["bracket_source"] == "reconstructed_databento_last_closed_proxy"
            assert "SL_RECONSTRUIDO" in group["warn"]
            direction = Decimal(group["dir"])
            aligned = [p.split(":") for p in group["imb_rows"].split("|")]
            stop = min(Decimal(r[0]) for r in aligned) - Decimal("1.25") if direction > 0 else max(Decimal(r[1]) for r in aligned) + Decimal("1.25")
            assert Decimal(group["stop"]) == stop
            risk = direction * (entry - stop)
            assert risk > 0
            # Decimal arithmetic can differ below 1e-22 for repeating weighted means.
            assert abs(Decimal(group["target"]) - (entry + direction * risk)) < Decimal("1e-22")
            assert abs(Decimal(group["risk_ticks"]) - risk / Decimal("0.25")) < Decimal("1e-22")
            checks["structural_reconstructed_brackets"] += 1
        checks["weighted_entry_groups"] += 1
    assert len(all_ids) == len(set(all_ids))
    assert set(all_ids) == set(by_id), "Lost or duplicated source executions"
    assert len(groups) == summary["entry_second_groups"]["count"]
    assert sum(Decimal(g["net_usd"]) for g in groups) == Decimal(summary["entry_second_groups"]["pnl_usd"])
    with sqlite3.connect(f"file:{out / 'lucid_history.sqlite'}?mode=ro", uri=True) as db:
        assert db.execute("select count(*) from fills").fetchone()[0] == len(rows)
        assert db.execute("select count(*) from entry_groups").fetchone()[0] == len(groups)
        assert db.execute("select count(*) from sessions").fetchone()[0] == summary["sessions"]
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    assert before == after == summary["source_sha256"]
    comparison = json.loads((out / "prior_source_comparison.json").read_text(encoding="utf-8"))
    assert not comparison["changed_execution_fields"] and not comparison["new_trade_ids"]
    assert comparison["prior_snapshot_cutoffs_only"]["entry_le_09_40_00"]["same_trade_ids_as_current"]
    result = {"status": "PASS", "source_read_method": "Independent zipfile/ElementTree OOXML reader",
              "source_sha256": before, "source_unchanged": before == after,
              "checks": dict(checks), "source_fill_count": len(rows), "entry_groups": len(groups),
              "qty_contracts": sum(int(g["qty"]) for g in groups),
              "all_source_fills_exactly_once": True, "database_rows_match": True,
              "current_matches_prior_audit_cutoff": True,
              "limitation": "Checks fidelity to supplied account file and reconstruction formula; does not authenticate broker records or verify historical initial SL/TP."}
    (out / "audit_verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
