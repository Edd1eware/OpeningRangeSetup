# CODEX AMD-3 — Recibo de codificación ciega

## Estado y conteos

- Casos completados: 98/98
- A: 36
- B: 38
- C: 24
- Codificador: `CODEX_AMD3`

## Integridad

- Esquema CSV: `CaseID,label,coder,ordinal`
- `CaseID` únicos: 98/98
- Ordinales: enteros consecutivos 1–98, sin duplicados ni huecos
- Orden: coincide exactamente con `ORDER_CODEX_AMD3.csv`
- Etiquetas válidas: únicamente A, B o C
- Campo `coder`: `CODEX_AMD3` en 98/98 filas

## Declaración de insumos

La codificación se realizó exclusivamente con:

1. `frozen/RUBRICA_PERCEPTUAL_V1.md`, leído completo.
2. `amd3_stability/orders/ORDER_CODEX_AMD3.csv`.
3. Las 98 imágenes `HB*.png` de `amd3_stability/renders_perturbed2/`, observadas en el orden indicado.

No se consultaron `outcomes` ni otros insumos prohibidos por la orden. No se entrenaron modelos. Ante duda razonable A/B se aplicó C.
