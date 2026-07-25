# MBO SNAPSHOT 8 — RESULTADO PREDICTIVO DISCOVERY

## NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO

Este veredicto usa únicamente A/B discovery 2022–2024. C permanece fuera del entrenamiento y 2025–2026 permanece sellado.

## Integridad

- Sesiones MBO: 100/100.
- A/B limpio: 70; A=29; B=41.
- Cutoff causal: 100/100; eventos posteriores usados: 0.
- Cobertura mínima: 250.000 ms en W250; 500.000 ms en W500.
- MATRIX causal: 14/14 controles requeridos.
- C/F ambiguos excluidos de cancelación pura: 41.
- Eventos incrementales sin estado previo: 0.
- MAE/MFE/TP/SL/PnL no usados.

## Resultados LOYO

| bloque | n | BA | IC95% | AUC | sens A | esp B | p perm | min año/lado | 5/6 mecanismo | estado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| MATRIX_TRANSITIONS | 70 | 0.542 | [0.426,0.655] | 0.597 | 0.621 | 0.463 | 0.2657 | 0.446 | 4/6 | NO_SUPERA_PUERTA_DISCOVERY |
| MBO_SNAPSHOT_8 | 70 | 0.485 | [0.377,0.603] | 0.511 | 0.483 | 0.488 | 0.5964 | 0.342 | 4/6 | NO_SUPERA_PUERTA_DISCOVERY |
| MATRIX_TRANSITIONS_PLUS_MBO_SNAPSHOT_8 | 70 | 0.537 | [0.431,0.653] | 0.514 | 0.586 | 0.488 | 0.3137 | 0.416 | 4/6 | NO_SUPERA_PUERTA_DISCOVERY |

## Estabilidad física año × lado

| celda | n A | n B | signos coherentes | estado |
|---|---:|---:|---:|---|
| 2022 BUY | 5 | 5 | 5/7 | PASS |
| 2022 SELL | 4 | 8 | 5/7 | PASS |
| 2023 BUY | 3 | 10 | 1/7 | FAIL |
| 2023 SELL | 10 | 7 | 5/7 | PASS |
| 2024 BUY | 4 | 6 | 3/7 | FAIL |
| 2024 SELL | 3 | 5 | 5/7 | PASS |

## Decisión

La puerta discovery no se superó. 2025–2026 no se abre y no se compran más fechas bajo esta representación.

Gráfica: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\mbo_snapshot_discovery100_20260723_r1\mbo_snapshot_discovery_effectiveness.png`.
