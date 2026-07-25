# Gobernanza compartida Codex–Claude

Vigente desde: 2026-07-24  
Proyecto: separación causal de absorción limpia frente a breakout limpio en
Liquidity Burst ORB NQ.

## Regla del usuario

Codex no decide unilateralmente el rumbo metodológico. Antes de una decisión
importante, Codex y Claude/Fable deben revisar la misma evidencia, exponer sus
desacuerdos y llegar a un punto de convergencia documentado.

## Decisiones que exigen convergencia previa

- cambiar la definición A/B/C;
- cambiar endpoint, horizonte, cutoff o universo;
- agregar, eliminar o transformar familias de predictores;
- modificar gates, umbrales o validación;
- descargar datos con costo;
- abrir 2025–2026;
- lanzar ATAS o repetir un replay;
- interpretar un resultado como éxito, refutación o autorización para ampliar;
- elegir el siguiente experimento.

## Flujo obligatorio

1. `CODEX_CONTEXT`: evidencia, propuesta y dudas de Codex.
2. `QUESTION_FOR_CLAUDE`: pregunta simétrica, sin pedir confirmación.
3. `CLAUDE_RESPONSE`: respuesta íntegra de Claude/Fable.
4. `CODEX_REVIEW`: acuerdos, objeciones y evidencia adicional.
5. Si persiste desacuerdo, una segunda ronda con la objeción exacta.
6. `CONVERGENCE_DECISION`: decisión común, límites y condiciones de paro.
7. Sólo entonces se ejecuta; si implica costo o autoridad nueva, también se
   solicita autorización del usuario.

## Trazabilidad

- Nunca se sobrescriben contextos anteriores.
- Cada ronda usa fecha y número secuencial.
- Los cambios post hoc se rotulan.
- Si no existe convergencia, la acción importante permanece detenida.

