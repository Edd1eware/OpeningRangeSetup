# Volume_Profile_Eddieware — creación detallada + outputs para backtest (2026-07-07)

> **ACTUALIZACIÓN 2026-07-08:** el LVN ya no usa 08:30–09:40. Ahora se construye
> exclusivamente con 09:30:00–09:31:00 ET, se revela a las 09:31 y se pinta en verde.
> El perfil 08:30–09:30 añade clasificación matemática D/P/b/double/trend con
> probabilidades continuas. El motor de backtest objetivo está documentado en
> `LVN_Retest_Research_Engine_2026-07-08.md`.

Archivo: `13_Volume_Profile_Eddieware.cs` · clase `VolumeProfileEddieware : Indicator` ·
`DisplayName = "Volume_Profile_Eddieware"` · namespace `ATAS.Indicators`.
Integrado a `EddiewareOpeningRangeSetup` (no toca ningún archivo existente).

---

## 1. Qué hace

Dos perfiles de volumen en **hora NY (DST aware)** para el NQ:

| Perfil | Ventana default (NY) | Marca |
|---|---|---|
| DIRECTION (perfil fijo) | **08:30–09:30** | POC + VAH + VAL + dirección `HIGH`/`LOW`/`INSIDE` |
| LVN primer minuto | **09:30–09:31** (congelado) | mejor LVN (Low Volume Node) — una línea verde |

- **LVN primer minuto** usa solo datos 09:30:00–09:31:00. No dibuja antes de 09:31 y nunca incorpora
  datos posteriores. Solo marca el candidato numérico más profundo para mantener un overlay limpio;
  el motor Python conserva todos los candidatos para investigación.
- **Dirección**: close del último bar vs value area → arriba de VAH = `HIGH` (posible barrido del high),
  abajo de VAL = `LOW` (posible barrido del low), dentro = `INSIDE`.

---

## 2. Cómo se construye (internamente)

1. `OnCalculate(bar, value)` — en cada barra nueva llama `Rebuild(bar)`.
2. **Conversión de tiempo**: `candle.Time` (UTC) → NY con
   `TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time")` + `ConvertTimeFromUtc`.
   El mismo `09:30` es correcto en EST (UTC-5) y EDT (UTC-4).
3. **Bins de volumen@precio**: `key = round(price / tick)`, `tick = 0.25`.
   - Footprint real vía `candle.GetAllPriceLevels()` → `vol = l.Ask + l.Bid`.
   - Fallback (feed sin footprint): todo el `Volume` de la vela en el bin del `Close`.
4. **POC / Value Area** (`ComputeProfile`): POC = bin de mayor volumen; VA se expande desde el POC
   sumando el lado adyacente más rico hasta cubrir `ValueAreaPct`% (default 70%) del volumen total.
5. **LVN causal** (`FindBestLvn`): cada precio debe ser menor que el promedio de los `N` vecinos de
   ambos lados, quedar bajo el porcentaje máximo de vecinos y del POC, y superar el volumen mínimo.
   El indicador selecciona el candidato con mejor profundidad; el backtest registra todos.
6. **Dibujo**: `TrendLines.Add(new TrendLine(...))` (líneas horizontales) + `AddText(...)` (labels).
   Las líneas se limpian y redibujan cada barra (developing) y en cada sesión nueva.

---

## 3. Render (lo que ves en el chart)

| Línea | Color | Grosor |
|---|---|---|
| POC (direction) | Oro | 3 |
| VAH | Azul (DodgerBlue) | 2 |
| VAL | Rojo (OrangeRed) | 2 |
| LVN | **Verde (LimeGreen)** | 3 |
| Label dirección | fondo verde (HIGH) / rojo (LOW) / gris (INSIDE) | — |
| Label LVN | **precio + quality score**, texto negro sobre verde | — |

---

## 4. OUTPUTS (el indicador NO escribe archivo — expone valores)

> El indicador **originalmente NO tenía outputs** (solo dibujaba). Ahora **entrega valores**
> (los niveles de precio de cada línea). **NO genera ningún excel/CSV** — de eso se encarga el
> **exporter** (`ATASScoreTradeResultExporter`), que lee estos valores y los agrega a su archivo.

### 4.1 Propiedades públicas (lectura directa)
`VolumeProfileEddieware` expone, actualizadas en cada rebuild:

| Propiedad | Tipo | Es |
|---|---|---|
| `HasDirection` | bool | ¿hay perfil de dirección? |
| `DirPoc` / `DirVah` / `DirVal` | decimal | POC / VAH / VAL (líneas oro/azul/roja) |
| `DirHigh` / `DirLow` / `DirRangeTicks` | decimal | extremos del perfil fijo + rango en ticks |
| `Direction` | string | `HIGH` / `LOW` / `INSIDE` |
| `HasLvn` / `LvnPoc` | bool / decimal | ¿calificó un LVN? + POC del perfil congelado 09:30–09:31 |
| `LvnConfidencePct` | decimal | score 0–100 del LVN seleccionado |
| `LvnLevels` | `IReadOnlyList<decimal>` | vacío o un único precio: la línea LVN seleccionada |
| `NearestLvnAbove(p)` / `NearestLvnBelow(p)` | decimal | helper: LVN más cercano arriba/abajo de un precio |

### 4.2 Puente al exporter (`VolumeProfileStore`)
En ATAS un indicador no lee otra instancia directo. Se usa un **store estático compartido**
(mismo idiom que `SharedTradeSignalSnapshot`), archivo `14_VolumeProfileStore.cs`:

- El indicador **publica** los niveles por fecha de sesión: `VolumeProfileStore.Publish(date, levels)`
  (llamado al final de `Rebuild`, cada barra).
- El exporter **lee**: `VolumeProfileStore.TryGet(nyDate, out levels)`.
- Ambos corren en el mismo proceso ATAS → el static se comparte. Sin I/O de archivo aquí.

---

## 5. Conexión con el exporter (quien genera el excel)

`ATASScoreTradeResultExporter` ya escribe un CSV por trade
(`score_trade_result_{fecha}_NY.csv`). Se le **agregaron 10 columnas VP al final** (sin tocar el
bloque frozen del medio):

| Columna nueva | Es |
|---|---|
| `VP_Dir_POC` / `VP_Dir_VAH` / `VP_Dir_VAL` | POC / VAH / VAL del perfil fijo 08:30–09:30 |
| `VP_Dir_High` / `VP_Dir_Low` / `VP_Dir_Range_Ticks` | extremos + rango |
| `VP_Direction` | HIGH / LOW / INSIDE |
| `VP_LVN_POC` | POC del perfil LVN congelado 09:30–09:31 |
| `VP_LVN_Count` | 0 o 1 (solo el LVN más claro) |
| `VP_LVN_Levels` | precio de la única línea LVN, ej. `21050.25` |

Detalles de implementación:
- Header: `CsvHeader` extendido con las 10 columnas.
- Punto único de inyección en `WriteTradeFile`: `csvRow += "," + BuildVolumeProfileCsvFields(nyDate);`
  → alinea **ambas** ramas (fila fresca y fila de replay-sync) con el header.
- `BuildVolumeProfileCsvFields` siempre emite **10 campos** (vacíos si aún no se publicó VP ese día).

**Requisito**: para que las columnas se poblen, **ambos** indicadores deben estar en el chart:
`Volume_Profile_Eddieware` (publica) **y** el exporter (lee/escribe). Si solo está el exporter,
las 10 columnas salen vacías.

**Causalidad OK**: el contexto se congela a las 09:30 y el LVN a las 09:31. La línea LVN empieza en
la barra de 09:31; nunca se extiende hacia atrás sobre la ventana que lo construyó.

### Backtest (Python/DuckDB)
Los niveles VP viajan **dentro del mismo CSV del exporter**, una columna por nivel:

```python
import pandas as pd, glob
df = pd.concat([pd.read_csv(f) for f in glob.glob(r"...\score_trade_result_*_NY.csv")])
df["VP_LVN_Levels"] = df["VP_LVN_Levels"].fillna("")
# explota LVN a filas si quieres testear distancia entry->LVN
df["lvn_list"] = df["VP_LVN_Levels"].str.split("|")
# join directo con el resto de features del trade (score, side, result, etc.)
```
Reportar por **año × métrica** (trades, trades/mes, WR, R:R, PF, EV bruto/neto) como el estándar.

---

## 6. Parámetros (todos editables en ATAS)

| Grupo | Param | Default |
|---|---|---|
| Windows | `DirectionStartNy` / `DirectionEndNy` | 08:30 / 09:30 |
| Windows | `LvnStartNy` / `LvnEndNy` | 09:30 / 09:31 |
| Profile | `ValueAreaPct` | 70 |
| Profile | `LvnNeighborLevels` | 2 |
| Profile | `LvnMaxPercentOfNeighbors` | 50 |
| Profile | `MinLvnVolume` | 1 |
| Profile | `MaxLvnVolumePercentOfPoc` | 50 |
| Profile | `MinTotalVolumeAtLvnProfile` | 1 |
| Profile | `ExtendBars` | 120 |
| Show | `ShowDirection` / `ShowLvn` / `ShowLabels` | on |

(Ya **no** hay parámetros de output/archivo — el indicador no escribe nada.)

Nota: la propiedad se llama `ValueAreaPct` (no `ValueAreaPercent`) porque `Indicator` base ya expone
`ValueAreaPercent` → colisión CS0108.

---

## 7. Archivos tocados / build

| Archivo | Cambio |
|---|---|
| `13_Volume_Profile_Eddieware.cs` | indicador (perfiles + propiedades output + publish al store) |
| `14_VolumeProfileStore.cs` | store estático compartido (nuevo) |
| `ATASScoreTradeResultExporter.cs` | +10 columnas VP en header y fila (lee del store) |

- Compila: **0 errores**, 20 warnings (todos preexistentes del proyecto + 1 CA1416 `Pen`, inofensivo en Windows).
- DLL `EddiewareOpeningRangeSetup.dll` (~423 KB) auto-copiado por el `.csproj` a:
  `bin\Release\net10.0\`, `%APPDATA%\ATAS\Indicators\`, `%APPDATA%\ATAS\Strategies\`.
- Para ver cambios: reiniciar ATAS y reaplicar los indicadores al chart NQ 1-min.

## 8. Pendiente
- Verificar en ATAS: aplicar `Volume_Profile_Eddieware` + exporter al mismo chart y revisar que las
  10 columnas `VP_*` se pueblan en `score_trade_result_*_NY.csv`.
- No optimizar parámetros con la misma muestra usada para medir resultados; el motor registra cada
  rechazo y su razón en `Debug` para poder hacer análisis walk-forward.
- Validar por año y por forma D/P/b los retests 09:31–09:40 con el motor causal independiente.
