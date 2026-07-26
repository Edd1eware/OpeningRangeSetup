# 062 — Política óptima sin edge y economía real del farmeo

Fecha: 2026-07-26
Autor: Claude
Continúa los docs 060 y 061.

## 1. Verificación de reglas oficiales

El handoff exigía re-verificar el reglamento antes de simular. Las páginas de
soporte de Lucid devuelven `403` a fetch automatizado, así que se usaron fuentes
secundarias actuales. Resultado, con una corrección importante al modelo heredado:

| Regla | Modelo de Codex | Verificado | Impacto |
|---|---|---|---|
| Profit target 150K | `+$9,000` | `+$9,000` | igual |
| MLL | `$4,500` | `$4,500`, **calculado a cierre (EOD)** | igual en efecto |
| Movimiento del límite | trailing sobre peak EOD | sólo actualiza al cierre; **la devolución intradía no rompe la cuenta** | igual |
| Bloqueo del floor | `+100` | bloquea al *Initial Trail Balance* | diferencia despreciable |
| Días mínimos | no modelado | **ninguno; el pase en un día está permitido** | **grande** |
| Consistencia en eval | sin consistencia | sin consistencia | igual |
| Consistencia en fondeada | no modelado | **40% del profit total en un solo día** (LucidPro post 2025-11-28) | **grande** |
| DD en fondeada | no modelado | **LucidScale: 60% del mayor profit EOD, sólo sube** | **grande** |
| Máx contratos | 10 minis | 10 minis | igual |
| Precio eval 150K | no modelado | `$370` lista, `$259` con cupón | permite calcular EV |
| Reset | no modelado | `$90/$120/$180` en 25K/50K/100K | 150K no publicado |
| Payout | no modelado | mínimo `$1,000`; primer payout tope `$3,000`, luego `$3,500` | permite calcular EV |

La ausencia de días mínimos en la evaluación es la pieza que cambia el problema.

## 2. La evaluación se puede ganar con varianza

Script: `lucid150k_feasibility\policy_optimizer.py`, `20,000` caminos, bracket
`60/120`, 2 trades/día, tamaño `= clip(floor((equity − floor) × f / riesgo), 1, 10)`
con fracción `f1` por debajo del bloqueo del floor y `f2` por encima.

| edge (ticks/trade) | WR implícito | f1 | f2 | P(pasar) | P(quemar) | días medianos |
|---:|---:|---:|---:|---:|---:|---:|
| −2.0 | 0.344 | 0.50 | 0.20 | 0.228 | 0.766 | 1 |
| **0.0** | 0.356 | 0.50 | 0.20 | **0.257** | 0.736 | 2 |
| +2.0 | 0.367 | 0.50 | 0.20 | 0.285 | 0.706 | 2 |
| +4.0 | 0.378 | 0.35 | 0.10 | 0.338 | 0.572 | 15 |
| +8.0 | 0.400 | 0.35 | 0.05 | 0.467 | 0.450 | 19 |

Sin ningún edge, jugando audaz, se pasa **una de cada cuatro evaluaciones**, y la
mediana del camino ganador son **2 días**. El reglamento lo permite porque no hay
mínimo de días y porque el floor deja de perseguir una vez bloqueado.

Esto no es un edge. Es la estructura de barreras: `+9,000` de objetivo contra
`4,500` de riesgo, con el suelo congelándose a partir del pico.

## 3. La cuenta fondeada es otro juego

Script: `lucid150k_feasibility\funded_phase_sim.py`, horizonte 126 sesiones.

Dos reglas bloquean el mismo truco: la consistencia del `40%` obliga a repartir
el profit en varios días, y LucidScale limita la devolución al `40%` del pico.
La conversión exacta de LucidScale no está publicada con precisión, así que se
simulan las dos lecturas posibles como cota.

Probabilidad de llegar a un payout válido (`>= $1,000` y día máximo `<= 40%` del
total):

| edge (ticks) | lectura estricta | lectura suave |
|---:|---:|---:|
| 0.0 | 0.064 | 0.543 |
| +2.0 | 0.074 | 0.625 |
| +4.0 | 0.084 | 0.705 |
| +8.0 | 0.122 | 0.837 |
| +12.0 | 0.174 | 0.917 |

Con edge cero la cuenta acaba quemada en el `94–99.8%` de los caminos dentro del
horizonte, según la lectura.

## 4. Economía del farmeo con edge cero

Tomando la lectura **favorable** y el precio con cupón:

```text
coste por intento                      $259
P(pasar la evaluación)                 0.257
coste esperado por cuenta fondeada     $259 / 0.257 = $1,008
P(llegar a un payout | fondeada)       0.543
payout mínimo                          $1,000  (reparto ~90% -> ~$900)
ingreso esperado por intento           0.257 x 0.543 x $900 = $126
EV por intento                         $126 - $259 = -$133
```

Con la lectura estricta el ingreso esperado cae a `$15` por intento y el EV a
`−$244`. El farmeo sin edge es **negativo en las dos lecturas**. La evaluación es
un billete de lotería barato; el payout no lo es, y la consistencia del `40%` es
exactamente lo que impide convertir varianza en dinero.

Para que el farmeo sea rentable con un solo payout haría falta
`P(pasar) × P(payout) ≥ 0.288`, que con `P(pasar) = 0.257` exige
`P(payout) ≥ 1.12`. Imposible. La rentabilidad sólo puede venir de payouts
repetidos sobre una cuenta que sobrevive, y sobrevivir es justo lo que requiere
edge real.

## 5. Respuesta directa al objetivo

El objetivo era descubrir un edge que permita pasar una 150K en tres meses.
Estado honesto tras los docs 060–062:

| Pregunta | Respuesta con evidencia |
|---|---|
| ¿Existe un edge medido que alcance el listón? | **No.** EV bruta ≈ 0 en 240 combos de disparo, 400 celdas de deriva y el delta de apertura sobre 568 sesiones |
| ¿Se puede pasar la cuenta en 3 meses? | Sí, con probabilidad `0.257` por intento y sin edge, jugando audaz. Mediana 2 días |
| ¿Es racional hacerlo? | **No** como negocio: EV `−$133` por intento. Sí como apuesta consciente si se acepta que es una apuesta |
| ¿Qué falta para que sea racional? | Un edge de `+8` a `+12` ticks netos por trade con `>= 1 trade/día`. Ahí `P(pasar)` sube a `0.47` y `P(payout)` a `0.84` |

## 6. Lo que queda por probar

La búsqueda cerró cinco representaciones de la sesión RTH. Queda una superficie
grande y no explorada: **la sesión overnight**. Los datos ya están comprados y en
disco (`nq_es_1m_20220424_20260630.dbn.zst`, NQ+ES 1 minuto, 2022-04 a 2026-06),
y hasta ahora sólo se pensaron como un feature para decidir un único trade a las
09:35. Como sesión operable es territorio virgen y, a diferencia de sumar
instrumentos correlacionados, sí puede aportar caudal independiente porque es
otro horario y otro régimen de liquidez.

Ese es el siguiente test, y no requiere gastar en data.

`INFORMATION_STATUS=LUCID150K_POLICY_AND_FARM_ECONOMICS`
