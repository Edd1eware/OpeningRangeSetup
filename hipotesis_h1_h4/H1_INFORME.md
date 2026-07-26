# H1 — Sesgo estructural UP: RECHAZADA (4 de 5 gates)

Fecha: 2026-07-25 · Preregistro `f5fa1d4b…` · Disparo único sobre FRESH 2024-26

## Veredicto: FAIL — pero es el fallo más cercano del proyecto

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| G1 EV neto > 0 | > 0 | **+2.379** | PASS |
| G2 PF > 1.15 | > 1.15 | **1.137** | **FAIL** |
| G3 Años EV>0 ≥ 2 | ≥ 2 de 3 | **2 de 3** | PASS |
| G4 Frecuencia ≥ 4/mes | ≥ 4 | **8.43** | PASS |
| G5 Supera baseline | > −0.577 | **+2.379** | PASS |

Falla **solo por PF, y por 0.013**. Por el preregistro eso es rechazo y no se
toca el umbral. Pero hay que decir lo que muestra la tabla.

## FRESH: solo UP vs ambas direcciones

| | Trades | Trades/mes | WR % | PF | EV bruto | EV neto |
|---|---:|---:|---:|---:|---:|---:|
| Baseline ambas | 402 | 18.27 | 39.30 | 0.970 | +1.42 | **−0.58** |
| **Solo UP** | 177 | 8.43 | 41.81 | 1.137 | +4.38 | **+2.38** |

Diferencia de **~3 ticks netos por trade**, conservando 8.4 trades/mes. Es la
primera vez en el proyecto que algo entrega EV neto positivo en holdout temporal
con frecuencia operable.

## Desglose por año (FRESH, solo UP)

| Year | Trades | Trades/mes | WR % | PF | EV bruto | EV neto |
|---|---:|---:|---:|---:|---:|---:|
| 2024 | 64 | 7.11 | 32.81 | 0.747 | −3.00 | **−5.00** |
| 2025 | 76 | 9.50 | 44.74 | 1.328 | +7.20 | **+5.20** |
| 2026 | 37 | 9.25 | 51.35 | 1.585 | +11.35 | **+9.35** |

**2024 es el único año que rompe el gate.** Sin 2024 el PF sería holgadamente
superior a 1.15. Pero excluir 2024 está explícitamente prohibido y sería el
autoengaño clásico: 2024 existe y volverá.

Nota: el WR sube monótonamente 32.8 → 44.7 → 51.4 y el PF con él. Puede ser
mejora estructural o puede ser que 2025-26 sean régimen favorable. No se puede
distinguir con estos datos.

## Caveat de contaminación (declarado en el preregistro)

El split UP/DOWN se observó full-sample mientras verificaba la semántica del
dataset, antes de preregistrar. H1 es por tanto una hipótesis *generada por
observación*. Mitigación: cero parámetros libres — no hay nada que ajustar, solo
sobrevivir o no el holdout. Aun así el resultado debe leerse con esa reserva.

## Lectura

El sesgo alcista del follow-through **existe y es económicamente grande**, pero
no es suficiente por sí solo para superar el estándar congelado, porque en
régimen de chop (2024) sigue perdiendo −5 ticks netos por trade.

Esto no invalida H1 como fenómeno: lo que dice es que **H1 necesita a H2**. El
sesgo direccional resuelve *qué lado operar*; no resuelve *cuándo no operar*.

## Encadenamiento (regla fijada antes de correr)

H1 falló → por preregistro, **H2 se aplica sobre ambas direcciones**, no sobre
solo-UP. Se respeta aunque solo-UP sea económicamente mejor: cambiar la regla
ahora sería exactamente el sesgo que el protocolo previene.

`INFORMATION_STATUS=H1_REJECTED_BY_GATE`
