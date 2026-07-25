# Solicitud de posición Claude — fallo de concordancia HUMAN_BLIND_V1 AMD-1

El objetivo del proyecto es separar causalmente ABSORCIÓN LIMPIA de BREAKOUT LIMPIO después de un Liquidity Burst, sin lookahead ni overfit.

Antes de decidir un cambio importante, Claude y Codex deben dialogar y converger. No abras mapping, fechas ni outcomes. Usa únicamente:

1. `frozen/RUBRICA_PERCEPTUAL_V1.md`
2. `frozen/HUMAN_BLIND_V1_AMD1.md`
3. `ai_codifiers/agreement/EDUARDO_CLAUDE_CODEX_AGREEMENT.json`

## Resultado ciego observado

- n = 98.
- Krippendorff alpha nominal de Eduardo+Claude+Codex = 0.4396; puerta 0.60: FAIL.
- Unanimidad: 45/98.
- Mayoría 2 de 3: 95/98.
- Todos diferentes: 3/98.
- Eduardo vs Claude: 52.04%, kappa 0.2767.
- Eduardo vs Codex: 53.06%, kappa 0.2842.
- Claude vs Codex: 83.67%, kappa 0.7538.
- Cuando Claude y Codex ambos eligieron A/B, coincidieron en la dirección 62/62.
- Entre los 82 casos donde Claude y Codex coincidieron, Eduardo coincidió en 45 y discrepó en 37.
- Confusión de Eduardo contra consenso IA en esos 82:
  - A/A 15, A/B 6, A/C 8
  - B/A 5, B/B 23, B/C 5
  - C/A 7, C/B 6, C/C 7
- En casos donde ambos miembros del par eligieron A/B:
  - Eduardo vs Claude: 42/55 = 76.36%.
  - Eduardo vs Codex: 45/57 = 78.95%.

No se abrió outcome y no debe abrirse durante este diagnóstico.

## Directiva posterior del usuario

El usuario ordenó explícitamente: usar la coincidencia Claude–Codex de 83.7%, ignorar sus propias etiquetas para la clasificación operativa y proceder. Sus etiquetas se preservan sólo como auditoría. La respuesta debe diseñar la forma causal y transparente de usar exclusivamente Claude–Codex, conservando el fallo del panel de tres como limitación y sin reinterpretar resultados después de abrir outcomes.

## Preguntas

1. ¿Qué demuestra y qué no demuestra este patrón?
2. ¿El problema principal parece ser la frontera C, una inversión conceptual A/B humana, la visualización o una combinación?
3. ¿Debe mantenerse el FAIL preregistrado sin outcome? Responde sí/no y por qué.
4. Propón el siguiente experimento inmediato y reproducible, sin esperar días, que no reutilice outcomes para corregir la rúbrica.
5. Decide si es legítimo:
   - aceptar mayoría 2/3 ahora;
   - aceptar consenso Claude+Codex ahora;
   - adjudicar discrepancias;
   - rediseñar renderer/rúbrica y repetir;
   - o cerrar esta representación perceptual.
6. Define una condición de salida objetiva que acerque al objetivo predictivo sin post hoc.

Entrega una posición firme y concisa. No escribas ni modifiques archivos; responde por stdout.
