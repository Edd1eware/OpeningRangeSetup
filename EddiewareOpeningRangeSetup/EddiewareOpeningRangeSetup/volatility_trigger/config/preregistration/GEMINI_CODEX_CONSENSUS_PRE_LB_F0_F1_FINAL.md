# Consenso final Gemini-Codex: PRE-LB F0/F1 outcome-blind

Fecha: 2026-07-27  
Línea: `PRE_LB_PRECURSOR_EXPLORATORY_V1`  
Audit ID: `PRE_LB_PRECURSOR_F0_F1_OUTCOME_BLIND_V1`

## Veredictos externos y conjunto

```text
GEMINI_CODE_REVIEW_F0_RUNNER_PRE_FREEZE: PASS
GEMINI_CODEX_PILOT_RUNTIME_CONSENSUS: PASS
GEMINI_CODEX_F0_F1_JOINT_REVIEW: PASS
```

Codex coincide con los tres veredictos bajo las restricciones de este
documento.

El `PASS` significa que F0/F1 fue ejecutado correctamente y que existe un
subdominio mecánicamente utilizable para diseñar F2. No significa que exista
señal predictiva, no repara el target padre y no autoriza abrir outcomes.

## Integridad

- Freeze manifest SHA256:
  `39DF6FBEC8571B87CCBDA9AB05E803AA39894A5EC8C2EE770263A51004C82F6B`.
- Pilot runtime SHA256:
  `F198F6F075287F1D0BBB6F18FA4C741756F7DCE377BFF4ED99C0A71D856534C2`.
- Output manifest SHA256:
  `3D4D434648342F8386160A895B130F7A1F8BF002CB9C1E2557F584ABCE19BD5E`.
- Los 10 outputs enumerados por `manifest.json` reproducen su SHA256.
- Suite pre-freeze: `54/54 PASS`.
- Labels, outcomes, modelos, validation y holdout permanecieron cerrados.

## Resultado de proceso

```text
depth sessions                         111 / 111
eligible after frozen trade QC         104 / 104
liquidity bursts                      2727 / 2727
VALID references                      2560 / 2560
invalid references                     167 / 167
PROCESS_ERROR                            0
row alignment / exclusive causes      PASS
level nesting                         PASS
forbidden output columns              PASS
```

Las 167 referencias inválidas son:

```text
SPREAD_GT_4       102
SPREAD_LE_0        65
```

El padre conserva:

```text
REGIME_V3_TARGET_DISCOVERY_FAIL
```

F0/F1 no puede rescatarlo.

## Conclusión mecánica sobre market depth

La cobertura condicional al tiempo `fresh-valid` es 100% para
`k in {1,3,5,10}` en agregado y en cada una de las 104 sesiones. Para L10,
la distancia p50 y p95 es 9 ticks en ambos lados. Esto valida exclusivamente
el vecindario local Top-10.

No valida el libro completo. El libro incremental conserva una cola publicada
grande:

- mediana aproximada de 627 niveles bid y 633 ask;
- aproximadamente 92% de niveles a más de 50 ticks;
- aproximadamente 2.5% de niveles actualizados en los últimos 250 ms.

Además, aunque el estado es `VALID` en 111/111 sesiones a las 09:30, el conteo
mediano crece de aproximadamente 277 niveles a las 09:30 a aproximadamente
497 a las 09:40. El full-book no demuestra convergencia antes del open.

Por consenso:

- sólo Top-10 local puede entrar al catálogo F2;
- se prohíben features de full-depth, cola lejana, `TotalVolume`, centro de
  masa global o cualquier interpretación de que el libro completo convergió;
- pulls, adds, refill y depletion seguirán identificados únicamente como
  proxies de L2 agregado, nunca como MBO, cola individual, iceberg o spoofing;
- una feature depth sólo existe bajo estado causal `VALID` y freshness
  aplicable; fuera de ese estado es `NaN` con flags explícitos.

## Missingness y ventanas

Disponibilidad con la ventana completamente `fresh-valid`:

```text
1 s     2244 / 2727 = 0.8228822882
5 s     1560 / 2727 = 0.5720572057
30 s     439 / 2727 = 0.1609827649
```

Sesiones elegibles especialmente degradadas:

```text
2022-10-14   fresh-valid = 0.003957
2022-10-21   fresh-valid = 0.303265
2022-11-24   fresh-valid = 0.257529
2022-11-25   fresh-valid = 0.563774
```

Por consenso:

- ninguna sesión puede excluirse, recortarse o reponderarse para ocultar la
  degradación;
- no se permite imputación, LOCF, sustitución por cero ni threshold elegido
  después de ver outcomes;
- F2 debe conservar `NaN`, estado y coverage flags;
- la disponibilidad es parte del estimand condicional y debe reportarse;
- 30 s no puede describirse como una ventana universalmente disponible.

## Perfil causal trade-only

```text
profile raw available       2722 / 2727
profile drift 300s          2597 / 2727
VA exhausted                  0
```

Los cinco profiles ausentes ocurren con `profile_elapsed_seconds=0`. La
ausencia del drift es mecánica al inicio de sesión. F11 puede avanzar a F2
con `NaN` y flags explícitos, sin imputación.

El POC es exclusivamente session-to-date RTH y causal:

```text
trade event_time < source_second_ticks
```

Un POC calculado después del LB no puede ser predictor, filtro, target,
rescate ni evidencia de atracción causal.

## Dependencia entre LB

```text
overlap <= 1 s       1 / 2727
overlap <= 5 s      26 / 2727
overlap <= 30 s    254 / 2727 = 0.0931426476
```

F2 debe impedir pseudo-replicación mediante agrupación por sesión y un
tratamiento prerregistrado de clusters LB. Gemini consideró mecánicamente
válido tratar el cluster como unidad o aplicar ponderación determinista.
La elección exacta todavía está cerrada: deberá acordarse Gemini-Codex y
hashearse antes de outcomes. No se permite escoger entre alternativas por
performance.

## Baseline y corte causal de F2

El baseline obligatorio es price-history causal pre-LB. Toda observación del
baseline y de las features debe cumplir:

```text
event_time < source_second_ticks
```

Las ventanas permanecen fijas en 1/5/30 s. Ningún high/low, POC, flujo o
price-action de los 5-30 segundos posteriores al LB puede entrar como
predictor. El futuro `event_time > publish_ticks` pertenece exclusivamente al
outcome congelado.

F2 debe probar aporte incremental del Top-10/profile respecto al baseline; no
se permite interpretar una asociación redundante con price-history como señal
propia del libro o del perfil.

## Autorizado y pendiente

Autorizado:

1. redactar el catálogo F2 outcome-blind;
2. acordar con Gemini la unidad de cluster, missingness, estimand y protocolo
   de inferencia/modelo;
3. generar manifest y SHA256 antes de abrir outcomes.

Todavía prohibido:

- leer o unir labels/outcomes;
- calcular asociaciones feature-outcome;
- seleccionar features, thresholds o ventanas;
- entrenar modelos;
- abrir validation u holdout;
- usar sensitivity para rescatar un FAIL;
- concluir que existe predictibilidad.

`INFORMATION_STATUS=PRE_LB_F0_F1_GEMINI_CODEX_PASS_WITH_MECHANICAL_LIMITATIONS`
