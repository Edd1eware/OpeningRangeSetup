# Ronda 007 — dictamen

## Aceptación

Mi condición de ronda 006 fijó el principio correcto (completitud del evento atómico) en la granularidad equivocada: exigir `F_LAST` por `sequence` asume que el Match Event vive en un solo mensaje, y el registro físico demuestra lo contrario — el evento abarca múltiples `sequence` (T, F, y cierre C con `F_LAST` en mensaje posterior). La auditoría es concluyente: 21,225/21,225 eventos cerrados con `F_LAST` y cada uno con `ts_event` único, aunque la mayoría multisequence (hasta 13).

La corrección V4 es la versión ejecutable del mismo principio:

1. **Delimitación por Match Event hasta `F_LAST`, en orden físico**: correcto; coincide con la semántica MDP3 (un evento de matching = varios mensajes, `F_LAST` cierra para el instrumento).
2. **Múltiples `sequence`, lados y precios dentro del evento**: aceptado; resuelve además con naturalidad el paquete bilateral de 2023-05-18 (legs de evento implícito) que antes era anomalía.
3. **Último T físico del evento = last-sale hasta el siguiente evento con T**: defendible, misma lógica que ronda 006 (extremo del barrido = precio final del evento atómico), ahora bien delimitada. `ts_event` único por evento (verificado 21,225/21,225) elimina ambigüedad de ventana; estados internos con dwell cero preservan que no existe tiempo físico intraevento.
4. **INTEGRITY_FAIL** por evento no cerrado, timestamps mezclados o no-determinismo entre decodificaciones: cubre completitud, atomicidad y reproducibilidad. Suficiente.
5. **Regla idéntica en pseudo-ventanas y ventanas reales**: condición que hace inocuo cualquier sesgo de la convención — se cancela en los percentiles.

Sin cambios a taxonomía, calibración, horizonte ni gates. Enmienda estructural pre-resultado, asentada en el registro de desviaciones; siguen vigentes doble decodificación SHA-256, sincronía de reloj ≤2 ticks en `p0` y contrato por sesión. Ningún umbral, etiqueta ni resultado producido aún.

`CONVERGENCIA_FINAL_V4`
