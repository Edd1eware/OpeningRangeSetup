# OR_ABSORPTION_TEST_2026_V23 baseline

Snapshot inmutable de la corrida `score-exporter-2026-07-16-v23-liquidity-burst-entry` sobre las 89 sesiones operables entre 2026-03-09 y 2026-07-15.

## Identidad

- Código ejecutado: commit `5fc72154e719d2b2b4a9e536f35d3dda194e3aad` (`liquidity burst`).
- Rama de congelado: `codex/or-absorption-v23-baseline`.
- DLL SHA-256: `49022B2B565CF6A9D3F1F79DEB23765EC7EC5DFEABB533D7C10CD569B5F2CC75`.
- La DLL de `bin/Release`, ATAS `Indicators` y ATAS `Strategies` era idéntica al terminar.
- Workspace: `Eddieware_workspace`; su hash y los paths exactos están en `environment_hashes.csv`.
- Parámetros serializados del exporter, Liquidity Burst y visual: `indicator_parameters.json`.

La ejecución original arrancó antes de la prohibición definitiva de X1 y su primer log conserva seis fechas históricas de sincronía X1/X10. La continuación que completó la baseline se ejecutó con `--x10-only`; el conjunto operativo congelado, las métricas y los 89 terminales provienen exclusivamente de `raw/X10_R1`. No había ningún proceso X1 activo al congelar. Las ramas posteriores deben deshabilitar X1 en el pipeline.

## Conciliación final

- Estado: completada correctamente.
- Fechas esperadas/terminales: 89/89.
- Pendientes/fallidas: 0/0.
- Trades: 53 (30 wins, 23 losses, 0 BE).
- WR: 56.6038%.
- PF: 1.266535.
- Expectancy: +5.09434 ticks/trade.
- Average win: +42.7667 ticks.
- Average loss: -44.0435 ticks.
- Neto: +270 ticks / +$8,100 con 6 contratos y $5/tick.
- Cuenta simulada: $150,000 -> $158,100.
- MAE promedio/máximo: 20.9434/60 ticks.
- MFE promedio/máximo: 28.2075/60 ticks.
- Lucid 150k: `NO PASS`; sin breach y sin DLL hit. Faltaron $900 para el objetivo de $9,000.
- Balance persistido: 89 fechas, +$8,100; coincide exactamente con `270 * $5 * 6`.
- Telegram: el log confirma `Telegram resumen enviado` después del reporte diario completo y antes de la salida limpia del runner.

## Resultados mensuales

| Mes | Trades | WR | PF | Neto ticks |
|---|---:|---:|---:|---:|
| 2026-03 | 8 | 87.50% | 14.76 | +289 |
| 2026-04 | 10 | 40.00% | 0.46 | -131 |
| 2026-05 | 17 | 58.82% | 1.16 | +53 |
| 2026-06 | 15 | 46.67% | 1.00 | -1 |
| 2026-07 | 3 | 66.67% | 2.00 | +60 |

## RR inicial

Los 53 trades cumplieron `initial TP >= initial SL`; todos nacieron exactamente 1:1.

| SL/TP inicial | Trades |
|---|---:|
| 20/20 | 14 |
| 21/21 | 3 |
| 26/26 | 1 |
| 46/46 | 1 |
| 51/51 | 1 |
| 60/60 | 33 |

Los 14 trades cuya fuente fue `LIQUIDITY BURST ABSORTION` nacieron 60/60.

## Reducción dinámica por CVD

Hubo siete reducciones de target 60 -> 30 por `CVD_RISK_BRACKET_50_PERCENT`, todas después de abrir con RR 1.00. No hubo movimientos de stop.

| Fecha | Fuente | Salida | Realizado | MAE | MFE |
|---|---|---|---:|---:|---:|
| 2026-03-27 | BREAKOUT | TP dinámico CVD | +30 | 0 | 40 |
| 2026-04-06 | BREAKOUT | TP dinámico CVD | +30 | 0 | 35 |
| 2026-04-14 | BREAKOUT | TP dinámico CVD | +30 | 0 | 35 |
| 2026-04-20 | BREAKOUT | TP dinámico CVD | +30 | 0 | 55 |
| 2026-06-11 | BREAKOUT | TP dinámico CVD | +30 | 30 | 35 |
| 2026-06-17 | BREAKOUT | SL inicial | -60 | 60 | 0 |
| 2026-07-08 | LIQUIDITY BURST ABSORTION | SL inicial | -60 | 60 | 20 |

El archivo `cvd_target_reduction_events.csv` contiene el detalle completo. `trades_reconstructed.csv` conserva para cada trade el plan inicial, bracket final, salida, MAE/MFE y flags de gestión solicitados.

## Causa de `TP 30 / SL 60`

No fue un trade abierto con RR 0.5. El exporter escribió en el CSV final el target mutable ya reducido; `telegram_run_summary_after_sync.py::compute_run_stats()` tomó ese `TP_ticks` final y `_format_stats_line()` lo presentó como si fuera el plan original. La corrección posterior debe separar plan inicial, target dinámico y salida realizada sin cambiar `Result_Label`, entradas, precios, tiempos ni PnL de esta baseline.

## Inventario

- `raw/X10_R1/`: 89 CSV terminales y 53 timelines dinámicos.
- `raw/state/`: inputs, resultados, balance y trazas persistidas.
- `logs/`: log original, continuación X10-only, stderr vacíos y estado del runner.
- `artifacts/`: DLL ejecutada y workbook generado.
- `daily_terminal_results.csv`: conciliación de las 89 fechas.
- `trades_reconstructed.csv`: reconstrucción de los 53 trades.
- `cvd_target_reduction_events.csv`: los siete cambios de target.
- `indicator_parameters.json`: configuración serializada de ATAS usada.
- `environment_hashes.csv`: hashes de código, workspace y DLL.
- `SHA256SUMS.txt`: hashes de todos los archivos del snapshot.

No contiene credenciales de Telegram. No se modificó Liquidity Burst, CVD, entradas, filtros, trailing, break-even, time exit ni la lógica del replay para producir este snapshot.
