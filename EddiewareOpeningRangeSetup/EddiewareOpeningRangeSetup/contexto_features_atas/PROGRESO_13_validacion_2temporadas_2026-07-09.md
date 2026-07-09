# PROGRESO 13 — validación 2 temporadas: candidato muere, techo actual y bug imbalances (2026-07-09)

## Captura completada

| Temporada | Sesiones | LVNs | Eventos | Fallas |
|---|---:|---:|---:|---|
| DST 2026 (03-09 → 07-08) | 84 | 89 | 181 | 0 (13 reintentadas OK tras reabrir Replay) |
| DST 2025 (03-09 → 10-31) | 165 | 125 | 286 | 0 |
| **Banco total** | **249** | **214** | **467** | — |

Excels: `lvn_retest_DST_2026_full_v2.xlsx`, `lvn_retest_DST_2025.xlsx` (+ retry junio). Nada
se borra: regla de preservación activa.

## Validación del candidato de PROGRESO_12: MUERE out-of-sample

`ACCEPTANCE + LVN debajo del VAH ctx` (descubierto en 2026 parcial con n=33):

| Segmento | Año | n | tr/mes | WR% | PF |
|---|---|---:|---:|---:|---:|
| Candidato VAH | 2026 (in-sample ampliado) | 49 | 9.8 | 65.3 | 1.88 |
| Candidato VAH | **2025 (OOS)** | 98 | 12.2 | **55.1** | **1.23** |
| ACCEPTANCE crudo | 2025 | 119 | 14.9 | 58.0 | 1.38 |

En 2025 el filtro VAH ni siquiera mejora el crudo (55.1 vs 58.0): **overfit exploratorio,
descartado**. Matar barato — funcionó el proceso.

## Univariadas era-blind (umbrales de dev 2025, un solo test en 2026): también se desinflan

| Regla (ACC 80/80) | DEV 2025 | HOLDOUT 2026 |
|---|---|---|
| prob_trend_up ≤ 0.42 | 63.4% / PF 1.73 | 53.1% / PF 1.13 |
| retest ≤ 240s | 60.4% / PF 1.53 | 55.0% / PF 1.22 |
| ambas | 61.8% / PF 1.62 | 51.9% / PF 1.08 |

## CatBoost (dev 2025, holdout 2026 tocado UNA vez)

- AUC walk-forward interno dev: 0.529 / 0.494 (débil).
- AUC holdout: 0.587.
- Top-30% score en holdout: n=44 (8.8/mes), WR 61.4%, PF 1.59 — mejor que crudo, no llega a PF 2.
- Importancias top: aggression_delta_per_second, lvn_retest_delta, delta_touch_bar,
  prior_move_from_open_ticks — el flujo delta manda, coherente con order flow.

## Lo ESTABLE tras 2 temporadas (n=193 ACC resueltos 80/80)

ACCEPTANCE crudo: WR 54-58%, PF 1.18-1.38 en ambos años. La dirección H7 es real pero el
PF 2.0 del gate requiere más discriminación de la que estas features dan hoy.

## HALLAZGO TÉCNICO: imbalances rotos por granularidad

`buy/sell/net_imbalance_count = 0` en el 100% de los eventos. Causa: el footprint exporta
grid de 5 ticks (1.25) y `_imbalance_metrics` compara bid/ask diagonal asumiendo niveles de
1 tick — sobre niveles agregados de 5 ticks el ratio 3:1 nunca dispara. La feature que el
usuario pidió explícitamente ("imbalances para confirmar agresión") está ciega. Arreglos
posibles (pendiente): comparar diagonal sobre el grid nativo detectado (mismo fix que
level_step) y/o bajar el row size del chart a 1 tick en el template correcto de ATAS.

## Fases del proyecto (definidas por el usuario 2026-07-09)

| Fase | Qué | Estado |
|---|---|---|
| 1 | Captura multi-temporada (replay corto, banco de eventos) | 2025+2026 hechas; 2024 corriendo |
| **2 (ACTUAL)** | Descubrir el ADN de los ganadores (look-ahead + CatBoost + era-blind) | en curso |
| 3 | Simular cuenta Lucid $150k: máx 3 contratos (sizing según winrate), reglas de Lucid (MaxDD $4,500), medir tiempo-a-pasar vs probabilidad de quemarla (Monte Carlo de paths) | pendiente de que Fase 2 produzca un setup que pase gates |

Secuencia acordada al terminar 2024: reporte → gates 3 temporadas → CatBoost 3 temporadas
SOLO si algún segmento pasa gate → MD + Telegram.

## Decisión pendiente (gates NO pasan → el loop no autoriza escalar solo)

Opciones para el usuario:
1. **Lanzar DST 2024** igualmente: más n para descubrimiento + tercera temporada de
   validación (~6-7h replay). Argumento: el banco multi-año se necesita de todos modos.
2. Arreglar primero imbalances (grid nativo) + recapturar nada (es cálculo Python sobre CSVs
   existentes) y repetir el ciclo de ADN/CatBoost con la feature reparada.
3. Ambas: arreglar imbalances (rápido) y lanzar 2024 después.

Recomendación: opción 3 — el fix de imbalances es Python-only sobre data ya capturada
(barato), y 2024 corre en tiempo muerto.
