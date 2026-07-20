# Resultado piloto MBO — Liquidity Burst

## Decisión

Puerta de compra: **NO PASÓ**.
Por tanto: **se detienen las compras de MBO**.

## Resultado primario

- Eventos/días: 30 (15 A, 15 B).
- AUC LOYO baseline causal: 0.796.
- AUC LOYO MBO-only: 0.387.
- AUC LOYO baseline + MBO: 0.569.
- Mejora incremental: -0.227.
- p de permutación para la mejora: 0.9980 (1000 permutaciones dentro de año).

## Puerta congelada

| Criterio | Observado | Umbral | Pasó |
| --- | ---: | ---: | ---: |
| MBO_ONLY_AUC_AT_LEAST_0_65 | 0.3867 | 0.6500 | 0 |
| DELTA_AUC_AT_LEAST_0_08 | -0.2267 | 0.0800 | 0 |
| DELTA_PERMUTATION_P_AT_MOST_0_10 | 0.9980 | 0.1000 | 0 |
| AT_LEAST_TWO_YEARS_NONNEGATIVE_DELTA | 1.0000 | 2.0000 | 0 |
| NO_YEAR_DELTA_BELOW_MINUS_0_05 | -0.4000 | -0.0500 | 0 |
| BUY_MBO_AUC_AT_LEAST_0_55 | 0.6071 | 0.5500 | 1 |
| SELL_MBO_AUC_AT_LEAST_0_55 | 0.1964 | 0.5500 | 0 |
| AT_LEAST_ONE_ROBUST_COMPACT_FEATURE | 0.0000 | 1.0000 | 0 |

## Features compactas

| Feature | Cobertura | Cliff A-B | q BH | Años estable | Lados estable | Robusta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| burst_w1_refill_100ms_share | 100.0% | -0.396 | 0.816 | 1 | 1 | 0 |
| burst_w1_new_order_survival_share | 100.0% | 0.236 | 0.839 | 0 | 1 | 0 |
| burst_w3_cancel_to_add_size | 100.0% | 0.280 | 0.839 | 0 | 1 | 0 |
| near_w1_fill_size_side_imbalance | 100.0% | -0.271 | 0.839 | 0 | 0 | 0 |
| burst_w1_passive_add_size | 100.0% | -0.004 | 1.000 | 0 | 0 | 0 |
| burst_w1_passive_pure_cancel_size | 100.0% | 0.164 | 1.000 | 0 | 1 | 0 |
| burst_w1_passive_fill_size | 100.0% | -0.027 | 1.000 | 0 | 1 | 0 |
| burst_w1_short_lived_250ms_share | 100.0% | 0.022 | 1.000 | 0 | 0 | 0 |
| near_w1_add_size_side_imbalance | 100.0% | 0.084 | 1.000 | 0 | 0 | 0 |
| near_w1_pure_cancel_size_side_imbalance | 100.0% | 0.120 | 1.000 | 0 | 1 | 0 |
| near_w3_orderbook_message_rate | 100.0% | 0.022 | 1.000 | 1 | 0 | 0 |
| near_w3_reuse_order_id_share | 100.0% | 0.129 | 1.000 | 0 | 0 | 0 |

## Restricciones

- El piloto está balanceado por etiqueta; AUC es interpretable, prevalencia/WR no.
- Las órdenes existentes antes de los 10 segundos no tienen snapshot completo. Las métricas de vida/supervivencia usan solo órdenes añadidas dentro de la ventana.
- Esta es una puerta de viabilidad discovery, no una validación final ni autorización para modificar entradas.
- Todas las filas con `ts_event` posterior al cutoff fueron excluidas.

Artefactos: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\mbo_liquidity_burst_viability_20260720_r1`
