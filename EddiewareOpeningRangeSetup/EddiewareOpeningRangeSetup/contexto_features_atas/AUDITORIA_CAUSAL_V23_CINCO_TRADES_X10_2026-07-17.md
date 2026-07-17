# Auditoría causal v23: cinco trades divergentes en Historia X10

Fecha de cierre de investigación: 2026-07-17

Estrategia: `OR_ABSORPTION_TEST_2026_V23 / Liquidity Burst`

Modo usado: **Historia X10 únicamente**

Replay X1: **DESHABILITADO**

## Conclusión ejecutiva

La baseline v23 no abrió trades con `TP 30 / SL 60`. Los 53 trades nacieron con RR inicial 1.00; los siete casos 60/30 fueron reducciones dinámicas de target por `CVD_RISK_BRACKET_50_PERCENT` después de la entrada. Telegram confundía el `TP_ticks` mutable/final con el TP inicial.

La regresión del reporte no es idéntica a v23 y se detuvo. Conservó 53 trades, 30 wins, 23 losses y WR 56.6038%, pero cambió cinco resultados individuales: 2026-03-30, 2026-04-20, 2026-05-26, 2026-06-02 y 2026-07-15. El efecto neto fue +5 ticks, PF 1.266535 -> 1.282631 y expectancy +5.09434 -> +5.18868 ticks/trade. Por la regla de regresión, no se sustituyó la baseline y no se crearon las ramas A/B/C.

La causa inmediata queda demostrada trade por trade:

| Fecha | Primera divergencia concreta | Efecto causal |
|---|---|---|
| 2026-03-30 | `CvdPullbackLabel` pasa por primera vez a `Riesgo de reversion` a las 09:31:44.420 en la regresión; baseline terminó con 5/5 muestras `Excelente` | target 60 -> 30; TP +30 a las 09:31:44.421 |
| 2026-04-20 | `Signal.CumulativeDelta` 1282 vs 1284 a las 09:31:06.7048302 | baseline alcanza ratio CVD 1.00 a las 09:31:21.535, reduce 60 -> 30; regresión no registra muestra Risk y conserva 60 |
| 2026-05-26 | `SignalTime` 13:34:13.6514324 vs 13:34:13.673186 UTC; `EntryPrice` 29852.50 vs 29851.25 | con stop 29864.00, bracket 46/46 vs 51/51 |
| 2026-06-02 | la regresión emite señal primero, 13:34:18.6809792 vs 13:34:18.720759 UTC; `EntryPrice` 30470.00 vs 30471.25 | el mismo stop 30470.25 es válido en regresión y no válido en baseline: 20/20 vs fallback 60/60 |
| 2026-07-15 | `SignalTime` 13:37:42.74399 vs 13:37:42.7580026 UTC; `EntryPrice` 29901.25 vs 29900.00 | el mismo stop 29900.25 es inválido en baseline y válido en regresión: 60/60 vs 20/20 |

No se modificó la lógica de entrada, Liquidity Burst, CVD, TP/SL, replay, trailing, break-even, time exit ni gestión activa para obtener esta evidencia.

## Identidad y artefactos canónicos

- Código ejecutado por baseline: commit `5fc72154e719d2b2b4a9e536f35d3dda194e3aad`.
- Snapshot inmutable: `baselines/OR_ABSORPTION_TEST_2026_V23_20260716`.
- Rama/commit del congelado: `codex/or-absorption-v23-baseline` / `7295d35f35352815853e88ba2f772e8ce870ba5c`.
- Rama de reporte auditada: `codex/or-absorption-report-rr-x10`.
- Commit de reporte/RR/X10: `534be49f81ce850455afb1066ca8f6a76ac41de4`.
- Regresión fallida preservada: `regressions/OR_ABSORPTION_TEST_2026_V23_REPORT_X10_20260716_FAILED`.
- Comparación tabular: `regressions/OR_ABSORPTION_TEST_2026_V23_REPORT_X10_20260716_FAILED/trade_behavior_diff.csv`.
- Métricas completas: `regressions/OR_ABSORPTION_TEST_2026_V23_REPORT_X10_20260716_FAILED/summary.json`.
- Evidencia compacta de esta investigación: `AUDITORIA_CAUSAL_V23_CINCO_TRADES_X10_2026-07-17.csv`.

Los CSV terminales bajo `raw/X10_R1` y los signal snapshots archivados son la fuente canónica de las dos ejecuciones. Los timelines de la raíz no se consideran cronología inmutable: `InitializeDynamicTimeline()` usa `File.WriteAllText` y una recalculación posterior puede vaciar y reescribir el mismo nombre.

## Cadena de código común

1. `ATASScoreTradeResultExporter.UpdateTradeResult()` (`ATASScoreTradeResultExporter.cs:741-847`) actualiza excursiones, CVD y gestión.
2. `UpdateCvdPullback()` (`ATASScoreTradeResultExporter.cs:1313-1338`) obtiene y registra la muestra CVD.
3. `CumulativeDeltaDetector.CalculatePullback()` (`06_CumulativeDelta_Detector.cs:64-94`) calcula peak/current/ratio.
4. Para SELL, el ratio es `(currentCvd - peakCvd) / (entryCvd - peakCvd)` (`06_CumulativeDelta_Detector.cs:97-121`).
5. Un ratio `>= 0.75` se clasifica `Riesgo de reversion` (`06_CumulativeDelta_Detector.cs:124-135`).
6. `TryApplyCvdRiskBracket()` (`ATASScoreTradeResultExporter.cs:849-875`) llama a `ATASScoreTradeExecutionManager.TryApplyCvdRiskBracket()` (`02_B_ATASScoreTradeExecutionManager.cs:123-150`), que cambia el target a `floor(TpTicks * 0.50)`.
7. Los stops normales se aceptan solo si están detrás de la entrada: BUY `stop < entry`, SELL `stop > entry` (`04_trade_manager_TP_SL_BE_EXIT_TIMEOVER.cs:899-903`).
8. Un stop normal válido construye TP 1:1 (`04_trade_manager_TP_SL_BE_EXIT_TIMEOVER.cs:205-237`). Si no hay stop válido, el SL fallback es 60 ticks (`04_trade_manager_TP_SL_BE_EXIT_TIMEOVER.cs:5,263-268`). Si cualquier lado queda bajo 20 ticks, ambos lados se elevan a 20 (`04_trade_manager_TP_SL_BE_EXIT_TIMEOVER.cs:6,308-339`).

## Trade 1 — 2026-03-30

### Cronología comparada

| Instante NY | Baseline v23 | Regresión | Comparación |
|---|---|---|---|
| 09:31:09.8925707 | BUY 23523.75, CVD entrada 2934, SL/TP inicial 60/60 | idéntico | Los dos JSON tienen SHA-256 `374B06BE788F7062A79B2D54BBF5929C47CFE1C2EB5BC9DEDF5DC68D68115A83`; no hay divergencia de entrada |
| muestras 1-3 | terminaron dentro de las 5 muestras `Excelente` | 3 muestras `Excelente` antes de la alarma | todavía no existe muestra negativa en la regresión |
| 09:31:44.420 | baseline canónica termina con E=5, Risk=0, episodios=0 y cambios=0 | cuarta muestra: `CvdPullbackLabel=Riesgo de reversion`, pullback 1.15, E=3, Risk=1, total=4, primer episodio y primer cambio | **primera divergencia persistida:** `CvdPullbackLabel` |
| 09:31:44.420 | TP permanece 23538.75/60 | `TryApplyCvdRiskBracket`: TP 60 -> 30, 23538.75 -> 23531.25 | cambio causado en la misma llamada de gestión |
| 09:31:44.421 | sigue abierto | `EXIT_TP_DYNAMIC_CVD_RISK_BRACKET_50_PERCENT` a 23531.25, +30 | 1.543 ms después de la alarma |
| 09:32:03.0799849 | `EXIT_TP` a 23538.75, +60 | ya estaba cerrado | resultado final divergente |

El CSV canónico de la regresión registra además `Open_PnL_Ticks_At_Alarm=-15`, `MFE_Ticks_At_Alarm=45`, drawdown desde MFE 60 y `Cvd_NonExcellent_Consecutive_Samples=1`. El valor `Cvd_NonExcellent_Seconds_At_Alarm=0` demuestra que 09:31:44.420 fue la primera muestra no excelente de esa ejecución. La baseline registra cinco muestras, todas `Excelente`; por tanto nunca satisface la condición de la línea 863 y conserva TP60.

El timeline original detallado de la regresión fue sobrescrito por una recalculación posterior. El timestamp y los contadores anteriores permanecen en el CSV terminal canónico; no se sustituyeron por datos de una reproducción posterior.

## Trade 2 — 2026-04-20

### Primera divergencia en el snapshot

Ambas señales se escriben en `2026-04-20T13:31:06.7048302` UTC (09:31:06.7048302 NY), con SELL 26780.00 y SL/TP inicial 60/60. En ese mismo snapshot difieren primero estos campos:

| Campo | Baseline | Regresión |
|---|---:|---:|
| `Signal.CumulativeDelta` | 1282 | 1284 |
| `Signal.Delta` | -144 | -142 |
| `Signal.DeltaChange` | -333 | -331 |
| `Signal.Volume` | 806 | 808 |
| `Signal.Vwap` | 26711.986196445676 | 26711.99217556464 |

La primera variable que entra directamente a la fórmula que decide el bracket es `EntryCvd`: 1282 vs 1284.

### Cadena baseline reproducida y capturada

La traza completa está en:

`regressions/OR_ABSORPTION_TEST_2026_V23_REPORT_X10_20260716_FAILED/causal_trace_x10/pilot7/trials/cycle_01_2026-04-20/captures/000111_dynamic_timeline_1784267995466414100_cf062693faf9.csv`

| Instante NY | Evento baseline | Estado |
|---|---|---|
| 09:31:06.704 | ENTRY | entryCvd=1282, peak=1282, TP=26765.00/60, Excelente |
| 09:31:21.483 | SAMPLE | current=1281, peak=1281, Excelente, precio 26766.25, MFE55 |
| 09:31:21.535 | CVD_LABEL_CHANGE | current=1282, peak=1281: expansion=`1282-1281=1`, pullback=`1282-1281=1`, ratio=`1/1=1.00`, Risk |
| 09:31:21.535 | CVD_LABEL_CHANGE | target 26765.00 -> 26772.50, 60 -> 30 |
| 09:31:21.535 | EXIT_TP | 26772.50, +30 |

La regresión canónica registra CVD entrada 1284, E=3, Risk=0, episodios=0, cambios=0; por ello la condición `CvdPullbackLabel == Riesgo de reversion` nunca se cumple, el target queda en 26765.00/60 y sale `EXIT_TP_INITIAL` a las 09:31:21.551 con +60. La variable concreta que difiere primero es `EntryCvd` a las 09:31:06.7048302; la primera decisión distinta se materializa en el evento Risk de baseline a las 09:31:21.535.

## Trade 3 — 2026-05-26

### Cronología y aritmética

| Dato | Baseline | Regresión |
|---|---:|---:|
| SignalTime UTC | 13:34:13.6514324 | 13:34:13.673186 |
| SignalTime NY | 09:34:13.6514324 | 09:34:13.673186 |
| EntryPrice | 29852.50 | 29851.25 |
| SELL imbalance stop | 29864.00 | 29864.00 |

La baseline emite la señal 21.7536 ms antes. Ese es el primer instante cronológico divergente: a las 13:34:13.6514324 UTC existe una señal/entrada en baseline y todavía no existe en la regresión.

En ambas ejecuciones el predicado SELL `stop > entry` es verdadero, así que se usa el mismo stop:

- baseline: `(29864.00 - 29852.50) / 0.25 = 46` ticks; SL 29864.00; TP 1:1 = 29841.00; TP a las 09:35:02.137;
- regresión: `(29864.00 - 29851.25) / 0.25 = 51` ticks; SL 29864.00; TP 1:1 = 29838.50; TP a las 09:35:07.401.

La variable `EntryPrice` cambia la distancia al stop fijo y, por construcción 1:1, cambia simultáneamente `SL_ticks`, `TP_ticks` y `TP_price`.

## Trade 4 — 2026-06-02

### Cronología y bifurcación de código

| Dato | Baseline | Regresión |
|---|---:|---:|
| SignalTime UTC | 13:34:18.720759 | 13:34:18.6809792 |
| SignalTime NY | 09:34:18.720759 | 09:34:18.6809792 |
| EntryPrice | 30471.25 | 30470.00 |
| SELL imbalance stop | 30470.25 | 30470.25 |

La regresión emite la señal 39.7798 ms antes. A las 13:34:18.6809792 UTC ese evento existe únicamente en la regresión: es la primera divergencia cronológica.

- regresión: `30470.25 > 30470.00` es verdadero. Distancia inicial=1 tick. `EnforceMinimumOneToOneBracket()` eleva ambos lados a 20: SL 30475.00, TP 30465.00; `EXIT_SL_INITIAL` a las 09:34:23.836, -20.
- baseline: `30470.25 > 30471.25` es falso. No se acepta ese stop y entra el fallback de 60: SL 30486.25, TP 30456.25; SL a las 09:35:11.127, -60.

El mismo `BreakoutSideImbalanceStopPrice` cambia de lado respecto de la entrada porque `EntryPrice` cambia 1.25 puntos. Esa comparación booleana concreta selecciona dos ramas distintas y causa 20/20 vs 60/60.

## Trade 5 — 2026-07-15

### Cronología y bifurcación de código

| Dato | Baseline | Regresión |
|---|---:|---:|
| SignalTime UTC | 13:37:42.74399 | 13:37:42.7580026 |
| SignalTime NY | 09:37:42.74399 | 09:37:42.7580026 |
| EntryPrice | 29901.25 | 29900.00 |
| SELL imbalance stop | 29900.25 | 29900.25 |

La baseline emite la señal 14.0126 ms antes. Ese evento de señal es la primera divergencia cronológica.

- baseline: `29900.25 > 29901.25` es falso; fallback 60/60: SL 29916.25, TP 29886.25; TP a las 09:37:51.921, +60.
- regresión: `29900.25 > 29900.00` es verdadero; distancia=1 tick, elevada a 20/20: SL 29905.00, TP 29895.00; TP a las 09:37:43.978, +20.

La variable concreta `EntryPrice` invierte el resultado de `IsStopBehindEntry()` para el mismo stop y determina toda la diferencia posterior.

## Por qué un timeline final puede contradecir el CSV terminal

La captura X10 demuestra múltiples escrituras del mismo trade durante recálculos de indicadores:

- `pilot9` capturó 309 versiones de archivos para 2026-03-30 y 168 para 2026-04-20; ambas pruebas terminaron correctamente y declaran `Replay X1: DESHABILITADO`.
- `pilot7` capturó 585 y 956 versiones, respectivamente.
- `ATASScoreTradeResultExporter.InitializeDynamicTimeline()` abre el nombre compartido con `File.WriteAllText` (`ATASScoreTradeResultExporter.cs:1596-1620`), por lo que una instancia posterior borra la cronología anterior.
- `TryWritePersistedTradeExit()` no reemplaza un resultado de la misma versión si el archivo ya existe (`ATASScoreTradeResultExporter.cs:2708-2730`): el primer escritor terminal queda canónico.
- Las instancias posteriores adoptan ese resultado mediante `TryApplyPersistedTradeExit()` (`ATASScoreTradeResultExporter.cs:2633-2667`).

Estas operaciones de archivo explican de forma determinista por qué el CSV terminal conserva el resultado del primer escritor mientras el timeline visible al final puede pertenecer a otra recalculación. La prueba `pilot9` restauró byte por byte los 19 archivos de estado intervenidos (`restoration_verification.json`, 19/19 `bytes_restored=true`) y no envió Telegram de prueba.

## Estado de RR y reporte

- Baseline: 53/53 trades con RR inicial exacto 1.00; mínimo 1.00; cero fechas inválidas.
- Los cinco trades comparados también nacen >=1:1 en ambas ejecuciones.
- `TP 30 / SL 60` corresponde a target final dinámico, no al plan inicial.
- El reporte corregido separa `Initial_TP_ticks`, `Initial_SL_ticks`, `Initial_RR`, bracket final, motivo de modificación y `Exit_Reason`.
- El guard actual invalida un plan si `TpTicks < SlTicks` antes de abrir y el optimizador rechaza configuraciones con RR inicial <1.

## Decisión y cambio mínimo propuesto

La regresión no puede aprobarse como idéntica. No se debe corregir la sincronización ni cambiar CVD dentro de esta auditoría, porque hacerlo puede cambiar cuál instancia produce el resultado canónico y, por tanto, entradas/salidas.

El siguiente cambio admisible, sujeto a aprobación expresa, es solo de observabilidad: escribir una traza append-only con identificador único por instancia y secuencia, sin que esa traza participe en decisiones de trading. Después se repetirían exactamente las mismas fechas X10 y se exigiría igualdad trade por trade. No se implementó ese cambio aquí.

La baseline `7295d35f35352815853e88ba2f772e8ce870ba5c` permanece inmutable y sigue siendo la referencia del edge v23.
