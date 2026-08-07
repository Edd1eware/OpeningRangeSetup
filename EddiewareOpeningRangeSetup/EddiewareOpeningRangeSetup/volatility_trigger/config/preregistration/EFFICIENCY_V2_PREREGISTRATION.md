# Prerregistro Efficiency V2 diagnóstica

Fecha: 2026-07-27

ID: `VT_EFFICIENCY_DIAGNOSTIC_V2`

## Decisión mecánica

La auditoría congelada `VT_EFFICIENCY_OUTCOME_ONLY_V1` eligió
`impulse_retention` mediante una jerarquía que prohibía usar positivos, AUC,
PR-AUC o PnL.

Resultado que activó la decisión:

- cobertura: 100%;
- diferencia de mediana BUY/SELL: 0;
- KS BUY/SELL: 0.029168;
- máximo `abs(Spearman)` con actividad/path: 0.013473;
- mejora frente a `PATH_EFFICIENCY_TRADE_V1`: 0.056160;
- gate requerido: 0.05.

No se rescata `mid_efficiency_sampled_25ms`, aunque superó numéricamente el gate,
porque la jerarquía congelada sólo permitía 50 ms como representante del bloque
mid muestreado y 50 ms falló.

## Fórmula V2

Para la trayectoria trade posterior al candidato hasta 2 segundos:

```text
SignedMove(t) = direction * (Price(t) - EntryPrice)
MFE_2s = max(0, max(SignedMove))
PositiveFinal_2s = max(0, SignedMove_2s)

IMPULSE_RETENTION_V2 =
    PositiveFinal_2s / max(MFE_2s, epsilon)
```

Si `MFE_2s=0`, la medida vale cero. El rango es `[0,1]`.

## Threshold

```text
threshold = 0.65
policy = CARRY_FORWARD_UNCHANGED_FROM_V1
```

No se redujo el threshold después de observar distribuciones.

## Rol

`IMPULSE_RETENTION_V2` es sólo diagnóstico outcome-only. Puede combinarse con
los cinco gates de `SNIPER_CORE` para describir trayectorias, pero:

- no es el target principal;
- no es predictor;
- no puede seleccionar features;
- no puede rescatar el estudio original;
- no abre discovery.

El target científico principal pasa a ser `POST_LB_REGIME`:
`CONTINUATION / REVERSAL / NO_EXPANSION / AMBIGUOUS`.

Discovery, validation y holdout continúan sellados.

`INFORMATION_STATUS=EFFICIENCY_V2_DIAGNOSTIC_FROZEN`
