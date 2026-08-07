# Errata 001: artefacto de referencia ausente

Fecha: 2026-07-27

El archivo:

```text
artifacts/equivalence/reference_smoke_v1/liquidity_bursts.csv
```

no existe físicamente, aunque
`artifacts/equivalence/reference_smoke_v1/manifest.json` conserva el hash
esperado:

```text
4FCF29AB5205F4D1F3947F15EF1A195FCD21E9EDC333B5049C1C4D785A699254
```

El manifest histórico no se reescribe ni se presenta como íntegro. Los otros
tres archivos declarados en ese manifest sí existen y coinciden con sus hashes.

Impacto:

- la cadena agregada `reference_smoke_v1` está incompleta;
- no invalida por sí sola la comparación exacta por sesión realizada contra
  los caches por sesión;
- impide afirmar que el snapshot agregado histórico está completo.

`INFORMATION_STATUS=ERRATA_MISSING_REFERENCE_ARTIFACT_RECORDED`
