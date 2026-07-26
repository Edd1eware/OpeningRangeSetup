# LUCID100K-V1 — fixed 60/60 UP-only: FAIL por 0.96 puntos

Fecha: 2026-07-25 · Preregistro `372249ff…` · Disparo único sobre FRESH

## 1. Veredicto: FAIL (3 de 4 gates pasan)

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| G1 EV neto > 0 | > 0 | **+3.763** | PASS |
| G2 WR > breakeven | > 51.67% | **54.80%** | PASS |
| G3 **P(pasar) ≥ 30%** | ≥ 30% | **29.04%** | **FAIL** |
| G4 Años EV>0 ≥ 2 | ≥ 2 de 3 | 2 de 3 | PASS |

Falla **solo** por P(pass), y por 0.96 puntos porcentuales. Por el preregistro
eso es rechazo y el umbral no se toca.

## 2. La regla y su desempeño

```text
primer breakout del OR 09:30, SOLO UP, bracket FIJO 60/60 (RR exactamente 1:1)
2 contratos | comision 2 ticks | breakeven WR = 51.67%
```

| Bloque | n | Trades/mes | WR % | PF | EV neto |
|---|---:|---:|---:|---:|---:|
| DEV 2022-23 | 155 | 9.69 | 51.61 | 0.998 | **−0.065** |
| FRESH 2024-26 | 177 | 8.43 | **54.80** | 1.134 | **+3.763** |

Por año en FRESH:

| Year | n | WR % | PF | EV neto |
|---|---:|---:|---:|---:|
| 2024 | 64 | 45.31 | 0.775 | **−7.625** |
| 2025 | 76 | 59.21 | 1.358 | +9.053 |
| 2026 | 37 | 62.16 | 1.537 | +12.595 |

## 3. Simulación de la evaluación (métrica primaria)

| | Valor |
|---|---:|
| **P(pasar)** | **29.04%** |
| P(quemar) | 70.89% |
| P(timeout 120 días) | 0.07% |
| **Intentos esperados para pasar** | **3.44** |

Con 2 contratos, el SL de 60 ticks son $600; el MLL de $3,000 aguanta **5
pérdidas seguidas**. Con WR 54.8%, esa racha ocurre lo bastante seguido como
para quemar 7 de cada 10 intentos.

## 4. El caveat que importa más que el gate

**DEV 2022-23 está en breakeven exacto**: EV −0.065, PF 0.998, WR 51.61% contra
un breakeven de 51.67%. Y 2024 pierde −7.625.

Es decir: el WR de 54.8% en FRESH viene **enteramente de 2025-2026**. Es el mismo
patrón de concentración que apareció en todo lo demás hoy. No hay corroboración
en el periodo anterior.

Un P(pass) de 29% construido sobre un edge que solo existe en dos años recientes
no es lo mismo que uno construido sobre un edge estable.

## 5. Observación no probada (declarada, no promovida)

El tamaño de posición está congelado en 2 contratos y **no se puede tocar para
hacer pasar el MC** (prohibido por el preregistro). Pero la aritmética sugiere un
trade-off real: con 1 contrato el MLL aguantaría 10 pérdidas seguidas en vez de
5, a costa de necesitar el doble de trades netos ganadores para el target.

Cuál de los dos maximiza P(pass) es una pregunta legítima **que requiere su
propio preregistro**, no un ajuste sobre este resultado.

## 6. Lectura económica

P(pass) 29% ⇒ **3.44 intentos esperados**. Si la evaluación de Lucid 100k es
barata frente al valor de una cuenta fondeada, 3.4 intentos puede ser
económicamente razonable aunque el gate diga FAIL. Esa decisión depende del fee y
del valor esperado de la cuenta, datos que no tengo. **El gate mide el edge, no
la economía del negocio.**

`INFORMATION_STATUS=LUCID100K_V1_FAIL_BY_096PP_EDGE_CONCENTRATED_2025_2026`
