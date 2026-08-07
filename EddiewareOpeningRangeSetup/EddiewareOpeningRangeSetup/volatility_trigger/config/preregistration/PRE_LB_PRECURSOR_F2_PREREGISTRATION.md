# Prerregistro F2 del precursor pre-LB

Fecha: 2026-07-27  
Audit ID: `PRE_LB_PRECURSOR_F2_PREREGISTRATION_V1A`  
Estado: `BEFORE_F3_OUTCOME_BLIND_FEATURE_MATRIX`

## 1. Autorización

Este prerregistro implementa el siguiente consenso:

```text
GEMINI_F2A_CATALOG_CONSENSUS: PASS
GEMINI_F2B_PROTOCOL_CONSENSUS: PASS
GEMINI_F2_SUPPORT_AMENDMENT: APPROVE
```

F2 sólo fija catálogo, lineage, supports y protocolo de evaluación. En esta
fase continúa prohibido leer o unir labels, calcular asociaciones, entrenar
modelos, abrir validation o abrir holdout.

### 1.1 Enmienda técnica de supports W5/W30

Antes de abrir cualquier dato real F3, Codex detectó que los secundarios ya
prerregistrados nombraban `COMBINED_W5_SUPPORT` y
`COMBINED_W30_SUPPORT`, pero F2 V1 sólo había definido y persistido
`COMBINED_W1_SUPPORT`. Gemini y Codex coincidieron en que era una omisión
estructural bloqueante y aprobaron corregirla antes del freeze F3.

La enmienda no cambia las 60 features, ventanas, modelos, gates ni regla
terminal. Sólo completa dos máscaras outcome-blind para las muestras matched
de comparaciones secundarias ya fijadas. Ambas siguen siendo metadata y
quedan prohibidas como predictor, filtro global o rescate.

## 2. Pregunta y estimand

Pregunta:

> Condicionado a que el libro sea mecánicamente utilizable, ¿el Top-10 local
> y el perfil causal pre-LB añaden capacidad predictiva respecto de un
> baseline causal de atributos del LB, precio y tape?

El target padre conserva:

```text
REGIME_V3_TARGET_DISCOVERY_FAIL
```

El resultado máximo de esta línea es `DISCOVERY_ONLY_SIGNAL`. No rescata el
padre ni autoriza validación automáticamente.

## 3. Guard contra contaminación histórica

Durante la preparación F2 se encontró un documento de otra investigación
2025–2026 con AUCs y una shortlist outcome-informed. No contiene los labels V3
actuales, pero podría contaminar selección.

Por tanto:

- se ignoran todos sus AUCs, rankings, direcciones y shortlists;
- ninguna feature se incluye por performance histórica;
- sólo se reutilizan definiciones físicas justificables de forma
  outcome-blind;
- el catálogo de este documento es terminal y no admite pruning por outcome.

## 4. Corte causal

```text
predictor/profile event_time < source_second_ticks
detector zone                [source_second_ticks, publish_ticks]
outcome event_time           > publish_ticks
```

Ventanas:

```text
W1  = [source_second_ticks-1s,  source_second_ticks)
W5  = [source_second_ticks-5s,  source_second_ticks)
W30 = [source_second_ticks-30s, source_second_ticks)
```

No se añadirán ni barrerán ventanas.

Los atributos `BLB_*` pertenecen al detector y sólo son baseline. Nunca se
presentarán como precursor.

## 5. Universo y conservación de filas

- Se re-derivan 2727 LB trade-only en las 104 sesiones elegibles.
- La matriz F3 conserva exactamente 2727 filas.
- Ninguna sesión o evento se elimina por calidad, support o clustering.
- Ausencia se representa con `NaN` y columnas de support.
- Los supports se escriben y hashean antes de abrir labels.
- Una prueba futura utiliza una máscara únicamente si quedó nombrada y
  congelada en F3.

## 6. Semántica direccional

`direction=+1` para BUY y `direction=-1` para SELL.

Una feature con sufijo `_Favor` está normalizada de forma que valores
positivos favorecen la dirección del LB. Bajo espejo completo de precios,
lados y dirección, debe permanecer invariante.

Las features no direccionales deben permanecer iguales bajo el mismo espejo.

## 7. Baseline del detector y controles — 11

```text
BLB_Delta1s_Favor
BLB_Delta3s_Favor
BLB_DeltaChangeZ_Favor
BLB_DeltaPercentile
BLB_TradesPerSecond
BLB_ContractsPerSecond
BLB_Velocity1s_Favor
BLB_Acceleration1s_Favor
CTL_RthElapsed_seconds
CTL_LbOrdinalPriorCount
CTL_PriorLbWithin30s
```

Definiciones direccionales:

```text
BLB_Delta1s_Favor          = direction * delta_1s
BLB_Delta3s_Favor          = direction * delta_3s
BLB_DeltaChangeZ_Favor     = direction * delta_change_zscore
BLB_Velocity1s_Favor       = direction * velocity_1s
BLB_Acceleration1s_Favor   = direction * acceleration_1s
```

`CTL_PriorLbWithin30s` sólo consulta el LB anterior en la misma sesión. No
consulta el siguiente LB.

## 8. Baseline de historia de precio — 9

Para `W in {1,5,30}`:

```text
PX_NetMoveFavor_ticks_pre_Ws
PX_Range_ticks_pre_Ws
PX_PathEfficiencyFavor_pre_Ws
```

Sobre trades de la ventana:

```text
net_favor = direction * (last_price - first_price)
range     = max_price - min_price
path      = sum(abs(price_i - price_i-1))
eff       = net_favor / path, con eff=0 si path=0
```

Con cero o un trade, net, range y efficiency valen cero. Esto describe
ausencia observada de movimiento; no es imputación de un valor faltante.

## 9. Baseline de tape — 12

Para `W in {1,5,30}`:

```text
TAPE_TradeRate_pre_Ws
TAPE_ContractRate_pre_Ws
TAPE_DeltaImbalanceFavor_pre_Ws
TAPE_AggressorSizeLogRetention_pre_Ws
```

Definiciones:

```text
TradeRate    = trade_count / W
ContractRate = contract_volume / W
DeltaImbalanceFavor =
    direction * (buy_volume-sell_volume) / max(total_volume,1)
```

Para retention se divide la ventana en dos mitades. Se usan sólo prints del
agresor alineado con la dirección del LB:

```text
log((mean_size_second_half + 1) / (mean_size_first_half + 1))
```

Una mitad sin prints alineados tiene media observada cero. El `+1` es
pseudoconteo fijo y no se ajusta.

## 10. Estado Top-10 en `cut-` — 8

```text
DOM_Spread_ticks
DOM_MicropriceOffsetFavor_ticks
DOM_ImbalanceL1_Favor
DOM_ImbalanceL3_Favor
DOM_ImbalanceL5_Favor
DOM_ImbalanceL10_Favor
DOM_AheadDepthPerLbContractsL3
DOM_AheadL1ConcentrationL5
```

`DOM_STATE_SUPPORT=True` exige:

1. último group depth con timestamp estricto `<source_second_ticks`;
2. edad global `<=250 ms`;
3. libro bilateral;
4. spread entre 1 y 4 ticks;
5. al menos diez niveles activos por lado.

En caso contrario las ocho features son `NaN`.

Para nivel `k`:

```text
imbalance_k = direction *
    (sum_bid_depth_k-sum_ask_depth_k)
    / max(sum_bid_depth_k+sum_ask_depth_k,1)
```

Microprice usa best bid/ask y sus tamaños L1. Offset:

```text
direction * (microprice-midpoint)
```

Ahead side es ASK para BUY y BID para SELL:

```text
AheadDepthPerLbContractsL3 =
    ahead_depth_L3 / max(BLB_ContractsPerSecond,1)

AheadL1ConcentrationL5 =
    ahead_depth_L1 / max(ahead_depth_L5,1)
```

## 11. Dinámica Top-10 — 12

Para `W in {1,5,30}`:

```text
DOM_ImbalanceL10MeanFavor_pre_Ws
DOM_MicropriceDriftFavor_ticks_pre_Ws
DOM_ProxyDirectionalStackPullBalanceL10_pre_Ws
DOM_NearChurnTurnoversPerSecondL10_pre_Ws
```

`DOM_W_SUPPORT=True` sólo si toda la ventana es `fresh-valid`. Si existe
cualquier intervalo inválido o stale, las cuatro features de esa ventana son
`NaN`.

Definiciones:

- `ImbalanceL10MeanFavor`: promedio duration-weighted.
- `MicropriceDriftFavor`: `direction*(microprice_cut_minus -
  microprice_window_start)`.
- Para cada group se usa la unión de Top-10 inmediatamente antes y después del
  group. Sólo se cuentan updates reales a precios de esa unión.
- `delta_bid` y `delta_ask` son cambios firmados de volumen publicado.

```text
ProxyDirectionalStackPullBalance =
    direction * (sum(delta_bid)-sum(delta_ask))
    / max(sum(abs(individual_delta_volume)),1)
```

```text
NearChurnTurnoversPerSecond =
    sum(abs(individual_delta_volume))
    / max(duration_weighted_mean_top10_total_depth * W,1)
```

Son proxies MBP. No identifican cancelaciones, ejecuciones, refill MBO,
icebergs, spoofing ni posición en cola.

## 12. Perfil F11 — 8

```text
PRF_PocSignedDistance_ticks
PRF_PocSide_Favor
PRF_VaSignedPositionNorm
PRF_InsideValueArea
PRF_VaWidth_ticks
PRF_PocDrift_ticks_300s
PRF_PocVolumeShare
PRF_ProfileEntropyNorm
```

Se conserva la definición ya aprobada:

- trades RTH estrictamente anteriores al corte;
- anchor 09:30 NY;
- bins de un tick;
- Value Area 70%;
- drift fijo de 300 s;
- POC/VA deterministas y simétricos;
- sin HVN/LVN.

`PROFILE_F11_SUPPORT=True` exige:

```text
profile raw available
drift 300s available
profile_trade_count >= 500
profile_elapsed_seconds >= 1
las ocho features finitas
```

F1 mostró que los 2722 perfiles raw tienen al menos 505 trades y tres segundos
de historia. El gate 500/1 no selecciona adicionalmente esa muestra; excluye
los cinco profiles vacíos al open y los 125 sin drift.

## 13. Catálogo terminal

```text
detector + controls       11
price baseline             9
tape baseline             12
DOM state                  8
DOM dynamics              12
profile F11                8
TOTAL                      60
```

Flags, timestamps, lineage, IDs y cluster metadata no son predictores y no
cuentan dentro de 60.

## 14. Supports y comparación justa

Se persisten:

```text
BASELINE_SUPPORT
DOM_STATE_SUPPORT
DOM_W1_SUPPORT
DOM_W5_SUPPORT
DOM_W30_SUPPORT
PROFILE_RAW_SUPPORT
PROFILE_F11_SUPPORT
COMBINED_W1_SUPPORT
COMBINED_W5_SUPPORT
COMBINED_W30_SUPPORT
LB_CLUSTER_ID_30S
LB_CLUSTER_SIZE_30S
```

```text
COMBINED_W1_SUPPORT =
    BASELINE_SUPPORT
    & DOM_STATE_SUPPORT
    & DOM_W1_SUPPORT
    & PROFILE_F11_SUPPORT

COMBINED_W5_SUPPORT =
    BASELINE_SUPPORT
    & DOM_STATE_SUPPORT
    & DOM_W5_SUPPORT
    & PROFILE_F11_SUPPORT

COMBINED_W30_SUPPORT =
    BASELINE_SUPPORT
    & DOM_STATE_SUPPORT
    & DOM_W30_SUPPORT
    & PROFILE_F11_SUPPORT
```

Cada baseline y modelo aumentado se evalúan sobre exactamente las mismas filas
de su comparación. Queda prohibido comparar scores obtenidos sobre poblaciones
distintas.

W1 es el dominio DOM primario por su disponibilidad outcome-blind. W5 y W30
son secundarios. W30 deberá describirse como altamente condicionado; no se
generaliza a todos los LB.

## 15. Clustering

Los clusters son connected components por sesión: dos LB consecutivos
pertenecen al mismo cluster si su gap es `<=30 s`.

El cluster completo puede usar el gap siguiente únicamente como metadata de
dependencia. Se prohíbe usar ID, tamaño o pertenencia futura como predictor,
filtro o peso.

La única feature causal relacionada es:

```text
CTL_PriorLbWithin30s
```

No habrá sensibilidad excluyendo clusters. La dependencia se maneja mediante
splits, bootstrap y permutación dentro de sesión.

## 16. Target futuro inmutable

F5 podrá unir una sola vez el target:

```text
16 ticks / 5 s / current MID / depth age <=250 ms / spread 1-4
```

Clases:

```text
CONTINUATION
REVERSAL
NO_EXPANSION
```

`AMBIGUOUS` es abstención. No se fusiona, renombra ni convierte en target
binario/continuo.

## 17. Folds discovery

Las 104 sesiones elegibles se ordenan cronológicamente y se usan por posición:

```text
fold 1  train 1-40   test 41-56
fold 2  train 1-56   test 57-72
fold 3  train 1-72   test 73-88
fold 4  train 1-88   test 89-104
```

Sólo las predicciones de test son OOF. Si cualquier train/test fold o el OOF
total carece de una clase resuelta, se declara `PROCESS_FAIL`; no se cambian
folds.

## 18. Modelos fijos

Pipeline único:

```text
StandardScaler train-fold only
Multinomial Logistic Regression
L2
C=1.0
solver=lbfgs
max_iter=10000
class weight = n_train/(3*n_train_class), train-fold only
```

No hay tuning, selección, pruning, calibración, ensembles ni modelos
alternativos.

Baselines:

```text
B_UNIFORM
B_TRAIN_CLASS_RATE
B_RANDOM_DIRICHLET_SEED_20260727
B_LB
B_PRICE
M0_BASE = BLB + controls + PX + TAPE
```

Modelos aumentados:

```text
M_DOM_W1 = M0_BASE + DOM state + DOM W1
M_PRF    = M0_BASE + F11
M_ALL_W1 = M0_BASE + DOM state + DOM W1 + F11
```

## 19. Primary único

```text
M_ALL_W1 vs M0_BASE
support = COMBINED_W1_SUPPORT
```

Métrica:

```text
BMLL = mean over the 3 classes(
           mean(-log(probability_of_true_class) within class)
       )

Delta = BMLL(M0_BASE) - BMLL(M_ALL_W1)
```

Delta positivo significa mejora.

## 20. Gates primarios terminales

Todos deben pasar:

1. `Delta >= 0.01`.
2. Bootstrap de 2000 remuestreos de sesiones, seed `20260727`;
   límite inferior CI95 estrictamente `>0`.
3. Permutación circular intrasesión de labels, 1000 repeticiones, seed
   `20260727`; refit completo y `p<=0.05`.
4. Delta positivo en al menos 3 de 4 folds.
5. Delta BUY estrictamente positivo.
6. Delta SELL estrictamente positivo.

Permutación:

- ordenar eventos por `source_second_ticks` dentro de cada sesión;
- para una sesión con `n>1`, rotar el vector completo de labels por un offset
  uniforme no cero entre 1 y `n-1`;
- una sesión con `n=1` permanece sin cambio;
- no se fijan ni protegen clases concretas durante la rotación;
- se conserva la secuencia/autocorrelación interna pero se rompe su alineación
  con las features.

## 21. Secundarios

Cinco comparaciones:

```text
M_DOM_W1 - M0_BASE, matched DOM_W1 support
M_PRF - M0_BASE, matched PROFILE_F11 support
B_PRICE+F11 - B_PRICE, matched PROFILE_F11 support
M_ALL_W5 - M_ALL_W1, matched COMBINED_W5 support
M_ALL_W30 - M_ALL_W5, matched COMBINED_W30 support
```

Control Benjamini–Hochberg:

```text
q <= 0.10
```

Ningún secundario, side, mes, cluster, sensibilidad o descriptor de POC futuro
puede rescatar el primary.

## 22. Regla terminal

```text
si falla cualquier gate primary:
    NO_DISCOVERY_SIGNAL_CLOSE_LINE

si pasan todos:
    DISCOVERY_ONLY_SIGNAL
```

Un PASS no abre validation/holdout automáticamente y no repara V3.

## 23. Fases restantes

```text
F3  matriz outcome-blind + feature_lineage + supports + hashes
F4  tests sintéticos anti-lookahead/simetría
F5  freeze y único join/evaluación discovery
F6  POC posterior descriptivo sólo después de hashear F5
```

Antes de F3 se requiere aprobación Gemini del documento y config actuales.

## 24. Prohibiciones

- No labels/outcomes antes del freeze F3.
- No evento en o después de `source_second_ticks` dentro del precursor.
- No post-LB POC como predictor.
- No full-depth ni cola lejana.
- No imputación o LOCF.
- No excluir sesiones pobres.
- No filtrar o ponderar clusters.
- No sweep de ventanas, thresholds, modelos o hiperparámetros.
- No ranking/pruning outcome-informed.
- No validation/holdout.
- No rescate del parent V3.

`INFORMATION_STATUS=PRE_LB_F2_V1A_PREREGISTERED_BEFORE_OUTCOME_BLIND_MATRIX`
