# Auditoría de diseño — MATRIX + MBO CLASSIFICATION TEST, piloto 100

Estado: **PASS**.

MBO real: 100 archivos, 1,274,719 filas, 23,611,127 bytes. Ciclos iniciados con ADD dentro de ventana: 78.12%; censurados por la izquierda: 21.88%.

La censura inicial no se imputa. La ruta predictora termina en t_decision y los outcomes se unen después.

| Control | Evidencia | Pasó |
| --- | --- | ---: |
| MANIFEST_100_UNIQUE | 100 fechas/BurstId | 1 |
| DISCOVERY_ONLY | validation=0 holdout=0 | 1 |
| TEMPORAL_COVERAGE | years={2022: 34, 2023: 37, 2024: 29} | 1 |
| FAMILY_COVERAGE | families={'B_CLEAN_BREAKOUT': 41, 'C_MIXED_PATH': 30, 'A_TRUE_ABSORPTION': 29} | 1 |
| MBO_FILES_100 | files=100 | 1 |
| MBO_RAW_SCHEMA | order_id/actions/timestamps/flags/sequence | 1 |
| MBO_NO_BAD_BOOK | F_MAYBE_BAD_BOOK rows=0 | 1 |
| MBO_WITHIN_REQUEST | rows at/after end=0 | 1 |
| MBO_ACTIONS | actions={'C': 494465, 'A': 485688, 'M': 158532, 'F': 80925, 'T': 55109} | 1 |
| MBO_CENSORSHIP_EXPLICIT | snapshot=0 clear=0 | 1 |
| MBP_METADATA_100 | C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\preentry_liquidity_features_20260720_preentry_r2\preentry_mbp_feature_ledger.csv | 1 |
| DETECTOR_VERSION | liquidity-burst-detector-2026-07-22-v7-postburst-matrix | 1 |
| POST_LB_EXPORT_BOUND | start=max(configured,t_burst) | 1 |
| DECISION_EXPORT_BOUND | event<=t_decision | 1 |
| MBO_CAUSAL_BOUND | ts_event<=cutoff | 1 |
| MATRIX_CAUSAL_BOUND | matrix.audit_timeline | 1 |
| OUTCOMES_JOINED_LAST | predictors before target | 1 |
| FROZEN_COMBINATIONS | 7 exact families | 1 |
| LOYO_FIXED_MODEL | LOYO years; C=0.2 | 1 |
| PERMUTATION_BOOTSTRAP | 1000 + 1000 | 1 |
| NO_OUTCOME_IN_TRADING | analysis observational | 1 |
| TELEGRAM_LABEL | ETIQUETA MATRIX+MBO | 1 |
| FINAL_VERDICT_FROZEN | NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO | 1 |
| WORKSPACE_DETECTOR | LiquidityBurstDetector attached | 1 |
| DLL_INSTALLED | installed DLL equals current build | 1 |
| X10_ONLY | X10_R1 only | 1 |
| DATES_MATCH_MANIFEST | 100 manifest dates | 1 |
| TECHNICAL_GATE | dates=['05/04/2022', '06/04/2022', '26/04/2022', '27/04/2022'] | 1 |
| ISOLATED_ROOT | new/owned R1 root | 1 |
| PROTOCOL_PRESENT | C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_features_atas\PROTOCOLO_AUDITORIA_MATRIX_MBO_PILOTO100_20260722.md | 1 |
| MONITOR_REFRESH_EVERY_SESSION | progress_every=1 | 1 |
