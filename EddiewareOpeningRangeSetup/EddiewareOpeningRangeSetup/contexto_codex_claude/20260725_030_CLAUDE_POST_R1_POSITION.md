# Posición Claude posterior a R1 — HUMAN_BLIND_V1

Fecha: 2026-07-25  
Información disponible: etiquetas ciegas y concordancia; outcomes todavía cerrados.

## Diagnóstico de Claude

- AMD-1 falla y el fallo debe conservarse: alpha nominal de tres codificadores = 0.4396 frente a 0.60.
- Claude–Codex sí muestra reproducibilidad operacional:
  - acuerdo exacto 82/98 = 83.67%;
  - Cohen kappa = 0.7538;
  - alpha nominal de dos codificadores = 0.7546;
  - cuando ambos eligieron A/B, coincidieron en la dirección 62/62.
- La discrepancia humano–IA está dominada por la frontera C:
  - 26/37 discrepancias contra consenso IA involucran C;
  - 11/37 son inversión A/B.
- El acuerdo IA no prueba corrección ni capacidad predictiva; puede existir sesgo compartido entre modelos.

## Posición

Claude considera legítimo usar el consenso Claude–Codex como clasificador operativo sólo si:

1. se congela una AMD-2 antes de abrir outcomes;
2. el fallo de tres codificadores queda como limitación permanente;
3. A exige A/A y B exige B/B;
4. cualquier desacuerdo pasa a C/abstención;
5. se ejecuta antes un test inmediato de estabilidad ante perturbaciones cosméticas informacionalmente equivalentes;
6. el flip rate de etiquetas consenso A/B es <=10%;
7. sólo si pasa se ejecuta una vez el endpoint discovery 2022–2023 ya congelado;
8. 2024 permanece cerrado hasta que discovery pase.

## Opciones descartadas

- No usar mayoría 2/3: ocultaría que la mayoría está dominada por el par IA.
- No adjudicar discrepancias después de conocer los estadísticos.
- No borrar ni reinterpretar el fallo AMD-1.
- No corregir rúbrica con outcomes.

## Condición de cierre

Si la perturbación cambia más de 10% de las etiquetas A/B de consenso, se cierra esta representación y no se abre outcome. Si es estable, se permite una única prueba discovery con:

`delta = E[MFE_ticks/OR_ticks]_A - E[MFE_ticks/OR_ticks]_B`

Éxito:

- IC95% block bootstrap por sesión, 10,000 réplicas, excluye cero;
- `|delta| >= 0.25`.
