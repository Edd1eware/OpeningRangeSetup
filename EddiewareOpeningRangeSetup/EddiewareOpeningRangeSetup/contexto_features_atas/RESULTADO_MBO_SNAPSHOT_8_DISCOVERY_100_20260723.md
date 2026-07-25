# Resultado MBO Snapshot 8 — Discovery 100 sesiones

Fecha de cierre: 2026-07-23  
Objetivo: separar causalmente una absorción limpia (A) de un breakout limpio (B) antes de abrir 2025–2026.

## Veredicto

**NO SOY CAPAZ DE SEPARAR UNA ABSORCIÓN DE UN BREAKOUT LIMPIO con esta representación.**

Las ocho variables MBO preregistradas, aun con snapshot y estado inicial completo, no mejoran el baseline MATRIX ni superan las puertas de permutación, estabilidad temporal y estabilidad BUY/SELL.

## Integridad causal

- 100/100 sesiones procesadas.
- Discovery limpio A/B: 70 observaciones; A=29 y B=41.
- Familia C: 30 observaciones, excluidas del ajuste A/B.
- Cutoff causal cumplido: 100/100.
- Eventos posteriores a `t_decision` usados: 0.
- Ventanas MBO completas: 250 ms y 500 ms.
- Comprobaciones causales MATRIX: 14/14.
- Eventos F/C ambiguos excluidos de la cancelación pura: 41.
- Eventos con estado desconocido: 0.
- MFE, MAE, TP, SL, PnL y resultado no fueron predictores.
- Validación: LOYO 2022/2023/2024, 1,000 bootstraps y 1,000 permutaciones.

## Comparación fuera de año

| Bloque | BA LOYO | AUC LOYO | IC95% BA | p permutación |
|---|---:|---:|---:|---:|
| MATRIX_TRANSITIONS | 0.542 | 0.597 | [0.426, 0.655] | 0.266 |
| MBO_SNAPSHOT_8 | 0.485 | 0.511 | [0.377, 0.603] | 0.596 |
| MATRIX_TRANSITIONS + MBO_SNAPSHOT_8 | 0.537 | 0.514 | [0.431, 0.653] | 0.314 |

El bloque combinado pierde 0.005 de BA y 0.083 de AUC frente a MATRIX. Su sensibilidad para A es 0.586 y su especificidad para B es 0.488. El mínimo marginal año/lado es 0.416 y sólo 4 de 6 celdas año×lado presentan dirección física coherente.

## Estabilidad

Resultado combinado por año:

- 2022: BA 0.641; AUC 0.598.
- 2023: BA 0.416; AUC 0.430.
- 2024: BA 0.604; AUC 0.584.

Resultado combinado por lado:

- BUY: BA 0.470; AUC 0.425.
- SELL: BA 0.578; AUC 0.562.

Las celdas que no cumplen coherencia direccional son 2023 BUY (1/7 signos) y 2024 BUY (3/7). Solamente `impact_efficiency_250ms` conserva el signo esperado en 5/6 celdas; no es suficiente para una clasificación estable. `durable_refill_removed_ratio_250ms` sólo es coherente en 2/6.

## Lectura de las ocho variables

En el agregado A/B, varias medias conservan el sentido físico esperado —más supervivencia y refill en A, y más consumo, retiro, impacto, depleción y patrón breakout en B—, pero las diferencias son pequeñas y cambian por año o lado. El problema no es que el MBO carezca de identidad o snapshot: el problema es que esta agregación fija de 250/500 ms destruye o mezcla parte de la secuencia que diferencia ambos mecanismos.

## Auditoría de alineación de precio

Se corrigió la comparación anterior: `burst_price` no debía tratarse como el primer precio real del DOM/tape. Comparando el L0 MBO con el primer tape causal de ATAS:

- 86 sesiones comparables.
- Diferencia mediana: 2 ticks.
- Percentil 90: 4 ticks.
- 78/86 están dentro de 4 ticks.

Hay dos outliers, ambos el 13 de junio en rollover:

- 2022-06-13: MBO resolvió NQM2 mientras ATAS parece estar en NQU2.
- 2023-06-13: MBO resolvió NQM3 mientras ATAS parece estar en NQU3.

Excluir post hoc esas dos sesiones deja al combinado en BA 0.516 y AUC 0.523. Por tanto, los rollovers deben corregirse para integridad del archivo, pero no explican ni rescatan el resultado negativo.

## Decisión

- No abrir 2025–2026.
- No descargar más fechas bajo esta representación MBO de ocho agregados.
- Conservar los datos y artefactos; no reinterpretar BA/AUC como WR/PF.

## Next steps

1. Corregir exclusivamente las dos sesiones de rollover con el contrato NQU correspondiente y repetir el mismo análisis congelado, sin cambiar variables ni umbrales.
2. Si el veredicto continúa negativo, cerrar formalmente `MBO_SNAPSHOT_8`.
3. Si se continúa investigando, preregistrar una representación secuencial en tiempo de evento: anclar `t0` al primer paquete MBO causal de agresión/impacto direccional, conservar identidad de orden y medir la duración/orden de consumo, refill, supervivencia e impacto, en vez de resumir todo en ventanas fijas.
4. Utilizar estas mismas 100 sesiones como discovery y exigir de nuevo estabilidad por año y BUY/SELL, permutación e incremento sobre MATRIX.
5. Abrir una sola vez 2025–2026 únicamente si la nueva representación supera todas las puertas preregistradas.

