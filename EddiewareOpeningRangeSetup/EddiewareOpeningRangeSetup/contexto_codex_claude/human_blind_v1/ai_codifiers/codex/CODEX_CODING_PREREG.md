# Codificación Codex — prerregistro

Fecha: 2026-07-24  
Protocolo: `HUMAN_BLIND_V1_AMD1`

- Casos: 98.
- Rúbrica: `frozen/RUBRICA_PERCEPTUAL_V1.md`.
- Inputs visuales: únicamente `annotator_round1/renders/HBxxx.png`.
- Orden: Fisher–Yates con `System.Random(32452843)`.
- SHA-256 de `ORDER_CODEX.csv`:
  `c1ea0a3653cefbcb8987a980c27fcf5113e3f29e74990b3d8c5274c35c7a4343`.
- No consultar mapping, fechas, sides originales, split, outcomes ni etiquetas
  de Eduardo o Claude antes de congelar `CODEX_LABELS_98.csv`.
- Clasificación: A, B o C; ante duda entre A y B se asigna C.
- No revisar decisiones anteriores después de avanzar.

El hecho de que Codex haya realizado anteriormente una inspección técnica de
tres renders (`HB001`, `HB065`, `HB098`) queda declarado. No se conoció su
mapping ni outcome. Esta exposición limita la independencia perfecta, pero no
aporta la clase correcta de esos casos.

