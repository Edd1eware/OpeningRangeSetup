# Diagnóstico CatBoost — Liquidity Burst A vs B

## Alcance

- Discovery 2022–2024: 70 A/B.
- Corrida abierta 2025–2026: 45 A/B.
- Esta investigación es posterior a abrir el holdout. Sirve para generar hipótesis; no crea una nueva validación.
- CatBoost usa profundidad 2, regularización L2 fuerte y parámetros fijos; no se optimiza contra 2025–2026.
- Respuestas 1/3/5 s y campos de outcome no entran como predictores.

## Desempeño temporal

| Corte | Features | n | AUC | Balanced acc. | p permutación |
| --- | --- | ---: | ---: | ---: | ---: |
| DISCOVERY_TO_NEW | CORE_FROZEN | 45 | 0.384 | 0.333 | 0.9416 |
| DISCOVERY_TO_NEW | BURST_MECHANISM | 45 | 0.436 | 0.433 | 0.8400 |
| DISCOVERY_TO_NEW | ALL_CAUSAL | 45 | 0.327 | 0.317 | 0.9874 |
| THROUGH_2025_TO_2026 | CORE_FROZEN | 11 | 0.067 | 0.183 | 0.9946 |
| THROUGH_2025_TO_2026 | BURST_MECHANISM | 11 | 0.333 | 0.383 | 0.8422 |
| THROUGH_2025_TO_2026 | ALL_CAUSAL | 11 | 0.200 | 0.183 | 0.9638 |

## Incremento frente al core

| Features | Delta AUC | Bootstrap 95% | P(delta>0) |
| --- | ---: | ---: | ---: |
| ALL_CAUSAL | -0.058 | [-0.249, +0.140] | 0.277 |
| BURST_MECHANISM | +0.051 | [-0.113, +0.216] | 0.723 |

## Features univariadas estables

Candidatas que pasan todos los criterios: **0**.

| Feature | Familia | AUC old | AUC new | 2025 | 2026 | BUY | SELL | q |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Realized_Volatility_10s_Ticks | BURST_INTENSITY | 0.594 | 0.708 | 0.727 | 0.400 | 0.463 | 0.889 | 0.996 |
| Realized_Volatility_60s_Ticks | BURST_INTENSITY | 0.559 | 0.704 | 0.693 | 0.400 | 0.481 | 0.873 | 0.996 |
| Realized_Volatility_30s_Ticks | BURST_INTENSITY | 0.588 | 0.686 | 0.722 | 0.400 | 0.420 | 0.929 | 0.996 |
| Dist_OR_Low_Ticks | AUCTION_CONTEXT | 0.559 | 0.671 | 0.753 | 0.467 | 0.519 | 0.611 | 0.996 |
| Flow_3_5_GrossAggressive | FLOW_PERSISTENCE | 0.615 | 0.670 | 0.818 | 0.400 | 0.685 | 0.675 | 0.996 |
| Dist_VAL_Ticks | BURST_INTENSITY | 0.561 | 0.659 | 0.738 | 0.400 | 0.469 | 0.591 | 0.996 |
| Flow_3_5_DirectionalVelocityTPS | FLOW_PERSISTENCE | 0.571 | 0.642 | 0.627 | 0.533 | 0.512 | 0.714 | 0.996 |
| Dist_VWAP_Ticks | AUCTION_CONTEXT | 0.553 | 0.642 | 0.760 | 0.367 | 0.457 | 0.532 | 0.996 |
| Dist_OR_High_Ticks | AUCTION_CONTEXT | 0.548 | 0.639 | 0.756 | 0.333 | 0.426 | 0.548 | 0.996 |
| BreakOut_TICKS_PER_SEC_AtEntry | BURST_INTENSITY | 0.549 | 0.620 | 0.662 | 0.533 | 0.481 | 0.690 | 0.996 |
| Pre_Approach_Velocity_TPS | CROSSING_ANATOMY | 0.600 | 0.613 | 0.620 | 0.350 | 0.389 | 0.782 | 0.996 |
| Velocity_Retention_3_5 | FLOW_PERSISTENCE | 0.573 | 0.604 | 0.582 | 0.520 | 0.516 | 0.605 | 0.996 |
| Signed_Previous_Delta_Share_AtEntry | BURST_INTENSITY | 0.541 | 0.590 | 0.629 | 0.417 | 0.506 | 0.730 | 0.996 |
| Profile_Excess_Kurtosis | AUCTION_CONTEXT | 0.574 | 0.571 | 0.596 | 0.533 | 0.568 | 0.540 | 0.996 |
| signed_velocity_3s | BURST_INTENSITY | 0.584 | 0.563 | 0.604 | 0.267 | 0.389 | 0.683 | 0.996 |

## SHAP fuera de muestra — ALL_CAUSAL

| Rango | Feature | Familia | Mean abs SHAP | Corr(value, SHAP) | SHAP A-B |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | Flow_1_3_CounterflowShare | FLOW_PERSISTENCE | 0.4603 | 0.668 | -0.0192 |
| 2 | Previous_Delta_AtEntry | BURST_INTENSITY | 0.3957 | -0.706 | -0.2600 |
| 3 | mean_trade_size | BURST_INTENSITY | 0.1828 | -0.830 | -0.0126 |
| 4 | Profile_Local_Maxima_Count | AUCTION_CONTEXT | 0.1694 | 0.838 | -0.0348 |
| 5 | Directional_VWAP_Distance_Ticks_AtEntry | AUCTION_CONTEXT | 0.1216 | 0.933 | -0.1555 |
| 6 | PreEntry_Volume_Climax_Ratio_AtEntry | BURST_INTENSITY | 0.1113 | 0.813 | -0.0207 |
| 7 | PreEntry_Directional_Efficiency3_AtEntry | BURST_INTENSITY | 0.0913 | 0.399 | -0.0059 |
| 8 | Nearest_OR_Edge_Distance_Ticks_AtEntry | AUCTION_CONTEXT | 0.0850 | 0.642 | -0.0481 |
| 9 | BuySellRatio | BURST_INTENSITY | 0.0830 | -0.803 | -0.0326 |
| 10 | Flow_3_5_GrossAggressive | FLOW_PERSISTENCE | 0.0824 | 0.788 | +0.0453 |
| 11 | Flow_3_5_CounterflowShare | FLOW_PERSISTENCE | 0.0738 | -0.882 | +0.0981 |
| 12 | Short_Long_Volatility_Ratio | BURST_INTENSITY | 0.0727 | 0.726 | -0.0215 |
| 13 | Velocity_Retention_1_3 | FLOW_PERSISTENCE | 0.0692 | 0.875 | -0.0040 |
| 14 | Previous_Volume_AtEntry | BURST_INTENSITY | 0.0666 | -0.663 | -0.0506 |
| 15 | Flow_3_5_DirectionalNetDelta | FLOW_PERSISTENCE | 0.0541 | 0.796 | +0.0168 |

## Familias

| Familia | Modo | Features | AUC new |
| --- | --- | ---: | ---: |
| ACCEPTANCE_REJECTION | ONLY_FAMILY | 2 | 0.563 |
| EFFORT_RESULT | ONLY_FAMILY | 2 | 0.547 |
| FLOW_PERSISTENCE | ONLY_FAMILY | 19 | 0.500 |
| CROSSING_ANATOMY | ONLY_FAMILY | 3 | 0.496 |
| AUCTION_CONTEXT | ONLY_FAMILY | 23 | 0.436 |
| LEVEL_MEMORY | ONLY_FAMILY | 4 | 0.436 |
| BURST_INTENSITY | ONLY_FAMILY | 66 | 0.280 |
| BURST_INTENSITY | WITHOUT_FAMILY | 53 | 0.473 |
| ACCEPTANCE_REJECTION | WITHOUT_FAMILY | 117 | 0.358 |
| AUCTION_CONTEXT | WITHOUT_FAMILY | 96 | 0.344 |
| LEVEL_MEMORY | WITHOUT_FAMILY | 115 | 0.340 |
| CROSSING_ANATOMY | WITHOUT_FAMILY | 116 | 0.336 |
| FLOW_PERSISTENCE | WITHOUT_FAMILY | 100 | 0.318 |
| EFFORT_RESULT | WITHOUT_FAMILY | 117 | 0.316 |

## Regla de interpretación

CatBoost sólo demuestra información nueva si ALL_CAUSAL o BURST_MECHANISM supera al CORE fuera de era con delta positivo, intervalo bootstrap que no cruce cero y estabilidad en 2025/2026 y BUY/SELL. SHAP por sí solo explica el modelo; no valida una feature.
