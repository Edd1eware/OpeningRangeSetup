"""Guard de procesos ATAS (OFT.Platform).

Mata instancias ATAS COMPLETAS huerfanas (aperturas/crashes previos que nunca
cerraron) que quedan sin ventana y siguen vivas consumiendo >~1GB. Esas instancias
cargan su propio Exporter/Strategy -> multiples statics separados peleando por
pending_strategy_signal.txt -> race/entradas fantasma en el replay (signal=PENDING
o trades sin contabilizar). Dejar UNA sola instancia arregla eso.

Reglas de seguridad (NUNCA mata la instancia que se va a usar):
  - Solo considera "pesadas" las > threshold_mb (default 900 MB). Los procesos hijo
    de ATAS (data/render, ~400-650 MB) quedan siempre fuera.
  - Si hay <=1 pesada, NO mata nada (esa es la instancia buena).
  - Con >1 pesada: conserva la KEEPER (la que tiene ventana; si ninguna tiene, la de
    mas memoria) y mata SOLO las demas pesadas SIN ventana. Nunca mata una con ventana.

Windows-only (usa PowerShell). En otros SO no hace nada.
"""

import json
import platform
import subprocess


def _list_atas():
    """Devuelve [{id, has_window, mem_mb}] de los procesos OFT.Platform via PowerShell."""
    ps = (
        "Get-Process OFT.Platform -ErrorAction SilentlyContinue | "
        "ForEach-Object { [pscustomobject]@{ id=$_.Id; "
        "has_window=($_.MainWindowHandle -ne 0); "
        "mem_mb=[math]::Round($_.WorkingSet64/1MB) } } | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        if not out:
            return []
        data = json.loads(out)
        return [data] if isinstance(data, dict) else data
    except Exception as exc:
        print(f"[atas_guard] no se pudo listar procesos: {exc}")
        return []


def cleanup_orphan_atas(threshold_mb=900, dry_run=False):
    """Mata instancias ATAS pesadas huerfanas. Devuelve lista de PIDs matados.

    dry_run=True solo reporta lo que haria (no mata)."""
    if platform.system() != "Windows":
        return []

    procs = _list_atas()
    if not procs:
        print("[atas_guard] no hay procesos OFT.Platform.")
        return []

    heavy = [p for p in procs if p["mem_mb"] >= threshold_mb]
    if len(heavy) <= 1:
        print(f"[atas_guard] {len(procs)} procesos, {len(heavy)} instancia(s) pesada(s). "
              "Nada que limpiar (1 instancia = OK).")
        return []

    # Keeper: prioriza la que tiene ventana; si ninguna, la de mas memoria.
    windowed = [p for p in heavy if p["has_window"]]
    if windowed:
        keeper = max(windowed, key=lambda p: p["mem_mb"])
    else:
        keeper = max(heavy, key=lambda p: p["mem_mb"])

    # Candidatas a matar: pesadas, SIN ventana, distintas de la keeper.
    targets = [p for p in heavy
               if p["id"] != keeper["id"] and not p["has_window"]]

    kw = " (CON ventana)" if keeper["has_window"] else " (sin ventana, mas memoria)"
    print(f"[atas_guard] {len(heavy)} instancias pesadas. Keeper=PID {keeper['id']} "
          f"({keeper['mem_mb']} MB){kw}. Huerfanas a matar: "
          f"{[p['id'] for p in targets] or 'ninguna'}.")

    killed = []
    for p in targets:
        if dry_run:
            print(f"[atas_guard] (dry-run) mataria PID {p['id']} ({p['mem_mb']} MB)")
            continue
        try:
            subprocess.run(["taskkill", "/PID", str(p["id"]), "/F"],
                           capture_output=True, text=True, timeout=15)
            killed.append(p["id"])
            print(f"[atas_guard] matado PID {p['id']} ({p['mem_mb']} MB, huerfana sin ventana).")
        except Exception as exc:
            print(f"[atas_guard] no se pudo matar PID {p['id']}: {exc}")
    return killed


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Limpia instancias ATAS huerfanas.")
    ap.add_argument("--dry-run", action="store_true", help="Solo reporta, no mata.")
    ap.add_argument("--threshold-mb", type=int, default=900,
                    help="MB minimos para considerar una instancia 'pesada' (default 900).")
    a = ap.parse_args()
    cleanup_orphan_atas(threshold_mb=a.threshold_mb, dry_run=a.dry_run)
