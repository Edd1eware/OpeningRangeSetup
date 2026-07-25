# Prerregistro — Mechanical Book Outcome V1

Fecha: 2026-07-24  
Estado: congelar y hashear antes de aplicar

## Pregunta

¿El estado futuro del libro después de `t_decision` permite crear una etiqueta
mecánica, causal y estable de absorción limpia frente a breakout limpio?

Esta etapa sólo valida el instrumento. No entrena predictores.

## Población

- 98 sesiones discovery 2022–2024.
- Excluidas `2022-06-13` y `2023-06-13`.
- 2025–2026 cerrado.
- Una observación por `BurstId`.

## Handoff obligatorio

- Estado activo reconstruido del MBO snapshot al
  `strict_feature_cutoff_utc_exclusive`.
- Debe existir prefijo lógico exacto en el solape del outcome MBO.
- Cola de paquete incompleto sólo se aplica cuando llega su `F_LAST`.
- `F_MAYBE_BAD_BOOK=0`, sin retrocesos incrementales de sequence.
- `Q0>0`.

## Reloj y paquetes

```text
W = [strict_feature_cutoff, strict_feature_cutoff + 5 s) por ts_recv
```

Un Match Event se consume completo cuando su registro `F_LAST` se recibe
dentro de W. Todo el paquete se excluye si `F_LAST` llega fuera de W.
El orden físico DBN decide precedencia.

Los eventos con `ts_event<cutoff` pero `ts_recv>=cutoff` son futuros causales y
entran únicamente al confirmarse su Match Event.

## Nivel atacado

```text
BUY  -> attacked_side=A, L0=best ask
SELL -> attacked_side=B, L0=best bid
Q0   -> profundidad agregada visible en attacked_side,L0 al cutoff
```

## Contabilidad

- `F_dep`: suma de F en attacked_side,L0.
- Una C del mismo Match Event, `order_id` y precio que una F es mutación de
  estado por fill, no cancelación pura.
- Si C excede la F hermana, sólo el exceso es `C_dep`.
- `C_dep`: cantidad C no explicada por F hermana.
- `ADD`: A o incremento M añadido en attacked_side,L0.
- `Q_end`: profundidad agregada en attacked_side,L0 al terminal.
- `queue_zero`: Q(L0) llegó a cero después de un paquete confirmado.
- `ceded`:
  - BUY: best ask >L0 o no existe ask;
  - SELL: best bid <L0 o no existe bid.

## Clasificación base

Con `h=0.5`:

```text
A_ABSORCION_LIMPIA:
  F_dep >= h*Q0
  AND ceded nunca fue verdadero
  AND Q_end > 0

B_BREAKOUT_LIMPIO:
  queue_zero fue verdadero
  AND F_dep/(F_dep+C_dep) >= h
  AND ceded es verdadero al final

C_VARIABLE:
  resto
```

A y B son mutuamente excluyentes. ADD, supervivencia de órdenes iniciales,
refill durable, tiempo en cero y profundidad terminal se publican como
diagnóstico, pero no añaden puertas post hoc.

## Sensibilidad

Repetir exactamente con:

- `h=0.425`;
- `h=0.575`.

Jaccard base contra cada perturbación debe ser >=0.70 para A y B.

## Gates

- Handoff e integridad: 98/98.
- Elegibilidad: reportar exclusiones; `Q0>0` obligatorio.
- A>=15% y B>=15% de elegibles.
- Ninguna clase supera 70% de A+B.
- A y B en 2022, 2023, 2024.
- A y B en BUY y SELL.
- Jaccard A/B >=0.70 en ambas perturbaciones.

Si falla cualquier gate, Mechanical Book V1 se cierra sin ajustar constantes,
horizonte o reglas.

## Prohibiciones

- No MFE, MAE, TP, SL, PnL ni resultado terminal.
- No last-sale futuro en la etiqueta.
- No usar V4/V5 precio para desempatar.
- No entrenar modelo antes de que pase el instrumento.
- No descargar fechas nuevas.

`INFORMATION_STATUS=MECHANICAL_OUTCOME_ONLY_NEVER_PREDICTOR`
