# Tarea cerrada: codificación ciega de 98 secuencias

Codifica los 98 casos exactamente en el orden de `ORDER_CLAUDE.csv`.

## Únicos insumos permitidos

1. Rúbrica:
   `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\human_blind_v1\frozen\RUBRICA_CIEGA_HUMANA_V1.md`
2. Orden:
   `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\human_blind_v1\ai_codifiers\claude\ORDER_CLAUDE.csv`
3. Renders:
   `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\human_blind_v1\annotator_round1\renders`

No busques ni leas mapping, fechas, outcomes, familias históricas, datos de trades, MAE, MFE, TP, SL, PnL, etiquetas humanas ni etiquetas Codex.

## Regla

- Asigna A, B o C siguiendo literalmente la rúbrica.
- Ante duda entre A y B, usa C.
- No entrenes modelos.
- No cambies archivos existentes.
- No expliques caso por caso.

## Salidas obligatorias

Escribe únicamente:

1. `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\human_blind_v1\ai_codifiers\claude\CLAUDE_LABELS_98.csv`
   con esquema exacto `CaseID,label,coder,ordinal`, coder `CLAUDE`, 98 filas únicas y ordinal 1..98.
2. `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\contexto_codex_claude\human_blind_v1\ai_codifiers\claude\CLAUDE_CODING_RECEIPT.md`
   con conteos A/B/C, validación 98/98 y declaración de insumos usados.

En stdout informa solamente `CLAUDE_CODING_COMPLETE` o un error breve. No imprimas las etiquetas.
