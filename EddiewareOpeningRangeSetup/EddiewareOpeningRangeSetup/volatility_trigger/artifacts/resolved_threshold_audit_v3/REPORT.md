# Auditoría de thresholds resueltos V3

Fecha: 2026-07-27

Fuente: matriz V1 corregida y congelada, cinco sesiones técnicas, 106/111
referencias MID válidas.

Jerarquía consumida:

```text
8 -> 12 -> 4 -> 16
```

Resultado:

- 8 ticks: FAIL por TVD resuelta 0.167667 > 0.15;
- 12 ticks: FAIL por TVD resuelta 0.187523 > 0.15;
- 4 ticks: FAIL porque `NO_EXPANSION=0`;
- 16 ticks: PASS de todos los gates resueltos.

Threshold seleccionado mecánicamente: `16` ticks.

El resultado es invariante a calcular TVD con o sin `AMBIGUOUS`: ningún
threshold cambia PASS/FAIL.

La jerarquía queda consumida. Si 16 ticks falla discovery no se vuelve a
8/12/4 y no se recorre otra vez.

`INFORMATION_STATUS=RESOLVED_THRESHOLD_V3_SELECTED_16T`
