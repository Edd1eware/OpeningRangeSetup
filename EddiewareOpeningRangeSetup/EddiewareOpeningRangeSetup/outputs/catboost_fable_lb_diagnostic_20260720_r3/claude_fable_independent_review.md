# Revisión independiente de Claude Fable — Liquidity Burst A vs B

## 1. Veredicto CatBoost

**No hay información no lineal incremental demostrada. Todo es consistente con inestabilidad de muestra chica.**

| Evidencia | Valor | Lectura |
|---|---|---|
| AUC fuera de era (n=45) | 0.327–0.436 | Todas por debajo del azar |
| p permutación | 0.84–0.99 | La nula no se rechaza en ningún corte |
| Delta AUC BURST_MECHANISM vs CORE | +0.051, IC95 [−0.113, +0.216] | Cruza cero; P(delta>0)=0.723 no es evidencia |
| Delta AUC ALL_CAUSAL | −0.058 | Las 119 features restan frente al core |
| Features univariadas estables | 0, q=0.996 uniforme | La corrección múltiple elimina todo |
| AUC n=11 (2026) | 0.067–0.333 | Sin precisión suficiente |

Puntos centrales:

- La desviación nula aproximada de AUC es ±0.088 con n=45 y ±0.18 con n=11. Gran parte de los movimientos observados cabe en fluctuación aleatoria.
- Las interacciones de un árbol de profundidad 2 entrenado con 70 eventos y 119 variables no son evidencia física sin réplica fuera de era.
- SHAP explica un modelo con AUC 0.327: describe sus decisiones y errores, no valida el mecanismo.
- Las mejores AUC univariadas fueron seleccionadas después de abrir 2025–2026 y entre muchas variables; son hipótesis, no estimaciones de desempeño.

## 2. Reversión 2022–2024 frente a 2025–2026

**La evidencia disponible no establece un mecanismo.**

Hechos:

1. La inestabilidad aparece entre eras, entre 2025 y 2026 y entre BUY y SELL. Ese patrón es compatible con ruido de muestra pequeña.
2. Las estimaciones de 2026 descansan en sólo 11 eventos.
3. El AUC 0.327 de ALL_CAUSAL sugiere una posible inversión leve de las direcciones aprendidas, pero no la demuestra.

Hipótesis, no conclusiones:

| Hipótesis | Mecanismo | Prueba |
|---|---|---|
| Ruido puro | La muestra no soporta estimaciones estables de dirección | Ya es consistente con p de permutación 0.84–0.99 |
| Variables crudas más cambio de régimen | Umbrales de volatilidad, volumen y delta cambian entre eras | Normalizar contra baseline histórico de sesión y hora |
| Fragilidad de la etiqueta | Casos cercanos al umbral A/B/C cambian de clase con pequeñas perturbaciones | Auditoría de sensibilidad de umbrales |

## 3. Features causales propuestas

El eje nuevo principal es abandonar agregados exclusivamente de un segundo e incorporar secuencia por print, granularidad subsegundo, normalización entre sesiones y referencias previas congeladas.

| # | Feature | Fórmula | Fuente, ventana y disponibilidad | Signo esperado | Racional y falsación |
|---:|---|---|---|---|---|
| 1 | `Max_SamePrice_Run_Share_3s` | Máximo volumen de una corrida consecutiva de prints al mismo precio / volumen total [−3,0] s | Tape por print, disponible en t0 | A > B | Repetición al mismo precio es compatible con refill/iceberg. Debe mantener signo por BUY y SELL y correlación absoluta <0.6 con presión de absorción y volumen previo en nivel. |
| 2 | `Tick_Gap_Share_1s` | Cambios print-a-print de al menos 2 ticks en dirección del burst / cambios de precio [−1,0] s | Tape por print, t0 | B > A | Detecta huecos en el camino, no sólo desplazamiento neto. Debe ser distinto de velocidad y eficiencia del burst. |
| 3 | `Aggressor_Frag_Asym_1s` | `(trades_burst/volume_burst) / (trades_contra/volume_contra)` [−1,0] s | Tape con agresor, t0 | A > B | Mide fragmentación por lado que el tamaño medio agregado no conserva. Exigir estabilidad BUY/SELL. |
| 4 | `SubSec_Vol_Concentration_1s` | Máximo volumen en ventana deslizante de 100 ms / volumen total [−1,0] s | Tape con timestamp de milisegundos, t0 | B > A | Un sweep limpio debería concentrarse más que una absorción sostenida. Falsar si sólo replica TradesPerSecond. |
| 5 | `Dist_PriorSession_Ref_Ticks` | `min(abs(price−PDH), abs(price−PDL), abs(price−settlement))/tick` | Niveles congelados de la sesión previa, t0 | A < B | Referencias previas pueden concentrar liquidez pasiva. Falsar si no mantiene signo por lado. |
| 6 | `Rel_Intensity_TOD20` | `ContractsPerSecond(t0) / median(ContractsPerSecond del mismo segundo del día en 20 sesiones previas)` | Histórico congelado hasta el día previo, t0 | A > B | Normaliza intensidad por régimen y hora. También debe reducir la inestabilidad de las medidas crudas; si no, la hipótesis de régimen pierde apoyo. |
| 7 | `Counter_LargePrint_Recency_10s` | Segundos desde el último print contra-dirección de tamaño al menos P90 de la sesión, censurado en 10 | Tape, [−10,0] s, t0 | A < B | Distingue presencia reciente de un defensor grande de counterflow agregado. |
| 8 | `Print_Size_Trend_5s` | Pendiente OLS de tamaños de prints agresivos en dirección del burst contra índice temporal | Tape, [−5,0] s, t0 | A < B | Dinámica del tamaño por print, no tamaño medio puntual. Falsar si el signo no replica en BUY y SELL. |

## 4. Decisión

**STOP** para seguir recombinando el diccionario actual. Con 119 variables causales elegibles, cero estables y ninguna familia superior a 0.563 por sí sola, continuar buscando combinaciones abre más caminos oportunistas.

**CONTINUE acotado** sólo para ejes de medición realmente nuevos, con fórmulas y signos prerregistrados. 2025–2026 queda como muestra de generación de hipótesis; la validación tendrá que ser forward y no vista.

## 5. Experimento mínimo sugerido

Antes de añadir variables, auditar sensibilidad de la etiqueta en los 115 eventos:

1. Perturbar los umbrales A/B/C en ±10% y ±20%.
2. Contar transiciones A↔B y hacia/desde C.
3. Si más de aproximadamente 20% cambia, robustecer la definición de etiqueta antes de seguir con features.
4. Si la etiqueta es robusta, prerregistrar las features nuevas y exigir signo consistente por era y lado, prueba unilateral por signo, BH q<0.10 y una muestra forward del orden de 80–100 A/B antes de leer resultados.

Esta revisión se realizó sobre el expediente cerrado generado por el diagnóstico; Claude Fable no tuvo acceso de lectura ni escritura al proyecto y no ajustó ningún modelo.
