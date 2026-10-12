# Búsqueda del edge de entrada con RR 1:1

Fecha: 12 de octubre de 2026. Se apartaron el feature condicional de tendencia y nuevas mejoras de trailing, según la prioridad del usuario. Este estudio mantiene RR 1:1, el stop estructural, el reloj `ts_recv` y los costes supuestos del replay de referencia.

## Qué se comparó

Sobre las mismas 150 sesiones se evaluaron cuatro políticas independientes: referencia; vela que abre dentro del OR y cierra fuera; delta agresor alineado; y una fila completa de imbalance alineado fuera del OR. Las tres reglas se probaron por separado, sin combinarlas ni ajustar umbrales por resultados.

Cada política espera su primera vela válida entre los cierres 09:32 y 09:40 NY. Rechazar una vela no elimina el día: se siguen evaluando las siguientes. El SL siempre queda detrás del imbalance alineado más lejano de la vela, incluido uno que esté dentro del OR. No se usa el resultado futuro para seleccionar la señal.

Abrir dentro del OR es una variante de investigación mientras se confirma si el usuario lo exige en su operativa. La referencia conserva por ahora la interpretación previa: cierre fuera del rango aunque el open ya estuviera fuera. No se presenta la nueva variante como reproducción confirmada de una regla que todavía es ambigua.

## Resultados completos

| Política | Entradas | Aciertos | Media neta, ticks | Media neta, R | Total neto, ticks | PF neto en ticks |
|---|---:|---:|---:|---:|---:|---:|
| Referencia | 82 | 41.46% | −15.90 | −0.3163 | −1,303.6 | 0.588 |
| Open dentro del OR | 39 | 53.85% | +7.58 | −0.0221 | +295.8 | 1.308 |
| Delta agresor alineado | 81 | 41.98% | −16.02 | −0.2464 | −1,297.8 | 0.589 |
| Imbalance completo fuera del OR | 76 | 42.11% | −12.77 | −0.3133 | −970.8 | 0.614 |

La variante de cuerpo desde dentro es la única con resultado positivo para un NQ fijo: **+USD 1,479**, con DD de resultados cerrados de **USD 1,261**. Es una pista exploratoria sobre la entrada, no un edge demostrado. La media normalizada por riesgo sigue ligeramente negativa: −0.0221R; total −0.8615R. Al variar la distancia del SL, beneficio con un contrato fijo y beneficio por unidad de riesgo pueden tener signos distintos. Esa diferencia no demuestra ausencia universal de ventaja, pero impide afirmar rentabilidad robusta con ambos modos de ponderación.

Los intervalos absolutos de esta variante, por bloques de cinco sesiones y ajustados de forma descriptiva por cuatro políticas, son amplios:

- Media neta en ticks, IC 98.75%: **[−23.29, +35.04]**.
- Media neta en R, IC 98.75%: **[−0.4819, +0.4277]**.

Ambos incluyen cero. El periodo 2026 ya se inspeccionó y el ajuste no cubre todas las búsquedas anteriores; no es validación independiente.

## Estabilidad de la pista de cuerpo

| Mitad de 75 sesiones | Entradas | Total neto, ticks | Total neto, R |
|---|---:|---:|---:|
| Primera | 21 | +188.2 | −2.0117 |
| Segunda | 18 | +107.6 | +1.1501 |

Hay cinco meses positivos en ticks y tres positivos en ambas métricas. Quitar el mejor trade todavía deja +168.6 ticks y quitar el mejor mes deja +55.8 ticks; esas mismas comprobaciones siguen negativas en R. Los cinco mejores trades suman +581 ticks y los otros 34 suman −285.2. La concentración se informa como diagnóstico, sin eliminar los mejores trades de una estrategia operable.

La variante mejora la referencia en P&L por las mismas sesiones calendario: +10.66 ticks y +0.1671R por sesión de diferencia. Los intervalos pareados de 98.33% por bloques son positivos: [1.29, 23.14] ticks y [0.0397, 0.3180] R por sesión. Esto indica una mejora respecto a una referencia que pierde; no sustituye la prueba de rentabilidad absoluta, cuyos intervalos siguen incluyendo cero.

La regla no cumple los criterios conservadores de avance registrados antes de leer resultados: falta positividad absoluta y estabilidad en R, las cotas inferiores son negativas, la segunda mitad tiene 18 entradas y sólo tres meses son positivos en ambas métricas. Ninguna de las cuatro políticas cumple los criterios para justificar gasto en nuevos datos.

## Sensibilidades de ejecución

La variante de cuerpo no tiene entradas propias marcadas como `entry_print_at_or_beyond_stop`. Al excluir las dos fechas problemáticas de la referencia, su resultado cambia a +336.6 ticks / +0.2718R en 38 trades. **Esa exclusión no corrige una ejecución defectuosa de esta variante:** el 8 de julio la variante entra más tarde, al cierre de las 09:40, con riesgo de 36 ticks y pierde −40.8 ticks / −1.1333R. Es una operación legítima diferente de la entrada señalada en la referencia. No se quita del resultado principal ni se presenta la sensibilidad positiva como candidato nuevo.

Los costes continúan siendo supuestos: fill de entrada con un tick adverso, salida de SL con un tick adverso más overshoot observado y USD 4 round-trip por NQ. No se cambiaron para conseguir positividad. Las curvas de R no representan contratos fraccionarios realizables ni una cuenta Lucid.

## Verificaciones y archivos

La referencia reproduce sus 82 operaciones exactamente en 36 campos. Se conservaron 1,350 candidatos, 5,400 decisiones y 600 filas diarias, sin censura. Diez entradas de variantes esperaron correctamente una señal posterior a la primera válida de referencia. Las 39 pruebas del conjunto pasan.

La auditoría independiente comprobó las primeras selecciones de las 600 combinaciones política/sesión y reconstruyó siete fechas desde trades originales sin diferencias en OR, velas, VWAP M1, delta, diagonales o primer print de entrada. Código, plan y resultados tienen hashes concordantes.

- Plan: `C:/Users/k_99_/Documents/ChatGPT/research_edge/CORE_ENTRY_RESEARCH_PLAN.md`.
- Criterios de avance: `C:/Users/k_99_/Documents/ChatGPT/research_edge/CORE_EDGE_ADVANCE_CRITERIA.md`.
- Motor: `C:/Users/k_99_/Documents/ChatGPT/research_edge/scripts/core_entry_replay.py`.
- Operaciones y candidatos: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/core_entry_replay/`.
- Estadística: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/core_entry_audit/statistics.json`.
- Auditoría de lógica: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/core_entry_audit/logic_audit.json`.
- Antecedentes: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/core_entry_audit/PRIOR_SEARCH_REVIEW.md`.

![Entradas con RR 1:1 y costes supuestos](C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/core_entry_replay/comparacion_entradas_RR1.png)

La búsqueda queda centrada en la entrada. Se conserva la variante de cuerpo como pista, sin aplicarle trailing, combinarla con otros filtros, descartar fechas desfavorables ni comprar más datos. Todavía no se ha validado un edge para escoger Lucid 50K/100K.
