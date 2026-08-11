# Auditoría Adversarial — Opening Range Setup (edge_optimization_fast_20260711_192450)

Fecha: 2026-07-11. Archivos originales NO modificados. Todos los cálculos recomputados
de forma independiente desde los 730 CSVs crudos de `X10_R1` (scripts `audit_calc.py`,
`audit_exit_policy.py`; resultados en `audit_results.json`, `audit_exit_policy.json`).

Snapshot Fase 0: `audit_snapshot/20260711_215559` (hashes, git HEAD aff987f, pip freeze).

## VEREDICTO GLOBAL

**El PF 3.01 / WR 73.4% / +15.54 ticks es un artefacto de look-ahead. No existe en vivo.**

`Cvd_Pullback_Label` se escribe en el CSV con su valor AL CIERRE del trade
(`ATASScoreTradeResultExporter.cs`: se inicializa "Excelente" en la entrada — línea ~392,
se sobreescribe en cada update durante el trade — línea ~938, y la fila final exporta el
último valor — línea ~2414). Filtrar por `cvd=Excelente` equivale a seleccionar ex-post los
trades donde el CVD nunca se degradó, es decir, los ganadores.

Prueba empírica (recomputada, tabla cruzada label × resultado real):

| Cvd_Pullback_Label (al cierre) | n | TP | SL | WR real | Exp (ticks) |
|---|---|---|---|---|---|
| Excelente | 342 | 257 | 84 | 75.1% | +15.54 |
| Normal | 22 | 8 | 14 | 36.4% | −0.64 |
| Advertencia | 21 | 7 | 14 | 33.3% | −7.10 |
| Riesgo de reversion | 179 | 26 | 153 | 14.5% | −19.68 |

La etiqueta ES el resultado. Un clasificador de outcome disfrazado de filtro de entrada.

Prueba causal definitiva: usar la señal CVD de forma legal (alarma dinámica DURANTE el
trade, columnas at-alarm del exporter) para salir, sobre los 564 trades:

| Política de salida (causal) | WR | PF | Exp (ticks) |
|---|---|---|---|
| Baseline (salidas actuales) | 52.8% | 1.20 | +2.89 |
| Salir en alarma | 26.6% | 0.96 | −0.40 |
| Trail 10 tras alarma | 28.7% | 0.96 | −0.36 |
| Trail 15 tras alarma | 32.8% | 0.98 | −0.19 |
| Trail 20 tras alarma | 38.5% | 1.01 | +0.16 |
| BE en alarma | 26.6% | 0.96 | −0.40 |

La señal CVD usada causalmente NO agrega valor. Confirma que el 73% WR era outcome leakage.

## LOS 12 RIESGOS — RESULTADO

| # | Riesgo | Veredicto | Evidencia |
|---|---|---|---|
| 1 | Look-ahead | **CONFIRMADO — fatal** | Label CVD al cierre usado como filtro de entrada (código + tabla cruzada arriba) |
| 2 | Leakage train/test | **CONFIRMADO** | `edge_optimization_fast.py`: filtro robusto exige `test_exp > 0` y `test_trades >= 20` (el test participa en la selección); `robust_score` se calcula sobre la muestra completa. El test_pf 4.25 NO es OOS |
| 3 | Overfitting | **CONFIRMADO (vía minería)** | 4,298 setups evaluados en `all_candidates.csv`; selección por máximo |
| 4 | Sesgo de selección | **CONFIRMADO** | Igual que #3; además thresholds de score generados por cada valor único observado |
| 5 | Optimización excesiva | **PARCIAL** | Grid TP/SL cosmético: avg MFE 27 ticks → TP 60–200 nunca se alcanza, resultados idénticos. El "TP=100 SL=40" no describe la operativa real |
| 6 | Errores de ejecución | **CONFIRMADO (moderado)** | 43/342 trades subsegundo, 8 no gestionables por latencia, p10 duración 822 ms; columna de slippage del propio exporter baja expectancy de +15.54 → +13.58 (−1.95 ticks) |
| 7 | Targets ambiguos | OK | `TP_And_SL_Hit_Same_Update` = 0; sim resuelve empates a favor del SL (conservador) |
| 8 | Duplicación de eventos | OK | 730 archivos, 0 fechas duplicadas, 0 entradas duplicadas, 1 fila por archivo |
| 9 | Dependencia de pocos meses/trades | OK | Top 10 trades = 12.7% del profit; top 3 meses = 17.0%. Sin concentración |
| 10 | Variables que describen el futuro | **CONFIRMADO — es el caso #1** | `Cvd_Pullback_Label`; también `Cvd_Worst_Label`, counts Cvd_* y todo lo post-entrada del CSV |
| 11 | Categorías/thresholds minados | **CONFIRMADO** | Cortes por cuantiles full-sample (or_regime, score percentiles) + 4,298 combos |
| 12 | Sizing con info no disponible | **CONFIRMADO** | Cutoffs = cuantiles del score sobre TODA la muestra; la regla ganadora se elige por `risk_score` calculado EN EL TEST SET; buckets degenerados (c3=0: 8 de 10 reglas idénticas). Los $33,510 no son proyectables |

## EDGE HONESTO SUPERVIVIENTE

Walk-forward anidado con SOLO features disponibles en la entrada (side, speed, score,
flags OK, A+), selección del setup exclusivamente con datos previos al año evaluado:

| year (OOS) | trades | WR | PF | EV bruto (ticks) | Setup elegido en train |
|---|---|---|---|---|---|
| 2023 | 72 | 51.4% | 1.43 | +4.53 | Delta_With_Side TP80 SL30 |
| 2024 | 74 | 47.3% | 1.10 | +1.22 | Delta_With_Side TP80 SL30 |
| 2025 | 76 | 51.3% | 1.13 | +1.92 | Delta_With_Side TP80 SL40 |
| 2026 | 62 | 51.6% | 1.46 | +5.53 | Body_OK TP80 SL30 |
| **TOTAL OOS** | **284** | **50.4%** | **~1.25** | **+3.19** | — |

Costos: slippage medido por el exporter ≈ 1.95 ticks/trade + comisión NQ ≈ 1 tick →
**EV neto OOS ≈ +0.2 ticks/trade ≈ CERO**. t-stat bruto ≈ 1.8 (ni el bruto es concluyente).

Único candidato débil restante: `score >= 9` (+8.0 ticks brutos, n=59, ~+5 netos), pero es
un threshold minado con n chico — solo válido si se pre-registra y se valida en datos
futuros no tocados.

## QUÉ CONSERVAR / QUÉ DESCARTAR

- DESCARTAR: filtro `cvd=Excelente`, PF 3.01, WR 73%, sizing 1/3/4, proyección $33,510, Lucid MC.
- DESCARTAR: cualquier feature del CSV medida después de la entrada como filtro de entrada.
- CONSERVAR (como hipótesis, no como edge): estrategia base ≈ breakeven tras costos;
  `score >= 9` como única hipótesis pre-registrable para validación forward.
- CORREGIR el pipeline antes de re-optimizar: (a) whitelist de columnas at-entry,
  (b) selección sin tocar test, (c) holdout final intocable, (d) sizing con cutoffs causales.
