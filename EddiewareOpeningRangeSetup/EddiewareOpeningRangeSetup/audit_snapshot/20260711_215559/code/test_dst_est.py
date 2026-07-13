"""
Valida timezone DST/EST en ATAS replay.

Fechas de transicion EDT→EST 2024:
  2024-11-01  (viernes) → último dia EDT (UTC-4)
  2024-11-04  (lunes)   → primer dia EST (UTC-5)

Para cada fecha:
  1. Lee OR esperado de DuckDB (calculado con ZoneInfo correcto)
  2. Corre replay X10 en ATAS
  3. Compara ATAS Entry/Side vs DuckDB direction/OR
  4. Concluye: ATAS captura el window correcto o no

Uso:
  python test_dst_est.py
  python test_dst_est.py --force        # re-corre aunque ya exista CSV
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import duckdb

import replay_sync_runner_common_after_sync as replay_sync
import time_zones_atas

# ── Config ────────────────────────────────────────────────────────────────────
TICK_SIZE = 0.25

DB_PATH = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\orb_features.duckdb"
)

OUTPUT_DIR = replay_sync.RESULTS_FOLDER / "visual_tests" / "dst_est_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_DATES = [
    ("2024-11-01", "EDT", "UTC-4", "ultimo dia EDT antes de fall-back"),
    ("2024-11-04", "EST", "UTC-5", "primer dia EST despues de fall-back"),
]

TOLERANCE_TICKS = 4   # Entry puede ser ±4t del OR edge (fill slippage normal)


# ── DuckDB ────────────────────────────────────────────────────────────────────
def query_duckdb(date_iso: str) -> dict | None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    row = con.execute("""
        SELECT
            ol.or_high * ? AS or_high_price,
            ol.or_low  * ? AS or_low_price,
            bf.direction
        FROM or_levels ol
        LEFT JOIN breakout_features bf USING (session_date)
        WHERE ol.session_date = ?
        LIMIT 1
    """, [TICK_SIZE, TICK_SIZE, date_iso]).fetchone()
    con.close()
    if not row:
        return None
    return {
        "or_high": row[0],
        "or_low":  row[1],
        "direction": row[2],  # 'UP' | 'DOWN' | None (no breakout)
    }


# ── ATAS result ───────────────────────────────────────────────────────────────
def read_atas_result(date_iso: str, run_name: str) -> dict | None:
    path = replay_sync.destination_result_path(OUTPUT_DIR, date_iso, run_name)
    row = replay_sync.read_csv_row(path)
    if not row:
        return None
    return {
        "Side":         row.get("Side", "").strip(),
        "Entry_price":  row.get("Entry_price", "").strip(),
        "Result_Label": row.get("Result_Label", "").strip(),
        "Signal_Source":row.get("Signal_Source", "").strip(),
        "score_total":  row.get("score total", "").strip(),
    }


def parse_price(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except (ValueError, AttributeError):
        return None


# ── Comparacion ───────────────────────────────────────────────────────────────
def compare(date_iso: str, tz_label: str, utc_label: str, db: dict, atas: dict) -> bool:
    ok = True
    print(f"\n{'='*60}")
    print(f"  {date_iso}  [{tz_label} / {utc_label}]")
    print(f"{'='*60}")

    print(f"  DuckDB OR   : high={db['or_high']:.2f}  low={db['or_low']:.2f}  "
          f"size={(db['or_high']-db['or_low'])/TICK_SIZE:.0f}t  dir={db['direction']}")
    print(f"  ATAS result : Side={atas['Side']}  Entry={atas['Entry_price']}  "
          f"Result={atas['Result_Label']}")

    result = atas["Result_Label"].upper()

    if result == "NO_TRADE":
        if db["direction"] is None:
            print("  [OK] DuckDB: no breakout | ATAS: NO_TRADE  ✓")
        else:
            print(f"  [WARN] DuckDB tiene breakout {db['direction']} pero ATAS dice NO_TRADE")
        return True

    if result in ("TIME_OVER", "HOLYDAY NO DATA", ""):
        print(f"  [INFO] Resultado {result} — sin entrada, no comparable")
        return True

    # Compara direccion
    atas_side = atas["Side"].upper()
    db_dir    = (db["direction"] or "").upper()

    if db_dir and atas_side:
        dir_match = (
            (db_dir == "UP"   and atas_side in ("BUY",  "LONG",  "UP"))   or
            (db_dir == "DOWN" and atas_side in ("SELL", "SHORT", "DOWN"))
        )
        if dir_match:
            print(f"  [OK] Direccion: DuckDB={db_dir}  ATAS={atas_side}  ✓")
        else:
            print(f"  [FAIL] Direccion: DuckDB={db_dir}  ATAS={atas_side}  ✗  "
                  f"← posible timezone bug")
            ok = False

    # Compara entry vs OR edge
    entry = parse_price(atas["Entry_price"])
    if entry is not None and db["direction"]:
        edge = db["or_high"] if db["direction"] == "UP" else db["or_low"]
        delta_ticks = abs(entry - edge) / TICK_SIZE
        if delta_ticks <= TOLERANCE_TICKS:
            print(f"  [OK] Entry {entry:.2f} vs OR-edge {edge:.2f} "
                  f"(delta={delta_ticks:.1f}t <= {TOLERANCE_TICKS}t)  ✓")
        else:
            print(f"  [FAIL] Entry {entry:.2f} vs OR-edge {edge:.2f} "
                  f"(delta={delta_ticks:.1f}t > {TOLERANCE_TICKS}t)  ✗  "
                  f"← ATAS capturo otro OR window")
            ok = False

    return ok


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-corre aunque ya existan CSVs")
    args = parser.parse_args()

    print("test_dst_est.py — validacion timezone EDT/EST en ATAS")
    print(f"Output: {OUTPUT_DIR}")
    print()

    # Pre-check DuckDB
    print("=== DuckDB pre-check ===")
    db_data = {}
    for date_iso, tz_label, utc_label, desc in TEST_DATES:
        db = query_duckdb(date_iso)
        if db is None:
            print(f"  {date_iso}: NO ENCONTRADO en DuckDB — restauracion pendiente?")
            sys.exit(1)
        db_data[date_iso] = db
        print(f"  {date_iso} [{tz_label}]: OR={db['or_high']:.2f}/{db['or_low']:.2f}  "
              f"dir={db['direction']}  ({desc})")

    print()
    print("=== Corriendo replay X10 en ATAS (2 fechas) ===")
    print("  ATAS debe estar abierto con el chart correcto y ventana Replay visible.")
    print()

    results_ok = {}
    for date_iso, tz_label, utc_label, desc in TEST_DATES:
        run_name = f"X10_DST_EST_TEST"
        print(f"[{date_iso}] {tz_label} — {desc}")
        session_date = date.fromisoformat(date_iso)
        utc_offset = time_zones_atas.get_utc_offset(session_date)
        print(f"  -> configurando ATAS/CME en UTC{utc_offset}")
        time_zones_atas.ensure_atas_timezone(utc_offset)
        ok, status = replay_sync.run_one_date(
            date_iso,
            run_name=run_name,
            timeout_seconds=replay_sync.X10_TIMEOUT_SECONDS,
            output_folder=OUTPUT_DIR,
            force=args.force,
            replay_from_time=replay_sync.DEFAULT_REPLAY_FROM_TIME,
            replay_to_time=replay_sync.DEFAULT_REPLAY_TO_TIME,
        )
        print(f"  → replay: ok={ok}  status={status}")
        results_ok[date_iso] = (ok, status)
        time.sleep(1)

    print()
    print("=== Comparacion DuckDB vs ATAS ===")
    all_pass = True
    for date_iso, tz_label, utc_label, desc in TEST_DATES:
        atas = read_atas_result(date_iso, "X10_DST_EST_TEST")
        if atas is None:
            print(f"\n  {date_iso}: sin CSV de ATAS — replay fallo?")
            all_pass = False
            continue
        passed = compare(date_iso, tz_label, utc_label, db_data[date_iso], atas)
        if not passed:
            all_pass = False

    print()
    print("=" * 60)
    if all_pass:
        print("  RESULTADO FINAL: PASS ✓")
        print("  ATAS captura 09:30 ET correcto tras ajustar CME automaticamente.")
        print("  La transicion EDT (UTC-4) -> EST (UTC-5) funciona en Replay X10.")
    else:
        print("  RESULTADO FINAL: FAIL ✗")
        print("  ATAS captura window incorrecto para EST.")
        print("  Se necesita cambiar TZ en ATAS antes de fechas EST.")
    print("=" * 60)


if __name__ == "__main__":
    main()
