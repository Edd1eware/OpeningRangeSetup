# 02 — La trampa del K=150, y por qué el momentum intradía no se pudo medir

Fecha: 2026-10-13. Scripts: `30_bracket_scaling.py`, `31_bracket_scaling_audit.py`,
`32_isolate_bracket_vs_horizon.py`, `33_intraday_momentum.py`. Sin gasto nuevo.

## 1. El resultado que parecía un edge

La nota 01 dejó abierta una pregunta: la señal del modelo valía ~0.45 ticks en K=20 y en K=40, y había dos mundos
compatibles con eso. Si la ventaja es un tick fijo, nunca cubre el costo de 1.8 a ningún K. Si es deriva
direccional, crece con el bracket y en algún K cruza el costo.

Al añadir K=80 y K=150 salió esto, out of sample:

| K | lado | n | WR | bruto tk | neto tk | baseline tk |
|---:|---|---:|---:|---:|---:|---:|
| 80 | long | 206 | 53.40% | +5.44 | +3.64 | +1.07 |
| 80 | short | 297 | 51.85% | +2.96 | +1.16 | −1.07 |
| 150 | long | 207 | 57.49% | +22.46 | +20.66 | +0.38 |
| 150 | short | 229 | 54.15% | +14.06 | +12.26 | −0.38 |

WR 57.49% con RR 1:1 pasaría una Lucid 50K casi a voluntad: la nota 01 fijó la vara en WR 55%. Si esto fuera
cierto, el proyecto estaría terminado. No lo es.

## 2. Dos defectos, y el segundo mata

**Defecto A, confusión de variables, mío.** Entre K=40 y K=80 cambié tres cosas a la vez: el bracket, el timeout
(30 min → 3 h) y la rejilla de decisión (60 s → 300 s). El salto de 0.35 a 4.2 ticks es atribuible a cualquiera
de las tres. `32_isolate_bracket_vs_horizon.py` existe para variar sólo K sobre una rejilla y un timeout únicos.

**Defecto B, el n es falso, y esto es lo que lo mata.** Con decisiones cada 300 s y etiquetas que miran 3 horas
adelante, las ~41 decisiones de una sesión comparten casi la misma ventana futura y casi la misma respuesta. El
tamaño de muestra efectivo es el número de **sesiones**, no de trades. Remuestreando sesiones completas en lugar
de trades:

| K | lado | trades | sesiones | bruto tk | CI 95% por sesión | top-3 sesiones | ticks por fold |
|---:|---|---:|---:|---:|---|---|---|
| 80 | long | 206 | 70 | +5.44 | [−6.61, +17.24] | 114% del total | +2.2 / +3.8 / −9.4 / +20.0 / +7.5 |
| 80 | short | 297 | 66 | +2.96 | [−8.57, +14.04] | 164% del total | +3.5 / +6.2 / +14.9 / +4.0 / −15.4 |
| 150 | long | 207 | 55 | +22.46 | [−20.99, +62.75] | 110% del total | +8.8 / **+105.0** / −9.4 / −20.3 / +16.7 |
| 150 | short | 229 | 59 | +14.06 | [−15.21, +43.16] | 79% del total | 0 / 0 / +28.6 / +56.4 / −45.7 |

Los cuatro intervalos cruzan el cero **y** cruzan el costo. "Top-3 sesiones = 110% del total" quiere decir que
tres días de cincuenta y cinco cargan más que el total y el resto neto pierde. Un fold da +105 ticks y el
siguiente −20. Limitando a un trade por sesión, que destruye el solapamiento, el intervalo sigue conteniendo el
cero: [−19.09, +57.27].

No es un edge. Es la quinta vez que este proyecto cae en la misma trampa, y la primera en que la máscara fue el
conteo de trades en vez del multiple testing.

**La regla que se saca de aquí:** cuando la etiqueta mira H segundos adelante y la rejilla es de G segundos con
G ≪ H, el n a reportar es el de sesiones y el intervalo se construye remuestreando sesiones. Reportar 207 trades
en ese diseño es reportar 55 observaciones disfrazadas.

## 3. Momentum intradía: no se detecta, pero tampoco se refuta

Es la única hipótesis probada en este proyecto que **no se inventó aquí**: Gao, Han, Li y Zhou (2018) reportan
que el retorno de la primera media hora predice el de la última, y que la penúltima media hora también. Eso
importa para la aritmética de Bonferroni — son dos tests especificados por otros sobre otros datos, no dos
celdas de un barrido — y encaja con la estructura de pago de Lucid: un trade al día, salida por reloj.

| Test | beta | t (Newey-West) | p | veredicto |
|---|---:|---:|---:|---|
| H1 primera → última | −0.0313 | −0.69 | 0.4908 | no replica |
| H2 penúltima → última | +0.2350 | +1.17 | 0.2431 | no replica |

Traducción a trading, signo del predictor a las 15:30 y salida a las 16:00:

| regla | n | WR | bruto tk | neto tk | PF | CI 95% |
|---|---:|---:|---:|---:|---:|---|
| primera, todo | 150 | 48.00% | −10.33 | −12.13 | 0.881 | [−54.07, +32.22] |
| primera, 1ª mitad | 75 | 54.67% | +5.03 | +3.23 | 1.033 | [−59.56, +63.95] |
| primera, 2ª mitad | 75 | 41.33% | −25.68 | −27.48 | 0.736 | [−85.99, +36.61] |
| penúltima, todo | 148 | 52.03% | +0.75 | −1.05 | 0.989 | [−44.12, +43.42] |
| penúltima, 1ª mitad | 74 | 58.11% | +38.92 | +37.12 | 1.446 | [−22.53, +97.11] |
| penúltima, 2ª mitad | 74 | 45.95% | −37.42 | −39.22 | 0.640 | [−96.53, +24.47] |

Las mitades voltean de +37 a −39 ticks. Exploratorio: 0 de 12 buckets sobreviven Bonferroni.

**Lo honesto es decir que no hay potencia, no que el efecto no existe.** El intervalo mide ±44 ticks sobre un
efecto publicado que es chico. Con 150 sesiones este test no puede distinguir un efecto real de cero. Marcarlo
como refutado sería el error simétrico al de la sección 2: allí el n falso infló una conclusión positiva, aquí
el n honesto pero corto no permite ninguna.

## 4. Dónde queda el espacio precio/volumen a 1 segundo

Cerrado, y con evidencia densa en vez de veinte reglas a mano:

| Horizonte | Bracket | Resultado |
|---|---|---|
| 30 min | K=20, 40 | ventaja bruta +0.45 tk, costo 1.8 tk → neto negativo siempre |
| 3 h | K=80, 150 | ventaja aparente +3 a +22 tk, **toda dentro del ruido entre sesiones** |
| medio día | momentum publicado | sin potencia para decidir con n=150 |

El gate de la nota 01 decía: negativo ⇒ el presupuesto que queda no va a más barras de 1 segundo. El gate se
cumplió.

## 5. Lo que sí cambió de precio

Cotización gratis con `metadata.get_cost`, barras de 1 minuto, que es toda la granularidad que una hipótesis de
frecuencia diaria necesita:

| schema | ventana | sesiones 2015-2025 EDT | total |
|---|---|---:|---:|
| ohlcv-1m | RTH 09:30-16:00 | 1,799 | **$2.56** |
| ohlcv-1m | día completo | 1,799 | **$8.34** |

Doce veces la muestra actual por menos de nueve dólares, contra los $66 que cuestan cinco años de barras de 1
segundo. Con 1,799 sesiones el test de momentum intradía pasa de no tener potencia a tenerla, y se vuelven
medibles por primera vez las hipótesis de frecuencia diaria: gap overnight, día de la semana, días de dato
macro, persistencia de día de tendencia. Son justo las que encajan con la forma que la nota 01 encontró óptima
para pasar la evaluación: **un trade al día con stop grande**.
