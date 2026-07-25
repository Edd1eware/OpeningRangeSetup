# Convergencia Claude–Codex — HUMAN_BLIND_V1 AMD-1

Fecha: 2026-07-24

## Decisión conjunta

Claude y Codex aceptan la corrección del usuario:

- no habrá espera de siete días;
- no habrá R2 del mismo anotador;
- no se utilizará una prohibición manual de abrir archivos como prueba de
  causalidad;
- R1 continúa hoy.

La concordancia se medirá mediante tres codificaciones separadas e inmediatas
de los mismos 98 renders: Eduardo, Claude y Codex. El gate preregistrado es
`Krippendorff alpha nominal >=0.60`.

La causalidad se sostiene por el cutoff, la allowlist, el renderer sin outcomes
y las auditorías de precedencia. El overfit se controla con un solo endpoint,
una sola ejecución y el split temporal sellado antes de revelar outcomes:

- discovery 2022–2023: 69 casos;
- validation 2024: 29 casos.

## Limitación explícita

La concordancia de tres codificadores comprueba que la rúbrica puede aplicarse
de forma operacionalmente reproducible. No demuestra por sí sola que las
etiquetas predigan el movimiento ni que los codificadores sean una muestra
independiente de la población.

## Evidencia congelada

- Enmienda: `human_blind_v1/frozen/HUMAN_BLIND_V1_AMD1.md`
- Split: `human_blind_v1/admin_sealed/SPLIT_TEMPORAL_AMD1.csv`
- SHA-256 split:
  `862e7041d7d4cd3ad2aa3588f7eeafa504e1b3b76cfd4f87b88f4dc2d0f8f664`
- Commit aislado:
  `2ab16c32a12a433bd24bd67b6e6c50ff803ba276`
- Tag:
  `humanblind-v1.1`

## Próximo paso

1. Eduardo termina R1 sin esperar días.
2. Claude y Codex congelan sus CSV separados.
3. Se calcula alpha y los gates descriptivos.
4. Sólo si pasan, se abre discovery para la prueba outcome única.
5. Validation 2024 permanece cerrada para una futura regla/predictor.

