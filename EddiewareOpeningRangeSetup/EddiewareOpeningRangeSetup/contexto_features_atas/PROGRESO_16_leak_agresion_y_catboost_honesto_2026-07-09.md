# PROGRESO 16 — leak en features de agresión + CatBoost honesto multi-tamaño (2026-07-09)

## Contexto

Usuario define la tarea crítica de CatBoost: sacar el ADN de los ganadores sin importar su
tamaño (chicos y grandes). Se rediseñó `catboost_lvn_dna.py`: 5 objetivos (winners 20/40/60/80t
+ regresión de MFE continua), ADN = rank medio de importancias entre objetivos, era-blind
paramétrico (dev/val/holdout separados; holdout solo con flag explícito, una mirada).

## HALLAZGO 1: leak en las features de "agresión durante el episodio"

Primer smoke test dio AUC 0.89 (win_20) — demasiado bueno. Causa: `time_inside_lvn_zone_seconds`,
`aggression_volume/delta_per_second`, `tape_speed_trades_per_second` y `lvn_retest_*` se
calculaban sobre el episodio COMPLETO del retest (touch → último toque antes de re-arm), que
puede extenderse DESPUÉS de la confirmación de entrada. El modelo veía flujo posterior a la
entrada: un ganador rápido sale de la zona rápido → dwell corto → predicción mecánica.

**Fix**: nuevas features causales `pre_entry_*` (volume/delta/tape/lvn_delta/lvn_volume por
segundo) calculadas SOLO en la ventana touch→confirmación. Las de episodio completo quedan en
el dataset como descriptivas pero EXCLUIDAS de la whitelist del modelo. Reportes de 2022mid/
2024/2025 regenerados (`*_v3`) con las columnas nuevas — sin recapturar (Python-only).

Lección para el pipeline: toda feature "durante el retest" debe cortarse en la confirmación.
Ya son causales: approach/zone speed, deceleration, seconds_touch_to_entry, delta del bar del
touch (conocido al cierre de esa barra = momento de confirmación).

## HALLAZGO 2: CatBoost honesto = sin señal OOS con el banco parcial

dev 2022mid+2024 (287 eventos) → val 2025 (286), 69 features causales:

| Objetivo | n dev | AUC val |
|---|---:|---:|
| win 20/20 | 125 | 0.531 |
| win 40/40 | 227 | 0.533 |
| win 60/60 | 242 | 0.453 |
| win 80/80 | 232 | 0.446 |
| MFE (R² log) | 270 | -0.02 |

ADN ranking (consistente aunque sin poder predictivo aún): delta flow pre-entrada
(`pre_entry_delta_per_second`, `delta_change_touch_bar`, `delta_touch_bar`), pendientes
EMA/VWAP, `min_entropy`, `distance_to_vwap_ticks`, volatilidad realizada.

Lectura honesta: con footprint 1-min/grid 5-tick y ~290 eventos de dev, no hay ADN que
generalice de 2022+2024 a 2025. NO es la conclusión final: falta el banco completo
(+2023 +2022early ≈ n~1,000, dev de 3 años). Esa corrida es la última bala con ESTAS
features; si tampoco separa, las palancas siguientes son de DATOS, no de modelo:
granularidad fina (1s/tick, delta intrabar) o replantear el evento.

## Regla adicional del usuario (congelada para F3/F4)

En la estrategia probada en replay es CRÍTICO diferenciar cuál objetivo tocó primero (SL o
TP) cuando ambos caen en la misma vela. Estado: el motor ya marca `AMBIGUOUS` y nunca
resuelve por suposición; en simulación F3 los AMBIGUOUS se estresan como peor caso (SL
primero); en ejecución ATAS se resolverá con granularidad 1s/tick o se contará aparte.

## Estado

- Cadena de captura 2022-early → 2023 corriendo (cierre del banco 2022→2026).
- Al terminar: regenerar TODO con feature engine completo → CatBoost multi-tamaño final
  (dev 2022-2024, val 2025; holdout 2026 se gasta solo con decisión explícita) → opciones
  Lucid por Telegram.
