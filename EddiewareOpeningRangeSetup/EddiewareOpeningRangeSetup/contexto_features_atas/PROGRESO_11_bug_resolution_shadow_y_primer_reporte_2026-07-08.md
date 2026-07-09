# PROGRESO 11 — bug de shadowing + primer reporte real julio 2026 (2026-07-08)

## Contexto

Captura julio (2026-07-01 a 2026-07-08, 5 fechas hábiles reales, feriado 07-03 excluido)
completó 5/5 OK con el DLL nuevo (`bar_trades` confirmado presente). El paso final —generar el
Excel agregado— falló: `TypeError: '>' not supported between instances of 'dict' and 'int'`.

Nota aparte: el primer intento de lanzar "julio completo" incluía fechas futuras (07-09 a
07-31, que no existen porque hoy es 2026-07-08). Se detuvo a tiempo antes de perder horas en
timeouts de 15 min por fecha inexistente; relanzado con el rango correcto tras confirmación
del usuario.

## Bug: variable `resolution` shadowed dentro de `detect_retests`

`retest_detector.py::detect_retests` ya tenía `resolution` como nombre de variable — el float
de segundos de resolución de barra devuelto por `_path_for_detection` (línea 329). La
implementación de H7 (aceptación/rechazo, sesión anterior) reutilizó el mismo nombre para el
dict devuelto por `_resolve_interaction()` dentro del loop de retests (línea 358 original),
tapando la variable original. La primera vez que el código intentaba `resolution > 0` (línea
375, lógica de BAR_UNORDERED dwell time) comparaba un dict contra un int → `TypeError`.

No apareció en el smoke test sintético porque ese test usaba precisión `TICK` (`precision ==
"TICK"` evita la rama `resolution > 0` en la línea 375). Con datos reales `BAR_UNORDERED`
(footprint de 1 min) sí entra en esa rama.

**Fix**: renombrado el dict de `_resolve_interaction()` a `interaction` en todo
`detect_retests` (líneas 358-464), dejando `resolution` únicamente para el float de segundos
original.

## Verificación

Reprocesado directo (sin pasar por el runner) sobre las 5 fechas reales:

```
sessions: 5, lvns: 3, events: 5, no_retest_days: 0
```

Primer resultado real con el motor corregido (`LVN_Events.csv`):

| Fecha | LVN | Approach | Interaction | Trade logic | Lado | Entry | MFE | MAE | MAE-antes-MFE | RR max | t→MFE(s) | Result 20/20 | Shape |
|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 07-02 | 30048.75 | FROM_ABOVE | REJECTION | REVERSAL | LONG | 30052.50 | 90.0 | 35.0 | 35.0 | 2.57 | 60 | AMBIGUOUS | unknown |
| 07-02 | 30048.75 | FROM_ABOVE | REJECTION | REVERSAL | LONG | 30055.00 | NaN | NaN | NaN | NaN | NaN | NO_PATH | unknown |
| 07-07 | 29616.25 | FROM_ABOVE | REJECTION | REVERSAL | LONG | 29642.50 | 80.0 | 605.0 | 205.0 | 0.39 | 60 | AMBIGUOUS | trend_down |
| 07-07 | 29616.25 | FROM_ABOVE | ACCEPTANCE | CONTINUATION | SHORT | 29607.50 | 465.0 | 15.0 | 15.0 | 31.00 | 360 | TP | trend_down |
| 07-07 | 29662.50 | FROM_BELOW | REJECTION | REVERSAL | SHORT | 29607.50 | 465.0 | 15.0 | 15.0 | 31.00 | 360 | TP | trend_down |

n=5, no interpretar edge todavía (regla de la doctrina). Confirma que las columnas nuevas
(`lvn_interaction`, `trade_logic`, `mae_before_mfe_ticks`, `rr_max_achievable`) funcionan con
datos reales end-to-end.

## Actualización: columnas exit price/time/duración por bracket (2026-07-08, mismo día)

Pedido del usuario: agregar al Excel precio de entrada, precio de salida, hora de entrada,
hora de salida, duración del trade y RR máximo. Ya existían `entry_price`/`entry_time_et`
(momento de confirmación aceptación/rechazo) y `rr_max_achievable`. Faltaban exit/duración.

Como el motor evalúa 4 brackets en paralelo (20/40/60/80 ticks), se agregaron por bracket:
`exit_price_X_X`, `exit_time_et_X_X`, `trade_duration_seconds_X_X`.

Reglas de cómputo:
- `TP`/`SL`: exit_price = entry_price ± target_ticks*tick_size (según lado y resultado);
  exit_time = timestamp de la barra/tick donde se confirmó el touch; duration = segundos
  desde entry hasta ese touch.
- `AMBIGUOUS` (TP y SL en la misma barra sin orden intrabar observable): exit_time SÍ se
  reporta (la barra se conoce), exit_price queda NaN — nunca se adivina cuál lado tocó
  primero.
- `TIME_EXIT`/`NO_PATH`: exit_price = último close observado, exit_time = último timestamp
  del path, duration = todo el tramo medido.

`statistics.first_touch_result` se extendió para devolver también el índice de la fila donde
ocurrió el touch (antes solo devolvía status + tiempo), necesario para ubicar el timestamp
real en el path.

Verificado: 12 columnas nuevas (3 × 4 brackets) presentes y pobladas correctamente en
`LVN_Events.csv` tras regenerar el reporte julio 01-08.

## Pendiente

- El Excel del run (`lvn_retest_DST_2026-07-01_2026-07-08.xlsx`) fue regenerado directamente;
  el manifest del runner (`..._run_manifest.json`) sigue mostrando el error de la corrida
  original — no afecta el reporte final, ya corregido, pero queda como nota para no
  confundirse si se revisa el manifest.
- Seguir acumulando fechas (agosto en adelante conforme pase el tiempo, o retroceder a meses
  ya completos como junio) antes de mirar frecuencia/WR con significancia.
