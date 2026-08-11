# Contexto de reinicio - ORB causal ATAS v21

Fecha local de trabajo: 2026-07-12 noche.

Ruta principal:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup`

Ruta de resultados ATAS:

`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score`

Ruta de corridas guardadas:

`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs`

## Principio obligatorio

No hacer overfit, no hacer look-ahead, no mentir, no maquillar resultados y no tratar un `OPEN` como si fuera `BE`.

El objetivo no es encontrar un PF bonito. El objetivo es producir resultados reproducibles en vivo, con features disponibles antes o al momento de entrada y salidas causales.

## Objetivo actual

1. Eliminar resultados finales `OPEN`.
2. Extender Replay hasta `10:30 NY`.
3. Si un trade no llega a TP/SL antes de `10:30`, cerrarlo como `EXIT` causal con el ultimo precio disponible y PnL con signo correcto.
4. Repetir Q2 2022.
5. Solo si Q2 2022 tiene potencial real para pasar Lucid 150k en maximo 6 meses, escalar a temporada DST 2025.
6. Solo si DST 2025 tambien sostiene edge, lanzar corrida larga desde `2022-04-04` hasta la ultima sesion operable disponible, excluyendo fines de semana, feriados de Estados Unidos y cierres CME.

## Criterio Lucid 150k

El usuario aclaro que la cuenta Lucid 150k debe pasarse en maximo 6 meses.

Antes de afirmar "pasa Lucid", hay que verificar reglas reales actuales de Lucid o usar el monitor local si ya codifica esas reglas correctamente. No afirmar pase sin simulacion:

- objetivo de profit,
- drawdown maximo,
- trailing/static drawdown segun regla aplicable,
- dias minimos/maximos si existen,
- ritmo de trades/mes,
- contratos usados,
- slippage/comisiones si se integran.

Gate minimo para escalar:

- cero `OPEN` finales,
- cero fechas con error,
- version esperada en todos los CSV,
- PF y expectancy positivos despues de incluir `EXIT`,
- DD compatible con Lucid 150k,
- simulacion de maximo 6 meses con frecuencia realista,
- resultado no dependiente de 1 o 2 trades aislados.

## Resultado valido mas reciente antes del cambio v21

Corrida Q2 2022 v20:

- Carpeta: `...\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1`
- Fechas: 61/61
- Version: `score-exporter-2026-07-12-v20-causal-terminal-results`
- TP: 15
- SL: 9
- OPEN: 28
- TIME_OVER: 9
- Trades cerrados TP/SL: 24
- WR sobre TP/SL: 62.50%
- PF sobre TP/SL: 2.03
- Net sobre TP/SL/OPEN=0: +311 ticks
- Expectancy sobre TP/SL: +12.96 ticks/trade cerrado

Advertencia critica:

Los 28 `OPEN` NO son BE reales. En CSV aparecen sin `ExitTime_NY`, sin `Exit_price`, sin MAE/MFE util. Por tanto Q2 v20 es prometedor pero NO aprobado para escalar.

## Cambios aplicados para v21

Archivos modificados:

- `ATASScoreTradeResultExporter.cs`
- `04_trade_manager_TP_SL_BE_EXIT_TIMEOVER.cs`
- `replay_sync_runner_common_after_sync.py`
- `04_run_replay_score_trade_results_dst_2025_2026_after_sync.py`
- workspace ATAS: `C:\Users\k_99_\AppData\Roaming\ATAS\Workspaces_v3\Eddieware_workspace.ws`

Version nueva del exporter:

`score-exporter-2026-07-12-v21-1030-forced-exit`

Cambios de intencion:

- `REPLAY_END_TIME = "10:30"`
- `DEFAULT_REPLAY_TO_TIME = "10:30"`
- `X10_TIMEOUT_SECONDS = 9 * 60`
- `SPEED_DEFAULT_SECONDS["X10"] = 390`
- `TimeOverTimeNy = 10:30:00`
- Si hay trade abierto al llegar a `TimeOverTimeNy`, intentar cerrar como `EXIT`.
- `EXIT` ahora calcula ticks con signo correcto:
  - BUY: `(exit - entry) / tick_size`
  - SELL: `(entry - exit) / tick_size`
- La estructura A+ se limito a `_signalEndNy` para no extender features de entrada hasta 10:30.

Workspace backup:

`C:\Users\k_99_\AppData\Roaming\ATAS\Workspaces_v3\Eddieware_workspace.ws.backup_timeover_1030_20260712_225408`

DLL v21 compilada y copiada a:

- `C:\Users\k_99_\AppData\Roaming\ATAS\Indicators\EddiewareOpeningRangeSetup.dll`
- `C:\Users\k_99_\AppData\Roaming\ATAS\Strategies\EddiewareOpeningRangeSetup.dll`

Build:

- `dotnet build .\EddiewareOpeningRangeSetup.csproj -c Release`
- Resultado: compilacion correcta con warnings existentes, 0 errores.

Python:

- `python -m py_compile .\replay_sync_runner_common_after_sync.py .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py`
- Resultado: OK.

## Smoke test v21 realizado

Comando ejecutado:

```powershell
python -u .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py --x10-only --from-date 2022-04-07 --to-date 2022-04-07 --section-label 2022-04-07-v21-smoke-1030 --reset-state --force
```

Telegram:

- Limpieza realizada antes del smoke: 67 mensajes borrados, 0 no borrables.

Resultado del smoke:

- Fecha: `2022-04-07`
- Version CSV: `score-exporter-2026-07-12-v21-1030-forced-exit`
- EntryTime_NY: `09:33:42`
- Side: `BUY`
- Entry_price: `14511.25`
- Result_Label: `OPEN`
- result TP SL BE: `0`
- ExitTime_NY: vacio
- Exit_price: vacio
- MAE_ticks: `0`
- MFE_ticks: `0`

Conclusion del smoke:

v21 todavia NO es valido. No lanzar Q2, 2025 ni corrida larga hasta corregir esto.

## Bug pendiente principal

El runner imprimio `Resultado terminal detectado` y guardo el CSV aunque el resultado era `OPEN`.

Esto no debe pasar. Un CSV con `Result_Label=OPEN` debe ser considerado no terminal siempre.

Siguiente correccion recomendada:

1. Endurecer `row_has_terminal_result()` en `replay_sync_runner_common_after_sync.py`:
   - si `Result_Label == "OPEN"`, retornar `False` sin mirar otros campos.
   - tratar cualquier valor cero (`0`, `+0`, `-0`, `0.0`, `0.00`, `+0.00`, `-0.00`) como no terminal salvo `Result_Label == "BE"` explicito.
   - exigir `ExitTime_NY` y `Exit_price` para `TP`, `SL`, `EXIT`, `BE`.
2. Investigar por que `ForceExitOpenTradeAtTimeOver()` no alcanzo a escribir `EXIT` en 2022-04-07.
   - Posible causa: el runner acepto el archivo `OPEN` demasiado pronto, antes de que Replay llegara a 10:30.
   - Al corregir terminal detection, Replay debe seguir hasta TP/SL/EXIT o timeout.
3. Si aun llega a 10:30 y no cambia a `EXIT`, revisar `TryWriteTimeOver()` y confirmar que el update de 10:30 entra con `nyTime.TimeOfDay >= TimeOverTimeNy`.
4. No contar `OPEN` como BE.

## Estado de ATAS

ATAS fue reiniciado, login realizado, workspace cargado.

Ventanas vistas despues del login:

- `ATAS - [Eddieware_workspace]`
- `Replay`
- `NQ 1m Chart`

Si el nuevo chat necesita reiniciar ATAS:

1. Cerrar proceso `OFT.Platform`.
2. Copiar DLL compilada a `Indicators` y `Strategies`.
3. Abrir `C:\ProgramData\Microsoft\Windows\Start Menu\Programs\ATAS Platform\ATAS Platform.lnk`.
4. Si aparece `Authorization`, hacer click en `Connect`.
5. Esperar workspace `Eddieware_workspace`.

## Comandos utiles

Validar una fecha que antes quedaba OPEN:

```powershell
python -u .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py --x10-only --from-date 2022-04-07 --to-date 2022-04-07 --section-label 2022-04-07-v21-smoke-1030 --reset-state --force
```

Cuando el smoke ya no produzca OPEN, correr Q2:

```powershell
python -u .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py --x10-only --from-date 2022-04-04 --to-date 2022-06-30 --section-label 2022-Q2-v21-1030-no-open --reset-state --force
```

Si Q2 pasa gate Lucid 150k max 6 meses, correr DST 2025:

```powershell
python -u .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py --x10-only --from-date 2025-03-10 --to-date 2025-11-03 --section-label 2025-DST-v21-1030-validation --reset-state --force
```

Notas:

- Confirmar fechas DST 2025 exactas con el calendario del runner antes de ejecutar.
- El runner ya excluye fines de semana y feriados/cierres configurados.
- Para corrida larga hasta "hoy", usar fecha final como ultima sesion operable disponible, no una sesion incompleta.

## Reglas de reporte

Siempre separar:

- sesiones esperadas,
- entradas,
- TP,
- SL,
- EXIT,
- BE real,
- TIME_OVER sin trade,
- fallas de UI/script,
- saltadas,
- OPEN, que debe ser 0.

WR principal:

- `wins / (TP + SL + EXIT + BE)` si `EXIT` tiene PnL real.
- Tambien reportar WR crudo contra entradas.

PF:

- usar todos los resultados con PnL real (`TP`, `SL`, `EXIT`, `BE=0`).
- No excluir `EXIT` si es salida causal.
- No contar `TIME_OVER` sin trade como trade.

Lucid:

- reportar si pasa o no pasa en maximo 6 meses.
- incluir tiempo estimado para objetivo, DD maximo y peor racha.
- no declarar "potencial" si el DD o la frecuencia no dan para 6 meses.

## Estado final antes de reiniciar chat

No lanzar corrida grande todavia.

Bloqueo actual:

`2022-04-07` v21 sigue saliendo `OPEN`.

Siguiente paso exacto:

Corregir terminal detection del runner para que no acepte `OPEN` y confirmar que Replay continua hasta `10:30`; luego volver a smoke test 2022-04-07. Solo si sale `TP`, `SL` o `EXIT` con `ExitTime_NY` y `Exit_price`, relanzar Q2.
