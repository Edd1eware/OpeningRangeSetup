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

## OBJETIVO DE LA CORRIDA — validar la EJECUCIÓN en ATAS, NO el edge

El edge ya se midió (Python, PROGRESO_05: PF 1.67 / WR 63.7% / 14.4 tr-mes en 2025;
2026 bandera amarilla PF 1.10, n=9). Lo NO probado es que el port a C# reproduzca esa
contabilidad fecha tras fecha en Replay. Eso valida esta corrida:

| # | Qué valida | Criterio de éxito |
|---|---|---|
| 1 | **Fills virtuales causales** | Strategy entra en el EntryBar canónico, aplica SL 50 / trailing, sin lookahead. Exits pueden diferir del canónico (trailing), pero coherentes |
| 2 | **Kill-switch graduado (port C#)** | Tiers/contratos por trade = mismos que el sim Python (`analysis_vp/kill_switch_sim.py`) sobre la misma secuencia de 174 señales (sim: +$19,780, 1.9% quema) |
| 3 | **Risk Governor** | Nunca sizing que rompa MaxDD $4,500 (Lucid 150k); headroom=0 → skip + freeze |
| 4 | **Equity/DD acumulado** | `challenge_equity` continuo entre las 239 fechas: sin resets fantasma, sin dobles conteos |
| 5 | **Infra a escala** | 239 fechas sin trades fantasma, sin CSV falsos, sin strategy detenida silenciosa |

Salida esperada: `strategy_tester_trades.csv` rico (fecha, contratos, ticks, pnl_usd,
exit_motivo, challenge_equity, challenge_dd) para cruzar contra el sim Python trade por trade.

**Qué NO es esta corrida:** no mide WR/PF del edge (ya medido), no descubre nada nuevo,
no es forward. `OnlyAPlusSpeed=OFF` TEMP a propósito: las 174 señales canónicas estresan
el kill-switch; el subset A+ Speed es lo que se operaría en vivo. REVERTIR flags TEMP
antes de producción.

**Si pasa** → revertir flags TEMP → gate forward 2 meses (EV>0 / PF>1.15) → fondeo.
**Si el C# no cuadra con el sim** → bug de port; corregir antes de tocar dinero real.

### Bloqueador detectado 07-jul tarde (corrida manual del usuario)
- Mensaje de trade salió `6c (nominal)` = el Execution Manager NO ejecutó (bus sin
  contratos reales); `signal=CONSUMED` con `trades=0` en el log rico. La prueba NO vale
  corriendo así. **Verificar strategy Started en ATAS antes de relanzar** (síntoma igual
  a PROGRESO_05 §3b; probable strategy Stopped tras los kills/relanzamientos).
- Traceback en terminal tras 2025-03-11: incompleto, pendiente el paste completo.

### Higiene agregada al runner (07-jul tarde, aplica al próximo lanzamiento)
Al arrancar (UNA sola vez, antes de la fecha 1; se salta con `--keep-state`):
1. Borra `telegram_balance.json` → balance arranca en $150,000 exactos (sin basura de
   corridas muertas — hoy un `-1800` viejo de 03-11 hizo que un TP de +$1,800 mostrara
   $150,000 plano).
2. `clear_telegram_before_run` → borra TODO el historial del bot en el chat (los >48h
   la Bot API no los puede borrar; se reportan y la corrida continúa).
DENTRO del recorrido nada se resetea: el JSON acumula fecha a fecha (cada fecha
sobrescribe solo su propia entrada = idempotente) y el balance sube/baja como cuenta real.
También: barra de progreso global en consola (10 bloques + % + min restantes) además
del mensaje Telegram por fecha.

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

