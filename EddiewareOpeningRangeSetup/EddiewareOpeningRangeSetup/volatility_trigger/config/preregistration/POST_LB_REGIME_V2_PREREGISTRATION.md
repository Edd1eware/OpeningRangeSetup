# Prerregistro final del target post-LB V2

Fecha: 2026-07-27

ID: `POST_LB_REGIME_V2_RESOLVED_WITH_ABSTENTION`

Estado: `BEFORE_DISCOVERY_REGIME_LABELS`

## Evidencia que activa V2

La auditoría V1 fue congelada antes de etiquetas reales y concluyó
`REGIME_TARGET_INVALID` para modelar cuatro clases.

En el threshold 8 ticks, horizonte 5 s, referencia MID:

```text
CONTINUATION 47
REVERSAL     40
NO_EXPANSION 23
AMBIGUOUS     1
```

8 ticks era el primer threshold de la jerarquía congelada `8→12→4→16` y pasó:

- cobertura 1.00;
- clase máxima 0.423;
- TVD BUY/SELL 0.141;
- acuerdo MID/ejecutable 0.874;
- estabilidad ambigüedad 0.991;
- estabilidad threshold ±1 tick 0.865;
- estabilidad horizonte 4.5/5/5.5 s 0.955.

Falló exclusivamente porque `AMBIGUOUS` no tiene muestra para convertirse en
una cuarta clase aprendible.

## Definición V2

Se mantienen sin cambios:

```text
reference = LB_Mid
threshold = 8 ticks
horizon = 5 seconds
ambiguity_window = 250 ms
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

`AMBIGUOUS` se preserva como outcome separado. No se fusiona, renombra ni suma
a `NO_EXPANSION`. Se excluye de la pérdida del clasificador resuelto y se
reporta como cobertura/abstención y error de resolución.

Esto implementa la regla original de no forzar siempre continuación o reversión
y no altera ninguna trayectoria.

## Discovery target-only

Antes de entrenar cualquier modelo se etiquetan sólo los LB discovery 2022 con
depth/MID válido. Gates:

- al menos 500 LB válidos;
- al menos 100 ejemplos por clase resuelta;
- cada clase resuelta en al menos 6 meses;
- ninguna clase resuelta supera 70%;
- TVD BUY/SELL `<=0.15`;
- ningún mes concentra más de 35% de una clase resuelta;
- `AMBIGUOUS<=10%`;
- cobertura de referencia `>=95%` dentro de sesiones con depth.

Si falla cualquier gate:

```text
REGIME_V2_TARGET_DISCOVERY_FAIL
```

y no se entrenan baselines ni features.

## Checkpoints causales posteriores

Sólo si el target pasa:

```text
LB, +100ms, +250ms, +500ms, +1s, +2s
```

Cada predictor debe cumplir `max_feature_timestamp<=checkpoint`. La etiqueta
verdadera de régimen nunca es feature del trigger.

Unidad de split y bootstrap: `LB_ID`/sesión. Prohibido split aleatorio por fila.

Validation 2023, holdout 2024 y 2025–2026 permanecen sellados.

`INFORMATION_STATUS=POST_LB_REGIME_V2_PREREGISTERED_DISCOVERY_TARGET_ONLY`
