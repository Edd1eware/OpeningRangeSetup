# Codex — decisión de schema postdecisión, ronda 008

## Cotización completa, no billable

98 sesiones, ventana uniforme:

```text
[t_decision-100 ms, t_decision+5 s)
```

| schema | sesiones | costo estimado total | promedio/sesión | máximo |
|---|---:|---:|---:|---:|
| trades | 98 | USD 2.822613001 | USD 0.028802173 | USD 0.042048275 |
| mbo | 98 | USD 5.755439754 | USD 0.058728977 | USD 0.095859066 |

Espacio libre: 100.57 GiB. Reserva de 10 GiB: PASS. No comenzó descarga.

## Diferencia de capacidad

`trades` conserva los T pero, al ser subconjunto MBO, no garantiza que incluya
el registro no-T que porta `F_LAST`. Permitiría agrupar por `ts_event` usando
la regularidad empírica 21,225/21,225, pero no verificar la completitud del
Match Event en las 98 ventanas nuevas.

`mbo` conserva:

- todos los T;
- orden físico;
- `F_LAST`;
- validación de evento cerrado;
- `F_MAYBE_BAD_BOOK`;
- sequence.

La ausencia de snapshot inicial en una petición MBO de 5.1 s no es relevante:
el outcome usa sólo T-events y sus fronteras F_LAST; no reconstruye estado del
libro posterior.

## Recomendación Codex

Elegir `mbo`. El sobrecosto es USD 2.932827 frente a trades y compra la puerta
de integridad exacta que motivó V4. Elegir trades exigiría relajar el protocolo
congelado justo antes de observar las etiquetas.

No se descargará sin autorización del usuario para el costo MBO exacto.
