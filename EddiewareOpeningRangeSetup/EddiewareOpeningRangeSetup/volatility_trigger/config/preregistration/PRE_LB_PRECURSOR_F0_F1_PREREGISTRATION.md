# Prerregistro F0/F1 outcome-blind del precursor pre-LB

Fecha: 2026-07-27  
Audit ID: `PRE_LB_PRECURSOR_F0_F1_OUTCOME_BLIND_V1`  
Estado: `BEFORE_REAL_F0_F1_DATA`

Este prerregistro ejecuta exclusivamente F0/F1 del consenso:

```text
config/preregistration/PRE_LB_PRECURSOR_CLAUDE_CODEX_DESIGN_CONSENSUS.md
```

## Propósito

Auditar, sin abrir outcomes:

1. calidad duration-weighted del libro RTH;
2. profundidad L2 publicada y convergencia desde el arranque 09:25;
3. causa de las 167 referencias ausentes;
4. disponibilidad causal de ventanas pre-LB 1/5/30 s;
5. clustering de LB;
6. perfil causal F11 sobre los 2727 LB como diagnóstico de missingness.

## Universo

- discovery 2022: 2022-04-04 a 2022-12-30;
- 111 sesiones con `marketdepth.dat` real;
- 104 sesiones elegibles tras el mismo QC trade congelado;
- las 111 se auditan como contexto;
- sólo las 104 deciden viabilidad de niveles y producen filas LB.

Los LB se re-derivan desde trades mediante el detector congelado. Está
prohibido leer el parquet de etiquetas para obtener LB o timestamps.

## Cortes causales

```text
feature/profile event_time < source_second_ticks
reference state event_time <= publish_ticks
future event_time > publish_ticks
```

F0/F1 nunca consulta el tercer conjunto.

## Outputs congelados

```text
session_quality.csv
book_depth_characterization.csv
book_startup_convergence.csv
reference_missingness_audit.csv
pre_window_availability.csv
lb_clustering_audit.csv
profile_missingness_diagnostic.csv
data_audit.csv
level_viability.csv
result.json
manifest.json
```

## Gates de proceso

- 111/111 sesiones depth auditadas;
- 104 sesiones elegibles reproducidas;
- 2727 LB trade-only reproducidos;
- 2560 `VALID` y 167 no válidos reproducidos;
- cero `PROCESS_ERROR`;
- causas de referencia mutuamente excluyentes;
- anidamiento de viabilidad L1/L3/L5/L10;
- ningún output contiene `regime`, tiempos de cruce, excursiones o `OUT_*`.

Si falla un gate, F0/F1 queda `PROCESS_FAIL` y no se abre F2.

## Viabilidad de niveles

Se aplica literalmente la regla aprobada en el consenso de diseño:

- nivel activo hasta update o volumen cero; sin expiración individual;
- tiempo fresh-valid basado en edad global depth `<=250 ms`;
- `k` en 1/3/5/10;
- `>=99%` agregado y `>=95%` en cada una de las 104 sesiones;
- ninguna sesión puede excluirse, recortarse o reponderarse para habilitar k;
- distancias, `far_level_share_gt50` y reciente/publicado son diagnósticos;
- patología o falta de convergencia se escala y no se resuelve post-hoc.

## Perfil

F11 usa trades RTH estrictamente anteriores a `source_second_ticks`, bin de un
tick, POC/Value Area simétricos y drift fijo de 300 s. F1 no aplica
`MIN_PROFILE_TRADES` ni `MIN_PROFILE_ELAPSED_SECONDS`; sólo persiste la
distribución ciega que permitirá fijarlos en F2.

## Prohibiciones

- no leer ni unir etiquetas;
- no entrenar modelos;
- no calcular POC posterior;
- no seleccionar features;
- no abrir validation/holdout;
- no cambiar el target V3;
- no excluir sesiones usando cobertura de LB;
- no convertir este audit en PASS del target padre.

`INFORMATION_STATUS=PRE_LB_F0_F1_OUTCOME_BLIND_PREREGISTERED`
