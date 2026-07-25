# Claude Fable — revisión cerrada HUMAN_BLIND_V1

Fecha: 2026-07-24  
Estado: `APPROVE` automático al aplicar las cinco correcciones

## Correcciones exigidas y aceptadas por Codex

1. Heatmap: `log1p(depth)` normalizado al percentil 99 del propio caso; cap
   en p99. No usar `depth/Q0` con cap `8*Q0`.
2. Tape y tamaño de marcadores: normalizar al máximo del propio caso para no
   filtrar régimen/año por magnitud absoluta.
3. Rúbrica: `durable` significa sostenido hasta el estado terminal visible
   de la ventana, `t=5.00s`.
4. PNG: eliminar metadata y uniformar `mtime`; nombre sólo `CaseID`.
5. HTML: completamente offline; mapping administrativo fuera del árbol del
   anotador. Una vez etiquetado un caso no se permite retroceder.

## Seeds congeladas

- Ronda 1: `104729`.
- Ronda 2: `1299709`.
- Generador: `numpy.random.default_rng(seed).permutation(98)`.
- Ronda 2: mismos CaseID, orden nuevo, no antes de siete días después de
  completar Ronda 1.

## Conclusión

No se detectó lookahead estructural: el precio y tape dentro de los cinco
segundos pertenecen al instrumento-outcome. Queda prohibido cualquier dato
posterior a `cutoff+5s` y cualquier outcome terminal derivado de la operación.

Claude Fable y Codex convergen en la especificación que incorpora literalmente
estas correcciones.

