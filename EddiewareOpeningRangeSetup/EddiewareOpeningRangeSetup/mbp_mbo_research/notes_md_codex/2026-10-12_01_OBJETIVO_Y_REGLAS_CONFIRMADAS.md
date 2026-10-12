# Objetivo y reglas confirmadas para buscar el edge

Fecha: 2026-10-12, hora del usuario America/Mexico_City.

El objetivo solicitado es encontrar estadísticamente una ventaja neta de costes que permita comparar y aspirar a pasar LucidPro 50K o 100K. La captura de la curva es una referencia de comportamiento, no una curva que haya que reproducir ajustando parámetros.

## Setup confirmado directamente por el usuario

- OR: high y low de la vela 09:30–09:31 de Nueva York.
- Operativa en M1. Primera decisión al cierre 09:32; esperar cierre de la vela.
- Debe romper el rango con cuerpo, tener imbalance en la dirección y VWAP a favor. Si no cumple, seguir esperando hasta el cierre 09:40.
- Aclaración posterior del usuario del 12 de octubre: también acepta que la vela abra fuera del rango. No se exige apertura dentro del OR. La referencia `baseline_1r` ya usa esta regla; exigir apertura dentro es únicamente una variante experimental.
- Comparación diagonal: compra ask contra bid inferior; venta bid contra ask superior.
- Ratio 300%, mínimo 70 contratos, filas de 5 ticks.
- Imbalances separados son válidos; SL una fila (5 ticks) detrás del más lejano al precio.
- RR inicial 1:1. Máximo una operación al día.

VWAP de la captura: indicador ATAS VWAP/TWAP, periodo Custom, modo VWAP, volumen Total, sesión09:30–16:00, fuente Close(NQ), solo VWAP, sin mostrar primer periodo parcial, lookback20.

El código oficial de ATAS usa el precio fuente de cada vela y su volumen. Con un gráfico M1 y fuente Close: `VWAP = suma(Close_M1 × Volume_M1) / suma(Volume_M1)` desde09:30. No usar la VWAP heredada ponderada por cierres de1segundo ni una VWAP tick a tick como sustitutos exactos. El color azul corresponde a valor creciente, rojo a no creciente en la fuente publicada.

Fuente: https://github.com/AtasPlatform/Indicators/blob/Develop/Technical/VWAP.cs

## Datos comprobados

- `C:/Users/k_99_/Desktop/codding/MBP_MBO/ohlcv1s`:150archivos DBN,103,990,763bytes.
- `C:/Users/k_99_/Desktop/codding/MBP_MBO/trades`:150archivos DBN,247,567,034bytes.
- Rango de fechas:2026-03-09 a2026-10-09.
- Hay también5archivosMBO de septiembre. No hacen falta para construir el footprint si los trades incluyen lado agresor.
- Databento trades: A=vendedor agresor (bid), B=comprador agresor (ask).
- Los archivos muestreados de trades declaran la ventana09:25–10:30NY y NQ.v.0.
- La entrada enviada como de hoy12octubre no se puede reconstruir con estos archivos, que terminan9octubre. La imagen muestra una posición short con VWAP roja, pero no permite medir precios exactos de entry/SL/TP.

## Correcciones detectadas

1. En `scripts/05_l2_features.py:153` y `scripts/12_full_spec.py:160-168` las guardas de bordes están invertidas. Compra referencia fila inferior: debe existir `lvl-1`; venta referencia superior: debe existir `lvl+1`. Los nuevos motores corrigen esto sin sobrescribir reportes históricos.
2. La primera lectura de `imbalances.png` incluyó erróneamente un tercer imbalance. Ampliación verificada: solo venta107/29 y compra294/95 tienen relleno;85×64 no tiene relleno y la fila superior es159×124.
3. El código heredado añade filtros no confirmados aquí: banda30–120ticks, pool de imbalances anteriores, invalidación por revisita y ausencia de cambios de color VWAP desde el OR. No incorporarlos silenciosamente a la regla del usuario.

## Alcance estadístico

Las150sesiones ya se usaron en búsquedas previas del proyecto. Todos los resultados nuevos sobre ese periodo son exploratorios. Un candidato requiere validación con reglas congeladas en datos no inspeccionados o seguimiento prospectivo.

Los reportes heredados no demuestran edge. En `MBP_MBO/reports/full_spec_far.csv`,RR1:1 tiene26operaciones reales,12ganadoras,WR46.15%,EVneto−3.2615ticks con coste supuesto1.8ticks. Sus operaciones están repetidas para5RR; no son130observaciones independientes. Además, usa la lógica de bordes y VWAP heredada, y reglas extras. No tomar ese resultado como estimación definitiva del setup actualizado.

Se preparan dos estudios nuevos: un control fijo60/60ticks del aporte direccional del footprint, y replay del stop estructural con las reglas confirmadas. El control fijo no sustituye la estrategia real.

## LucidPro, reglas oficiales consultadas2026-10-12

| Cuenta | Target | MLL inicial | DLL activado | Máximo |
|---|---:|---:|---:|---|
|50K|USD3,000|USD2,000|USD1,200|4minis o40micros|
|100K|USD6,000|USD3,000|USD1,800|6minis o60micros|

MLL según máximo balance de cierre diario, bloqueo en capital inicial+USD100. El DLL es una configuración de compra y puede estar desactivado. No trasladar condiciones de LucidFlex a LucidPro ni condiciones de payout funded a evaluación.

Target/MLL=1.5 para50K y2 para100K. Es una ventaja estructural de50K en ese criterio, no una recomendación definitiva. La selección necesita señales, sizing y trayectorias netas de equity iguales y comparables.

Fuentes:

- https://support.lucidtrading.com/en/articles/12890029-lucidpro-evaluation-account
- https://support.lucidtrading.com/en/articles/12890136-lucidpro-drawdown
- https://support.lucidtrading.com/en/articles/16226068-lucidpro-customization

Protocolo detallado y código nuevos: `C:/Users/k_99_/Documents/ChatGPT/research_edge/RESEARCH_PROTOCOL.md`.
