# MBO DATA CAPABILITY AUDIT

Fecha de auditoría: 2026-07-22. Alcance: lectura directa, sin features nuevas, sin clasificadores y sin outcomes de trading.

## Veredicto

**B. SIRVEN PARCIALMENTE.**

Los DBN sí conservan identidad de orden, A/C/M/F/T, precio, tamaño, exchange-time nanosegundo, orden físico y secuencia. Permiten estudiar ciclos causales de órdenes cuyo ADD aparece en la ventana y medir fills, modificaciones, cancelaciones puras inferidas, reposición visible y supervivencia observada. No permiten reconstruir el libro inicial ni la cola completa porque las solicitudes de 10 segundos no incluyen el snapshot de medianoche.

## Inventario real

- 100 archivos DBN zstd, 23,611,127 bytes, 1,274,719 registros.
- Fechas: 2022-04-05 a 2024-08-14; 2022/2023/2024.
- Ruta MBO: `C:\Users\k_99_\Desktop\codding\data_footprint_generator\databento_mbo\liquidity_burst_pilot_20260720`.
- Manifiesto: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_features_atas\DATABENTO_MBO_PILOTO_100_DISCOVERY_20260722.csv`.
- Ruta ATAS MBP/tape: `C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings`.
- Dataset: GLBX.MDP3; schema: MBO; símbolo solicitado: NQ.v.0 continuo.
- Instrumentos numéricos por sesión: mínimo 1, máximo 1; el contrato raw no quedó persistido.
- Profundidad: eventos MBO de todas las órdenes publicadas para el instrumento durante la ventana; no equivale a libro completo al inicio porque falta el snapshot.
- El DBN quedó con `stype_out=InstrumentId`; el campo `stype_out=raw_symbol` del manifiesto no fue pasado por el descargador.
- Acciones reales: {'A': 485688, 'C': 494465, 'M': 158532, 'F': 80925, 'T': 55109, 'R': 0}.
- ATAS MBP+tape coincidente: 92/100 y 92/100 sesiones.
- Archivos ATAS MBO por orden: 0. Los CSV de ATAS disponibles son MBP agregado y tape.

### Versiones y lectores comparados

- **Fuente con mayor información:** DBN MBO crudo anterior, leído con `databento.DBNStore` por `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\audit_mbo_data_capability.py`.
- Descargador: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\download_databento_mbo_manifest.py`; preparador del manifiesto: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\prepare_databento_mbo_request_manifest.py`.
- Exportador ATAS: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\features\BookRecorder.cs`. Generó MBP/tape, pero ningún `mbo_*.csv`.
- Versión transformada anterior: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\mbo_liquidity_burst_viability_20260720_r1\mbo_feature_ledger.csv`; es un ledger derivado y pierde la secuencia por orden.
- Ledger MBP/tape: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\preentry_liquidity_features_20260720_preentry_r2\preentry_mbp_feature_ledger.csv`; también es derivado y no sustituye el DBN.

## Ciclo de vida y explicitud

- Órdenes únicas por archivo sumadas: 621,262.
- Ciclos cuyo primer evento observado es ADD: 485,360 (78.12%).
- Órdenes censuradas por la izquierda: 135,902 (21.88%).
- Grupos de fill cuyo efecto en libro se reconcilia por C agregado o M con estado: 78,088/80,133 (97.45%).
- Grupos de fill con cantidad previa reconstruible: 66,668/80,133 (83.20%).
- Ejecuciones parciales/completas inferidas con estado conocido: 2,604/63,737.
- Eventos C ambiguos porque F y C comparten clave pero no cantidad: 181.
- Eventos identidad-dependientes no reconciliables por censura/inconsistencia: 99,149/733,577 (13.52%).

### Qué es explícito

`A`, `C`, `M`, `F`, `T`, order_id, lado, precio, size, ts_event, ts_recv, sequence y flags. El `F` identifica la orden reposante ejecutada; el `T` registra el trade agresor. El `C` es la reducción efectiva del libro y puede representar cancelación pura o la reducción que acompaña un fill.

### Qué es inferido

Cancelación pura = C sin F para la misma orden/ts_event/precio; modificación de precio/tamaño = comparación de M con estado previo; fill parcial/completo = F frente a cantidad previa; refill de la misma orden = aumento de size mediante M; supervivencia = orden aún presente al cutoff. Cancel-replace con ID nuevo no es enlazable con certeza.

## Cola

La prioridad relativa de órdenes nacidas dentro de la ventana puede seguirse por orden físico/sequence. El `queue_ahead_estimate` entregado es un **límite inferior** que suma solo órdenes observadas. No es posición exacta: faltan las órdenes que ya estaban vivas al iniciar la descarga y su prioridad.

## Precedencia temporal y sincronización

- Filas MBO fuera de orden por ts_event: 0; retrocesos de sequence: 0.
- Registros adicionales idénticos en todos los campos MBO: 264 (A 0, C 0, M 0, F 264, T 0). No se deduplican automáticamente: múltiples F/T idénticos pueden ser ejecuciones unitarias legítimas y reconciliar una reducción agregada.
- `F_MAYBE_BAD_BOOK`: 0; `F_BAD_TS_RECV`: 0.
- Eventos MBO submicrosegundo: 100.00%.
- Eventos dentro del milisegundo final pero posteriores al timestamp nominal: 595 en 81/100 sesiones; se excluyeron de la reconstrucción causal.
- Eventos en/después de `end_utc_exclusive`: 0.
- Match MBO T vs ATAS tape: exacto a milisegundo 5.49%; dentro de ±5 ms 13.03%.
- Match de cambios MBO conocidos vs ATAS MBP: exacto 1.25%; dentro de ±5 ms 2.29%.

MBO usa UTC exchange-time y sequence. ATAS escribe un `DateTime` convertido a NY y truncado a milisegundos, sin persistir Kind, sequence, receive-time ni export-time. Por ello la precedencia interna MBO es recuperable; la precedencia cruzada MBO↔ATAS solo es aproximada y debe mantener una banda de empate, nunca resolverse por orden de filas después de redondear. La etiqueta de decisión sólo tiene milisegundos: los eventos posteriores dentro de ese mismo milisegundo son una zona de empate, no evidencia predecisional.

## Prueba manual: tres sesiones

Sesiones: 2022-04-05, 2023-05-18, 2024-07-12. Filas publicadas: 572. Eventos identidad-dependientes no reconciliables en la muestra: 28.49%.

| fecha | lado | precio | eventos | ADD Δ | MODIFY Δ | C Δ | F qty | net MBO | residuo ecuación | net ATAS MBP | no reconciliable |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-04-05 | A | 15134.00 | 12 | 4 | 0 | -4 | 0 | 0 | 0 | 0 | 25.00% |
| 2022-04-05 | A | 15134.25 | 21 | 11 | 0 | -10 | 0 | 1 | 0 | 0 | 0.00% |
| 2022-04-05 | A | 15134.50 | 17 | 11 | -5 | -5 | 0 | 1 | 0 | 0 | 40.00% |
| 2022-04-05 | A | 15134.75 | 13 | 8 | -2 | -3 | 0 | 3 | 0 | 0 | 20.00% |
| 2022-04-05 | A | 15135.00 | 16 | 6 | 0 | -6 | 0 | 0 | 0 | 0 | 30.00% |
| 2023-05-18 | A | 13680.25 | 39 | 15 | 2 | -17 | 16 | 0 | 0 | 0 | 42.86% |
| 2023-05-18 | A | 13680.50 | 51 | 22 | -5 | -18 | 13 | -1 | 0 | 0 | 32.43% |
| 2023-05-18 | A | 13680.75 | 74 | 20 | 1 | -24 | 24 | -3 | 0 | 0 | 23.53% |
| 2023-05-18 | A | 13681.00 | 72 | 17 | 0 | -17 | 25 | 0 | 0 | 0 | 54.55% |
| 2023-05-18 | A | 13681.25 | 43 | 13 | 1 | -12 | 12 | 2 | 0 | -51 | 33.33% |
| 2023-05-18 | B | 13680.25 | 55 | 35 | 0 | -30 | 5 | 5 | 0 | 0 | 0.00% |
| 2023-05-18 | B | 13680.50 | 40 | 22 | 2 | -15 | 2 | 9 | 0 | 0 | 0.00% |
| 2023-05-18 | B | 13680.75 | 27 | 9 | 0 | -8 | 3 | 1 | 0 | 0 | 0.00% |
| 2023-05-18 | B | 13681.00 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | N/A% |
| 2023-05-18 | B | 13681.25 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | N/A% |
| 2024-07-12 | A | 20467.75 | 37 | 15 | 0 | -13 | 4 | 2 | 0 | 0 | 27.27% |
| 2024-07-12 | A | 20468.00 | 19 | 6 | -1 | -9 | 3 | -4 | 0 | 0 | 46.15% |
| 2024-07-12 | A | 20468.25 | 9 | 2 | -1 | -5 | 0 | -4 | 0 | 0 | 14.29% |
| 2024-07-12 | A | 20469.00 | 8 | 5 | 0 | -8 | 0 | -3 | 0 | 0 | 0.00% |
| 2024-07-12 | A | 20469.75 | 6 | 1 | 0 | -4 | 0 | -3 | 0 | 0 | 20.00% |
| 2024-07-12 | B | 20467.75 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | N/A% |
| 2024-07-12 | B | 20468.00 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | N/A% |

### Filas reales anonimizadas

| sesión | exchange timestamp | sequence | order_id | evento | lado | precio | qty antes | cambio | qty después | trade qty | cola delante |
| --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-04-05 | 2022-04-05 13:32:00.151610019+00:00 | 69882272 | OID_9b743e61faf6 | PURE_CANCEL_INFERRED | A | 15135.00 | N/A | 0 | N/A | 0 | N/A |
| 2022-04-05 | 2022-04-05 13:32:00.181478607+00:00 | 69882672 | OID_ea0284a85b98 | ADD_NEW_ORDER | A | 15134.50 | 0 | 5 | 5 | 0 | 1 |
| 2022-04-05 | 2022-04-05 13:32:00.290097255+00:00 | 69884070 | OID_ae0be491e487 | ADD_NEW_ORDER | A | 15134.50 | 0 | 1 | 1 | 0 | 6 |
| 2022-04-05 | 2022-04-05 13:32:00.292853983+00:00 | 69884123 | OID_84ebd485e871 | PURE_CANCEL_INFERRED | A | 15135.00 | 1 | -1 | 0 | 0 | 1 |
| 2023-05-18 | 2023-05-18 13:34:35.978195061+00:00 | 112884014 | OID_5109b499b83d | ADD_NEW_ORDER | A | 13681.25 | 0 | 1 | 1 | 0 | 2 |
| 2023-05-18 | 2023-05-18 13:34:36.039361925+00:00 | 112884086 | OID_9ce6c2824ce3 | ADD_NEW_ORDER | A | 13681.00 | 0 | 1 | 1 | 0 | 4 |
| 2023-05-18 | 2023-05-18 13:34:36.178062167+00:00 | 112884243 | OID_cdb998bb203b | ADD_NEW_ORDER | A | 13680.25 | 0 | 1 | 1 | 0 | 0 |
| 2023-05-18 | 2023-05-18 13:34:36.279871503+00:00 | 112884383 | OID_9ce6c2824ce3 | PURE_CANCEL_INFERRED | A | 13681.00 | 1 | -1 | 0 | 0 | 4 |
| 2024-07-12 | 2024-07-12 13:31:00.785296975+00:00 | 218442573 | OID_d55b288b6e94 | MODIFY_PRICE | A | 20468.25 | 2 | 0 | 2 | 0 | N/A |
| 2024-07-12 | 2024-07-12 13:31:00.967487265+00:00 | 218443801 | OID_d55b288b6e94 | MODIFY_PRICE | A | 20469.00 | 2 | 0 | 2 | 0 | N/A |
| 2024-07-12 | 2024-07-12 13:31:01.000932349+00:00 | 218444123 | OID_1ae633a75141 | ADD_NEW_ORDER | A | 20469.00 | 0 | 1 | 1 | 0 | 5 |
| 2024-07-12 | 2024-07-12 13:31:01.022902787+00:00 | 218444478 | OID_d55b288b6e94 | MODIFY_PRICE | A | 20468.25 | 2 | 0 | 2 | 0 | N/A |

La diferencia contra MBP no implica que el MBO sea falso: MBP procede de ATAS/Rithmic, tiene milisegundos y otra ruta de datos; además el MBO inicia sin snapshot. Sí demuestra que no es defendible fusionar ambas fuentes como si compartieran un reloj y estado idénticos.

## Conclusiones permitidas

- Cuántos contratos se ejecutaron por T y qué órdenes reposantes recibieron F.
- Ciclos exactos desde ADD para la fracción no censurada.
- Cancelaciones puras inferidas por exclusión del par F/C.
- Modificaciones de precio/tamaño y reposición visible cuando el estado previo es conocido.
- Supervivencia durante la ventana observada, con censura explícita.

## Conclusiones prohibidas

- Posición inicial exacta en cola o volumen exacto delante al inicio.
- Afirmar que un C seguido de A con otro ID es cancel-replace del mismo participante.
- Inferir intención iceberg/spoofing solo por refill visible.
- Considerar MBP/tape y MBO perfectamente sincronizados.
- Extrapolar supervivencia más allá del cutoff o antigüedad previa al inicio.

## Datos adicionales necesarios

Para completar la hipótesis hay que volver a solicitar MBO incluyendo 00:00:00 UTC del mismo día hasta el cutoff, de modo que llegue el snapshot sintético R + A con `F_SNAPSHOT`. Alternativamente, descargar snapshot histórico y todos los incrementales posteriores sin huecos. Para una unión exacta con estrategia, exportar desde ATAS el timestamp UTC original con 100 ns/ticks o mejor, sequence/feed ID, receive timestamp y contrato raw; idealmente usar tape/MBP derivados del mismo Databento MBO.

## Referencias de semántica

- https://databento.com/docs/schemas-and-data-formats/mbo
- https://databento.com/docs/standards-and-conventions/common-fields-enums-types
- https://databento.com/docs/standards-and-conventions/mbo-snapshot
- https://databento.com/docs/venues-and-datasets/glbx-mdp3
- https://databento.com/docs/examples/order-book/queue-position
