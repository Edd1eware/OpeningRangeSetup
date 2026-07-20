# Resultado piloto MBO Liquidity Burst — STOP de compra

Fecha: 2026-07-20

## Decisión ejecutiva

La puerta preregistrada MBO **NO PASÓ**. Se detiene la compra de datos:

- No se descargaron las 40 fechas discovery restantes.
- No se descargaron ni evaluaron las 54 fechas A/B reservadas.
- No se modificó la lógica de trading.
- No se lanzó ATAS.

## Datos analizados

- 30 señales discovery: 15 absorciones A y 15 breakouts B.
- 10 fechas por año: 2022, 2023 y 2024.
- 15 BUY y 15 SELL.
- 360,492 mensajes MBO causales.
- 203 mensajes del padding posterior fueron excluidos con `ts_event <= cutoff`.
- 1,000 permutaciones de etiqueta dentro de año.

## Resultado primario

| Set de features | AUC LOYO |
| --- | ---: |
| Baseline causal existente (features originales + MBP/tape) | 0.796 |
| MBO solamente | 0.387 |
| Baseline causal + MBO | 0.569 |

La incorporación de MBO redujo el AUC en **0.227**. La prueba de permutación para la mejora produjo `p=0.9980`, por lo que no existe evidencia de información incremental bajo el protocolo congelado.

## Estabilidad

- MBO-only por año: 2022 `0.400`, 2023 `0.280`, 2024 `0.680`.
- MBO-only BUY: `0.607`.
- MBO-only SELL: `0.196`.
- Solo una de ocho condiciones de compra pasó.
- Ninguna de las 12 features compactas fue robusta tras BH y estabilidad por año/lado.

La señal univariada más grande fue `burst_w1_refill_100ms_share`, con Cliff delta `-0.396` y signo consistente, pero su `q_BH=0.816`; no es evidencia suficiente para comprar más observaciones.

## Conclusión científica

En esta muestra, la identidad de órdenes MBO local de los 10 segundos anteriores no anticipa de forma robusta absorción frente a breakout limpio y degrada el baseline causal. El resultado coincide con la experiencia anterior: añadir microestructura más granular no garantiza información predictiva incremental.

La falta del snapshot de medianoche limita únicamente el estado de órdenes preexistentes. Las métricas de órdenes nuevas, altas, cancelaciones, modificaciones, fills, refills, churn y asimetrías sí fueron observables dentro de las ventanas. El fracaso no puede atribuirse solamente a ausencia de cobertura MBO: las 12 features compactas tuvieron 100% de cobertura.

## Próximo paso recomendado

No continuar comprando MBO con el diseño actual. Conservar los archivos y el extractor para auditoría. El siguiente esfuerzo debe volver a la señal causal ya disponible y estudiar representaciones/condiciones de contexto sin retrasar la entrada, especialmente segmentación de régimen y la estabilidad del baseline existente. Cualquier hipótesis nueva debe usar las fechas 2025–2026 como validación cerrada, no como discovery.

## Artefactos

- Protocolo congelado: `contexto_features_atas/PROTOCOLO_PUERTA_MBO_LIQUIDITY_BURST_20260720.md`
- Reporte completo: `outputs/mbo_liquidity_burst_viability_20260720_r1/final_report.md`
- Auditoría: `outputs/mbo_liquidity_burst_viability_20260720_r1/final_integrity_audit.json`
- Ledger MBO: `outputs/mbo_liquidity_burst_viability_20260720_r1/mbo_feature_ledger.csv`
- Unión MBO+MBP+tape: `outputs/mbo_liquidity_burst_viability_20260720_r1/joined_mbo_mbp_tape_features.csv`
- Métricas: `outputs/mbo_liquidity_burst_viability_20260720_r1/loyo_model_metrics.csv`
- Permutaciones: `outputs/mbo_liquidity_burst_viability_20260720_r1/permutation_tests.csv`
- Puerta: `outputs/mbo_liquidity_burst_viability_20260720_r1/purchase_gate.csv`
- Gráficas: `outputs/mbo_liquidity_burst_viability_20260720_r1/visualizations/`

