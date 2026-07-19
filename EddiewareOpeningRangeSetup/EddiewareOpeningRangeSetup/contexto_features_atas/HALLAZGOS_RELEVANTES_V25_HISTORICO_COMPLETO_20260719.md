# Hallazgos relevantes — V25 histórico completo

Fecha de cierre: 2026-07-19  
Modo: Historia X10 únicamente  
Replay X1: DESHABILITADO  
Versión del exporter: `score-exporter-2026-07-18-v25-response-families`  
Commit de instrumentación: `8df8eaea6299bb8481d68ab6b1fd0f0169a6fac6`

## Cierre de cobertura

- Rango oficial: 2022-04-04 a 2026-07-16.
- Sesiones planificadas: 735.
- Sesiones terminales válidas: 735.
- Sesiones pendientes: 0.
- Único hueco encontrado: 2025-08-21.
- El hueco se recorrió de forma aislada, sin repetir fechas ya válidas.
- Resultado terminal del hueco: `SL`, entrada 23281.25.
- No se reiniciaron el balance, los resultados ni el historial de Telegram.
- No se recompiló ni se copió una DLL para completar el hueco.
- No se modificó la lógica de trading ni la sincronización del Replay.

## Resultado global de la corrida

- Trades terminales: 500.
- Ganadores: 258.
- Perdedores: 242.
- Break-even: 0.
- Win rate: 51.60%.
- Profit factor: 0.9788.
- Expectancy: -0.434 ticks por trade.
- Net: -217 ticks.
- Average win: +38.90 ticks.
- Average loss: -42.37 ticks.
- MAE promedio / máximo: 23.52 / 110 ticks.
- MFE promedio / máximo: 23.23 / 75 ticks.
- TIME_OVER: 235.
- Equity teórica, seis contratos NQ: $150,000 -> $143,490, PnL -$6,510.
- RR inicial mínimo observado: 1.00.
- Targets modificados dinámicamente: 50, todos por `CVD_RISK_BRACKET_50_PERCENT`.

La simulación secuencial de LucidPro 150k incluida en el reporte alcanzó el objetivo el 2022-05-25, tras 26 días operados, con equity $159,780 y sin breach registrado en ese tramo. Esto no convierte el histórico completo en rentable: la misma serie completa acaba en $143,490. Deben tratarse como preguntas distintas: posibilidad de pasar una evaluación en un tramo y estabilidad del edge a largo plazo.

## Muestra de investigación de Liquidity Burst

- Trades Liquidity Burst unidos a features: 183.
- Filas causales válidas para los análisis que exigían disponibilidad completa: 141.
- Grupo A, ganadores: 91.
- Grupo B, perdedores con MFE > 30: 2.
- Grupo C, perdedores con 2 < MFE <= 30: 19.
- Grupo D, perdedores con MFE <= 2: 71.
- Años observados: 2022, 2023, 2024, 2025 y 2026.
- Split cronológico congelado: 60% discovery, 20% validation y 20% holdout.

## Hallazgo principal

Ninguna variable disponible superó simultáneamente significancia corregida, tamaño de efecto y estabilidad cronológica. Por tanto, esta corrida no demuestra una feature capaz de identificar de manera robusta los trades que nacen mal y no autoriza crear filtros ni cambiar la estrategia.

Las mayores separaciones descriptivas de D frente a A aparecieron en:

1. `Directional_VWAP_Distance_Ticks_AtEntry`, Cliff delta absoluto 0.319.
2. `PreEntry_Directional_Efficiency3_AtEntry`, Cliff delta absoluto 0.312.
3. `liquidity_absorption_score` y `absorption_pressure_1s`, Cliff delta absoluto 0.265.
4. `burst_efficiency_score`, Cliff delta absoluto 0.265.

Sin embargo, sus valores q corregidos fueron 0.8908 o 1.0000 y ninguna quedó clasificada como robusta. Son hipótesis de trabajo, no evidencia para operar.

## Validación temporal

Cinco candidatos pasaron el gate temporal implementado de estabilidad anual, walk-forward y último año OOS:

- `PreEntry_Directional_Efficiency3_AtEntry`, D vs resto: BA walk-forward mediana 0.603; OOS 0.789.
- `PreBurst_Rotation_Index_10s`, D vs resto: BA 0.553; OOS 0.589.
- `Profile_Skewness`, D vs resto: BA 0.537; OOS 0.522.
- `BreakOut_TICKS_PER_SEC_AtEntry`, D vs resto: BA 0.528; OOS 0.622.
- `BreakOut_TICKS_PER_SEC_AtEntry`, D vs A: BA 0.505; OOS 0.686.

Estos cinco candidatos no superaron el criterio confirmatorio estadístico completo. No deben convertirse en reglas ni thresholds todavía.

## Hallazgo de calidad de datos

La auditoría causal de `Directional_CLV_AtEntry` no pudo reproducir una sola fila válida: 0 de 183. Las filas se excluyeron en vez de rellenarlas o reconstruirlas con información futura. Hasta corregir la disponibilidad causal del rango, Directional CLV no puede considerarse validada en este histórico.

También se detectó alta redundancia:

- Features numéricas auditables: 104.
- Clusters con |Spearman| >= 0.65: 44.
- Pares con correlación >= 0.90: 100.
- Componentes PCA necesarios para explicar 80% de la varianza: 11.

Esto aconseja representar fenómenos físicos independientes y evitar optimizar decenas de variantes altamente correlacionadas.

## Respuesta posterior al burst

- Auditoría temporal: OK.
- Filas descriptivas por horizonte, familia y métrica: 180.
- Los horizontes 1s, 3s y 5s están marcados `POST_BURST_ONLY`.
- No se usaron como predictores de la entrada del mismo trade.

Estas respuestas sirven para diseñar una confirmación causal futura o para describir cómo evoluciona el burst, pero no para reetiquetar retrospectivamente la calidad de una entrada.

## Próximas hipótesis con mejor relación causalidad/complejidad

Prioridad inmediata usando datos ya disponibles:

- `seconds_from_open`.
- `or_position_fraction`.
- `execution_cvd_alignment`.
- `velocity_decay_1_5`.
- `delta_decay_1_5`.
- `nearest_profile_reference`.

Siguiente instrumentación propuesta, todavía sin convertirla en filtro:

1. ATR previo, overnight range y gap normalizado.
2. Pendiente causal de VWAP y migración de POC/Value Area.
3. Acceptance dwell ratio y número de retests de OR/VA/POC.
4. Momentos matemáticos del perfil.
5. Refill, book e icebergs sólo si Historia X10 demuestra un stream reproducible.

## Artefactos y Telegram

Reporte global:

`outputs/born_bad_trade_research_20260719_095531/final_report.md`

Gráficos enviados a Telegram:

- `visualizations/group_counts.png`.
- `visualizations/ranking_D_vs_A.png`.
- `visualizations/ranking_D_vs_REST.png`.

El análisis terminó con código 0. El coordinador registró `ALL_POST_RUN_PROCESSES_COMPLETE`; esa marca ocurre después de enviar el reporte, los tres gráficos y el mensaje `ya termine todos mis procesos`.

Logs de cierre:

- `research_run_logs/v25_gap_20250821_20260719_095259_stdout.log`.
- `research_run_logs/v25_gap_20250821_20260719_095259_stderr.log` (vacío).
- `research_run_logs/born_bad_research_20260719_095514_stdout.log`.
- `research_run_logs/born_bad_research_20260719_095514_stderr.log` (advertencias de rendimiento y precisión numérica; sin excepción fatal).

## Decisión

No modificar el edge con base en esta corrida. El siguiente paso válido es mejorar la captura causal de las features propuestas, especialmente el rango necesario para CLV, y repetir el mismo protocolo congelado sin seleccionar thresholds sobre el holdout ya abierto.
