# Posición de Claude — AMD-1 sin espera obligatoria

Fecha: 2026-07-24  
Objetivo: separar absorción limpia de breakout limpio con información causal
DOM+tape/MBO hasta `t_decision`, sin lookahead ni overfit.

## Dictamen

Claude acepta la objeción del usuario y retira su apoyo anterior a:

- repetir la clasificación con el mismo anotador después de siete días;
- usar la prohibición manual de abrir carpetas como una barrera causal.

Esas condiciones miden memoria y disciplina, no precedencia causal.

## Reemplazo propuesto

1. Mantener R1 y eliminar R2.
2. Clasificar inmediatamente los mismos 98 estímulos mediante tres
   codificaciones separadas: Eduardo, Claude y Codex.
3. Usar `Krippendorff alpha` nominal `>=0.60` como gate único de concordancia.
4. Mantener la representación congelada, el cutoff causal, `F_LAST`, hashes,
   anonimización y la rúbrica A/B/C.
5. Reemplazar prohibiciones manuales por controles verificables:
   allowlist de inputs, hashes, manifest y separación de procesos.
6. Sellar antes de revelar outcomes:
   - discovery: 2022–2023;
   - validation futura: 2024.
7. Ejecutar una sola prueba outcome preregistrada sobre discovery. Conservar
   2024 sin abrir para una futura regla/predictor.

## Aclaración

El acuerdo entre Eduardo, Claude y Codex mide si la rúbrica puede aplicarse de
forma operacionalmente concordante. No convierte a los tres codificadores en
una muestra independiente de la población ni demuestra capacidad predictiva.
La capacidad predictiva exige superar después el contraste outcome y la
validación temporal cerrada.

## Estado de R1

R1 sigue siendo utilizable porque la enmienda se realiza antes de comparar
etiquetas o abrir outcomes. La información mostrada, la rúbrica y el orden no
cambian.

