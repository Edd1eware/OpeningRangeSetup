# Prerregistro LUCID150K-SNIPER-V3

Fecha: 2026-07-26  
Estado: **CONGELADO ANTES DE REGENERAR RESULTADOS DST**

Objetivo: una candidata para la evaluación **LucidPro 150K**, RR inicial
superior a 1:1, sostenible entre regímenes y con capacidad simulada de alcanzar
+USD 9,000 dentro de 63 sesiones.

## 0. Origen y estatus de la hipótesis

Resultados anteriores sugieren:

- el primer breakout UP supera DOWN en 8/8 gestiones;
- el bracket 120/55 sin modelo tuvo EV positivo;
- esos resultados usaron `13:30 UTC` fijo y omitieron gran parte del invierno.

Por ello V3 no considera 2022–2026 un holdout. Regenera el fenómeno con DST
correcto y lo usa solo como evidencia de desarrollo. El único examen
confirmatorio disponible es 2020-01-01..2022-04-22, aún no descargado.

V3 no usa Liquidity Burst, MBO ni el bloque sellado LB V2-2024.

## 1. Datos y reloj

```text
instrumento = NQ.c.0 ohlcv-1s
timezone = America/New_York
OR = [09:30:00, 09:31:00)
scan = 09:31:00..10:00:00
force exit = 15:55:00
DEV_SEEN = 2022-04-25..2026-06-30
HOLDOUT = 2020-01-01..2022-04-22
```

Los timeouts se incluyen a precio de cierre de la última barra disponible
antes o en 15:55; no se eliminan.

## 2. Entrada única — `FIRST_UP_ORB_120_55_TRAIL`

1. Detectar el primer toque de cualquiera de estos límites después del OR:
   - UP: `high >= OR_high + 1 tick`;
   - DOWN: `low <= OR_low - 1 tick`.
2. Si ambos ocurren en el mismo segundo, excluir la sesión.
3. Si DOWN ocurre primero, no operar ese día.
4. Si UP ocurre primero, entrada stop LONG en `OR_high + 1 tick`.
5. Máximo una operación por sesión.

No se exige ES, retest, volumen, tendencia ni filtro de mes.

## 3. Riesgo, RR y trailing

```text
tick = 0.25
coste round-trip = 4 ticks
stop inicial = 55 ticks
target duro = 120 ticks
RR bruto inicial = 120 / 55 = 2.1818:1
activar trailing al tocar +55 ticks
stop mínimo al activar = entry + 4 ticks (break-even neto)
trailing = mejor extremo favorable - 55 ticks
```

Orden intrabar pesimista:

1. stop heredado;
2. target;
3. actualizar mejor extremo;
4. activar/actualizar trailing para la siguiente barra.

Diagnóstico no seleccionable: mismo bracket fijo 120/55 sin trailing.

## 4. Gates sobre `DEV_SEEN`

Todos deben cumplirse:

| Gate | Umbral |
|---|---:|
| D1 n | >= 200 |
| D2 frecuencia | >= 6 trades/mes |
| D3 EV neto | > +0.08R |
| D4 PF | > 1.20 |
| D5 años con EV > 0 | >= 3 |
| D6 semestres con EV > 0 | >= 65% |
| D7 mayor aporte de un semestre al PnL positivo | <= 50% |
| D8 trailing menos fixed | >= -0.03R |

Aquí `R=55 ticks`. Pasar estos gates solo autoriza descargar y abrir el
HOLDOUT; no valida el edge.

## 5. HOLDOUT único

2020-01-01..2022-04-22 se ejecuta una vez sin cambiar reglas. Todos:

```text
n >= 100
frecuencia >= 6 trades/mes
EV neto > +0.05R
PF > 1.15
>= 2 años con EV > 0
ningún año con EV < -0.05R
bootstrap IC95 EV, límite inferior > -0.03R
10,000 réplicas, seed 0x8A12C736E4B509FD
```

Si falla, V3 termina y el mismo holdout no se usa para rescatar una variante.

## 6. Simulación LucidPro 150K

Solo se ejecuta tras PASS del holdout:

```text
target = +USD 9,000
MLL EOD = USD 4,500
floor relativo = min(peak_EOD - 4,500, +100)
DLL soft = USD 2,700
horizonte = 63 sesiones
intentos bootstrap = 50,000
```

Sizing congelado:

```text
equity EOD < +3,000  -> 4 NQ
+3,000 a < +6,000   -> 5 NQ
>= +6,000           -> 6 NQ
```

El peor resultado inicial por contrato incluye 55 ticks de stop y 4 de coste:
USD 295. Incluso 6 NQ = USD 1,770, debajo del DLL. Una sola operación diaria.

Gates Lucid, todos:

```text
P(pass dentro de 63 sesiones) >= 50%
P(breach antes del pase) <= 20%
mediana de sesiones al pase, condicionada a pasar, <= 63
```

## 7. Prohibiciones

No cambiar lado, OR, horario, stop, target, activación, distancia, costes,
sizing ni gates después de ver V3. No excluir timeouts. No filtrar 2024,
invierno, semestres malos, noticias o volatilidad. No seleccionar el bracket
fijo. No abrir holdout si falta un gate DEV.

PASS final significa candidato para forward/sim, no garantía ni autorización de
operación real.

`INFORMATION_STATUS=LUCID150K_SNIPER_V3_PREREGISTERED_NO_RESULT`
