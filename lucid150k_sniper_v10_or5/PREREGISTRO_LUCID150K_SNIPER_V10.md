# Prerregistro LUCID150K-SNIPER-V10-OR5

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE MEDIR V10**

## Hipótesis

El OR de 1 minuto es microestructura ruidosa. Un OR de 5 minutos, seguido de
aceptación por cierre, confirmación ES y pullback defendido, puede aislar la
resolución real de la apertura NQ.

## Datos

```text
NQ/ES ohlcv-1s
America/New_York
OR5 [09:30:00,09:35:00)
scan aceptación 09:35:00..10:15:00
retorno máximo 300 s
última entrada 10:30:00
force exit 15:55
```

ES siempre usa cierre completo estrictamente anterior.

## Entrada `OR5_ACCEPTANCE_ES_PULLBACK`

1. Detectar los primeros 3 cierres NQ consecutivos:
   - LONG: `close >= NQ_OR5_high +1 tick`;
   - SHORT: `close <= NQ_OR5_low -1 tick`.
2. En el tercer cierre, ES debe estar fuera de su OR5 por >=1 tick en el mismo
   lado.
3. Si la primera secuencia de 3 no tiene confirmación ES, invalidar el día.
4. Desde el segundo siguiente y hasta 300 s:
   - LONG pullback: `low <= NQ_OR5_high` y
     `close >= NQ_OR5_high+1 tick`;
   - SHORT: `high >= NQ_OR5_low` y
     `close <= NQ_OR5_low-1 tick`.
5. En el pullback ES debe continuar fuera por >=1 tick en el mismo lado.
6. Si NQ cierra fuera del límite OR5 opuesto antes del pullback, invalidar.
7. Entrada siguiente open +1 tick adverso.
8. Stop fijo 40 ticks; target 80 ticks.
9. Máximo un trade/día.

## Gestión

```text
RR inicial 2:1
coste4 ticks
activar trailing +40 ticks
stop mínimo entry+4 ticks
distancia trailing40 ticks
target duro80 ticks
orden intrabar pesimista
```

Fixed80/40 sin trailing es diagnóstico no seleccionable.

## Gates

DEV 2022-04-25..2023-12-31:

```text
n>=50
frecuencia>=2.5/mes
EV>+0.10R
PF>1.30
2/2 años positivos
>=60% semestres positivos
trailing-fixed>=-0.05R
```

PSEUDO 2024:

```text
n>=25
EV>0
PF>1.15
IC95 low>-0.10R, 10k, seed0xE2A7601D4CB895F3
```

Solo PASS permite HOLDOUT.

HOLDOUT 2020..2022-04-22:

```text
n>=50, EV>0, PF>1.20, >=2 años positivos, IC95 low>-0.05R
```

LucidPro150K: target9k, MLL4.5k EOD, DLL2.7k, floor lock+100, 63 sesiones,
50k intentos, 8/9/10 NQ según equity; Ppass>=50%, breach<=20%.

No cambiar OR5, 3 cierres, ES, 300s, stop40, target80, horarios, costes o gates.

`INFORMATION_STATUS=LUCID150K_SNIPER_V10_PREREGISTERED_NO_RESULT`
