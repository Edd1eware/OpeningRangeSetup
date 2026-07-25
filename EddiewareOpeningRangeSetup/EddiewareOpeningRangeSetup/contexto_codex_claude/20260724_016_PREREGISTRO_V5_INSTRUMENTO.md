# Prerregistro V5 — instrumento causal de outcome A/B/C

Este documento congela la implementación operativa de la convergencia
`20260724_015_CONVERGENCIA_V5_P75_DWELL_ALINEADO.md`.

## Datos permitidos para calibración

- Los mismos MBO snapshot predecisión de 98 sesiones usados por V4.
- Ventanas no solapadas de 5 s desde 08:29:00 America/Chicago.
- Fin exclusivo `t_decision - 60 s`.
- Último T físico del Match Event fija last-sale.
- Dos orientaciones por ventana física.
- Ningún outcome real se lee durante la calibración.

## Estadísticos congelados

```text
T_push = quantile(positive_excursion_oriented, 0.50)
T_ext  = quantile(positive_excursion_oriented, 0.75)
T_ret  = quantile(adverse_excursion_oriented, 0.50)
```

Para dwell:

1. localizar el primer push;
2. buscar sólo después de ese ordinal físico:
   - B: intervalos continuos `d >= T_ext`;
   - A: intervalos continuos `d <= -T_ret`;
3. conservar el máximo dwell calificante por observación;
4. incluir únicamente observaciones donde exista la secuencia correspondiente;
5. `T_dwB=P50(dwell_B)` y `T_dwA=P50(dwell_A)`;
6. exigir soporte >=100 en ambas ramas.

## Aplicación congelada

- Usar los 98 outcome MBO con padding uniforme.
- Evaluar base, 0.85 y 1.15 con todos los umbrales de precio y dwell escalados
  simultáneamente.
- No modificar fórmulas después de ver conteos.
- No entrenar predictores salvo que todos los gates del instrumento pasen.
- Los resultados V4 se usan sólo para justificar la corrección estructural;
  no seleccionan valores numéricos V5.

## Gate terminal

Si A <15% o B <15%, se termina la taxonomía de precio 5 s sin V6.

`INFORMATION_STATUS=INSTRUMENT_DIAGNOSTIC_NEVER_PREDICTIVE_EVIDENCE`
