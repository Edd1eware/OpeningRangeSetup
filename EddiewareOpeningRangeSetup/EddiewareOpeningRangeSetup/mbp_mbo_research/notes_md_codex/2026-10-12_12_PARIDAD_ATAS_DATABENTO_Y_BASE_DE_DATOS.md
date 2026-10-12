# Primero paridad de datos ATAS / Databento

El usuario indicó comparar footprints antes de seguir buscando edge. ATAS será la referencia si difieren; después MBP/MBO se alineará a sus precios. También pidió encontrar el exportador ATAS y guardar los datos en una base para consultas rápidas.

## Entregado

Se encontraron exports históricos CSV de `NetFlowFootprintExporter` en:

`C:/Users/k_99_/Documents/Indicador ATAS/netflow-orderflow-research-db/data/raw/atas_footprint`

No requieren pasar por Excel. Se cargaron800 velas M1 de diez sesiones de julio en una nueva base DuckDB, conservando archivos originales, filas de origen y hashes. La SQLite del proyecto anterior fue inspeccionada en lectura y no se cambió.

Base nueva:

[footprint_research.duckdb](C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/footprint_parity_numeric_v3/footprint_research.duckdb)

[Informe detallado y consultas](C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/footprint_parity_numeric_v3/README.md)

## Comparación

Hay650 minutos con cobertura común completa: diez fechas entre17 y31 de julio,09:25–10:30NY. Los150 minutos ATAS posteriores no tienen tape descargado para cotejar.

| Medida | Hora evento | Hora recepción |
|---|---:|---:|
| Footprints completos idénticos |647/650|635/650|
| Celdas Bid/Ask idénticas |40,381/40,388|40,367/40,388|
| OHLC idénticos después de agrupar |650/650|646/650|
| Footprints de09:30–09:39 idénticos |99/100|98/100|

**No hay coincidencia total.** Persisten siete celdas distintas en22Jul09:52,24Jul09:44 y29Jul09:36 al usar hora de evento. El archivo ATAS tiene83 unidades de volumen adicionales en esas velas; la causa no está demostrada. Se conservan ambos valores y ATAS como referencia.

La rejilla se identificó mediante prints sin agrupar: cada etiqueta es el tick superior de un intervalo de5ticks, `[etiqueta−1.00,etiqueta]`. Equivale a redondear hacia arriba a1.25, no al nivel más cercano. Los OHLC del export también están agrupados: no son una comprobación del OHLC nativo ni autorizan a sustituirlo en OR, cuerpo o VWAP sin revisar la plataforma.

## Calidad y alcance

- Volumen y delta de niveles coinciden internamente con800/800 velas ATAS.
- El20 de julio tiene duplicados numéricamente idénticos de dos versiones; se deduplican claves y se preserva la fuente completa.
- El4 de agosto con tagM1 contiene segundos: queda excluido.
- La versión exacta del DLL exportador, conexión y contrato no constan en los CSV. Los favoritos históricos contienen `NetFlowFootprintExporter` y `ATASFootprintExporterPilot`, pero no se ha localizado su código/DLL exacto. La comparación acredita esos archivos archivados, no toda la instalación actual.
- El fragmento visual del9 de octubre coincide en46/46 celdas legibles con Databento y la misma agrupación; es sólo una muestra parcial adicional.
- No se modificó el replay ni se recalculó WR/PF. Los resultados anteriores siguen siendo reproducciones exploratorias pendientes de equivalencia con ATAS.
- Los cinco MBO descargados son de septiembre y no coinciden con estas diez fechas. No se encontró MBP local. Aún no se ha medido su reacción sobre estos niveles.

Las diferencias se consultan por fecha, minuto, precio y reloj en DuckDB/Parquet; no hace falta abrir Excel. Se verificaron cinco tests del importador y se hizo auditoría independiente. La base actual esv3: conserva nanosegundos exactos en BIGINT para futuros cruces MBP/MBO. Los resultados M1 son idénticos av2. La corrida `numeric_v1` queda supersedida al corregir un desbordamiento de delta sin signo. Los paquetes anteriores se preservan.

[Comparador en navegador](http://127.0.0.1:8765/parity.html): selector de fecha, minuto y reloj; filtro de diferencias; Bid/Ask lado a lado y OHLC nativo frente a agrupado. Se verificaron navegación, filtros, estado sin diferencias y cifras de las dos filas del29Jul09:36; no guarda validaciones ficticias ni recalcula rendimiento.

El siguiente control es verificar con el ATAS actual el contrato, precios nativos frente a agrupados y comportamiento de imbalances/VWAP antes de volver a evaluar señales. No se compraron datos ni se enviaron órdenes.

[Auditoría independiente final](C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/footprint_parity_independent/numeric_v3_audit.json): PASS sin fallos. Se comprobaron hashes, ingesta de las diez DBN, nanosegundos exactos y reconstrucción SQL independiente de ambos relojes.
