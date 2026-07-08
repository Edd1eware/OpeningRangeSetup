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

## Iteración 07-jul tarde — balance reset + progreso/ETA global a Telegram

### Balance Telegram reseteado a 150k
- `telegram_balance.json` (en `data_footprint_generator\trade_results_score\`) vaciado a `{}`.
  Backup: `telegram_balance_backup_20260707_185734.json`.
- El balance = `TelegramStartingBalance (150000)` + suma de PnL por fecha
  (`ATASScoreTradeResultExporter.cs:187` y `:2663`). Con `{}` el próximo mensaje muestra $150,000.
- El JSON es idempotente por fecha (X1/X10/re-runs sobrescriben su día); el recorrido lo
  repuebla solo con las fechas que replaye.
- Estado kill-switch (`challenge_equity.txt`, `killswitch_state.txt`) NO se tocó aquí: el runner
  ya los borra por defecto en cada lanzamiento (cuenta limpia). Para balance 100% limpio: relanzar.

### Progreso + ETA GLOBAL al Telegram (código, aplica al PRÓXIMO lanzamiento)
Problema: `run_replay_period` corre UNA fecha por llamada, así que su ETA por-etapa siempre daba
`remaining=0 / ETA N/A`. El progreso real del recorrido de 239 fechas no se veía.

- `telegram_run_summary_after_sync.py`: nuevo `send_overall_progress(...)` + `_format_elapsed(...)`.
  Manda barra de 10 bloques, `%`, `(done/total)`, `Balance $ / PnL`, `W-L / WR`,
  `Transcurrido | Restante` (ETA = transcurrido/hechas × restantes).
- `06_run_strategy_replay.py`: en el loop, tras cada fecha, calcula elapsed/ETA y llama
  `send_overall_progress`. `_print_date_summary` ahora retorna `(wins, losses, total_pnl, contracts)`.
- Se quitó `progress_meta` de la llamada a `run_replay_period` (ya no manda el mensaje parcial
  engañoso). La alerta de N fechas-fallidas-seguidas se re-implementó en el runner
  (`REPLAY_FAIL_ALERT_STREAK`, default 3).
- Ambos archivos `py_compile` OK. El PID 6632 en curso usa el código VIEJO en memoria; los
  cambios aplican al próximo `python -u 06_run_strategy_replay.py ...`.

## Fase actual — VALIDACIÓN de ejecución, NO descubrimiento de edge

El recorrido con el Execution Manager **valida la ejecución del edge congelado**, no busca edge
nuevo. El edge (OR CatBoost / A+ Speed, F7 PASA) ya está congelado; esta corrida prueba, sobre
Replay DST 2025–2026:
- fills virtuales causales, SL/trailing canónico,
- kill-switch graduado (base 3c) + Risk Governor (MaxDD $4,500),
- acumulación de equity/DD entre fechas.

`OnlyAPlusSpeed` está TEMP en OFF (toma las 174 señales canónicas del modelo) para estresar el
kill-switch; revertir a ON antes de producción (el edge vivo es solo A+ Speed).
Gate pendiente: 2 meses forward EV>0 / PF>1.15 sobre v1 antes de fondear.

## Pista nueva (paralela, NO estorba el recorrido) — LVN del Volume Profile previo

La infra YA existe (ver `PROGRESO_04`, DLL 19:06): el **Feature Scanner** emite
`distance_to_{PREOPEN_15m|PREOPEN_30m|PREOPEN_60m|ON|PD}_LVN_ticks` (+ HVN, POC/VAH/VAL,
`profile_confluence_count`), todos CONGELADOS a 09:29:59 (sin lookahead). Probe de datos PASÓ:
100% de barras pre-open/overnight/RTH traen footprint Levels → VP real en C#.

Falta para probar la hipótesis "precio cerca de un LVN previo predice follow-through del breakout":
1. Correr featsweep DST completo: `python -u 04_run_replay_featsweep_after_sync.py --force`
   (sin `--limit`) → dataset con las columnas LVN.
2. Meter `distance_to_*_LVN_ticks` en el embudo de descubrimiento (era-blind, matar barato, n chico)
   junto al resto de features causales. Recorder/BookRecorder solo si se quiere LVN intradía del libro.
Track de descubrimiento aparte del recorrido de validación (PID 6632) — no interfieren.

