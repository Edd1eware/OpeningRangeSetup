# Resultados de la corrida v24 de un año

## Identificación

- Período solicitado: 2025-07-17 a 2026-07-16.
- Sesiones DST operables procesadas: 166 de 166.
- Modo: Historia X10 únicamente.
- Replay X1: deshabilitado.
- Exporter: `score-exporter-2026-07-18-v24-born-bad-context`.
- Balance inicial simulado: USD 150,000.
- Sizing del reporte: 6 contratos NQ, USD 5 por tick y contrato.
- Comisiones y fees: no incluidos.
- Baseline Git: commit `00d688a`, rama
  `codex/baseline-v24-1y-20260718`.

Este informe describe la simulación del exporter. No representa fills reales ni
autoriza cambios de trading.

## Resumen global

| Métrica | Resultado |
|---|---:|
| Sesiones con TIME_OVER/sin trade | 63 |
| Trades | 103 |
| Ganadores | 49 |
| Perdedores | 54 |
| Break-even | 0 |
| WR | 47.57% |
| PF | 0.8490 |
| Expectancy | -3.58 ticks/trade |
| Average Win | +42.35 ticks |
| Average Loss | -45.26 ticks |
| Net PnL | -369 ticks |
| Net PnL simulado | -USD 11,070 |
| Balance final simulado | USD 138,930 |
| Max drawdown simulado | USD 23,370 |
| Fecha del máximo drawdown | 2025-10-28 |
| MAE medio | 26.31 ticks |
| MAE mediano | 20 ticks |
| MFE medio | 23.30 ticks |
| MFE mediano | 20 ticks |

## Trades por mes

| Mes | Trades | Wins | Losses | WR | PF | Net ticks | PnL USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-07 | 5 | 2 | 3 | 40.00% | 0.8824 | -16 | -480 |
| 2025-08 | 11 | 4 | 7 | 36.36% | 0.5145 | -151 | -4,530 |
| 2025-09 | 16 | 6 | 10 | 37.50% | 0.5769 | -198 | -5,940 |
| 2025-10 | 17 | 6 | 11 | 35.29% | 0.3723 | -349 | -10,470 |
| 2026-03 | 8 | 7 | 1 | 87.50% | 13.3333 | +259 | +7,770 |
| 2026-04 | 10 | 4 | 6 | 40.00% | 0.5809 | -101 | -3,030 |
| 2026-05 | 17 | 10 | 7 | 58.82% | 1.3267 | +98 | +2,940 |
| 2026-06 | 15 | 7 | 8 | 46.67% | 0.9972 | -1 | -30 |
| 2026-07 | 4 | 3 | 1 | 75.00% | 2.5000 | +90 | +2,700 |

La discontinuidad noviembre-febrero corresponde al universo de sesiones DST
definido por el runner; no se inventaron ni interpolaron fechas.

## Segmentos observacionales

| Segmento | Trades | WR | PF | Net ticks |
|---|---:|---:|---:|---:|
| OR >= 140, filtro congelado de ejecución | 67 | 49.25% | 0.9165 | -131 |
| OR < 140, sólo simulación del exporter | 36 | 44.44% | 0.7280 | -238 |
| BREAKOUT, todos | 62 | 53.23% | 1.2765 | +261 |
| BREAKOUT con OR >= 140 | 43 | 55.81% | 1.3423 | +229 |
| LIQUIDITY BURST ABSORTION, todos | 41 | 39.02% | 0.5800 | -630 |
| LIQUIDITY BURST ABSORTION con OR >= 140 | 24 | 37.50% | 0.6000 | -360 |

Estos cortes son descriptivos y posteriores a la corrida. No son filtros nuevos
ni evidencia suficiente para modificar la estrategia.

## Bracket y motivos de salida

Todos los 103 trades nacieron con RR inicial 1.00. Distribución TP/SL inicial:

- 60/60: 65 trades.
- 20/20: 24 trades.
- 21/21: 4 trades.
- 26/26: 2 trades.
- 31/31: 2 trades.
- 36/36: 2 trades.
- 41/41: 1 trade.
- 51/51: 2 trades.
- 56/56: 1 trade.

Motivos de salida:

- `EXIT_SL_INITIAL`: 54.
- `EXIT_TP_INITIAL`: 38.
- `EXIT_TP_DYNAMIC_CVD_RISK_BRACKET_50_PERCENT`: 11.

Por tanto, el reporte confirma que las reducciones CVD son modificaciones
dinámicas posteriores a la entrada; no representan un TP inicial menor al SL.

## Familias de Liquidity Burst

El estudio A-D utilizó únicamente los 41 trades Liquidity Burst con unión causal
completa entre entrada, burst y resultado:

- A — Winner: 16.
- B — Loser con MFE > 30: 1.
- C — Loser con 2 < MFE <= 30: 3.
- D — Born Bad con MFE <= 2: 21.

`Directional_CLV_AtEntry` apareció primero en los rankings exploratorios de este
año. Sin embargo, v24 no guardó el High y Low exactos usados por ATAS en el
snapshot. Por ello su causalidad runtime todavía no está demostrada y no puede
aceptarse como feature validada.

## Interpretación científica

Esta corrida es exclusivamente una fase de generación de hipótesis. Un solo año
no permite afirmar estabilidad, generalización ni propiedad estructural del
mercado. No se autoriza:

- modificar entradas o salidas;
- crear filtros;
- eliminar trades;
- optimizar Liquidity Burst;
- aceptar CLV, Delta, Velocity o Imbalance como predictores estables.

La siguiente corrida deberá usar el histórico completo desde 2022-04-04 hasta
2026-07-16, conservar causalidad estricta y validar por año, walk-forward, OOS y
regímenes antes de proponer cualquier cambio a la estrategia.
