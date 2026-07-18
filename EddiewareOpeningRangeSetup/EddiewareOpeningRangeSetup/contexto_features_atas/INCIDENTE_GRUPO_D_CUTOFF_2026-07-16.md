# Incidente Grupo D y cutoff oficial — 18/07/2026

## Resultado

La investigación Grupo D se volvió a ejecutar correctamente sobre Historia X10
con cutoff oficial inclusivo `2026-07-16`. La sesión `2026-07-17` queda fuera del
universo de investigación y del control de huecos.

## Causa exacta del error

El primer intento sí terminó los cálculos estadísticos, pero falló al construir
el Markdown. La columna
`direction_stable_discovery_validation_holdout` contenía `NaN` para una fila con
muestra insuficiente y el reporte ejecutaba `int(NaN)`, produciendo:

`ValueError: cannot convert float NaN to integer`

Era un error de serialización del reporte, no de Replay, datos, estrategia ni
cálculo de trades.

## Correcciones de pipeline

- Cutoff reproducible fijo: `2026-07-16`.
- Las filas posteriores al cutoff se excluyen antes de clasificar A/B/C/D.
- El coordinador sólo considera fechas hasta el cutoff.
- Los flags estadísticos faltantes se muestran como `0` sin modificar los
  cálculos subyacentes.
- Los warnings numéricos de SciPy permanecen en stderr para auditoría, pero no
  se clasifican como fallo si el proceso termina con código `0`.

## Validación

- Sesiones oficiales: `735`.
- Última sesión oficial: `2026-07-16`.
- Huecos terminales: `0`.
- Trades analizados: `189`.
- Grupo A: `94`.
- Grupo B: `2`.
- Grupo C: `19`.
- Grupo D: `74`.
- Modo: Historia X10 únicamente.
- Replay X1: deshabilitado.
- Lógica de trading modificada: no.
- Filtros creados: no.

Reporte resultante:

`contexto_features_atas/INVESTIGACION_TRADES_NACEN_MAL_20260718_004112.md`
