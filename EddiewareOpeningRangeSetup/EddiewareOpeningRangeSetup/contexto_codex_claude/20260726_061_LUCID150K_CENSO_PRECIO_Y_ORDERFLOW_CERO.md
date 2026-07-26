# 061 — Censo de precio y order flow: EV bruta cero en todo el espacio

Fecha: 2026-07-26
Autor: Claude
Estado: **tres resultados negativos duros. Cierran la vía precio-solo y la vía delta de apertura.**

Continúa `20260726_060_LUCID150K_FEASIBILITY_FRONTIER_GATES_MISALIGNED.md`.

## 1. Por qué censo y no hipótesis 14

Trece hipótesis manuales fallaron una por una. En vez de proponer la catorce, se
midió la **superficie completa** de una familia paramétrica. Un censo responde
algo que una hipótesis no puede: si ningún rincón de la familia sirve, la
familia entera queda descartada y no hay que volver a visitarla.

Scripts:

```text
lucid150k_feasibility\build_cache.py            (1,029 días NQ 1s -> npz, 23.0M barras)
lucid150k_feasibility\throughput_census.py      (240 combos de disparo)
lucid150k_feasibility\drift_census.py           (400 celdas de deriva)
lucid150k_feasibility\orderflow_open_test.py    (568 sesiones con tape firmado)
lucid150k_feasibility\orderflow_discriminate.py (atribución delta vs precio)
```

Coste `4 ticks` round turn en todos. El stop gana los empates dentro de la misma
barra de 1 segundo. DEV = `2022-04-25..2023-12-31`, `415` sesiones.

## 2. Censo de caudal — 240 combinaciones, cero positivas

Familia: en el segundo `t`, `move = close[t] - close[t-W]`; si `|move| >= K`
entrar a favor (CONT) o en contra (FADE), bracket `S` / `S*RR`, una posición a
la vez. Grid: `W ∈ {30,60,180,300}s`, `K ∈ {10,15,20,30,40}t`,
`S ∈ {20,30,40}t`, `RR ∈ {1,2}`, dirección `∈ {CONT,FADE}`.

| métrica | valor |
|---|---|
| combos con datos | 240 |
| combos con EV neta positiva | **0** |
| combos que cumplen el listón de caudal | **0** |
| EV neta: mín / mediana / máx | −4.41 / −4.06 / **−3.56** ticks |
| EV **bruta** implícita | −0.41 / +0.06 / **+0.44** ticks |
| WR a RR 2:1 en el mejor combo | 0.337 |

El win rate observado a `2:1` es `0.337` contra `0.333` teórico bajo azar puro.
La superficie entera es el coste: **EV bruta ≈ 0**. Esto también valida el
simulador, que reproduce el nulo con precisión.

## 3. Censo de deriva — 400 celdas, la única superviviente es de 2023

Sin disparo alguno: entrar LONG o SHORT a una hora fija, todos los días, con
bracket fijo. `25` ventanas de entrada × `2` direcciones × `4` stops × `2` RR.

EV bruta sobre las 400 celdas: media `−0.14`, mediana `−0.02`, p5 `−4.53`,
p95 `+4.27` ticks. Plano.

Una sola celda destacó: LONG en la primera barra de la sesión con stop `60` /
target `120`, EV neta `+9.73t`, PF `1.258`, `t = 2.24` sobre `n = 415`. Es el
máximo de 400 sorteos, exactamente lo que produce el azar. Test de era:

| era | n | WR | EV neta | PF | t |
|---|---:|---:|---:|---:|---:|
| DEV 2022 | 170 | 0.353 | −0.47 | 0.989 | −0.07 |
| DEV 2023 | 245 | 0.449 | **+16.82** | 1.477 | +2.93 |
| 2024 | 247 | 0.267 | **−15.90** | 0.661 | −3.13 |
| 2025 | 245 | 0.347 | −1.55 | 0.963 | −0.28 |
| 2026 | 122 | 0.361 | +0.92 | 1.022 | +0.12 |

Todo el resultado vive en 2023 y se invierte en 2024. Mismo patrón que el sesgo
UP que V3 ya había matado con la corrección DST. Descartada.

## 4. Order flow de apertura — la quinta representación que falla

Data: `book_recordings\tape_*_NY.csv`, `684` archivos, `2022-04-04..2026-07-02`,
con `time_ny, price, volume, direction`. La cobertura real es `09:29`–`09:40`
aproximadamente, es decir sólo la apertura. Tras exigir cobertura hasta
`09:33:00` quedan `568` sesiones y `543` con outcome unido al cache de 1s.

Features causales sobre `09:30:00–09:33:00`: delta acumulado, `delta_ratio`
(delta/volumen), número de trades, movimiento de precio del tape. Entrada a las
`09:33:00`.

En DEV el resultado del lado largo es **monótono decreciente** en `delta_ratio`
—flujo vendedor fuerte en la apertura precede subida—, que es un patrón con
sentido de mecanismo. Los cortes de quintil se fijaron en DEV y se aplicaron
sin cambios a las eras posteriores:

Bracket `40/80`, EV del lado largo por quintil de `delta_ratio` (EV/n):

| era | q0 | q1 | q2 | q3 | q4 |
|---|---|---|---|---|---|
| DEV 22-23 | **+13.3**/44 | +9.0/43 | +7.8/44 | −2.1/43 | **−8.5**/44 |
| 2024 | −17.6/50 | −5.8/22 | −7.6/33 | +7.0/40 | −15.8/17 |
| 2025-26 | −10.0/53 | +5.1/22 | −9.7/35 | −20.0/30 | −7.5/23 |

El orden desaparece por completo fuera de DEV. La atribución lo confirma: el
diferencial de EV entre delta bajo y delta alto, controlando por el movimiento
de precio en terciles, es `+13.4 / +15.3 / +38.6` ticks en DEV y **cambia de
signo** a `−35.8 / −15.6` en 2024 y `−32.8 / −4.0 / +28.4` en 2025-26.

El movimiento de precio por sí solo tampoco ordena nada (`+4.0, +2.8, +6.2,
+1.7, +3.4` en DEV; negativo y desordenado después).

Con esto son **cinco representaciones** independientes las que no encuentran
dirección en NQ: MBO V1, MBO V2 continuo, features 1s con CatBoost, velas HOLC,
y ahora delta firmado de apertura.

## 5. Qué queda cerrado y qué no

| Vía | Estado | Evidencia |
|---|---|---|
| Disparo por momentum/fade sobre barras | **Cerrada** | 240/240 negativas, EV bruta ≈ 0 |
| Deriva por hora del día | **Cerrada** | 400 celdas planas; la única superviviente es artefacto 2023 |
| Delta firmado de apertura | **Cerrada** | orden monótono en DEV, invertido en 2024 |
| Confirmación multiinstrumento | **Degradada** | NQ/ES/YM/RTY están correlacionados; sumar instrumentos correlacionados aumenta el tamaño, no el caudal independiente. La recomendación de subir V17 a prioridad 1 del doc 060 queda corregida por este motivo |
| V14 inventario overnight | Suspendida | doc 060: aunque acierte, `P(pass) = 0.00` con sizing prudente |

## 6. Consecuencia para el objetivo

El requisito del doc 060 es `>= 9.5 ticks por sesión` con 3 minis. La evidencia
acumulada dice que la EV bruta disponible en la información explorada es
estadísticamente cero, y el coste de `4 ticks` es real. No existe en esta data
un edge que llegue al listón por la vía de predecir dirección.

Queda una vía que **no** es de predicción y que todavía no se ha cuantificado:
dado que el edge direccional es ~0, ¿cuál es la política de tamaño y parada que
maximiza `P(pasar)` por intento bajo el reglamento Lucid, y cuánto vale esa
probabilidad? El floor `min(peak_EOD − 4500, +100)` se bloquea en `+100`, lo que
crea una asimetría estructural real del reglamento, no del mercado. Eso se
cuantifica en el siguiente documento.

No se abrió el pseudo 2024 de V14. No se abrió el holdout `2020-01-01..2022-04-22`.
No se optimizó ningún umbral de ninguna hipótesis preregistrada.

`INFORMATION_STATUS=LUCID150K_PRICE_AND_ORDERFLOW_CENSUS_ZERO`
