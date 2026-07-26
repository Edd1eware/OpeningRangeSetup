# CODEX_CONTEXT — Post-V2: auditoría DST/Lucid y señal ES→NQ

Fecha: 2026-07-25  
Autor: Codex  
Estado: **EVIDENCIA PARA REVISIÓN; SIN AUTORIZACIÓN DE AMPLIAR**

## 1. Nuevo objetivo del usuario

El usuario pidió continuar formulando hipótesis del Liquidity Burst, explorar
señales multi-instrumento ejecutadas exclusivamente en NQ y orientar el trabajo
a pasar cuentas Lucid de 150k. Autorizó considerar nuevas descargas, con límite
aproximado de 100 GB libres.

## 2. Dos defectos metodológicos detectados

### 2.1 OR 09:30 fijado erróneamente en 13:30 UTC

Los scripts históricos usan `13:30 UTC` todo el año y lo llaman `09:30 NY`.
Durante EST la apertura es `14:30 UTC`.

Evidencia:

```text
raw_dbn_2 fechas = 1,029
orb_trailing_pnl filas = 698
meses en CSV: dic=0, ene=0, feb=0, nov=8
archivo NQ 2025-01-06:
  índice UTC; 13:30-13:31 = 0 barras; 14:30-14:31 = 60 barras
```

Conclusión factual: los informes OR describen como 2022-2026 una muestra casi
exclusivamente EDT. Sus resultados siguen siendo reproducibles en ese
subconjunto, pero no cubren el año.

Corrección propuesta: convertir UTC a `America/New_York` y definir el OR por
09:30 local.

### 2.2 Monte Carlo Lucid no implementa el lock del MLL

Los simuladores previos usan `floor = peak - MLL` para siempre y algunos imponen
120 días. LucidPro vigente:

```text
150k: target 9,000 | MLL 4,500 | DLL 2,700 soft | max 10 NQ
floor relativo = min(peak_EOD - 4,500, +100)
sin expiración
```

En el pool ya visto de fixed60/60 UP-only, 3 NQ:

```text
sim anterior ~= 29.7% pass
sim con lock oficial ~= 36.8% pass
```

Esto no valida el edge; demuestra que las probabilidades anteriores eran
pesimistas.

## 3. Exploración unilateral ES→NQ ya ejecutada

Nota de gobernanza: esta exploración se ejecutó antes de releer
`README_GOBERNANZA_CODEX_CLAUDE.md`. Por tanto **no se presenta como experimento
convergente ni como autorización de operar/ampliar**. Se conserva porque produjo
una auditoría reproducible y abrió datos EST antes no analizados.

Regla congelada antes de calcular EST:

```text
NQ primer breakout UP, bracket 60/60
coste 4 ticks
ES_CONFIRM = último segundo ES estrictamente anterior a entrada NQ
             cierra por encima del OR-high de ES
primary = sesiones EST omitidas
```

Resultados:

| Brazo EST | n | EV neto | PF | años + | P(pass) LucidPro 150k |
|---|---:|---:|---:|---:|---:|
| BASE | 165 | -1.45t | 0.953 | 2 | 14.60% |
| ES_CONFIRM | 26 | +5.23t | 1.193 | 3 | 39.42% |

ES_CONFIRM mejora +6.69t, pero:

```text
IC95 bootstrap EV = [-17.85, +28.31]
2026 EV = -40t, n=5
gates formales: FAIL por n<50 e IC95_low<=0
```

Clasificación honesta: efecto prometedor, infra-potenciado e inestable; no edge.

Control: la reconstrucción DST-aware reproduce exactamente las 177 operaciones
EDT 2024-2026 del estudio anterior.

Artefactos:

```text
C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\cross_instrument_nq_v1
```

## 4. Hipótesis LB multi-instrumento propuestas, no ejecutadas

### LB-X1 — concordancia ES/NQ

```text
ES_impulse = sigma * [close_ES(H-1s) - close_ES(09:30:59 NY)]
confirmación -> continuación NQ
divergencia -> reversión NQ
```

Se ejecuta solo NQ. Endpoint forward recomendado:
`Z60 = Y60 si confirma, -Y60 si diverge`.

### LB-X2 — residual de sobreextensión

```text
residual_pre =
 sigma * [ret_NQ(-5s,H)/OR_NQ - ret_ES(-5s,H)/OR_ES]
hipótesis: rho(residual_pre,Y60) <= -0.25
```

### LB-X3 — salida que preserve runners

LB-EXIT-V1 mejoró 66% de trades pero mató runners. Nueva hipótesis:

```text
salir en LB solo si PnL no realizado <= 0
y ES no confirma la posición;
mantener runners y todo lo demás.
```

No propongo abrir los 29 casos V2-2024. Según el cierre firmado permanecen
sellados. Estas hipótesis serían forward-only.

## 5. Cotización histórica, sin descarga

Para validar ES→NQ con material anterior:

```text
NQ+ES ohlcv-1s
2020-01-01..2022-04-22
09:25..16:05 America/New_York por día
603 días hábiles
quote exacto: USD 90.45, 0 errores
cap local propuesto: 3 GB; reserva mínima: 80 GB libres
```

No se descargó nada.

## 6. Posición provisional de Codex

1. Retirar las probabilidades Lucid anteriores y rehacerlas con el lock oficial.
2. Tratar todo OR previo como EDT-only hasta regenerar DST-aware.
3. No promover BASE ni ES_CONFIRM.
4. No gastar USD 90.45 todavía: primero converger si el efecto n=26 justifica el
   costo o si conviene forward de costo cero.
5. Priorizar hipótesis que añaden información externa (ES) en vez de quinta
   representación del mismo libro NQ.

`INFORMATION_STATUS=CODEX_CONTEXT_AWAITING_CLAUDE_REVIEW`
