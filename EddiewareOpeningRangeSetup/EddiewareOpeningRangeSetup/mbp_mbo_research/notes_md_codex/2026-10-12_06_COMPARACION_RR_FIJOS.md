# Comparación de RR fijos sobre las mismas entradas

Fecha: 12 de octubre de 2026. Estudio exploratorio sobre datos ya inspeccionados.

Se conservaron las 82 señales, fills de entrada y stops estructurales del replay corregido. Sólo cambió el target, con RR nominal 0.75, 1, 1.5 y 2. El target se redondea hacia arriba a ticks enteros. Se mantuvieron el horizonte de 30 minutos, un tick de slippage adverso en entrada y stop, y USD 4 de comisión round-trip por NQ.

| RR | Operaciones | Aciertos | Media neta, ticks | Media neta, R | Profit factor | DD cerrado, ticks |
|---|---:|---:|---:|---:|---:|---:|
| 0.75 | 82 | 48.78% | −13.31 | −0.280 | 0.606 | 1,142.8 |
| 1.00 | 82 | 41.46% | −15.90 | −0.316 | 0.588 | 1,371.8 |
| 1.50 | 82 | 31.71% | −18.28 | −0.377 | 0.588 | 1,498.6 |
| 2.00 | 82 | 23.17% | −20.46 | −0.481 | 0.575 | 1,677.6 |

Las cuatro variantes pierden tanto en las primeras 75 sesiones como en las últimas 75. Reducir o ampliar el target no produjo un candidato prometedor en esta comparación. No se elige RR 0.75 por ser el menos negativo.

La incertidumbre se estimó remuestreando bloques de cinco sesiones, incluidas las fechas sin operación. Los intervalos descriptivos ajustados por cuatro comparaciones siguen siendo amplios; todos los de ticks incluyen cero. En R, los intervalos de RR 1.5 y 2 permanecen completamente negativos. Este ajuste no cubre las búsquedas históricas previas y no convierte 2026 en validación independiente.

## Verificación y archivos

RR 1 reproduce exactamente los 82 resultados de referencia en 15 campos de ejecución y resultado, con tolerancia numérica de 1e−9. No cambió ninguna señal, entrada ni stop inicial. Se guardaron 328 filas de operaciones y 600 filas de resultados diarios, junto con meses, mitades cronológicas y comprobaciones.

- Código: `C:/Users/k_99_/Documents/ChatGPT/research_edge/scripts/compare_fixed_exits.py`.
- Plan registrado antes de ejecutar: `C:/Users/k_99_/Documents/ChatGPT/research_edge/EXIT_COMPARISON_PLAN.md`.
- Resultados y límites: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/exit_comparison/README.md` y `results.json`.

El DD corresponde a una unidad fija de NQ; no es el drawdown de una cuenta Lucid ni un sizing por riesgo con contratos enteros. Se mantienen las advertencias de ejecución de las dos entradas cuyo print coincide con el stop inicial.

El siguiente estudio, solicitado por el usuario, añade un feature causal de tendencia y una regla de trailing para dejar correr operaciones. Se definieron sus parámetros en `TRAILING_RESEARCH_PLAN.md` antes de ejecutar. No se ha comprado más información de mercado.
