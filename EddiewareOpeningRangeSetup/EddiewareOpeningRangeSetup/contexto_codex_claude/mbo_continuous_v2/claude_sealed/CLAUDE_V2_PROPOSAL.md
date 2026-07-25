# Propuesta Claude — V2 score mecánico continuo defensa–aceptación

Fecha: 2026-07-25
Autor: Claude Fable (propuesta independiente, sellada por hash antes de ver la de Codex)
Estado: PROPUESTA — no congelada; la especificación final sale de la convergencia Claude+Codex.

---

## 0. Alcance y datos

- Población: los mismos 98 casos (BurstId) del experimento ciego, MBO snapshot Databento.
- Ventana causal: `[strict_feature_cutoff, cutoff + 5s)` por `ts_recv`.
- Un paquete se aplica únicamente al llegar `F_LAST`; si `F_LAST` cae en o después del límite derecho, el paquete completo se excluye.
- Orientación canónica: dirección del ataque = positiva. SELL espejado. Así, **aceptación/breakout → signo positivo; defensa/absorción → signo negativo**.
- Prohibido: MFE, MAE, TP, SL, PnL, Result_Label, etiquetas AMD, mapping, outcomes.
- Normalización y calibración: SOLO con inputs discovery 2022–2023 y/o pseudoventanas predecisión (outcome-blind). 2024 congelado.

## 1. Componentes (8), ecuaciones y signos

Notación: `L0` = nivel atacado (BBO MBO en `t_burst`); `p(t)` = mid/BBO canónico en ticks relativos a L0, orientado (positivo = más allá de L0 en dirección del ataque); `T = 5s`; `Q0` = profundidad inicial defensora en L0.

| # | Nombre | Ecuación | Signo teórico |
|---|---|---|---|
| 1 | `acc_time_frac` | (1/T) ∫ 1[p(t) > 0] dt | + |
| 2 | `term_disp` | p(T⁻) — último valor antes del límite derecho | + |
| 3 | `signed_area` | (1/T) ∫ p(t) dt | + |
| 4 | `hold_terminal` | duración del último estado (aceptado o no) / T, con signo del estado final | + |
| 5 | `fill_q0` | contratos ejecutados contra la cola defensora L0 / Q0, cap 3.0 | + |
| 6 | `refill_ratio` | volumen repuesto en L0 lado defensor (adds+mods entrantes) tras el primer fill / max(fills L0, 1) | − |
| 7 | `net_adds_def` | (adds − cancels) lado defensor L0:L2 durante agresión / Q0 | − |
| 8 | `tape_align` | (vol agresor alineado − vol counterflow) / (suma), misma fuente MBO | + |

Excluyo deliberadamente: conteo de reclaims como componente separado (redundante con 1, 3 y 4; n de eventos es inestable en 5 s), y supervivencia por identidad de orden (dejarlo para V3 si V2 falla; complejidad alta, riesgo de bugs silenciosos).

## 2. Normalización y faltantes

- Cada componente → z robusto: `z_k = (x_k − mediana_k) / (1.4826·MAD_k)`, winsorizado a ±3.
- Mediana/MAD calculadas EXCLUSIVAMENTE sobre **pseudoventanas predecisión** de discovery 2022–2023 (mismo mecanismo que la calibración ciega V5: ventanas físicas de 5 s anteriores al cutoff, sin outcome). Congeladas antes de tocar los 98 casos.
- Faltante (componente no computable, p. ej. Q0=0 o sin fills): el componente se excluye del promedio y penaliza `Q_cobertura`; nunca se imputa 0.

## 3. Score y cobertura

```text
S_defensa_aceptacion = mean( s_k · z_k )  sobre componentes disponibles
  donde s_k ∈ {+1, −1} es el signo teórico de la tabla.

Q_cobertura = (componentes disponibles / 8) × (tiempo de ventana cubierto por paquetes completos / T)
```

- Pesos iguales. Cero optimización contra outcomes o etiquetas AMD.
- Banda neutra: `|S| ≤ b`, con `b` = percentil 25 de `|S|` sobre las pseudoventanas predecisión de discovery. Es tolerancia numérica, no clase.
- Cobertura mínima para caso evaluable: `Q_cobertura ≥ 0.75` y ≥ 6 componentes.

## 4. Calibración sintética (antes de estabilidad)

Generar secuencias sintéticas deterministas de comportamiento conocido (absorción pura: fills sin desplazamiento + refill alto; breakout puro: depleción + desplazamiento sostenido; ruido plano). Gate sanidad: el score debe ordenarlas correctamente (breakout > ruido > absorción) en 10/10 casos sintéticos por tipo. Si falla, corregir bug de implementación — esto NO usa datos reales ni outcomes.

## 5. Puerta de estabilidad outcome-blind (V2-4)

Perturbaciones (solo representación, nunca semántica):

- P1: re-muestreo temporal 50 ms → 25 ms y → 100 ms;
- P2: redondeo de tamaños a múltiplos de 1 lote donde aplique;
- P3: orden alternativo determinista de paquetes con mismo `ts_recv`;
- P4: reconstrucción equivalente desde snapshot+incrementales re-empalmados.

Gates congelados (todos deben pasar, sobre los 98 casos):

| Gate | Umbral |
|---|---|
| Spearman rank corr S original vs perturbado | ≥ 0.90 en cada perturbación |
| Cambios de signo fuera de banda neutra | ≤ 5% de casos evaluables |
| Error absoluto mediano normalizado `mediana(|ΔS|)/IQR(S)` | ≤ 0.15 |
| Casos evaluables (cobertura) | ≥ 90% de 98 |

FAIL → no abrir outcomes; documentar causa; rediseñar con estímulos sintéticos nuevos. No re-perturbar hasta lograr PASS casual.

## 6. Endpoint discovery único (V2-5)

Un solo endpoint continuo, preregistrado antes de abrir cualquier outcome:

```text
endpoint = Spearman rho( S, D_norm ) en discovery 2022–2023 (n=69)
  D_norm = desplazamiento futuro firmado normalizado por OR_ticks,
           orientado igual que S (aceptación positiva), ventana outcome
           idéntica a la ya congelada en el diseño previo.
incertidumbre = block bootstrap por sesión, 10,000 réplicas, IC95%.
éxito = IC95% excluye 0 Y rho ≥ 0.35.
```

- Un solo número, una sola apertura. Sin colas, sin subgrupos, sin segundo intento.
- Definición exacta de `D_norm` (horizonte y fuente) debe cerrarse en convergencia — única pieza que dejo abierta a Codex porque el outcome congelado previo era MFE/OR y hay que elegir su análogo firmado sin introducir elección post hoc.

## 7. Condición para abrir 2024 (V2-6)

Solo si discovery PASS exacto: aplicar fórmula, normalización, banda, cobertura y endpoint sin ningún cambio a 2024 (n=29), una sola vez. Exigir mismo signo de rho, IC95 excluye 0, y consistencia BUY/SELL (mismo signo de rho en ambos lados). Si 2024 falla → NO VALIDADO, línea cerrada sin recalibrar.

---

Fin de propuesta. Hash de este archivo publicado en `20260725_036_QUESTION_FOR_CODEX_V2_PROPOSAL.md` antes de recibir la propuesta de Codex.
