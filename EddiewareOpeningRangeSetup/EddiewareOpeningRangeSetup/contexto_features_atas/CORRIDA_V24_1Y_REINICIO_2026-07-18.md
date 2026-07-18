# Corrida v24 de un año — reinicio y recuperación

Fecha de operación: 2026-07-18.

## Alcance congelado

- Período: 2025-07-17 a 2026-07-16, inclusive.
- Sesiones operables: 166.
- Modo: Historia X10 únicamente.
- Replay X1: deshabilitado.
- Balance inicial simulado: USD 150,000.
- Exporter: `score-exporter-2026-07-18-v24-born-bad-context`.
- No se modificaron señales, entradas, salidas, Liquidity Burst, TP/SL, CVD,
  trailing ni la sincronización de Replay.

## Validación de la nueva captura

`trade_inputs.csv` fue creado con 89 columnas y contiene las 16 features
causales nuevas definidas en `FEATURES_GRUPO_D_V24_CORRIDA_1Y_2026-07-18.md`.
Las primeras filas tienen valores poblados y la versión v24 correcta. Las
features se capturan en el snapshot de entrada y no son consumidas por la
lógica de trading.

## Detención observada y recuperación

El runner inicial completó y preservó 2025-07-17, 2025-07-18 y 2025-07-21.
En 2025-07-22 detectó primero un CSV terminal inestable y terminó con
`NON_TERMINAL_CSV`; por diseño fail-fast no avanzó a otra fecha.

La corrida se reanudó sin recompilar, sin copiar DLL, sin reiniciar ATAS, sin
reiniciar balance y sin borrar Telegram. El runner confirmó que las tres fechas
anteriores ya estaban guardadas con v24 y las saltó. Volvió a ejecutar
2025-07-22 y guardó el resultado terminal; después guardó 2025-07-23 y continuó
con 2025-07-24.

No se atribuye una causa de código al estado transitorio del CSV porque los
logs actuales no demuestran todavía qué escritor o transición produjo el
artefacto no terminal. La recuperación demuestra únicamente que el mecanismo
de preservación/reanudación funcionó.

## Reconstrucción comprobada de 2025-07-22

- Entrada: 09:31:38.252 NY a 23298.75.
- Salida: 09:31:41.001 NY a 23303.75.
- TP inicial: 20 ticks.
- SL inicial: 20 ticks.
- RR inicial: 1.00.
- Resultado: SL, -20 ticks.
- Motivo: `EXIT_SL_INITIAL`.
- Versión: `score-exporter-2026-07-18-v24-born-bad-context`.

Telegram conservó las marcas de las fechas ya enviadas y publicó los nuevos
terminales con ETA global. `windows_run_awake.py` quedó activo sin movimiento
de mouse ni envío de teclas.
