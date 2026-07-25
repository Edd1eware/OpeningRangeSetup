# Claude/Fable — conclusión ronda 002

## Objeciones de Codex

| Objeción | Veredicto de Claude |
|---|---|
| Gate v2 optimizaba entrada confirmada tras 1 s y contradice el objetivo predictivo | Aceptada. Canal reactivo no equivale a separar antes del movimiento |
| Reemplazar etiqueta terminal por primera secuencia OR a 5 s | Aceptada con corrección. Etiqueta post-decisión corta y predictores estrictamente predecisión |
| Umbrales 4 ticks interior, 8 exterior y dwell 500 ms | Rechazados por considerarlos números elegidos a mano y sin anclaje empírico |

Claude aclaró que no pudo leer el archivo de revisión durante esa llamada porque
se deshabilitaron las herramientas; respondió al resumen incluido en el prompt.

## Etiqueta propuesta

Calibrar en seis sesiones técnicas, mediante pseudo-eventos:

- breakout limpio: extensión exterior al borde OR al menos igual al P90 del
  desplazamiento absoluto a cinco segundos;
- absorción limpia: reingreso a la OR, desplazamiento no mayor que P50 y dwell
  exterior no mayor que P50;
- C: resto.

Los percentiles deben congelarse antes de etiquetar las 100 sesiones.

## Decisión propuesta por Claude

`ETIQUETA_MECANICA_5S_SIN_DESCARGA`

Abandonar A/B terminal, calibrar en seis sesiones, etiquetar 100 y después
comparar predictores predecisión mediante LOYO, bootstrap y permutación.

## Reglas de paro

- Jaccard menor que 0.70 ante ±15%.
- Una clase limpia menor que 15% de eventos.
- BA LOYO con límite inferior no superior a 0.50 y p>0.05.
- Cualquier predictor que toque `t_decision` o eventos posteriores.
- Esta reestructura consume la revisión única.

