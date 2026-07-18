# Auditoría causal e instrumentación v25 — Response Families

Fecha: 2026-07-18  
Modo autorizado: Historia X10 únicamente  
Replay X1: deshabilitado  
Rango programado: 2022-04-04 a 2026-07-16

## Decisión

La lógica de trading permanece congelada. No se modificaron entradas, filtros, parámetros de Liquidity Burst, TP, SL, break-even, trailing, CVD ni reglas de salida. Los cambios de v25 son exclusivamente instrumentación y análisis observacional.

La corrida anual v24 sigue siendo generación de hipótesis. Ninguna feature, incluido `Directional_CLV_AtEntry`, está autorizada como filtro hasta superar estabilidad multi-año, walk-forward y out-of-sample.

## Hallazgo 1 — El CLV v24 no era auditable de forma concluyente

La fórmula v24 era:

`side_sign * (2 * entry_price - candle_high - candle_low) / (candle_high - candle_low)`

El snapshot no guardó el `High` y `Low` exactos utilizados ni demostró si ATAS entregó el rango parcial conocido al instante de la señal o el OHLC final de la vela. Por ello, el resultado anual de CLV no constituye evidencia causal confirmada.

v25 conserva el OHLC de plataforma sólo como auditoría y construye el CLV elegible con precios de trades que cumplen:

- mismo bar de entrada;
- timestamp real menor o igual al timestamp de la señal;
- al menos dos observaciones;
- rango causal positivo;
- fórmula reproducible exactamente desde los campos exportados.

Campos añadidos:

- `Causal_Entry_High_AtEntry`
- `Causal_Entry_Low_AtEntry`
- `Causal_Entry_Range_Ticks_AtEntry`
- `Causal_Entry_Observation_Count_AtEntry`
- `Causal_Entry_First_Timestamp_UTC`
- `Causal_Entry_Last_Timestamp_UTC`
- `Causal_Entry_Source_AtEntry`
- `CLV_Causality_Status_AtEntry`
- `Platform_Candle_High_AtEntry`
- `Platform_Candle_Low_AtEntry`
- `Platform_Directional_CLV_AtEntry`
- `Platform_vs_Causal_CLV_Diff_AtEntry`

Una fila sólo puede usar CLV en modelos si `CLV_Causality_Status_AtEntry = CAUSAL_EVENT_RANGE`. Las demás quedan en el dataset de auditoría, pero el CLV se convierte en ausente para el análisis.

## Hallazgo 2 — Diferencia entre timestamp del evento y disponibilidad de la feature

Liquidity Burst agrupa trades en buckets de un segundo. El evento conserva su timestamp histórico en el inicio del bucket porque ese timestamp forma parte del comportamiento actual de la estrategia. Sin embargo, las estadísticas completas del bucket sólo están disponibles cuando termina ese segundo.

Modificar el timestamp consumido por la estrategia podría alterar entradas y el edge, por lo que no se hizo. En su lugar se añadió al CSV:

- `Timestamp_UTC`: timestamp histórico del evento, sin cambios;
- `Feature_Available_Timestamp_UTC`: instante causal en que el bucket completo ya está disponible, `Timestamp_UTC + 1 segundo`.

El pipeline científico usa exclusivamente `Feature_Available_Timestamp_UTC <= prediction_timestamp`. Así se preserva la operativa y se evita acreditar como preentrada una feature que todavía no estaba completamente formada.

Las respuestas posteriores usan el mismo contrato:

- `Burst_Feature_Available_Timestamp_UTC`
- `Response_Available_Timestamp_UTC`
- horizontes de 1, 3 y 5 segundos medidos desde la disponibilidad del burst.

## Familias instrumentadas

### Preentrada causales

- Acceptance/Reclaim: dwell ratio, reclaims y velocidad de rechazo.
- Persistence/Exhaustion: supervivencia y pendiente de decaimiento del impulso.
- Effort vs Price Response: ticks por delta y ticks por volumen.
- Auction Theory: momentos del perfil, entropía, concentración, multimodalidad, percentil de posición y migración causal de POC.
- Temporal Sequence: rotation index, entropía local y eficiencia de trayectoria.

### Posteriores al burst, no elegibles como predictors

`burst_response_events.csv` contiene respuestas a 1, 3 y 5 segundos. Todas las filas declaran:

- `AvailableBeforeEntry = 0`
- `Model_Eligibility = POST_BURST_ONLY`

Estas variables se analizan como outcomes descriptivos para generar hipótesis. Nunca se incorporan a `FEATURE_NAMES`, a las entradas ni a filtros.

### Liquidity Response

Refill, depth recovery, MBO/MBP e icebergs se excluyen. Historia X10 no ha demostrado todavía un stream de libro reproducible con el contrato requerido; no se simulan datos ausentes.

## Protocolo confirmatorio de la corrida completa

La investigación v25 exporta:

- matriz Pearson y Spearman;
- clustering jerárquico por correlación;
- PCA y varianza explicada;
- VIF;
- mutual information entre features y MI con la etiqueta sólo en discovery;
- estabilidad por año;
- walk-forward expansivo, con thresholds calculados sólo en train;
- último año como OOS;
- análisis post-burst separado.

Gate mínimo de confirmación:

1. mismo signo en al menos tres años;
2. dirección estable en al menos dos folds walk-forward;
3. balanced accuracy walk-forward mediana mayor a 0.50;
4. balanced accuracy del último año OOS mayor a 0.50;
5. causalidad y fórmula reproducibles;
6. información no redundante frente a Delta, Velocity, Imbalance y CLV.

Pasar este gate sólo convierte una variable en candidata científica. No crea automáticamente un filtro ni autoriza modificar la estrategia.

## Versiones y validación técnica

- Exporter: `score-exporter-2026-07-18-v25-response-families`
- Liquidity Burst detector: `liquidity-burst-detector-2026-07-18-v2-response-families`
- Compilación Release: correcta, 0 errores.
- Pruebas Python de causalidad/leakage: 11 correctas.
- Balance de Telegram para la nueva corrida: debe reiniciarse y verificarse en `$150,000` antes de aceptar el primer resultado.

## Archivos involucrados

- `ATASScoreTradeResultExporter.cs`
- `12_LiquidityBurstDetector.cs`
- `absorption_breakout_research.py`
- `born_bad_trade_research.py`
- `replay_sync_runner_common_after_sync.py`
- `replay_start_ui_supervisor.py`
- `04_run_replay_score_trade_results_dst_2025_2026_after_sync.py`
- `test_born_bad_trade_research.py`

## Salvaguarda final

Si la instrumentación observacional cambia cualquier entrada, salida, precio, timestamp operativo o PnL frente a la lógica congelada, la corrida deberá detenerse y el cambio no podrá presentarse como una simple mejora de reporte.
