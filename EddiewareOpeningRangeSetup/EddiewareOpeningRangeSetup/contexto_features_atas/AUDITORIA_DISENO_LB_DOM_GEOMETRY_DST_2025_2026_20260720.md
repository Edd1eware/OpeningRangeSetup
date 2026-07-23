# Auditoría de diseño — LB DOM_GEOMETRY DST 2025–2026

Estado: **PASS**.

## Enfoque preservado

Se detecta primero el Liquidity Burst y se fotografía el DOM disponible en el mismo cutoff causal. Las respuestas 1/3/5s y el resultado del trade sólo etiquetan A/B después; nunca predicen la misma entrada.

No se agregan Heatmap, Smart Tape ni DOM Power al chart de replay: son visualizaciones del mismo stream y no exportan columnas adicionales. El detector ya está adjunto y consume MarketDepthChanged directamente.

## Checklist

| Control | Evidencia | Pasó |
| --- | --- | ---: |
| DETECTOR_VERSION | liquidity-burst-detector-2026-07-20-v5-dom-geometry | 1 |
| DOM_FEATURE_COUNT | 11 expected=11 | 1 |
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
| PRIMARY_HYPOTHESIS | Wall ahead/aggression preregistered A>B | 1 |
