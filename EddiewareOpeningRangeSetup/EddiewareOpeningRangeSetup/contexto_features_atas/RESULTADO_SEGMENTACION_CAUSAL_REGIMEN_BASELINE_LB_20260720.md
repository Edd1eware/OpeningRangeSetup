# Resultado — segmentación causal de régimen del Liquidity Burst

Fecha: 2026-07-20.

## Pregunta preservada

El objetivo no es buscar temporadas rentables ni retrasar cinco segundos la entrada. Es detectar el Liquidity Burst y, en el cutoff causal de la decisión original, anticipar si el movimiento posterior será:

- A: absorción verdadera;
- B: breakout limpio;
- C: trayectoria mixta, tratada como abstención.

## Aislamiento

- Muestra: 70 eventos A/B discovery, exclusivamente 2022–2024.
- A: 29; B: 41.
- Años: 2022 = 22, 2023 = 30, 2024 = 18.
- Lados: BUY = 33, SELL = 37.
- Filas o resultados 2025–2026 abiertos: 0.
- Validación: leave-one-year-out; 2,000 permutaciones de modelo, 5,000 permutaciones de régimen y 5,000 bootstraps.

## Baseline

| Modelo | AUC OOF global | 2022 | 2023 | 2024 | BUY | SELL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Core causal, 10 variables | 0.686 | 0.889 | 0.652 | 0.662 | 0.806 | 0.541 |
| Core + 12 MBP/tape | 0.681 | 0.838 | 0.652 | 0.727 | 0.810 | 0.521 |

- El baseline con MBP/tape fue significativo frente al azar: p = 0.0135.
- Bootstrap 95% del AUC: [0.568, 0.790].
- La puerta global no pasó por una sola condición: SELL quedó debajo de 0.55.
- Las 12 variables MBP/tape no agregaron información: delta AUC frente al core = -0.005; p incremental = 0.515.
- El piloto MBO tampoco agregó valor y empeoró el baseline. No se justifica comprar más MBO.

## Regímenes encontrados en el análisis preregistrado

Con el baseline causal existente pasaron la puerta completa:

| Régimen | Cobertura | A/B | AUC OOF | Complemento | Delta | q BH | BUY | SELL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| VWAP distante | 47.1% | 11/22 | 0.781 | 0.596 | +0.185 | 0.020 | 0.848 | 0.764 |
| Volatilidad 60 s alta | 42.9% | 13/17 | 0.778 | 0.628 | +0.151 | 0.021 | 0.967 | 0.702 |
| Flujo 3–5 s bajo | 51.4% | 11/25 | 0.756 | 0.580 | +0.177 | 0.020 | 0.875 | 0.571 |

## Auditoría de robustez de representación

Se repitió la evaluación de regímenes con el baseline mínimo, sin las 12 variables MBP/tape. El resultado fue:

- VWAP distante: mantuvo AUC 0.773, BUY 0.864 y SELL 0.782.
- Volatilidad 60 s alta: mantuvo AUC 0.805, BUY 0.967 y SELL 0.762.
- Flujo 3–5 s bajo perdió la mejora mínima frente al complemento; se descarta antes del holdout.
- ATR5 alto y perfil disperso aparecieron sólo con el core, pero no fueron estables con el baseline existente; se descartan.

Por tanto, los únicos contextos retenidos para la validación ciega son VWAP distante y volatilidad 60 s alta.

## Umbrales congelados para 2025–2026

- `VWAP_FAR`: `abs(Directional_VWAP_Distance_Ticks_AtEntry) > 136.565000`.
- `RV60_HIGH`: `Realized_Volatility_60s_Ticks > 11.8109928443754`.
- Clasificador: regresión logística regularizada del core causal de 10 variables.
- Umbral de clase: probabilidad de A >= 0.50.
- Cutoff: `feature_timestamp_utc`, el mismo callback causal de la decisión original.

Los regímenes son estratos científicos. No bloquean entradas ni modifican TP, SL o gestión.

## Interpretación correcta

Existe señal suficiente para justificar una única validación temporal ciega, pero todavía no existe evidencia suficiente para operar un filtro. El baseline global es prometedor y los dos contextos son hipótesis concretas; ambos deben sobrevivir 2025–2026 sin reentrenamiento.

Si el holdout falla, no se ajustará el modelo con 2025–2026 y se detendrá esta línea de investigación.

## Artefactos

- Investigación: `outputs/causal_regime_baseline_20260720_r1`.
- Paquete congelado: `outputs/lb_absorption_breakout_frozen_20260720_r1`.
- Auditoría previa: `contexto_features_atas/AUDITORIA_DISENO_VALIDACION_LB_ABSORCION_VS_BREAKOUT_DST_2025_2026_20260720.md`.

