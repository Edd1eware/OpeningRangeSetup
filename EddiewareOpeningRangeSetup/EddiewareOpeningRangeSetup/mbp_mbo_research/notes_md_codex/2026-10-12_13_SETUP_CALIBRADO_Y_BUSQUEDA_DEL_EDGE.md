# Setup calibrado: referencia y una pista experimental

El usuario pidió retomar el edge después del cotejo ATAS/Databento y medir imbalance +VWAP +cuerpo a favor de ruptura. Se fijaron las reglas antes de calcular nuevos outcomes y se ejecutaron150 sesiones disponibles, del9Mar al9Oct2026. Todas corresponden a DST de Nueva York. No cubre fechas posteriores todavía no descargadas.

## Resultado principal

| Política RR1:1 | Trades | TP | SL | WR | PF neto,1NQ | PF neto,R | Neto,1NQ | Neto,R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Reglas del usuario: apertura fuera permitida |78|33|45|42.31%|0.602|0.572|−USD5,937|−23.56R|
| Control experimental: apertura dentro del OR |35|19|16|54.29%|1.382|0.959|+USD1,515|−0.79R|

No hay un edge confirmado. La referencia completa tiene expectativa negativa en ambas mitades. El control dentro del rango mejora y gana dinero con un contrato constante, pero su expectativa porR es ligeramente negativa y los intervalos son amplios. Un stop variable pondera de forma distinta un NQ constante y riesgo constante; PF monetario y PF_R no son equivalentes. El resultado favorable de un control tampoco convierte35 trades en evidencia suficiente para una evaluación Lucid.

## Qué cambió tras la paridad

Se conservan como fuente principal las diez fechas con export ATAS; otras140 se reconstruyen con Databento sobre la rejilla calibrada. Las ejecuciones usan trades nativos Databento en las150. Para señales, OHLC/OR/cuerpo y Close de VWAP usan etiquetas superiores ceil5, según los exports comparados; el reloj es ts_event. Se aplica cuerpo estricto a favor y ratio de imbalance estrictamente>3, mínimo70, comparación diagonal interna de cinco ticks, referencias cero permitidas. La adaptación a filas agrupadas no certifica la DLL instalada.

OR09:30–09:31NY; primer cierre09:32 y último09:40; primera señal válida, una por día. VWAP de cierres M1 ponderados por volumen desde09:30. Imbalance de la propia vela, sin exigir filas consecutivas. SL tras la banda alineada más lejana más cinco ticks nativos; long etiqueta−2.25puntos, short etiqueta+1.25. RR1:1.

Supuestos de ejecución: siguiente print por evento desde el cierre más un tick adverso; SL al primer cruce más un tick adverso; TP exacto; comisión USD4 round trip/NQ; timeout30min. Son supuestos del estudio, no fills de ATAS. Dos operaciones de la referencia tienen primer print exactamente enSL y riesgo simulado1tick por deslizamiento; permanecen marcadas y requieren revisión. El control no contiene esos casos.

## Un único control adicional

Se repitió la hipótesis conocida de apertura dentro del OR, sin buscar umbrales nuevos ni combinar filtros. Se eligió la primera vela base válida que además cumpliese ORLow≤Open≤ORHigh. No es un recorte de trades ganadores: de35 señales,32 coinciden con referencia y tres fechas toman una señal posterior válida:8Jul,5Ago y6Ago. El usuario acepta aperturas fuera: el control no modifica silenciosamente sus reglas.

## Tabla mensual

| Mes2026 | Trades base | WR base | PF1NQ base | Trades dentro | WR dentro | PF1NQ dentro |
|---|---:|---:|---:|---:|---:|---:|
| Marzo,desde9 |7|28.57%|0.358|3|33.33%|0.179|
| Abril |11|45.45%|1.013|7|57.14%|3.039|
| Mayo |11|45.45%|0.338|3|66.67%|0.296|
| Junio |13|46.15%|1.513|4|50.00%|7.038|
| Julio |12|33.33%|0.709|5|40.00%|0.635|
| Agosto |11|45.45%|0.254|6|83.33%|6.217|
| Septiembre |9|55.56%|1.453|6|50.00%|1.537|
| Octubre,hasta9 |4|25.00%|0.265|1|0.00%|0.000|

Los meses con pocas operaciones no se convierten en filtros de calendario. La muestra completa ya se exploró anteriormente.

## Auditoría e incertidumbre

13tests de referencia y6del control aprobados. Auditorías independientes PASS:1350 candidatos por estudio,78y35 primeros cruces crudos, precios/SL/TP/costes, fuente y primera selección. Ninguna operación censurada, ningún timeout, ninguna sesión excluida. Las métricas recalculadas desde CSV coinciden con el motor. No hubo información recibida después de la entrada según Databento; una señal recibió un print después del cierre pero antes de entrar. El export ATAS no registra recepción propia.

Control dentro: WR Wilson95%38.19–69.53%; bootstrap circular5sesiones/5000repeticiones, expectativa ticks por trade IC95%[−16.37,+31.32], expectativaR[−0.439,+0.377] y PF1NQ[0.554,4.039]. Son intervalos exploratorios y no corrigen la selección histórica ni prueban edge.

El diagnóstico de referencia verificó78/78 rutas MAE/MFE. Compras37trades, WR27.03%; ventas41,WR56.10%, pero PF monetario0.703. Son subdivisiones descriptivas; no se adopta un filtro de dirección ni se concluye rentabilidad de trailing porque una pérdida haya avanzado antes a favor.

## Dónde revisar

- Navegador local: http://127.0.0.1:8765/edge.html, tablas generales/mensuales, incertidumbre y descargas. El visor anterior de81 trades queda identificado como histórico.
- Workspace: `C:/Users/k_99_/Documents/ChatGPT/research_edge`.
- Planes: `CALIBRATED_SETUP_REPLAY_PLAN.md` y `CALIBRATED_INSIDE_CONTROL_PLAN.md`.
- Referencia: `outputs/calibrated_setup_replay_v1/README.md`; control: `outputs/calibrated_inside_control_v1/README.md`.
- Auditorías: `outputs/calibrated_setup_audit_v1` y `outputs/calibrated_inside_audit_v1`, con `logical_audit.json` y `statistics.json`.
- Diagnóstico: `outputs/calibrated_setup_diagnostics_v1`.

La búsqueda sigue abierta. La pista de apertura dentro requiere reproducción manual/ATAS y validación posterior; no se ajusta el histórico hasta forzar60%. No se han comprado datos, instalado indicadores ni enviado órdenes. Trailing continúa pospuesto; después se mantiene la secuencia navegador→C#/ATAS→indicador de propuestas para confirmación manual.
