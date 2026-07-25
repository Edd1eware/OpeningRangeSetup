# Solicitud de revisión independiente a Claude/Fable — ronda 001

Lee primero:

1. `README_GOBERNANZA_CODEX_CLAUDE.md`
2. `20260724_001_CODEX_CONTEXT.md`
3. `C:\Users\k_99_\Desktop\fmd_files\RUNBOOK_AB_ORB_NQ.md`
4. `C:\Users\k_99_\Desktop\fmd_files\PREREGISTRO_AB_ORB_NQ.md`
5. `..\contexto_features_atas\PREREGISTRO_NUEVO_ENFOQUE_AB_FMD_V1_20260724.md`

No confirmes por cortesía la propuesta de Codex. Audítala como investigador
adversarial.

## Preguntas

1. ¿Es correcto invalidar el Test Cero MFE/MAE porque A/B se construyen con
   Result_Label, MFE y MAE?
2. ¿El Gate Cero de desplazamiento durante el primer segundo posterior a
   `t_decision` responde una pregunta científicamente útil o es otra elección
   post hoc?
3. ¿Puede utilizarse la muestra estratificada de 100 sesiones para ese gate como
   discovery/stop rule, aunque no estime prevalencia ni calibración?
4. ¿Es defendible descargar tape uniforme de las 100 ventanas, o debe detenerse
   el proyecto antes de gastar más?
5. Evalúa exactamente el endpoint p0/p1, el horizonte de 1 segundo, el umbral de
   utilidad de 1 tick, MDE=2 ticks, bootstrap y permutación año/lado.
6. ¿Qué controles faltan antes de interpretar el gate?
7. Propón una decisión concreta:
   - `REANUDAR_DESCARGA`;
   - `MODIFICAR_DISEÑO_ANTES_DE_DESCARGAR`;
   - `DETENER_ESTA_LINEA`.
8. Si propones modificar, especifica una sola versión cerrada del diseño; no
   presentes un menú de experimentos.

La respuesta debe separar:

- acuerdos con Codex;
- desacuerdos;
- riesgos de lookahead/overfit;
- decisión recomendada;
- condiciones mínimas de convergencia.

No edites archivos ni ejecutes descargas.

