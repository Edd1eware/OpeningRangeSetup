# Consenso Gemini-Codex: enmienda técnica de support masks F2

Fecha local: 2026-07-27  
Amendment ID: `PRE_LB_F2_SUPPORT_MASKS_W5_W30_V1`  
Estado: `APPROVED_BEFORE_ANY_REAL_F3_DATA`

## Omisión detectada

F2 V1 ya había prerregistrado estas comparaciones secundarias:

```text
M_ALL_W5_MINUS_M_ALL_W1_MATCHED_COMBINED_W5_SUPPORT
M_ALL_W30_MINUS_M_ALL_W5_MATCHED_COMBINED_W30_SUPPORT
```

Sin embargo, sólo definía y persistía `COMBINED_W1_SUPPORT`. No existían
definiciones explícitas para `COMBINED_W5_SUPPORT` ni
`COMBINED_W30_SUPPORT`. Codex la clasificó como inconsistencia bloqueante:
derivar esas muestras después de abrir labels habría dejado una decisión
metodológica sin congelar.

## Veredicto independiente de Gemini

Canal de contingencia: Gemini web, modo Flash-Lite, porque Gemini CLI devolvió
cuota diaria agotada. La consulta fue outcome-blind y no transmitió datos,
labels, outcomes ni resultados del estudio.

```text
GEMINI_F2_SUPPORT_AMENDMENT: APPROVE
```

Gemini coincidió en que:

1. la ausencia era una omisión estructural simétrica a W1;
2. completarla antes de datos reales no introduce lookahead;
3. las máscaras deben permanecer estrictamente como metadata;
4. config, documento y manifiesto deben rehashearse antes del freeze F3;
5. los tests añadidos de `PROFILE_F11` threshold/NaN y tape retention con
   mitad vacía/pseudoconteo `+1` cierran los gaps de su auditoría previa.

## Definiciones aprobadas

```text
COMBINED_W5_SUPPORT =
    BASELINE_SUPPORT
    & DOM_STATE_SUPPORT
    & DOM_W5_SUPPORT
    & PROFILE_F11_SUPPORT

COMBINED_W30_SUPPORT =
    BASELINE_SUPPORT
    & DOM_STATE_SUPPORT
    & DOM_W30_SUPPORT
    & PROFILE_F11_SUPPORT
```

Uso permitido:

- fijar la muestra matched del secundario W5;
- fijar la muestra matched del secundario W30;
- persistirse y hashearse outcome-blind.

Uso prohibido:

- predictor;
- filtro global;
- selección outcome-informed;
- rescate del primary o del parent V3;
- cambio de features, ventanas, modelos, gates o regla terminal.

## Integridad anterior a la enmienda

```text
F2 V1 config SHA256:
23C45992D5327F663A68B4DDC72914C19304309E87729A19E35A47C1366F9B63

F2 V1 MD SHA256:
0037B8247019CE6742693B0127F8E965F46D39AA65A9A2D009B5DEACF6364668

F2 V1 manifest SHA256:
84AE75B433D9FF5C416185EC188FC367CA68ECDE97904A09A3AA0A0B2F428A34
```

## Declaración Codex

Codex coincide con Gemini. Esta enmienda se adopta antes de generar cache,
piloto o matriz F3 real. A este punto:

```text
REAL_F3_DATA_OPENED=false
LABELS_OPENED=false
OUTCOMES_OPENED=false
MODELS_OPENED=false
VALIDATION_OPENED=false
HOLDOUT_OPENED=false
```

