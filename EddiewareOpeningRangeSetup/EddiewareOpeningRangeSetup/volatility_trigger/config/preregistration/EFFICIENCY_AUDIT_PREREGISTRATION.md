# Prerregistro: auditoría outcome-only de eficiencia

Fecha: 2026-07-26

ID: `VT_EFFICIENCY_OUTCOME_ONLY_V1`

Estado al congelar: `BEFORE_EFFICIENCY_VARIANT_OUTPUTS`

Discovery 2022, validation 2023, holdout 2024 y 2025–2026 permanecen sellados.

## Motivo

El smoke A1 produjo:

```text
PATH_EFFICIENCY_TRADE_V1
threshold = 0.65
status = DEGENERATE_TARGET_COMPONENT
```

La fórmula y el threshold originales no se cambian ni se eliminan.

## Universo

Se usan exclusivamente los candidatos del smoke A1. La auditoría es
outcome-only: no entrena modelos, no calcula AUC/PR-AUC/PnL y no convierte
ninguna variante en predictor.

Horizonte común: 2 segundos posteriores a cada candidato.

`SNIPER_CORE` es una máscara diagnóstica que exige simultáneamente:

- `TimeToImpulse_4t <= 750 ms`;
- `SignedDisplacement_1s >= 4 ticks`;
- `SignedDisplacement_2s >= 8 ticks`;
- `PreExpansionAE_4t <= 2 ticks`;
- `InitialImpulseMFE_3tPullback >= 8 ticks`.

No incluye eficiencia y no puede utilizarse como target de entrenamiento.

## Relojes y libro

Trades:

- usa el orden de archivo y timestamps efectivos A1;
- ninguna observación posterior a un instante puede entrar en su precio as-of.

Depth:

- carga desde 09:25 NY para calentar el libro antes de 09:30;
- procesa orden de archivo;
- mantiene un watermark causal igual al máximo timestamp visto;
- si un update queda hasta 50 ms detrás del watermark, se conserva con tiempo
  efectivo igual al watermark;
- si queda más de 50 ms detrás, se descarta como bloque obsoleto;
- nunca se reordena un update usando filas futuras.

Los updates con el mismo timestamp efectivo se coalescen antes de emitir un
estado BBO. Cada evento quote contiene best bid/ask y tamaños L1 absolutos.

Quote válido:

- `1 <= spread <= 4 ticks`;
- quote de entrada y terminal con edad máxima de 250 ms.

Mid:

```text
Mid = (BestBid + BestAsk) / 2
```

Microprice:

```text
Microprice =
    (BestAsk * BidSize + BestBid * AskSize)
    / (BidSize + AskSize)
```

Toda consulta en una malla usa last-observation-carried-forward as-of. No hay
interpolación con quotes futuras.

## Variantes congeladas

Para una serie `X_0...X_n` y dirección `d`:

```text
SignedNet = d * (X_n - X_0)
PathLength = sum(abs(X_i - X_i-1))
Efficiency = max(0, SignedNet) / max(PathLength, epsilon)
```

1. `trade_path_efficiency_v1`: trades, idéntica a la original.
2. `mid_efficiency_quote_changes`: mid en cada cambio BBO coalescido.
3. `mid_efficiency_sampled_25ms`: mid as-of cada 25 ms.
4. `mid_efficiency_sampled_50ms`: mid as-of cada 50 ms.
5. `mid_efficiency_sampled_100ms`: mid as-of cada 100 ms.
6. `microprice_efficiency`: microprice en cada cambio BBO coalescido.

Con precios trade y movimientos firmados desde la entrada:

```text
MFE = max(0, max(SignedMove))
MAE = max(0, -min(SignedMove))
PositiveFinal = max(0, SignedMove_2s)

excursion_efficiency =
    PositiveFinal / max(MFE + MAE, epsilon)

impulse_retention =
    PositiveFinal / max(MFE, epsilon)
```

Ambas se fijan en cero si su denominador es cero y se limitan a `[0,1]` sólo
contra error flotante.

## Actividad y correlaciones

Por candidato:

- `TradeCount`: trades en `(t0,t0+2s]`;
- `TradeRate = TradeCount / 2`;
- `DOMUpdateCount`: updates depth aceptados en `(t0,t0+2s]`;
- `PathLength`: denominador/source path de cada variante.

Se reportan Pearson y Spearman, con `n` pareado. La medida primaria para
dependencia mecánica es Spearman.

## Distribuciones obligatorias

Para cada variante:

- todos los candidatos;
- `SNIPER_CORE`;
- BUY;
- SELL.

Se reportan cobertura, faltantes, media, desviación y cuantiles congelados en
`efficiency_audit_config.json`. También se reportan distribución por sesión y
simetría BUY/SELL.

## Gates mecánicos

- variantes trade: cobertura global `>=0.99`;
- variantes quote: cobertura global `>=0.90` y por sesión `>=0.80`;
- todos los valores finitos dentro de `[0,1]`;
- tests sintéticos de espejo BUY/SELL exactos;
- diferencia absoluta de mediana BUY/SELL `<=0.05`;
- KS BUY/SELL `<=0.10`;
- mid 25/50/100: Spearman pareado mínimo `>=0.90` y diferencia absoluta de
  mediana máxima `<=0.05`;
- la variante V2 debe mejorar al menos 0.05 el máximo `abs(Spearman)` frente a
  `PATH_EFFICIENCY_TRADE_V1` sobre TradeCount, DOMUpdateCount y PathLength.

TradeCount y TradeRate se reportan ambos aunque sean transformaciones lineales.

## Elección sin optimizar positivos

Está prohibido usar conteo/tasa de positivos, `SNIPER_SUCCESS`, AUC, PR-AUC o
PnL para elegir variante.

Se recorre esta jerarquía fija y se toma la primera variante que supere todos
sus gates aplicables:

1. `mid_efficiency_sampled_50ms`, sólo si el bloque 25/50/100 es robusto;
2. `excursion_efficiency`;
3. `impulse_retention`;
4. `mid_efficiency_quote_changes`;
5. `microprice_efficiency`.

Si ninguna pasa: `NO_MECHANICALLY_VALID_EFFICIENCY_V2`.

Si una pasa, el resultado sólo nombra la medida elegida. Antes de usarla para
discovery se creará un prerregistro V2 separado, con fórmula, threshold y hash.
El threshold original 0.65 no se reduce.

`INFORMATION_STATUS=EFFICIENCY_AUDIT_PREREGISTERED_DISCOVERY_SEALED`
