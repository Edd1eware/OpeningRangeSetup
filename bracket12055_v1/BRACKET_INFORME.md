# BRACKET 120/55 — RECHAZADO (0 de 6). El +3.945 era un fenómeno de 2025.

Fecha: 2026-07-25 · Preregistro `c756e20b…` · Caracterización, no validación

## 1. Veredicto: FAIL (0 de 6 checks)

| Check | Umbral | Obtenido | |
|---|---|---:|---|
| A1-C1 EV neto > 0 en DEV | > 0 | **−0.834** | FAIL |
| A1-C2 PF > 1.15 en DEV | > 1.15 | **0.978** | FAIL |
| A2-C1 ≥60% ventanas positivas | ≥ 60% | **50%** | FAIL |
| A2-C2 ninguna ventana >50% PnL | ≤ 50% | **81.6%** | FAIL |
| A3-C1 payouts esperados > 0.5 | > 0.5 | **0.235** | FAIL |
| A3-C2 quema sin payout < 50% | < 50% | **81.1%** | FAIL |

## 2. Lo decisivo: el periodo que NO había visto es negativo

DEV 2022-2023 era el único material limpio para esta pregunta. Resultado:

| | n | Trades/mes | WR % | PF | EV neto |
|---|---:|---:|---:|---:|---:|
| **DEV 2022-23 (no visto)** | 296 | 17.41 | **32.09** | **0.978** | **−0.834** |
| 2022 | 134 | — | 30.60 | 0.913 | −3.455 |
| 2023 | 162 | — | 33.33 | 1.035 | +1.333 |
| FRESH 2024-26 (ya quemado) | 402 | 18.27 | 34.83 | 1.106 | +3.945 |

WR de 32.09% contra un breakeven de **31.43%**: un margen de 0.66 puntos
porcentuales. Es indistinguible de un coin flip con costes.

**El +3.945 que vi en FRESH no generaliza hacia atrás.**

## 3. Toda la ganancia vive en 2025

| Ventana | n | EV neto | PnL |
|---|---:|---:|---:|
| 2022-H1 | 46 | +0.07 | +3 |
| 2022-H2 | 88 | −5.30 | **−466** |
| 2023-H1 | 75 | +8.33 | +625 |
| 2023-H2 | 87 | −4.70 | **−409** |
| 2024-H1 | 75 | −10.33 | **−775** |
| 2024-H2 | 87 | −0.68 | −59 |
| 2025-H1 | 76 | +14.38 | **+1093** |
| 2025-H2 | 86 | +12.19 | **+1048** |
| 2026-H1 | 77 | +4.36 | +336 |

Solo 50% de las ventanas son positivas, y **una sola concentra el 81.6% del
PnL**. Hay tres semestres con pérdidas fuertes (−466, −409, −775).

Esto no es un edge con varianza: es un año bueno rodeado de años malos.

## 4. Monte Carlo: inviable para el objetivo

| | Valor |
|---|---:|
| Payouts esperados | 0.235 |
| P(quema) | 100.0% |
| P(quema sin cobrar payout) | **81.1%** |

El SL de 55 ticks con 4 contratos = $1,100 por pérdida. Con WR ~33%, cuatro
pérdidas seguidas ocurren el 20% de las veces y consumen los $4,500 de MaxLoss.
La estructura del bracket es incompatible con el límite de la cuenta.

## 5. Por qué este test valía la pena

Vi el resultado de FRESH antes de preregistrar, así que FRESH no podía confirmar
nada. Lo único limpio disponible era DEV — y **DEV lo mató**. Si hubiera evaluado
sobre los mismos datos que ya había visto, esto habría "pasado" y sería un
falso positivo camino al fondeo.

`INFORMATION_STATUS=BRACKET12055_REJECTED_2025_ARTIFACT`
