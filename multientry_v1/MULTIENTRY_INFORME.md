# MULTIENTRY-V1 — La palanca de frecuencia está CERRADA

Fecha: 2026-07-25 · Preregistro `a784adf3…` · Disparo único sobre FRESH

## 1. Veredicto: FAIL (1 de 6 gates)

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| G1 EV neto > 0 | > 0 | **−0.294** | FAIL |
| G2 PF > 1.15 | > 1.15 | **0.983** | FAIL |
| G3 Años EV>0 ≥ 2 | ≥ 2 de 3 | **1 de 3** | FAIL |
| G4 Frecuencia ≥ 20/mes | ≥ 20 | **53.27** | PASS |
| G5 Payouts esperados > 0.5 | > 0.5 | **0.170** | FAIL |
| G6 Quema sin payout < 50% | < 50% | **85.5%** | FAIL |

## 2. El resultado central: la frecuencia se logró y destruyó el edge

| Configuración | Trades/mes | EV neto |
|---|---:|---:|
| 1 trade/día (primer breakout, UP) | 8.4 | **+2.38** |
| 3.26 trades/día (todos los cruces, UP) | 53.3 | **−0.29** |

Se multiplicó la frecuencia por 6.3× y el EV pasó de positivo a negativo.

## 3. Confound descartado: no es el trailing

La versión multi-entrada usa trailing 40/20/40 y la de 1 trade/día usaba
50/20/40. Comprobado con **la misma gestión** (datos ya calculados en
`upbias_v2\output\PARTE_A_RESULT.json`):

| Gestión | 1 trade/día (UP) | 3.26 trades/día (UP) |
|---|---:|---:|
| trail_40_20_40 | **+3.166** | **−0.294** |
| trail_50_20_40 | +2.732 | — |

Mismo trailing, misma dirección, mismo instrumento, mismo periodo. **La única
diferencia son las entradas adicionales**, y son las que destruyen el resultado.

## 4. Qué significa

**El edge vive exclusivamente en el PRIMER breakout del día.** Las reentradas
tras volver dentro del rango, y las reversiones tras fallo bajista, tienen EV
negativo y arrastran la media por debajo de cero.

Tiene sentido estructural: el primer cruce del OR-high es el evento —la
resolución de la apertura—. Los cruces posteriores son el mismo nivel ya
digerido; operar ahí es perseguir.

Detalle: el filtro anti-absorción (umbral p66 calculado **solo en DEV**, no
full-sample como en el script original) mejora de −0.642 a −0.294. Ayuda, pero no
salva. Y DEV ya era negativo (−1.563): la configuración perdía también dentro de
muestra.

## 5. La aritmética que cierra el caso Lucid 150k

Con lo mejor que tenemos —primer breakout, UP-only, trail 40/20/40:

```text
EV +3.17 ticks x 8.4 trades/mes = ~27 ticks/mes
27 ticks x $5 x 4 contratos     = ~$530/mes
target $9,000                   -> ~17 meses hasta el primer payout
MaxLoss $4,500                  = 225 ticks de drawdown con 4 contratos
```

Un edge que tarda 17 meses en alcanzar el target, contra un límite de pérdida que
se toca en semanas, **no puede farmear payouts**. No es cuestión de afinar: es
aritmética.

## 6. Qué queda cerrado y qué no

**Cerrado:** la palanca de frecuencia por multi-entrada en el mismo nivel. No se
prueban otros percentiles del filtro, ni otros SL/ACT/DIST, ni la versión sin
filtro: el preregistro lo prohíbe y el resultado no es marginal.

**No probado (observación honesta, no resultado):** la frecuencia podría subir
**sin degradar el edge** operando el *primer* breakout de **varios instrumentos**
en paralelo, en lugar de varias entradas del mismo. Cada instrumento aportaría su
propio evento estructural. La cuarentena de ES fue sobre la regla *fade*, no
sobre *primer-breakout-UP*, así que no está descartado por la evidencia actual.
Requeriría su propio preregistro y datos de otros instrumentos.

`INFORMATION_STATUS=MULTIENTRY_REJECTED_EDGE_IS_FIRST_BREAKOUT_ONLY`
