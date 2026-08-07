# Prerregistro del target de régimen post-LB

Fecha: 2026-07-27

ID: `POST_LB_REGIME_TARGET_AUDIT_V1`

Estado: `BEFORE_REAL_REGIME_LABELS`

El objetivo principal pasa a ser el régimen posterior a cada Liquidity Burst.
`SNIPER_SUCCESS`, path efficiency e impulse retention quedan como diagnósticos.

Discovery, validation, holdout y 2025–2026 permanecen sellados.

## Unidad y reloj

Unidad científica: un `LB_ID`. Nunca una fila candidata independiente.

```text
tLB = DetectorPublishTimestamp
reference <= tLB
outcome trades > tLB
```

El LB v7, su lado, umbrales, cooldown y publicación no cambian.

## Referencias

Primaria:

```text
LB_Mid = (BestBid_asof_tLB + BestAsk_asof_tLB) / 2
```

Diagnósticas:

```text
LB_Executable:
    LB BUY  -> BestAsk_asof_tLB
    LB SELL -> BestBid_asof_tLB

LB_LastTrade = price del evento LB congelado
```

Quotes se reconstruyen desde 09:25 NY con el protocolo depth outcome-blind ya
auditado: orden de archivo, watermark causal, clamp <=50 ms, descarte de
updates obsoletos >50 ms y coalescencia por timestamp efectivo.

Referencia válida si el feed depth más reciente no tiene más de 250 ms y el
spread está entre 1 y 4 ticks.

## Movimiento firmado

```text
LB_DIRECTION = +1 BUY, -1 SELL

SignedMoveLB(t) =
    LB_DIRECTION * (TradePrice(t) - ReferencePrice)
```

Sólo trades estrictamente posteriores a `tLB` pueden cruzar un threshold.

## Cruces

Para `k in {4,8,12,16}`:

```text
TimeToContinue_k =
    primer t > tLB con SignedMoveLB(t) >= k

TimeToReverse_k =
    primer t > tLB con SignedMoveLB(t) <= -k
```

Se auditan horizontes `{500,1000,2000,5000,10000}` ms. El horizonte principal
es 5 segundos y no puede cambiar por performance predictiva.

## Etiqueta

Para threshold `k`, horizonte `H` y ventana ambigua `A=250 ms`:

1. `NO_EXPANSION`: ningún lado cruza dentro de `H`.
2. `CONTINUATION`: sólo continuación cruza, o cruza primero por más de `A`.
3. `REVERSAL`: sólo reversión cruza, o cruza primero por más de `A`.
4. `AMBIGUOUS`: ambos cruzan dentro de `H` y la diferencia absoluta entre sus
   primeros cruces es `<=A`, incluido empate exacto.

`AMBIGUOUS` nunca se fusiona con `NO_EXPANSION`.

## Outcomes continuos

Por horizonte y referencia:

- movimiento neto firmado;
- máximo favorable hacia continuación;
- máximo hacia reversión;
- tiempos de ambos cruces;
- primera dirección de expansión;
- diferencia temporal entre cruces;
- `ExpansionDominance`:

```text
(MaxContinue - MaxReverse)
/
(MaxContinue + MaxReverse + epsilon)
```

Nunca son predictors.

## Auditorías

Matriz principal:

```text
threshold 4/8/12/16 × horizon 0.5/1/2/5/10 s
```

Se reporta distribución:

- global;
- BUY/SELL;
- sesión;
- mes;
- año;
- hora.

También:

- transiciones entre horizontes adyacentes;
- acuerdo MID vs EXECUTABLE y MID vs LAST_TRADE;
- sensibilidad de ambigüedad 200/250/300 ms;
- perturbación de threshold `k-1/k+1`;
- perturbación de horizonte 4.5/5.5 s.

## Gates del target

Para cada threshold en el horizonte primario, referencia MID:

- cobertura `>=0.95`;
- cada clase `n>=5`;
- ninguna clase `>0.75`;
- `AMBIGUOUS<=0.25`;
- distancia de variación total BUY/SELL `<=0.15`;
- cada clase aparece en al menos 3 sesiones;
- ninguna sesión concentra más de 0.60 de una clase;
- acuerdo MID/EXECUTABLE `>=0.85`;
- acuerdo de ventanas ambiguas `>=0.90`;
- acuerdo de perturbación threshold `>=0.80`;
- acuerdo de perturbación horizonte `>=0.85`.

Selección fija:

```text
8 -> 12 -> 4 -> 16 ticks
```

Se toma el primer threshold que supera todos los gates. Está prohibido elegir
por AUC, F1, accuracy, PnL, PF o WR.

Resultados permitidos:

```text
TECHNICAL_REGIME_TARGET_CANDIDATE
REGIME_TARGET_INVALID
```

Aunque un candidato pase, discovery sólo puede abrirse después de un
prerregistro final separado con definición y hash.

## Tests sintéticos obligatorios

- continuation BUY;
- continuation SELL;
- reversal tras LB BUY;
- reversal tras LB SELL;
- no expansion;
- bidireccional ambiguo;
- empate temporal;
- expansión tardía;
- trade exactamente en `tLB` ignorado;
- espejo BUY/SELL exacto.

`INFORMATION_STATUS=POST_LB_REGIME_AUDIT_PREREGISTERED_DISCOVERY_SEALED`
