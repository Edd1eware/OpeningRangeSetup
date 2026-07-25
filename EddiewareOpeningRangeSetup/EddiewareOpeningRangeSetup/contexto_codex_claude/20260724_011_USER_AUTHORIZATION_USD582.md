# AUTORIZACIÓN DEL USUARIO — DESCARGA MBO OUTCOME V4 PAD100

Fecha local: 2026-07-24  
Objetivo: descargar las 96 ventanas MBO pendientes para construir el outcome A/B/C independiente.

## Autorización

El usuario autorizó expresamente continuar la descarga con un tope total de:

**USD 5.82**

## Alcance autorizado

- Conservar las 2 ventanas ya descargadas y validadas.
- Considerar como potencialmente facturada la tercera solicitud anterior cuyo archivo fue descartado por el validador incorrecto.
- Descargar solamente las 96 solicitudes pendientes.
- Solicitud Databento delimitada por `ts_recv`:
  - inicio: `t_decision - 100 ms`;
  - fin exclusivo: `t_decision + 5 s + 100 ms`.
- Etiquetado causal delimitado exclusivamente por `ts_event`:
  - `p0`: último Match Event T completo en los 100 ms anteriores;
  - outcome: `[t_decision, t_decision + 5 s)`;
  - los 100 ms finales de transporte jamás entran a la etiqueta ni a los predictores.
- Mantener al menos 10 GiB libres en disco.
- No ejecutar ATAS, no entrenar modelos y no modificar la estrategia durante la descarga.

## Coste congelado

- Coste ya incurrido asumido: USD 0.166896311939.
- Coste cotizado de las 96 solicitudes con padding: USD 5.643840841949.
- Peor caso total proyectado: USD 5.810737153888.
- Margen bajo el tope autorizado: USD 0.009262846112.

## Integridad de notificaciones

Los mensajes de investigación y solicitudes de acción se registran desde esta
autorización en un ledger persistente separado. La limpieza previa de Telegram
para corridas ATAS no puede eliminarlos.
