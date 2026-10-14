# 03 — Política de tamaño que pasa el 43% de las 50K con CERO edge

Fecha: 2026-10-13. Scripts: `37_lucid_policy_search.py`, `38_validate_bracket_fairness.py`,
más dos barridos de validación en scratchpad. Reportes: `lucid_policy_search.csv`,
`lucid50k_stake_sweep.csv`, `lucid50k_taper_sweep.csv`, `bracket_fairness.csv`.

## De dónde vino esto

Codex atacó la nota 01 en cuatro puntos. Tres se cerraron en negativo y están en la nota 04. El cuarto fue el
bueno: *"el 55% requerido pertenece a tu política simulada, no es una constante de Lucid"*. Tenía razón. El
script 28 fijó un stop constante, el mismo cada trade, cada día, sin mirar el estado de la cuenta. Eso no es el
objetivo de Lucid. El objetivo es

> maximizar, sobre políticas π, la probabilidad de llegar a $53,000 antes de romper el piso

y una política de tamaño fijo tira a la basura la estructura de las reglas.

## El resultado

Política **taper**: un trade al día, bracket simétrico, arriesgando `min(distancia al target, $1,500)`.
$1,500 = 300 ticks de NQ. Cuando el balance se acerca al target la apuesta se encoge sola, porque ya sólo falta
una ganancia chica.

| WR | P(pasar) | días mediana |
|---|---:|---:|
| **0.50 — cero edge** | **43.2%** | 5 |
| 0.52 | 46.8% | 5 |
| 0.55 | 52.8% | 5 |

Contra el mejor tamaño fijo del script 28 (25.2%): **+18 puntos absolutos, 1.71x, sin ningún edge.**

Es insensible al mínimo de apuesta, que es la objeción obvia — si el truco dependiera de apostar un tick al
final, sería inejecutable:

| cap | ticks | mín 5t | mín 10t | mín 20t | mín 40t |
|---:|---:|---:|---:|---:|---:|
| $1,400 | 280 | 0.4053 | 0.4031 | 0.3943 | 0.3851 |
| **$1,500** | **300** | 0.4350 | **0.4322** | 0.4274 | 0.4151 |
| $1,600 | 320 | 0.0084 | 0.3311 | 0.4022 | 0.4186 |
| $1,700 | 340 | 0.0000 | 0.0882 | 0.3610 | 0.3811 |

## Por qué funciona, y por qué no es un edge

**Hay que decirlo claro: esto no crea esperanza positiva.** El valor esperado de la cuenta sigue siendo negativo
por exactamente el costo pagado. Lo único que hace la política es reacomodar la misma masa de probabilidad para
poner más de ella arriba del target. Es apostar mejor, no tener ventaja. Lo que compra, para el objetivo
declarado, es una probabilidad materialmente más alta de convertir una cuota de evaluación en una cuenta
fondeada, y cuesta cero investigar.

Dos mecanismos, los dos medidos no supuestos:

**1. Resonancia aritmética.** La curva de P(pasar) contra tamaño constante no es suave, es escalonada:

| stake | ticks | P(pass) WR .50 | días |
|---:|---:|---:|---:|
| $1,500 | 300 | 0.2944 | 5 |
| **$1,550** | **310** | **0.3804** | **2** |
| $1,650 | 330 | 0.3851 | 2 |
| $1,950 | 390 | 0.3775 | 2 |
| $2,000 | 400 | 0.2476 | 2 |

Con stake ≥ $1,550 **dos ganadas cubren el target** ($3,100 > $3,000) y se pasa en dos días. Con $1,500 dos
ganadas dan $2,982 y hace falta una tercera, que es un trade entero de riesgo adicional. El salto de 8 puntos
sale de ahí, no de ninguna propiedad del mercado.

**2. El acantilado del piso.** Con stake ≥ $2,000 y el piso en balance − $2,000, la secuencia gana-pierde deja
al trader obligado a una apuesta que lo mata con certeza. Por eso $2,000 da 0.03% y $3,000 da 0.00%. El tope
correcto no es un número bonito sino **algo estrictamente menor que la distancia al piso**, y $1,500 es el 75%
de los $2,000. Esto invierte el consejo que el proyecto traía escrito: "stop grande" sólo es bueno hasta el 75%
del drawdown, y pasado ese punto la probabilidad no baja, se desploma.

## Dos hipótesis mías que se cayeron en la validación

Las puse en el diseño creyéndolas importantes. No lo son, y conviene que quede escrito:

| Hipótesis | Realidad medida |
|---|---|
| El lock del piso en $50,100 crea una asimetría grande que hay que explotar | vale **+0.0017** de probabilidad. Irrelevante |
| La regla de consistencia del 50% ata y hay que trabajar alrededor | cuesta **−0.0036**. Irrelevante |

El motor sí está validado contra un caso con solución cerrada: ruina del jugador desde 50,000 con barreras
absorbentes en 48,000 y 53,000, sin costo y pasos chicos, da 0.4005 y 0.4008 medidos contra 0.4000 analítico.

## Lo que los datos dicen del supuesto central

Todo el 43% descansa en que un bracket simétrico de 300 ticks gane la mitad de las veces y **se resuelva dentro
de la sesión**. Medido sobre las 150 sesiones, una entrada por sesión a hora fija:

| entrada | K=300 sin resolver al cierre | EV bruto (ticks) |
|---|---:|---:|
| 09:35 | 0.00% | 0.0000 |
| 10:00 | 0.00% | 0.0000 |
| 11:00 | 2.00% | 0.0000 |
| 13:00 | 19.33% | 0.0000 |

Entrando antes de las 10:00 resuelve el 100% de las veces. Entrando a las 13:00 el 19% queda abierto al cierre,
y entonces la política ya no es "un trade al día resuelto": hay que aguantar el gap o cerrar a mercado, y
ninguna de las dos es el pago modelado. **La política exige entrada matutina.**

**Trampa en mi propia medición, para que no se lea mal:** el WR agrupando long y short sale exactamente 0.5000 en
las 28 celdas, y eso es tautológico — si el long gana, el short pierde, son espejos mecánicos. Ese número no
prueba que el bracket sea justo. Lo que sí se establece es que el WR de cada dirección por separado cae dentro de
un intervalo del 95% que contiene 0.5, o sea que no hay inclinación direccional detectable en brackets de 200 a
400 ticks, y que el EV bruto es 0.0000 exacto, que es la ausencia de edge medida con precisión en vez de
estimada.

## Qué falta antes de operarlo

1. **Precio de la evaluación.** Con P(pasar) = 43.2% se esperan ~2.3 evaluaciones por cuenta fondeada. Si la
   cuota de una 50K son $150, son ~$350 esperados. Ese número decide si conviene, y no lo tengo verificado.
2. **La cuenta fondeada tiene sus propias reglas**, y pasar la evaluación no es el final. No modelado todavía.
3. **Slippage del stop.** El modelo llena en la barrera. Un stop de 300 ticks en NQ se llena mejor que uno de 10,
   pero no exacto. Todo el 43.2% es una **cota optimista** por esto y porque los trades se simulan independientes.
4. Que pasar una evaluación **no demuestra edge**: con cero habilidad se pasa el 43% de las veces con esta
   política. Una cuenta pasada no valida la estrategia que la pasó, ni propia ni de nadie.

## Corrección: las reglas por plan, verificadas en vez de supuestas

El primer barrido aplicó el mismo reglamento a los dos planes. Está mal. Verificado contra las reglas
publicadas de la firma:

| | LucidFlex 50K | LucidPro 50K |
|---|---|---|
| Profit target | $3,000 | $3,000 |
| Max Loss (piso duro, trailing EOD) | $2,000 | $2,000 |
| Daily loss limit | **ninguno** | $1,200 |
| Regla de consistencia en la eval | **50%** | **ninguna** |

Y un detalle que cambia la lectura del riesgo: **el daily loss de Lucid es un breach blando**. Tocarlo bloquea
la cuenta hasta la siguiente sesión, no la quema, siempre que no se haya tocado también el Max Loss. El único
piso duro es el Max Loss. Mi simulación modelaba el bloqueo blando correctamente por casualidad, pero le
aplicaba la regla de consistencia a los dos planes, lo cual es falso para Pro.

Rehecho con el reglamento correcto, 60,000 cuentas por celda:

| cap | ticks | Flex WR.50 | Flex WR.52 | Flex WR.55 | Pro WR.50 | Pro WR.52 | Pro WR.55 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| $1,300 | 260 | 0.3754 | 0.4173 | 0.4721 | 0.3747 | 0.4135 | 0.4738 |
| $1,400 | 280 | 0.4046 | 0.4410 | 0.5059 | 0.4035 | 0.4433 | 0.5029 |
| **$1,500** | **300** | **0.4312** | 0.4718 | 0.5318 | 0.4320 | 0.4695 | 0.5238 |
| $1,550 | 310 | 0.4114 | 0.4545 | 0.5211 | 0.4348 | 0.4758 | 0.5313 |
| **$1,600** | **320** | 0.3313 | 0.4004 | 0.4862 | **0.4413** | 0.4786 | 0.5281 |

**Recomendación por plan, con cero edge:**

| plan | stop óptimo | P(pasar) | días mediana |
|---|---|---:|---:|
| LucidFlex 50K | 300 ticks ($1,500) | 43.1% | 5 |
| **LucidPro 50K** | **320 ticks ($1,600)** | **44.1%** | 5 |

Pro gana por poco, y por una razón concreta: sin regla de consistencia tolera una apuesta un poco más grande.
En Flex el cap de $1,500 es también la mitad exacta del target, que es donde la regla del 50% empieza a morder;
pasar a $1,600 en Flex cuesta 10 puntos de probabilidad (0.4312 → 0.3313) mientras que en Pro gana uno.

Fuentes de las reglas: [daily loss blando](https://propvator.com/blog/lucid-trading-daily-loss-limit/),
[reglas por plan](https://www.helloweekends.com/firms/lucid-trading/rules),
[Flex vs Pro](https://mytradingbuddy.ai/blog/lucid-trading-evaluation-rules).

## Robustez: las dos derivadas que deciden si esto es real

Un número puntual no sirve sin saber qué lo rompe. Dos sensibilidades, 60,000 cuentas por celda.

### 1. ¿Y si la dirección se elige PEOR que al azar?

Esta es la objeción fuerte. El 43% descansa en WR = 0.50, que se cumple **por simetría cuando la dirección se
escoge al azar**. Un trader real no escoge al azar, y todas las reglas que este proyecto probó salieron
ligeramente negativas después de costo. Hay que leer el número en el lado malo, no en el centro:

| WR | Flex 300t | Pro 320t | referencia: stop fijo 150t |
|---:|---:|---:|---:|
| 0.45 | **0.3443** | 0.3461 | — |
| 0.47 | 0.3750 | 0.3859 | — |
| 0.48 | 0.3968 | 0.4027 | **0.2053** |
| 0.49 | 0.4147 | 0.4192 | — |
| 0.50 | 0.4356 | 0.4385 | 0.2528 |
| 0.52 | 0.4700 | 0.4751 | 0.3082 |
| 0.55 | 0.5278 | 0.5283 | — |

**Aguanta.** Con WR 0.45, que son cinco puntos por debajo de justo, todavía pasa el 34.4%. Y la comparación
contra el stop fijo es donde se ve el valor de la política: con WR 0.48 el stop fijo de 150 ticks pasa el 20.5%
y el taper el 39.7%, casi el doble. La política no necesita que el trader tenga razón, necesita que no se
equivoque mucho.

### 2. ¿Y el slippage del stop?

El modelo llena en la barrera. Un stop de 300 ticks en NQ es una orden stop-market y paga lo que el libro dé.
Cargado como costo extra de round trip:

| costo round trip | USD | WR.48 | WR.50 | WR.52 |
|---:|---:|---:|---:|---:|
| 1.8 tk (lo modelado) | $9 | 0.3963 | 0.4367 | 0.4734 |
| 3 tk | $15 | 0.3846 | 0.4257 | 0.4652 |
| 5 tk | $25 | 0.3739 | 0.4164 | 0.4597 |
| 8 tk | $40 | 0.1997 | **0.2502** | 0.3101 |
| 12 tk | $60 | 0.0000 | 0.0000 | 0.0000 |

Plano hasta 5 ticks, y luego otra vez un acantilado en 8. El mecanismo es el mismo de siempre: cuando el costo
crece, dos ganadas dejan de cubrir los $3,000 y hace falta un trade entero más. Ocho ticks de costo total en un
stop de 300 ticks sería extremo, así que el 43% sobrevive al slippage realista.

## La economía, con precios verificados

Evaluación LucidFlex 50K: **$146** de lista, **$87.60** con el código público de descuento, **reset $95**.
LucidPro 50K: reset $120. Sin cuota mensual, sin fee de activación.

| WR | P(pasar) | intentos esperados | costo con lista | costo con código |
|---:|---:|---:|---:|---:|
| 0.48 | 0.3968 | 2.52 | $290 | $232 |
| **0.50** | **0.4356** | **2.30** | **$269** | **$211** |
| 0.52 | 0.4700 | 2.13 | $253 | $195 |
| 0.45 | 0.3443 | 2.90 | $327 | $268 |

O sea: **una cuenta 50K fondeada cuesta unos $211-269 esperados, sin ningún edge**, en una mediana de 5 días de
operación por intento. Lo que no está modelado y conviene tener presente antes de tratar esto como un plan: las
reglas de la cuenta ya fondeada son otro juego (Flex trae un plan de escalado que ajusta el tamaño con la
ganancia), y pasar la evaluación no da acceso a dinero propio sino a un reparto de utilidades sobre una cuenta
que tiene su propio piso.
