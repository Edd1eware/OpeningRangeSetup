# Prerregistro LUCID150K-SNIPER-V2

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE CALCULAR LAS DOS ENTRADAS V2**

Objetivo explícito incorporado antes de ejecutar: **evaluación LucidPro 150K
pasada en un máximo de 63 sesiones (~3 meses)**.

## 0. Motivación y separación

V1 falsificó:

- perseguir el primer breakout NQ solo porque ES salió antes;
- desvanecer el primer sweep/reclaim NQ no confirmado por ES.

V2 prueba mecanismos distintos, no filtros retrospectivos de V1:

1. aceptación NQ + retest mientras ES sigue confirmado;
2. reclaim fallido + rebreak cuando ES pasa de no confirmar a confirmar.

No se eligen meses, lados, volatilidades ni subgrupos vistos. V2 es
independiente de Liquidity Burst A/B/C y no toca los 29 eventos V2-2024, el
score LB ni MBO.

## 1. Datos, bloques y causalidad

```text
NQ = NQ.c.0 ohlcv-1s
ES = ES.c.0 ohlcv-1s
timezone = America/New_York
OR = [09:30:00, 09:31:00)
scan = 09:31:00..10:00:00
force exit = 15:55:00
```

Para toda decisión NQ solo se permite el último cierre ES con timestamp
estrictamente anterior al segundo de decisión.

```text
DEV         = 2022-04-25..2023-12-31
PSEUDO_VAL  = 2024
STRESS_SEEN = 2025..2026-07-01, descriptivo
HOLDOUT     = 2020-01-01..2022-04-22, cerrado
```

## 2. Costes y gestión común

```text
tick NQ = 0.25
coste round-trip = 4 ticks
riesgo válido = 20..80 ticks
máximo = 1 trade por familia y sesión
entrada next-open = 1 tick de slippage adverso
stop inicial = -1R
target duro = +2R
activar trailing al tocar +1R
stop mínimo al activar = entry + coste (break-even neto)
trailing = mejor extremo favorable - 1R
```

Orden OHLCV-1s pesimista:

1. stop heredado;
2. target;
3. actualizar extremo favorable;
4. activar/actualizar trailing para el segundo siguiente.

Se calcula `FIXED_1R` solo como diagnóstico y no puede seleccionarse.

## 3. Familia A — `CROSS_ACCEPTANCE_RETEST`

Hipótesis: el primer rompimiento es operable solo después de aceptación NQ y
un retest defendido, mientras ES conserva aceptación en el mismo sentido.

Regla:

1. Buscar los primeros **dos cierres NQ consecutivos**:
   - LONG: ambos `close >= NQ_OR_high + 1 tick`;
   - SHORT: ambos `close <= NQ_OR_low - 1 tick`.
2. En el segundo cierre, el último ES completo debe confirmar:
   - LONG: `ES_close >= ES_OR_high + 1 tick`;
   - SHORT: `ES_close <= ES_OR_low - 1 tick`.
3. Desde el segundo siguiente y por hasta 120 segundos, buscar el primer
   retest defendido:
   - LONG: `low <= NQ_OR_high` y `close >= NQ_OR_high + 1 tick`;
   - SHORT: `high >= NQ_OR_low` y `close <= NQ_OR_low - 1 tick`.
4. En el retest, el último cierre ES completo debe seguir confirmando con el
   mismo umbral de 1 tick.
5. Si NQ cierra más allá del límite opuesto antes del retest, invalidar.
6. Entrada = apertura de la siguiente barra disponible + 1 tick adverso.
7. Stop = midpoint del OR NQ.
8. Operar solo si `20 <= R <= 80`.

No se prueba otra cantidad de cierres, ventana o buffer.

## 4. Familia B — `FAILED_RECLAIM_CROSS_REBREAK`

Hipótesis: el primer sweep NQ no confirmado que vuelve al OR puede atrapar a
los faders; el edge de continuación aparece si NQ rompe nuevamente el extremo
del sweep cuando ES finalmente confirma.

Regla:

1. Detectar la primera perforación NQ:
   - UP: `high >= NQ_OR_high + 1 tick`;
   - DOWN: `low <= NQ_OR_low - 1 tick`;
   - ambos en el mismo segundo = excluir.
2. El último ES completo debe **no confirmar**:
   - UP: `ES_close < ES_OR_high + 1 tick`;
   - DOWN: `ES_close > ES_OR_low - 1 tick`.
3. Dentro de 15 segundos, exigir reclaim:
   - UP: primer `close < NQ_OR_high`;
   - DOWN: primer `close > NQ_OR_low`.
4. Congelar el extremo del sweep observado desde su inicio hasta el reclaim.
5. Desde el segundo posterior al reclaim y durante 120 segundos, exigir:
   - UP: `NQ_close >= sweep_high + 1 tick` y último
     `ES_close >= ES_OR_high + 1 tick`;
   - DOWN: `NQ_close <= sweep_low - 1 tick` y último
     `ES_close <= ES_OR_low - 1 tick`.
6. Entrada = apertura de la siguiente barra + 1 tick adverso en dirección del
   sweep.
7. Stop = extremo adverso NQ observado desde el reclaim hasta el rebreak,
   más 2 ticks de buffer.
8. Operar solo si `20 <= R <= 80`.

No se prueba rebreak sin confirmación ES, otra ventana o buffer.

## 5. Gates DEV

Cada familia debe cumplir todos:

| Gate | Umbral |
|---|---:|
| D1 n | >= 40 |
| D2 EV neto | > +0.05R |
| D3 PF | > 1.20 |
| D4 años positivos | 2/2 |
| D5 semestres positivos | >= 60% |
| D6 trailing menos FIXED_1R | >= -0.05R |

Si ambas pasan, avanza la de mayor mediana de EV semestral; empate a 1e-9:
Familia A.

## 6. PSEUDO_VAL y HOLDOUT

PSEUDO_VAL, todos:

```text
n >= 20
EV > 0
PF > 1.10
bootstrap IC95 EV, límite inferior > -0.10R
10,000 réplicas, seed 0x5F06A76E51C2D94B
```

Solo si DEV y PSEUDO_VAL pasan se permite descargar/abrir HOLDOUT.

HOLDOUT, todos:

```text
n >= 40
EV > 0
PF > 1.15
>= 2 años con EV > 0
bootstrap IC95 EV, límite inferior > -0.05R
P(pass LucidPro 150K dentro de 63 sesiones) >= 50%
P(breach antes de 63 sesiones) <= 20%
mediana de sesiones al pase, condicionada a pasar, <= 63
```

PASS final significa candidato a forward, no autorización para operar real.

## 7. Simulador LucidPro

Se conserva sin cambios:

```text
target = +USD 9,000
MLL EOD = USD 4,500
floor relativo = min(peak_EOD - 4,500, +100)
DLL soft = USD 2,700
evaluación = LucidPro 150K
horizonte de validación = máximo 63 sesiones
risk budget = USD 900/trade
contracts = min(3, floor(900 / ((R_ticks + 4) * 5)))
50,000 intentos bootstrap usando PnL y MAE
```

## 8. Prohibiciones

No barrer parámetros, OR, ventanas, buffers, costes, target, trailing, meses,
dirección ni volatilidad después de ver V2. No seleccionar FIXED_1R. No abrir
HOLDOUT si falta un gate anterior. Una familia fallida se cierra y no se
rescata con subgrupos.

`INFORMATION_STATUS=LUCID150K_SNIPER_V2_PREREGISTERED_NO_RESULT`
