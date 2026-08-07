# Volatility Trigger post-Liquidity Burst

Investigación aislada y reproducible para comprobar si features causales
posteriores a un `Liquidity Burst` anticipan una expansión inmediata, limpia y
direccional.

La primera corrida (`tier1_trade`) usa exclusivamente:

- trades ATAS;
- dirección del agresor;
- precio y volumen;
- contexto acumulado disponible hasta cada candidato.

No modifica `12_LiquidityBurstDetector.cs` ni `02_Visual_Logic.cs`. Tampoco usa
TP, SL, PnL, MFE/MAE de una estrategia ni información posterior como predictor.

## Orden

1. `run_research.py freeze`
2. `run_research.py smoke --telegram`
3. `run_research.py discovery --telegram`
4. `run_research.py validation --telegram` únicamente si discovery pasa.
5. `run_research.py holdout --telegram` únicamente si validation pasa.

Los artefactos se escriben en `artifacts/<stage>/`.

