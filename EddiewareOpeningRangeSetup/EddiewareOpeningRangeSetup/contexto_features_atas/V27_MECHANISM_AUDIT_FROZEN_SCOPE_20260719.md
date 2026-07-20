# V27 — Alcance congelado antes de la corrida de 79 horas

## Decisión

La estrategia permanece congelada. V27 sólo añade instrumentación, auditoría, análisis y Telegram. No cambia entradas, filtros, Liquidity Burst, TP, SL, CVD ni gestión.

## Familias causales incluidas

### Flujo no superpuesto

- Segmentos `[0,1]`, `[1,3]` y `[3,5]` segundos, sin observaciones compartidas.
- Buy volume, sell volume, volumen agresivo bruto, delta neto y delta direccional.
- Counterflow share, desplazamiento direccional, velocidad y ticks por contrato agresivo.
- Segundos esperados, observados y flag de validez por segmento.
- Retención de velocidad y delta entre segmentos. El denominador cero se exporta vacío, no con epsilon.

### Anatomía del cruce y memoria del nivel

- Nivel congelado y tipo de referencia.
- Distancia, velocidad y pausa durante la aproximación de 5 segundos.
- Contactos, cruces completos y volumen en una banda fija de un tick durante 60 segundos.
- Tiempo desde el último contacto previo, excluyendo el burst actual.

### Régimen y conflicto multihorizonte

- Volatilidad realizada causal de 10, 30 y 60 segundos.
- Ratio corto/largo normalizado por raíz del tiempo.
- Número de segmentos alineados y en conflicto entre delta y precio.
- Máscara descriptiva `ALIGNED|CONFLICT|NEUTRAL`.

### Dependencia y calidad del dato

- ID de episodio, ordinal del burst y segundos desde el burst anterior; un episodio nuevo comienza tras 30 segundos sin burst.
- Segundos observados, segundos Tape, segundos GapFill y cobertura en 60 segundos.
- Fuente, validez y motivo de exclusión.

### Entrada y contexto

- Timestamp del burst, disponibilidad nominal al cierre del segundo y timestamp efectivo de publicación del detector.
- Delay de publicación, latencia nominal→entrada, latencia publicación→entrada, validez causal estricta y diagnóstico de jitter de frontera de hasta 50 ms.
- Una fila con latencia negativa queda excluida del modelado causal estricto aunque se conserve completa para auditoría.
- La repetición del gate confirmó bursts y respuestas idénticos, pero variación subsegundo del callback de entrada por múltiples escritores X10. Los campos contextuales de entrada se interpretan con esa limitación y no se modifica la sincronización congelada.
- OR position, CVD direccional/alineación y contexto de subasta ya instrumentado.
- La entrada actual es simulada al precio de señal; no se afirma medir slippage ni fill real.

### Respuesta posterior

- Horizontes 1, 3 y 5 segundos.
- Tiempo en lado aceptado, banda del nivel y lado rechazado.
- Buy/sell bruto, contra-flujo, esfuerzo/resultado, trayectoria y migración causal de POC.
- Todo permanece marcado `POST_BURST_ONLY` y no puede predecir la misma entrada.

## Elementos rechazados antes de la corrida

- Order book, refill, withdrawal, depth recovery e icebergs: no existe todavía evidencia de reproducción determinista Level 2 en Historia X10.
- Slippage/fill real: el exporter actual utiliza el precio de señal.
- ATR diario, overnight, opening gap y VWAP slope cuando el historial causal requerido no está cargado: se exportan como no disponibles con motivo, nunca se rellenan.
- Calendario macro: no hay una fuente versionada y congelada integrada al Replay.
- Scores agregados nuevos: primero se capturan componentes primarios para evitar ocultar mecanismos y duplicar variables correlacionadas.

## Entregables automáticos del análisis

- `feature_dictionary.md`
- `feature_coverage_matrix.csv`
- `family_summary.csv`
- `incremental_information_report.md`
- `causality_audit.csv`
- `rejected_features.csv` y `rejected_features.md`
- Reporte final, dataset, rankings, modelos y gráficas, incluida cobertura por familia y por feature v27.

## Gates antes de iniciar el histórico

1. Compilación sin errores.
2. Igualdad de hash entre `bin/Release`, Indicators y Strategies.
3. Igual número de columnas en headers y filas de `trade_inputs.csv`, `burst_events.csv` y `burst_response_events.csv`.
4. Prueba de una fecha con trade para cobertura y valores.
5. Repetición de la misma fecha para comprobar timestamps, señal, entrada, salida y features deterministas.
6. Prueba de una fecha TIME_OVER.
7. Telegram: primer mensaje explicativo propuesto por Codex, trade detallado con ETA y reporte/gráficas finales.
8. Sólo después de superar los gates se reinicia estado/equity y se lanza el histórico completo.
