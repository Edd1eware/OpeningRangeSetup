# Auditoría del estado vigente de quote en smoke

Fecha: 2026-07-27

Alcance: cinco sesiones `TECHNICAL_DEVELOPMENT_SET`, 111 LB.

La reconstrucción independiente reprodujo
111/111 referencias históricas.

Resultado:

- aceptación anterior: 111/111;
- aceptación con estado vigente válido:
  106/111;
- falsas aceptaciones por estado vigente inválido:
  5.

No se recalcularon clases de régimen en esta medición y no se abrió ninguna
etiqueta no-smoke.

`INFORMATION_STATUS=QUOTE_STATE_SMOKE_IMPACT_MEASURED`
