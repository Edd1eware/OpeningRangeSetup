"""Corre UNA sola fecha del ladder exclusivamente en Historia X10.

Util para probar rapido una fecha que fallo sin re-correr toda la etapa.
Requiere ATAS con Replay al frente.

Uso:
    python run_single_date.py 2024-03-11
    python run_single_date.py 2024-03-11 06_dst_6m_20240311_20240501

IMPORTANTE: NO correr esto mientras el ladder principal este vivo (dos procesos
controlando ATAS = corrupcion). Detener el ladder con Ctrl+C primero.
"""

import sys
from pathlib import Path

import replay_sync_runner_common_after_sync as replay_sync


RUN_ID = "sync_v11_ladder_001_resume"
LADDER_ROOT = (
    replay_sync.RESULTS_FOLDER / "visual_tests" / "sync_ladder_runs" / RUN_ID
)


def main():
    if len(sys.argv) < 2:
        print("Uso: python run_single_date.py <YYYY-MM-DD> [stage_key]")
        return 2

    date_iso = sys.argv[1]
    stage_key = sys.argv[2] if len(sys.argv) > 2 else "06_dst_6m_20240311_20240501"
    output_folder = LADDER_ROOT / stage_key

    if not output_folder.exists():
        print(f"No existe la carpeta de etapa: {output_folder}")
        return 2

    run_plan = replay_sync.build_run_plan(quick=True)  # X10_R1 únicamente
    print(f"Corriendo SOLO {date_iso} en {stage_key}")
    print("Run plan:", [name for name, _, _ in run_plan])

    passed, failures = replay_sync.run_replay_period(
        [date_iso],
        output_folder=output_folder,
        run_plan=run_plan,
        report_prefix=f"single_{date_iso}",
        replay_to_time=replay_sync.DEFAULT_REPLAY_TO_TIME,
    )

    print("\n==============================")
    print("RESULTADO:", "PASS X10" if passed else "FAIL")
    if failures:
        for d, run, reason in failures:
            print(f"  fallo: {d} {run} -> {reason}")
    print("==============================")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
