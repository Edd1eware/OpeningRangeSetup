# CODEX AMD-2 — Recibo de codificación ciega

## Estado

- Codificación completa: 98/98 casos.
- Codificador constante: `CODEX_AMD2`.
- Conteos: A = 28, B = 42, C = 28.

## Integridad validada

- 98 filas de datos.
- 98 `CaseID` únicos.
- Ordinales exactos del 1 al 98.
- Orden idéntico a `amd2_stability/orders/ORDER_CODEX_AMD2.csv`.
- Dominio de etiquetas limitado a `A`, `B` y `C`.
- Esquema del CSV: `CaseID,label,coder,ordinal`.

## Entradas permitidas consultadas

- Rúbrica completa: `frozen/RUBRICA_PERCEPTUAL_V1.md`.
- Orden sellado: `amd2_stability/orders/ORDER_CODEX_AMD2.csv`.
- Únicamente los 98 renders `HB*.png` requeridos en `amd2_stability/renders_perturbed/`, observados una sola vez y secuencialmente en el orden sellado.

No se consultaron etiquetas previas, consenso original, codificadores de IA, material sellado administrativo, envíos de ronda, mappings, outcomes, fechas, familias, MFE, MAE, TP, SL ni PnL. No se emplearon modelos auxiliares.

## SHA-256

- `RUBRICA_PERCEPTUAL_V1.md`: `1D76FBA5838F1D5FE550167649D192B88B4BD9B7A6EA7AAA204D359721DAC6C4`
- `ORDER_CODEX_AMD2.csv`: `451ABAD340C4934714FC5B3AED35F84485290A9D20DE5E54E687F2DBE10D509D`
- `CODEX_AMD2_LABELS_98.csv`: `B0EF4FB1779442771185BB2D5E1CB64260D1A2CBF8CA5DDB17CF2B90FA95A5CE`
