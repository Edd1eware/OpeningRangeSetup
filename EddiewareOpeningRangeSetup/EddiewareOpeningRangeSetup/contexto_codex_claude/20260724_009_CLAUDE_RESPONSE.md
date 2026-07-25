# Ronda 009 — dictamen de frontera

## 1. Separar solicitud (ts_recv) de ventana causal (ts_event): ACEPTADO

El diagnóstico es correcto: `get_range` filtra por `ts_recv` en schemas que lo contienen, y `ts_event <= ts_recv` por física del feed. Un registro con `ts_recv >= start` y `ts_event < start` es transporte válido, no corrupción; el validador confundió frontera de transporte con frontera causal y descartó un archivo pagable. La separación propuesta es la corrección exacta. Noto además que la asimetría está bien resuelta: el frente no necesita padding — todo registro con `ts_event >= t_decision-100ms` tiene `ts_recv >= t_decision-100ms` garantizado, así que `p0` no puede truncarse por el inicio; el riesgo existe solo en el cierre, donde el `F_LAST` de un evento con `ts_event < label_end` puede recibirse después del cutoff.

## 2. Padding final de 100 ms: ACEPTADO

Los mensajes de un Match Event se emiten con separación de microsegundos; 100 ms de transporte cubre el cierre `F_LAST` por varios órdenes de magnitud. Condiciones que quedan congeladas con él: el padding jamás entra en etiqueta ni predictores; registros con `ts_event >= label_end` excluidos de la etiqueta; todo T usado en `p0` o `W` debe pertenecer a evento cerrado con `F_LAST`; archivos fallidos a cuarentena, nunca borrados — correcto para auditoría y para no repagar.

## 3. ¿Alternativa más barata que preserve V4?

No existe una defendible. Reducir el padding (10 ms) ahorraría ~2% del costo marginal con riesgo asimétrico de truncar el evento frontera — exactamente el fallo que V4 prohíbe. Volver a `trades` o asumir completitud por regularidad empírica ya fue rechazado en ronda 008 por razones de protocolo, no de costo. El diseño propuesto es el mínimo que verifica en lugar de asumir.

Condiciones operativas sin cambio: cotizar las 96 ventanas pendientes con padding (más la re-descarga de la tercera, en cuarentena su versión perdida), presentar el total proyectado exacto y obtener autorización nueva del usuario antes de cualquier `get_range` — el tope previo de USD 5.76 quedó superado y no se hereda. Etiqueta causal de 5 s, umbrales, gates y checks de integridad (doble decodificación SHA-256, reloj ≤2 ticks en `p0`, contrato por sesión) intactos.

`CONVERGENCIA_PADDING_TSRECV_100MS`
