# Convergencia Claude–Codex — AMD-2 Consenso IA

Fecha: 2026-07-25  
Estado informativo al congelar: labels ciegas disponibles; mapping/outcomes no abiertos para esta decisión.

## Directiva del usuario

El usuario ordenó:

- utilizar el acuerdo Claude–Codex de 83.7%;
- ignorar sus etiquetas humanas para la clasificación operativa;
- proceder sin esperar días.

Las etiquetas humanas se preservan como auditoría, pero no participan en la regla ni en la prueba outcome.

## Registro obligatorio de AMD-1

AMD-1 no pasó:

- alpha Eduardo+Claude+Codex = 0.4396;
- umbral = 0.60.

Este fallo no se borra. Demuestra que la rúbrica V1 no fue reproducible entre humano e IA.

## Evidencia que habilita AMD-2

- Claude–Codex: 82/98 coincidencias = 83.67%.
- Cohen kappa = 0.7538.
- Alpha nominal = 0.7546.
- En los casos donde ambos dieron una clase limpia A/B: dirección idéntica 62/62.

Esto demuestra reproducibilidad entre los dos codificadores IA, no capacidad predictiva.

## Regla operacional congelada

```text
CLAUDE=A y CODEX=A -> A
CLAUDE=B y CODEX=B -> B
cualquier otra combinación -> C/ABSTENCION
```

Distribución antes de outcome:

- A = 27;
- B = 35;
- C/abstención = 36;
- A entre A+B = 43.55%;
- B entre A+B = 56.45%;
- C = 36.73%.

## Gate de estabilidad previo a outcome

Se crean renders cosméticamente perturbados utilizando exclusivamente los PNG causales existentes. No se añaden, eliminan ni reordenan eventos.

- orden nuevo por codificador;
- paleta alternativa determinista;
- pequeño desplazamiento/padding de canvas;
- sin mapping, fechas ni outcome.

Claude y un Codex de contexto fresco recodifican 98/98.

Endpoint único:

```text
flip_rate_AB_consensus <= 10%
```

Se compara la etiqueta consenso original A/B contra la nueva etiqueta consenso:

- sólo A/A o B/B son clasificables;
- desacuerdo vuelve a C;
- un cambio A<->B o A/B->C cuenta como flip;
- C original no puede incorporarse post hoc al denominador primario.

Falla: representación cerrada; no abrir outcome.  
Pasa: ejecutar una única prueba discovery 2022–2023 con el endpoint ya congelado en AMD-1.

## Outcome posterior, si estabilidad pasa

```text
delta = E[MFE_ticks/OR_ticks]_A - E[MFE_ticks/OR_ticks]_B
bootstrap = bloque por sesión, 10,000 réplicas
éxito = IC95% excluye 0 AND |delta| >= 0.25
```

2024 permanece cerrado. No se ajustan etiquetas, rúbrica, endpoint ni umbral después de abrir discovery.
