# HUMAN_BLIND_V1 — R1 lista para etiquetado

Fecha: 2026-07-24  
Estado: `READY_FOR_USER_ACK`

## Resultado de la auditoría previa

- 98/98 secuencias DOM+tape renderizadas.
- 12/12 puertas técnicas aprobadas.
- Máxima saturación visual: 4.149%, por debajo del límite preregistrado de 5%.
- PNG sin metadatos identificadores y con fecha de modificación uniforme.
- Orden R1 reproducible y congelado antes del primer render real.
- Mapeo de identidades fuera del árbol accesible al anotador.
- Interfaz totalmente local y sin llamadas de red.
- La interfaz exige aceptar el compromiso de cegamiento antes del primer caso.
- No se crearon etiquetas.
- No se entrenó ningún modelo.
- No se utilizaron MFE, MAE, TP, SL, PnL ni resultado.

## Archivos

- Interfaz R1:
  `human_blind_v1/annotator_round1/annotator_round1.html`
- Auditoría:
  `human_blind_v1/audit/PRE_R1_AUDIT.json`
- Estadísticas de render:
  `human_blind_v1/audit/RENDER_STATS_98.csv`
- Instrucciones y carpeta de recepción:
  `human_blind_v1/round1_submission/INSTRUCCIONES_R1.md`

## Acción del usuario

Etiquetar los 98 casos como A, B o C y exportar:

`human_blind_v1/round1_submission/HUMAN_BLIND_V1_ROUND1_LABELS.csv`

La carpeta `admin_sealed` no debe abrirse durante R1. La ronda R2 permanece cerrada durante un mínimo de siete días después de completar R1.

Las instrucciones fueron enviadas mediante un mensaje persistente de Telegram.

