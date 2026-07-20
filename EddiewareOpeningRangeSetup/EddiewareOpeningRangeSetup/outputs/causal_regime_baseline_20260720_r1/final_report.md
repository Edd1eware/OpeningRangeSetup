# Segmentación causal de régimen y estabilidad del baseline

## Aislamiento

- Eventos discovery: 70.
- Años utilizados: 2022–2024.
- Filas 2025–2026 utilizadas: **0**.
- Validation/holdout abiertos por esta investigación: **0**.

## Resultado global

Estabilidad global del baseline causal: **NO PASÓ**.
Regímenes candidatos que pasan todos los criterios: **3**.

- AUC OOF CORE_BASELINE: 0.686.
- AUC OOF EXISTING_CAUSAL: 0.681.
- p de permutación EXISTING_CAUSAL: 0.0135.
- Bootstrap 95%: [0.568, 0.790].

## Estabilidad por año y lado

| Subgrupo | Core | Existing causal |
| --- | ---: | ---: |
| YEAR_2022 | 0.889 | 0.838 |
| YEAR_2023 | 0.652 | 0.652 |
| YEAR_2024 | 0.662 | 0.727 |
| SIDE_BUY | 0.806 | 0.810 |
| SIDE_SELL | 0.541 | 0.521 |

## Puerta global congelada

| Criterio | Observado | Umbral | Pasó |
| --- | ---: | ---: | ---: |
| OVERALL_AUC_AT_LEAST_0_65 | 0.6812 | 0.6500 | 1 |
| PERMUTATION_P_AT_MOST_0_05 | 0.0135 | 0.0500 | 1 |
| YEAR_2022_AUC_AT_LEAST_0_55 | 0.8376 | 0.5500 | 1 |
| YEAR_2023_AUC_AT_LEAST_0_55 | 0.6516 | 0.5500 | 1 |
| YEAR_2024_AUC_AT_LEAST_0_55 | 0.7273 | 0.5500 | 1 |
| BUY_AUC_AT_LEAST_0_55 | 0.8095 | 0.5500 | 1 |
| SELL_AUC_AT_LEAST_0_55 | 0.5206 | 0.5500 | 0 |
| BOOTSTRAP_CI_LOWER_AT_LEAST_0_50 | 0.5677 | 0.5000 | 1 |

## Regímenes con mayor AUC

| Eje | Segmento | Cobertura | A/B | AUC | Complemento | q BH | Candidato |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| VWAP_DISTANCE_ABS | FAR | 47.1% | 11/22 | 0.781 | 0.596 | 0.020 | 1 |
| REALIZED_VOL_60S | HIGH | 42.9% | 13/17 | 0.778 | 0.628 | 0.021 | 1 |
| FLOW_INTENSITY | LOW | 51.4% | 11/25 | 0.756 | 0.580 | 0.020 | 1 |
| ATR5 | HIGH | 41.4% | 14/15 | 0.790 | 0.572 | 0.020 | 0 |
| PROFILE_CONCENTRATION | DISPERSED | 47.1% | 15/18 | 0.759 | 0.618 | 0.020 | 0 |
| OR_WIDTH | WIDE | 45.7% | 15/17 | 0.725 | 0.670 | 0.034 | 0 |
| PATH_EFFICIENCY | ROTATIONAL | 50.0% | 13/22 | 0.696 | 0.661 | 0.037 | 0 |
| OR_WIDTH | NARROW | 54.3% | 14/24 | 0.670 | 0.725 | 0.061 | 0 |
| PATH_EFFICIENCY | DIRECTIONAL | 50.0% | 16/19 | 0.661 | 0.696 | 0.072 | 0 |
| REALIZED_VOL_60S | LOW | 57.1% | 16/24 | 0.628 | 0.778 | 0.130 | 0 |

## Coeficientes

Features con signo idéntico en los tres folds: 12/21.

## Interpretación

- Los segmentos se evaluaron con predicciones fuera de año y umbrales de régimen aprendidos sin el año de prueba.
- Un AUC alto aislado no basta: debe conservar cobertura, significancia, estabilidad anual y ambos lados.
- Este análisis no modifica entradas, no estima WR/PF y no autoriza abrir 2025–2026.

Artefactos: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\causal_regime_baseline_20260720_r1`
