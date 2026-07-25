# AMD-2 FAIL y posición Claude para AMD-3

Fecha: 2026-07-25  
Outcomes abiertos al producir este documento: ninguno.

## Resultado AMD-2

Gate congelado:

```text
denominador = 62 etiquetas consenso original A/B
flip = A/B cambia de dirección o pasa a C
PASS = flip_rate <= 10%
```

Resultado:

- flips = 9/62;
- flip rate = 14.516%;
- veredicto AMD-2 = FAIL.

El FAIL es final y no se redefine el endpoint después del resultado.

## Hallazgo secundario

Transiciones:

- A→A: 20;
- A→C: 7;
- B→B: 33;
- B→C: 2;
- C→A: 7;
- C→C: 29;
- A↔B: 0.

Toda la inestabilidad estuvo en la frontera C/abstención. La dirección de los 53 casos A/B retenidos fue idéntica 53/53.

## Posición de Claude

Claude considera legítimo crear AMD-3 antes de outcomes:

```text
A = consenso original A AND consenso perturbación 1 A
B = consenso original B AND consenso perturbación 1 B
C = todo lo demás
```

Distribución AMD-3:

- A = 20;
- B = 33;
- C = 45.

Esto no convierte AMD-2 en éxito. AMD-3 es una nueva regla outcome-blind seleccionada por estabilidad perceptual y su discovery deberá rotularse exploratorio-preregistrado.

Claude exige una segunda perturbación cosmética independiente para evitar declarar estabilidad por construcción. Sólo si el núcleo AMD-3 cambia <=10% se permite abrir una vez discovery 2022–2023.

## Límites

- Seleccionar usando etiquetas ciegas X sin ver outcome Y no introduce lookahead.
- Sí introduce multiplicidad de reglas perceptuales; se registra explícitamente.
- Validation 2024 es la única evidencia confirmatoria futura.
