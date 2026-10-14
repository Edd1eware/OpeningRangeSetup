# 08 — De la deriva al bracket: la geometría, el truco de micros, y cuánto vale de verdad

Fecha: 2026-10-13. Scripts: `45_direction_to_bracket_map.py`, `46_drift_to_bracket_theory.py`,
`47_micro_contract_leverage.py`. Reportes: `direction_to_bracket.csv`, `drift_to_bracket_theory.csv`,
`micro_contract_leverage.csv`.

## El problema que había que resolver

La nota 06 estableció la dirección con fuerza: ^GSPC da p=0.0001 en 64 años sobre los días +1..+3 del mes, y el
efecto vive **entero en la sesión diurna** (94-107%, overnight exactamente cero). La nota 05 midió el bracket
sobre NQ y falló: WR 0.5778 fuera de muestra, p=0.1967.

Y la aritmética dice que va a seguir fallando. Separar 0.578 de un breakeven de 0.503 a un α corregido de
0.0125 exige **unos 280 días de ventana**; las 976 sesiones completas dan ~140. **Más segundos de NQ no arreglan
un tamaño de muestra de frecuencia diaria.**

La salida es dejar de intentarlo por ahí. Las dos cantidades que hacen falta no necesitan la misma muestra:

| cantidad | qué necesita | de dónde sale |
|---|---|---|
| dirección, P(cierre > apertura) | décadas, nada intradía | ^GSPC 64 años, ^NDX 41, NQ=F 26 |
| conversión a bracket | ruta de 1 segundo, **no** muestra larga | todas las sesiones en disco |

## Un error mío que corregí, y la geometría que lo explica

El script 45 midió, sobre 69 sesiones de ventana, un edge negativo en K=150, 200 y 250 y fuertemente positivo
en K=300 y 400. **Llamé a esa inconsistencia una bandera roja**, razonando que una deriva real debería aparecer
en todos los brackets. Ese razonamiento estaba mal.

Para movimiento browniano con deriva diaria μ y volatilidad σ, barreras simétricas en ±b dan

    P(toca arriba primero) = 1 / (1 + exp(−2μb/σ²))

y para μ chica eso es ≈ 0.5 + μb/(2σ²), de donde

    **EV bruto en ticks ∝ μ·k²**

El edge crece con el **cuadrado** del bracket mientras el costo se queda plano en 1.8 ticks. Los brackets chicos
no pueden cubrirlo por geometría, no por el mercado. El patrón de signos que encontré es lo que la teoría
predice, no evidencia en contra.

Y antes de eso había otro error en el mismo script: los días sin resolver los marcaba como ganados si el día
cerró arriba, lo que **le regala al trade la dirección del día**. Se vio en la columna de control: con P(up)=0.50
el bracket debía dar 0.5000 y daba 0.5090 en K=300 (7.3% sin resolver) contra 0.4999 en K=150 (0.7% sin
resolver). El sesgo era el manejo, no el mercado. Corregido a marcar a mercado.

## La consecuencia incómoda

La misma aritmética dice que +0.1% de deriva vale **~+11 ticks netos** en K=300, no los +56 que reportaron 69
sesiones. Lo medido es ruido alrededor de un valor chico, y el valor chico es el que hay que planear.

Modelo con σ=1.1145% medida y la deriva de 26 años de NQ=F:

| fuente | K150 | K200 | K250 | K300 | K400 |
|---|---:|---:|---:|---:|---:|
| ventana +0.1088% | +1.49 | +4.04 | +7.33 | **+11.34** | +21.56 |
| no-ventana +0.0296% | −0.91 | −0.21 | +0.68 | +1.78 | +4.56 |

WR que vería la política en K=300: **0.5219** contra breakeven 0.5030.

**El modelo no está falsado.** Contra 355 sesiones de control predice los EV medidos: K300 +2.86 modelo vs +2.23
medido, K400 +6.49 vs +5.17, K100 −1.28 vs −1.52, K500 +11.15 vs +15.21.

## El truco de los micros

De `EV ≈ μ·b·R/σ²` y `R = b·N`, sustituyendo b = R/N:

    **EV ≈ μ·R² / (N·σ²)**

Para un riesgo en dólares **fijo**, el edge es inversamente proporcional al nocional. Medio nocional, doble
edge. Y no es apalancamiento ni sube el riesgo: el stop son los mismos dólares. Lo que cambia es que una
posición más chica deja el mismo stop en dólares **más lejos en porcentaje**, y la distancia es lo que convierte
una deriva en ventaja de primer paso.

En una 50K el stop está clavado cerca de $1,500 por las reglas de drawdown, así que la única palanca es el
nocional, y el micro es un quinto del contrato completo.

## Lo que mata la versión agresiva

**Lucid exige estar plano a las 16:45 ET y no permite overnight ni fin de semana en cuentas de evaluación.** Un
bracket que necesita más de una sesión no existe como trade: se cierra a mercado en la campana, sin quedarse
nada de la ventaja de primer paso. Eso descarta las configuraciones anchas de un golpe.

| posición | nocional | stop | resuelve en sesión | WR modelo | breakeven | EV modelo |
|---|---:|---:|---:|---:|---:|---:|
| 2 NQ | $1.0M | 37.5 pts | 100.0% | 0.5066 | 0.5060 | +$1.71 |
| 1 NQ | $500k | 75 pts | 98.6% | 0.5131 | 0.5030 | +$37.55 |
| **8 MNQ** | $400k | **94 pts** | **96.2%** | 0.5164 | 0.5040 | **+$51.82** |
| 5 MNQ | $250k | 150 pts | 84.0% | 0.5263 | 0.5025 | +$102 |
| 2 MNQ | $100k | 375 pts | 29.0% | 0.5653 | 0.5010 | inoperable |

Dato útil del mismo hallazgo: en Lucid **la pérdida no realizada no cuenta contra el drawdown**, sólo el balance
de cierre. Los swings intradía no matan; lo que mata es cerrar el día abajo del piso.

## Cuánto vale esto de verdad

Mejor configuración operable: **8 MNQ con stop de 94 puntos**, riesgo $1,500, sólo en los días +1..+3 del mes.
WR modelada 0.5164 contra breakeven 0.5040.

Metido en la política escasa de la nota 07: **P(pasar) ≈ 46.4%** contra 43.3% sin ningún edge.

**Tres puntos porcentuales.** Eso es lo que vale el edge más fuerte que este proyecto ha encontrado, una vez
quitados el sesgo de los días sin resolver, el ruido de 69 sesiones y la restricción de cerrar en el día. Es
real, es gratis y es mucho menos de lo que sugerían los números crudos de +56 ticks y WR 0.6875.

## Lo que falta

1. La descarga (42% al escribir esto) triplica los días de ventana de NQ y aprieta la tasa de resolución, que es
   el input menos medido del modelo.
2. La deriva de NQ=F (+0.1088%, p=0.183) no es significativa por sí sola; el modelo se apoya en que ^GSPC con
   64 años y p=0.0001 estime la misma cosa. Son índices correlacionados, no muestras independientes.
3. σ se midió sobre 424 sesiones que incluyen 2021 y 2026, dos años alcistas. Un σ mal estimado mueve el WR
   linealmente, así que conviene rehacerlo con las 976.

## Corrección: dos inputs estaban mal estimados

Script `50_model_inputs_long_history.py`. La configuración de arriba (8 MNQ, 94 puntos, WR 0.5164) descansaba en
dos números sacados de las 424 sesiones de 1 segundo en disco, que son 2021, parte de 2022 y 2026 — dos años
alcistas. Reestimados sobre los 6,582 días de NQ=F:

| input | lo que usé | 26 años | últimos 5 años |
|---|---|---|---|
| σ apertura-cierre | 1.1145% | **1.5749%** | **1.3738%** |
| precio de planeación | 25,000 | 30,847.50 (cierre real) | — |

Los dos empujan el WR hacia abajo: σ mayor reduce μ/σ², y un precio mayor hace que $1,500 de stop quede más
cerca en porcentaje, que es la unidad que el modelo necesita. La tasa de resolución también se reestimó sobre
6,582 máximos y mínimos diarios en vez de 424 rutas, lo cual es exacto para la pregunta "¿se alcanzó la
barrera?" aunque no diga cuándo.

Configuración corregida, con σ de los últimos 5 años:

| posición | stop | resuelve en sesión | WR ventana | breakeven | EV ventana | edge de calendario |
|---|---:|---:|---:|---:|---:|---:|
| 1 NQ | 75 pts | 99.9% | 0.5070 | 0.5030 | +$12.92 | +$15.95 |
| 8 MNQ | 94 pts | 99.4% | 0.5088 | 0.5040 | +$17.44 | +$21.43 |
| **5 MNQ** | **150 pts** | **95.4%** | **0.5140** | 0.5025 | **+$48.06** | **+$40.45** |
| 4 MNQ | 187 pts | 89.8% | 0.5175 | 0.5020 | +$68.67 | +$54.35 |
| 2 MNQ | 375 pts | 53.4% | 0.5350 | 0.5010 | +$115.59 | inoperable |

**La configuración a operar es 5 MNQ con stop de 150 puntos**, no las 8 MNQ de 94 puntos. Resuelve dentro de la
sesión el 95.4% de las veces, que respeta la regla de cerrar antes de 16:45 con margen, y deja el 4.6% restante
cerrando a mercado en la campana.

P(pasar) con WR 0.5140 en la política escasa: **≈45.9%** contra 43.3% sin edge. La conclusión de tres puntos no
cambia; lo que cambia es que ahora descansa en 26 años de volatilidad medida y no en 424 sesiones de dos años
alcistas, y que la posición correcta es otra.

El patrón de siempre se repite en la tabla: la mejor EV está en 2 MNQ con stop de 375 puntos (+$115), y es
inoperable porque sólo resuelve el 53% dentro de la sesión. Cada vez que este proyecto encuentra un número
grande, la restricción que lo hace inalcanzable aparece una línea después.
