# Resumen de traspaso — Liquidity Burst / OR Absorption

Última actualización: 2026-07-19  
Objetivo: permitir continuar el proyecto en un chat nuevo sin perder decisiones, restricciones, resultados ni rutas operativas.

## 1. Objetivo final

Desarrollar y validar una estrategia reproducible en vivo basada en Opening Range y Liquidity Burst que tenga posibilidades reales de pasar una evaluación de LucidPro, preferentemente de $150k, sin lookahead, mentira estadística, overfit ni cambios que rompan la causalidad.

La investigación actual busca anticipar el movimiento cuando aparece la condición visual de posición asociada al detector de absorción/Liquidity Burst. La lógica de entrada v23 convirtió la etiqueta visual `BUY ABSORPTION | SELL POSITION` / `SELL ABSORPTION | BUY POSITION` en una señal causal utilizable por el exporter.

## 2. Rutas principales

Repositorio Git:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup`

Proyecto ATAS/C#/Python:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup`

Datos y estado de corridas:

`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score`

Corridas X10 guardadas:

`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs`

Logs operativos y de investigación:

`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\research_run_logs`

Documentación de contexto:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_features_atas`

DLL de ATAS cuando corresponda desplegar una compilación aprobada:

- `C:\Users\k_99_\AppData\Roaming\ATAS\Indicators\EddiewareOpeningRangeSetup.dll`
- `C:\Users\k_99_\AppData\Roaming\ATAS\Strategies\EddiewareOpeningRangeSetup.dll`

No copiar DLL ni reiniciar ATAS durante una mera reanudación de huecos. Sólo hacerlo después de una modificación aprobada y compilada, verificando que `bin/Release`, `Indicators` y `Strategies` tengan el mismo hash.

## 3. Arquitectura relevante

- Los archivos `.cs` construyen el setup, capturan las señales/features, gestionan el trade y pintan la parte visual.
- `ATASScoreTradeResultExporter.cs` congela el snapshot de entrada, mantiene el ciclo del trade, actualiza MFE/MAE/CVD/gestión y exporta resultados.
- El detector de Liquidity Burst genera el evento de burst y su snapshot.
- Los scripts Python controlan ATAS Replay, esperan CSV terminales, consolidan resultados, calculan métricas y publican en Telegram.
- `trade_inputs.csv` contiene la información causal congelada al entrar.
- `trade_results.csv` contiene outcome, MFE/MAE, motivo de salida y estados dinámicos.
- `burst_events.csv` contiene eventos del burst y su timestamp de disponibilidad.
- `burst_response_events.csv` contiene respuestas posteriores al burst y está marcado como `POST_BURST_ONLY`.

Scripts operativos importantes:

- `04_run_replay_score_trade_results_dst_2025_2026_after_sync.py`: runner principal X10.
- `resume_replay_x10_uia_failfast.py`: reanudación segura sin cambiar la lógica del Replay.
- `replay_sync_runner_common_after_sync.py`: validación y persistencia terminal.
- `replay_start_ui_supervisor.py`: fallback UIA para Start; no cambia fechas, velocidad ni sincronización.
- `telegram_terminal_eta_monitor.py`: mensajes terminales con ETA global.
- `windows_run_awake.py`: evita suspensión sin mover el mouse.
- `post_gap_born_bad_coordinator.py`: valida huecos, ejecuta análisis global y cierra Telegram.
- `born_bad_trade_research.py`: análisis A/B/C/D causal.
- `absorption_breakout_research.py`: construcción de features y análisis cuantitativo auxiliar.
- `telegram_run_summary_after_sync.py`: métricas, equity Lucid y Telegram.

## 4. Restricciones no negociables

1. Preservar el edge antes que mejorar métricas.
2. No introducir lookahead.
3. Mantener causalidad y reproducibilidad en vivo.
4. No optimizar sobre MFE, MAE, resultado, duración ni estados posteriores a la entrada.
5. No modificar entradas, filtros, Liquidity Burst, CVD, trailing, break-even, time exit, salida dinámica, TP o SL sin diagnóstico y autorización explícita.
6. Nunca tocar la lógica de sincronización del Replay para intentar igualar resultados; es frágil y X1/X10 pueden divergir por orden de eventos.
7. El modo oficial de validación actual es Historia X10 únicamente. Replay X1 está deshabilitado como validación/comparación.
8. Una velocidad menor sólo puede considerarse como instrumento diagnóstico de captura si se autoriza expresamente; no debe mezclarse con la muestra oficial X10.
9. Antes de abrir un trade debe cumplirse `initial_target_ticks >= initial_stop_ticks`.
10. El optimizador debe rechazar cualquier combinación con RR inicial menor a 1.
11. Una salida dinámica menor al TP inicial sí está permitida; debe reportarse por su motivo real y no como si fuera el target planeado.
12. No sobrescribir la baseline v23.
13. Si una regresión cambia cualquier entrada, salida, timestamp, precio o PnL, detenerse y generar diff; no sustituir la versión anterior.
14. Los hallazgos estadísticos no autorizan filtros hasta superar significancia corregida, efecto, estabilidad anual, walk-forward y OOS.

## 5. Reglas operativas de reinicio y reanudación

Corrida nueva completa:

- Reiniciar ATAS para cargar la DLL aprobada.
- Reiniciar el estado de resultados de la nueva corrida.
- Reiniciar Telegram y equity exactamente en $150,000.
- Verificar versión y hash antes de aceptar el primer trade.
- Mantener Windows despierto sin mover el mouse.

Reanudación de huecos:

- Detectar primero las fechas realmente no terminales.
- Recorrer sólo esas fechas.
- Usar `--preserve-telegram-history` y no usar `--reset-state`.
- No recompilar, no copiar DLL y no reiniciar resultados/equity.
- La actualización de `telegram_balance.json` es idempotente por fecha; una fecha repetida reemplaza su PnL y no debe contarse dos veces.

Telegram:

- Encabezado de investigación: `ANALISIS  FAMILIAS A, B, C, ETC.`
- Todo mensaje de PnL o `TIME_OVER` debe incluir ETA de toda la corrida.
- Al concluir correctamente debe enviarse `ya termine todos mis procesos`.

## 6. Auditoría v23: TP 30 / SL 60

Conclusión definitiva: la baseline v23 no abrió trades con TP 30 y SL 60.

- Los 53 trades v23 nacieron con RR inicial exacto 1.00.
- El mensaje `TP 30 / SL 60` confundía el target mutable/final con el plan inicial.
- Siete trades nacieron con TP 60 / SL 60 y luego redujeron el target de 60 a 30 por `CVD_RISK_BRACKET_50_PERCENT`.
- Esa reducción ocurrió después de la entrada.
- El comportamiento CVD se conservó; se corrigió la distinción entre plan inicial, modificación dinámica y salida realizada.
- El guard vigente invalida una entrada si `TpTicks < SlTicks`.

Baseline inmutable v23:

- Rama: `codex/or-absorption-v23-baseline`.
- Commit: `7295d35f35352815853e88ba2f772e8ce870ba5c`.
- Exporter: `score-exporter-2026-07-16-v23-liquidity-burst-entry`.
- DLL SHA-256: `49022B2B565CF6A9D3F1F79DEB23765EC5DFEABB533D7C10CD569B5F2CC75`.
- Snapshot: `contexto_features_atas/baselines/OR_ABSORPTION_TEST_2026_V23_20260716`.

## 7. Divergencia causal de cinco trades v23

Una regresión del reporte conservó 53 trades y WR 56.6038%, pero cambió cinco resultados: 2026-03-30, 2026-04-20, 2026-05-26, 2026-06-02 y 2026-07-15. Por la regla de regresión no se aprobó como idéntica y no sustituyó la baseline.

Las primeras variables divergentes quedaron identificadas con timestamp y cadena causal, no como hipótesis:

- En algunos casos cambia primero `Signal.CumulativeDelta`/`EntryCvd`; esa diferencia cambia el ratio de pullback, determina si aparece la etiqueta CVD Risk y, por tanto, si el target baja de 60 a 30.
- En otro caso cambia primero el precio/stop candidato; la comparación causal acepta un bracket mínimo distinto y termina cambiando SL/TP iniciales manteniendo RR 1:1.
- Se observaron múltiples instancias/escritores durante recalculación. El CSV terminal puede conservar el primer resultado canónico mientras un timeline visible posterior pertenece a otra instancia.

Documento con la cronología exacta:

`contexto_features_atas/AUDITORIA_CAUSAL_V23_CINCO_TRADES_X10_2026-07-17.md`

No intentar arreglar esta divergencia tocando la sincronización del Replay.

## 8. Evolución v24 y v25

V24 amplió la captura de features para investigar trades que nacen mal sin modificar la estrategia. La corrida de un año 2025-2026 fue tratada únicamente como generación de hipótesis, no como confirmación.

V25 añadió instrumentación causal de familias de respuesta y análisis observacional. No cambió señales, filtros, parámetros Liquidity Burst, TP/SL, CVD ni gestión.

Versiones v25:

- Exporter: `score-exporter-2026-07-18-v25-response-families`.
- Detector: `liquidity-burst-detector-2026-07-18-v2-response-families`.
- Commit de instrumentación: `8df8eaea6299bb8481d68ab6b1fd0f0169a6fac6`.
- Rama actual: `codex/response-families-v25`.
- Hash de la DLL v25 verificada en las tres rutas: `249FB4BDB0DB46C2A4091FA8AC7E63560B26BF8ABB59633D282DA2657C2435A7`.

Auditoría técnica v25:

`contexto_features_atas/AUDITORIA_CAUSAL_FEATURES_RESPUESTA_V25_20260718.md`

## 9. Estado final de la corrida histórica v25

Rango oficial: 2022-04-04 a 2026-07-16.

- Sesiones planificadas: 735.
- Sesiones terminales válidas: 735.
- Huecos pendientes: 0.
- El único hueco detectado fue 2025-08-21.
- Se recorrió aisladamente en X10, sin resetear equity, resultados ni Telegram.
- Resultado del hueco: `SL`, entrada 23281.25.
- El runner terminó con la marca `TERMINO LA PRUEBA DE TEMPORADAS DST COMPLETAS 2022-2026 V11.`
- El coordinador terminó con `RESEARCH_EXIT code=0` y `ALL_POST_RUN_PROCESSES_COMPLETE`.
- El reporte, tres gráficos y el mensaje final se enviaron a Telegram.
- No queda ningún runner, supervisor, monitor, coordinador ni proceso de investigación Python activo.
- ATAS sigue abierto en Replay con PID 35508 y responde correctamente; la reproducción quedó detenida.

Logs del cierre:

- `research_run_logs/v25_gap_20250821_20260719_095259_stdout.log`.
- `research_run_logs/v25_gap_20250821_20260719_095259_stderr.log`, vacío.
- `research_run_logs/v25_gap_coordinator_20260719_095259_stdout.log`.
- `research_run_logs/born_bad_research_20260719_095514_stdout.log`.
- `research_run_logs/born_bad_research_20260719_095514_stderr.log`, sólo warnings de pandas/scipy, sin excepción fatal.

## 10. Métricas globales v25

- Trades terminales: 500.
- Ganadores: 258.
- Perdedores: 242.
- Break-even: 0.
- WR: 51.60%.
- PF: 0.978835.
- Expectancy: -0.434 ticks/trade.
- Net: -217 ticks.
- Average Win: +38.90 ticks.
- Average Loss: -42.37 ticks.
- MAE promedio / máximo: 23.52 / 110 ticks.
- MFE promedio / máximo: 23.23 / 75 ticks.
- TIME_OVER: 235.
- RR inicial mínimo observado: 1.00.
- Targets modificados dinámicamente: 50.
- Motivo de las 50 modificaciones: `CVD_RISK_BRACKET_50_PERCENT`.
- Cuenta teórica con 6 NQ: $150,000 -> $143,490.
- PnL completo: -$6,510.

La simulación secuencial LucidPro 150k implementada localmente dio `PASS` el 2022-05-25, después de 26 días, con equity $159,780 y sin breach en ese tramo. Esto no demuestra estabilidad de largo plazo: el histórico completo termina en $143,490. No confundir la posibilidad de pasar una evaluación en un tramo con un edge estable en toda la muestra.

Supuestos del simulador local usados en esta corrida:

- Objetivo: $9,000.
- MLL EOD: $4,500.
- DLL: $2,700.
- Tamaño simulado: 6 NQ de un máximo configurado de 10.

Antes de tomar una decisión financiera real deben verificarse nuevamente las reglas vigentes de Lucid en fuente oficial.

## 11. Investigación A/B/C/D sobre Liquidity Burst

Definición congelada:

- A: trade ganador.
- B: trade perdedor con MFE > 30 ticks.
- C: trade perdedor con 2 < MFE <= 30 ticks.
- D: trade perdedor con MFE <= 2 ticks.

Muestra v25:

- Trades Liquidity Burst unidos: 183.
- Filas causales válidas para análisis que requerían captura completa: 141.
- A: 91.
- B: 2.
- C: 19.
- D: 71.
- Split cronológico: 60% discovery, 20% validation, 20% holdout.
- Años: 2022, 2023, 2024, 2025 y 2026.

Resultado principal:

Ninguna variable superó simultáneamente significancia corregida, tamaño de efecto y estabilidad cronológica. No existe autorización estadística para crear filtros o modificar el edge.

Mayores separaciones descriptivas D vs A:

- `Directional_VWAP_Distance_Ticks_AtEntry`: |Cliff delta| 0.319, q 0.8908.
- `PreEntry_Directional_Efficiency3_AtEntry`: |Cliff delta| 0.312, q 0.8908.
- `liquidity_absorption_score`: |Cliff delta| 0.265, q 1.0000.
- `absorption_pressure_1s`: |Cliff delta| 0.265, q 1.0000.
- `burst_efficiency_score`: |Cliff delta| 0.265, q 1.0000.

Son hipótesis de investigación, no señales operables.

## 12. Walk-forward, OOS y redundancia

Cinco candidatos pasaron el gate temporal implementado, pero no el criterio confirmatorio estadístico completo:

- `PreEntry_Directional_Efficiency3_AtEntry`, D vs resto: BA WF 0.603, OOS 0.789.
- `PreBurst_Rotation_Index_10s`, D vs resto: BA WF 0.553, OOS 0.589.
- `Profile_Skewness`, D vs resto: BA WF 0.537, OOS 0.522.
- `BreakOut_TICKS_PER_SEC_AtEntry`, D vs resto: BA WF 0.528, OOS 0.622.
- `BreakOut_TICKS_PER_SEC_AtEntry`, D vs A: BA WF 0.505, OOS 0.686.

Redundancia observada:

- Features numéricas auditables: 104.
- Clusters con |Spearman| >= 0.65: 44.
- Pares con correlación >= 0.90: 100.
- PCA para 80% de varianza: 11 componentes.

Implicación: investigar fenómenos físicos independientes en vez de optimizar muchas variaciones correlacionadas.

## 13. Hallazgo de calidad de datos: Directional CLV

La auditoría causal de `Directional_CLV_AtEntry` reprodujo 0 de 183 filas. El rango causal requerido no estaba disponible de forma suficiente y las filas fueron excluidas; no se rellenaron con OHLC futuro ni se simuló información.

Por tanto, Directional CLV fue una hipótesis prometedora en la corrida de un año, pero no queda validada en el histórico completo. Antes de volver a probarla hay que capturar de forma reproducible el high/low causal disponible exactamente al timestamp de señal.

## 14. Respuesta posterior al burst

- Auditoría: OK.
- Horizontes: 1s, 3s y 5s posteriores.
- Filas descriptivas agregadas: 180.
- Marcado obligatorio: `POST_BURST_ONLY`.
- Nunca se utilizaron como predictores de la entrada del mismo trade.

Las respuestas post-burst pueden servir para diseñar una confirmación causal futura, pero no para reetiquetar retrospectivamente la calidad de la entrada actual.

## 15. Features siguientes propuestas

Disponibles ahora, prioridad alta:

- `seconds_from_open`.
- `or_position_fraction`.
- `execution_cvd_alignment`.
- `velocity_decay_1_5`.
- `delta_decay_1_5`.
- `nearest_profile_reference`.

Instrumentación causal siguiente, aún sin filtros:

1. ATR previo.
2. Overnight range.
3. Opening gap normalizado por ATR.
4. Pendiente causal de VWAP.
5. Migración causal de POC/Value Area.
6. Acceptance dwell ratio.
7. Número de retests de OR/VA/POC.
8. Momentos matemáticos del perfil.

Refill, book imbalance e icebergs sólo deben investigarse si Historia X10 ofrece un stream Level 2 reproducible. Si no es reproducible, deben rechazarse.

## 16. Artefactos finales

Reporte global:

`outputs/born_bad_trade_research_20260719_095531/final_report.md`

Dataset agrupado:

`outputs/born_bad_trade_research_20260719_095531/grouped_trades.csv`

Manifest:

`outputs/born_bad_trade_research_20260719_095531/run_manifest.json`

Gráficos enviados a Telegram:

- `outputs/born_bad_trade_research_20260719_095531/visualizations/group_counts.png`.
- `outputs/born_bad_trade_research_20260719_095531/visualizations/ranking_D_vs_A.png`.
- `outputs/born_bad_trade_research_20260719_095531/visualizations/ranking_D_vs_REST.png`.

Resumen breve anterior:

`contexto_features_atas/HALLAZGOS_RELEVANTES_V25_HISTORICO_COMPLETO_20260719.md`

Reporte completo copiado al contexto:

`contexto_features_atas/INVESTIGACION_TRADES_NACEN_MAL_20260719_095531.md`

## 17. Git y estado del workspace

- Rama actual: `codex/response-families-v25`.
- Commit de v25: `8df8eaea6299bb8481d68ab6b1fd0f0169a6fac6`.
- Commit del cierre histórico: `98b78fa7b4ccda0daad20aacbd928559431a2728`.
- La baseline v23 permanece aparte en `codex/or-absorption-v23-baseline`.

El worktree contiene artefactos generados/modificados por la corrida: workbook, `__pycache__`, `bin/obj`, PDB/DLL y el output de investigación. No hacer `reset --hard`, `checkout --` ni limpieza destructiva. No incluir cambios ajenos de `Nautilus_OR/Nautilus_OR` en commits de Liquidity Burst.

## 18. Decisión actual y punto de reanudación

Decisión actual: no cambiar la estrategia con base en la corrida v25. El histórico completo tiene PF menor que 1 y la investigación no encontró una feature confirmada que permita filtrar el grupo D sin riesgo de overfit.

Punto seguro para el chat nuevo:

1. Leer este documento y `HALLAZGOS_RELEVANTES_V25_HISTORICO_COMPLETO_20260719.md`.
2. Confirmar que no existe una corrida activa antes de tocar ATAS o estados.
3. Elegir una nueva hipótesis causal, preferentemente mejorar la captura de CLV o instrumentar ATR/overnight/gap/VWAP/POC.
4. Modificar sólo instrumentación/exportación, no la lógica de entrada o gestión, salvo autorización explícita.
5. Ejecutar tests de causalidad y disponibilidad temporal.
6. Abrir una corrida nueva únicamente después de fijar versión, hash, fechas y política de reset.
7. Mantener el holdout ya abierto fuera de cualquier selección posterior de thresholds.

La prioridad sigue siendo preservar el edge y producir evidencia reproducible, incluso si la conclusión correcta es no modificar la estrategia.
