# Auditoría de diseño — MATRIX CLASSIFICATION TEST R5

Estado: **PASS**.

La ruta predictora comienza en LB y termina en t_decision. El outcome A/B/C se une después.

| Control | Evidencia | Pasó |
| --- | --- | ---: |
| DETECTOR_VERSION | liquidity-burst-detector-2026-07-22-v7-postburst-matrix | 1 |
| POST_LB_EXPORT_BOUND | start=max(configured,t_burst) | 1 |
| DECISION_EXPORT_BOUND | event<=t_decision | 1 |
| ANALYSIS_CAUSAL_BOUND | t_burst<=event<=t_decision | 1 |
| PHYSICAL_100MS_STATES | 100 ms macro states | 1 |
| PATTERN_MINING | bigrams/trigrams/length4 + bifurcations | 1 |
| OUTCOMES_AFTER_FEATURES | labels joined after state construction | 1 |
| NO_OUTCOME_IN_TRADING | matrix files never enter exporter/signal bus | 1 |
| TEMPORAL_VALIDATION | discovery/validation/holdout | 1 |
| PERMUTATION_AND_CI | permutation + bootstrap CI | 1 |
| ABSTENTION | NO_DECISION at frozen confidence | 1 |
| TELEGRAM_LABEL | MATRIX CLASSIFICATION TEST | 1 |
| WORKSPACE_DETECTOR | LiquidityBurstDetector attached | 1 |
| DLL_INSTALLED | installed DLL equals current build | 1 |
| X10_ONLY | X10_R1 only | 1 |
| DST_SCOPE | 256 dates 2025-03-10->2026-07-17 | 1 |
| TECHNICAL_GATE | known burst dates=['10/03/2025', '18/03/2025', '27/03/2025', '03/04/2025'] | 1 |
| ISOLATED_ROOT | R5 root new/owned | 1 |
| PROTOCOL_PRESENT | C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_features_atas\PROTOCOLO_MATRIX_CLASSIFICATION_POST_LB_R5_20260722.md | 1 |
