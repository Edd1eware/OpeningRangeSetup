# Progreso sesión — Barrido de features ATAS (2026-07-06)

Objetivo: lograr que el **Feature Scanner** exporte `features_scan_*.csv` durante el
replay y se mergeen al Excel, más limpieza de nombres, balance en Telegram y arreglo del
cuelgue del runner. **Resultado: pipeline funcionando end-to-end.**

---

## 1. Estado final

| Item | Estado |
|---|---|
| Features exportadas (`features_scan_{fecha}_NY.csv`, 276 cols) | ✅ |
| Merge de features al Excel del runner | ✅ |
| Balance corrido en Telegram (arranca $150,000) | ✅ |
| Cuelgue del replay (pywinauto) | ✅ resuelto |
| Escritura de la fila de features | ✅ resuelto (incremental) |
| Alineación de OR scanner ↔ exporter | ✅ `OrMinutes=1` |

Pendiente operativo: reiniciar ATAS con el DLL nuevo y correr `--limit 5 --force` para
confirmar **5/5 fechas** con features; luego escalar quitando `--limit`.

---

## 2. Arquitectura (2 tracks de features)

Las specs `contexto_OR_catboost/features_voume.txt` + `features_volume_v2.txt` se parten en:

| Track | Qué | Dónde |
|---|---|---|
| **A — ejecutado (footprint)** | consumo, impact, VPIN, Kyle, Amihud, absorción, whale-by-exec | ✅ C# `features/MicrostructureFeatures.cs` (`mx_*`) + otros módulos |
| **B — libro / MBO** | depth, spread, pulling, stacking, refill, iceberg, OFI, OBI, queue depletion, book churn... | ❌ BLOQUEADO por datos → reconstrucción **offline en Python** desde dumps del BookRecorder (ver `TRACK_B_MBO_pendiente.md`). NO va en C# (footprint no lo ve). |

El **Feature Scanner** es un indicador HERMANO: corre en chart 1m junto a `02_Visual_Logic`
+ exporter, detecta el 1er breakout OR, snapshotea todos los módulos de features y escribe
un sidecar por fecha, joinable al `score_trade_result` por `fecha`. No toca el exporter
congelado.

---

## 3. Cambios de código (esta sesión)

### Renombres
- `features/AtrapadosFeatureScanner.cs` → **`FeatureScanner.cs`** (clase `FeatureScanner`,
  DisplayName "Feature Scanner"). Se conservó `namespace ATAS.Indicators.Atrapados`
  (compartido por 20 archivos; cambiarlo rompe todo).
- `10_AtrapadosFadeStrategy.cs` → **`10_TrappedFadeStrategy.cs`** (clase `TrappedFadeStrategy`,
  "EW Trapped Fade v1"). **Conservadas** 3 rutas/archivos externos que son contrato con
  Python (`atrapados_sizing_*.txt`, `atrapados_atas_replay.csv`, dir `\atrapados`).

### FeatureScanner.cs — fixes clave
1. **Finalize dentro de la ventana**: antes solo escribía en `FinalizePending` a las 16:00
   (RTH end) o al cambiar de día. El replay corre 09:30–09:50 → nunca escribía.
2. **Escritura incremental por barra** (`EmitPendingRow` + `WriteRawRow`): el replay para
   apenas hay resultado terminal (TP ~09:33, TIME_OVER ~09:40), antes de cualquier finalize.
   Ahora sobrescribe el CSV cada barra mientras hay evento pendiente → en la barra que pare
   el replay, el archivo ya está.
3. **`OrMinutes` default 5 → 1**: el exporter usa OR = candle de apertura 09:30 (1 min, via
   `IsOpeningCandle` en `02_Visual_Logic`). Con 5, el OR no bloqueaba hasta 09:35 y los TP
   rápidos (09:31–09:33) se perdían (solo salían TIME_OVER). Con 1 quedan alineados.
4. **Heartbeat de diagnóstico** (`featscan_status_{fecha}.txt`, ungated): prueba que el
   indicador está cargado/corriendo (bars_seen, or_locked, event_detected, wrote_features_row).

### Runner `04_run_replay_featsweep_after_sync.py` (copia de producción, aislado)
- `--limit N` (prueba rápida; 1 semana = 5) y plan **solo X10** por default.
- Merge de las columnas del Feature Scanner al Excel (`read_feature_scan` +
  `get_feature_scan_headers_for_dates`; `setdefault` → score gana en cols compartidas).
- `print_feature_scans()` + `print_excel_sizes_by_year()`.
- **Reset del balance Telegram**: borra `telegram_balance.json` antes de la 1ª fecha →
  exporter recomienza en $150,000 y acumula solo esta corrida.
- **FIX cuelgue (monkeypatch)**: `replay_sync.get_replay_controls` → versión por HANDLE.

### Exporter `ATASScoreTradeResultExporter.cs` — Telegram balance
- Nuevo `Balance: $#,##0` en el mensaje (trade y TIME OVER).
- `TelegramStartingBalance = 150000` (editable).
- Persistencia `telegram_balance.json` (dict `{fecha: pnl}`), idempotente por fecha
  (X1/X10/re-runs sobrescriben, no doble cuentan).
- **NO** se tocó `CsvHeader` ni `ExporterVersion` (congelados por sync-guards X1/X10).

---

## 4. Cuelgue del replay (causa raíz + fix)

`get_replay_controls()` del común hacía `Desktop(backend="uia").windows(...)` → enumera
**todo el desktop UIA** y se bloquea infinito cuando hay apps pesadas abiertas
(Chrome/Edge/**msedgewebview2**/**ChatGPT**/GitHub Desktop/PowerPoint).

Diagnóstico (`diag_replay_*.py`):

| Método | Tiempo |
|---|---|
| `Desktop.windows()` | cuelga ∞ |
| `app.windows()` (scope proceso) | cuelga ∞ |
| **por HANDLE** (win32 `EnumWindows` → `connect(handle)`) | **0.0s** ✅ |

Fix aplicado en el runner featsweep (monkeypatch, común intacto). Portable al común si se
quiere permanente.

---

## 5. Cómo correr el barrido

Requisitos:
- Chart **1m** con **`02_Visual_Logic` + exporter + `Feature Scanner`** (con "OR minutos"=1).
- ATAS abierto, panel **Replay** visible; recomendado Replay en **X10** manual.
- Reiniciar ATAS tras recompilar para cargar el DLL nuevo.

```powershell
cd "C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup"
python -u 04_run_replay_featsweep_after_sync.py --limit 5 --force   # prueba 1 semana
python -u 04_run_replay_featsweep_after_sync.py --force             # temporada completa
```

Verificación:
- `features_scan_{fecha}_NY.csv` (276 cols) en `data_footprint_generator\trade_results_score`.
- `featscan_status_{fecha}.txt` con `wrote_features_row=1`.
- Excel `Score_indicator_results_updated_2025_2026.xlsx` con score + features.

---

## 6. Despliegue (regla ATAS)

Tras compilar (Release), copiar el DLL a:
- `C:\Users\k_99_\AppData\Roaming\ATAS\Indicators`
- `C:\Users\k_99_\AppData\Roaming\ATAS\Strategies`

Último DLL de la sesión: **2026-07-06 13:34** (0 errores), con todos los fixes.

---

## 7. Pendientes / siguientes pasos

1. Confirmar **5/5 fechas** con features tras reiniciar ATAS (OrMinutes=1 + incremental).
2. Escalar a la temporada completa (quitar `--limit`).
3. (Opcional) Repuntar el Excel del runner featsweep a nombre propio (hoy usa el de
   producción `..._2025_2026.xlsx`).
4. (Opcional) Portar el fix HANDLE al común para todos los runners.
5. Track B (libro/MBO) sigue pendiente por datos → Python offline desde dumps BookRecorder.
