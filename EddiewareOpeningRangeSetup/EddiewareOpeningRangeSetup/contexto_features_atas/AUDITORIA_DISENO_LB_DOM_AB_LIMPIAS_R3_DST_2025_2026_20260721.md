# Auditoría de diseño — LB DOM absorción vs continuación limpias R3

Estado: **PASS**.

## Enfoque preservado

Se detecta primero el Liquidity Burst y se fotografía el DOM disponible en el mismo cutoff causal. MAE/MFE y el resultado sólo etiquetan después: absorción limpia, continuación limpia o trade variable; nunca predicen la misma entrada. El target primario es A vs B; C se conserva como abstención descriptiva y no diluye la separación limpia.

No se agregan Heatmap, Smart Tape ni DOM Power al chart de replay: son visualizaciones del mismo stream y no exportan columnas adicionales. El detector ya está adjunto y consume MarketDepthChanged directamente.

## Checklist

| Control | Evidencia | Pasó |
| --- | --- | ---: |
| DETECTOR_VERSION | liquidity-burst-detector-2026-07-20-v5-dom-geometry | 1 |
| DOM_FEATURE_COUNT | 11 expected=11 | 1 |
| DOM_ONLY_SCOPE | active predictors=11 expected=11 | 1 |
| NO_NON_DOM_PREDICTORS | Every active predictor starts with DOM_ | 1 |
| DOM_SCHEMA | Every preregistered DOM feature is emitted by C# | 1 |
| DOM_CAUSAL_WINDOWS | Every DOM window ends at t0 or earlier | 1 |
| DIRECT_DEPTH_CALLBACK | MarketDepthChanged is consumed in arrival order | 1 |
| DOM_VALIDITY_GUARD | top-5, spread, crossed/stale checks | 1 |
| NO_POST_T0_DOM | No response/MAE/MFE fields among DOM predictors | 1 |
| WORKSPACE_DETECTOR | LiquidityBurstDetector attached to saved chart | 1 |
| WORKSPACE_EXPORTER | ATASScoreTradeResultExporter attached to saved chart | 1 |
| WORKSPACE_CSV_ENABLED | Detector ExportCsv=true and expected output folder | 1 |
| DLL_INSTALLED | Installed indicator DLL equals current Debug build | 1 |
| X10_ONLY | Run plan contains X10_R1 only | 1 |
| DST_SCOPE | 256 dates; 2025-03-10 -> 2026-07-17 | 1 |
| TRADING_UNCHANGED | DOM fields are observational; exporter change is Telegram text only | 1 |
| CLEAN_AB_TARGET | Model target is clean absorption versus clean continuation; C is abstention | 1 |
| THREE_FAMILY_LEDGER | Every trade is still grouped A, B or C from terminal MAE/MFE | 1 |
| TELEGRAM_FORMAT | Efectividad del DOM antes del movimiento : 69.6% 96 sesiones | 1 |
| R3_ISOLATED_ROOT | New R3 root is empty/new or owned by this exact run label | 1 |
| OUTCOME_ONLY_PATH | MAE/MFE organize labels but are excluded from predictor specifications | 1 |
| PRIMARY_HYPOTHESIS | Wall ahead/aggression preregistered ABSORPTION > CONTINUATION | 1 |
