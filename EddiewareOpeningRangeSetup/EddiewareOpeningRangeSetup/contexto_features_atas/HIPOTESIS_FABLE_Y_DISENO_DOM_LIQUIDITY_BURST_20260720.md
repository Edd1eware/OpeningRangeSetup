# Hipótesis Fable y diseño DOM — Liquidity Burst A vs B

Fecha: 2026-07-20  
Objetivo invariable: detectar el Liquidity Burst y, en el cutoff causal original, anticipar si terminará como **A) absorción verdadera** o **B) breakout limpio**, sin esperar cinco segundos ni modificar la operativa.

## Evidencia que motivó esta última corrida

- La última muestra 2025–2026 no mostró separación fuera de muestra: CORE AUC 0.384; BURST_MECHANISM 0.436; ALL_CAUSAL 0.327.
- El incremento BURST_MECHANISM sobre CORE fue +0.051, pero su bootstrap cruzó ampliamente cero `[-0.113, +0.216]`.
- No hubo candidatos univariados estables entre años y BUY/SELL.
- El piloto MBO de 30 eventos tampoco justificó seguir comprando datos: MBO-only AUC 0.387 y baseline+MBO 0.569 frente a baseline 0.796.
- Las variables MBP/tape anteriores estaban ancladas a niveles puntuales. No medían la geometría transversal simultánea del touch y los primeros cinco niveles.

## Lectura física propuesta por Claude Fable

### Absorción verdadera

- Pared pasiva o reposición delante de la agresión.
- Ejecuciones concentradas repetidamente en el mismo precio.
- Extremo direccional alcanzado temprano y estancamiento antes del cutoff.
- Intervalos entre prints agresivos que aumentan y tamaños que se reducen.
- Contraflujo que aparece en la parte final del burst.

### Breakout limpio

- Libro delgado delante del movimiento.
- Barrido de varios niveles y saltos en la escalera.
- Cancelación de liquidez que estaba delante del agresor.
- Apertura temporal del spread.
- Extremo direccional alcanzado cerca del final del burst.
- Agresión que conserva intensidad y tamaño.

## Hipótesis sugeridas por Fable

| ID | Variable | Dirección esperada |
| --- | --- | --- |
| H1 | `Hidden_Reload_Ratio_BurstPrice`: volumen ejecutado en el precio final / máximo visible allí | A > B |
| H2 | `Max_Same_Price_Volume_Run_Share` | A > B |
| H3 | `Terminal_Stall_Ms`: tiempo desde el último extremo direccional nuevo hasta t0 | A > B |
| H4 | Proximidad a nivel previo no probado: PDH/PDL/ONH/ONL/settle/POC | A > B |
| H5 | `Intra_Burst_Front_Load_Share` | A > B |
| H6 | `Inter_Print_Interval_Slope` | A > B |
| H7 | `Counterflow_Late_Share` | A > B |
| H8 | `Aggressor_Size_Retention` | B > A |
| H9 | `Ladder_Gap_Count` | B > A |
| H10 | `Largest_Sweep_Levels` | B > A |
| H11 | `Spread_Vacuum_Share_1s` | B > A |
| H12 | `Ahead_Wall_Persistence_Ratio` | A > B |

Shortlist recomendada por Fable: `DOM_Ahead_Depth_Per_Aggressive_L3`, H1, H2, H3 y H4. Esta corrida instrumenta primero la familia causal transversal DOM_GEOMETRY; las hipótesis que requieran identidad de orden no se aproximan desde MBP.

## Familia DOM_GEOMETRY instrumentada por Codex

El detector v5 consume `MarketDepthChanged` directamente en orden de callbacks de ATAS y publica sólo estado disponible hasta t0. Variables:

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

También exporta validez, motivo de exclusión, niveles disponibles, best bid/ask, profundidades y conteos de actualizaciones. Se rechaza un snapshot con menos de cinco niveles por lado, libro cruzado, spread fuera de 1–4 ticks o midpoint a más de cuatro ticks del precio del burst.

## Indicadores ATAS

El workspace operativo ya contiene `Liquidity Burst Detector`, `ATAS Score Trade Result Exporter`, CVD y la lógica visual OR. Los indicadores incorporados de heatmap/DOM/Smart Tape pueden ayudar a inspección humana, pero no añaden columnas a los CSV. Añadirlos al gráfico de replay duplicaría procesamiento. Por eso la medición se realiza dentro del detector conectado al DOM y no mediante un panel visual adicional.

## Métrica Telegram

`Efectividad del DOM antes del movimiento : xx% xx sesiones promedio de ticks: xx a favor del movimiento esperado` usa una regla direccional congelada en discovery (`DOM_Ahead_Depth_Per_Aggressive_L3 < 0.20` pronostica continuación; de lo contrario reversión) contra la respuesta a un segundo. El porcentaje es tasa de acierto, no WR. Los ticks son el desplazamiento medio firmado en la dirección pronosticada, incluyendo errores como valores negativos; las sesiones son fechas X10 realmente terminadas.

## Criterio de decisión

La corrida es de investigación observacional, no un filtro de trading. Una señal prometedora debe tener cobertura suficiente, magnitud fuera de azar y estabilidad temporal y BUY/SELL. Si DOM_GEOMETRY no mejora claramente el baseline ni conserva dirección, se detiene esta línea y no se compra más MBO. 2025–2026 se analiza sin reajustar umbrales durante la corrida.

## Adenda R2: Familia C solicitada

Antes de reiniciar la corrida se amplió la taxonomía sin tocar la operativa. La hipótesis principal ahora exige el orden **ABSORCIÓN LIMPIA > TRADE VARIABLE > CONTINUACIÓN LIMPIA**. La concordancia de Telegram es la media de AUC A–C, C–B y A–B. La Familia C incorpora todos los outcomes con MAE/MFE, SL y TP iniciales válidos que no sean una trayectoria limpia; conserva `MAE/SL`, `MFE/TP` y su forma de trayectoria exclusivamente para describir/etiquetar el resultado. Esas variables posteriores a la entrada están prohibidas como predictores.
