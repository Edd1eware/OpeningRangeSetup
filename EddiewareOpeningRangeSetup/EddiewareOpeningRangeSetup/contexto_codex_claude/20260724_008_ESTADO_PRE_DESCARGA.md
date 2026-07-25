# Estado previo a descarga — estudio conjunto A/B V4

## Completado

- Convergencia Codex–Claude/Fable sobre etiqueta independiente: V4.
- Diseño congelado SHA-256:
  `c1eb770c0d69b9d684fc60147a0cf9d9aa15fdd7d39eccb33e367f612c9a339c`.
- Calibración predecisión: PASS 12/12 gates.
- Sesiones: 98 válidas; rollovers incorrectos excluidos.
- Pseudo-ventanas: 3,533.
- Umbrales:
  - `T_push=T_ret=14 ticks`;
  - `T_ext=33 ticks`;
  - `T_dwA=0.671530336 s`;
  - `T_dwB=0.4535600705 s`.
- Cotización no billable:
  - trades: USD 2.822613001;
  - MBO: USD 5.755439754.
- Espacio libre: 100.57 GiB; reserva 10 GiB PASS.
- Convergencia de schema: MBO.

## Bloqueo autorizado

No se descargó nada. Falta autorización explícita del usuario para gastar como
máximo USD 5.755439754 en las 98 ventanas MBO de 5.1 segundos.

## Después de autorización

1. descarga resumible con reserva de 10 GiB;
2. auditoría F_LAST/sequence/F_MAYBE_BAD_BOOK/contrato/p0;
3. etiquetado A/B/C una sola vez;
4. gates de taxonomía y sensibilidad;
5. LOYO, bootstrap 10,000 y permutación 10,000;
6. revisión conjunta del resultado;
7. informe y gráfica a Telegram.
