# Preregistro MULTIINST-V1 — ¿el edge del primer breakout transfiere entre instrumentos?

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE MEDIR** (ambas etapas se fijan ahora)

## 0. Hipótesis y diseño por etapas

`multientry_v1` cerró la frecuencia por multi-entrada: el edge vive solo en el
**primer** breakout del día. La única vía restante para subir frecuencia sin
degradarlo es operar el primer breakout de **varios instrumentos**.

**Etapa 1 (COSTE $0):** ES ya está en disco (1,092 días de `ohlcv-1s-full`,
`raw_dbn_es`). Si el edge no transfiere a ES, la hipótesis multi-instrumento
queda gravemente debilitada y **no se gasta un centavo**.

**Etapa 2 (COSTE ~$139.29):** solo si la Etapa 1 pasa. Descarga YM + RTY
(cotización real por `metadata.get_cost`: YM $67.77, RTY $71.52, ventana
13:29-21:05Z, 1,029 días) y evalúa la cartera.

Ambas etapas se congelan ahora para que los gates de la Etapa 2 no puedan
ajustarse después de ver la Etapa 1.

## 1. La regla transferida (idéntica, sin re-optimizar)

```text
entrada  = primer cierre de barra 1s que perfora el OR-high 09:30-09:31,
           SOLO direccion UP, a partir de 13:31:00 UTC
gestion  = trailing (SL, ACT, DIST) = (40, 20, 40) ticks en NQ
comision = 2.0 ticks del instrumento respectivo
```

**Escalado preespecificado, sin fitting.** El rango diario de ES/YM/RTY difiere
del de NQ, así que un stop de 40 ticks NQ no es comparable. Se escala por el
tamaño mediano del OR:

```text
k_X = mediana_OR_ticks(X, DEV) / mediana_OR_ticks(NQ, DEV)
(SL, ACT, DIST)_X = round(40*k_X), round(20*k_X), round(40*k_X)
```

`k_X` se calcula **solo con DEV (2022-2023)** y se aplica congelado a FRESH.
No se barre ningún parámetro por instrumento.

## 2. Split

```text
DEV   = 2022 + 2023    (solo para k_X)
FRESH = 2024 + 2025 + 2026    (disparo unico por instrumento)
```

## 3. Gates

### Etapa 1 — transferencia a ES (los tres, en FRESH)

| # | Criterio | Umbral |
|---|---|---|
| E1 | EV neto | > 0 |
| E2 | Años con EV neto > 0 | ≥ 2 de 3 |
| E3 | Profit Factor | > 1.15 |

PASS → se autoriza la descarga de la Etapa 2. FAIL → **el edge es NQ-específico**,
la hipótesis multi-instrumento se cierra y no se descarga nada.

Nota: la cuarentena previa de ES fue sobre la regla *fade DOWN*, no sobre
*primer-breakout-UP*. Este test es legítimo y distinto.

### Etapa 2 — cartera NQ + ES + YM + RTY (los cuatro, en FRESH)

| # | Criterio | Umbral |
|---|---|---|
| P1 | EV neto combinado (en $ por contrato) | > 0 |
| P2 | Frecuencia combinada | ≥ 20 trades/mes |
| P3 | Payouts esperados (MC Lucid 150k) | > 0.5 |
| P4 | P(quema antes del primer payout) | < 50% |

MC: 10,000 cuentas, target $9,000, MaxLoss $4,500, base 4 contratos, kill-switch
dinámico, seed `0x22f9cadf098b1625`. Los trades de los instrumentos se agrupan
por día (son eventos simultáneos, no secuenciales).

## 4. Prohibiciones

No se re-optimiza SL/ACT/DIST por instrumento. No se elige el subconjunto de
instrumentos que mejor funcione: la cartera es la unión de los que pasen su test
de transferencia individual, decidido por el mismo umbral para todos. No se
excluye ningún año. No se cambia el número de contratos para hacer pasar el MC.
Si la Etapa 1 falla, no se descarga y se cierra.

`INFORMATION_STATUS=MULTIINST_V1_PREREGISTERED_NO_RESULT`
