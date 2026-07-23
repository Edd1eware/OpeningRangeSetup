# Protocolo R3 — DOM-only para separar absorción y continuación limpias

## Objetivo único

Detectar primero el `Liquidity Burst` y decidir si el estado causal del DOM en `t0` permite distinguir:

- **A — ABSORCIÓN LIMPIA:** resultado TP, `MAE <= 10 ticks` y `MFE >= TP inicial`.
- **B — CONTINUACIÓN LIMPIA:** resultado SL, `MFE <= 10 ticks` y `MAE >= SL inicial`.
- **C — TRADE VARIABLE:** trayectoria terminal válida que no cumple A ni B. Se conserva para auditoría y abstención, pero no forma parte del target de inferencia ni del entrenamiento.

No se modifica la operativa, entrada, SL, TP, RR ni gestión. La corrida es observacional.

## Predictores congelados

La R3 conserva exclusivamente estas once variables `DOM_*`, disponibles en el cutoff causal del burst:

1. `DOM_Spread_Ticks`
2. `DOM_Directional_Microprice_Ticks`
3. `DOM_Directional_Depth_Imbalance_L1`
4. `DOM_Directional_Depth_Imbalance_L3`
5. `DOM_Directional_Depth_Imbalance_L5`
6. `DOM_Ahead_Depth_Per_Aggressive_L3`
7. `DOM_Ahead_L1_Concentration_L5`
8. `DOM_Directional_PullStack_1s`
9. `DOM_Directional_PullStack_3s`
10. `DOM_Ahead_Stack_Share_1s`
11. `DOM_Near_Churn_Per_Aggressive_1s`

Campos de validez, niveles y best bid/ask se conservan únicamente para auditar la calidad del snapshot. No son predictores del modelo.

## Prevención de contaminación

- R2 queda archivada como exploratoria y no se mezcla con R3.
- R3 usa una carpeta, estado y manifiesto nuevos.
- El manifiesto queda congelado en 256 sesiones DST, del 10/03/2025 al 17/07/2026.
- Respuestas a 1/3/5 segundos, MAE, MFE, resultado, precio/hora de salida y métricas finales son posteriores a `t0`: solo sirven para etiqueta o auditoría.
- No se incorporan tape, CVD, OR, VWAP, perfil, régimen, MBO ni features derivadas que no comiencen con `DOM_`.
- C no participa en selección de features, permutation test, AUC ni modelos. Solo se reporta su posición descriptiva.

## Hipótesis y medición primaria

Hipótesis preregistrada: `DOM_Ahead_Depth_Per_Aggressive_L3` será mayor en A que en B, porque una pared pasiva suficiente respecto de la agresión debería frenar el desplazamiento.

La métrica visible en Telegram será:

`Efectividad del DOM antes del movimiento : xx% xx sesiones`

Ese porcentaje es el AUC A-vs-B de la hipótesis primaria. `50%` equivale a azar; no es WR ni probabilidad de ganar. Las familias A/B/C y sus conteos siguen disponibles en el detalle de cada trade y en los reportes.

El análisis final aplicará a las once features:

- AUC A-vs-B con orientación física preregistrada.
- Permutación unilateral A-vs-B.
- Tamaño de efecto, overlap y corrección BH.
- Split cronológico discovery/validation/holdout.
- Modelos binarios A-vs-B, incluyendo CatBoost si está disponible.
- Estabilidad temporal y por lado BUY/SELL antes de considerar una señal prometedora.

## Criterio de decisión

La hipótesis primaria solo se considera prometedora si reúne simultáneamente:

- al menos 20 eventos limpios A/B con DOM válido;
- cobertura DOM A/B de al menos 75%;
- AUC A-vs-B de al menos 0.60;
- `p < 0.10` en permutación unilateral;
- AUC A-vs-B media de las once features de al menos 0.55.

La decisión científica real exigirá además estabilidad cronológica y BUY/SELL. Si DOM no mejora claramente el azar fuera de muestra, se detiene esta línea sin convertirla en filtro de trading.

## Paquete exploratorio entregado a Claude Fable

La R2 parcial se congeló en:

`C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\outputs\claude_fable_r2_dom_20260721\R2_DOM_features_para_Claude_Fable_20260721.xlsx`

Debe usarse únicamente para proponer hipótesis. La hoja principal es `DOM_Labeled`; `Responses_Audit` contiene información posterior al burst y está prohibida como predictor.
