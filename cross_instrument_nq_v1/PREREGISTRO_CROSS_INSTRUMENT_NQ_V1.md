# Preregistro CROSS-INSTRUMENT-NQ-V1 — ES confirma el breakout UP de NQ

Fecha: 2026-07-25  
Estado: **CONGELADO ANTES DE CALCULAR LOS OUTCOMES EST**

## 0. Hipótesis causal

La transferencia de la estrategia a ES falló. Eso no responde si ES contiene
información contemporánea útil para decidir una operación ejecutada
exclusivamente en NQ.

Hipótesis primaria:

> Cuando NQ hace el primer breakout alcista del OR, el movimiento tiene mayor
> probabilidad de continuación si el último segundo ya cerrado de ES está por
> encima de su propio OR-high. Si ES no confirma, el impulso de NQ es más
> idiosincrático y tiene mayor probabilidad de fallo.

La regla usa un nivel estructural, no un umbral calibrado.

## 1. Datos y bloque no observado

```text
NQ = raw_dbn_2, ohlcv-1s-full, 2022-04-25..2026-07-01
ES = raw_dbn_es, ohlcv-1s-full, fechas emparejadas
timezone = America/New_York
OR = 09:30:00 <= hora NY < 09:31:00
```

Los resultados históricos anteriores omitieron las sesiones en que Nueva York
estaba en EST (UTC-5) por usar 13:30 UTC fijo. Se fija:

```text
PRIMARY_HOLDOUT = sesiones EST omitidas (offset NY = -05:00)
SEEN_EDT        = sesiones EDT ya estudiadas; solo descriptivas
```

El holdout es limpio respecto al outcome de esta estrategia, pero no es un
forward cronológico y representa una estación concreta. Un PASS produce una
candidata, no autorización automática para operar real.

## 2. Entrada y outcome de NQ

```text
señal base = primer breakout del día; solo si UP ocurre antes que DOWN
empate UP/DOWN en la misma barra de 1s = sesión ambigua, excluida
entrada = OR-high de NQ
bracket inicial = TP 60 ticks / SL 60 ticks
salida = primer toque; si ambos ocurren en una barra, gana SL
si no toca ninguno = cierre de la última barra de la sesión
coste primario = 4 ticks round-trip (2 comisión + 2 slippage)
```

Se registra también MAE hasta la salida para simular breaches intradía.

## 3. Señal ES, estrictamente causal

Sea `t_NQ` el timestamp de la barra que dispara el breakout de NQ:

```text
es_confirm = close_ES(t < t_NQ, último segundo cerrado) > OR_high_ES
```

No se usa la barra simultánea de ES, para evitar depender del orden de eventos
dentro del mismo segundo. No se usan datos posteriores a `t_NQ`.

Los dos brazos congelados son:

- `BASE`: todos los primeros breakouts UP de NQ;
- `ES_CONFIRM`: subconjunto con `es_confirm == true`.

No se probarán OR-mid, retorno normalizado, retardos, percentiles ni variantes
de “confirmación” en este disparo.

## 4. Gates sobre PRIMARY_HOLDOUT

### A. Supervivencia del edge base

Todos deben pasar:

| Gate | Umbral |
|---|---:|
| B1 EV neto con coste 4t | > 0 |
| B2 Profit Factor | > 1.10 |
| B3 bloques-año con EV > 0 | >= 3 |
| B4 n | >= 100 |

### B. Valor incremental de ES_CONFIRM

Todos deben pasar:

| Gate | Umbral |
|---|---:|
| C1 EV neto con coste 4t | > 0 |
| C2 Profit Factor | > 1.15 |
| C3 mejora de EV vs BASE | >= +2.0 ticks |
| C4 bloques-año con EV > 0 | >= 3 |
| C5 n | >= 50 |
| C6 IC95 bootstrap del EV de ES_CONFIRM | límite inferior > 0 |

Bootstrap: 10,000 réplicas por trade, seed `0x22f9cadf098b1625`.

Clasificación:

- B PASS + C PASS: edge base sobrevive y ES añade información;
- B PASS + C FAIL: sobrevive el edge base, ES no ayuda;
- B FAIL + C PASS: candidata condicionada a ES, requiere forward;
- B FAIL + C FAIL: línea rechazada.

## 5. LucidPro 150k (compatibilidad, no gate de existencia)

Para BASE y ES_CONFIRM se calcula:

```text
target = +9,000 USD
MLL = 4,500 USD EOD
floor = min(peak_EOD - 4,500, +100)
DLL = 2,700 USD soft
size = 3 NQ
max account duration = ninguna
attempts = 50,000
```

Antes de acreditar el PnL diario se comprueba el MAE del trade contra el piso
vigente. Se reportan `P(pass)`, `P(burn)`, mediana de trades para pasar y meses
estimados usando la frecuencia observada. Criterio operativo indicativo:
`P(pass) >= 30%`.

## 6. Prohibiciones

No se cambia la definición de ES_CONFIRM. No se barren brackets, tamaños ni
costes. No se excluyen años del holdout. No se mezcla EST con EDT para otorgar
PASS. No se descarga RTY/YM antes de cerrar este test gratuito. Un resultado
fallido se documenta sin reintento.

`INFORMATION_STATUS=CROSS_INSTRUMENT_NQ_V1_PREREGISTERED_NO_RESULT`
