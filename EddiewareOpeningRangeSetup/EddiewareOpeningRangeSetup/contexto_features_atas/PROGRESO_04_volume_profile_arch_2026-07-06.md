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

## 6. Estado

- Probe desplegado (DLL 16:18). **Pendiente: correr sanity + leer probe_* → decidir C# vs Python.**
- Diseño fijado. Build NO iniciado (espera confirmación de datos).
