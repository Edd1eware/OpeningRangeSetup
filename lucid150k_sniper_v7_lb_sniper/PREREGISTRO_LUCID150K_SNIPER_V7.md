# Prerregistro LUCID150K-SNIPER-V7-LB-SNIPER

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE CALCULAR OUTCOMES V7**

Objetivo: convertir la pista `LB continuation acceptance` de V5 en una entrada
sniper con frecuencia suficiente para LucidPro 150K, sin relajar causalidad ni
usar 2024.

## 0. Cambio mecanístico respecto a V5

V5 dio en DEV `EV +0.305R`, `PF 1.92`, 2/2 años, pero n=16. Su stop al midpoint
expulsó gran parte del universo por riesgo >80.

V7 congela antes de medir:

- stop fijo 20 ticks y target 40 ticks;
- hasta dos episodios LB independientes por día;
- solo el primer burst de cada episodio;
- separación mínima 120 segundos;
- nunca posiciones solapadas.

No se cambia la regla de aceptación 4/5 ni se usa absorción.

## 1. Datos y bloques

Detector idéntico:
`liquidity-burst-detector-2026-07-22-v7-postburst-matrix`.

```text
DEV = 2022-04-25..2023-12-31
PSEUDO_VAL = 2025-01-01..2026-06-30
2024 = prohibido
NQ = NQ.c.0 ohlcv-1s
force exit = 15:55 NY
```

## 2. Episodios elegibles

Por sesión, en orden de `Detector_Publish_Timestamp_UTC`:

```text
09:31:00..10:00:00 NY
Mechanism_Validity == VALID
Reference_Type OR_HIGH para BUY / OR_LOW para SELL
Burst_Index_In_Episode == 1
```

Elegir el primer episodio elegible. Un segundo solo puede considerarse si:

- su publish ocurre al menos 120 s después del publish del primero;
- su entrada ocurre después de la salida efectiva del primer trade.

Máximo dos trades por sesión. Si un episodio es ambiguo, no consume el cupo de
trade pero sí permanece como episodio observado; el siguiente aún debe respetar
120 s respecto al primer episodio considerado.

## 3. Acceptance causal

Después de `t_pub`, tomar las primeras cinco barras NQ completas igual que V5:

- primera barra empieza en el siguiente segundo entero;
- quinta empieza no más de 7 s después de publish;
- `outside_count >=4/5`;
- quinto close sigue fuera por al menos 1 tick en dirección del burst.

Si no cumple, no hay trade para ese episodio.

## 4. Entrada y gestión

Entrada en dirección del burst, apertura de la barra posterior a la quinta, con
1 tick de slippage adverso.

```text
stop inicial = 20 ticks
target duro = 40 ticks
RR bruto inicial = 2:1
coste round-trip = 4 ticks
activar trailing al tocar +20 ticks
stop mínimo = entry + 4 ticks (break-even neto)
trailing = mejor extremo - 20 ticks
```

Orden intrabar pesimista. Diagnóstico no seleccionable: mismo bracket fijo
40/20 sin trailing.

## 5. DEV gates

Todos:

```text
n >= 30
frecuencia >= 1.5 trades/mes calendario
EV neto > +0.15R
PF > 1.40
2/2 años con EV > 0
>=60% semestres positivos
trailing menos fixed 40/20 >= -0.05R
```

## 6. PSEUDO_VAL gates

Todos:

```text
n >= 25
frecuencia >= 1.5 trades/mes calendario
EV > +0.10R
PF > 1.30
2025 y 2026 con EV > 0
bootstrap IC95 EV, límite inferior > -0.10R
10,000 réplicas, seed 0x4C8E1A70B2D659F3
```

Solo PASS en ambos autoriza HOLDOUT.

## 7. HOLDOUT y LucidPro 150K

HOLDOUT 2020-01-01..2022-04-22:

```text
n >= 40
frecuencia >=1.5/mes
EV >0
PF >1.20
>=2 años positivos
IC95 EV límite inferior >-0.05R
```

Simulación:

```text
target +USD 9,000
MLL EOD USD 4,500
floor min(peak_EOD-4,500,+100)
DLL USD 2,700 soft
horizonte 63 sesiones
50,000 intentos
10 NQ máximo
```

Sizing por equity:

```text
<+3,000 -> 8 NQ  (riesgo stop+coste = USD 960)
<+6,000 -> 9 NQ  (USD 1,080)
>=+6,000 -> 10 NQ (USD 1,200)
```

Con máximo dos trades diarios, si la pérdida acumulada del día alcanzaría el
DLL, el segundo trade se omite.

Gates:

```text
P(pass <=63 sesiones) >=50%
P(breach antes del pase) <=20%
mediana condicional <=63
```

## 8. Prohibiciones

No usar 2024. No cambiar 5 barras, 4/5, 120 s, máximo dos, stop20, target40,
trailing, costes, horarios, versión del detector o gates. No seleccionar
absorción, lados, meses ni features DOM. No solapar. No abrir HOLDOUT antes de
PASS.

PASS = candidata a forward, no garantía ni autorización de operación real.

`INFORMATION_STATUS=LUCID150K_SNIPER_V7_PREREGISTERED_NO_RESULT`
