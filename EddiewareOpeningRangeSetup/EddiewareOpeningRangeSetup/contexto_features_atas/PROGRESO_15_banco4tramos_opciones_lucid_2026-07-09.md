# PROGRESO 15 — banco 4 tramos completo + opciones con lente Lucid $150k (2026-07-09)

## Captura terminada (0 fallas en toda la cadena)

| Tramo | Sesiones | LVNs | Eventos |
|---|---:|---:|---:|
| DST 2022 mid (06-15→11-04) | 100 | 42 | 105 |
| DST 2024 | 165 | 76 | 182 |
| DST 2025 | 165 | 125 | 286 |
| DST 2026 (03-09→07-08) | 84 | 89 | 181 |
| **TOTAL** | **514** | **332** | **754** |

**2022 SÍ tiene datos de replay** — la frontera real está más atrás de 2022-06-15 (sin mapear).
Gap pendiente: DST 2023 completa y DST 2022 temprana (mar–jun).

## Medición por shape × año (frecuencia + MFE mediana/p90, SIN WR/PF)

| Shape | 2022m | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| unknown | 8.2/m, 68/175t | 3.8/m, 55/147t | 12.2/m, 100/263t | 17.6/m, 105/280t |
| trend_up | 3.3/m, 70/292t | 7.1/m, 78/227t | 11.6/m, 80/224t | 11.4/m, 215/580t |
| trend_down | 3.8/m, 160/320t | 7.4/m, 80/158t | 10.0/m, 70/305t | 6.0/m, 85/235t |
| double | 2.2/m, 112/371t | 3.6/m, 62/140t | 1.8/m, 98/175t | 1.2/m, 370/452t |
| D | 0 | 0.9/m, 88/222t | 0.1/m | 0 |
| P/b puros | 0 | 0 | 0 | 0 |

Global: 27.9 eventos/mes; **14.3/mes alcanzan ≥80 ticks de extensión** (51% de los eventos).

## Lente Lucid $150k (MaxDD $4,500 = 900 ticks NQ @$5; máx 3 contratos)

**Dejar correr sin SL es inviable**: MAE por evento p90 300-408t y peores días acumulan
1,120–9,675t. Cualquier ejecución viable REQUIERE stop definido.

**Riesgo real que necesitaron los eventos que SÍ llegaron a 80t** (`mae_before_mfe`):

| Shape | n≥80t | MAE-antes-MFE med | p75 | p90 |
|---|---:|---:|---:|---:|
| double | 33 | **25t** | 50t | **74t** |
| unknown | 133 | 45t | 90t | 128t |
| trend_down | 99 | 50t | 82t | 160t |
| trend_up | 117 | 50t | 110t | **314t** |

## Opciones (medición → para decidir diseño; NO es estrategia aún)

1. **SL estructural ~50-55t**: cubre la mediana del riesgo de todos los grupos. Aritmética
   Lucid: 1 SL con 3c = ~165t (~$825) → el buffer de 900t aguanta ~5 SL seguidos a 3c,
   ~11 a 1-2c. Sugiere escalado de contratos por colchón ganado (como el kill dinámico
   validado en el proyecto OR).
2. **double = mejor perfil riesgo/extensión** (riesgo med 25t, p90 74t; MFE med 62–370t)
   pero raro (1.2–3.6/mes) → capa premium, no base.
3. **unknown + trend_down = el volumen operable** (riesgo med 45-50t, frecuencia 10-18/mes
   combinados, MFE med 55-160t).
4. **trend_up = cola peligrosa** (p90 del riesgo 314t): o se evita o SL duro sin excepciones;
   su MFE 2026 (215t med) es anómala/regimen-dependiente.
5. **Completar el banco**: DST 2023 + DST 2022 temprana (~5h de replay) → banco continuo
   2022→2026 y mapa de la frontera real de datos.

## Reglas Lucid 150k Pro Eval CONFIRMADAS (2026-07-09, vía reviews; la página bloquea fetch)

| Regla | Valor | Ticks NQ |
|---|---|---|
| Profit target | $9,000 | 1,800t |
| Daily Loss Limit | $2,700 — SOFT breach (pausa el día) | 540t |
| Max Loss | $4,500 — drawdown **EOD** | 900t |
| Sizing | 10 minis (proyecto usa máx 3) | — |
| Consistencia / días mín | ninguna / ninguno | — |

Implicación clave para F3: intradía solo mata el daily (540t); el total 900t se evalúa al
CIERRE → la estrategia puede tolerar MAE intradía si el día cierra dentro del presupuesto.

## Corrida lanzada: cierre del banco 2022→2026 (pedido usuario)

Cadena en 2 tramos (robustez: cada fecha es atómica CSV+marker; relanzar salta completas):
1. DST 2022 temprana: 2022-04-04 → 2022-06-14
2. DST 2023 completa: 2023-03-13 → 2023-11-03
Feriados US/CME auto-excluidos. Si 2022-early topa frontera de datos, aborta ese tramo tras
6 fallas×3 intentos y la cadena continúa con 2023.

## Telegram por fecha enriquecido (pedido usuario)

Cada fecha ahora manda: barra de progreso, % y ETA total (con hora estimada de fin), filas,
intentos, shape contextual, interacciones, RR max alcanzable (prom/max/min) y el DETALLE POR
LVN: precio, ancho en ticks, volumen del nivel, profundidad, si tuvo retest y su MFE máxima.
Ejemplo real (2026-07-07):
`LVN 29616.25 | ancho 5t | vol 11 | prof 0.51 | RETEST MFEmax 465t`

## Profile Feature Engine (idea del usuario, implementada 2026-07-09)

Cada evento ahora genera ~120+ features numéricas (187 columnas totales en `LVN_Events`):
- Contexto: distancias LVN→POC/VAH/VAL/Open/OR/VWAP (ya existían) + **Open→POC/VAH/VAL** y
  **distancia al HVN principal** (nuevas).
- Forma (contexto Y minuto como features del evento): skewness, kurtosis, entropía,
  # distribuciones, separación/profundidad de valle doble, width, VA width, posiciones de
  POC/centro de masa, volume slope, shares upper/lower, probs de shape.
- Estructura: **# HVN, # LVN, dominancia del HVN principal** (nuevas).
- Micro: volumen total y delta (contexto + minuto), delta del nodo, delta touch/change,
  velocidad (approach/zone/tape), big trades. Imbalances ciegos (grid 5t, opcional).
  Refill/consumo: NO disponibles — requieren DOM/MBO (BookRecorder existe, captura futura).
- Temporal: hora del retest, **día de la semana** (nueva), tiempo en zona, retest #.

Flujo acordado: al cerrar el banco 2022→2026, regenerar reportes por temporada con
`--report-only` (Python-only, sin recapturar — las columnas nuevas se calculan retro desde
los CSV crudos) y correr CatBoost sobre el set completo para obtener el top ~12 de variables
que separan los días buenos de los malos (dev 2022-2024 → val 2025 → holdout 2026).

## Pendiente del usuario

- Confirmar reglas EXACTAS de Lucid $150k: ¿DD diario? ¿trailing o EOD? ¿$4,500 es trailing
  máximo total? — necesarias para la simulación formal de Fase 3 (tiempo-a-pasar vs P(quemar)
  con 1/2/3 contratos).
- Decidir si lanzo 2023 + 2022 temprana para cerrar el banco.
