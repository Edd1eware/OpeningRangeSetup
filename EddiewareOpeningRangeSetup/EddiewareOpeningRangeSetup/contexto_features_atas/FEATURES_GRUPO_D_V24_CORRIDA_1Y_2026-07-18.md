# Features Grupo D v24 y corrida de un año — 18/07/2026

## Evidencia de partida

El dataset v23 cerrado al 16/07/2026 contiene 189 trades Liquidity Burst:

- A ganador: 94.
- B perdedor con MFE > 30: 2.
- C perdedor con 2 < MFE <= 30: 19.
- D perdedor con MFE <= 2: 74.

Ninguna feature v23 cumplió simultáneamente significancia corregida, tamaño de
efecto y estabilidad discovery/validation/holdout. Las recombinaciones simples
de delta, volumen, velocidad y rango tampoco justifican un filtro. Por tanto,
v24 no modifica decisiones: sólo captura contexto que no podía reconstruirse
después del entry.

## Hipótesis nuevas pre-registradas

1. Un trade D puede nacer tras trayectoria ineficiente o contra delta persistente
   de las barras cerradas anteriores.
2. La volatilidad previa y la compresión respecto al OR pueden separar bursts
   genuinos de ruido.
3. Retests repetidos y falta de aceptación fuera del borde OR pueden identificar
   agotamiento del nivel.
4. La ubicación intrabar y respecto a VWAP/OR puede distinguir absorción real de
   una señal tardía.

## Columnas nuevas de `trade_inputs.csv`

- `Seconds_From_Open_AtEntry`.
- `Directional_OR_Extension_Ticks_AtEntry`.
- `Directional_VWAP_Distance_Ticks_AtEntry`.
- `Nearest_OR_Edge_Distance_Ticks_AtEntry`.
- `Body_OR_Ratio_AtEntry`.
- `Signed_Delta_Share_AtEntry`.
- `Signed_Previous_Delta_Share_AtEntry`.
- `Prior_Closed_ATR3_Ticks_AtEntry`.
- `Prior_Closed_ATR5_Ticks_AtEntry`.
- `PreEntry_Directional_Efficiency3_AtEntry`.
- `PreEntry_Directional_Delta_Share3_AtEntry`.
- `PreEntry_Range_Compression3_AtEntry`.
- `PreEntry_Volume_Climax_Ratio_AtEntry`.
- `Nearest_OR_Edge_Retest_Count_AtEntry`.
- `Nearest_OR_Edge_Acceptance_Ratio3_AtEntry`.
- `Directional_CLV_AtEntry`.

## Causalidad

- ATR, eficiencia, delta share, volumen, aceptación y retests usan únicamente
  barras cerradas anteriores al entry.
- CLV y ubicación usan sólo el estado observable en el instante del snapshot.
- No se usa MFE, MAE, exit, target final ni información futura como predictor.
- Las features no son leídas por el motor de señales, TradeManager, Execution
  Manager, trailing, CVD ni salida dinámica.
- El filtro de ejecución y toda la lógica Liquidity Burst permanecen intactos.

## Features aplazadas/rechazadas en esta etapa

- Overnight range y opening gap: requieren ampliar el rango de Replay antes de
  09:30; no se toca esa lógica de sincronización en esta corrida.
- DOM/refill/icebergs: no se usarán hasta demostrar que Historia X10 reproduce el
  book de forma completa y estable.
- POC/VWAP históricos exactos: se aplazan hasta disponer de snapshots causales
  por barra; no se reconstruyen con valores finales.

## Protocolo de corrida

- Versión: `score-exporter-2026-07-18-v24-born-bad-context`.
- Intervalo: `2025-07-17` a `2026-07-16`, inclusivo.
- Modo: Historia X10 únicamente.
- Replay X1: deshabilitado.
- Balance inicial: $150,000.
- Resultados/capturas anteriores: archivados por `--reset-state`.
- Telegram: reiniciado; cada TIME_OVER/PnL incluye ETA global.
- Grupo D: se ejecutará una vez al terminar el año completo.
- No se habilita ningún filtro con estas features durante la captura.

## Validación técnica previa

- Build Release: 0 errores.
- CSV: 89 columnas de encabezado y 89 expresiones de fila.
- Python del runner/análisis/coordinadores: sintaxis válida.
