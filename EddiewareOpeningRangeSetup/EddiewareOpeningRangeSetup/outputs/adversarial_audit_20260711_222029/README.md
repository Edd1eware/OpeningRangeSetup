# Auditoria adversarial de robustez - Opening Range Setup

Generado: 2026-07-11 22:31:36

Dataset: `C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1`



## Veredicto corto

El resultado reportado `cvd=Excelente | TP=100 SL=40` NO queda aceptado como edge causal en esta auditoria.

La razon principal es que `Cvd_Pullback_Label` se exporta como estado dinamico del trade y el optimizador lo lee del CSV final. En codigo, el trade nace con CVD `Excelente`, pero el archivo final contiene el estado al cierre/rewrite posterior. Por tanto, filtrar por CVD final `Excelente` es look-ahead/leakage si se usa como condicion de entrada.



## Resultados clave

| case | trades | months | trades_per_month | wr | pf | expectancy | profit | dd | max_w_streak | max_l_streak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| raw_actual_all_trades | 564.00 | 39.00 | 14.46 | 52.84 | 1.20 | 2.89 | 1629.00 | 674.00 | 6.00 | 9.00 |
| no_cvd_filter_TP100_SL40 | 564.00 | 39.00 | 14.46 | 51.24 | 1.27 | 3.47 | 1955.00 | 435.00 | 6.00 | 9.00 |
| current_reported_final_CVD_Excelente_TP100_SL40 | 342.00 | 39.00 | 8.77 | 73.39 | 3.01 | 15.54 | 5316.00 | 120.00 | 25.00 | 4.00 |
| excluded_non_Excelente_TP100_SL40 | 222.00 | 37.00 | 6.00 | 17.12 | 0.26 | -15.14 | -3361.00 | 3361.00 | 3.00 | 24.00 |



## Alertas duras

- 185 trades filtrados como CVD final Excelente tuvieron peor estado CVD no Excelente durante el trade.
- 121 trades filtrados como CVD final Excelente dispararon alarma dinamica intratrade.
- 250 de 342 trades del candidato ganan menos de +100 ticks; TP100 no es un target limpio 2.5:1.
- Faltan CSVs para fechas planeadas: 2024-05-16.



## Integridad

- CSVs encontrados: 730

- Fechas planeadas en log: 731

- Trades ejecutados: 564

- TIME_OVER: 166

- Fechas faltantes planeadas: 2024-05-16

- Fechas duplicadas: ninguna



## Evidencia de leakage CVD

Referencias de codigo:

- `ATASScoreTradeResultExporter.cs`: `CvdPullbackLabel = "Excelente"` al crear el trade.

- `ATASScoreTradeResultExporter.cs`: `UpdateCvdPullback(...)` corre durante la vida del trade antes de reescribir el CSV.

- `edge_optimization_fast.py`: el optimizador filtra con `row.get("Cvd_Pullback_Label")` del CSV final.



| Cvd_Pullback_Label | trades | wr | pf | expectancy | profit | dd |
| --- | --- | --- | --- | --- | --- | --- |
| Excelente | 342.00 | 73.39 | 3.01 | 15.54 | 5316.00 | 120.00 |
| Riesgo de reversion | 179.00 | 13.41 | 0.19 | -17.61 | -3153.00 | 3163.00 |
| Normal | 22.00 | 31.82 | 0.75 | -3.86 | -85.00 | 121.00 |
| Advertencia | 21.00 | 33.33 | 0.62 | -5.86 | -123.00 | 183.00 |



Comparacion directa:

- PF con filtro CVD final Excelente: 3.01

- PF sin usar CVD final: 1.27

- Caida de PF al quitar la variable sospechosa: 1.73



## Ambiguedad del target TP100/SL40

| result_bucket | count | mean | sum |
| --- | --- | --- | --- |
| +100 target | 1.00 | 100.00 | 100.00 |
| -40 stop | 41.00 | -40.00 | -1640.00 |
| negative before -40 | 49.00 | -20.63 | -1011.00 |
| positive before +100 | 250.00 | 31.47 | 7867.00 |
| zero | 1.00 | 0.00 | 0.00 |



- Trades con TP y SL teoricamente alcanzables en la misma simulacion MFE/MAE: 0 seleccionados, 0 en todos los trades.

- Trades seleccionados con flag `TP_And_SL_Hit_Same_Update`: 0.

- TP exportado promedio seleccionado: 33.37 ticks; SL exportado promedio seleccionado: 35.13 ticks.



## Robustez temporal del candidato sospechoso

| year | trades | wr | pf | expectancy | profit | dd | max_w_streak | max_l_streak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022.00 | 99.00 | 63.64 | 2.00 | 10.62 | 1051.00 | 120.00 | 7.00 | 4.00 |
| 2023.00 | 67.00 | 79.10 | 3.37 | 14.93 | 1000.00 | 120.00 | 24.00 | 4.00 |
| 2024.00 | 71.00 | 74.65 | 3.16 | 15.45 | 1097.00 | 104.00 | 7.00 | 2.00 |
| 2025.00 | 68.00 | 77.94 | 4.10 | 19.46 | 1323.00 | 80.00 | 14.00 | 2.00 |
| 2026.00 | 37.00 | 78.38 | 4.51 | 22.84 | 845.00 | 81.00 | 7.00 | 2.00 |



## Ranking y sizing

El sizing solicitado tambien queda bajo reserva: los cortes se calculan con toda la muestra. Ademas, por discretizacion del score, la regla top10/bottom30 casi no deja zona media.

| rule | high_cut | low_cut | avg_contracts | c1 | c3 | c4 | trades | wr | pf | expectancy | profit | dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_sample_top10_bottom30 | 9.00 | 8.00 | 1.34 | 303.00 | 0.00 | 39.00 | 342.00 | 73.39 | 2.63 | 97.98 | 33510.00 | 1895.00 |
| train_2022_2024_cutoffs_on_train | 9.00 | 8.00 | 1.39 | 206.00 | 0.00 | 31.00 | 237.00 | 71.31 | 2.07 | 77.93 | 18470.00 | 1895.00 |
| train_2022_2024_cutoffs_on_2025_2026 | 9.00 | 8.00 | 1.23 | 97.00 | 0.00 | 8.00 | 105.00 | 78.10 | 5.50 | 143.24 | 15040.00 | 405.00 |
| expanding_walkforward_prior_year_cutoffs |  |  |  |  |  |  | 243.00 | 77.37 | 3.40 | 118.74 | 28855.00 | 1600.00 |



## Calidad del ranking score

| bucket | cutoff | trades | wr | pf | expectancy | profit | dd |
| --- | --- | --- | --- | --- | --- | --- | --- |
| top_10pct | 9.00 | 39.00 | 61.54 | 1.95 | 11.85 | 462.00 | 130.00 |
| top_20pct | 8.00 | 263.00 | 73.00 | 2.95 | 15.22 | 4003.00 | 120.00 |
| top_30pct | 8.00 | 263.00 | 73.00 | 2.95 | 15.22 | 4003.00 | 120.00 |
| top_40pct | 8.00 | 263.00 | 73.00 | 2.95 | 15.22 | 4003.00 | 120.00 |
| top_50pct | 8.00 | 263.00 | 73.00 | 2.95 | 15.22 | 4003.00 | 120.00 |
| bottom_50pct | 8.00 | 303.00 | 74.92 | 3.24 | 16.02 | 4854.00 | 100.00 |
| score=5 | 5.00 | 5.00 | 100.00 | inf | 28.20 | 141.00 | -20.00 |
| score=6 | 6.00 | 57.00 | 75.44 | 3.37 | 16.70 | 952.00 | 80.00 |
| score=7 | 7.00 | 17.00 | 64.71 | 2.10 | 12.94 | 220.00 | 80.00 |
| score=8 | 8.00 | 224.00 | 75.00 | 3.27 | 15.81 | 3541.00 | 100.00 |
| score=9 | 9.00 | 20.00 | 60.00 | 1.48 | 6.80 | 136.00 | 160.00 |
| score=10 | 10.00 | 18.00 | 61.11 | 2.45 | 16.44 | 296.00 | 44.00 |
| score=11 | 11.00 | 1.00 | 100.00 | inf | 30.00 | 30.00 | -30.00 |



## Riesgo de multiple testing / overfitting

- Mascaras unicas probadas: 65

- Mascaras con >=50 trades: 53

- Pares TP/SL por mascara: 80

- Candidatos aproximados en busqueda: 4305



Mejor candidato observado por la misma busqueda:

| filter | tp | sl | trades | wr | pf | expectancy | test_exp | robust_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cvd_Pullback_Label=Excelente | 100.00 | 40.00 | 342.00 | 73.39 | 3.01 | 15.54 | 20.65 | 483.85 |



Permutacion de outcomes contra features:

| permutations | p_best_pf_ge_observed | p_best_exp_ge_observed | p_best_score_ge_observed | perm_best_pf_p95 | perm_best_exp_p95 | perm_best_score_p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 300.00 | 0.00 | 0.00 | 0.00 | 1.99 | 9.30 | 77.47 |



## Archivos generados

- `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\adversarial_audit_20260711_222029\audit_summary.json`

- `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\adversarial_audit_20260711_222029\key_results.csv`

- `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\adversarial_audit_20260711_222029\cvd_label_audit.csv`

- `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\adversarial_audit_20260711_222029\leakage_and_target_examples.csv`

- `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\adversarial_audit_20260711_222029\permutation_best_candidates.csv`