# Investigación cuantitativa — Trades que nacen mal

## Resultado principal

Ninguna variable disponible superó simultáneamente significancia corregida, tamaño de efecto y estabilidad cronológica. La hipótesis no queda demostrada con el dataset actual y no se autoriza modificar la estrategia.

## Definición congelada

- A: trade ganador (resultado realizado positivo).
- B: trade perdedor con MFE > 30 ticks.
- C: trade perdedor con 2 < MFE <= 30 ticks.
- D: trade perdedor con MFE <= 2 ticks.
- MFE, MAE, duración y resultado son etiquetas posteriores; nunca entran como features.

## Muestra

- Filas Liquidity Burst unidas: 189.
- Filas causales válidas: 189.
- Grupo A: 94.
- Grupo B: 2.
- Grupo C: 19.
- Grupo D: 74.
- Split cronológico congelado: 60% discovery, 20% validation, 20% holdout.

## Grupo D vs Grupo A

| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |
|---|---:|---:|---:|---:|---:|
| Previous_Delta_AtEntry | 1.0000 | 0.232 | 0.719 | 0 | 0 |
| absorption_pressure_1s | 1.0000 | 0.219 | 0.828 | 1 | 0 |
| burst_efficiency_score | 1.0000 | 0.219 | 0.791 | 1 | 0 |
| price_impact_per_100_contracts | 1.0000 | 0.218 | 0.745 | 1 | 0 |
| liquidity_absorption_score | 1.0000 | 0.215 | 0.832 | 1 | 0 |
| signed_velocity_1s | 1.0000 | 0.185 | 0.866 | 1 | 0 |
| mean_trade_size | 1.0000 | 0.184 | 0.808 | 0 | 0 |
| signed_acceleration_1s | 1.0000 | 0.176 | 0.695 | 1 | 0 |
| Score_AtEntry | 1.0000 | 0.174 | 0.843 | 0 | 0 |
| signed_velocity_decay_1_5 | 1.0000 | 0.173 | 0.852 | 1 | 0 |
| OR_WidthTicks | 1.0000 | 0.159 | 0.864 | 0 | 0 |
| range | 1.0000 | 0.159 | 0.864 | 0 | 0 |

## Grupo D vs todos los demás

| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |
|---|---:|---:|---:|---:|---:|
| Previous_Delta_AtEntry | 0.9936 | 0.254 | 0.661 | 0 | 0 |
| price_impact_per_100_contracts | 0.9936 | 0.179 | 0.674 | 0 | 0 |
| signed_acceleration_1s | 0.9936 | 0.158 | 0.716 | 0 | 0 |
| BuySellRatio | 0.9936 | 0.127 | 0.712 | 0 | 0 |
| Delta_Change_AtEntry | 0.9936 | 0.130 | 0.728 | 0 | 0 |
| Score_AtEntry | 0.9936 | 0.179 | 0.849 | 0 | 0 |
| signed_velocity_decay_1_5 | 0.9936 | 0.115 | 0.780 | 0 | 0 |
| burst_efficiency_score | 0.9936 | 0.153 | 0.837 | 1 | 0 |
| OR_WidthTicks | 0.9936 | 0.159 | 0.850 | 0 | 0 |
| range | 0.9936 | 0.159 | 0.850 | 0 | 0 |
| TradesPerSecond | 0.9936 | 0.100 | 0.781 | 0 | 0 |
| vwap_poc_spread_ticks | 0.9936 | 0.120 | 0.821 | 0 | 0 |

## Variables nuevas recomendadas para Build Alpha

| Feature | Impacto | Implementación | Overfit | Estado | Mecanismo |
|---|---|---|---|---|---|
| seconds_from_open | HIGH | EASY | LOW | AVAILABLE_NOW | Régimen temporal de apertura |
| or_position_fraction | HIGH | EASY | LOW | AVAILABLE_NOW | Entrada extendida o dentro del balance |
| execution_cvd_alignment | HIGH | EASY | LOW | AVAILABLE_NOW | Conflicto con agresión acumulada |
| velocity_decay_1_5 | HIGH | EASY | MEDIUM | AVAILABLE_NOW | Impulso que se extingue al disparar |
| delta_decay_1_5 | HIGH | EASY | MEDIUM | AVAILABLE_NOW | Agresión instantánea sin persistencia |
| nearest_profile_reference | HIGH | EASY | LOW | AVAILABLE_NOW | Choque inmediato contra liquidez estructural |
| prior_atr_ticks | HIGH | MEDIUM | LOW | ADD_EXPORTER_NEXT | Normaliza SL/OR por volatilidad |
| overnight_range_ticks | HIGH | MEDIUM | LOW | ADD_EXPORTER_NEXT | Compresión/expansión previa |
| opening_gap_atr | HIGH | MEDIUM | LOW | ADD_EXPORTER_NEXT | Inventario overnight y repricing |
| vwap_slope_ticks_per_min | HIGH | MEDIUM | MEDIUM | ADD_EXPORTER_NEXT | Dirección/curvatura del valor negociado |
| poc_migration_ticks_per_min | HIGH | HARD | MEDIUM | ADD_EXPORTER_NEXT | Migración del valor contra la entrada |
| profile_shape_moments | MEDIUM | HARD | MEDIUM | ADD_EXPORTER_LATER | P/b/D/B/doble distribución sin etiqueta subjetiva |
| acceptance_dwell_ratio | HIGH | HARD | MEDIUM | ADD_EXPORTER_NEXT | Acceptance frente a rechazo instantáneo |
| level_retest_count | MEDIUM | MEDIUM | LOW | ADD_EXPORTER_NEXT | Nivel debilitado por pruebas repetidas |
| refill_after_sweep_ratio | HIGH | HARD | HIGH | REQUIRES_REPLAYABLE_BOOK | Absorción real frente a vacío de liquidez |
| book_imbalance_multilevel | MEDIUM | HARD | HIGH | REQUIRES_REPLAYABLE_BOOK | Asimetría de profundidad preentrada |

## Orden mínimo de instrumentación siguiente

1. ATR previo, overnight range y gap normalizado.
2. Pendiente causal de VWAP y migración de POC/Value Area.
3. Acceptance dwell ratio y número de retests de OR/VA/POC.
4. Momentos matemáticos del perfil (skew, kurtosis y multimodalidad).
5. Refill/book/icebergs sólo si Historia X10 entrega un stream reproducible; si no, se rechazan.

## Salvaguardas

- No se optimizaron parámetros, thresholds, TP, SL, trailing ni gestión.
- No se creó ningún filtro de entrada.
- No se usó información posterior a la entrada como predictor.
- Ninguna ausencia de order book se rellenó o simuló.
- Cualquier feature descubierta deberá validarse en una temporada futura no utilizada aquí.

Artefactos: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\born_bad_trade_research_20260718_004112`
