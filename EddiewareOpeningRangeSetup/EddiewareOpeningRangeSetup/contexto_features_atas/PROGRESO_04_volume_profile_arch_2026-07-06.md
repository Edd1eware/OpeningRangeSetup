# Progreso 04 — Arquitectura Volume Profile (análisis vs ejecución) (2026-07-06)

Nuevo requerimiento: separar **ventana de análisis** (construye perfiles, congela a 09:29:59)
de **ventana de ejecución** (09:30+, solo usa los perfiles como referencia). Elimina lookahead:
las zonas (POC/VAH/VAL/HVN/LVN) representan info que un trader conocía ANTES de la señal.

---

## 1. Perfiles a construir (todos CONGELADOS a 09:29:59 NY)

| Perfil | Ventana NY | Métricas |
|---|---|---|
| PREOPEN_15m | 09:15:00–09:29:59 | POC, VAH, VAL, HVN(s), LVN(s), High, Low, Range |
| PREOPEN_30m | 09:00:00–09:29:59 | idem |
| PREOPEN_60m | 08:30:00–09:29:59 | idem |
| ON (overnight) | Globex start (18:00 ET prev) → 09:29:59 | ON_POC/VAH/VAL/HVN/LVN/High/Low |
| PD (prev day) | RTH previa 09:30–16:00 | PD_POC/VAH/VAL/HVN/LVN/High/Low |

Ejecución (en el breakout/slide bar): `distance_to_{PERFIL}_{POC|VAH|VAL|HVN|LVN}_ticks`,
`position_vs_{PREOPEN|ON|PD}_value_area`, `breakout_inside/outside_PREOPEN_value_area`,
`profile_confluence_count`.

---

## 2. Infra existente (reutilizar)

- `SessionContext.FinalizePrevSession(...)` ya construye un perfil PD **close-based** (crudo):
  bin = round(Close/tick) × Volumen, VA greedy 70%. Expuesto en `PrevPoc/Vah/Val`, `HasPrev`.
- `MarketProfileFeatures` + `DistanceFeatures` ya emiten `mp_*`, `dist_poc/vah/val`,
  `dist_prev_high/low`. **VERIFICADO poblado** en el CSV (06-26 dist_prev_close=-399, dist_poc=-362)
  → el chart **SÍ carga la historia (prev-RTH)** durante el featsweep.
- `BarData.Levels` (footprint por barra) disponible → base para VP real.

**El PD viejo (close-based) queda como LEGACY.** Los nuevos `PD_*` usan VP real (Levels).

---

## 3. Decisiones de diseño (fijadas con el usuario)

| Punto | Elegido |
|---|---|
| Fuente del perfil | **Footprint Levels** (volumen-a-precio real). Fallback a Close si una barra no trae niveles. |
| HVN/LVN | **Extremos locales** de histograma suavizado (~3 bins): HVN = máx local > media; LVN = mín local < media. |
| Salida HVN/LVN | **Más cercano** al precio (`distance_to_*_HVN/LVN_ticks`) + `profile_confluence_count`. Sin top-K (evita explosión de columnas). |
| ON Globex start | 18:00 ET (apertura CME NQ estándar). |

---

## 4. BLOQUEADOR pendiente — probe de datos (DLL 16:18)

Antes de construir ~300 líneas: ¿el featsweep replay carga barras **pre-open (08:30-09:29)**
y **overnight**, y traen **footprint Levels**? (Hoy el código las SKIPea; PD funciona pero
prev-RTH sí carga — pre-open/ON sin verificar.)

Probe temporal agregado a `FeatureScanner.cs` → escribe en `featscan_status_{fecha}.txt`:
```
probe_preopen_bars=<n> with_levels=<n>
probe_overnight_bars=<n> with_levels=<n>
probe_rth_bars=<n> with_levels=<n>
```

**ACCIÓN:** correr sanity `--limit 5 --force`, luego leer los status. Criterio:
- `preopen_bars>0 with_levels>0` **y** `overnight_bars>0 with_levels>0` → **build en C#**.
- Si bars>0 pero with_levels=0 → hay OHLC pero NO footprint → VP degradado a close-based, o mover a Python.
- Si bars=0 → el replay no carga esa historia → **offline Python** (como Track B).

---

## 5. Plan de build (post-probe, si data OK)

1. Nuevo módulo `VolumeProfile.cs`: `Add(BarData)` acumula Levels→dict(tickBin→vol);
   `Freeze()` calcula POC, VAH/VAL (greedy 70%), High/Low/Range, HVN/LVN (extremos locales
   sobre histograma suavizado). Fallback close cuando `Levels.Count==0`.
2. Holder de 5 perfiles + acumulación por ventana NY (manejo del cruce de medianoche para ON;
   evening 18:00-23:59 = fecha previa, overnight 00:00-09:29 = fecha target).
3. **Freeze a 09:29:59**: al llegar la 1ª barra RTH (tod>=09:30) del target, copiar a slots
   congelados; nunca recalcular después.
4. Nuevo `ProfileDistanceFeatures.Collect(...)`: ~40 features de distancia + position_vs_VA +
   breakout_inside/outside + confluence_count. Integrar en `BuildFeatureRow` (traded + slide).
5. Quitar el probe temporal.
6. Compilar, desplegar, sanity, validar sin lookahead (todos los perfiles idénticos en traded
   y slide de la misma fecha = congelados).

---

## 5b. BUILD A ejecutado (DLL 16:34) — Volume Profile en C#

Construido **sin esperar el probe** (degrada a NaN/legacy si pre-open/ON no cargan; PD sí carga).

- `features/VolumeProfile.cs`: POC, VA greedy 70% (expande desde POC al lado más rico),
  High/Low/Range, HVN/LVN = extremos locales de histograma suavizado 3-bins. Fuente footprint
  `BarData.Levels`, fallback close×vol. `CopyFrom` para congelar el builder live.
- Scanner: 5 perfiles live + 5 frozen. `AccumulateProfiles` (ventanas NY), `FreezeAnalysisProfiles`
  a las 09:30 (ON reset post-freeze; PD freeze en cambio de fecha; pre reset en cambio de fecha).
- `AddProfileFeatures` en `BuildFeatureRow` (traded + slide): `distance_to_{PREOPEN_15m|PREOPEN_30m|
  PREOPEN_60m|ON|PD}_{POC|VAH|VAL|HVN|LVN}_ticks`, `position_vs_*_value_area`,
  `profile_confluence_count` (POC/VAH/VAL ≤8t), `breakout_inside/outside_PREOPEN_value_area` (30m).
- Dibujo: `TrendLine` azul-magenta `Color.FromArgb(170,40,235)` (POC w3, VA w2, HVN/LVN w1),
  `TrendLines.Clear()` por fecha. Desde el **Feature Scanner** (NO se tocó 02_Visual_Logic ni el exec).
- Congelado a 09:30 = **sin lookahead** (breakout es 09:31+, perfiles ya fijos).

Pendiente validar en 1 sanity: profiles poblados (o NaN si data ausente), líneas en el chart,
columnas nuevas en el CSV, mismos valores de perfil en traded y slide de la misma fecha (= congelado).

## 6b. BUILD B ejecutado (DLL 16:37) — DOM overlay NARANJA (indicador aparte)

Nuevo indicador **`features/DomLevels.cs`** → DisplayName **"DOM Levels (orange)"**. Agregarlo
al chart aparte (no mezcla con el Feature Scanner).

- Libro live: `MarketDepthChanged(MarketDataArg)` acumula `price→size` (bids/asks); `Volume<=0`
  borra el nivel. `_lastNy` = última hora de depth.
- `OnRender`: línea **naranja** horizontal por nivel + label del **nº de contratos**;
  `RedrawChart()` en cada cambio → refresca al cambiar el tamaño.
- Gate horario configurable (default **09:30–09:50 NY**), solo dibuja dentro de la ventana.
- Params: `StartNy`, `EndNy`, `MinContracts` (filtro ruido), `ShowLabels`.
- **Live-only:** el replay NO reconstruye el libro → NO se ve en el featsweep, solo operando en
  vivo. (Coherente con `mbo_frozen_day4` / `atas_mbo_api_available`.)
- Overlay visual puro: NO genera features, NO toca exporter/scanner/exec/sync.
- Compila 0 errores (API render OFT.Rendering válida: RenderContext/RenderPen/RenderFont/
  Container.Region/GetYByPrice/SubscribeToDrawingEvents).

## 6. Estado

- Probe desplegado (DLL **16:18**). Diseño fijado. Build NO iniciado (espera datos).
- **Probe AÚN NO corrido:** los `featscan_status_*.txt` en disco NO tienen los campos
  `probe_*` → el DLL 16:18 no está cargado todavía. Falta **reiniciar ATAS** y correr el sanity.

### Cómo verificar el probe (acción pendiente)
```powershell
cd "C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup"
python -u 04_run_replay_featsweep_after_sync.py --limit 5 --force
```
Luego revisar cualquier `featscan_status_{fecha}.txt` — deben aparecer:
```
probe_preopen_bars=<n> with_levels=<n>
probe_overnight_bars=<n> with_levels=<n>
probe_rth_bars=<n> with_levels=<n>
```
Decisión según §4. Si no aparecen los campos `probe_*` → ATAS no recargó el DLL 16:18
(reiniciar ATAS antes de correr).

### Decisiones de diseño (ya fijadas, no re-preguntar)
| Punto | Elegido |
|---|---|
| Fuente perfil | Footprint Levels (VP real), fallback close |
| HVN/LVN | Extremos locales de histograma suavizado (~3 bins) |
| Salida HVN/LVN | Más cercano + `profile_confluence_count` |
| ON Globex start | 18:00 ET |
