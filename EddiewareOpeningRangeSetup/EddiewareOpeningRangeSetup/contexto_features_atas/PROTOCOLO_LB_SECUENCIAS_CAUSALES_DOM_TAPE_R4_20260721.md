# Protocolo R4 — secuencias causales DOM+tape hasta t_decision

## Objetivo

Investigar si el orden causal de agresión, progreso/stall del precio y depleción/reposición del DOM distingue:

- `A_CLEAN_ABSORPTION`;
- `B_CLEAN_CONTINUATION` o breakout limpio;
- `C_VARIABLE_TRADE`, conservada como abstención y nunca usada para entrenar A-vs-B.

La operativa permanece congelada. La nueva salida es exclusivamente observacional.

## Versión y archivos

- Detector: `liquidity-burst-detector-2026-07-21-v6-causal-sequence`.
- Timeline global: `burst_causal_timeline.csv`.
- Runner: `04_run_replay_lb_causal_sequence_dst_2025_2026.py`.
- Analizador: `lb_causal_sequence_research.py`.
- Monitor Telegram: `lb_causal_sequence_monitor.py`.
- Carpeta de corrida: `visual_tests/04_run_replay_lb_causal_sequence_r4_dst_2025_2026_runs`.

## Relojes

- `Burst_Timestamp_UTC`: segundo que contiene el burst.
- `Decision_Timestamp_UTC`: instante real de publicación del detector.
- `Event_Source_Timestamp_UTC`: timestamp entregado originalmente por ATAS.
- `Event_Causal_Timestamp_UTC`: reloj monotónico disponible durante replay.
- `Global_Arrival_Sequence`: orden causal de callbacks recibido por el detector.

En Historia, `depth.Time` no siempre es monotónico. Por ello los eventos DOM conservan el timestamp original para auditoría, pero se ordenan causalmente con el último reloj de trade ya procesado y con el número de llegada. Los trades usan su timestamp real.

Solo se exportan eventos con:

`Event_Causal_Timestamp_UTC <= Decision_Timestamp_UTC`

y se marcan `Model_Eligibility=CAUSAL_PRE_DECISION`.

## Semántica MBP

ATAS entrega profundidad agregada MBP. El timeline usa:

- `DEPTH_INCREASE`;
- `DEPTH_DECREASE`;
- `TAPE_BUY`, `TAPE_SELL` o `TAPE_UNKNOWN`.

No se afirma cancelación, fill, modificación ni refill de la misma orden. Esas identidades requieren MBO.

## Estados derivados

- `AGGRESSION_PROGRESS`;
- `AGGRESSION_STALL`;
- `COUNTERFLOW`;
- `DEPTH_REPLENISHMENT_AHEAD`;
- `DEPTH_DEPLETION_AHEAD`;
- `DEPTH_REPLENISHMENT_BEHIND`;
- `DEPTH_DEPLETION_BEHIND`.

Cada fila conserva además touch, spread, microprice, profundidad L1/L3/L5 e imbalance direccional después del evento.

## Gramáticas preregistradas

Absorción:

`AGGRESSION → AGGRESSION_STALL → DEPTH_REPLENISHMENT_AHEAD → microprice opuesto`

Breakout:

`AGGRESSION → DEPTH_DEPLETION_AHEAD → AGGRESSION_PROGRESS → microprice alineado`

Son hipótesis, no reglas de trading. También se estudiarán transiciones y bigramas descubiertos únicamente en discovery.

## Puerta técnica automática

Antes de la corrida completa se ejecutan cuatro sesiones conocidas por contener Liquidity Bursts:

- 10/03/2025;
- 18/03/2025;
- 27/03/2025;
- 03/04/2025.

La corrida continúa solamente si:

- existen al menos dos BurstId;
- hay eventos DOM y tape;
- la mediana es de al menos diez eventos por BurstId;
- la secuencia comienza en 1 y no contiene huecos;
- el orden global aumenta estrictamente;
- el reloj causal no retrocede;
- no existe ningún evento posterior a t_decision;
- se observa al menos un snapshot de libro válido.

Si falla, el runner publica el motivo y no consume las 256 sesiones.

## Corrida completa

- Historia X10 exclusivamente.
- 256 sesiones DST: 10/03/2025 a 17/07/2026.
- Las cuatro sesiones técnicas se conservan y se saltan al entrar en la etapa completa.
- Telegram publica sesiones, BurstId, eventos, porcentaje causal, ETA, trades y resultado final.

## Validación

- Etiquetas A/B/C se unen después por `BurstId`.
- C no participa en modelos binarios.
- Splits cronológicos y agrupados por sesión/episodio.
- Dirección de cada variable fijada en discovery.
- Comparación de feature individual, gramáticas, regresión logística, random forest y CatBoost.
- Holdout abierto una sola vez al terminar.
- Se reportan AUC, balanced accuracy, matriz de confusión, cobertura y estabilidad BUY/SELL.

## Criterio científico

No se declara separación clara salvo que la evidencia fuera de muestra supere azar, sea estable temporalmente y no invierta dirección entre BUY/SELL. Ningún resultado modifica la estrategia automáticamente.
