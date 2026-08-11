# Liquidity Burst: de etiqueta visual a entrada causal (v23)

## Hallazgo

La etiqueta visual `BUY ABSORPTION | SELL POSITION` / `SELL ABSORPTION | BUY POSITION`
se dibujaba directamente desde `LiquidityBurstSignalBus`, pero no era por si sola una
decision terminal de entrada. El motor de score solo adjuntaba el burst cuando ya habia
un breakout del mismo lado y aun podia exigir rango, volumen y delta. Ademas, el lado
opuesto no quedaba garantizado para un burst aislado.

Consecuencia: ver la etiqueta en pantalla no implicaba necesariamente un trade en el
mismo precio y segundo. Validar el CSV anterior como estrategia de absorcion habria sido
conceptualmente incorrecto.

## Correccion causal v23

- El snapshot inmutable de un segundo del `LiquidityBurstDetector` es la decision.
- `BUY` agresion absorbida ejecuta `SELL`; `SELL` agresion absorbida ejecuta `BUY`.
- La entrada usa `burst.Price` y el timestamp ya publicado por el detector.
- No se agregan filtros posteriores a esta rama que retrasen o supriman una etiqueta
  emitida. El detector conserva sus propios umbrales causales.
- Sigue limitada a una entrada por sesion por las guardas existentes del exporter.
- Version de exporter: `score-exporter-2026-07-16-v23-liquidity-burst-entry`.

## Protocolo de validacion

1. Comparar 6 fechas en Replay X1 y X10.
2. Abortar si difieren los campos operativos (entrada, lado, SL, TP, salida, resultado).
3. Si sincroniza, correr DST 2026 completo en X10 con balance inicial de $150,000.
4. Verificar en cada trade que el lado sea opuesto al burst y que precio/tiempo coincidan.
5. Medir MAE, MFE, WR, PF, trades por mes y reglas LucidPro 150k.
6. Solo si 2026 es prometedor, ampliar sin reoptimizar a 2025 y despues hacia atras,
   con limite de datos 04/04/2022.

## Reglas anti-sesgo

- Sin look-ahead ni revision retrospectiva de etiquetas.
- No elegir parametros usando el resultado del mismo periodo que se reporta como prueba.
- Mantener baseline congelado al ampliar años.
- Reportar slippage/costos y cualquier fallo de Replay; no rellenar fechas fallidas.
- No mezclar CSV de versiones anteriores con v23.
