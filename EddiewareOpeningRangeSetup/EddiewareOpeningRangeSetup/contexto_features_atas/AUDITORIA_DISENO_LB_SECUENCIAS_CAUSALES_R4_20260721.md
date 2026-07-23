# Auditoría de diseño — secuencias causales DOM+tape R4

Estado: **PASS**.

La operativa permanece congelada. El nuevo archivo es observacional y solo incluye eventos con reloj causal no posterior a t_decision.

| Control | Evidencia | Pasó |
| --- | --- | ---: |
| DETECTOR_VERSION | liquidity-burst-detector-2026-07-21-v6-causal-sequence | 1 |
| TIMELINE_ENABLED_DEFAULT | ExportCausalTimeline defaults true | 1 |
| LOOKBACK_BOUND | 1..10 seconds | 1 |
| EVENT_SCHEMA | arrival/source/causal/available/decision timestamps | 1 |
| DOM_AND_TAPE_CAPTURE | MarketDepthChanged + ProcessTrade append events | 1 |
| PREDECISION_FILTER | timeline writer enforces causal timestamp <= decision | 1 |
| ACTUAL_DECISION_TIMESTAMP | Feature available equals detector publish timestamp | 1 |
| MBP_SEMANTICS | depth changes are not mislabeled cancel/fill | 1 |
| NO_OUTCOME_IN_TIMELINE | no MAE/MFE/result columns in timeline header | 1 |
| RESET_ARCHIVES_TIMELINE | fresh runs archive burst_causal_timeline.csv | 1 |
| TRADING_UNCHANGED | timeline never enters exporter or signal bus | 1 |
| WORKSPACE_DETECTOR | LiquidityBurstDetector attached | 1 |
| DLL_INSTALLED | installed indicator equals current build | 1 |
| X10_ONLY | run plan X10_R1 only | 1 |
| DST_SCOPE | 256 dates 2025-03-10->2026-07-17 | 1 |
| TECHNICAL_GATE | known burst dates=['10/03/2025', '18/03/2025', '27/03/2025', '03/04/2025'] | 1 |
| ISOLATED_ROOT | R4 root is new/owned | 1 |
| HANDLE_REPLAY | Replay acquisition avoids whole-desktop UIA | 1 |
