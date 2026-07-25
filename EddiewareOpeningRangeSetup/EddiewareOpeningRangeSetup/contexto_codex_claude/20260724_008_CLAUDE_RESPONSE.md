# Ronda 008 — dictamen de schema

## Decisión: `mbo`

Tres razones, dos de ellas de protocolo, no de costo:

1. **V4 exige verificar completitud del Match Event, no asumirla.** `trades` no garantiza el registro no-T que porta `F_LAST`; agrupar por `ts_event` apoyándose en la regularidad 21,225/21,225 convierte una puerta de integridad congelada en una suposición empírica extrapolada a 98 ventanas nuevas. Relajar el protocolo justo antes de observar etiquetas es exactamente el patrón que las siete rondas anteriores eliminaron.
2. **Simetría pseudo/real (V4, punto 7).** El pool de calibración se procesó desde MBO con delimitación por evento físico y `F_LAST`. Etiquetar las ventanas reales con `trades` aplicaría una regla de agrupación distinta en el lado que decide A/B/C — asimetría metodológica que rompe la cancelación de sesgos de convención en los percentiles.
3. **Costo**: sobrecosto USD 2.93 total. Irrelevante frente al costo de una etiqueta indefendible; además `F_MAYBE_BAD_BOOK` y `sequence` completos quedan disponibles para el `INTEGRITY_FAIL` ya congelado.

Acepto también el punto de Codex sobre el snapshot: irrelevante para 5.1 s de outcome, porque solo se consumen T-events y fronteras `F_LAST`, sin reconstrucción de libro.

Condiciones sin cambio: descarga solo tras autorización explícita del usuario por el costo MBO exacto (USD 5.755439754, 98 sesiones); etiqueta, umbrales, horizonte y gates intactos; doble decodificación SHA-256, sincronía de reloj ≤2 ticks en `p0` y contrato por sesión vigentes.

`CONVERGENCIA_SCHEMA_MBO`
