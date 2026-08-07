# Consenso de diseño Claude–Codex: precursor pre-LB

Fecha: 2026-07-27  
Estado: `DESIGN_ONLY_BEFORE_OUTCOME_BLIND_F0`  
Línea: `PRE_LB_PRECURSOR_EXPLORATORY_V1`  
Target padre: `POST_LB_REGIME_V3_CURRENT_QUOTE_RESOLVED_WITH_ABSTENTION`

## Autorización y separación del target padre

El usuario autorizó explícitamente investigar si el Liquidity Burst es el
síntoma visible de una preparación anterior en el libro y si el perfil previo
aporta información sobre el movimiento posterior.

La línea es independiente y no rescata el target padre:

- V3 permanece `REGIME_V3_TARGET_DISCOVERY_FAIL / DATA_QUALITY_FAIL`;
- no se modifica el gate de cobertura 0.95;
- no se excluyen sesiones para voltear el resultado;
- no se vuelve a 8, 12 o 4 ticks;
- no se cambia threshold, horizonte, referencia ni ambigüedad;
- no se usa la sensibilidad como selección;
- validation 2023 y holdout 2024 siguen sellados.

La conclusión máxima posible es `DISCOVERY_ONLY_SIGNAL`. Nunca se afirmará que
la señal está validada ni que predice fuera de discovery 2022.
El tamaño efectivo es 104 sesiones, no 2560 LB.

## Estimando y censura

La existencia de la etiqueta depende del mismo libro del que salen los
predictores: 167 de 2727 LB carecen de referencia válida en `tLB`. Por tanto,
la disponibilidad no es aleatoria respecto del predictor.

El único estimando permitido es:

> Condicional a que el libro estuviera sano en `tLB`, ¿el libro y el perfil
> causal previos al LB aportan asociación predictiva incremental para la
> etiqueta congelada de régimen post-LB?

No se imputarán ni reponderarán los 167 eventos sin etiqueta. La censura se
caracterizará antes de calcular asociaciones.

## Etiqueta inmutable

El único outcome primario permitido es la etiqueta V3 ya congelada:

```text
16 ticks / 5 segundos / MID vigente / profundidad <=250 ms
spread 1–4 ticks / AMBIGUOUS como abstención
```

Se usarán las 2559 etiquetas resueltas de los 2560 eventos con referencia
válida. Queda prohibido crear un target binario, continuo o alternativo si el
primario no da señal.

## Corte causal y zonas

El corte predictor es:

```text
event_time < source_second_ticks
```

- Zona B, precursor: todo evento estrictamente anterior a
  `source_second_ticks`.
- Zona A, detector: `[source_second_ticks, publish_ticks]`; queda fuera del
  bloque precursor y sólo puede ser baseline del propio LB.
- Zona C, outcome: `event_time > publish_ticks`; nunca feature.

Usar `publish_ticks` como corte de features está prohibido porque incluiría el
segundo que activa el detector.

Ventanas pre-LB fijas, sin barrido:

```text
W_SHORT = [t_cut-1s, t_cut)
W_MED   = [t_cut-5s, t_cut)
W_LONG  = [t_cut-30s, t_cut)
W_SESSION = [09:30 NY, t_cut)
W_PROFILE_DRIFT = 300s
```

No se añadirán ventanas de 2, 3, 10, 60 o 600 segundos para buscar resultados.

## Datos y límites de medición

`marketdepth.dat` contiene L2 agregado por precio. No contiene order IDs.

Permitido:

- profundidad e imbalance por niveles técnicamente disponibles;
- slope/convexity si la profundidad real los soporta;
- microprice, spread, compresión y drift;
- tasa de updates y churn del libro;
- volatilidad/compresión pre-evento;
- flujo de trades pre-evento;
- `ProxyPull`, `ProxyAdd`, `ProxyRefill` y
  `ProxyLevelDepletion`.

No identificable y fuera de alcance:

- posición o vida de una orden;
- cola MBO real;
- icebergs o spoofing;
- cancelación frente a ejecución sin el prefijo `Proxy`;
- informed flow como hecho observado.

## Fases outcome-blind F0/F1

Ninguna fase de esta sección puede importar el parquet de etiquetas ni usar
`regime`, tiempos de cruce o excursiones futuras. Los 2727 LB y sus
`source_second_ticks` se re-derivan desde el detector trade-only; nunca se
leen del parquet que también contiene outcomes.

### F0 — calidad del libro y profundidad real

Entregables:

```text
session_quality.csv
book_depth_characterization.csv
F0_F1_result.json
manifest.json
```

`session_quality.csv`, sobre las 111 sesiones con depth presente, reportará:

- fracción de tiempo RTH con libro bilateral y spread 1–4;
- fracción `fresh-valid`: lo anterior y edad del último grupo depth global
  `<=250 ms`;
- duración por causa inválida: libro unilateral, spread <=0, spread >4 y sin
  estado previo;
- update rate de rows y timestamp-groups;
- gap mediano, p95, p99 y máximo;
- cantidad de gaps >250 ms;
- distribución duration-weighted de spread;
- QC causal de timestamps.

`book_depth_characterization.csv` reportará, duration-weighted:

- niveles activos por BID, ASK y mínimo de ambos lados;
- p05, mediana y p95;
- fracción del tiempo válido con al menos 1, 3, 5 y 10 niveles por lado.

Regla mecánica de viabilidad de niveles, fijada antes de observar:

1. **Nivel publicado activo.** El libro es L2 incremental:
   `volume_raw>0` fija o actualiza el nivel de ese precio y `volume_raw==0` lo
   borra. Un nivel permanece activo hasta un update posterior o borrado
   explícito. No caduca por antigüedad individual.
2. **Tiempo fresh-valid.** Base duration-weighted única: RTH con libro
   bilateral, spread 1–4 ticks y edad del último grupo depth global `<=250
   ms`.
3. **Existencia de Lk.** Por lado se ordenan niveles activos por proximidad al
   best. `Lk` existe si hay al menos `k`; es ordenación por rango y no exige
   contigüidad de precios.
4. **Diagnósticos obligatorios no decisorios.** Por lado y duration-weighted se
   reportan distancia del nivel `k` al best —p50, p95 y máximo—,
   `published_level_count` y `far_level_share_gt50`. No descartan niveles ni
   deciden `k`.
5. **Criterio.** Un `k` de {1,3,5,10} es viable sólo si ambos lados mantienen
   al menos `k` niveles activos durante `>=99%` del tiempo fresh-valid agregado
   y `>=95%` en cada sesión. El universo decisor son las 104 sesiones
   elegibles; las 111 con depth son contexto. Se reportan la binding session,
   margen frente a 95% y distribución por sesión.
6. El conjunto viable debe ser anidado. Toda violación detiene F0 como defecto
   de implementación.
7. Queda prohibido excluir, recortar, reponderar o truncar temporalmente
   sesiones para habilitar un `k` mayor. Si ningún `k>1` pasa, sólo L1 es
   admisible y las familias multinivel quedan no computables.
8. `recently_updated_level_count_250ms` y su share frente a
   `published_level_count` se reportan sólo como diagnóstico de residuo; nunca
   definen nivel activo ni deciden `k`.
9. **Convergencia de arranque.** El libro se reconstruye desde vacío a las
   09:25 NY y el formato no contiene snapshot, reset ni clear-book. Se
   reportará `published_level_count` por lado en cortes de un minuto durante
   los primeros 15 minutos desde el inicio de carga. Si no converge antes de
   09:30, la decisión de ancla/warm-up se escala a acuerdo
   Claude–Codex–usuario; queda prohibido elegir el arranque que mejore `k`.
10. **Escalada por patología.** Si el conteo de niveles crece monótonamente
    junto con la distancia al nivel k, o el share de niveles actualizados
    recientemente es persistentemente muy inferior al publicado, la
    viabilidad de `k>1` queda `NO ESTABLECIDA` y sólo L1 es admisible hasta una
    enmienda separada. No se inventará un umbral post-hoc para automatizar este
    juicio.

F0 es descriptiva. Ninguna métrica de calidad puede excluir sesiones ni
convertir V3 en PASS.

### F1 — missingness, ventanas y clustering

Entregables:

```text
reference_missingness_audit.csv
pre_window_availability.csv
lb_clustering_audit.csv
profile_missingness_diagnostic.csv
```

Sobre los 2727 LB de las 104 sesiones elegibles:

- causa exacta de referencia disponible/ausente:
  `VALID`, `NO_PRIOR_DEPTH`, `ONE_SIDED_BOOK`, `SPREAD_LE_0`,
  `SPREAD_GT_4` o `STALE_DEPTH_GT_250MS`;
- disponibilidad completa de libro válido y feed fresco en 1, 5 y 30 s;
- tiempo desde LB previo any/same/opposite side;
- solapamiento con LB previo en 1, 5 y 30 s;
- disponibilidad e historia RTH del perfil.

Las métricas de perfil fijadas abajo se calcularán también para los 167
censurados, exclusivamente para caracterizar MNAR. No podrán modificarse,
seleccionarse o descartarse por ese diagnóstico.

La causa de missingness es única y tiene esta precedencia:

1. `NO_PRIOR_DEPTH`;
2. `ONE_SIDED_BOOK`;
3. `SPREAD_LE_0`;
4. `SPREAD_GT_4`;
5. si el estado es válido, `STALE_DEPTH_GT_250MS`;
6. `VALID`.

La edad se mide contra el último grupo depth global, no contra el último
registro de cambio de quote.

## Familia F11: perfil causal

Parámetros inmutables:

- trades con `event_time < source_second_ticks`;
- ancla RTH 09:30 NY;
- binning nativo de 1 tick;
- referencia de precio: último trade estrictamente anterior al corte;
- Value Area: 70%;
- drift POC: 300 segundos;
- sin HVN/LVN;
- unidades de precio en ticks y volumen en contratos;
- flags `_available`, sin imputación.

Features:

1. `PRF_PocSignedDistance_ticks`
2. `PRF_PocSide_Favor`
3. `PRF_VaSignedPositionNorm`
4. `PRF_InsideValueArea`
5. `PRF_VaWidth_ticks`
6. `PRF_PocDrift_ticks_300s`
7. `PRF_PocVolumeShare`
8. `PRF_ProfileEntropyNorm`

Regla POC:

1. nivel o niveles con volumen máximo;
2. empate: nivel empatado más cercano al último trade causal;
3. empate persistente: media aritmética de los precios restantes, conservada
   como ticks fraccionarios.

Regla Value Area:

1. `poc_candidates` son todos los precios con el volumen máximo;
2. la semilla es el intervalo cerrado entre el mínimo y el máximo candidato,
   incluyendo todo volumen negociado intermedio;
3. si la semilla ya acumula al menos 70%, terminar con
   `VAL=min(poc_candidates)`, `VAH=max(poc_candidates)` y
   `va_tie_steps=0`;
4. comparar el siguiente nivel negociado superior e inferior;
5. agregar el de mayor volumen;
6. en empate exacto, agregar ambos en el mismo paso;
7. si un lado se agota, continuar sólo por el otro;
8. si ambos se agotan antes de 70%, usar todos los niveles y marcar
   `va_exhausted=True`;
9. terminar al alcanzar al menos 70% del volumen.

Se persisten `poc_tie_count`, `va_tie_steps`, `n_levels_traded` y
`profile_total_volume`, además de `poc_candidate_span_ticks` y
`va_exhausted`.

`PRF_PocVolumeShare` se define exactamente como
`max_single_level_volume/profile_total_volume`, aunque existan varios POC
empatados. No se suma el volumen de todos los empatados ni se busca volumen en
un POC fraccional.

`PRF_PocDrift_ticks_300s` exige un snapshot causal en `t_cut-300s` con la misma
ancla RTH. Si ese instante es anterior a 09:30 NY, se marca
`PRF_PocDrift_ticks_300s_available=False`; no se imputa, sustituye ni recorta.

La afirmación máxima permitida es asociación incremental. Quedan prohibidas
las palabras `causa`, `genera`, `imán` o `atractor` para interpretar F11.

La causalidad no es identificable porque perfil y trayectoria proceden del
mismo proceso de mercado, existe causalidad inversa plausible entre perfil e
historia de precio, ambos están confundidos por régimen/hora/volatilidad y la
precedencia temporal por sí sola no demuestra causa.

## POC posterior

Un POC calculado con trades en `(publish_ticks, publish_ticks+5s]` usa la misma
ventana que forma la etiqueta y es endógeno al outcome.

Sólo podrá calcularse en F6, después de escribir y hashear el resultado
primario F5:

- fichero separado;
- prefijo obligatorio `OUT_PostLbPoc_`;
- nunca feature, target, filtro, estrato, peso o criterio de éxito;
- nunca rescate o reinterpretación del primario;
- descripción permitida: `precio modal del recorrido posterior`;
- prohibido llamarlo punto de atracción.

## Precursor frente a tautología

Los atributos del segundo detector —delta, z-score, percentil, trade rate,
contracts/s, velocidad y cumulative delta— no pertenecen al bloque precursor.
Se conservan sólo como baseline obligatorio.

Los LB con otro LB dentro de los 30 segundos se conservan. Se incluyen
`time_since_previous_LB` y `previous_lb_direction` como controles
preregistrados. La exclusión de eventos solapados se reportará únicamente como
sensibilidad secundaria y nunca seleccionará o rescatará el resultado.
Esa sensibilidad tendrá una sola definición: LB con otro LB de cualquier lado
dentro de `W_LONG=30s`. Las mediciones de 1 y 5 segundos en F1 son únicamente
descriptivas.

## F2–F6

- F2: después de F0/F1, acuerdo Claude–Codex y puerta del usuario; preregistro
  completo y hash antes de calcular la matriz.
- F3: matriz de features outcome-blind y `feature_lineage.json`; máximo 60
  features exactas listadas por nombre.
- F4: tests sintéticos anti-lookahead en verde.
- F5: único join feature–label y una sola evaluación discovery.
- F6: descriptores de POC futuro, sólo después de cerrar y hashear F5.

Tests mínimos:

- evento gigante después del corte no cambia ninguna feature;
- segundo detector excluido;
- ventanas left-closed/right-open;
- espejo BUY/SELL exacto;
- normalización sólo con pasado;
- missingness visible, no imputada;
- matriz sin outcomes ni columnas `OUT_*`;
- bloque precursor sin atributos del LB;
- POC ignora volumen futuro;
- empate POC determinista y simétrico;
- ancla 09:30 respetada;
- Value Area invariante al orden de trades.

## Protocolo anti-overfit para F2

F2 deberá fijar, antes de calcular features:

- catálogo exacto de máximo 60 features;
- valores únicos de `MIN_PROFILE_TRADES` y
  `MIN_PROFILE_ELAPSED_SECONDS`, fijados usando sólo la distribución
  outcome-blind de F1 y antes de F3; no podrán ajustarse después;
- una única métrica primaria incremental;
- baseline de tasas de clase;
- baseline de atributos del LB;
- baseline simple de velocidad/volatilidad pre-LB;
- baseline aleatorio;
- baseline de sola historia de precio, obligatorio para F11;
- split cronológico por sesión dentro de discovery, declarado no-holdout;
- bootstrap y permutación por sesión, no por LB;
- control Benjamini–Hochberg para familias secundarias;
- delta mínimo, alpha, q y regla de estabilidad mensual;
- criterio terminal de abandono en un solo disparo.

Si F11 no supera el baseline de sola historia de precio, sólo podrá
interpretarse como proxy de ubicación histórica.

## Estado

```text
ACUERDO_DISENO_PRELB: SI
ACUERDO_PERFIL_POC: SI
FEATURE_OUTCOME_ASSOCIATIONS_OPENED: false
MODELS_OPENED: false
VALIDATION_OPENED: false
HOLDOUT_OPENED: false
```
