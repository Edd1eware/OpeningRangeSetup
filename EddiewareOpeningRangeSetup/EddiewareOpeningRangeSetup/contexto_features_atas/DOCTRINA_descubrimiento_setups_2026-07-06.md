# DOCTRINA — El camino repetible para descubrir setups cuando unos mueren (2026-07-06)

## Principio raíz
El entregable NO es un setup inmortal. Los edges mueren y nacen con el régimen. El activo
durable es la **fábrica de descubrir edge** (captura causal + replay + MC + era-split + gate
forward). Un setup es un producto desechable de la fábrica. Aprender el **camino** > tener un edge.

Objetivo del negocio (ver `objective_payout_farming`): farmear payouts (pasar→farmear→si truena,
repetir). No se necesita sobrevivir 5 años; se necesita EV>0 + cojín para farmear antes de quemar,
y un proceso para rotar al edge nuevo cuando el viejo decae.

---

## El embudo de descubrimiento (cada paso mató algo antes en este proyecto)

| # | Paso | Lección/cicatriz que lo justifica |
|---|---|---|
| 1 | **Hipótesis desde estructura de mercado**, no de minar datos | cartera candle minada full-sample murió; empezar por *por qué* ocurre el movimiento |
| 2 | **Captura causal**: todo congelado con info ANTES de la señal | look-ahead = asesino #1 (ORB m1v_5 "grande no es raro"); arquitectura freeze-at-signal (como ventanas VP 09:30) |
| 3 | **Label alcanzable y = al bracket real del trade** | +60t sobre slide de 20-min roto (base rate 1.5%, fwd_bars med 2) |
| 4 | **Split era-blind / walk-forward desde el día 1** (nunca optimizar in-sample) | meta-label y veto candle REPROBARON fresh holdout |
| 5 | **Matar barato**: univariada + stats simples antes de ML pesado | la mayoría de familias muere aquí; no enamorarse |
| 6 | **Disciplina de n chico**: pocas features, modelo shallow, reportar CI | ~1 trade/día ⇒ ~250/año; OR-CB ya marcaba "n chico" con n=90; 293 features vs ~110 trades = overfit seguro |
| 7 | **Gauntlet de robustez**: cross-asset + cross-era + MC path + breakeven explícito | ES cuarentena (edge solo-NQ); batería `next_session_es_replication` |
| 8 | **Forward paper antes de subir tamaño** (gate ~2 meses EV>0, PF>1.15) | gate ATRAPADOS |
| 9 | **Banco + rotación**: survivors congelados y documentados, listos a jalar | cuando el régimen mata uno, entra el siguiente |

---

## Ya construido vs lo que falta

**Construido (lo caro):** captura causal, replay/featsweep, MC payout-farming, era-split,
batería robustez, gate forward. La fábrica existe.

**Falta (barato pero clave):**
| Pieza | Función |
|---|---|
| **Front-end de hipótesis** | de dónde salen setups nuevos: estratificar data por régimen (vol/trend) y buscar edge CONDICIONAL (plano en el pool completo, vivo dentro de un régimen); analizar near-miss (señales rechazadas + su outcome) |
| **Detector de régimen** | monitor EV/día rolling-20 vs intervalo del backtest; cuando cae bajo breakeven N trades → bandera "edge decayendo" → downsize/pausa antes de la quema (control chart / CUSUM) |
| **Checklist codificado** | que ningún candidato salte un paso del embudo (error humano bajo emoción/sunk-cost) |

---

## El insight que amarra todo
El paso 1 (hipótesis) es el único creativo y no se automatiza — PERO se sistematiza la **fuente**:
al cambiar el régimen, el **order-flow cambia de carácter primero** (ya operas CVD/imbalance).
Estratificas por régimen → los setups que nacen aparecen como **edges condicionales**. Ahí CatBoost
SÍ sirve: **descubrir el edge condicional nuevo**, no ordeñar PF del viejo (PF 3 sin matar
frecuencia = fantasma; realista 1.4→1.6-1.8 pagando frecuencia).

## Reencuadre de CatBoost
Herramienta de la fábrica para DESCUBRIMIENTO, no ordeñe. Su mejor uso en el edge actual:
recortar los peores días de pérdida para **cortar quemas** (mueve el farm más que subir PF),
no perseguir PF 3.
