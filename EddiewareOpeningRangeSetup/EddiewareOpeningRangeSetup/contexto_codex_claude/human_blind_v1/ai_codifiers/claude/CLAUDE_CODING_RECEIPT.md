# CLAUDE_CODING_RECEIPT

- Coder: CLAUDE
- Fecha: 2026-07-24
- Casos codificados: 98/98 (ordinal 1..98, orden exacto de ORDER_CLAUDE.csv)
- CaseID unicos: 98/98 (sin duplicados)

## Conteos

| label | n |
|---|---|
| A | 30 |
| B | 38 |
| C | 30 |
| TOTAL | 98 |

## Validacion

- Esquema de salida: `CaseID,label,coder,ordinal` — cumplido.
- 98 filas, ordinal consecutivo 1..98, coder = CLAUDE en todas.
- Regla de duda aplicada: ante duda entre A y B se asigno C.

## Declaracion de insumos usados

Unicamente:
1. `frozen/RUBRICA_PERCEPTUAL_V1.md` (rubrica A/B/C congelada; el archivo `RUBRICA_CIEGA_HUMANA_V1.md` citado en la tarea no existe en `frozen/` — se uso la rubrica perceptual congelada presente).
2. `ai_codifiers/claude/ORDER_CLAUDE.csv` (orden de presentacion).
3. `annotator_round1/renders/HB001..HB098.png` (98 renders DOM+tape 0–5 s).

No se consultaron mapping, fechas, outcomes, familias historicas, datos de trades, MAE, MFE, TP, SL, PnL, etiquetas humanas ni etiquetas Codex. No se entrenaron modelos. No se modificaron archivos existentes.
