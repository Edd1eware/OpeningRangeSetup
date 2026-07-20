# Validación temporal ciega — Liquidity Burst: absorción A vs breakout B

Conclusión congelada: **NOT_SUPPORTED**.

## Objetivo y cutoff

El detector identifica el Liquidity Burst. El clasificador estima A vs B en `feature_timestamp_utc`, el mismo callback causal de la decisión original, después de la publicación real del detector y sin esperar 1/3/5 s.

- Modelo/variables/umbrales congelados con 70 eventos de 2022–2024.
- Reentrenamientos o ajustes usando 2025–2026: **0**.
- MBO y MBP incremental: excluidos.
- C mixto: abstención; no se fuerza a A/B.
- La lógica operativa no fue modificada.

## Muestra

- Eventos unidos: 60.
- A/B estrictos: 45 (15 A, 30 B).
- Familias: `{"A_TRUE_ABSORPTION": 15, "B_CLEAN_BREAKOUT": 30, "C_MIXED_PATH": 15}`.

## Resultado principal

- AUC: 0.336.
- Balanced accuracy @0.5: 0.350.
- Sensibilidad absorción A: 0.400.
- Especificidad breakout B: 0.300.
- p permutación temporal: 0.9930.
- Bootstrap 95% AUC: [0.160, 0.513].

## Regímenes congelados

| Régimen | Cobertura | A/B | AUC | Complemento | Delta | Soportado |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| VWAP_FAR | 51.1% | 10/13 | 0.362 | 0.306 | +0.056 | 0 |
| RV60_HIGH | 77.8% | 13/22 | 0.336 | 0.125 | +0.211 | 0 |

## Interpretación permitida

`SUPPORTED` significa que el baseline causal o al menos uno de los dos contextos congelados sobrevivió fuera de muestra. No autoriza por sí solo un filtro operativo; primero se revisan cobertura, errores y C mixtos.
`NOT_SUPPORTED` detiene esta línea: no se reajusta el modelo sobre 2025–2026.
