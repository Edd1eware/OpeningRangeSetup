# Compromiso y objetivo de la fase de diseño de estrategia LVN

Congelado con el usuario: 2026-07-10.
Se activa SOLO si el paso 1 de `PASOS_A_SEGUIR_lvn_2026-07-10.md` (era-split del ranking
estructural) confirma estabilidad. Nada de estrategia antes de estar seguros con datos.

## Compromiso de trabajo

| Compromiso | Aplicación |
|---|---|
| **Máximo razonamiento, sin escatimar tokens** | Exploración exhaustiva del espacio de diseño: entrada (confirmación aceptación/rechazo), SL, TP/trailing, selección por ranking de extensión, tope de eventos/día, sizing 1-3 contratos, secuencia intradía |
| **Objetivo: maximizar WR + PF + frecuencia al máximo posible** | Con el matiz honesto: las tres pelean entre sí (filtrar sube WR/PF pero mata frecuencia). Se presentará la **frontera completa de combinaciones** — ej. "62%/1.6/12 tr-mes" vs "70%/2.2/6 tr-mes" — y el usuario elige el punto según el objetivo Lucid (pasar la cuenta rápido sin quemarla) |
| **Maximizar DENTRO de las reglas duras, no maquillando** | Era-blind; holdout 2026 = UNA sola mirada final; costos y slippage incluidos en todo número; AMBIGUOUS resuelto como peor caso (SL primero); cero optimización sobre la muestra de evaluación; desglose año×métrica obligatorio (nunca solo el total) |

## Objetivo final de la estrategia

Pasar la cuenta LucidPro EVAL $150k farmeando payouts:
target $9,000 (1,800t) | daily loss $2,700 (540t, soft) | max loss $4,500 (900t, EOD) |
máx 3 minis (sizing según WR). Métrica de éxito = distribución de días-a-pasar y P(quemar)
vía Monte Carlo con las reglas de la firma — no un PF bonito aislado.

## Referencia de partida (medido, no promesa)

Crudo breakeven; con ranking top-40% (subset con libro): WR 55-62%, PF 1.2-1.6 antes de
costos, ~10-12 tr/mes, MFE med top 150-165t, riesgo med winners 35-45t, RR operable
plausible 1.5-2.2:1 (supuesto de trailing NO probado). Detalle y caveats:
`PASOS_A_SEGUIR_lvn_2026-07-10.md`.
