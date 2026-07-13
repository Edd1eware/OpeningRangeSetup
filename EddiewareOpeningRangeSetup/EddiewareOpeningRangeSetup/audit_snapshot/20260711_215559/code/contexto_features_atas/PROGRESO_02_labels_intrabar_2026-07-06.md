# Progreso 02 — Labels, captura intrabar y plan de run (2026-07-06)

Continuación de `PROGRESO_SESION_2026-07-06.md`. Cubre lo que salió al validar las
primeras corridas de features y las decisiones para el dataset de CatBoost.

---

## 1. Resultado de las corridas de prueba (semana 06-26 → 07-02)

| Iteración | Fechas con features | Nota |
|---|---|---|
| Inicial (OrMinutes=5) | 2/5 | solo TIME_OVER (07-01, 07-02) |
| OrMinutes=1 | 4/5 | rescató 06-26, 06-29; faltó 06-30 |
| + intrabar (fix A) | objetivo 5/5 | pendiente confirmar |

06-30 (TP BUY 09:31:08) se perdía: breakout instantáneo justo tras bloquear OR; el
replay paraba antes de que cerrara la barra 09:31.

---

## 2. HALLAZGO CRÍTICO — el label del scanner está truncado

El scanner calcula `mfe_ticks` / `label_move60` con forward-tracking DESPUÉS del breakout.
Pero el replay **para cuando el exporter cierra el trade** (TP rápido) → sin barras hacia
adelante → `mfe=0`, `label_move60=0` aunque el trade **sí movió 60 ticks**.

Evidencia (semana de prueba):

| fecha | exporter | scanner mfe_ticks | scanner label_move60 |
|---|---|---|---|
| 06-26 | **TP (+60)** | **0** ❌ | **0** ❌ |
| 06-29 | TIME_OVER | 40 | 0 |
| 07-01 | TIME_OVER | 26 | 0 |
| 07-02 | TIME_OVER | 20 | 0 |

El único mover real (06-26) quedó etiquetado 0. **Nunca entrenar con el label del scanner.**

### Decisión: el label viene del EXPORTER, no del scanner
| Rol | Fuente | Columnas |
|---|---|---|
| **X (features @ breakout)** | Feature Scanner | las 269 (`mx_*`, `dist_*`, `imbalance_*`, `deltacore_*`...) |
| **y (outcome real)** | Exporter (score CSV) | `Result_Label`, `result TP SL BE`, `MFE_ticks` |

El merge del runner ya pone ambos en la misma fila por `fecha`. Al entrenar:
- **Descartar** del scanner: `mfe_ticks, mae_ticks, bars_to_60, first_60_before_20adv,
  label_move60, label_whale, whale_orderflow` (truncados/look-ahead).
- Definir `y` con el exporter, p.ej. `MFE_ticks >= 60` o `result TP SL BE == "+60"`.

---

## 3. Fix A — captura intrabar (desplegado DLL 13:56)

`FeatureScanner.cs` → `LiveBreakoutCheck(bar)`:
- Corre en la barra EN FORMACIÓN cada tick (no solo al cierre).
- Bloquea el OR por **tiempo** apenas pasa `orEnd` (no espera al cierre de la barra).
- Detecta el cruce de OR en vivo → captura features + escribe al instante (`EmitPendingRow`).
- Sin doble-conteo: `_eventDone` hace que la lógica de cierre lo salte.
- `StartEvent`/`BuildFeatureRow` refactorizados para aceptar `(session, i)` y usar la barra
  en formación como última barra del contexto.

Efecto colateral (aceptado): las features se capturan en el **momento del cruce** (intrabar),
más alineado con la entrada real del exporter. Mismo criterio para todos los días.

---

## 4. Cobertura temporal del runner — SOLO DST (UTC-4)

`DST_SEASONS`:
```
(2025-03-10 → 2025-10-31)   # EDT
(2026-03-09 → 2026-10-30)   # EDT
```
Meses de invierno (EST / UTC-5) **NO** incluidos. Pendiente: agregar temporadas EST para año
completo, con cuidado del **DST anchor gotcha** (mapeo de la ventana 09:30 NY según offset).
Por ahora la temporada DST completa sirve como test (la más larga disponible).

---

## 5. Plan de run

1. Reiniciar ATAS (DLL 13:56) + "Feature Scanner" en chart (OrMinutes=1).
2. Sanity 5 fechas: `python -u 04_run_replay_featsweep_after_sync.py --limit 5 --force`
   → confirmar **5/5** (06-30 presente).
3. Temporada DST completa: `python -u 04_run_replay_featsweep_after_sync.py --force`
   (~250 sesiones, varias horas, X10, no tocar foco).

Verificación post-run (se lee del disco, no hace falta pegar texto):
- `features_scan_*.csv` por fecha (276 cols) en `trade_results_score`.
- `featscan_status_*.txt` con `wrote_features_row=1`.
- Excel `Score_indicator_results_updated_2025_2026.xlsx` con score + features mergeados.

---

## 6. Análisis CatBoost (cuando haya n suficiente)

Objetivo: **ADN de los trades que mueven ≥60 ticks** (perfilado, no predicción a ciegas).

| Punto | |
|---|---|
| Target de "calidad" | preferir `first_60_before_20adv` (del exporter) o `MFE/MAE` alto = Big Whale limpio |
| Método | CatBoost + **SHAP** + top-decil vs resto + partial dependence + ablación |
| Validación | CV purgado/embargo (`metalabel_timeline_cpcv.py`), OOS estricto, estabilidad año×año, EV neto vs breakeven `SL/(TP+SL)` |
| Expectativa | features son Track A (consecuencia); evidencia previa PF 1.2–1.6. El salto real está en Track B (liquidez/MBO), aún bloqueado por datos |
| Reporte | año × métrica (trades, WR, PF, EV neto), nunca solo el total |

---

## 7. Estado de despliegues (esta sesión, cronológico)

| Hora | DLL |
|---|---|
| 12:25 | balance Telegram |
| 12:57 | finalize 09:48 |
| 13:08 | heartbeat |
| 13:24 | escritura incremental por barra |
| 13:34 | OrMinutes=1 |
| **13:56** | **captura intrabar (fix A)** — vigente |
