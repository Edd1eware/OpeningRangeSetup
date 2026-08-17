using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Drawing;
using System.Globalization;
using OFT.Rendering.Context;       // RenderContext
using OFT.Rendering.Control;       // RenderControlMouseEventArgs, RenderControlMouseButtons
using OFT.Rendering.Tools;         // RenderPen, RenderFont

namespace ATAS.Indicators
{
    // Candle counter driven by two manual vertical cursors (A and B).
    //
    // Place cursors with the mouse on the price chart:
    //   Shift + left click -> Cursor A
    //   Ctrl  + left click -> Cursor B
    // Plain clicks are never intercepted, so normal chart interaction is untouched.
    //
    // Between the two cursors every candle is numbered 1..N on the chart, and a summary
    // box reports bar count, elapsed time, close-to-close move and the high/low range of
    // the span (in ticks).
    //
    // Pure overlay: reads candles only. Touches nothing of the exporter, feature scanner,
    // execution strategy or replay-sync.
    [DisplayName("18_Candle_Cursor_Counter")]
    public class CandleCursorCounter : Indicator
    {
        private const decimal FallbackTickSize = 0.25m;

        // Cursor anchors. The bar index is the fast path; the candle open time is the
        // durable key used to re-resolve the index after the chart reloads history.
        private int _barA = -1;
        private int _barB = -1;
        private DateTime _timeA = DateTime.MinValue;
        private DateTime _timeB = DateTime.MinValue;

        private RenderFont _numberFont = new("Arial", 10, FontStyle.Bold);
        private readonly RenderFont _labelFont = new("Arial", 11, FontStyle.Bold);
        private readonly RenderFont _summaryFont = new("Arial", 11);
        private float _builtFontSize = 10;

        public CandleCursorCounter()
        {
            Name = "18_Candle_Cursor_Counter";
            EnableCustomDrawing = true;
            SubscribeToDrawingEvents(DrawingLayouts.Final);
            DrawAbovePrice = true;
            DenyToChangePanel = true;
            Panel = IndicatorDataProvider.CandlesPanel;
        }

        #region Settings

        [Display(Name = "Colocar cursores con el mouse (Shift=A, Ctrl=B)", GroupName = "Cursores", Order = 1)]
        public bool EnableMousePlacement { get; set; } = true;

        [Display(Name = "Contar tambien las velas de los cursores", GroupName = "Cursores", Order = 2)]
        public bool IncludeCursorBars { get; set; } = true;

        [Display(Name = "Borrar cursores (se auto-desactiva)", GroupName = "Cursores", Order = 3)]
        public bool ResetCursors
        {
            get => false;
            set
            {
                if (!value)
                    return;

                _barA = _barB = -1;
                _timeA = _timeB = DateTime.MinValue;
                RedrawChart();
            }
        }

        [Display(Name = "Color Cursor A", GroupName = "Cursores", Order = 4)]
        public Color CursorAColor { get; set; } = Color.Orange;

        [Display(Name = "Color Cursor B", GroupName = "Cursores", Order = 5)]
        public Color CursorBColor { get; set; } = Color.Orange;

        [Display(Name = "Grosor de linea", GroupName = "Cursores", Order = 6)]
        [Range(1, 10)]
        public int LineWidth { get; set; } = 2;

        [Display(Name = "Mostrar numeros sobre las velas", GroupName = "Numeracion", Order = 10)]
        public bool ShowNumbers { get; set; } = true;

        // On dense charts numbering every candle turns into noise; 5 labels only 1,5,10...
        [Display(Name = "Etiquetar cada N velas", GroupName = "Numeracion", Order = 11)]
        [Range(1, 100)]
        public int LabelEveryNBars { get; set; } = 1;

        // Horizontal centering is always on; this only controls the vertical anchor.
        [Display(Name = "Centrar el numero dentro de la vela (si no, va encima)", GroupName = "Numeracion", Order = 12)]
        public bool CenterNumberInCandle { get; set; } = false;

        // Pixels, not ticks: a tick-based gap explodes visually when the chart is zoomed in
        // (8 ticks on a zoomed footprint is ~200 px), so the spacing must be zoom-independent.
        [Display(Name = "Separacion del numero (pixeles sobre la vela, si no esta centrado)", GroupName = "Numeracion", Order = 13)]
        [Range(0, 200)]
        public int LabelOffsetPixels { get; set; } = 20;

        [Display(Name = "Color del numero", GroupName = "Numeracion", Order = 13)]
        public Color NumberColor { get; set; } = Color.White;

        [Display(Name = "Tamano de fuente", GroupName = "Numeracion", Order = 14)]
        [Range(6, 60)]
        public float FontSize { get; set; } = 10;

        [Display(Name = "Mostrar aviso cuando no hay cursores", GroupName = "Resumen", Order = 19)]
        public bool ShowHint { get; set; } = true;

        [Display(Name = "Mostrar resumen (velas / tiempo / ticks)", GroupName = "Resumen", Order = 20)]
        public bool ShowSummary { get; set; } = true;

        [Display(Name = "Color del resumen", GroupName = "Resumen", Order = 21)]
        public Color SummaryColor { get; set; } = Color.White;

        #endregion

        // Nothing to compute per bar: the indicator is fully driven by the cursors.
        protected override void OnCalculate(int bar, decimal value) { }

        #region Mouse placement

        public override bool ProcessMouseClick(RenderControlMouseEventArgs e)
        {
            if (!EnableMousePlacement || e == null || e.Button != RenderControlMouseButtons.Left)
                return false;

            // Only modifier-held clicks are consumed; a bare click stays with the chart.
            var isA = e.Shift && !e.Control;
            var isB = e.Control && !e.Shift;
            if (!isA && !isB)
                return false;

            var bar = ChartInfo?.MouseLocationInfo?.BarBelowMouse ?? -1;
            if (bar < 0 || bar > CurrentBar - 1)
                return false;

            var time = GetCandle(bar).Time;
            if (isA)
            {
                _barA = bar;
                _timeA = time;
            }
            else
            {
                _barB = bar;
                _timeB = time;
            }

            RedrawChart();
            return true;
        }

        #endregion

        #region Rendering

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (ChartInfo == null || Container == null)
                return;

            RebuildFontsIfNeeded();

            _barA = ResolveBar(_barA, _timeA);
            _barB = ResolveBar(_barB, _timeB);

            var region = Container.Region;

            // With no cursors placed the indicator would draw nothing at all, which is
            // indistinguishable from "the indicator is not loaded" or "clicks are not
            // arriving". The hint makes the live state explicit.
            if (_barA < 0 && _barB < 0)
            {
                DrawHint(context, region);
                return;
            }

            DrawCursor(context, _barA, "Cursor A", CursorAColor, region);
            DrawCursor(context, _barB, "Cursor B", CursorBColor, region);

            if (_barA < 0 || _barB < 0)
                return;

            var from = Math.Min(_barA, _barB);
            var to = Math.Max(_barA, _barB);
            if (!IncludeCursorBars)
            {
                from++;
                to--;
            }

            if (from > to)
                return;

            if (ShowNumbers)
                DrawNumbers(context, from, to, region);

            if (ShowSummary)
                DrawSummary(context, from, to, region);
        }

        private void DrawCursor(RenderContext context, int bar, string label, Color color, Rectangle region)
        {
            if (bar < 0 || !IsNearVisible(bar))
                return;

            var x = GetBarCenterX(bar);
            var pen = new RenderPen(color, LineWidth);
            context.DrawLine(pen, x, region.Top, x, region.Bottom);

            var size = context.MeasureString(label, _labelFont);
            var labelX = Math.Max(region.Left, x - (size.Width / 2));
            context.DrawString(label, _labelFont, color, labelX, region.Bottom - size.Height - 2);
        }

        private void DrawNumbers(RenderContext context, int from, int to, Rectangle region)
        {
            var step = Math.Max(1, LabelEveryNBars);

            for (var bar = from; bar <= to; bar++)
            {
                var number = bar - from + 1;

                // Always keep the first and last label so the span stays readable when stepping.
                if (step > 1 && number != 1 && bar != to && (number - 1) % step != 0)
                    continue;

                if (!IsNearVisible(bar))
                    continue;

                var candle = GetCandle(bar);
                var x = GetBarCenterX(bar);
                var text = number.ToString(CultureInfo.InvariantCulture);
                var size = context.MeasureString(text, _numberFont);

                int y;
                if (CenterNumberInCandle)
                {
                    // Midpoint of the candle range, then lift the text by half its height so
                    // the glyph straddles that price instead of hanging below it.
                    var mid = (candle.High + candle.Low) / 2m;
                    y = Chart.GetYByPrice(mid, true) - (size.Height / 2);
                }
                else
                {
                    // candle.High already includes the wick, so the gap is measured from the
                    // top of the whole candle, and the text sits fully above it.
                    y = Chart.GetYByPrice(candle.High, true) - LabelOffsetPixels - size.Height;
                }

                if (y + size.Height > region.Bottom)
                    continue;

                // Clamp instead of skipping: a number pushed past the top edge should still
                // be readable rather than silently vanish.
                if (y < region.Top)
                    y = region.Top;

                context.DrawString(text, _numberFont, NumberColor, x - (size.Width / 2), y);
            }
        }

        private void DrawHint(RenderContext context, Rectangle region)
        {
            if (!ShowHint)
                return;

            // AllowedInteraction is Visible && !Locked. A locked indicator never receives
            // mouse events, so say that out loud instead of letting the user click forever.
            var text = !EnableMousePlacement
                ? "18_Candle_Cursor_Counter: colocacion con mouse DESACTIVADA en propiedades"
                : !AllowedInteraction
                    ? "18_Candle_Cursor_Counter: indicador BLOQUEADO (Locked) - el mouse no llega"
                    : "18_Candle_Cursor_Counter listo  |  Shift+click = Cursor A  |  Ctrl+click = Cursor B";

            var color = AllowedInteraction && EnableMousePlacement ? SummaryColor : Color.Orange;
            DrawBoxedText(context, text, color, region);
        }

        private void DrawBoxedText(RenderContext context, string text, Color color, Rectangle region)
        {
            var size = context.MeasureString(text, _summaryFont);
            var box = new Rectangle(region.Left + 8, region.Top + 8, size.Width + 10, size.Height + 6);
            context.FillRectangle(Color.FromArgb(180, 0, 0, 0), box);
            context.DrawRectangle(new RenderPen(color, 1), box);
            context.DrawString(text, _summaryFont, color, box.Left + 5, box.Top + 3);
        }

        private void DrawSummary(RenderContext context, int from, int to, Rectangle region)
        {
            var tickSize = GetTickSize();
            var first = GetCandle(from);
            var last = GetCandle(to);

            var count = to - from + 1;
            var elapsed = last.LastTime - first.Time;
            var moveTicks = tickSize > 0 ? (last.Close - first.Close) / tickSize : 0m;

            decimal high = first.High, low = first.Low;
            for (var bar = from; bar <= to; bar++)
            {
                var candle = GetCandle(bar);
                if (candle.High > high) high = candle.High;
                if (candle.Low < low) low = candle.Low;
            }

            var rangeTicks = tickSize > 0 ? (high - low) / tickSize : 0m;

            var text = string.Format(
                CultureInfo.InvariantCulture,
                "{0} velas  |  {1}  |  cierre {2:+0;-0;0} ticks  |  rango {3:0} ticks",
                count,
                FormatElapsed(elapsed),
                moveTicks,
                rangeTicks);

            DrawBoxedText(context, text, SummaryColor, region);
        }

        #endregion

        #region Helpers

        private void RebuildFontsIfNeeded()
        {
            if (Math.Abs(_builtFontSize - FontSize) < 0.01f)
                return;

            // Only the bar numbers scale with FontSize. Cursor labels and the summary box
            // stay fixed, otherwise a large number size blows up the whole overlay.
            _builtFontSize = FontSize;
            _numberFont = new RenderFont("Arial", FontSize, FontStyle.Bold);
        }

        // Bar indices survive within a session but shift when history reloads, so the
        // candle open time is the source of truth and the index is only a cache.
        private int ResolveBar(int cached, DateTime time)
        {
            if (time == DateTime.MinValue || CurrentBar <= 0)
                return -1;

            if (cached >= 0 && cached <= CurrentBar - 1 && GetCandle(cached).Time == time)
                return cached;

            var lo = 0;
            var hi = CurrentBar - 1;
            while (lo <= hi)
            {
                var mid = lo + ((hi - lo) / 2);
                var midTime = GetCandle(mid).Time;
                if (midTime == time)
                    return mid;
                if (midTime < time)
                    lo = mid + 1;
                else
                    hi = mid - 1;
            }

            return -1;
        }

        // Every caller runs inside OnRender, which returns early when ChartInfo is null.
        private IChart Chart => ChartInfo!;

        // The flag is isStartOfBar: true = left edge, false = right edge. Half a bar past
        // the left edge is the true horizontal center of the candle.
        private int GetBarCenterX(int bar)
        {
            var barsWidth = Chart.PriceChartContainer.BarsWidth;
            return Chart.GetXByBar(bar, true) + (int)(barsWidth / 2);
        }

        // One bar of slack on each side keeps labels from popping at the chart edges.
        private bool IsNearVisible(int bar)
        {
            var container = Chart.PriceChartContainer;
            return bar >= container.FirstVisibleBarNumber - 1 && bar <= container.LastVisibleBarNumber + 1;
        }

        private decimal GetTickSize()
        {
            var tickSize = InstrumentInfo?.TickSize ?? 0m;
            return tickSize > 0 ? tickSize : FallbackTickSize;
        }

        private static string FormatElapsed(TimeSpan span)
        {
            if (span < TimeSpan.Zero)
                span = span.Negate();

            if (span.TotalHours >= 1)
                return string.Format(CultureInfo.InvariantCulture, "{0:0}h {1:00}m", Math.Floor(span.TotalHours), span.Minutes);

            if (span.TotalMinutes >= 1)
                return string.Format(CultureInfo.InvariantCulture, "{0:0}m {1:00}s", Math.Floor(span.TotalMinutes), span.Seconds);

            return string.Format(CultureInfo.InvariantCulture, "{0:0}s", span.TotalSeconds);
        }

        #endregion
    }
}
