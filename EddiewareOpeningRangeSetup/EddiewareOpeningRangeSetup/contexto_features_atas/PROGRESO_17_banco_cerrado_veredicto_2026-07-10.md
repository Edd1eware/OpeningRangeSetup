# PROGRESO 17 — banco 2022→2026 cerrado + veredicto CatBoost + opciones (2026-07-10)

## Banco final (0 fallas en toda la campaña)

| Tramo | Sesiones | Eventos |
|---|---:|---:|
| DST 2022 early (04-04→06-14) | 50 | 67 |
| DST 2022 mid (06-15→11-04) | 100 | 105 |
| DST 2023 | 165 | 193 |
| DST 2024 | 165 | 182 |
| DST 2025 | 165 | 286 |
| DST 2026 (→07-08) | 84 | 181 |
| **TOTAL** | **729** | **1,014** |

194 columnas/evento (Profile Feature Engine completo, reportes `_v4`). La frontera de datos
de replay NO se alcanzó ni en abril 2022 — hay más historia disponible si se quisiera.

## Medición shape × año (frecuencia, MFE med/p90 ticks) — SIN WR/PF

| Shape | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| unknown | 10.8/m 115/261 | 7.0/m 60/129 | 3.8/m 55/147 | 12.2/m 100/263 | 17.6/m 105/280 |
| trend_down | 5.1/m 105/324 | 8.0/m 75/185 | 7.4/m 80/158 | 10.0/m 70/305 | 6.0/m 85/235 |
| trend_up | 3.0/m 90/275 | 5.4/m 65/115 | 7.1/m 78/227 | 11.6/m 80/224 | 11.4/m 215/580 |
| double | 2.6/m 50/386 | 3.5/m 55/210 | 3.6/m 62/140 | 1.8/m 98/175 | 1.2/m 370/452 |
| D | 0 | 0.2/m | 0.9/m | 0.1/m | 0 |

Estable multi-año: el evento existe SIEMPRE (~21-28 ev/mes), MFE mediana 55-115t según
año/régimen. La extensión es real; su dirección/resultado no es predecible (abajo).

## Lente Lucid (daily 540t soft, total 900t EOD, máx 3 minis)

| Shape | MAE evento med/p90 | Riesgo real winners ≥80t (med/p90) | días con MAE agregada >540t |
|---|---|---|---|
| double | 78/212t | **25/73t** | 7/27 |
| trend_down | 70/272t | 35/135t | 20/61 |
| unknown | 85/288t | 45/130t | 26/75 |
| trend_up | 105/336t | 45/278t | 21/73 |

Tomar TODOS los eventos sin filtro rompería el daily 1 de cada 3 días → cualquier ejecución
requiere selección + SL + tope de eventos/día.

## VEREDICTO CatBoost (dev 2022+2023+2024 = 547 eventos → val 2025 = 286; holdout 2026 INTACTO)

| Objetivo | AUC val |
|---|---:|
| win 20/20 | 0.464 |
| win 40/40 | 0.499 |
| win 60/60 | 0.428 |
| win 80/80 | 0.449 |
| MFE continua (R²) | 0.003 |

**Con footprint 1-min / grid 5-tick y 69 features causales, el resultado del retest NO es
predecible en ningún tamaño de winner (AUC ≈ azar o peor), con n=833 y 3 años de dev.**
El ranking de importancias apunta consistente a delta flow pre-entrada y pendientes
VWAP/EMA, pero sin poder de generalización. Esto NO es un fallo del proceso: es la
respuesta de la Fase 2 con esta granularidad de datos.

## Opciones (para decidir con el usuario)

A) **Gestión, no predicción**: aceptar entrada no-selectiva en subgrupos (ej. double) y
   buscar el edge en la asimetría MFE/riesgo con trailing — PERO el crudo con SL fijo ya
   midió PF ~0.8-1.2, margen estrecho; alta probabilidad de ser espejismo de selección.
B) **Data más fina (recomendada si se sigue con LVN)**: el bloqueo es la granularidad.
   Ya existe `raw_dbn_2` ohlcv-1s de sesión completa (1,029 días, memoria del proyecto):
   reconstruir retests con timing 1s (elimina AMBIGUOUS y el conservador next-bar) y/o
   capturar delta intrabar fino / MBO (BookRecorder listo). Costo: pipeline nuevo de merge.
C) **Matar/pausar la hipótesis LVN-minuto-1** (doctrina: matar barato) y redirigir las horas
   al pipeline con setups ya congelados (OR-CB F8/F9, ATRAPADOS port ATAS).
D) **Redefinir el evento**: LVN del perfil premarket completo (no minuto 1), ventana de
   retest más larga, o retest de LVN multi-día.

El banco de 1,014 eventos con 194 features queda como activo permanente para cualquier
opción — la fábrica es el activo, no el setup.
