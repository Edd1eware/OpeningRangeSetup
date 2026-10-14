# 01 — Gate ML sobre RTH completo, y cuánto edge exige realmente la 50K

Fecha: 2026-10-13. Scripts: `26_rth_ml_dataset.py`, `27_rth_ml_eval.py`,
`28_lucid50k_requirement.py`, `29_rth_ml_concentration.py`.
Datos: 150 sesiones EDT, 2026-03-09 a 2026-10-09, barras 1s día completo. Sin gasto nuevo en Databento.

## Por qué este estudio

El proyecto había probado ~20 reglas a mano (ORB follow/fade, imbalance de agresor, absorción, drive) y todas
salieron planas o negativas. Veinte puntos elegidos a mano no cubren el espacio de hipótesis. Un modelo de
gradient boosting sobre un bloque amplio de features causales lo muestrea mucho más denso: si **ahí tampoco hay
nada**, el negativo es bastante más fuerte que veinte reglas más, y entonces el presupuesto que queda de
Databento no debe ir a más barras de 1s. Eso es lo que este gate decide.

Nunca se había corrido ML sobre datos reales en este proyecto: `06_train_catboost.py` existía pero no hay ningún
reporte suyo en `reports/`.

## Aviso de lectura sobre el reloj

DuckDB renderiza `TIMESTAMP WITH TIME ZONE` en la zona de la sesión, que por defecto es la local de la máquina
(UTC−6, México). Por eso la apertura 09:30 ET **imprime como 07:30** y la hora 15:00-15:59 local aparece vacía
(es el halt de CME 17:00-18:00 ET). El dato siempre estuvo bien; lo que engaña es el render. Los scripts nuevos
hacen `SET TimeZone='America/New_York'` antes de leer. No es un bug del pipeline: `04_or_events.py` ya casaba
exacto contra la barra correcta.

## Diseño, congelado antes de correr

| Elemento | Valor |
|---|---|
| Decisiones | cada 60s, 09:35–15:30 ET → 53,250 filas |
| Features | 40, todas causales (retornos 10s–30m, vol realizada, posición en rango, VWAP, distancia a OR y a máx/mín overnight, eficiencia, volumen normalizado, hora) |
| Entrada | apertura del segundo siguiente, siempre llena |
| Barreras | simétricas K ∈ {20, 40} ticks, timeout 30 min **marcado a mercado** |
| Empates | si una barra de 1s toca ambas, se cobra el SL |
| Costo | 1.8 ticks round trip |
| Validación | walk-forward expansivo, 5 folds, purga de 5 sesiones |
| Selección | sólo decisiones sobre el percentil 80 de las predicciones **de entrenamiento** |
| Controles | baseline take-all + placebo con etiquetas barajadas |

Long y short se etiquetan por separado, no como espejo: la regla de empate y el timeout los hacen asimétricos.

## Resultado 1 — el modelo sí le gana al baseline, pero en bruto y por centavos

| K | lado | n | WR | EV bruto | EV neto | PF | baseline EV bruto |
|---:|---|---:|---:|---:|---:|---:|---:|
| 20 | long | 4,408 | 50.48% | +0.0095R | −0.0805R | 0.851 | −0.0080R |
| 20 | short | 6,009 | 51.14% | +0.0228R | −0.0672R | 0.874 | +0.0059R |
| 40 | long | 5,313 | 50.59% | +0.0118R | −0.0332R | 0.936 | −0.0112R |
| 40 | short | 5,628 | 50.25% | +0.0050R | −0.0400R | 0.923 | +0.0112R |

Take-all sobre las 26,625 decisiones OOS da EV bruto entre −0.011R y +0.011R, o sea el mercado no tiene deriva,
que es exactamente lo que debe pasar y sirve de sanity check del etiquetado.

El modelo le gana al take-all en bruto en 3 de 4 combinaciones. Pero traducido a ticks la ventaja es
**≈ 0.45 ticks por trade**, contra un costo de 1.8 ticks. No alcanza por un factor de 4.

Y el detalle que importa más que el signo: **0.45 ticks en K=20 y 0.45 ticks en K=40**. Si fuera pronóstico
direccional real, un bracket del doble debería cosechar más ticks. Que sea constante apunta a un efecto de
timing sub-tick, no a dirección. El placebo no se corrió para estas celdas porque ninguna superó al baseline en
neto; correrlo habría sido gastar cómputo en confirmar un negativo.

## Resultado 2 — cuánto edge exige la Lucid 50K

Reglas modeladas (LucidFlex 50K): target +$3,000, trailing drawdown $2,000 sobre equity de cierre, lock del piso
en $50,100 al tocar $52,100, consistencia 50%, y como variante el daily loss de $1,200 de LucidPro. El ratio
target/DD es **1.5**, contra 2.0 de la 100K: la 50K es más difícil, no una copia a escala. Monte Carlo de 20,000
cuentas por celda, 120 días máximo, costo 1.8 ticks por trade, breach intradía mata aunque el piso sólo se mueva
al cierre.

P(pasar) con 1 NQ, por tamaño de stop y win rate:

| SL ticks | WR .50 | .51 | .52 | .53 | .55 | .58 |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.001 |
| 20 | 0.002 | 0.009 | 0.022 | 0.049 | 0.201 | 0.656 |
| 40 | 0.110 | 0.168 | 0.239 | 0.325 | **0.529** | **0.789** |
| 60 | 0.196 | 0.248 | 0.313 | 0.377 | 0.518 | 0.716 |
| 80 | 0.229 | 0.267 | 0.312 | 0.364 | 0.475 | 0.631 |
| 100 | 0.232 | 0.262 | 0.300 | 0.338 | 0.421 | 0.555 |
| 150 | **0.252** | **0.282** | 0.303 | 0.340 | 0.397 | 0.511 |

Tres lecturas, todas accionables:

1. **El stop óptimo se invierte según si hay edge.** Sin edge gana el stop grande (150 ticks → 25.2%); con
   WR 55% gana el chico (40 ticks → 52.9%). Elegir stop de 20 ticks es apostar a que el edge es real: si no lo
   es, la probabilidad de pasar cae de 25% a 0.2%, dos órdenes de magnitud. Un stop de 10 ticks es cero en los
   dos mundos, porque el costo fijo de 1.8 ticks se come el 18% de cada apuesta.
2. **Cero edge no es cero probabilidad.** 25% de pasar sin ninguna habilidad, con un stop de 150 ticks y un
   trade al día. Eso significa que *pasar una evaluación no demuestra edge*, ni propio ni de nadie, y que una
   cuenta pasada no valida la estrategia que la pasó.
3. **El objetivo real es WR 55% con RR 1:1**, es decir +2.75 puntos sobre el breakeven neto de 52.25%. Esa es la
   vara. La señal medida arriba vale 0.45 ticks por trade; para WR 55% con K=40 hacen falta ~4 ticks.

Todos estos números son una **cota optimista**: los trades se simulan independientes, los fills se asumen en la
barrera, y no hay slippage de stop ni plan de escalado.

## Qué sigue

- `29_rth_ml_concentration.py` (corriendo): la señal de 0.45 ticks es el promedio del top 20%. Si se concentra,
  el top 1% podría valer varios ticks. Se barre la selectividad de 50% a 99.9% y se lee la **forma** de la curva,
  no una celda: subida monótona = efecto condicional real; perfil plano o dentado = ruido ordenado. Como es un
  barrido, el placebo repite el barrido completo con etiquetas barajadas, así el nulo es "la mejor celda que
  encuentra un barrido de esta forma en datos sin señal".
- `30_bracket_scaling.py` (escrito): separa los dos mundos compatibles con 0.45 ticks constantes. Añade K=80 y
  K=150 con timeout de 3 horas. Si el EV bruto en ticks sigue plano, el espacio precio/volumen a 1s está cerrado
  y el presupuesto se va a datos de libro. Si sube y cruza 1.8 ticks, ese K es la configuración a validar.

## Presupuesto, cotizado gratis con `metadata.get_cost`

| schema | ventana | sesiones 2021-25 | total |
|---|---|---:|---:|
| ohlcv-1s | RTH 09:30-16:00 | 805 | $66.29 |
| ohlcv-1s | 09:25-10:30 | 805 | $11.34 |
| trades | 09:25-10:30 | 805 | $89.55 |
| mbo | 09:30-10:00 | 805 | $120.18 |
| mbp-10 | 09:30-09:45 | 644 | $92.11 |

Nada comprado todavía. Hoy hay **5 sesiones de MBO** y **cero de MBP-10**, así que todo lo que diga "footprint"
o "imbalance de libro" en este proyecto descansa sobre n=5 sesiones.
