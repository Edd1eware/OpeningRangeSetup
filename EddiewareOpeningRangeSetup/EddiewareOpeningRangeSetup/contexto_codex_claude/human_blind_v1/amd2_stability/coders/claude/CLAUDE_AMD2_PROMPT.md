# AMD-2 stability — codificación Claude ciega

Codifica 98 casos exactamente en el orden de:

`amd2_stability/orders/ORDER_CLAUDE_AMD2.csv`

## Únicos insumos permitidos

1. `frozen/RUBRICA_PERCEPTUAL_V1.md`
2. `amd2_stability/orders/ORDER_CLAUDE_AMD2.csv`
3. `amd2_stability/renders_perturbed/HB001.png` a `HB098.png`

No leas ninguna otra carpeta o archivo. En particular, no leas:

- `ai_codifiers`;
- `original_consensus`;
- `admin_sealed`;
- `round1_submission`;
- mapping, fechas, outcomes, familias, MFE, MAE, TP, SL o PnL;
- etiquetas previas de Claude, Codex o Eduardo.

## Regla

- Asigna A, B o C siguiendo literalmente la rúbrica.
- Ante duda A/B, usa C.
- No entrenes modelos.
- No expliques caso por caso.

## Salidas

Escribe únicamente:

1. `amd2_stability/coders/claude/CLAUDE_AMD2_LABELS_98.csv`
   con esquema `CaseID,label,coder,ordinal`, coder `CLAUDE_AMD2`.
2. `amd2_stability/coders/claude/CLAUDE_AMD2_RECEIPT.md`
   con conteos, 98/98 únicos y declaración de insumos.

En stdout informa sólo `CLAUDE_AMD2_COMPLETE` o un error breve. No imprimas etiquetas.
