# 06 — Replicación independiente del turn of month, en 33 años y cuatro instrumentos

Fecha: 2026-10-13. Scripts: `42_tom_independent_replication.py`, más el refinamiento en scratchpad.
Reportes: `tom_independent_replication.csv`, `tom_corrected_window.csv`. **Costo: cero.**

## Por qué buscar fuera

El candidato de la nota 05 vive en 32 días de un año parcial de NQ. Comprar más historia de NQ ensancha esa
muestra pero sigue siendo el mismo instrumento, el mismo venue y la misma época. La pregunta previa, que es la
que importa primero, es si la anomalía existe **en absoluto** en un tramo lo bastante largo para que la suerte
no la explique. Y eso se puede contestar sin pagar nada: las barras diarias de SPY van a 1993.

Las barras diarias no pueden validar el bracket de 300 ticks, porque no tienen ruta. Pero sí contestan si el
efecto está ahí.

## El efecto clásico, agrupado, NO es significativo

Ventana clásica de la literatura: último día hábil del mes más los tres primeros del siguiente.

| | SPY (8,483 sesiones, 1993-2026) | QQQ (6,941, 1999-2026) |
|---|---|---|
| turn of month vs resto | t=+1.59, **p=0.1124** | t=+1.15, p=0.2485 |
| placebo, ventana +5 días | t=−1.36, p=0.1745 | t=−1.54, p=0.1229 |
| lunes (control negativo) | t=+0.94, p=0.3471 | t=+0.93, p=0.3548 |

Treinta y tres años y no llega. El control del lunes sale nulo, que es lo que debe pasar en futuros de índice y
sirve de prueba de que la medición no está fabricando efectos.

## La descomposición pre-registrada rechaza una de sus cuatro celdas

El script 41 ya traía escrito, antes de correr nada, que *"la literatura pone el efecto en el último día del mes
y los primeros dos o tres del siguiente"*. Esa descomposición es la que decidió:

| posición | SPY media | SPY t | SPY WR | QQQ media | QQQ t | QQQ WR |
|---|---:|---:|---:|---:|---:|---:|
| **último día del mes** | **−0.0840%** | **−1.83** | **0.4360** | **−0.0920%** | −1.39 | **0.4277** |
| +1 | +0.1165% | +2.37 | 0.5654 | +0.0404% | +0.49 | 0.5361 |
| +2 | +0.0625% | +1.34 | 0.5630 | +0.0699% | +0.74 | 0.5542 |
| +3 | +0.0683% | +1.57 | 0.5827 | +0.1495% | +1.83 | 0.5693 |

**El último día del mes es negativo en los dos instrumentos**, con win rate de 0.43-0.44. La ventana clásica lo
incluía y por eso el efecto agrupado no llegaba: se estaba promediando con un día que activamente resta.

Esto importa para la contabilidad de multiple testing y conviene dejarlo claro: **no es una ventana escogida
después de ver la respuesta.** La descomposición estaba declarada de antemano, y fue ella la que rechazó una de
sus propias celdas, sobre datos que este proyecto nunca compró ni tocó.

## La ventana corregida: días +1, +2, +3

| símbolo | sesiones | n | media | t | p | WR | placebo t | placebo p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **SPY** | 8,483 | 1,215 | +0.0824% | **+3.01** | **0.0027** | 0.5704 | +0.32 | 0.7514 |
| QQQ | 6,941 | 996 | +0.0866% | +1.91 | 0.0565 | 0.5532 | +0.37 | 0.7102 |
| **DIA** | 7,227 | 1,038 | +0.0760% | **+2.51** | **0.0123** | 0.5645 | +0.26 | 0.7977 |
| IWM | 6,633 | 953 | +0.0225% | +0.83 | 0.4072 | 0.5373 | −0.20 | 0.8416 |

Dos de cuatro pasan Bonferroni con α=0.0125. Los cuatro placebos salen limpios, con p entre 0.71 y 0.84, que es
exactamente lo que debe pasar si el efecto es del calendario y no deriva de mercado que la ventana alcanzó a
muestrear.

Por década:

| década | SPY t | SPY WR | QQQ t | QQQ WR | DIA t | DIA WR | IWM t | IWM WR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1990 | +2.64 | 0.5944 | — | — | +1.60 | 0.5417 | — | — |
| 2000 | +0.73 | 0.5528 | +0.58 | 0.5250 | +1.37 | 0.5833 | −0.02 | 0.5447 |
| 2010 | +0.99 | 0.5472 | +1.09 | 0.5278 | +0.29 | 0.5222 | −0.32 | 0.4944 |
| **2020** | **+2.52** | **0.6057** | **+2.11** | **0.6382** | **+2.57** | **0.6057** | +1.50 | 0.5894 |

No es una anomalía que decayó: fuerte en los noventa, floja en los 2000 y 2010, y **fuerte otra vez en los
2020 en los cuatro instrumentos**, con win rates de 0.589 a 0.638. Eso converge con el WR de 0.67 medido en NQ
2026, que era el candidato original.

## Lo que esto NO prueba

1. **SPY, QQQ, DIA e IWM están muy correlacionados.** "Dos de cuatro significativos" no son cuatro pruebas
   independientes; efectivamente hay como una observación y media. La corrección de Bonferroni que apliqué es
   por lo tanto **demasiado benévola en la estructura y demasiado severa en el conteo** al mismo tiempo.
2. **La década 2020 siendo la más fuerte es una celda de cuatro.** Que destaque puede ser régimen real o puede
   ser selección entre décadas. Lo que no es selección es el resultado agrupado de SPY en 33 años, p=0.0027.
3. **Esto mide la media de apertura a cierre, no un bracket.** Un efecto de +0.08% es, sobre NQ en 25,000, unos
   20 puntos o 80 ticks, contra 1.8 ticks de costo. Es grande respecto al costo. Pero un bracket simétrico de
   300 ticks resuelve antes y su win rate es otro número, que es lo que mide el script 41 sobre NQ.
4. **IWM, el de small caps, sale nulo.** Si el mecanismo fuera el flujo de aportaciones a fondos de retiro a
   principio de mes, debería aparecer también ahí. No aparece, y no tengo explicación.

## Qué queda y por qué ahora es una predicción, no un ajuste

El script 41 ya quedó cableado con la ventana corregida +1..+3, dejando la clásica como fila de comparación.
Aplicarla a NQ es ahora una **predicción traída desde datos independientes**, y eso es la diferencia entre una
prueba y un ajuste de curva: si NQ 2021-2024 no la confirma, el candidato muere, y no hay grado de libertad
disponible para rescatarlo.

Nota de tensión honesta: en NQ 2026 la ventana corregida da WR 0.6667 con n=24 y la clásica 0.6875 con n=32, es
decir que en NQ el último día **no** restó. Con n=8 en ese día no hay información, pero si tras la descarga el
último día de NQ sigue siendo positivo mientras en los cuatro ETFs es negativo, eso es una inconsistencia que
hay que explicar y no barrer.
