# MULTIINST-V1 Etapa 1 — El edge NO transfiere a ES. Cerrado sin gastar.

Fecha: 2026-07-25 · Preregistro `7a9b5620…` · **Coste: $0.00**

## 1. Veredicto: FAIL (3 de 3 gates)

| Gate | Umbral | Obtenido | |
|---|---|---:|---|
| E1 EV neto > 0 | > 0 | **−0.877** | FAIL |
| E2 Años EV>0 ≥ 2 | ≥ 2 de 3 | **1 de 3** | FAIL |
| E3 PF > 1.15 | > 1.15 | **0.757** | FAIL |

**Consecuencia según el preregistro: no se descargan YM ni RTY. Ahorro $139.29.**

## 2. ES vs NQ, misma regla, FRESH 2024-2026

| | Trades | Trades/mes | WR % | PF | EV neto |
|---|---:|---:|---:|---:|---:|
| **NQ** (referencia) | 177 | 8.43 | 38.98 | 1.156 | **+2.582** |
| **ES** (transferido) | 285 | 9.50 | 32.28 | 0.757 | **−0.877** |

Por año en ES:

| Year | n | WR % | PF | EV neto |
|---|---:|---:|---:|---:|
| 2024 | 112 | 27.68 | 0.682 | −1.295 |
| 2025 | 117 | 32.48 | 0.675 | −1.162 |
| 2026 | 56 | 41.07 | 1.200 | +0.554 |

No es marginal: ES pierde en 2 de 3 años, con PF 0.67-0.68 en los dos primeros.
Y 2025 —año excelente para NQ (+6.59)— es negativo en ES (−1.16). No es cuestión
de régimen compartido: los instrumentos se comportan distinto ante la misma regla.

## 3. El escalado aplicado (preespecificado, sin fitting)

```text
mediana OR en DEV:  NQ = 99.5 ticks   ES = 18.0 ticks
k_ES = 18.0 / 99.5 = 0.1809
(SL, ACT, DIST) NQ = (40, 20, 40)  ->  ES = (7, 4, 7)
```

**Limitación honesta:** un stop de 7 ticks en ES (1.75 puntos) es muy ceñido y
podría estar dominado por ruido de microestructura. No se puede descartar que
otro transform de escalado diera otro resultado. Pero probar más transforms es
exactamente fitting, y el preregistro lo prohíbe. Se reporta como límite del
test, no como excusa.

## 4. Qué queda establecido

**El edge del primer breakout es NQ-específico.** Coincide con la cuarentena
previa de ES (que fue sobre la regla *fade*, regla distinta, misma conclusión).
Dos reglas independientes fallan al transferir al índice más líquido y más
correlacionado con NQ.

Con esto, **la palanca de frecuencia queda cerrada por completo**:

| Vía para subir trades/día | Resultado |
|---|---|
| Multi-entrada en el mismo nivel | FAIL — EV +2.38 → −0.29 |
| Multi-instrumento | FAIL — no transfiere a ES |

## 5. El valor del diseño por etapas

La Etapa 1 costó $0 porque ES ya estaba en disco. Si hubiera descargado YM+RTY
primero, habría gastado $139.29 para llegar a la misma conclusión. El orden
—probar gratis lo que se puede probar gratis— fue lo que ahorró el dinero.

`INFORMATION_STATUS=MULTIINST_STAGE1_FAIL_EDGE_IS_NQ_SPECIFIC_NO_DOWNLOAD`
