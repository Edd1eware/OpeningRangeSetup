# Cursores A/B contador de velas — cómo se construyó

**Fecha:** 2026-08-07
**Archivo:** `BarCounterCursors.cs`, clase `BarCounterCursors : Indicator` — **único `.cs` del proyecto**
**Referencia visual:** `Desktop\imagenes_IA\cursores_A_B.png`

Dos reglas verticales naranjas arrastrables que numeran y cuentan las velas encerradas
entre ellas. Este documento explica **por qué** cada pieza está como está, no solo qué hace.

> **Historia:** la feature nació incrustada en `02_Visual_Logic.cs` (indicador de Opening
> Range, ~1,700 líneas) y colgaba de 9 archivos de lógica OR para compilar. Después se
> extrajo a este indicador autocontenido y el resto del proyecto se eliminó. Al extraer
> desapareció el switch maestro `ShowBarCounter` — ya no hace falta, el indicador entero
> *es* la feature — y se agregó `CursorColor` configurable. La mecánica no cambió.

---

## 1. La decisión que define todo: anclar al borde, no al centro

Un cursor de medición tiene que vivir **entre** velas, no encima de una. Si anclas al
centro de la barra aparece de inmediato la pregunta sin respuesta: "¿la vela debajo del
cursor cuenta o no?". Anclando al **borde izquierdo** de una barra el problema desaparece.

| Concepto | Fórmula |
|---|---|
| Rango encerrado | `[min(A,B), max(A,B))` — semiabierto |
| Total de velas | `max(A,B) − min(A,B)` |
| Numeración de la vela `bar` | `bar − first + 1` |

El rango es semiabierto: la barra en `max(A,B)` **no** se cuenta, porque el cursor está en
su borde izquierdo, o sea justo antes de ella. De ahí sale un conteo exacto sin casos
especiales ni `+1`/`−1` correctivos por ningún lado.

## 2. El ancla `TotalBars` (una pasada del último índice)

La posición home pide encerrar **las 6 velas más recientes, vela en formación incluida**.
Con índices normales (`0..TotalBars-1`) eso es imposible: para encerrar la última vela el
cursor B tiene que estar en su **borde derecho**, que es el borde izquierdo de una barra
que todavía no existe.

Solución: permitir que el ancla llegue a `TotalBars`.

```csharp
// Cursors anchor to bar LEFT edges, so the rightmost usable anchor is one past
// the last bar — that is the right edge of the newest candle.
private static int MaxCursorAnchor(IChartContainer container)
{
    return container.TotalBars;
}
```

`ChartInfo.GetXByBar(TotalBars, true)` devuelve una coordenada válida porque ATAS extiende
el eje X hacia el margen derecho del chart. Esto tiene dos consecuencias que hay que
respetar en todo el resto del código:

- **`GetCandle(last)` puede reventar.** El ancla derecha no siempre es una vela real. Por
  eso `DrawBarCounterSummary` hace `Math.Min(last, CurrentBar - 1)` antes de leer un
  timestamp, y `DrawBarNumbers` numera solo hasta `last - 1` con guardia `bar >= CurrentBar`.
- **El clamp de arrastre sube a `TotalBars`**, no a `TotalBars - 1`. Si no, el usuario nunca
  podría devolver el cursor B a home arrastrando.

## 3. Posición home

```csharp
_cursorBarB = MaxCursorAnchor(container);          // borde derecho de la vela más nueva
_cursorBarA = ClampBar(_cursorBarB - span, container);   // span = HomeSpanBars = 6
```

Span 6 → encierra las 6 velas más recientes. Se aplica en dos momentos:

1. La primera vez que se muestran los cursores (`SeedCursorsIfNeeded`).
2. Cuando una recarga de datos dejó los índices fuera de rango.

**No** se re-aplica cuando nacen velas nuevas: el home deja de ser home y los cursores se
quedan donde el usuario los puso. Es lo correcto para una herramienta de medición — si se
movieran solos, no medirías nada. Para volver a home: **doble clic** sobre cualquier cursor.

## 4. Arrastre

### Enrutamiento de eventos

`ChartObject` expone `ProcessMouseDown/Move/Up/DoubleClick` y `GetCursor` como **públicos y
virtuales** — se sobreescriben directo, sin plumbing extra. Verificado por reflexión sobre
`ATAS.Indicators.dll`, no por memoria.

### Consumir el evento

```csharp
_draggingCursor = hit;
return true;                       // consume: stop the chart from panning
```

Devolver `true` en `ProcessMouseDown` es lo que impide que ATAS haga paneo del chart
mientras arrastras. Sin eso el cursor se mueve y el chart se desplaza al mismo tiempo.

Cuando el clic **no** cae sobre un cursor se hace `return base.ProcessMouseDown(e)` en vez
de `return false`: así el comportamiento nativo de ATAS queda intacto.

### Snap al borde más cercano

`ResolveBarFromMouse` barre los bordes visibles y se queda con el más cercano en píxeles:

```csharp
var from = Math.Max(0, container.FirstVisibleBarNumber);
var to   = Math.Min(MaxCursorAnchor(container), container.LastVisibleBarNumber + 1);
```

**Se descartó `MouseLocationInfo.BarBelowMouse` a propósito**, por dos razones:

1. Resuelve la barra *sobre la que está* el puntero, no el borde más cercano. Con anclaje
   a bordes eso produce un salto de media vela.
2. Nunca puede devolver `TotalBars`, así que el cursor B jamás alcanzaría el borde derecho
   de la última vela — mataría la posición home.

El barrido es sobre el rango visible (cientos de barras), corre por evento de mouse. Costo
irrelevante.

### Feedback del puntero

`GetCursor` devuelve `StdCursor.SizeWE` (↔) al pasar sobre una línea o mientras arrastras.
Fuera de eso delega en `base`. `StdCursor.NULL` es el centinela de "sin opinión".

## 5. Render

Enganchado con:

```csharp
EnableCustomDrawing = true;
SubscribeToDrawingEvents(DrawingLayouts.Final);
```

`Final` y no `LatestBar` (lo que usa `DomLevels.cs`) porque los cursores son un overlay de
chart completo: tienen que repintarse en cada scroll y zoom, no solo cuando cambia la
última vela.

Orden de dibujo en `OnRender`, de atrás hacia adelante:

| # | Elemento | Detalle |
|---|---|---|
| 1 | Sombreado del span | `Color.FromArgb(22, 255, 140, 0)` — naranja al 22 % alfa |
| 2 | Las dos líneas | `RenderPen(Color.Orange, CursorLineWidth)`, de `region.Top` a `region.Bottom` |
| 3 | Etiquetas "Cursor A"/"Cursor B" | Abajo, con caja oscura; se voltean al otro lado si se salen por la derecha |
| 4 | Números 1..N | Centrados sobre el cuerpo de cada vela, apenas arriba del High |
| 5 | Caja resumen | Arriba y centrada: `"N velas · MMm SSs"` |

El centro horizontal de cada número se calcula como
`(GetXByBar(bar, true) + GetXByBar(bar + 1, true)) / 2` — el punto medio entre los dos
bordes de la barra. Es robusto sin depender de la semántica exacta del flag `isStartOfBar`.

Los números se saltan si el span pasa de `MaxNumberedBars` (60): a partir de ahí solo
estorban y la caja resumen ya da el dato.

## 6. Estado: por qué los índices NO son propiedades

```csharp
private int _cursorBarA = -1;
private int _cursorBarB = -1;
```

Campos privados, deliberadamente. ATAS serializa las propiedades públicas en el template
del chart, y **un índice de barra no significa nada tras recargar datos**: el mismo entero
apunta a otro momento del mercado. Serializarlos daría posiciones basura al reabrir. Se
re-siembran por sesión.

## 7. Propiedades expuestas (grupo "Contador de velas")

| Propiedad | Campo | Default |
|---|---|---|
| Numerar velas entre cursores | `ShowBarNumbers` | true |
| Máx velas a numerar | `MaxNumberedBars` | 60 |
| Mostrar total y duración | `ShowSummary` | true |
| Sombrear zona entre cursores | `ShadeSpan` | true |
| Grosor de línea (px) | `CursorLineWidth` | 2 |
| Tolerancia de arrastre (px) | `CursorGrabTolerancePx` | 7 |
| Velas en posición home | `HomeSpanBars` | 6 |
| Color | `CursorColor` | `Color.Orange` |

## 8. API de ATAS usada

Todo verificado por reflexión sobre los DLL de `C:\Program Files (x86)\ATAS Platform\`.

| Necesidad | API |
|---|---|
| Habilitar dibujo propio | `EnableCustomDrawing`, `SubscribeToDrawingEvents(DrawingLayouts)` |
| Render | `OnRender(RenderContext, DrawingLayouts)` |
| Mouse | `ChartObject.ProcessMouseDown/Move/Up/DoubleClick` (public virtual) |
| Puntero | `GetCursor()` → `OFT.Rendering.StdCursor` |
| Barra → píxel X | `ChartInfo.GetXByBar(bar, isStartOfBar)` — extensión de `IChart` |
| Precio → píxel Y | `ChartInfo.GetYByPrice(price, isStartOfPriceLevel)` |
| Rango visible / total | `ChartInfo.PriceChartContainer.{First,Last}VisibleBarNumber`, `.TotalBars` |
| Área del panel | `Container.Region` |
| Forzar repintado | `RedrawChart()` |
| Primitivas | `context.DrawLine / FillRectangle / DrawRectangle / DrawString / MeasureString` |

`using` agregados: `System.ComponentModel.DataAnnotations`, `OFT.Rendering`,
`OFT.Rendering.Context`, `OFT.Rendering.Control`, `OFT.Rendering.Tools`.

## 9. Estado de compilación

Compilación correcta, **0 errores, 0 warnings CS**. DLL de 13,824 B desplegado a
`%APPDATA%\ATAS\Indicators` y `...\Strategies` por el target `CopyIndicatorToAtas` del
`.csproj` (automático post-build, no hay que copiar a mano).

Los 5 warnings restantes son `CA1416` (APIs de `System.Drawing` marcadas Windows-only) y
`MSB3277` (conflicto de versión de `WindowsBase` entre ATAS y net10). Ambos son ruido:
ATAS solo corre en Windows.

## 10. Pendiente de verificar EN VIVO

Nada de esto se probó dentro de ATAS. **Solo está confirmado que compila y despliega.**
Falta abrir el chart y confirmar:

1. **Que ATAS enruta los eventos de mouse al indicador.** Es la única pieza que no se pudo
   validar por reflexión — los métodos existen y son virtuales, pero que la plataforma los
   invoque para un `Indicator` (y no solo para objetos de dibujo nativos) está sin probar.
   *Síntoma si falla:* las líneas se pintan pero no se pueden arrastrar.
2. **Que `GetXByBar(TotalBars, true)` devuelve el borde derecho real** y no un valor
   degenerado. *Síntoma si falla:* el cursor B aparece pegado a la última vela o fuera de
   la pantalla, y el home cuenta 5 en vez de 6.
3. **Que el arrastre no pelea con las herramientas de dibujo nativas** de ATAS cuando hay
   una activa.
