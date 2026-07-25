# Codex — auditoría de paquetes MBO, ronda 006

## Gate activado

El calibrador V2 se detuvo en la primera sesión antes de producir umbrales:
encontró 215 grupos `ts_event+sequence` con más de un precio entre 08:29 CT y
el cutoff de calibración.

## Evidencia

Los grupos no son duplicados corruptos. Ejemplos reales:

```text
ts_event                         sequence  side  prices
2022-04-05 13:29:04.292116593   69321487  B     15104.00,15104.25,15104.50
2022-04-05 13:29:07.237937565   69323886  A     15104.50,15104.25
```

En ambos, `ts_recv`, `sequence` y el identificador del mensaje agresor son
comunes; el registro físico conserva el recorrido por niveles.

Auditoría ampliada 13:29–13:40 UTC:

| sesión | paquetes mult precio | lado único | último=extremo agresor | monotónico |
|---|---:|---:|---:|---:|
| 2022-04-05 | 314 | 314 | 314 | 314 |
| 2023-05-18 | 285 | 284 | 284 | 284 |
| 2024-07-16 | 244 | 244 | 244 | 244 |

El único paquete no monotónico:

```text
2023-05-18 13:31:30.173502597 sequence 112371450
A 13665.00
B 13665.25
```

Ambos registros comparten también `ts_recv`. Es un evento atómico con dos
prints; no existe tiempo físico entre ellos.

La documentación oficial de Databento para GLBX.MDP3 indica:

- `sequence` es el número de mensaje asignado por el venue;
- Trade y Fill se normalizan desde Trade Summary;
- los registros originados por un mismo mensaje nativo comparten `sequence`;
- `F_LAST` marca el último registro del evento para cada instrumento.

Por ello, exigir un solo precio por `ts_event+sequence` confundió mensaje
nativo con trade individual.

## Corrección propuesta V3

Sin cambiar etiquetas, umbrales, horizonte o gates:

1. preservar un `record_ordinal` físico creciente al decodificar DBN;
2. ordenar por `ts_event`, `sequence`, `record_ordinal`;
3. conservar todos los T del paquete: no colapsar prints distintos;
4. estados intermedios con el mismo `ts_event` aportan dwell cero;
5. el último T en orden DBN fija el last-sale hasta el siguiente `ts_event`;
6. reportar paquetes mult precio, mult lado y no monotónicos como calidad;
7. `INTEGRITY_FAIL` sólo si:
   - el ordinal no es único o no es recuperable;
   - hay retroceso incremental de sequence;
   - `F_MAYBE_BAD_BOOK`;
   - el orden físico cambia entre dos decodificaciones del mismo archivo;
8. comprobar determinismo decodificando dos veces una muestra de tres sesiones
   y comparando SHA-256 de
   `ts_event|sequence|record_ordinal|side|price|size`.

Esta corrección usa únicamente estructura del feed; no se produjo ningún
percentil, etiqueta nueva ni resultado predictivo.
