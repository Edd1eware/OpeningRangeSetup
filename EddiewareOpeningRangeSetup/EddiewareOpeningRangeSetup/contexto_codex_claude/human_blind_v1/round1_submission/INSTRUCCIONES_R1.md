# HUMAN_BLIND_V1 — entrega de etiquetas R1

1. Abrir localmente:
   `..\annotator_round1\annotator_round1.html`
2. Leer y aceptar el compromiso de cegamiento mostrado por la interfaz.
3. Clasificar las 98 secuencias como:
   - `A`: absorción limpia.
   - `B`: breakout limpio.
   - `C`: mixta, débil, ambigua o insuficiente.
4. Basar cada decisión únicamente en la secuencia causal mostrada. La separación
   de outcomes se verifica mediante el pipeline, la allowlist y hashes; no
   depende de una prohibición personal de abrir carpetas.
5. No regresar a casos anteriores ni cambiar una decisión después de avanzar.
6. Al terminar, exportar el CSV desde la interfaz y guardarlo en esta carpeta con el nombre:
   `HUMAN_BLIND_V1_ROUND1_LABELS.csv`

AMD-1 elimina la ronda R2 y cualquier espera obligatoria. Claude y Codex
realizarán codificaciones separadas e inmediatas sin conocer la clasificación
del usuario.
