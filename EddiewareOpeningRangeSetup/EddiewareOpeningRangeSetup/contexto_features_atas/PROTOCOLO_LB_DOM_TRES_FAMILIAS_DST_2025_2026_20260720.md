# Protocolo LB DOM — tres familias DST 2025–2026

Fecha: 2026-07-20  
Corrida: `CODEX LB DOM TRES FAMILIAS DST 2025-2026 R2`

## Objetivo

Detectar primero el Liquidity Burst y usar únicamente información presente en su cutoff causal para anticipar una de tres trayectorias. La entrada, SL, TP, RR y gestión quedan congelados.

## Etiquetas de resultado

1. `A_CLEAN_ABSORPTION`: resultado TP, MAE <=10 ticks y MFE >= TP inicial.
2. `B_CLEAN_CONTINUATION`: resultado SL, MFE <=10 ticks y MAE >= SL inicial.
3. `C_VARIABLE_TRADE`: outcome con MAE/MFE y SL/TP iniciales válidos que no cumple ninguna de las dos trayectorias limpias. Incluye TP/SL con camino mixto y otras salidas terminales medibles.
4. `EXCLUDED_NO_PATH_METRICS`: exclusión técnica; no es una cuarta familia analítica.

MAE, MFE y resultado solo se conocen después de la decisión. Se usan para formar estas etiquetas y para describir la Familia C; están excluidos del catálogo de predictores.

## Organización interna de la Familia C

Se conserva la diferencia `MFE/TP - MAE/SL`:

- mayor que +0.15: trayectoria variable inclinada hacia absorción por outcome;
- menor que -0.15: trayectoria variable inclinada hacia continuación por outcome;
- entre -0.15 y +0.15: trayectoria variable balanceada.

Al cierre se añade una organización DOM descriptiva por terciles del predictor primario: inclinación DOM a absorción, centro variable o inclinación DOM a continuación. No se convierte en filtro ni reemplaza la etiqueta C.

## Hipótesis causal DOM

Predictor primario pre-registrado: `DOM_Ahead_Depth_Per_Aggressive_L3`.

Orden esperado: **A > C > B**. Una pared pasiva grande frente a la agresión debería ser mayor en absorción limpia, intermedia en trades variables y menor en continuación limpia.

Telegram muestra el indicador operativo de investigación actualizado:

`Efectividad del DOM antes del movimiento : xx% xx sesiones promedio de ticks: xx a favor del movimiento esperado`

El porcentaje es la tasa de acierto causal del predictor DOM primario disponible en t0 para anticipar continuación frente a reversión del precio un segundo después. Se excluye desplazamiento cero. La regla queda congelada en discovery: `DOM_Ahead_Depth_Per_Aggressive_L3 < 0.20` pronostica continuación; un valor mayor o igual pronostica reversión. `xx sesiones` es el número real de fechas X10 terminadas. El promedio de ticks es firmado en la dirección pronosticada: los errores restan ticks, por lo que no se infla promediando solamente aciertos. AUC y concordancia A–C–B se conservan en el análisis científico, pero ya no ocupan esta línea de Telegram.

## Criterio final pre-registrado

- al menos 20 eventos DOM válidos;
- cobertura >=75%;
- concordancia ordinal primaria >=0.60;
- permutación unilateral <0.10;
- concordancia ordinal media de la familia DOM >=0.55;
- después se exige estabilidad temporal y BUY/SELL en el informe científico.

Si no se cumple, se detiene esta línea de hipótesis. No se ajustarán thresholds ni definiciones mirando 2025–2026 durante la corrida.

## Compatibilidad operativa ATAS

ATAS quedó actualizado a 8.0.14.395. En esta versión los botones WPF Play/Stop del Replay pueden ignorar clics físicos sintetizados aunque aparezcan habilitados. El runner R2 invoca directamente el comando de automatización y conserva el clic como fallback para versiones anteriores. Esto evita falsos `REPLAY_NOT_STARTED` y que un escritor activo vuelva inestable un CSV terminal.

## Artefactos esperados

- `engineered_features.csv`: dataset causal y etiquetas A/C/B;
- `dom_geometry_metrics.csv`: AUC A–C, C–B, A–B y concordancia ordinal;
- `variable_trade_dom_organization.csv`: organización descriptiva de Familia C;
- `final_report.md`, tablas y gráficas del análisis científico;
- auditoría y resultado final en `contexto_features_atas`.
