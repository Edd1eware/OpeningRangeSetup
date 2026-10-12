# Control del aporte direccional del footprint

Corrida independiente terminada el 2026-10-12. Estado: exploratorio, porque estas sesiones ya fueron inspeccionadas en investigaciones previas.

## Pregunta acotada

¿En la primera vela M1 que cierra fuera del OR, tener imbalance en la dirección mejora el resultado de seguir la ruptura?

Se usa el mismo bracket diagnóstico de 60 ticks de SL y 60 ticks de TP, horizonte de 30 minutos, para todos los eventos. No hay VWAP, espera de velas posteriores ni stop estructural. Por ello este control no equivale al setup completo del usuario.

Se mantienen ratio 3, mínimo 70 y agrupación de 5 ticks. Offset 1 tick y tratamiento de cero con vecino existente siguen siendo supuestos visibles. Costes constantes comparados: 0, 1.8 y 4 ticks round-trip. No se eligió el bracket por sus resultados.

## Calidad y causalidad

- 150 sesiones entre 2026-03-09 y 2026-10-09.
- 145 primeras rupturas y 5 sesiones sin cierre de ruptura elegible.
- Las 145 trayectorias se resolvieron con la secuencia de ejecuciones, no con una suposición favorable dentro de una barra.
- OHLCV de señal y trayectoria coincide exactamente con trades agrupados por `ts_recv`.
- Volumen de agresor desconocido en las velas de señal: 0.
- Fixture de la imagen: exactamente venta 107/29 y compra 294/95.
- Pruebas sintéticas confirman el error de extremos del código previo.
- En estas primeras rupturas, corregir los extremos añade 0 filas, retira 0 y cambia 0 sesiones. No atribuirle mejoras inexistentes.

Databento documenta que sus OHLCV se agregan con `ts_recv` de los trades. Un segundo sin ejecución no produce necesariamente una barra; no excluir por exigir actividad cada segundo.

Fuente: https://www.databento.tech/docs/schemas-and-data-formats/ohlcv?historical=python&live=python&reference=python

## Resultado a coste supuesto de 1.8 ticks

| Grupo | n | Acierto bruto | EV neta ticks | IC95% EV por bootstrap de sesiones |
|---|---:|---:|---:|---|
| Todas las primeras rupturas | 145 | 48.97% | −3.31 | [−13.19, +6.63] |
| Con imbalance a favor | 26 | 38.46% | −16.03 | [−38.36, +7.36] |

La diferencia entre el grupo con imbalance y tomar todas es −12.72 ticks, IC95% [−33.96, +8.52], con remuestreo pareado de sesiones. La diferencia de ventaja direccional D entre pasar y fallar el filtro es −15.44 ticks, IC95% [−40.64, +10.29].

No hay ventaja positiva demostrada de este filtro en la primera ruptura. La incertidumbre todavía admite otros valores; esto no demuestra que la política de esperar otra vela con stop estructural no pueda funcionar.

## Reproducibilidad

Código: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/footprint_control/diagnose_footprint.py`.

Resultados: `results.json`, `daily_events.csv`, `monthly_summary.csv`, `session_quality.csv` e `imbalance_edge_changes.csv` en esa misma carpeta. El README incluye el comando local de reproducción.

El modelo de prints no observa posición en cola, bid/ask ejecutable ni latencia manual. Un toque del target se modela como fill al target y no acredita un fill real.
