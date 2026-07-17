"""Lanza el runner v23 X10 usando la adquisición UI por HANDLE ya existente.

No modifica fechas, velocidad, Play/Stop, timeouts, sincronización ni validación
de resultados. Solo evita la enumeración global de UI Automation que puede
bloquearse después de reiniciar ATAS.
"""

import importlib


def main():
    runner = importlib.import_module(
        "04_run_replay_score_trade_results_dst_2025_2026_after_sync"
    )
    handle_controls = importlib.import_module(
        "04_run_replay_featsweep_after_sync"
    )._get_replay_controls_by_handle
    runner.replay_sync.get_replay_controls = handle_controls
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
