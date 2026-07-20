# Investigación features pre-entry MBP+tape

## Resultado principal

Features MBP robustas bajo criterios congelados: **0**.

Esta investigación usa exclusivamente filas de mercado con timestamp menor o igual al `prediction_timestamp` original. Las respuestas de 1/3/5 segundos no son predictors.

## Cobertura

- Eventos: 184.
- Cutoff causal válido: 184/184.
- MBP disponible antes del cutoff: 172/184.
- Tape disponible antes del cutoff: 174/184.

## Features con mayor evidencia discovery

| Feature | Cobertura | q BH | Cliff A-B | Dirección estable | Robusta |
| --- | ---: | ---: | ---: | ---: | ---: |
| burst_w1_counter_volume | 100.0% | 0.792 | -0.164 | 0 | 0 |
| burst_w3_update_count | 100.0% | 0.792 | -0.209 | 0 | 0 |
| burst_w3_known_change_count | 100.0% | 0.792 | -0.209 | 0 | 0 |
| burst_w3_add_events | 100.0% | 0.792 | -0.273 | 0 | 0 |
| burst_w5_update_count | 100.0% | 0.792 | -0.201 | 0 | 0 |
| burst_w5_known_change_count | 100.0% | 0.792 | -0.199 | 0 | 0 |
| burst_w5_add_events | 100.0% | 0.792 | -0.230 | 0 | 0 |
| burst_w5_remove_events | 100.0% | 0.792 | -0.205 | 0 | 0 |
| burst_w5_counter_volume | 100.0% | 0.792 | -0.140 | 0 | 0 |
| burst_w10_update_count | 100.0% | 0.792 | -0.159 | 1 | 0 |
| burst_w10_known_change_count | 100.0% | 0.792 | -0.158 | 1 | 0 |
| burst_w10_add_events | 100.0% | 0.792 | -0.143 | 0 | 0 |

## Información incremental fuera de muestra

| Set | Modelo | Split | n | Balanced accuracy | ROC AUC |
| --- | --- | --- | ---: | ---: | ---: |
| BASELINE | logistic | validation | 25 | 0.607 | 0.566 |
| BASELINE | logistic | holdout | 29 | 0.322 | 0.278 |
| BASELINE | random_forest | validation | 25 | 0.702 | 0.640 |
| BASELINE | random_forest | holdout | 29 | 0.322 | 0.261 |
| MBP_ONLY | logistic | validation | 25 | 0.493 | 0.463 |
| MBP_ONLY | logistic | holdout | 29 | 0.464 | 0.433 |
| MBP_ONLY | random_forest | validation | 25 | 0.518 | 0.515 |
| MBP_ONLY | random_forest | holdout | 29 | 0.508 | 0.494 |
| BASELINE_PLUS_MBP | logistic | validation | 25 | 0.456 | 0.581 |
| BASELINE_PLUS_MBP | logistic | holdout | 29 | 0.378 | 0.278 |
| BASELINE_PLUS_MBP | random_forest | validation | 25 | 0.610 | 0.654 |
| BASELINE_PLUS_MBP | random_forest | holdout | 29 | 0.328 | 0.244 |

## Restricciones

- MBP permite cambios agregados por nivel, pero no identidad MBO; `refill` significa aproximación MBP, no iceberg confirmado.
- El mejor bid/ask no se reconstruye de forma confiable, por lo que estas features no simulan fills.
- El holdout existente ya fue abierto; cualquier hallazgo sirve para decidir una captura futura, no para activar un filtro.
- Ninguna feature post-entry fue usada como predictor.

Artefactos: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\preentry_liquidity_features_20260720_095000`
