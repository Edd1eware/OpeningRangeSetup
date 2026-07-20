# Protocolo congelado — segmentación causal de régimen y estabilidad del baseline

Fecha de congelación: 2026-07-20, antes de calcular desempeño del baseline sobre las 70 fechas discovery completas.

## Alcance y aislamiento

- Se usan exclusivamente 70 eventos A/B del split `discovery`, comprendidos entre 2022 y 2024.
- 2025–2026 no se usan para seleccionar variables, umbrales, modelos, segmentos ni conclusiones.
- Las familias mixtas C quedan fuera de esta fase.
- Unidad estadística: evento/día.
- No se ejecuta ATAS y no se compran datos.

## Pregunta

Determinar si el baseline causal existente es estable fuera de año y si existe un régimen causal con cobertura suficiente donde la separación entre absorción A y breakout B sea materialmente más fuerte, sin retrasar la entrada.

## Baselines congelados

1. `CORE_BASELINE`: las 10 variables causales usadas anteriormente.
2. `EXISTING_CAUSAL`: `CORE_BASELINE` más las 12 variables MBP/tape pre-entry fijadas en la investigación anterior.

Modelo primario: regresión logística regularizada (`C=0.2`, class weight balanced), imputación mediana y estandarización dentro de cada fold.

## Validación temporal

- Leave-one-year-out (LOYO): entrenar en dos años y predecir el tercero.
- Reportar AUC global OOF, por año y por BUY/SELL.
- 2,000 permutaciones de etiqueta dentro de año, reajustando el modelo en cada repetición.
- Intervalo bootstrap 95% del AUC OOF, remuestreando dentro de estratos año × familia.
- Estabilidad de signo de coeficientes entre los tres folds.

## Ejes de régimen causales congelados

Cada umbral es la mediana calculada únicamente en los años de entrenamiento de cada fold. El año dejado fuera nunca participa en su propio umbral.

1. `ATR5`: `Prior_Closed_ATR5_Ticks_AtEntry` — bajo/alto.
2. `OR_WIDTH`: `OR_WidthTicks` — estrecho/ancho.
3. `REALIZED_VOL_60S`: `Realized_Volatility_60s_Ticks` — baja/alta.
4. `PATH_EFFICIENCY`: `PreBurst_Path_Efficiency_10s` — rotacional/direccional.
5. `FLOW_INTENSITY`: `Flow_3_5_GrossAggressive` — bajo/alto.
6. `VWAP_DISTANCE_ABS`: valor absoluto de `Directional_VWAP_Distance_Ticks_AtEntry` — cerca/lejos.
7. `PROFILE_CONCENTRATION`: `Profile_Concentration` — disperso/concentrado.

No se permiten combinaciones posteriores de ejes en esta fase para evitar fragmentación y búsqueda oportunista.

## Criterio de estabilidad global

El `EXISTING_CAUSAL` se considera estable en discovery solo si cumple simultáneamente:

1. AUC OOF global >= 0.65.
2. `p_permutación <= 0.05`.
3. AUC de cada año >= 0.55.
4. AUC BUY y SELL >= 0.55.
5. Límite inferior bootstrap 95% >= 0.50.

## Puerta de régimen candidato

Un segmento puede documentarse como hipótesis futura solo si cumple simultáneamente:

1. Cobertura >= 35% de las 70 operaciones.
2. Al menos 8 A y 8 B.
3. AUC OOF del `EXISTING_CAUSAL` >= 0.70.
4. Mejora de AUC frente a su complemento >= 0.10.
5. `q_BH <= 0.10` en la prueba exploratoria de permutación de predicciones OOF.
6. Al menos dos años elegibles con AUC >= 0.60 y ningún año elegible con AUC < 0.45. Un año es elegible con al menos 2 A y 2 B en el segmento.
7. AUC BUY y SELL >= 0.55 cuando ambos lados contienen al menos 2 A y 2 B.

Si ningún segmento pasa, no se propone un filtro de régimen. Si alguno pasa, se documenta como hipótesis congelada, no como cambio operativo ni como permiso para abrir 2025–2026.

## Adenda de autorización del usuario

Después de congelar los criterios anteriores, el usuario autorizó una corrida DST 2025–2026 únicamente si discovery identifica variables o un régimen que pase la puerta completa. Esta adenda no modifica umbrales ni criterios. Si la puerta falla, la corrida no se lanza.
