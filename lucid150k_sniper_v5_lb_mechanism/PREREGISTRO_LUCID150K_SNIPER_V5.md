# Prerregistro LUCID150K-SNIPER-V5-LB-MECHANISM

Fecha: 2026-07-26  
Orden: ejecutar solo si V4 no llega a HOLDOUT  
Estado: **CONGELADO ANTES DE CALCULAR OUTCOMES V5**

Objetivo: explotar el Liquidity Burst de forma causal para operar NQ, separando
breakout de absorción después de cinco barras completas, con RR inicial 2:1 y
validación para LucidPro 150K en máximo 63 sesiones.

## 0. Separación y contaminación

- El score LB V2 no predijo dirección a +60 s.
- Salir inmediatamente en todo LB mata runners.
- V5 no usa score, etiquetas A/B/C ni el bloque sellado de 29 eventos 2024.
- No usa ningún evento 2024.
- Usa detector idéntico
  `liquidity-burst-detector-2026-07-22-v7-postburst-matrix`:
  - DEV: 2022–2023;
  - PSEUDO_VAL: 2025–2026-06-30.

La clasificación se conoce solo después de observar cinco barras posteriores al
timestamp publicado. No pretende predecir en `t_burst`.

## 1. Universo

Por sesión:

1. eventos entre 09:31:00 y 10:00:00 NY;
2. `Mechanism_Validity == VALID`;
3. `Reference_Type` en `{OR_HIGH, OR_LOW}`;
4. coherencia obligatoria:
   - BUY con OR_HIGH;
   - SELL con OR_LOW;
5. elegir el primer evento elegible por
   `Detector_Publish_Timestamp_UTC`;
6. si queda ambiguo después de cinco barras, no buscar un evento posterior.

Máximo una entrada al día.

Datos de precio: `NQ.c.0 ohlcv-1s`, reloj `America/New_York`, cierre forzado
15:55 NY. Coste round-trip 4 ticks.

## 2. Ventana causal de cinco barras

Sea `t_pub` el publish timestamp. Se toma la primera barra NQ cuyo timestamp sea
mayor o igual al siguiente segundo entero después de `t_pub`, y las cuatro
barras siguientes. Se requieren cinco barras y que la quinta empiece no más de
7 segundos después de `t_pub`.

Referencia `L` = OR_HIGH para BUY, OR_LOW para SELL. Tick NQ = 0.25.

Para cada cierre:

```text
outside BUY  = close >= L + 1 tick
outside SELL = close <= L - 1 tick
inside BUY   = close < L
inside SELL  = close > L
```

Clasificación:

### A — `LB_CONTINUATION_ACCEPTANCE`

```text
outside_count >= 4 de 5
último close sigue outside
```

Entrada en dirección del burst.

### B — `LB_ABSORPTION_RECLAIM`

```text
existe al menos un close inside
último close queda inside por >= 2 ticks
```

Entrada contra el burst.

Los demás patrones son ambiguos y se excluyen.

## 3. Entrada y stop

Entrada = apertura de la primera barra posterior a la quinta observada, con
1 tick de slippage adverso.

Familia A:

```text
stop = midpoint del OR NQ recalculado 09:30–09:31 NY
```

Familia B:

```text
BUY burst / entrada SHORT:
  stop estructural = max(Price_evento, high de 5 barras) + 2 ticks
SELL burst / entrada LONG:
  stop estructural = min(Price_evento, low de 5 barras) - 2 ticks
si riesgo estructural <20 ticks, ampliar a exactamente 20 ticks
```

Ambas se excluyen si riesgo final >80 ticks o <20 ticks.

## 4. Gestión

```text
stop inicial = -1R
target duro = +2R
activar trailing al tocar +1R
stop mínimo al activar = entry + coste (break-even neto)
trailing = mejor extremo favorable - 1R
```

Orden intrabar pesimista: stop heredado, target, actualizar extremo y cambiar
trailing para la barra siguiente. `FIXED_1R` solo diagnóstico. RR inicial 2:1.

## 5. DEV 2022-04-25..2023-12-31

Cada familia debe cumplir:

```text
n >= 18
EV neto > +0.10R
PF > 1.30
2/2 años con EV > 0
>=60% semestres con EV > 0
trailing menos FIXED_1R >= -0.05R
```

Si ambas pasan, avanza la de mayor mediana de EV semestral; empate a 1e-9:
Familia A.

## 6. PSEUDO_VAL 2025-01-01..2026-06-30

Todos:

```text
n >= 18
EV > 0
PF > 1.15
2025 y 2026 con EV > 0
bootstrap IC95 EV, límite inferior > -0.15R
10,000 réplicas, seed 0x9B7C240E15D86AF3
```

Solo PASS DEV + PSEUDO_VAL autoriza construir/adquirir eventos LB del HOLDOUT.

## 7. HOLDOUT y LucidPro 150K

HOLDOUT 2020-01-01..2022-04-22, una sola apertura:

```text
n >= 30
EV > 0
PF > 1.15
>=2 años positivos
bootstrap IC95 EV, límite inferior > -0.05R
```

Simulación oficial:

```text
target +USD 9,000
MLL EOD USD 4,500
floor min(peak_EOD - 4,500, +100)
DLL soft USD 2,700
máximo 63 sesiones
50,000 intentos
budget USD 1,200 / 1,500 / 1,800 según equity <3k / <6k / >=6k
máximo 6 NQ
contracts = floor(budget / ((R_ticks + 4) * USD 5))
```

Gates:

```text
P(pass <=63 sesiones) >= 50%
P(breach antes del pase) <= 20%
mediana condicional al pase <=63 sesiones
```

## 8. Prohibiciones

No usar eventos 2024. No cambiar 5 barras, 4/5, buffers, familias, horarios,
stop, target, trailing, costes o gates después de medir. No elegir evento
posterior si el primero es ambiguo. No añadir score, DOM o lado retrospectivo.
No abrir HOLDOUT si falta un gate.

PASS = candidata a forward, no garantía ni autorización de operación real.

`INFORMATION_STATUS=LUCID150K_SNIPER_V5_PREREGISTERED_NO_RESULT`
