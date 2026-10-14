# 04 — Lo que Codex atacó, y qué quedó en pie

Fecha: 2026-10-13. Scripts: `34_tape_ml_scan.py`, `35_paired_bracket_and_tie_audit.py`,
`36_tie_rule_and_sparse_policy.py`. Prompt y respuesta completos en el scratchpad de la sesión.

Se le pasó a Codex el resultado de las notas 01 y 02 con la instrucción explícita de **refutar, no confirmar**,
siguiendo la regla de que es par y no subordinado. Su primera frase fue la correcta:

> **No has demostrado agotamiento. Has demostrado que esa combinación de representación, objetivo y selección no
> paga costes.**

Tenía razón en la forma. Sus cuatro ataques concretos se midieron uno por uno. Tres cerraron en negativo. El
cuarto produjo el único resultado útil de la sesión y está en la nota 03.

(Gemini no pudo opinar: cuota agotada, error 429 del free tier.)

## Ataque 1 — la comparación de brackets nunca fue pareada. **Tenía razón.**

Yo escribí que la ventaja del modelo era "~0.45 ticks tanto en K=20 como en K=40", y leí esa constancia como
señal de artefacto de timing. Codex revisó los cuatro números: long da **0.190 y 0.472**, short da **0.456 y
0.200**. El ~0.45 sale de escoger **una dirección distinta para cada K**, y encima el modelo reselecciona sus
entradas en cada K, así que las dos celdas ni siquiera describen los mismos trades. La constancia que leí no
estaba ahí.

Rehecho como experimento pareado: se congelan las entradas y la dirección **una vez**, y sobre esas mismas 206
observaciones se aplican todos los brackets y se mide el desplazamiento firmado a varios horizontes, con la
entrada retrasada 0, 1 y 5 segundos.

| horizonte | delay 0s | delay 1s | delay 5s |
|---:|---:|---:|---:|
| 1s | +0.45 | +0.37 | +0.53 |
| **5s** | **+4.13** | +2.72 | +1.45 |
| 15s | +2.43 | −0.47 | −3.77 |
| 60s | +1.01 | −0.13 | −3.15 |
| 300s | +0.77 | +0.85 | +0.39 |

| K (mismas entradas) | WR | bruto tk | neto tk | CI por sesión |
|---:|---:|---:|---:|---|
| 20 | 53.40% | +1.36 | −0.44 | [−1.49, +4.20] |
| 40 | 50.49% | +0.39 | −1.41 | [−5.88, +6.22] |
| 80 | 53.40% | +5.44 | +3.64 | [−6.42, +17.66] |
| 150 | 53.40% | +10.32 | +8.52 | [−14.86, +35.95] |

El criterio estaba fijado de antemano: crecimiento gradual con meseta y supervivencia al retraso = deriva
transitoria real; salto inicial que muere al retrasar = artefacto. **Salió artefacto, sin ambigüedad.** El
desplazamiento hace pico a los 5 segundos y se evapora al entrar 5 segundos más tarde — una deriva real no
desaparece porque llegues tarde. Y ningún bracket tiene intervalo que excluya el cero.

Mi conclusión original era la correcta por accidente: el razonamiento que la sostenía estaba mal, y el
experimento bien hecho la sostiene de verdad.

## Ataque 2 — la regla de empate podría esconder la ventaja. **Cerrado, y no puede.**

Cuando una barra de 1 segundo toca las dos barreras, la etiqueta cobra el stop. Es el default honesto a esa
resolución pero es una **cota**, no un estimador insesgado. Codex convirtió la duda en aritmética: voltear un
stop falso a objetivo vale 2K ticks, así que recuperar los 1.35 ticks que faltan exige corregir el **3.38%** de
todos los trades en K=20, o el **1.69%** en K=40.

| K | barras ambiguas | total | share | necesario | veredicto |
|---:|---:|---:|---:|---:|---|
| 20 | 62 | 53,250 | **0.1164%** | 3.38% | no puede explicarlo |
| 40 | 1 | 53,250 | **0.0019%** | 1.69% | no puede explicarlo |

Falta por un factor de 29 en K=20 y de 890 en K=40. Ni siquiera hizo falta el tape tick-a-tick para resolver el
orden dentro del segundo: no hay suficientes segundos ambiguos para que importe. La cota deja de ser una
preocupación.

## Ataque 3 — el promedio del top 20% no es una política ejecutable. **Cerrado en negativo.**

Un trader no toma el 20% de las decisiones del día, toma como mucho una. Política medida: **máximo un trade por
sesión, el primero del día cuya predicción cruza un umbral fijado en entrenamiento**, con abstención total los
días que nada cruza. "El primero", no "el mejor del día", que sería lookahead.

| K | lado | pct | trades | WR | bruto tk | neto tk | CI por sesión |
|---:|---|---:|---:|---:|---:|---:|---|
| 20 | long | 99 | 38 | 63.16% | +5.26 | +3.46 | [−1.05, +11.58] |
| 40 | long | 99 | 28 | **64.29%** | +11.43 | +9.63 | [−2.86, +25.71] |
| 40 | short | 99.5 | 11 | 63.64% | +10.91 | +9.11 | [−10.91, +32.73] |

Los WR de 63-64% son la clase de número que tienta. **Cero de 16 celdas** tienen la cota inferior del bootstrap
por sesión arriba del nulo del placebo (+3.5 ticks), y todas contienen el cero. Con n entre 11 y 38 no podía ser
de otro modo.

## Ataque 4 — el objetivo no es edge direccional. **Tenía razón, y de ahí salió la nota 03.**

> *"El 55% requerido pertenece a tu política simulada, no es una constante de Lucid."*

Correcto. Ver nota 03: una política de tamaño adaptativo pasa el 43.2% de las evaluaciones 50K con cero edge,
contra el 25.2% del mejor tamaño fijo.

## Ataque propio, no sugerido por Codex — el ML nunca había visto el tape

Los scripts 16-18 midieron señales de flujo **una por una**. El barrido 27 usó un modelo amplio pero sólo con
features de barra. Nadie había preguntado si el flujo de órdenes informa **condicionalmente**, en combinación
con el estado del tape y del precio. Un test univariado de imbalance no puede encontrar "el imbalance importa,
pero sólo cuando el libro está delgado y la sesión no ha escogido dirección".

21 features nuevas del tape de 13M de trades (imbalance firmado a 30/60/300s, lo mismo restringido a prints
grandes sobre el percentil 90 de la sesión, conteo e intensidad, tamaño medio, barrido de niveles por segundo,
todo contra el propio ritmo de la sesión), sobre la ventana 09:35-10:25 que es donde existe el tape.

| set | K | lado | n | sesiones | WR | bruto tk | CI por sesión |
|---|---:|---|---:|---:|---:|---:|---|
| bars+tape | 40 | long | 346 | 69 | 52.31% | +1.85 | [−2.60, +6.25] |
| bars+tape | 40 | short | 352 | 65 | 52.84% | +2.27 | [−1.62, +6.26] |
| **bars_only** | 40 | long | 429 | 69 | 52.91% | **+2.33** | [−1.25, +6.01] |
| **bars_only** | 40 | short | 396 | 67 | 53.28% | **+2.63** | [−0.83, +6.24] |

**Añadir el tape empeora el resultado.** Las barras solas rinden más que barras más tape, lo que es la firma de
21 features de ruido diluyendo la señal. Todos los intervalos cruzan el cero. El flujo de agresor tampoco aporta
información condicional, y eso cierra la última pregunta que los datos en disco podían contestar gratis.

## Estado al cierre de la sesión

| Espacio | Veredicto | Fuerza de la evidencia |
|---|---|---|
| ORB en todas sus variantes | sin edge | 20 reglas a mano, 78 trades, PF 0.602 |
| Tape univariado (imbalance, absorción, drive) | sin edge | markouts y barreras, IS+ / OOS− |
| Precio/volumen 1s, 40 features, ML, K=20..150 | sin edge | 53,250 decisiones, walk-forward purgado, placebo |
| Tape + barras conjuntas, 61 features | sin edge, y peor que barras solas | 150 sesiones, bootstrap por sesión |
| Momentum intradía publicado | **sin potencia para decidir** | n=150, CI ±44 ticks |
| Política de tamaño para la 50K | **43.2% de pase con cero edge** | MC validado contra solución cerrada |

Lo único que sigue abierto por falta de muestra, no por resultado negativo, es la frecuencia diaria. Por eso se
compraron 826 sesiones más de barras de 1 segundo (RTH 09:30-16:00, 2021-2025 EDT, $66.67), que llevan la
muestra de 150 a 976 sesiones.
