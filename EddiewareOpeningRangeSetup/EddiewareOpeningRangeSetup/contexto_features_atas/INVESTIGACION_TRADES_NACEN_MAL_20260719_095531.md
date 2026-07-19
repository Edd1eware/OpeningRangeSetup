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

- Filas Liquidity Burst unidas: 183.
- Filas causales válidas: 141.
- Grupo A: 91.
- Grupo B: 2.
- Grupo C: 19.
- Grupo D: 71.
- Split cronológico congelado: 60% discovery, 20% validation, 20% holdout.
- Años observados: 2022, 2023, 2024, 2025, 2026.
- Esta corrida es confirmación multi-año; ningún resultado aislado autoriza filtros.

## Grupo D vs Grupo A

| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |
|---|---:|---:|---:|---:|---:|
| Directional_VWAP_Distance_Ticks_AtEntry | 0.8908 | 0.319 | 0.747 | 0 | 0 |
| PreEntry_Directional_Efficiency3_AtEntry | 0.8908 | 0.312 | 0.765 | 0 | 0 |
| liquidity_absorption_score | 1.0000 | 0.265 | 0.954 | 1 | 0 |
| absorption_pressure_1s | 1.0000 | 0.265 | 0.954 | 1 | 0 |
| burst_efficiency_score | 1.0000 | 0.265 | 0.775 | 1 | 0 |
| price_impact_per_100_contracts | 1.0000 | 0.261 | 0.686 | 0 | 0 |
| Profile_Normalized_Entropy | 1.0000 | 0.246 | 0.764 | 0 | 0 |
| signed_acceleration_1s | 1.0000 | 0.236 | 0.812 | 0 | 0 |
| signed_velocity_1s | 1.0000 | 0.224 | 0.786 | 0 | 0 |
| PreBurst_Acceptance_Dwell_Ratio_5s | 1.0000 | 0.216 | 0.818 | 0 | 0 |
| PreBurst_Price_Per_Delta_3s | 1.0000 | 0.210 | 0.734 | 0 | 0 |
| Previous_Delta_AtEntry | 1.0000 | 0.196 | 0.686 | 0 | 0 |

## Grupo D vs todos los demás

| Feature | q permutación | |Cliff δ| | Overlap | Estable | Robusta |
|---|---:|---:|---:|---:|---:|
| PreEntry_Directional_Efficiency3_AtEntry | 0.6322 | 0.344 | 0.648 | 0 | 0 |
| Directional_VWAP_Distance_Ticks_AtEntry | 0.7663 | 0.303 | 0.760 | 0 | 0 |
| PreEntry_Directional_Delta_Share3_AtEntry | 0.7663 | 0.216 | 0.768 | 0 | 0 |
| PreBurst_Acceptance_Dwell_Ratio_5s | 1.0000 | 0.239 | 0.799 | 0 | 0 |
| price_impact_per_100_contracts | 1.0000 | 0.227 | 0.701 | 1 | 0 |
| Profile_Normalized_Entropy | 1.0000 | 0.224 | 0.651 | 0 | 0 |
| absorption_pressure_1s | 1.0000 | 0.216 | 0.918 | 1 | 0 |
| Previous_Delta_AtEntry | 1.0000 | 0.216 | 0.750 | 0 | 0 |
| burst_efficiency_score | 1.0000 | 0.216 | 0.750 | 1 | 0 |
| liquidity_absorption_score | 1.0000 | 0.208 | 0.951 | 1 | 0 |
| signed_acceleration_1s | 1.0000 | 0.204 | 0.749 | 0 | 0 |
| Score_AtEntry | 1.0000 | 0.201 | 0.801 | 0 | 0 |

## Auditoría de Directional CLV

- Fórmula: `side_sign * (2*entry-causal_high-causal_low)/(causal_high-causal_low)`.
- El rango causal se construye exclusivamente con trades cuyo timestamp es <= señal; el OHLC de ATAS queda como auditoría y no entra al modelo.
- Filas CLV que reprodujeron fórmula, fuente y orden temporal: 0/183.
- Las filas con rango causal insuficiente o cualquier discrepancia se excluyen, no se rellenan.

| Variable | Pearson con CLV | Spearman con CLV | n |
|---|---:|---:|---:|
| Sin muestra causal suficiente | | | 0 |

## Independencia entre familias

- Features numéricas auditables: 104.
- Clusters por |Spearman| >= 0.65: 44.
- Pares redundantes con correlación >= 0.90: 100.
- Componentes PCA para explicar 80%: 11.
- Correlación, clustering, PCA, VIF y mutual information se exportan completos; cuentan fenómenos, no thresholds de trading.

## Estabilidad multi-año, Walk Forward y OOS

- Features que pasan el gate confirmatorio completo: 5.
- Gate: mismo signo en >=3 años, dirección estable en >=2 folds walk-forward, balanced accuracy mediana >0.50 y último año OOS >0.50.

| Comparación | Feature | Años estables | Folds WF | BA WF mediana | BA último año OOS | Gate |
|---|---|---:|---:|---:|---:|---:|
| D_vs_REST | PreEntry_Directional_Efficiency3_AtEntry | 1 | 4 | 0.603 | 0.789 | 1 |
| D_vs_REST | PreBurst_Rotation_Index_10s | 1 | 4 | 0.553 | 0.589 | 1 |
| D_vs_REST | Profile_Skewness | 1 | 4 | 0.537 | 0.522 | 1 |
| D_vs_REST | BreakOut_TICKS_PER_SEC_AtEntry | 1 | 4 | 0.528 | 0.622 | 1 |
| D_vs_A | BreakOut_TICKS_PER_SEC_AtEntry | 1 | 4 | 0.505 | 0.686 | 1 |
| D_vs_A | Score_AtEntry | 0 | 3 | 0.622 | 0.557 | 0 |
| D_vs_REST | PreBurst_Acceptance_Dwell_Ratio_5s | 0 | 4 | 0.617 | 0.678 | 0 |
| D_vs_A | PreEntry_Directional_Efficiency3_AtEntry | 0 | 4 | 0.599 | 0.757 | 0 |
| D_vs_A | PreBurst_Local_Entropy_10s | 0 | 1 | 0.597 | nan | 0 |
| D_vs_REST | Score_AtEntry | 0 | 2 | 0.595 | 0.589 | 0 |
| D_vs_A | Profile_Skewness | 0 | 4 | 0.580 | 0.586 | 0 |
| D_vs_A | Directional_VWAP_Distance_Ticks_AtEntry | 0 | 4 | 0.569 | 0.143 | 0 |
| D_vs_REST | Directional_VWAP_Distance_Ticks_AtEntry | 0 | 4 | 0.565 | 0.111 | 0 |
| D_vs_REST | Signed_Delta_Share_AtEntry | 0 | 4 | 0.560 | 0.678 | 0 |
| D_vs_A | PreBurst_Acceptance_Dwell_Ratio_5s | 0 | 4 | 0.558 | 0.614 | 0 |

## Respuesta posterior al burst

- Auditoría: OK.
- Filas descriptivas por horizonte/familia/métrica: 180.
- Estas métricas responden qué ocurrió 1s/3s/5s después del burst; están marcadas `POST_BURST_ONLY` y jamás se usan para decidir la entrada del mismo trade.
- Sirven para generar hipótesis de dinámica de respuesta, no para presentar rendimiento preentrada.

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
- Las respuestas post-burst se analizaron sólo como outcomes descriptivos separados.
- Ninguna ausencia de order book se rellenó o simuló.
- Una feature sólo se considerará confirmada si conserva estabilidad anual, walk-forward y OOS; si falla, se rechaza.

Artefactos: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\born_bad_trade_research_20260719_095531`
