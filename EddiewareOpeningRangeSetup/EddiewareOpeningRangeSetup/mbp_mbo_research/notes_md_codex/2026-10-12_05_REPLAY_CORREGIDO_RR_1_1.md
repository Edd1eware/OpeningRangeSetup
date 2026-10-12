# Replay corregido: OR + imbalance + VWAP, RR 1:1

Corrida terminada el 12 de octubre de 2026. Periodo: 9 de marzo a 9 de octubre de 2026, 150 sesiones. Resultado exploratorio; el periodo ya fue inspeccionado en investigaciones anteriores.

## Resultado

| Métrica | Valor |
|---|---:|
| Operaciones | 82 |
| TP / SL / timeout | 34 / 48 / 0 |
| Acierto | 41.46% |
| Expectativa neta | −15.90 ticks por operación |
| Expectativa normalizada | −0.3163 R por operación |
| PF neto | 0.5882 |
| Resultado de un NQ fijo | −USD6,518 |
| Drawdown de resultados cerrados, un NQ fijo | USD6,859 |
| Riesgo mediano | 47 ticks |
| Riesgo mínimo / máximo | 1 / 254 ticks |

IC95% exploratorio de la media neta en ticks: [−32.59, +1.20] remuestreando sesiones y [−35.56, +1.88] con bloques de cinco sesiones. En R, el intervalo por bloques es [−0.5889, −0.0487]. No se presentan como validación independiente.

La versión modelada no muestra un edge positivo. Esto no equivale a afirmar que el operador no pueda ganar: la selección y ejecución real deben coincidir con la regla programada para que la comparación sea válida.

## Regla y ejecución

Se usan las reglas confirmadas: OR 09:30–09:31 de Nueva York, decisiones después del cierre M1 desde 09:32 hasta 09:40, cierre fuera del OR, imbalance diagonal de la misma vela y dirección, VWAP a favor, esperar mientras no cumpla, SL cinco ticks detrás del imbalance más lejano, RR1:1, una operación máxima al día.

La VWAP usa cierres M1 ponderados por volumen M1 desde 09:30, conforme al código oficial de ATAS para Source Close y volumen Total. El footprint exige un vecino diagonal real. No se añadieron el pool de imbalances antiguos, filtro de revisitas, banda de SL 30–120 ticks ni requisito de ausencia de cambios de color.

Reloj principal: `ts_recv`, consistente con la agregación OHLCV de Databento. Entrada en el primer print disponible después del cierre con un tick adverso; stop al primer print cruzador más un tick adverso; target al nivel exacto. Comisión supuesta de USD4 round-trip por NQ. Timeout supuesto de 30 minutos.

Quedan pendientes de calibrar el offset de agrupación de un tick, costes reales, latencia/colas de órdenes y la semántica temporal del feed ATAS instalado. No se afirma reproducción exacta de los fills reales.

## Verificación

- 19 pruebas automatizadas pasan: vecinos diagonales, límites de tiempo, ausencia de uso del futuro, VWAP, geometría de cinco ticks, imbalances separados, stop más lejano en ambos sentidos, gaps, censura y cobertura.
- 13 comprobaciones de resultados pasan.
- Metadata cubre la ventana requerida en 150 de 150 sesiones.
- Cero sesiones con mezcla de instrumentos, precios fuera de tick o registros inválidos.
- Cero operaciones censuradas.
- Seis prints de agresor desconocido: tres en OR y tres después de 09:40; ninguno dentro de las velas candidatas.
- El reloj de evento y el de recepción producen las mismas 82 señales y stops. Sólo cambia un fill, el 16 de abril: cuatro ticks de diferencia.

Dos entradas tienen riesgo de un tick y print de entrada exactamente sobre el stop: 30 de junio y 8 de julio. Están marcadas en los archivos; no se descartaron por conveniencia. El modelo de prints y riesgo divisible continuamente no acredita que ese sizing o esa activación del stop sea ejecutable en una cuenta real.

## Sensibilidad del coste de ejecución

Se conservan las señales del escenario base; no se vuelven a seleccionar entradas.

| Slippage adverso por entrada y SL | Operaciones válidas | EV neta ticks |
|---|---:|---:|
| 0 ticks | 80; dos stops inválidos con ese fill | −15.14 |
| 1 tick | 82 | −15.90 |
| 2 ticks | 82 | −17.03 |

La comisión de USD4 se mantiene en los tres escenarios. La pérdida no desaparece al quitar el slippage modelado.

## Diagnóstico del riesgo

Los cinco bins fijados antes del análisis descriptivo —(0,10], (10,30], (30,60], (60,120] y más de 120 ticks— tienen expectativa negativa en ticks y R. Los ocho trades de más de 120 ticks explican aproximadamente el 65.3% de la pérdida en ticks; los otros 74 también pierden en conjunto. Los stops de hasta 10 ticks son particularmente sensibles a costes y overshoot al expresarlos en R.

Sólo operar shorts no es un candidato estable: su pequeño total positivo en R depende de junio; los otros siete meses juntos dan R negativo, y los shorts totales siguen siendo negativos en ticks por contrato.

## Archivos y curva

Motor: `C:/Users/k_99_/Documents/ChatGPT/research_edge/scripts/structural_replay.py`.

Resultados, operaciones, calidad y manifiesto SHA256: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/structural_replay`.

Diagnóstico de distancias: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/risk_diagnostic`.

![Curva exploratoria, un NQ fijo](C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/structural_replay/curva_exploratoria_1NQ.png)

La curva es equity neta de operaciones cerradas con un NQ fijo. No representa la cuenta del usuario, una recomendación de tamaño ni una simulación de los límites de Lucid.

## Siguiente comparación acotada

El plan `C:/Users/k_99_/Documents/ChatGPT/research_edge/EXIT_COMPARISON_PLAN.md` fija RR0.75, 1.5 y 2 sobre las mismas entradas y stops, con targets en ticks ejecutables. No se cambian filtros para buscar una curva favorable.

El usuario autorizó considerar más datos de Databento sólo si hay resultados prometedores que justifiquen el gasto. Hasta ahora no se han comprado ni descargado datos de mercado nuevos.
