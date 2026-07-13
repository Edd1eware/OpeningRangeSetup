# LOOKAHEAD FIX REPORT

## Veredicto

El resultado anterior queda invalidado como edge causal porque `Cvd_Pullback_Label` era un estado final/intratrade. El pipeline ahora separa inputs congelados de outcomes y el optimizador aborta si intenta usar columnas futuras.

## Donde estaba el bug

- `ATASScoreTradeResultExporter.cs:348`: nace el trade en `CreateTrade(...)`.
- `ATASScoreTradeResultExporter.cs:447`: el nuevo `TradeInputSnapshot` congela CVD/Delta/VWAP/OR/ranking al entry.
- `ATASScoreTradeResultExporter.cs:1005`: `UpdateCvdPullback(...)` actualiza CVD durante la vida del trade.
- `ATASScoreTradeResultExporter.cs:2482`: se escribe `trade_inputs.csv` sin reescribir features.
- `ATASScoreTradeResultExporter.cs:2676`: se escribe `trade_results.csv` con outcomes y estados finales.

## Correccion aplicada

- `Cvd_Label_AtEntry` se congela en `Excelente` al crear el trade, igual que el estado real disponible en ese instante.
- `Cvd_Label_Final` queda en `trade_results.csv` y no puede entrar al optimizador.
- MFE, MAE, exit, profit, resultado, alarmas dinamicas y campos `*_Final` se tratan como outcome o variables dinamicas.
- `edge_optimization_fast.py` ya solo carga `trade_inputs.csv` + `trade_results.csv` y pasa por `audit_feature_columns()`.

## Comparacion antes/despues

| case | trades | months | trades_per_month | wr | pf | expectancy | profit | dd | max_w_streak | max_l_streak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| before_leaky_final_CVD_Excelente_TP100_SL40 | 342 | 39 | 8.77 | 73.39 | 3.01 | 15.54 | 5316.00 | 120.00 | 25 | 4 |
| recomputed_legacy_final_CVD_Excelente_TP100_SL40 | 342 | 39 | 8.77 | 73.39 | 3.01 | 15.54 | 5316.00 | 120.00 | 25 | 4 |
| after_causal_Cvd_Label_AtEntry_Excelente_TP100_SL40 | 564 | 39 | 14.46 | 51.24 | 1.27 | 3.47 | 1955.00 | 435.00 | 6 | 9 |
| after_causal_all_entry_trades_TP100_SL40 | 564 | 39 | 14.46 | 51.24 | 1.27 | 3.47 | 1955.00 | 435.00 | 6 | 9 |

Caida estimada de PF al quitar el CVD final: 1.73

## Entregables generados

- Dataset causal: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\causal_dataset_20260711_234544`
- Inputs: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\causal_dataset_20260711_234544\trade_inputs.csv` (564 trades)
- Results: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\causal_dataset_20260711_234544\trade_results.csv` (564 trades)
- Comparacion: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\causal_dataset_20260711_234544\causal_backtest_comparison.csv`
- Variables sospechosas: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\SuspectedLeakageVariables.csv` (2721 filas)
- Ciclo de vida: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\feature_lifecycle.csv`

## Riesgo restante

La reconstruccion usa CSV legacy para separar columnas, pero la prueba definitiva debe venir de una corrida nueva de ATAS con el DLL actualizado escribiendo `trade_inputs.csv` y `trade_results.csv` nativos. No se optimizo nada despues de ver el resultado corregido.