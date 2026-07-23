# Solicitud de hipótesis mecanísticas a Claude Fable — Liquidity Burst A vs B

Responde en español y entrega el informe final completo en una sola respuesta. No tienes herramientas y no debes pedir leer archivos adicionales. Todo lo necesario está en este expediente y en los anexos concatenados después.

## Objetivo operacional exacto

El detector identifica primero un `Liquidity Burst`: un segundo de agresión anormal BUY o SELL. En el callback causal que publica ese evento —sin esperar 1, 3 o 5 segundos— queremos distinguir:

- **A_TRUE_ABSORPTION**: la estrategia contraria al burst llega a TP; MAE ≤10 ticks; MFE ≥ TP inicial. Físicamente, la agresión fue absorbida y el fade funcionó casi de inmediato.
- **B_CLEAN_BREAKOUT**: el fade llega a SL; MFE ≤10 ticks; MAE ≥ SL inicial. Físicamente, la agresión desplazó el precio limpiamente y continuó.
- **C_MIXED_PATH**: TP/SL con excursión intermedia; se trata como abstención.

La entrada actual es contraria a `BurstSide`. El objetivo científico no es mejorar retrospectivamente WR/PF: es encontrar información observable en el callback que anticipe si el burst será absorbido o continuará.

## Restricciones no negociables

1. Cero look-ahead: no usar respuesta 1/3/5s, MAE, MFE, salida, resultado ni campos posteriores al callback.
2. Cero demora artificial: si la feature requiere esperar confirmación, no resuelve este objetivo.
3. 2025–2026 ya fue abierto y sólo sirve para generar hipótesis. Una validación real tendrá que ser forward/no vista.
4. No presentar SHAP, importancia de árbol o una AUC post-hoc como validación.
5. No proponer aliases algebraicos ni renombrar variables existentes.
6. Distinguir explícitamente evidencia observada, inferencia mecanística e hipótesis especulativa.

## Evidencia disponible

- Discovery 2022–2024: 70 A/B (29 A, 41 B).
- Muestra nueva abierta 2025–2026: 45 A/B (15 A, 30 B); 2025=34, 2026=11.
- Total combinado post-holdout: 115 A/B.
- Baseline congelado en 2025–2026: AUC 0.336; balanced accuracy 0.35; permutación p=0.993.
- CatBoost regularizado, sin tuning sobre 2025–2026:
  - CORE_FROZEN AUC 0.384, p=0.942.
  - BURST_MECHANISM AUC 0.436, p=0.840.
  - ALL_CAUSAL (119 variables elegibles) AUC 0.327, p=0.987.
  - BURST_MECHANISM − CORE: +0.051, bootstrap 95% [−0.113,+0.216].
  - 0 variables univariadas sobrevivieron estabilidad 2025/2026, BUY/SELL y BH; q mínimo efectivo 0.996.
- La reversión de signo aparece entre eras y entre lados. No hay mecanismo de régimen demostrado.

## Pruebas de libro ya realizadas

### MBP/DOM local previo

Se probaron en ventanas 1/3/5/10s, únicamente en el precio del burst y el nivel de referencia: start/end/min/max depth, cambio neto, add/remove, depth balance, refill/remove, recovery from min, level survived, update count, last update age, agresión/counterflow, refill latency y ratios frente a agresión.

Resultado: 0 features robustas; MBP-only holdout AUC 0.461 logística y 0.511 random forest; baseline+MBP AUC 0.283/0.250. Limitación: no reconstruía de forma confiable touch y top-N simultáneos.

### MBO previo

30 eventos balanceados, 360,492 mensajes causales. Se midieron altas, cancelaciones puras, modificaciones, fills, supervivencia, short-lived, refill 10/50/100/250ms, churn, reutilización de order_id y asimetrías.

Resultado: baseline LOYO 0.796; MBO-only 0.387; baseline+MBO 0.569; delta −0.227, p=0.998. Ninguna de 12 variables compactas fue robusta. Se detuvo la compra de más MBO.

## Familia DOM_GEOMETRY nueva ya instrumentada

La medición se hace dentro del detector con el estado del DOM recibido por ATAS hasta el callback. No se reconstruye offline usando eventos posteriores. `depth.Time` no es monotónico en replay, por lo que pull/stack usa orden causal de callbacks anclado al último trade procesado.

Se exige snapshot válido: cinco niveles Bid y Ask, best bid < best ask, spread 1–4 ticks y midpoint a ≤4 ticks del precio del burst. Si falla, todas las features DOM quedan nulas y se exporta la razón.

Predictores prerregistrados:

1. `DOM_Spread_Ticks = (bestAsk-bestBid)/tick`; esperado B>A.
2. `DOM_Directional_Microprice_Ticks = burstSign*(microprice-mid)/tick`; esperado B>A.
3. `DOM_Directional_Depth_Imbalance_L1 = burstSign*(bidDepth1-askDepth1)/(bid+ask)`; esperado B>A.
4. Lo mismo L3; esperado B>A.
5. Lo mismo L5; esperado B>A.
6. `DOM_Ahead_Depth_Per_Aggressive_L3 = aheadPassiveDepth3/grossAggressive[−1,0]`; esperado A>B.
7. `DOM_Ahead_L1_Concentration_L5 = aheadDepth1/sum(aheadDepth1..5)`; esperado A>B.
8. `DOM_Directional_PullStack_1s = (behindNetAdd-aheadNetAdd)/sum(abs(depthChanges top5))`; esperado B>A.
9. Lo mismo 3s; esperado B>A.
10. `DOM_Ahead_Stack_Share_1s = aheadAdds/(aheadAdds+aheadRemoves)`; esperado A>B.
11. `DOM_Near_Churn_Per_Aggressive_1s = sum(abs(depthChanges top5))/grossAggressive[−1,0]`; esperado A>B.

No usar best bid/ask absolutos, level count, update count o validez como señales económicas; son campos de auditoría.

## Tu tarea

1. Evalúa si la familia DOM_GEOMETRY mide mecanismos plausiblemente diferentes de las pruebas MBP/MBO que fallaron o si es otra reformulación del mismo espacio sin información.
2. Formula una explicación física paso a paso de qué debería ocurrir antes y durante el segundo del burst en A y en B: órdenes pasivas, agresores, trayectoria de prints, vacíos, refill, cancelaciones y localización respecto a referencias.
3. Propón hasta **12 hipótesis nuevas y específicas** que tengan probabilidad razonable de separar A/B exactamente en el callback. Para cada una entrega:
   - nombre único;
   - mecanismo físico;
   - fórmula exacta;
   - fuente mínima (tape por print, DOM/MBP, MBO, sesión previa, etc.);
   - ventana causal exacta;
   - timestamp de disponibilidad;
   - signo A vs B esperado y por qué;
   - interacción de régimen prevista;
   - variables existentes con las que puede ser redundante y prueba de redundancia;
   - prueba de falsación y condición STOP;
   - costo de instrumentación y riesgo de error en replay.
4. Prioriza por información incremental esperada, no por facilidad. Rechaza explícitamente propuestas que necesiten post-burst.
5. Considera representaciones de trayectoria/eventos —curvatura, secuencia, hazard, tiempo de mercado— si contienen información que los agregados actuales destruyen.
6. Audita la definición A/B/C: explica si la etiqueta basada en resultado y excursión ≤10 ticks puede volver imposible aprender el mecanismo y diseña una prueba de sensibilidad que no cambie etiquetas después de mirar features.
7. Diseña el **experimento mínimo** que decida si continuar con DOM, incluyendo tamaño de piloto, balance por año/lado, métricas, permutación, control de múltiples pruebas, criterio de cobertura, estabilidad y puerta STOP/CONTINUE.
8. Concluye con:
   - veredicto sobre las 11 DOM actuales;
   - shortlist máxima de 5 hipótesis para implementar primero;
   - qué no medir;
   - decisión STOP/CONTINUE y el siguiente paso exacto.

Sé adversarial. Si la evidencia indica que ninguna medición en t0 puede separar de forma útil porque la diferencia sólo se revela después, dilo claramente y especifica cómo demostrar esa imposibilidad empíricamente.
