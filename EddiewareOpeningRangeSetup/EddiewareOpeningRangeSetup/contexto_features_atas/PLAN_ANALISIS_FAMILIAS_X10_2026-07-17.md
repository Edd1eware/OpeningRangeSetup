# Plan causal — Familias de absorción vs breakout

Fecha: 2026-07-17
Rama: `codex/absorption-family-research-x10`

## Alcance congelado

- No se modificó código C# ni lógica de entrada, salida, TP, SL, CVD o Liquidity Burst.
- No se modificó la sincronización ni el mecanismo de Historia X10.
- Replay X1 permanece deshabilitado.
- El cambio Python sólo archiva acumuladores observacionales al reiniciar y ejecuta la investigación después de que todas las fechas X10 hayan terminado sin errores.

## Hallazgo de integridad de datos

Los outcomes de cada trade deben leerse de `score_trade_result_YYYY-MM-DD_NY.csv`, que es el artefacto terminal canónico preservado por fecha. `trade_results.csv` puede recibir después una recalculación sincronizada con MFE/MAE parciales; por eso no se usa como fuente de las etiquetas A/B/C. Esto evita clasificar un trade con información incompleta sin tocar el exporter ni el edge.

Las features proceden únicamente de `trade_inputs.csv` y `burst_events.csv`, con auditoría explícita de que sus timestamps son anteriores o iguales al `prediction_timestamp`. MFE, MAE, resultado y salida se usan únicamente como labels retrospectivos.

## Prueba de humo v23

La reconstrucción de las 14 entradas Liquidity Burst ya disponibles produjo:

- Familia A, absorción verdadera estricta: 6.
- Familia B, breakout limpio estricto: 5.
- Familia C, trayectoria mixta: 3.
- Violaciones causales: 0.

Esta muestra pequeña valida el pipeline, pero no autoriza filtros ni conclusiones sobre features. La inferencia final se hará con la corrida completa.

## Corrida aprobada

- Periodo: 2022-04-04 a 2026-07-16.
- Sesiones operables: 735.
- Modo: Historia X10 únicamente.
- Balance inicial: USD 150,000.
- Telegram se reinicia al comenzar.
- Encabezado del informe final: `ANALISIS  FAMILIAS A, B, C, ETC.`

El pipeline generará catálogo, dataset causal, estadísticas, tamaños de efecto, corrección por múltiples pruebas, modelos fuera de muestra, importancia, ablación, clustering, PCA/t-SNE, auditoría de leakage, ledger, visualizaciones y reporte final. Copiará el reporte final a esta carpeta sin sobrescribir esta nota.
