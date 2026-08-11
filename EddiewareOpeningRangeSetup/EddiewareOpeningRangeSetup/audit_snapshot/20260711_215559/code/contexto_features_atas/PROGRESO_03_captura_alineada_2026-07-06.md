# Progreso 03 — Captura alineada X↔y (traded bus + slide) (2026-07-06)

Continuación de `PROGRESO_02_labels_intrabar_2026-07-06.md`. Arregla los dos huecos
de captura que se detectaron al validar el sanity de 5 fechas, **antes de escalar** a
la temporada completa (el replay es el cuello de botella, no se quiere reproducir 250
sesiones y descubrir el label roto).

Estado del dataset ATAS real: **5 fechas, 2 traded (06-26, 06-30), 3 no-trade**. Todo lo
demás (165 traded históricos) es **y-sin-X** hasta correr el replay por el Feature Scanner.

---

## 1. Bug A — mismatch entry scanner ↔ exporter (GRAVE) → ARREGLADO

**Causa raíz (no era un precio, eran eventos OPUESTOS):**

| campo | Exporter (score CSV) | Scanner (naive) |
|---|---|---|
| Side / dir | **SELL** (short) | **up** (long) |
| EntryTime | 09:33:14 | 09:31 (break_bar_sec=60) |
| or_low / or_high | 29292.5 / 29362.5 | 29292.5 / 29362.5 (igual) |
| Entry | 29250.00 (debajo OR low) | 29363.75 (arriba OR high) |
| Result | TP +60 | — |

06-26 rompió **ambos lados**. El scanner agarraba el **primer close-cross del OR sin filtros**
(UP 09:31). El exporter tradeó un **SHORT calificado** (09:33, con `MinBodyBreakoutTicks=10`
+ speed + score + lógica de lado). Distinto evento, distinta dirección → las features X **no**
describían el trade y. Inservible para ML.

**Fix:** el scanner deja de detectar su breakout naive. Ahora lee el
`ExecutionSignalBus` (canal estático en memoria, mismo assembly) que el exporter **ya publica**
en cada entrada (`Side`, `EntryPrice`, `Bar`). El scanner hace `Peek(fecha)` (NO `MarkConsumed`,
para no romper al Execution Manager) y captura features con **la dirección y el precio reales
del exporter**. Garantiza X↔y = mismo trade.

- `Side=BUY → up`, `Side=SELL → down`.
- `entry_price` de la fila = `pe.EntryPrice` (exporter), no el Close vivo del scanner.
- Forward MFE/MAE se miden desde el entry real.
- Intrabar preservado: `LiveBreakoutCheck` también hace `Peek` cada tick → entradas de TP
  instantáneo se capturan igual.

**Nota de cobertura:** el bus solo publica trades con **OR range ≥ 140** (FROZEN EXECUTION
FILTER, línea 455 del exporter). Ese es exactamente el universo que la estrategia congelada
tradea (165 trades 2022-2026). Días con trade registrado pero OR<140 no publican → no generan
fila traded (correcto: fuera del universo operado).

---

## 2. Bug B — no-trade sin datos → ARREGLADO con SLIDE (sliding causal)

**Hallazgo:** TIME_OVER = **NO trade** (el exporter no entra; EntryTime/Side/Entry vacíos).
El replay **sí reproduce la ventana completa** (~09:30→09:40) en esos días, así que el
forward-tracking NO se trunca (los mfe 40/26/20 del sanity eran reales). No hace falta
segunda pasada ni tocar el TP/SL del exporter congelado.

**Diseño elegido (decidido con el usuario):** snapshot **causal por barra** (sliding window),
capturar **todo** (movers y no-movers, para que CatBoost tenga contraste).

En cada barra post-OR (todos los días, traded o no):
1. Extiende el forward de todos los snapshots previos con el High/Low de la barra nueva.
2. Crea un snapshot causal nuevo anclado en el Close de la barra (X_t = solo pasado).
3. Reescribe el CSV completo (overwrite incremental → seguro ante corte del replay).

Labels forward por fila (ambos lados, sin look-ahead):
`fwd_mfe_up, fwd_mfe_dn, fwd_bars, hit40_up, hit40_dn, hit60_up, hit60_dn, first_hit40`.

Salida separada: **`features_slide_{fecha}_NY.csv`** — NO se mezcla con el traded para que
`y`-exporter y `y`-forward no se contaminen.

---

## 3. Salidas y esquema

| Archivo | Filas | X | y | capture_type |
|---|---|---|---|---|
| `features_scan_{fecha}_NY.csv` | 1/día (solo traded) | @ entry exporter | del exporter (merge) | `traded` |
| `features_slide_{fecha}_NY.csv` | N/día (todos) | @ cada barra (causal) | forward mfe/hit (self) | `slide` |

Columnas nuevas en ambos: `capture_type` (tras `break_dir`). Slide agrega los 8 forward.

**Al entrenar:** descartar SIEMPRE los labels viejos del scanner truncados
(`mfe_ticks, mae_ticks, bars_to_60, first_60_before_20adv, label_move60, label_whale,
whale_orderflow`). `y` traded = exporter (`result TP SL BE` / `MFE_ticks`). `y` slide = las
columnas `fwd_*`/`hit*`.

---

## 4. Cambios de código (`features/FeatureScanner.cs`)

- `using System.Text;`.
- Campo `_slideSnaps` + reset en `OnRecalculate` y en cambio de fecha.
- ProcessBar: detección naive → `TryBusEntry(...)` + `SlideStep(bd)`.
- `LiveBreakoutCheck`: close-cross → `TryBusEntry` (bus intrabar).
- Nuevo `TryBusEntry` (Peek del bus, dir+entry del exporter).
- `StartEvent`/`BuildFeatureRow`: firma con `captureType` + `entryPrice` override; nueva
  columna `capture_type`.
- Nuevos `SlideStep`, `WriteSlideRows`, `Fmt`, clase `SlideSnap`.
- **Exporter y sync-guards NO tocados.** Bus solo `Peek`.

---

## 5. Sanity 1 (DLL 15:08) — captura VALIDADA

Corrida `--limit 5 --force`. Fix A y B confirmados leyendo disco:

| fecha | traded (scan) | slide | nota |
|---|---|---|---|
| 06-26 | ✅ `down` / `29250` / `traded` | ✅ 2 filas | antes era up/29363 — mismatch MUERTO |
| 06-30 | ✅ `up` / `30116.25` | ❌ 0 filas | TP instantáneo 09:31, sin barra cerrada |
| 06-29 | — (no-trade) | ✅ 9 filas | forward coherente (mfeU=84/hit60=1) |
| 07-01 | — (no-trade) | ✅ 9 filas | |
| 07-02 | — (no-trade) | ✅ 9 filas | |

`entry_price` del scanner == `Entry_price` del score CSV **exacto** (06-26 29250, 06-30 30116.25).
Labels forward slide consistentes (hit flags ↔ mfe; `fwd_bars` decrece al avanzar `bar_sec` = causal).

**2 problemas detectados → arreglados (DLL 15:20):**

1. **Stale traded:** los `features_scan` de 06-29/07-01/07-02 del run VIEJO (14:xx, sin
   `capture_type`) persistían — el nuevo run correctamente no los sobrescribe (no-trade), pero
   quedaban en disco y el merge los tomaría como traded falso. Borrados a mano + fix de código.
2. **Slide 0 filas en instant-TP** (06-30): el replay corta antes de que cierre la 1ª barra
   post-OR → `SlideStep` (solo barras cerradas) no alcanza a crear snapshot.

---

## 6. Fixes #1 y #2 (DLL desplegado 2026-07-06 15:20)

| Fix | Implementación (`FeatureScanner.cs`) |
|---|---|
| **#1 stale** | `CleanDateSidecars(date)` en el cambio de fecha → borra `features_scan_{date}` y `features_slide_{date}` viejos al empezar la fecha (solo target gated). No-trade ya no hereda traded falso entre runs. |
| **#2 instant-TP** | Fallback en `TryBusEntry`: si `_slideSnaps` está vacío, captura 1 snapshot slide de la barra de entrada. Guardado a `Count==0` → días normales intactos (siguen con features de barra cerrada). |

Seguridad: `AddSlideSnapshot` dedup por índice de barra (`_slidBars`); `ExtendSlide` salta la
propia barra (`Bar < bd.Bar`) → el snapshot intrabar no se duplica ni cuenta su barra como forward.
Campos nuevos: `_slidBars` (HashSet), `SlideSnap.Bar`. Refactor: `SlideStep` → `ExtendSlide` +
`AddSlideSnapshot` + `InSlideWindow`. Exporter/sync-guards intactos. Compilación 0 errores.

---

## 7. NEXT STEP

1. **Reiniciar ATAS** para cargar el DLL **15:20** (Feature Scanner en chart 1m, OrMinutes=1,
   junto a `02_Visual_Logic` + exporter).
2. **Sanity 5 fechas** (confirmar #1 y #2):
   ```powershell
   cd "C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup"
   python -u 04_run_replay_featsweep_after_sync.py --limit 5 --force
   ```
   Verificación (se lee del disco):
   - **#2:** `features_slide_2026-06-30_NY.csv` ahora **existe** (≥1 fila fallback).
   - **#1:** no-trade days (06-29/07-01/07-02) **sin** `features_scan` (no stale), con `features_slide`.
   - Días normales: slide igual que antes (barra cerrada, no intrabar).
   - 06-26 traded sigue `down`/`29250`/`traded`.
3. Si alinea: **temporada DST completa** (quitar `--limit`) → ~250 sesiones, horas, X10.
4. Con n suficiente: **CatBoost + SHAP** para el ADN de los movimientos (traded y slide por
   separado; validación año×año, EV neto vs breakeven `SL/(TP+SL)`, CV purgado).

Pendiente aparte: cobertura EST (invierno) — hoy solo DST. Track B (libro/MBO) sigue
bloqueado por datos.
