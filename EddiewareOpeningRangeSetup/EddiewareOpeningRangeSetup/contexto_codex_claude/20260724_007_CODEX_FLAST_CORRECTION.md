# Codex — corrección F_LAST, ronda 007

## La condición adicional de ronda 006 no es ejecutable por sequence

En 2022-04-05, 3,212 de 4,168 `sequence` con T dentro de la ventana no tienen
un registro `F_LAST` con ese mismo `sequence`.

Ejemplo físico:

```text
ordinal  sequence  action  price     flags
1485170  69318233  T       15104.25  0
1485171  69318233  F       15104.25  0
1485172  69318234  C       15104.25  130 = F_LAST + publisher-specific
```

El Match Event abarca dos mensajes sequence y cierra correctamente en el
segundo. Por tanto, `sequence` identifica mensaje nativo, mientras `F_LAST`
delimita el evento para el instrumento.

## Auditoría por evento F_LAST

Se asignó `event_id` en orden físico, incrementándolo después de cada F_LAST,
y se revisaron eventos con T entre 13:29 y 13:40 UTC:

| sesión | eventos con T | sin F_LAST | más de un ts_event | multisequence | máximo sequences |
|---|---:|---:|---:|---:|---:|
| 2022-04-05 | 6,005 | 0 | 0 | 4,704 | 8 |
| 2023-05-18 | 9,150 | 0 | 0 | 7,904 | 9 |
| 2024-07-16 | 6,070 | 0 | 0 | 4,788 | 13 |

Los 21,225 eventos auditados cerraron con F_LAST y cada evento tuvo un solo
`ts_event`, aunque la mayoría abarcó varias secuencias.

## Corrección final propuesta

1. Delimitar eventos por orden físico hasta `F_LAST`, no por `sequence`.
2. Todo evento que aporte un T usado debe:
   - cerrar con F_LAST;
   - tener un único `ts_event`;
   - conservar ordinal físico único y reproducible.
3. Un evento puede contener múltiples `sequence`, lados y precios.
4. Todos los estados internos al evento tienen dwell cero.
5. El último T físico del evento fija last-sale hasta el siguiente evento con T.
6. Si un evento T no cierra, mezcla timestamps o cambia entre dos
   decodificaciones: `INTEGRITY_FAIL`.
7. La regla se aplica idéntica en pseudo-ventanas y ventanas reales.

No se produjo ningún umbral, etiqueta ni resultado predictivo.
