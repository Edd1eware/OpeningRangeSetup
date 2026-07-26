# Prerregistro LUCID150K-SNIPER-V4-BREADTH

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE DESCARGAR/LEER YM Y RTY**

Objetivo: entrada NQ reproducible para evaluación **LucidPro 150K**, RR inicial
>=1:1, estabilidad temporal y capacidad simulada de pasar +USD 9,000 en máximo
63 sesiones.

## 0. Hipótesis

ES por sí solo no confirmó un edge estable. La hipótesis V4 es que una ruptura
NQ solo tiene continuación cuando existe breadth: al menos dos de los tres
índices ES, YM y RTY ya aceptaron fuera de su propio opening range en el mismo
sentido.

YM y RTY se adquieren outcome-blind después de firmar este documento.

## 1. Datos y causalidad

```text
NQ = NQ.c.0 ohlcv-1s
ES = ES.c.0 ohlcv-1s
YM = YM.c.0 ohlcv-1s
RTY = RTY.c.0 ohlcv-1s
timezone = America/New_York
OR por instrumento = [09:30:00, 09:31:00)
scan NQ = 09:31:00..10:00:00
force exit NQ = 15:55:00
```

Las confirmaciones usan exclusivamente el último cierre completo de cada
instrumento con timestamp estrictamente anterior al segundo NQ de decisión.

Ticks:

```text
NQ=0.25, ES=0.25, YM=1.0, RTY=0.10
```

Bloques:

```text
DEV = 2022-04-25..2023-12-31
PSEUDO_VAL = 2024
STRESS_SEEN = 2025..2026-06-30, descriptivo
HOLDOUT = 2020-01-01..2022-04-22, cerrado
```

## 2. Entrada — `NQ_FIRST_BREAK_BREADTH_2OF3`

1. Detectar el primer toque NQ:
   - UP: `NQ_high >= NQ_OR_high + 1 tick`;
   - DOWN: `NQ_low <= NQ_OR_low - 1 tick`.
2. Ambos lados en el mismo segundo = excluir.
3. En el último cierre completo de ES/YM/RTY antes del toque, contar:
   - confirmación UP: `close >= OR_high + 1 tick propio`;
   - confirmación DOWN: `close <= OR_low - 1 tick propio`.
4. Operar solo si al menos `2 de 3` confirman el lado del primer toque NQ.
5. Entrada stop NQ:
   - LONG `NQ_OR_high + 1 tick`;
   - SHORT `NQ_OR_low - 1 tick`.
6. Stop inicial = midpoint del OR NQ.
7. Excluir si el riesgo no está entre 20 y 80 ticks NQ.
8. Máximo una operación por sesión.

El tercer instrumento puede ser neutral u opuesto. No se prueban 1/3 ni 3/3.

## 3. Gestión

```text
coste round-trip = 4 ticks NQ
target duro = +2R
activar trailing = +1R
al activar, stop mínimo = entry + coste (break-even neto)
trailing = mejor extremo favorable - 1R
```

Orden OHLCV-1s pesimista: stop heredado, target, actualizar mejor extremo y
cambiar trailing para la barra siguiente. `FIXED_1R` es diagnóstico no
seleccionable. RR inicial = 2:1.

## 4. Gates DEV

Todos:

```text
n >= 40
EV neto > +0.08R
PF > 1.25
2/2 años con EV > 0
>= 60% semestres con EV > 0
trailing menos FIXED_1R >= -0.05R
```

## 5. Gates PSEUDO_VAL

Todos:

```text
n >= 20
EV > 0
PF > 1.10
bootstrap IC95 EV, límite inferior > -0.10R
10,000 réplicas, seed 0x72C18EF05A9346BD
```

Solo PASS DEV + PSEUDO_VAL autoriza adquirir/abrir HOLDOUT.

## 6. HOLDOUT único

Todos:

```text
n >= 40
EV > 0
PF > 1.15
>= 2 años con EV > 0
ningún año con EV < -0.05R
bootstrap IC95 EV, límite inferior > -0.05R
```

Un fallo cierra V4; no se cambia el umbral de breadth usando el mismo holdout.

## 7. Simulación LucidPro 150K

Solo tras PASS holdout:

```text
target = +USD 9,000
MLL EOD = USD 4,500
floor relativo = min(peak_EOD - 4,500, +100)
DLL soft = USD 2,700
horizonte = 63 sesiones
50,000 intentos bootstrap
```

Sizing por riesgo total, máximo 6 NQ:

```text
equity EOD < +3,000 -> budget USD 1,200
+3,000..<+6,000    -> budget USD 1,500
>= +6,000          -> budget USD 1,800
contracts = min(6, floor(budget / ((R_ticks + 4) * USD 5)))
```

Si contratos <1, no se opera. Gates:

```text
P(pass <=63 sesiones) >= 50%
P(breach antes del pase) <= 20%
mediana de sesiones al pase <= 63
```

## 8. Adquisición autorizada y límites

YM+RTY se descargan solo en 09:25–10:05 NY. Cotización muestral live:

```text
1,028 sesiones
coste proyectado = USD 15.4847
con margen 25% = USD 19.3558
```

Controles locales:

```text
cap específico V4 = 5 GB
cap acumulado autorizado por usuario = 80 GB
reserva mínima C: = 25 GB libres
```

## 9. Prohibiciones

No barrer breadth, instrumento, reloj, OR, entrada, stop, target, trailing,
costes, dirección, meses o volatilidad. No excluir timeouts ni años malos. No
abrir HOLDOUT antes de ambos gates. No usar el bloque sellado LB V2-2024.

PASS final = candidato a forward/sim, no garantía ni autorización de operar.

`INFORMATION_STATUS=LUCID150K_SNIPER_V4_PREREGISTERED_PRE_DOWNLOAD`
