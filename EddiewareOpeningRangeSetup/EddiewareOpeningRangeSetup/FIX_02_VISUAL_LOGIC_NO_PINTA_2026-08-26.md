# Fix — `02_Visual_Logic` dejó de pintar en el gráfico

Fecha: **2026-08-26**
Proyecto: `C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup`
Archivo principal: `02_Visual_Logic.cs` (clase `EddiewareOpeningRangeVisual`)
ATAS instalado: **8.0.14.397**, runtime **net10.0**, x86

> **Estado honesto**: la causa raíz **no está confirmada al 100%** porque ATAS no estaba
> corriendo durante el diagnóstico (última sesión cerró 16:19). Lo que sí está hecho:
> descartar cuatro hipótesis con evidencia, dejar el proyecto compilando, y **eliminar
> el fallo silencioso** para que la próxima vez el gráfico diga por qué no pinta.

---

## 1. Síntoma

El indicador dejó de dibujar en el gráfico: sin opening range, sin entrada/SL/TP, sin
etiquetas de score. Sin mensaje de error visible.

---

## 2. Hipótesis descartadas (con evidencia)

| # | Hipótesis | Evidencia | Veredicto |
|---|---|---|---|
| 1 | El código cambió y rompió el dibujo | `02_Visual_Logic.cs` es del 10 ago; el diff contra `audit_snapshot/20260711` solo añade features (etiquetas de Liquidity Burst, A+ speed) | ❌ Descartada |
| 2 | DLL desactualizado o mal desplegado | `bin\Release\...dll` = `AppData\ATAS\Indicators\...dll` = `AppData\ATAS\Strategies\...dll`, mismos 632,832 bytes | ❌ Descartada |
| 3 | Indicador borrado del workspace | `Eddieware_workspace.ws` contiene `EddiewareOpeningRangeVisual` con `ShowOpeningRange: true`, `OpeningTimeUtc: 13:30:00` | ❌ Descartada |
| 4 | Desajuste de versión con ATAS | Nuestro DLL referencia ATAS.Indicators / ATAS.Strategies / OFT.Rendering **8.0.14.397**, idéntico a lo instalado | ❌ Descartada |

### 2.1 El WARN del log que parecía la causa y no lo es

```
2026-08-26 07:36:43,998 WARN alizationBinder:
  Could not resolve type "ATAS.Indicators.EddiewareOpeningRangeVisual, EddiewareOpeningRangeSetup..."
  Could not load assembly 'EddiewareOpeningRangeSetup'. Objects with this type will be skipped.
```

Parece definitivo, pero **no lo es**:

- Ocurre a las **07:36:43**, durante la deserialización del workspace, y ATAS carga los
  tipos custom **después** (`Loading available types...` a las 07:36:44).
- El **mismo WARN aparece el 24 y el 25 de agosto**, días en los que el indicador sí
  pintaba. Es ruido de arranque, no la causa.

### 2.2 Falsa pista de `System.Drawing.Common`

Se detectó que el DLL referencia `System.Drawing.Common 10.0.0.0` mientras que
`C:\Program Files (x86)\ATAS Platform\System.Drawing.Common.dll` es **8.0.0.0** (jul 2024).
Parecía el culpable. **No lo es:**

- El propio `ATAS.Indicators 8.0.14.397` referencia también **10.0.0.0** (lo confirma el
  error CS1705 al intentar bajar la versión).
- `System.Drawing.Common 10.0.0.0` viene en el framework compartido
  `Microsoft.WindowsDesktop.App\10.0.9`, que es el que usa ATAS.
- El 8.0.0.0 de la carpeta de ATAS es un residuo de una instalación vieja.

**Intento revertido**: se probó bajar el `PackageReference` a `8.0.7` y la compilación
falló con dos `error CS1705`. Se dejó en `10.0.7`, que es lo correcto.

---

## 3. Hipótesis viva: zona horaria del gráfico

Todo el dibujo cuelga de una única condición:

```csharp
private bool IsOpeningCandle(dynamic candle)
{
    var time = candle.Time.TimeOfDay;
    return time.Hours == OpeningTimeUtc.Hours && time.Minutes == OpeningTimeUtc.Minutes;
}
```

Es una comparación **exacta** contra `13:30`. Si no aparece una vela cuyo `TimeOfDay` sea
exactamente 13:30:

1. `_orReady` nunca se pone en `true`,
2. no se dibuja el opening range,
3. `IsSignalWindow` nunca se evalúa,
4. no hay entrada, ni SL, ni TP, ni score,
5. **y no se emite ningún mensaje.**

Dato relevante encontrado en `AppData\Roaming\ATAS\Platform.cnf`:

```json
"SavedTimeZoneOffset": -6,
"IsAutoUpdateTimeZone": false,
```

Si el gráfico muestra hora local (offset −6) en vez de UTC, la apertura de 09:30 ET cae en
`07:30` de la hora del gráfico y **la vela de las 13:30 no existe nunca**. Encaja con el
síntoma "dejó de pintar sin haber tocado el código".

---

## 4. Cambios aplicados

### 4.1 `02_Visual_Logic.cs`

**a) Nuevo input para alinear la hora sin recompilar**

```csharp
[DisplayName("Chart Time Offset Minutes")]
public int ChartTimeOffsetMinutes { get; set; } = 0;
```

Se aplica en un único punto:

```csharp
private TimeSpan EffectiveTimeOfDay(DateTime chartTime)
{
    var shifted = chartTime.AddMinutes(ChartTimeOffsetMinutes).TimeOfDay;
    if (shifted < TimeSpan.Zero)
        shifted += TimeSpan.FromDays(1);
    return shifted;
}
```

y ahora lo usan **las tres** comparaciones horarias, que antes iban por separado y podían
desalinearse entre sí:

| Método | Antes | Ahora |
|---|---|---|
| `IsOpeningCandle` | `candle.Time.TimeOfDay` | `EffectiveTimeOfDay(candle.Time)` |
| `IsSignalWindow` | `candle.Time.TimeOfDay` | `EffectiveTimeOfDay(candle.Time)` |
| `TryDrawTimeOver` | `candle.Time.TimeOfDay` | `EffectiveTimeOfDay(candle.Time)` |

**b) Diagnóstico visible — se acabó el fallo silencioso**

```csharp
[DisplayName("Show Session Diagnostic")]
public bool ShowSessionDiagnostic { get; set; } = true;
```

Si pasados 20 minutos de la hora de apertura esperada no se encontró la vela, se dibuja
**una etiqueta amarilla, una sola vez por día**:

```
SIN OPENING RANGE | espero 13:30 | vela actual 07:52 | primera del dia 07:30 | offset 0min
```

Con eso el gráfico dice exactamente qué hora esperaba y qué hora está viendo, que es el
dato que faltaba para diagnosticar en segundos.

**c) Estado nuevo**, reseteado en `ResetDay`:

```csharp
private bool _sessionDiagnosticDrawn;
private TimeSpan _firstCandleTimeOfDay = TimeSpan.MinValue;
```

### 4.2 `EddiewareOpeningRangeSetup.csproj`

Comentario explicando por qué `System.Drawing.Common` debe quedarse en la línea 10.x,
para que nadie repita el intento de bajarlo:

```xml
<!-- ATAS ships System.Drawing.Common 8.0.0.0 in its own folder, and this
     assembly is NOT part of the shared framework... -->
<PackageReference Include="System.Drawing.Common" Version="10.0.7" />
```

---

## 5. Compilación y despliegue

```
Compilación correcta.
    63 Advertencia(s)   (todas CA1416, System.Drawing solo soportado en Windows; preexistentes)
     0 Errores
```

| Destino | Tamaño | Fecha |
|---|---:|---|
| `AppData\Roaming\ATAS\Indicators\EddiewareOpeningRangeSetup.dll` | 635,392 | 2026-08-26 22:50 |
| `AppData\Roaming\ATAS\Strategies\EddiewareOpeningRangeSetup.dll` | 635,392 | 2026-08-26 22:50 |

El `.csproj` copia a ambas carpetas automáticamente en el target `CopyIndicatorToAtas`.

---

## 6. Qué hacer al abrir ATAS

1. Abrir ATAS y mirar el gráfico donde estaba el indicador.
2. **Si aparece la etiqueta amarilla** `SIN OPENING RANGE`: leer la hora que reporta.
   - Si dice `vela actual 07:52` cuando espera `13:30`, la diferencia es de **6 horas** →
     poner `Chart Time Offset Minutes = 360`.
   - La fórmula: `offset = (hora esperada − hora que ve) en minutos`.
3. **Si no aparece la etiqueta y tampoco pinta**: entonces el indicador no se está
   ejecutando, y el problema es de carga del ensamblado, no de lógica. En ese caso
   confirmar en `Logs\app_AAAAMMDD.log` si hay algún mensaje después de
   `Loading available types...`.
4. Dato que separa los dos casos en un segundo: **¿los otros indicadores del mismo DLL
   siguen pintando?** (`DojiCandleDraw`, `CandleCursorCounter`, `NqEsStructuralSyncMonitor`).
   - Sí pintan → el DLL carga bien, el problema es de la lógica de `02_Visual_Logic`.
   - No pinta ninguno → es carga del ensamblado.

---

## 7. Pendiente

| # | Pendiente |
|---|---|
| 1 | Confirmar la causa con ATAS abierto; el diagnóstico visual la resuelve en un vistazo |
| 2 | Si la causa es la zona horaria, valorar sustituir la comparación exacta por una tolerancia de ventana, para que no vuelva a romperse con un cambio de zona o de DST |
| 3 | Limpiar el `System.Drawing.Common.dll` 8.0.0.0 residual de la carpeta de ATAS solo si se confirma que estorba (por ahora no hay evidencia de que lo haga) |
