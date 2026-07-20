# Auditoría de diseño — validación LB absorción vs breakout DST 2025–2026

Estado: **PASS**.

## Enfoque preservado

1. Detectar el Liquidity Burst con el detector vigente.
2. En el callback causal original de decisión (`feature_timestamp_utc`), estimar absorción verdadera A vs breakout limpio B.
3. No esperar la respuesta de 1/3/5 segundos para predecir. Esas ventanas sólo documentan el resultado físico posterior.
4. Tratar C mixto como abstención y D como otra salida; ninguno entra al AUC A/B.

El cutoff no es el inicio nominal del segundo: ocurre después de la publicación real del detector. En discovery, la latencia publicación→decisión fue mediana 38.935 ms y máxima 140.300 ms. No se agrega demora artificial.

## Modelo y contextos congelados

- Baseline mínimo: 10 variables, regresión logística regularizada.
- MBO: excluido; el piloto empeoró el baseline.
- MBP/tape incremental: excluido; delta de AUC discovery -0.005.
- VWAP_FAR: `abs(Directional_VWAP_Distance_Ticks_AtEntry) > 136.565000`.
- RV60_HIGH: `Realized_Volatility_60s_Ticks > 11.810993`.
- Los contextos sólo estratifican la validación; no filtran ni cambian trades.

## Por qué se retienen sólo dos contextos

VWAP_FAR y RV60_HIGH fueron los únicos contextos que conservaron señal al contrastar el baseline preregistrado con su representación mínima. FLOW_LOW, ATR_HIGH y PROFILE_DISPERSED dependieron del conjunto de variables y quedan descartados antes de abrir el holdout.

## Checklist

| Control | Evidencia | Pasó |
| --- | --- | ---: |
| PACKAGE_SHA256 | Frozen model hash matches sealed spec | 1 |
| LABEL_SOURCE_SHA256 | A/B/C labeling implementation matches frozen spec | 1 |
| TRAINING_ROWS | 70 expected; observed 70 | 1 |
| TRAINING_YEARS | Observed 2022-2024 | 1 |
| HOLDOUT_NOT_OPENED | Frozen spec validation years: [] | 1 |
| REPLAY_SCOPE | 256 dates; 2025-03-10 -> 2026-07-17 | 1 |
| CORE_FEATURE_ORDER | 10 frozen predictors | 1 |
| FEATURE_TIMING | Every frozen predictor has window_end_seconds <= 0 | 1 |
| NO_OUTCOME_PREDICTORS | No response/MAE/MFE/result/exit/future predictor | 1 |
| TRADE_EXPORT_HEADERS | All entry-side frozen predictors exist in trade_inputs | 1 |
| REGIME_EXPORT_HEADERS | VWAP-distance and RV60 are exported before entry | 1 |
| DISCOVERY_CAUSAL_ROWS | Causal rows 70/70 | 1 |
| PUBLISH_PRECEDES_DECISION | Publish-to-decision latency min=0.000 ms | 1 |
| MIXED_ABSTAINS | C_MIXED_PATH is abstention and is excluded from A/B metrics | 1 |
| NO_MBO_DEPENDENCY | MBO and incremental MBP/tape excluded | 1 |
| EXPORTER_VERSION | score-exporter-2026-07-19-v27-final-causal-publish-guard | 1 |
| DETECTOR_VERSION | liquidity-burst-detector-2026-07-19-v4-publish-clock-audit | 1 |
| X10_ONLY | Run plan rejects X1 and uses X10_R1 only | 1 |
| POST_RESPONSE_LABEL_ONLY | 1/3/5s response is excluded from same-entry predictors | 1 |
| TRADING_UNCHANGED | Observational runner and frozen offline evaluator only | 1 |

## Decisión previa a corrida

La estabilidad global discovery falló únicamente por SELL (AUC 0.521 para existing; 0.541 para core), por lo que esta corrida es una prueba de falsación única, no un despliegue. La adenda del protocolo sí autoriza abrir 2025–2026 porque tres regímenes pasaron la puerta preregistrada; la auditoría conserva sólo los dos robustos a representación.

Si el holdout falla, se detiene la línea y no se reajusta con 2025–2026.
