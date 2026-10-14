# 05 — Turn of month: el primer candidato que no pude matar hoy

Fecha: 2026-10-13. Script: `40_calendar_effects.py`. Reporte: `calendar_effects.csv`.
Datos: 150 sesiones, 2026-03-09 a 2026-10-09. **No es un resultado, es un candidato al filo.**

## Por qué se probó esta familia

Todos los negativos de este proyecto son intradía: precio y volumen a 1 segundo, flujo de órdenes, brackets de
20 a 400 ticks. La familia diaria quedó abierta por falta de muestra, no por resultado. Los efectos de
calendario son la parte de esa familia que **no necesita ningún dato extra**, y dos de ellos estaban
documentados y replicados mucho antes de que este proyecto existiera:

- **Turn of the month**: los retornos de índices se concentran en el último día hábil del mes y los primeros del
  siguiente. Una de las anomalías de calendario más replicadas que hay.
- **Día de la semana** (efecto lunes), que en futuros de índice está muy decaído, así que funciona casi como
  control negativo: encontrarlo fuerte sería una señal de alarma sobre la medición, no un descubrimiento.

Y dos que son plomería del mercado más que afirmaciones de comportamiento: OpEx (tercer viernes) y cierre de
trimestre. Todas las fechas se derivan del calendario de forma exacta — tercer viernes, último día hábil,
frontera de trimestre — así que nada depende de una lista escrita a mano que pudiera estar mal en silencio. Los
días de dato macro (FOMC, CPI, NFP) quedaron **fuera a propósito**: necesitan un calendario verificado, y una
fecha mal tecleada corrompería la prueba sin avisar.

## El número

Regla: **long desde la apertura, bracket simétrico de 300 ticks**, en los días de turn of month (último hábil
del mes más los tres primeros del siguiente). Un trade por día, que es la forma que la nota 03 encontró óptima.

| efecto | n | media dentro | media fuera | t | p | WR bracket | EV neto |
|---|---:|---:|---:|---:|---:|---:|---:|
| **H7 turn of month** | 32 | +427.84 tk | −67.19 tk | +2.37 | **0.0220** | **68.75%** | **+110.7 tk** |
| H8 lunes (control) | 29 | +188.62 | +2.41 | +0.86 | 0.3938 | 55.2% | +29.2 |

Breakeven neto con RR 1:1, K=300 y 1.8 ticks de costo: **50.30%**.

## Por qué NO lo estoy llamando edge

| Prueba | Resultado |
|---|---|
| Wilson 95% del WR, n=32 | **[0.5143, 0.8205]** — la cota inferior roza el breakeven |
| p binomial unilateral vs breakeven 50.30% | **0.0271** → falla el α=0.025 primario |
| Bonferroni sobre las 5 pruebas de calendario (α=0.01) | falla con holgura |
| Años cubiertos | **uno, y parcial**: marzo a octubre de 2026 |
| Exploratorias H9/H10/H11 | n<20, ni se pudieron correr |

Es decir: el efecto apunta en la dirección que la literatura predice, el tamaño es grande, y **no alcanza el
umbral que yo mismo fijé antes de correrlo**. Con n=32 no podía alcanzarlo salvo por suerte. Declararlo edge
sería repetir exactamente el error de la nota 02 con el K=150.

## Un bug propio que casi lo enterró al revés

La primera versión resolvía el bracket usando sólo el máximo y el mínimo del día. Está mal, y mal de forma
grave: el rango diario de NQ pasa de los mil ticks, así que un par de barreras de 300 ticks cae **dentro** del
rango en casi todas las sesiones, y la regla conservadora de empate cobraba el stop casi siempre. Eso producía
un WR de 0.375 en días cuya media era +428 ticks — no un hallazgo, la medición comiéndose a sí misma.

Resolviendo sobre la ruta segundo a segundo, que es lo único honesto, el mismo efecto da 0.6875. La regla de
empate sigue aplicando pero ahora sólo dentro de un **segundo**, donde es genuinamente indecidible, y la
auditoría de la nota 04 midió ese caso en bastante menos del uno por ciento.

La lección general: **una media significativa no es un bracket rentable, y un bracket mal resuelto no refuta una
media.** Son estimandos distintos y hay que medir el que se va a operar.

## Qué lo decide

Las 826 sesiones descargadas hoy (RTH 2021-2025 EDT) llevan la muestra a ~976 sesiones, lo que da
**~208 días de turn of month** repartidos en seis años. Eso convierte este test de "no puede decidirse" a
decidible, y además permite lo que ahora es imposible:

1. **Separar años.** 2021 a 2024 como desarrollo, 2025 y 2026 como prueba. Si el efecto vive en un año, se ve.
2. **Correr las exploratorias** H9 OpEx, H10 cierre de trimestre, H11 primer día hábil, que hoy ni tienen n.
3. **Descomponer el turn of month** por posición: último día, día +1, +2, +3. La literatura dice que el efecto
   se concentra en los primeros; si aquí está repartido parejo o vive en uno solo, eso informa.
4. **Placebo de calendario**: desplazar la ventana de turn of month cinco días hábiles y confirmar que el efecto
   desaparece. Si no desaparece, es deriva de mercado y no calendario.

Si sobrevive las cuatro, es el primer edge real que este proyecto encuentra, y combinado con la política taper
de la nota 03 (WR 0.55 → P(pasar) 53%) sería suficiente. Si no sobrevive, es el quinto trampa de la lista y se
escribe aquí con el mismo detalle que las otras cuatro.
