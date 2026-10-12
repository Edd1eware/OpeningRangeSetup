# Feature de tendencia y trailing

Fecha: 12 de octubre de 2026. Resultado exploratorio bajo las reglas codificadas y costes supuestos. No se compraron datos adicionales.

Se implementó un feature causal de continuidad del movimiento y un motor de trailing. Se conservaron las 82 entradas y los stops iniciales del replay corregido; no se optimizaron entradas ni distancias después de observar esta comparación.

## Regla probada

El SL comienza detrás del imbalance más lejano, como en el setup base. Al alcanzar +1R, se activa el trailing a una distancia de 1R del mejor precio favorable. El stop nunca retrocede. En modo trailing no hay TP fijo; se compararon límites temporales de 30 minutos y 15:55 Nueva York.

Con trades se comprueba primero el stop vigente y después se actualiza para el siguiente evento. Las barras de un segundo, previstas sólo después de las 10:30, comprueban primero el stop anterior y actualizan al completar el segundo. Un nuevo stop no se aplica retroactivamente dentro de esa misma barra. Se modelan gaps, un tick adverso en las salidas y USD 4 de comisión round-trip por NQ, conservando el fill original de entrada.

En esta muestra las 82 operaciones salieron por trades antes de 30 minutos; la mayor duración fue unos 13 minutos y 11 segundos. Por ello, ambos horarios dieron exactamente el mismo resultado y ninguna salida dependió del tramo de barras posterior a las 10:30. No hubo censura ni timeouts.

## Resultado sobre las 82 operaciones

| Salida | Media neta, ticks | Media neta, R | Profit factor | Aciertos | DD cerrado, ticks |
|---|---:|---:|---:|---:|---:|
| RR 1:1 base | −15.90 | −0.3163 | 0.588 | 41.46% | 1,371.8 |
| Trailing desde +1R, distancia 1R | −9.58 | −0.3097 | 0.752 | 37.80% | 930.8 |

El trailing se activó en 34 operaciones. Capturó cinco ganancias netas superiores a 2R; la mayor fue 9.17R. El total neto pasó de −1,303.6 a −785.6 ticks. Para una unidad fija de NQ equivale a −USD 6,518 frente a −USD 3,928. Es una mejora descriptiva de la pérdida, todavía sin expectativa positiva.

La diferencia pareada media fue +6.32 ticks, con intervalo descriptivo de 98.33% por bloques de cinco sesiones de [−9.85, +34.02]. En R, la mejora media fue sólo +0.0066R, con intervalo [−0.2162, +0.2961]. Son intervalos aproximados ajustados por tres comparaciones por métrica; no corrigen las búsquedas previas ni prueban una mejora estable.

La mejora se concentra en junio: ese mes aporta +763 ticks de diferencia contra la base, aunque la mejora total es +518. Fuera de junio, el trailing empeora −245 ticks frente al 1:1. Sus cinco mejores operaciones aportan +1,640 ticks; las otras 77 suman −2,425.6. Ambas mitades cronológicas siguen negativas: −770.6 ticks en la primera y −15.0 en la segunda. La segunda mitad tampoco es validación independiente, porque 2026 ya fue inspeccionado.

## Feature y prueba condicional

`trend_efficiency_entry` divide el avance neto desde las 09:30, en dirección de la entrada, por el recorrido absoluto entre cierres de un segundo. Un valor mayor indica más avance direccional por cada unidad de zigzag. Sólo usa ejecuciones `ts_recv` estrictamente anteriores al cierre de la señal. Su rango es [−1, 1].

El umbral se obtuvo sin cargar columnas de P&L: percentil 75 de las 42 entradas de las primeras 75 sesiones, del 9 de marzo al 24 de junio. Se congeló en **0.13342146952536124** y se aplicó a las 40 entradas de las últimas 75 sesiones, del 25 de junio al 9 de octubre. Seleccionó ocho operaciones para trailing; las otras 32 conservaron el 1:1.

| Política, sólo segunda mitad | Operaciones | Media neta, ticks | Media neta, R | Total neto, ticks |
|---|---:|---:|---:|---:|
| RR 1:1 base | 40 | −14.70 | −0.2889 | −588.0 |
| Trailing sólo si supera el umbral | 40 | −16.70 | −0.4071 | −668.0 |

La selección por el feature no mejoró el resultado. Sólo dos de sus ocho runners llegaron a activarse; ambas salidas empeoraron frente a su TP 1:1. Las otras 38 operaciones de la política completa quedaron iguales a la base. La diferencia media fue −2 ticks, con intervalo descriptivo ajustado por bloques [−7.33, 0]. No se buscaron otros percentiles después de ver este resultado.

También se conservaron, sin combinar ni ajustar por retornos, pendiente VWAP normalizada por el riesgo conocido al cierre, delta agresor y posición del cierre de la vela. El riesgo de un fill posterior no se usa para decidir el feature. Hay dos descriptores VWAP/riesgo nulos por distancia no positiva al cierre, sin descartar sus entradas.

## Verificación, sensibilidad y archivos

Las 82 entradas pasan comprobaciones de causalidad: truncar el futuro o añadir precios y volúmenes extremos exactamente al cierre y después no cambia sus features. El cierre y la VWAP coinciden con el replay base. El resultado condicional contiene sólo las 40 entradas de la segunda mitad: ocho copias de runner y 32 copias de la salida base.

Se comprobaron cobertura e instrumentos de los 82 días; los gaps sin prints de las barras ya existen en la fuente nativa. El motor base tiene 19 pruebas y el trailing tiene 10 pruebas específicas. Se conservan trazas de cada avance del stop, hashes y auditorías independientes.

Las dos entradas de ejecución dudosa ya señaladas en el replay base, del 30 de junio y 8 de julio, permanecen en los resultados principales. La sensibilidad registrada antes de finalizar la corrida también las excluye: el trailing sigue negativo, −9.70 ticks y −0.1974R de media sobre 80 operaciones. La conclusión no depende de conservar esas dos filas. No se propone un filtro nuevo de riesgo mínimo.

- Feature: `C:/Users/k_99_/Documents/ChatGPT/research_edge/scripts/trend_features.py` y `outputs/trend_features/`.
- Trailing: `C:/Users/k_99_/Documents/ChatGPT/research_edge/scripts/trailing_replay.py` y `outputs/trailing_replay/`.
- Auditoría: `C:/Users/k_99_/Documents/ChatGPT/research_edge/scripts/audit_trailing.py` y `outputs/trailing_audit/paired_results.json`.
- Plan principal: `C:/Users/k_99_/Documents/ChatGPT/research_edge/TRAILING_RESEARCH_PLAN.md`.
- Sensibilidad de ejecución: `C:/Users/k_99_/Documents/ChatGPT/research_edge/TRAILING_EXECUTION_SENSITIVITY_PLAN.md`.
- Curvas: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/trailing_replay/comparacion_trailing_1NQ.png`.

![Comparación de curvas con un NQ fijo](C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/trailing_replay/comparacion_trailing_1NQ.png)

El trailing permite capturar algunos movimientos mayores, pero esta regla y este feature todavía no producen un candidato robusto que justifique comprar más datos. Las curvas representan resultados cerrados de un NQ fijo; no son una simulación Lucid ni sizing por riesgo con contratos enteros. La elección 50K/100K y una probabilidad de pasar la cuenta quedan pendientes de contar con una estrategia validable.
