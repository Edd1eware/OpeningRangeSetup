# Preregistro LUCID150K-SNIPER-V1

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE CALCULAR LAS DOS ENTRADAS**

## 0. Alcance y separación de V2

Este estudio responde al objetivo directo del usuario:

> Encontrar una entrada reproducible para operar NQ y pasar una evaluación
> LucidPro 150k, con riesgo/recompensa inicial mínimo 1:1 y gestión trailing.

Es independiente de la clasificación Liquidity Burst A/B/C. No usa ni abre:

- los 29 eventos V2-2024 sellados;
- el score mecánico V2;
- etiquetas A/B/C;
- MBO del protocolo maestro.

## 1. Datos y reloj

```text
NQ = NQ.c.0 ohlcv-1s
ES = ES.c.0 ohlcv-1s
timezone = America/New_York
OR = [09:30:00, 09:31:00)
última entrada = 10:00:00 NY
cierre forzado = 15:55:00 NY
```

Toda decisión cross-market usa únicamente barras ES con timestamp
**estrictamente anterior** al segundo de la decisión NQ.

Bloques:

```text
DEV         = 2022-04-25..2023-12-31
PSEUDO_VAL  = 2024-01-01..2024-12-31
STRESS_SEEN = 2025-01-01..2026-07-01, solo descriptivo
HOLDOUT     = 2020-01-01..2022-04-22, no descargado al congelar
```

DEV/PSEUDO_VAL ya han sido usados por otras investigaciones; sirven para
selección y falsificación temprana, no para validación definitiva. HOLDOUT se
abre una sola vez únicamente si una familia pasa DEV y PSEUDO_VAL.

## 2. Costes y restricciones de ejecución

```text
tick NQ = 0.25
coste round-trip = 4 ticks
1 tick NQ = USD 5 por contrato
rango de riesgo permitido = 20..80 ticks
máximo = 1 trade por sesión
```

El rango 20–80 no se ajusta al resultado:

- debajo de 20t, 4t de coste consume al menos 20% del riesgo;
- encima de 80t, 3 NQ arriesgarían más de USD 1,260 incluyendo costes.

## 3. Familia S1 — `ES_LEADS_NQ_BREAKOUT`

Hipótesis: si ES acepta fuera de su OR antes que NQ, el breakout posterior de NQ
es una reacción rezagada y tiene mejor continuación.

Regla:

1. Mientras NQ no haya perforado ninguno de sus límites OR:
   - armar LONG si el último cierre ES completo está sobre `ES_OR_high`;
   - armar SHORT si está bajo `ES_OR_low`.
2. Entrada stop:
   - LONG en `NQ_OR_high + 1 tick`;
   - SHORT en `NQ_OR_low - 1 tick`.
3. El lado opuesto de NQ antes de la entrada invalida la sesión.
4. Stop inicial = midpoint del OR de NQ.
5. `R = distancia entrada-stop`; operar solo si `20 <= R <= 80`.

No se exige volumen, retest, LB, tendencia ni umbral adicional.

## 4. Familia S2 — `NQ_DIVERGENCE_RECLAIM`

Hipótesis: una primera perforación NQ que ES no confirma y que vuelve
inmediatamente al OR es un falso breakout operable en reversión.

Regla:

1. Detectar la primera perforación NQ:
   - sweep UP: `high >= OR_high + 1 tick`;
   - sweep DOWN: `low <= OR_low - 1 tick`;
   - ambos en el mismo segundo = ambiguo, excluir.
2. En el último segundo ES completo anterior al sweep:
   - UP no confirmado si `ES_close <= ES_OR_high`;
   - DOWN no confirmado si `ES_close >= ES_OR_low`.
3. Dentro de los siguientes 15 segundos:
   - UP reclaim: primer cierre NQ `< OR_high`; entrar SHORT;
   - DOWN reclaim: primer cierre NQ `> OR_low`; entrar LONG.
4. Entrada = apertura de la siguiente barra disponible, con 1 tick de slippage
   adverso.
5. Stop = extremo del sweep hasta el reclaim + 2 ticks.
6. `R = distancia entrada-stop`; operar solo si `20 <= R <= 80`.

No se prueba otra ventana de reclaim ni otro buffer.

## 5. Gestión única — `RR2_TRAIL_1R`

La misma gestión se aplica a S1 y S2:

```text
stop inicial = -1R
target duro = +2R              (RR inicial 2:1)
activación trailing = +1R
al activar:
  stop mínimo = entrada + coste (break-even neto)
  trailing = mejor extremo favorable - 1R
cierre forzado = 15:55 NY
```

Regla intrabar pesimista sobre OHLCV-1s:

1. comprobar el stop heredado;
2. comprobar target;
3. actualizar mejor extremo;
4. activar/actualizar trailing para la barra siguiente.

Como diagnóstico obligatorio se calcula también `FIXED_1R` (TP=SL=R), pero
**no puede ser seleccionado**. Solo determina si el trailing destruye valor.

## 6. Selección en DEV

Cada familia debe pasar todos:

| Gate | Umbral |
|---|---:|
| D1 n | >= 40 |
| D2 EV neto | > +0.05R |
| D3 Profit Factor | > 1.20 |
| D4 años con EV > 0 | 2 de 2 |
| D5 semestres con EV > 0 | >= 60% |
| D6 trailing vs FIXED_1R | diferencia EV >= -0.05R |

Si ambas pasan, avanza la de mayor mediana de EV semestral. Empate a 1e-9:
avanza S1. Si ninguna pasa, estudio FAIL y no se descarga HOLDOUT.

## 7. Gate PSEUDO_VAL

La familia elegida se aplica sin cambios:

| Gate | Umbral |
|---|---:|
| V1 n | >= 20 |
| V2 EV neto | > 0 |
| V3 PF | > 1.10 |
| V4 bootstrap IC95 EV | límite inferior > -0.10R |

Bootstrap por trade, 10,000 réplicas,
seed `0x22f9cadf098b1625`.

Un fallo detiene la descarga.

## 8. HOLDOUT único 2020–abril 2022

Solo si DEV y PSEUDO_VAL pasan. Datos autorizados:

```text
NQ+ES ohlcv-1s
09:25..16:05 America/New_York por día
coste máximo = USD 90.45
cap local = 3 GB
reserva mínima C: = 80 GB libres
```

Gates, todos:

| Gate | Umbral |
|---|---:|
| H1 n | >= 40 |
| H2 EV neto | > 0 |
| H3 PF | > 1.15 |
| H4 años con EV > 0 | >= 2 |
| H5 bootstrap IC95 EV | límite inferior > -0.05R |
| H6 `P(pass)` LucidPro 150k | >= 30% |

PASS = candidata para forward, no autorización de operar real.

## 9. Simulador LucidPro 150k

```text
target = +USD 9,000
MLL = USD 4,500 EOD
floor = min(peak_EOD - 4,500, +100)
DLL = USD 2,700 soft
sin expiración
max size = 10 NQ
risk budget = USD 900 por trade
contracts = min(3, floor(900 / ((R_ticks + 4) * 5)))
si contracts < 1: no trade
```

La simulación usa PnL y MAE intratrade, 50,000 intentos bootstrap. No modela
varios trades diarios porque la estrategia permite uno.

## 10. Prohibiciones

No barrer OR, reclaim, buffers, R, trailing, target, horarios ni costes. No
añadir filtros de meses/noticias/dirección. No elegir FIXED_1R. No abrir
HOLDOUT si falta un gate anterior. No repetir HOLDOUT con una segunda familia.

`INFORMATION_STATUS=LUCID150K_SNIPER_V1_PREREGISTERED_NO_RESULT`
