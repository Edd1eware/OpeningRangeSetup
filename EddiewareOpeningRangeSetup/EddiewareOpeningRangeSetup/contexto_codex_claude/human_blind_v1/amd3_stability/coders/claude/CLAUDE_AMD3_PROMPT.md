# AMD-3 stability — codificación Claude ciega

Codifica 98 casos exactamente en:

`amd3_stability/orders/ORDER_CLAUDE_AMD3.csv`

## Únicos insumos permitidos

1. `frozen/RUBRICA_PERCEPTUAL_V1.md`
2. `amd3_stability/orders/ORDER_CLAUDE_AMD3.csv`
3. `amd3_stability/renders_perturbed2/HB001.png` a `HB098.png`

No leas ninguna otra carpeta o archivo. En particular, no leas:

- `ai_codifiers`;
- `amd2_stability`;
- `amd3_stability/stable_core`;
- `admin_sealed`;
- `round1_submission`;
- mapping, fechas, outcomes, familias, MFE, MAE, TP, SL o PnL;
- etiquetas previas.

## Regla

- A, B o C según la rúbrica.
- Ante duda A/B, usa C.
- No entrenes modelos ni expliques caso por caso.

## Salidas

Escribe únicamente:

1. `amd3_stability/coders/claude/CLAUDE_AMD3_LABELS_98.csv`
   con esquema `CaseID,label,coder,ordinal`, coder `CLAUDE_AMD3`.
2. `amd3_stability/coders/claude/CLAUDE_AMD3_RECEIPT.md`
   con conteos, 98/98 únicos y declaración de insumos.

Stdout: sólo `CLAUDE_AMD3_COMPLETE` o error breve. No imprimas etiquetas.
