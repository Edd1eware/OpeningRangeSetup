# Hipótesis siguientes — Liquidity Burst, multi-instrumento y LucidPro 150k

Fecha: 2026-07-25  
Estado: propuestas; **ninguna es edge validado**

## Prioridad 1 — LB-X1: concordancia ES/NQ en el burst

La V2 demostró que la mecánica MBO de NQ durante los primeros +5 s es estable,
pero no predice el desplazamiento posterior. La hipótesis siguiente cambia la
fuente de información: no intenta volver a representar el mismo libro de NQ.

En el instante del Liquidity Burst `H`, con `sigma=+1 BUY / -1 SELL`:

```text
ES_impulse = sigma * [close_ES(H-1s) - close_ES(09:30:59 NY)]
```

- `ES_impulse > 0`: ES confirma; hipótesis de continuación en NQ.
- `ES_impulse <= 0`: divergencia; hipótesis de reversión en NQ.

La operación sigue siendo exclusivamente NQ. ES es sensor, no instrumento
operado. No hay percentil ni parámetro calibrado.

Endpoint primario forward:

```text
Z60 = +Y60 si ES confirma; -Y60 si diverge
gate: n >= 60, media(Z60) > 0, IC95 bootstrap inferior > 0
```

Gates económicos adicionales: PF > 1.20 con 4 ticks de coste y `P(pass) >= 30%`
en LucidPro 150k. Los 29 casos de 2024 de V2 no se abren: permanecen sellados
según el cierre firmado. Esta hipótesis se prueba en eventos nuevos.

## Prioridad 2 — LB-X2: residual NQ-ES como agotamiento

Un burst puede ser fuerte dentro de NQ pero débil respecto al mercado. Se
propone un endpoint continuo sin umbral:

```text
residual_pre =
  sigma * [ret_NQ(-5s,H)/OR_NQ - ret_ES(-5s,H)/OR_ES]
```

Hipótesis: cuanto mayor sea el residual (NQ más extendido que ES), menor será la
continuación posterior:

```text
rho_Spearman(residual_pre, Y60) <= -0.25
IC95 superior < 0
```

Esto distingue “aceptación de todo el complejo de índices” de “barrido local de
liquidez en NQ”. Debe congelarse sobre datos nuevos; no se ajusta un z-score
contra los 98 eventos ya vistos.

## Prioridad 3 — LB-X3: salida defensiva que preserve runners

`LB-EXIT-V1` mostró:

- ~66% de trades mejoran al salir en LB;
- la media empeora porque se cortan runners grandes.

La hipótesis mecánica resultante no es “salir siempre”, sino:

```text
si hay posición OR abierta
y PnL no realizado <= 0
y ES no confirma la dirección de la posición
entonces salir en LB;
en cualquier otro caso, mantener el trailing original.
```

La condición busca recortar únicamente trades que todavía no son runners. No se
prueba sobre los mismos 87 casos de LB-EXIT-V1; queda forward-only.

## Prioridad 4 — amplitud ES+RTY+YM

Si LB-X1 confirma señal con ES, se puede ampliar a un breadth score estructural:

```text
breadth = número de {ES, RTY, YM} alineados con sigma, rango 0..3
hipótesis: Y60 crece monótonamente con breadth
```

No se elige el mejor subconjunto. Se usarían los tres instrumentos y NQ seguiría
siendo el único ejecutado. Descargar RTY/YM antes de validar ES no está
justificado: la Etapa 1 previa ya mostró que transferir la estrategia a ES
fallaba, y la cotización existente de YM+RTY ronda $198.

## Validación histórica opcional de ES→NQ OR

Para resolver ahora la señal positiva pero infra-potenciada de
`CROSS-INSTRUMENT-NQ-V1`, se cotizó exactamente:

```text
rango       = 2020-01-01..2022-04-22
instrumentos= NQ.c.0 + ES.c.0
schema      = ohlcv-1s
ventana     = 09:25..16:05 America/New_York por día hábil
días        = 603
coste       = USD 90.45
errores quote= 0
```

Tamaño: el rango completo 24 h cotizado por Databento es 2.82 GiB billable; la
ventana exacta RTH cuesta 45.9% de ese total, por lo que se espera ~1.3 GiB
billable y bastante menos comprimido. Se impondrá un cap local de 3 GB y una
reserva mínima de 80 GB libres.

La compra solo tiene sentido con un preregistro de disparo único idéntico a V1:
ES por encima de su OR-high, NQ 60/60, coste 4t, sin variantes. No se descarga
hasta recibir autorización explícita para el cargo de $90.45.

## Vehículo Lucid

El objetivo se modela como **LucidPro 150k**:

```text
target 9,000 | MLL 4,500 EOD | lock del piso en 150,100
DLL 2,700 soft | sin expiración | máximo 10 NQ / 100 MNQ
```

El tamaño candidato de investigación es 3 NQ (o 30 MNQ equivalentes) con riesgo
nominal de ~$960 por stop incluyendo 4 ticks de coste. No se propone usar el
máximo de 10 contratos. El sizing no rescata una señal sin edge; solo se evalúa
después de que EV/PF/estabilidad pasen.

`INFORMATION_STATUS=NEXT_HYPOTHESES_PREREGISTRATION_REQUIRED`
