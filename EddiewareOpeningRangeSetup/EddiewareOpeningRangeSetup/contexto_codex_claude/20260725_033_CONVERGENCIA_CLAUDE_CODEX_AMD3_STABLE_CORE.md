# Convergencia Claude–Codex — AMD-3 Stable Core

Fecha: 2026-07-25  
Estado informativo: outcomes y mapping todavía cerrados.

## Acuerdo

Claude y Codex conservan:

- FAIL AMD-1 de concordancia humano–IA;
- FAIL AMD-2 de estabilidad A/B→C;
- cero inversiones direccionales A↔B como hallazgo secundario;
- exclusión operativa del coder humano por instrucción del usuario.

Se crea AMD-3 usando sólo el núcleo estable en dos presentaciones:

```text
original A + perturbación 1 A -> A
original B + perturbación 1 B -> B
cualquier otro caso -> C
```

Distribución:

- A=20;
- B=33;
- C=45;
- cobertura A+B=53/98=54.08%.

## Perturbación 2

La segunda presentación usa los mismos PNG causales originales con:

- rotación global de hue distinta;
- padding distinto;
- sin resize, crop ni flip temporal/espacial;
- órdenes Claude/Codex nuevos;
- codificadores frescos sin acceso a etiquetas previas.

Endpoint:

```text
denominador = 53 casos AMD-3 A/B
flip = nueva etiqueta consenso difiere de AMD-3 o pasa a C
PASS = flip_rate <=10%
```

La segunda perturbación no puede agregar casos C al denominador primario.

## Decisión

- FAIL: cerrar representación; no abrir outcome.
- PASS: ejecutar una única prueba discovery 2022–2023.

Endpoint outcome sin cambios:

```text
delta = E[MFE_ticks/OR_ticks]_A - E[MFE_ticks/OR_ticks]_B
bootstrap por sesión = 10,000
PASS = IC95% excluye 0 AND |delta| >=0.25
```

Discovery AMD-3 será exploratorio-preregistrado. Sólo validation 2024 puede aportar confirmación. 2025–2026 permanece cerrado.
