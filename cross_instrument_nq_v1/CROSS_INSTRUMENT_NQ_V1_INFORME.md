# CROSS-INSTRUMENT-NQ-V1 — ES mejora la media, pero no valida un edge

Fecha: 2026-07-25  
Preregistro SHA-256: `72fc5eae…`  
Resultado: **BASE FAIL + ES_CONFIRM FAIL**

## 1. Veredicto

Se reconstruyeron 1,028 fechas emparejadas NQ/ES con `09:30
America/New_York`, sin errores y sin descargar datos. El bloque primario fue el
conjunto EST que los backtests anteriores habían omitido.

### Edge base, EST no observado

| Gate | Resultado |
|---|---:|
| B1 EV neto > 0 | **-1.45t — FAIL** |
| B2 PF > 1.10 | **0.953 — FAIL** |
| B3 años positivos >= 3 | **2 — FAIL** |
| B4 n >= 100 | 165 — PASS |

El primer breakout UP con bracket 60/60 no sobrevive el bloque nuevo. Con coste
conservador de 4 ticks, su `P(pass)` LucidPro 150k es solo **14.60%**.

### Confirmación ES, EST no observado

Regla congelada: el último segundo completo de ES anterior al breakout de NQ
debe cerrar por encima del OR-high de ES.

| Gate | Resultado |
|---|---:|
| C1 EV neto > 0 | +5.23t — PASS |
| C2 PF > 1.15 | 1.193 — PASS |
| C3 mejora vs BASE >= +2t | +6.69t — PASS |
| C4 años positivos >= 3 | 3 — PASS |
| C5 n >= 50 | **26 — FAIL** |
| C6 IC95 del EV con límite inferior > 0 | **[-17.85, +28.31] — FAIL** |

ES_CONFIRM mejora la media y lleva el Monte Carlo corregido a
`P(pass)=39.42%`, pero no hay evidencia suficiente para llamarlo edge. La
muestra es pequeña, el intervalo incluye pérdidas grandes y 2026 da **-40t por
trade**.

## 2. Estabilidad temporal

| Año | BASE EV | ES_CONFIRM n | ES_CONFIRM EV |
|---|---:|---:|---:|
| 2022 | +16.00 | 4 | -4.00 |
| 2023 | -6.50 | 5 | +8.00 |
| 2024 | +5.00 | 6 | +36.00 |
| 2025 | -0.84 | 6 | +16.00 |
| 2026 | -14.00 | 5 | **-40.00** |

El resultado agregado de ES_CONFIRM depende de 11 trades en 2024-2025. No
compensa el colapso de 2026.

## 3. Control de reconstrucción

El brazo descriptivo EDT reproduce exactamente el conteo del estudio anterior
para 2024-2026: `64 + 76 + 37 = 177` trades. Al subir el coste de 2 a 4 ticks,
los EV anuales cambian exactamente -2 ticks. Esto confirma que la reconstrucción
DST-aware es compatible con la lógica anterior en los días donde 13:30 UTC sí
era la apertura correcta.

## 4. LucidPro 150k

| Pool EST | P(pass) | P(burn) | Mediana trades al pase | Meses activos estimados |
|---|---:|---:|---:|---:|
| BASE | 14.60% | 85.40% | 41 | 4.97 |
| ES_CONFIRM | **39.42%** | 60.58% | 39 | **22.50** |

El simulador usa el piso oficial bloqueado:

```text
floor = min(peak_EOD - 4,500, +100)
```

y comprueba el MAE intratrade antes de acreditar el resultado diario. No hay
vencimiento artificial. El DLL no se alcanza con una sola operación de 3 NQ.

El 39.42% es compatibilidad mecánica condicionada al pool observado; no
probabilidad prospectiva confiable, porque el pool ES_CONFIRM no validó.

## 5. Decisión

No se descarga YM/RTY y no se prueban variantes de ES_CONFIRM sobre este mismo
holdout. La señal se conserva como hipótesis forward, no como estrategia
operable.

La evidencia sí cambia la dirección de investigación:

1. el breakout UP incondicional queda debilitado por datos nuevos;
2. la confirmación cross-market tiene efecto del tamaño correcto, pero frecuencia
   y muestra insuficientes;
3. la siguiente validación legítima requiere historia anterior no usada o datos
   forward posteriores a 2026-07-01.

`INFORMATION_STATUS=CROSS_INSTRUMENT_NQ_V1_FAIL_POSITIVE_BUT_UNDERPOWERED`
