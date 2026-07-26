# Preregistro MULTIENTRY-V1 — atacar la magnitud vía frecuencia

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE MEDIR**

## 0. Por qué esta hipótesis y por qué NO se descarga nada

El diagnóstico de `upbias_v2\PARTE_A_INFORME.md` fue: el edge UP existe y es
robusto (8 de 8 configuraciones), pero **es demasiado pequeño para el vehículo**
— con 1 trade/día y +2.38 ticks netos, el 72% de las cuentas se quema antes del
primer payout bajo reglas Lucid 150k.

La palanca que señala la evidencia es **magnitud vía frecuencia**, no otro filtro
ni otra gestión (ambos ya fallaron siete veces).

Ya existe la infraestructura: `orb_multientry_mc.py` arma un largo en **cada**
perforación alcista del OR-high (primera ruptura, reentradas tras volver dentro,
y reversión tras fallo bajista), rearmando solo cuando el precio vuelve por
debajo del OR-high para que las entradas sean distintas.

```text
datos disponibles = orb_multientry.csv
n entradas = 2,360   dias = 645   media = 3.66 entradas/dia
rango      = 2022-04-25 .. 2026-07-01
por anio   = 2022:453  2023:560  2024:542  2025:538  2026:267
```

**No se descarga nada.** 2,360 trades es 3.4× la muestra de todos los tests
previos, cubre el mismo periodo y el mismo instrumento donde vive el edge (ES ya
está en cuarentena por FAIL robusto). Descargar historia anterior a 2022
introduciría otro régimen; descargar los ~17 días desde 2026-07-01 no cambia
nada. Si tras este test hiciera falta más muestra, se pedirá autorización
entonces con un objetivo concreto.

## 1. Defecto corregido del script original

`orb_multientry_mc.py` calcula el filtro anti-absorción como
`vpt <= quantile(2/3)` **sobre la muestra completa**. Eso es minado full-sample:
el umbral ve el futuro.

Corrección congelada: **el umbral se calcula SOLO sobre DEV** y se aplica sin
recalcular a FRESH.

## 2. Especificación congelada

```text
regla     = largo en cada perforacion alcista del OR-high 09:30 (UP-only)
gestion   = trailing SL=40, activacion=20, distancia=40   (la del script)
filtro    = vpt <= p66(DEV)    anti-absorcion, umbral SOLO de DEV
comision  = 2.0 ticks por trade
DEV       = 2022 + 2023
FRESH     = 2024 + 2025 + 2026    (disparo unico)
```

`net` en el CSV es ticks BRUTOS; el EV neto resta la comisión.

## 3. Gate — dos bloques, los seis criterios deben cumplirse en FRESH

**Bloque 1 — calidad del edge**

| # | Criterio | Umbral |
|---|---|---|
| G1 | EV neto | > 0 |
| G2 | Profit Factor | > 1.15 |
| G3 | Años con EV neto > 0 | ≥ 2 de 3 |
| G4 | Frecuencia | **≥ 20 trades/mes** |

G4 es el punto entero del ejercicio: con 8.4 trades/mes ya sabemos que no
alcanza. Si la frecuencia no sube materialmente, la hipótesis no sirve aunque el
EV sea positivo.

**Bloque 2 — el objetivo real (payout farming)**

Monte Carlo 10,000 cuentas sobre el stream FRESH filtrado, reglas Lucid 150k
(target $9,000, MaxLoss $4,500 EOD/trailing, DLL soft $2,700), base 4 contratos,
kill-switch dinámico, trades barajados respetando el número medio por día.

| # | Criterio | Umbral |
|---|---|---|
| G5 | Payouts esperados por cuenta | > 0.5 |
| G6 | P(quema antes del primer payout) | < 50% |

## 4. Prohibiciones

No se barren SL/ACT/DIST. No se prueban otros percentiles del filtro
anti-absorción. No se prueba la versión sin filtro como alternativa para escoger
la mejor. No se excluye ningún año. No se cambia el número de contratos para
hacer pasar el MC. Un solo fallo = rechazada y se documenta.

`INFORMATION_STATUS=MULTIENTRY_V1_PREREGISTERED_NO_RESULT`
