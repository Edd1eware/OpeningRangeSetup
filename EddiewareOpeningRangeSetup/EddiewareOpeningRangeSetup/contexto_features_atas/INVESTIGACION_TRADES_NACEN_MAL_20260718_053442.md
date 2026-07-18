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

- Filas Liquidity Burst unidas: 41.
- Filas causales válidas: 41.
- Grupo A: 16.
- Grupo B: 1.
- Grupo C: 3.
- Grupo D: 21.
- Split cronológico congelado: 60% discovery, 20% validation, 20% holdout.

## Grupo D vs Grupo A

| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |
|---|---:|---:|---:|---:|---:|
| Directional_CLV_AtEntry | 0.1334 | 0.893 | 0.214 | 1 | 0 |
| PreEntry_Directional_Delta_Share3_AtEntry | 0.9991 | 0.321 | 0.571 | 0 | 0 |
| mean_trade_size | 0.9991 | 0.429 | 0.696 | 1 | 0 |
| weekday_index | 0.9991 | 0.339 | 0.661 | 0 | 0 |
| PreEntry_Volume_Climax_Ratio_AtEntry | 0.9991 | 0.304 | 0.643 | 0 | 0 |
| Previous_Delta_AtEntry | 0.9991 | 0.232 | 0.536 | 0 | 0 |
| profile_confluence_4t | 0.9991 | 0.250 | 0.571 | 0 | 0 |
| Sell_Imbalance_Count_AtEntry | 0.9991 | 0.375 | 0.714 | 0 | 0 |
| TradesPerSecond | 0.9991 | 0.277 | 0.643 | 0 | 0 |
| Buy_Imbalance_Count_AtEntry | 0.9991 | 0.304 | 0.696 | 0 | 0 |
| delta_persistence_1_3 | 0.9991 | 0.304 | 0.696 | 0 | 0 |
| Prior_Closed_ATR3_Ticks_AtEntry | 0.9991 | 0.152 | 0.393 | 0 | 0 |

## Grupo D vs todos los demás

| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |
|---|---:|---:|---:|---:|---:|
| Directional_CLV_AtEntry | 0.1334 | 0.800 | 0.414 | 1 | 0 |
| signed_velocity_3s | 0.6392 | 0.379 | 0.571 | 0 | 0 |
| Sell_Imbalance_Count_AtEntry | 0.6392 | 0.429 | 0.657 | 0 | 0 |
| PreEntry_Directional_Delta_Share3_AtEntry | 0.6392 | 0.329 | 0.571 | 0 | 0 |
| Previous_Delta_AtEntry | 0.6499 | 0.329 | 0.586 | 0 | 0 |
| Velocity3s | 0.6392 | 0.336 | 0.614 | 0 | 0 |
| Delta5s | 0.6392 | 0.386 | 0.686 | 0 | 0 |
| DeltaChangeZScore | 0.6392 | 0.386 | 0.686 | 0 | 0 |
| PreEntry_Volume_Climax_Ratio_AtEntry | 0.6392 | 0.314 | 0.643 | 0 | 0 |
| Delta3s | 0.6392 | 0.357 | 0.686 | 0 | 0 |
| CumulativeDeltaWindow | 0.6392 | 0.357 | 0.686 | 0 | 0 |
| Buy_Imbalance_Count_AtEntry | 0.6392 | 0.329 | 0.671 | 0 | 0 |

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

Artefactos: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\born_bad_trade_research_20260718_053442`
