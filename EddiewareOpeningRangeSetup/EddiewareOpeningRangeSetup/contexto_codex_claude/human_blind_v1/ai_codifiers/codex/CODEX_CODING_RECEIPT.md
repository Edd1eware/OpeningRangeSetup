# Recibo de codificación independiente — Codex

Fecha de cierre: 2026-07-24

## Alcance

- 98 casos únicos codificados una sola vez.
- Orden de lectura: `ORDER_CODEX.csv`.
- Salida sellada: `CODEX_LABELS_98.csv`.
- Clases permitidas: A, B y C según la rúbrica congelada HUMAN BLIND V1.
- Codificador: CODEX.

## Distribución

- A: 35
- B: 37
- C: 26
- Total: 98

## Información utilizada

Únicamente se utilizaron:

- la rúbrica congelada;
- el orden aleatorio propio de Codex;
- los 98 renderizados PNG DOM+tape de 0 a 5 segundos.

No se consultaron fechas, sesión, contrato, lado real, familia histórica, resultado A/B/C, MFE, MAE, TP, SL, PnL, mapping sellado ni el archivo de etiquetas de Claude.

Codex declara que había inspeccionado técnicamente HB001, HB065 y HB098 antes del preregistro para comprobar la legibilidad del renderer, sin acceso al mapping ni al outcome. Esta limitación ya quedó declarada antes de comenzar en `CODEX_CODING_PREREG.md`.

## Regla de cierre

Las etiquetas se congelaron antes de abrir o validar la salida de Claude. Cualquier análisis de concordancia debe usar este archivo sin editarlo y reportar su SHA-256.
