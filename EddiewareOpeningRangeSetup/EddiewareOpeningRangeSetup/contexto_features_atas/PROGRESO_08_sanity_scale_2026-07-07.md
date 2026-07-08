# Progreso 08 — sanity cerrado + DST 2025–2026 en curso (2026-07-07)

Continúa de `PROGRESO_07_handoff_2026-07-07.md`.

## Estado en una línea

Sanity ATAS **PASÓ** con fills virtuales causales, SL canónico, CSV rico y equity acumulada.
Recorrido completo DST 2025–2026 **EN CURSO**: 239 sesiones, PID Python `6632`.

## Fix definitivo del sanity

- Root cause del falso SL de 2025-03-18: `ManageVirtualTrade` descartaba toda la barra de fill y
  usaba High/Low acumulados. El TP canónico ocurre 3.27 s después del fill dentro de esa barra.
- `02_C_ATASExecutionManagerStrategy.cs` ahora procesa `Close` (precio actual) causalmente en cada
  update y no llena antes del `EntryBar` canónico de la señal.
- Resultado validado 2025-03-18: SELL 3, 19830.00 → 19827.50, +10t / +$150, TRAIL;
  `challenge_equity=150`, `killswitch_state` no-cero.
- `ResetChallengeState` quedó OFF (también default en fuente) para acumular entre reloads/fechas.
  Muestra acumulativa: equity `150 → 300 → 450` en 2025-03-18, 2026-03-27, 2026-04-01.

## Runner endurecido

- `--from-date` / `--to-date` para acotar años.
- La señal pre-escrita lee primero el score X10 congelado del ladder canónico.
- Para fechas operables, Replay solo termina cuando existen **ambos**: resultado terminal del
  exporter y fila rica de la strategy para esa fecha.
- Eliminado el fallback que fabricaba un CSV corto desde score-results y ocultaba una strategy
  detenida.
- Chart restaurado con `02_Visual_Logic`, `ATASScoreTradeResultExporter` y la strategy en Started.

## Recorrido activo

Comando:

```powershell
python -u 06_run_strategy_replay.py --all --from-date 2025-01-01 --to-date 2026-12-31
```

- 239 sesiones sincronizadas (2025-03-10 → 2026-06-23).
- Aproximadamente 140 cumplen el filtro de ejecución `range >= 140`.
- PID: `6632`.
- stdout: `strategy_dst_2025_2026_20260707_181335.log`.
- stderr: `strategy_dst_2025_2026_20260707_181335.err.log` (vacío al arrancar).
- Progreso/ETA también se envía por Telegram.

## Verificación al terminar

1. Proceso PID 6632 ya no existe y el log termina en `Recorrido terminado`.
2. `strategy_tester_results/strategy_tester_trades.csv` conserva header rico
   (`challenge_equity`, `challenge_dd`, etc.).
3. Revisar fechas con problemas del resumen final y re-correr solo esas.
4. Comparar contratos/tier/equity de la strategy. No exigir mismo exit que el score canónico:
   la strategy usa trailing y puede convertir un SL/TP canónico en otro resultado.

