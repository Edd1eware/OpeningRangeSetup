# Análisis Familias A, B, C, etc.

## Resultado principal

No se descubrió todavía una feature que cumpla simultáneamente significancia corregida, tamaño de efecto y estabilidad cronológica. Este resultado no autoriza ningún filtro ni cambio de estrategia.

## Muestra

- Total de entradas Liquidity Burst causales: 184.
- Familia A — absorción verdadera estricta: 46.
- Familia B — breakout limpio estricto: 78.
- Familia C — trayectoria mixta: 60.
- Familia D — otras salidas: 0.
- Split cronológico: 60% discovery, 20% validation, 20% holdout abierto una sola vez al cierre.

## Definición de familias

- A: TP, MAE <=10 ticks y MFE >= TP inicial.
- B: SL, MFE <=10 ticks y MAE >= SL inicial.
- C: TP/SL con excursión intermedia que no cumple A/B estricta.
- D: time exit, break-even u otra salida.

## Features con mayor evidencia en discovery

| Feature | q permutación | Cliff delta A-B | Overlap | Estable | Robusta |
|---|---:|---:|---:|---:|---:|
| Profile_Local_Maxima_Count | 0.2129 | 0.409 | 0.696 | 0 | 0 |
| Previous_Delta_AtEntry | 0.6658 | -0.291 | 0.518 | 0 | 0 |
| Pre_Approach_Pause_Seconds | 0.6658 | -0.321 | 0.743 | 0 | 0 |
| Prior_Closed_ATR3_Ticks_AtEntry | 0.6658 | 0.286 | 0.733 | 0 | 0 |
| Prior_Closed_ATR5_Ticks_AtEntry | 0.6658 | 0.244 | 0.688 | 0 | 0 |
| Flow_3_5_DirectionalNetDelta | 0.6658 | 0.211 | 0.662 | 0 | 0 |
| Flow_3_5_GrossAggressive | 0.6658 | 0.230 | 0.698 | 0 | 0 |
| BuySellRatio | 0.6658 | -0.262 | 0.742 | 0 | 0 |
| Directional_VWAP_Distance_Ticks_AtEntry | 0.6658 | 0.288 | 0.774 | 0 | 0 |
| Signal_To_Entry_Latency_Milliseconds | 0.6658 | -0.191 | 0.686 | 0 | 0 |

## Modelos fuera de muestra

| Modelo | Split | n | Balanced accuracy | ROC AUC | Estado |
|---|---|---:|---:|---:|---|
| logistic | validation | 25 | 0.544 | 0.515 | OK |
| logistic | holdout | 29 | 0.292 | 0.239 | OK |
| decision_tree | validation | 25 | 0.401 | 0.364 | OK |
| decision_tree | holdout | 29 | 0.439 | 0.622 | OK |
| random_forest | validation | 25 | 0.640 | 0.559 | OK |
| random_forest | holdout | 29 | 0.383 | 0.278 | OK |
| catboost | validation | 25 | 0.548 | 0.507 | OK |
| catboost | holdout | 29 | 0.403 | 0.322 | OK |

## Causalidad y prevención de leakage

- Features aceptadas como causales: 142.
- Variables rechazadas o no disponibles: 9.
- MFE, MAE, resultado, salida y estados finales se usaron solo para etiquetas/outcomes.
- Refill, MBO, MBP y embeddings de libro se rechazaron porque el workspace replay actual no entrega ese stream; no se fabricaron valores.
- El análisis usa los CSV terminales por fecha como outcomes canónicos; `trade_results.csv` no se usa para MAE/MFE porque una recalculación sincronizada puede sobrescribir esa tabla con métricas parciales.

## Respuestas científicas

1. Las diferencias medibles se reportan con bootstrap, permutation test, Mann–Whitney, KS, Welch y corrección BH.
2. El ranking completo está en `feature_rankings.csv`; no se seleccionó por PF.
3. Las features nuevas se documentan con fórmula física en `feature_catalog.csv` y `candidate_features.csv`.
4. Mutual information, CMI proxy, SHAP de CatBoost, permutation importance y ablación quedan separados por método.
5. Ninguna combinación se convierte en filtro en esta corrida.
6. El porcentaje de B potencialmente detectable solo se considera si una feature es robusta en discovery/validation/holdout.
7. La pérdida potencial de ganadoras se calcula sobre A, nunca se oculta.
8. La prioridad siguiente es capturar un stream de libro reproducible solo si ATAS Historia lo suministra sin alterar el replay.

## Decisión

La estrategia y Liquidity Burst permanecen congelados. Este informe descubre o refuta propiedades; no optimiza entradas, TP, SL, RR ni gestión.

Artefactos: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\absorption_breakout_research_20260720_085139`
