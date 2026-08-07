# Prerregistro final del target post-LB V3

Fecha: 2026-07-27

ID: `POST_LB_REGIME_V3_CURRENT_QUOTE_RESOLVED_WITH_ABSTENTION`

Estado: `BEFORE_V3_DISCOVERY_TARGET_LABELS`

## Origen de V3

V3 corrige un defecto de proceso: la referencia anterior podía conservar una
quote válida histórica cuando el libro vigente en `tLB` era inválido. La
intención ya congelada exigía simultáneamente:

```text
reference <= tLB
depth age <= 250 ms
current spread in [1, 4] ticks
```

La auditoría técnica reprodujo 111/111 referencias anteriores y encontró cinco
falsas aceptaciones. Con estado vigente válido quedaron 106/111.

V1 de cuatro clases conserva su resultado `REGIME_TARGET_INVALID`.

## Selección mecánica del threshold

Antes de recalcular clases se congeló la regla:

```text
8 -> 12 -> 4 -> 16 ticks
```

Se toma el primer threshold que pasa los gates mecánicos aplicados a las clases
resueltas, mientras `AMBIGUOUS` se trata como abstención.

Resultado corregido a MID, 5 s y ambigüedad 250 ms:

| Threshold | C | R | N | A | Gate decisivo |
|---:|---:|---:|---:|---:|---|
| 8 | 46 | 36 | 23 | 1 | TVD 0.167667 > 0.15 |
| 12 | 34 | 25 | 47 | 0 | TVD 0.187523 > 0.15 |
| 4 | 52 | 48 | 0 | 6 | `NO_EXPANSION=0` |
| 16 | 27 | 19 | 60 | 0 | PASS |

Para 16 ticks:

- cobertura: 106/111 = 0.954955;
- mínimo por clase resuelta: 19;
- clase resuelta máxima: 0.566038;
- TVD BUY/SELL: 0.128830;
- presencia mínima: 4 sesiones;
- concentración máxima por sesión: 0.526316;
- acuerdo MID/ejecutable: 0.971698;
- estabilidad ambigüedad/threshold/horizonte:
  1.000000/0.962264/0.962264.

Calcular TVD incluyendo o excluyendo `AMBIGUOUS` no cambia PASS/FAIL en ningún
threshold. El resultado no depende de ese grado de libertad.

## Definición V3

```text
reference = LB_Mid del estado causal vigente y válido
threshold = 16 ticks
horizon = 5 seconds
ambiguity_window = 250 ms
spread = 1..4 ticks
max_depth_age = 250 ms
```

Clases resueltas:

```text
CONTINUATION
REVERSAL
NO_EXPANSION
```

Clase de abstención:

```text
AMBIGUOUS
```

`AMBIGUOUS` no se fusiona, renombra ni suma a otra clase.

## Jerarquía consumida

La jerarquía se consume una sola vez. Si 16 ticks incumple cualquier gate en
discovery:

```text
REGIME_V3_TARGET_DISCOVERY_FAIL
```

Está prohibido volver a 8, 12 o 4 ticks, volver a recorrer la jerarquía o
rescatar el target con otra definición.

## Gates discovery sin cambios

- al menos 500 LB válidos;
- al menos 100 ejemplos por clase resuelta;
- cada clase resuelta en al menos 6 meses;
- ninguna clase resuelta supera 70%;
- TVD BUY/SELL resuelta `<=0.15`;
- ningún mes concentra más de 35% de una clase resuelta;
- `AMBIGUOUS<=10%`;
- cobertura de referencia `>=95%` dentro de sesiones con depth.

Gate de proceso adicional:

```text
evaluated / eligible_after_frozen_QC = 1.00
```

`depth_present / weekdays` se reporta y no es gate. La cobertura outcome-blind
2022 es 111/195 = 0.569231; comienza el 2022-07-27.

`splits.discovery` no se recorta. Las cinco sesiones técnicas permanecen en el
discovery primario porque así estaba congelado. Se reportará sensibilidad
con/sin ellas, nunca como selección ni rescate.

## Riesgos registrados

1. Cinco exclusiones de quote cambian la elección de 8 a 16 ticks.
2. La cobertura técnica 106/111 supera 0.95 por aproximadamente un LB.
3. El corte TVD decide con sólo cinco sesiones; es protocolariamente válido,
   no evidencia de precisión estadística.
4. El significado pasa de expansión inicial a movimiento fuerte;
   `NO_EXPANSION` representa 60/106 en el set técnico.
5. `REVERSAL` es la clase escasa, 19/106.

Ningún riesgo autoriza modificar gates después de discovery.

## Causalidad y sellado

- `reference <= tLB`;
- outcome trades estrictamente `>tLB`;
- se persisten `quote_ticks`, `depth_age_ms` y `quote_group_lag_ms`;
- features/modelos permanecen cerrados hasta que el target pase;
- validation 2023, holdout 2024 y 2025–2026 permanecen sellados;
- split aleatorio por fila está prohibido.

`INFORMATION_STATUS=POST_LB_REGIME_V3_PREREGISTERED_TARGET_ONLY`
