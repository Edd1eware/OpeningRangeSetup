# PROGRESO 18 — Informe de decisión: valor incremental del order flow (2026-07-10)

Protocolo: `targets_mbo_incremental_2026-07-10.md`. Eventos idénticos (267 con grabaciones
MBP+tape, 113 fechas 2023-2026), Modelo A estructural (69 features) vs Modelo B = A + 25 de
flujo. Evaluación out-of-fold GroupKFold por fecha, corte fijo top-40%, sin optimización,
holdout 2026 del banco grande intacto.

## Resultado A vs B

| Bracket | Modelo | AUC | WR top40% | PF top40% | MAE winners med |
|---|---|---:|---:|---:|---:|
| 40/40 (n=176) | A | 0.608 | 54.9% | 1.22 | 45t |
| 40/40 | **B** | **0.649** | **62.0%** | **1.63** | **35t** |
| 80/80 (n=185) | A | 0.593 | 54.1% | 1.18 | 65t |
| 80/80 | B | 0.626 | 52.7% | 1.11 | 68t |

## Tabla por grupo de flujo (marginal A+grupo vs A)

| Grupo | 40/40: ΔAUC / ΔPF / ΔWR | 80/80: ΔAUC / ΔPF / ΔWR | Veredicto |
|---|---|---|---|
| **profundidad_liquidez** | **+0.056 / +0.51 / +8.5%** | +0.010 / 0 / 0 | **MANTENER** — el grupo estrella |
| agresion_delta | +0.014 / +0.23 / +4.2% | +0.029 / +0.07 / +1.4% | Marginal-útil (único positivo en ambos) |
| velocidad | −0.006 / 0 / 0 | +0.051 / 0 / 0 | Marginal (solo AUC en 80) |
| refill | −0.007 / +0.07 / +1.4% | +0.009 / 0 / 0 | No aporta |
| absorcion (proxy) | −0.005 / 0 / 0 | −0.000 / −0.12 / −2.7% | No aporta |
| cancelacion (proxy) | −0.008 / −0.07 / −1.4% | +0.013 / −0.06 / −1.4% | No aporta |

Lectura: el valor del flujo se concentra en **profundidad/liquidez** (resting bid/ask, liquidez
removida, niveles vaciados) + algo de **agresión/delta**. Refill/absorción/cancelación como
PROXIES desde MBP no aportan — justo las que el MBO real (orden-por-orden) mediría bien.

## INFORME DE DECISIÓN (criterios congelados antes de ver resultados)

| Campo | Valor |
|---|---|
| **¿Comprar Databento 5 años ahora?** | **TODAVÍA NO** |
| Nivel de confianza del hallazgo positivo | **MEDIO** en 40/40; BAJO en 80/80 |
| Mejora absoluta 40/40 | PF +0.41 (1.22→1.63), WR +7.1pp, MAE winners −10t, AUC +0.041 |
| Mejora relativa 40/40 | PF +34%, WR +13% |
| Mejora 80/80 | AUC +0.033 pero PF −0.07 → NO se traduce a trades mejores |
| Qué aporta | profundidad_liquidez >> agresion_delta; el resto nada como proxy |
| Estimación 1→5 años | n≈267→~1,300: intervalos ±½; si ΔPF≈+0.4 se sostiene, sería concluyente |

Razón del "todavía no" (criterio congelado: mejora clara Y CONSISTENTE): clara en 40/40,
inconsistente entre brackets, n=176 con CV (no era-split — 2026 solo tiene 21 fechas
grabadas, insuficiente para validación temporal limpia dentro del subset).

## Camino barato antes de gastar (recomendado)

1. **El BookRecorder graba gratis** en cada replay: recapturar con grabación activa las
   fechas del banco que NO tienen libro (2022, 2024 casi entero: solo 9 fechas grabadas)
   → duplica-triplica n sin comprar nada.
2. Repetir este A/B con n≥500 y era-split real (dev hasta 2025 / val 2026).
3. Si profundidad_liquidez sostiene ΔPF ≥ +0.3 consistente → comprar SSD + Databento
   MBO 5 años, sabiendo exactamente qué explotar: profundidad del libro y delta, no
   refill/icebergs.

## Nota metodológica

El baseline A en este subset (AUC ~0.60) luce mejor que en el banco completo (0.45-0.50).
Sesgos: cobertura concentrada en 2025-2026, CV-por-fecha en vez de era-split estricto, n
chico. NO leerlo como "el estructural ya predice"; leerlo como comparación INTERNA A vs B
sobre datos idénticos — para eso fue diseñado el experimento.
