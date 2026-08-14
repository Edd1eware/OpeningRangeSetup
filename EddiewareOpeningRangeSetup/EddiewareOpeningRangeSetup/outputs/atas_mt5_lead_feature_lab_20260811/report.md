# Laboratorio causal — CFD MT5 líder vs ATAS L2, RR 2R

Muestra: 2025-03-10 a 2026-08-07.
Guard de leakage: **PASS**. 37 features congeladas a la señal; 0 filas omitidas.

## Universos

- Todos los candidatos ejecutados: n=1271, W-L=299-972, WR=23.52%, PF=0.598, AvgR=-0.306, NetR=-389.03.
- Submuestra confirmada después por ATAS: n=113, W-L=45-68, WR=39.82%, PF=1.324, AvgR=+0.195, NetR=+22.00.

La submuestra confirmada usa información futura para definir el universo; sirve para describir el patrón, no para desplegar un filtro en vivo. Las features dentro de ambos universos sí son causales.

## Qué tienen en común las ganadoras

- **ATAS aún no ha rebasado el pivote mapeado con su cierre:** gap mediano ganador +0.349 ATR frente a -0.166 ATR en perdedoras.
- **ATAS ya dejó de insistir hacia ese pivote:** las ganadoras tuvieron mediana de 1 de las últimas 3 velas aproximándose; las perdedoras, 2 de 3.
- **El CFD va delante, pero no demasiado:** divergencia mediana de 1.110 ATR en ganadoras frente a 1.600 ATR en perdedoras. Un desfase extremo fue peor, no mejor.
- **ATAS muestra freno o inicio de reacción:** desplazamiento a 3 velas de -0.200 ATR en ganadoras frente a -0.667 ATR en perdedoras.

La regla estructural fija —sin calibrar umbrales— exige que solo 0–1 de las últimas 3 velas ATAS siga acercándose y que el cierre ATAS permanezca antes del pivote mapeado:

- TOTAL: n=394, W-L=147-247, WR=37.31%, PF=1.154, AvgR=+0.096, NetR=+37.81; IC95% bootstrap AvgR [-0.043, +0.238], p unilateral WR>33.33%=0.0535.
- 2025: n=243, W-L=93-150, WR=38.27%, PF=1.214, AvgR=+0.132, NetR=+32.01; IC95% bootstrap AvgR [-0.044, +0.315], p unilateral WR>33.33%=0.0600.
- 2026: n=151, W-L=54-97, WR=35.76%, PF=1.060, AvgR=+0.038, NetR=+5.80; IC95% bootstrap AvgR [-0.185, +0.262], p unilateral WR>33.33%=0.2901.

La dirección se repite en ambos años, pero el intervalo todavía incluye cero y 2026 solo deja un margen pequeño. Es una hipótesis candidata para congelar y validar hacia delante, no una regla aprobada para operar todavía.

## Top diferencias univariadas

### ALL_CAUSAL_CANDIDATES

| Feature | Dirección winners | d | AUC orientada | q FDR | d 2025 | d 2026 | estable |
|---|---|---:|---:|---:|---:|---:|---|
| MappedPivotGapATR_AtEntry | HIGHER | 0.724 | 0.701 | 0.0000 | 0.712 | 0.747 | sí |
| ATASAway3ATR_AtEntry | HIGHER | 0.627 | 0.672 | 0.0000 | 0.591 | 0.691 | sí |
| ATASApproachBars3_AtEntry | LOWER | -0.491 | 0.636 | 0.0000 | -0.474 | -0.518 | sí |
| LeadDivergence3ATR_AtEntry | LOWER | -0.410 | 0.617 | 0.0000 | -0.385 | -0.456 | sí |
| ATASAway5ATR_AtEntry | HIGHER | 0.441 | 0.617 | 0.0000 | 0.411 | 0.492 | sí |
| ATASApproachBars5_AtEntry | LOWER | -0.355 | 0.601 | 0.0000 | -0.357 | -0.348 | sí |
| LeadDivergence5ATR_AtEntry | LOWER | -0.317 | 0.585 | 0.0000 | -0.286 | -0.375 | sí |
| ReturnCorrelation20_AtEntry | HIGHER | 0.286 | 0.582 | 0.0001 | 0.338 | 0.197 | sí |
| ATASAway1ATR_AtEntry | HIGHER | 0.267 | 0.572 | 0.0006 | 0.236 | 0.319 | sí |
| ATASSignalBodyATR_AtEntry | HIGHER | 0.270 | 0.572 | 0.0006 | 0.234 | 0.328 | sí |
| ATASRange5ATR_AtEntry | LOWER | -0.178 | 0.547 | 0.0454 | -0.159 | -0.214 | sí |
| LeadDivergence1ATR_AtEntry | LOWER | -0.171 | 0.545 | 0.0549 | -0.139 | -0.228 | sí |

### CONFIRMED_LATER_SUBSET

| Feature | Dirección winners | d | AUC orientada | q FDR | d 2025 | d 2026 | estable |
|---|---|---:|---:|---:|---:|---:|---|
| MappedPivotGapATR_AtEntry | HIGHER | 0.614 | 0.671 | 0.0807 | 0.709 | 0.290 | sí |
| LeadDivergence3ATR_AtEntry | LOWER | -0.347 | 0.626 | 0.4329 | -0.397 | -0.231 | sí |
| CFDAway3ATR_AtEntry | LOWER | -0.288 | 0.599 | 0.7587 | -0.321 | -0.192 | sí |
| LeaderSwingATR_AtEntry | LOWER | -0.316 | 0.595 | 0.7587 | -0.285 | -0.380 | sí |
| ATASRange5ATR_AtEntry | HIGHER | 0.218 | 0.578 | 0.7587 | 0.155 | 0.352 | sí |
| CFDEfficiency5_AtEntry | HIGHER | 0.259 | 0.573 | 0.7587 | 0.229 | 0.378 | sí |
| CFDSignalRangeATR_AtEntry | LOWER | -0.266 | 0.572 | 0.7587 | -0.197 | -0.317 | sí |
| CFDAway1ATR_AtEntry | LOWER | -0.216 | 0.561 | 0.7587 | -0.095 | -0.385 | sí |
| ATASApproachBars3_AtEntry | LOWER | -0.241 | 0.560 | 0.7587 | -0.222 | -0.240 | sí |
| MinuteNY_AtEntry | HIGHER | 0.221 | 0.560 | 0.7587 | 0.297 | 0.036 | sí |
| CFDSignalBodyATR_AtEntry | LOWER | -0.223 | 0.559 | 0.7587 | -0.095 | -0.399 | sí |
| LeadDivergence1ATR_AtEntry | LOWER | -0.193 | 0.545 | 0.8245 | -0.110 | -0.323 | sí |

## Holdout por año: regla elegida solo con 2025

- **ALL_CAUSAL_CANDIDATES**: `MappedPivotGapATR_AtEntry >= -0.0411855`.
  - Train 2025: n=396, W-L=140-256, WR=35.35%, PF=1.078, AvgR=+0.050, NetR=+19.77.
  - Holdout 2026 seleccionado: n=259, W-L=83-176, WR=32.05%, PF=0.907, AvgR=-0.063, NetR=-16.26.
  - Baseline 2026: n=479, W-L=109-370, WR=22.76%, PF=0.566, AvgR=-0.334, NetR=-160.15.
- **CONFIRMED_LATER_SUBSET**: `MappedPivotGapATR_AtEntry >= 0.373455`.
  - Train 2025: n=38, W-L=23-15, WR=60.53%, PF=3.067, AvgR=+0.816, NetR=+31.00.
  - Holdout 2026 seleccionado: n=13, W-L=6-7, WR=46.15%, PF=1.714, AvgR=+0.385, NetR=+5.00.
  - Baseline 2026: n=37, W-L=13-24, WR=35.14%, PF=1.083, AvgR=+0.054, NetR=+2.00.

## Walk-forward anidado, una regla

- **ALL_CAUSAL_CANDIDATES** seleccionado OOS: n=311, W-L=100-211, WR=32.15%, PF=0.925, AvgR=-0.050, NetR=-15.59.
- Baseline en las mismas ventanas: n=635, W-L=152-483, WR=23.94%, PF=0.610, AvgR=-0.295, NetR=-187.60.
- **CONFIRMED_LATER_SUBSET** seleccionado OOS: n=15, W-L=6-9, WR=40.00%, PF=1.333, AvgR=+0.200, NetR=+3.00.
- Baseline en las mismas ventanas: n=53, W-L=20-33, WR=37.74%, PF=1.212, AvgR=+0.132, NetR=+7.00.

## Lectura disciplinada

- Las asociaciones full-sample son descriptivas hasta que sobrevivan el holdout 2026 y el walk-forward.
- Una feature con q baja pero dirección distinta entre 2025 y 2026 se trata como régimen, no como regla estable.
- No se usaron delay real, hora del pivote ATAS, reacción posterior, MFE/MAE, resultado ni salida como predictores.
- El siguiente gate es congelar cualquier regla superviviente y medirla en datos nuevos, sin recalibrar.
