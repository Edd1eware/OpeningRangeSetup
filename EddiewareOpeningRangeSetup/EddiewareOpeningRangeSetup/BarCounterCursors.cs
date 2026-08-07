using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Drawing;
using OFT.Rendering;                // StdCursor
using OFT.Rendering.Context;        // RenderContext
using OFT.Rendering.Control;        // RenderControlMouseEventArgs, RenderControlMouseButtons
using OFT.Rendering.Tools;          // RenderPen, RenderFont, RenderStringFormat

namespace ATAS.Indicators
{
    // Two draggable vertical rulers ("Cursor A" / "Cursor B") that number and count the
    // candles enclosed between them.
    //
    // ANCHORING: each cursor sits on the LEFT EDGE of a bar, never on its centre. A
    // measuring cursor has to live BETWEEN candles, otherwise "does the bar under the
    // cursor count?" has no answer. With edge anchoring the enclosed range is the
    // half-open interval [min, max), so the total is exactly max - min.
    //
    // The rightmost usable anchor is TotalBars — one past the last bar, i.e. the RIGHT
    // edge of the newest candle. Without it the pair could never enclose the forming bar
    // and the home position would be off by one.
    [DisplayName("Contador de velas (cursores A/B)")]
    public class BarCounterCursors : Indicator
    {
        private const int CursorNone = 0;
        private const int CursorA = 1;
        private const int CursorB = 2;

        // Bar indices live in private fields on purpose: ATAS serializes public
        // properties into the chart template, and a bar index means nothing after a data
        // reload — the same integer points at a different moment of the market. They are
        // re-seeded per session instead.
        private int _cursorBarA = -1;
        private int _cursorBarB = -1;
        private int _draggingCursor = CursorNone;

        private readonly RenderFont _labelFont = new RenderFont("Arial", 11, FontStyle.Bold);
        private readonly RenderFont _numberFont = new RenderFont("Arial", 11, FontStyle.Bold);
        private readonly RenderStringFormat _centerFormat = new RenderStringFormat
        {
            Alignment = StringAlignment.Center,
            LineAlignment = StringAlignment.Center
        };

        [Display(Name = "Numerar velas entre cursores", Order = 10)]
        public bool ShowBarNumbers { get; set; } = true;

        [Display(Name = "Máx velas a numerar", Order = 20)]
        public int MaxNumberedBars { get; set; } = 60;

        [Display(Name = "Mostrar total y duración", Order = 30)]
        public bool ShowSummary { get; set; } = true;

        [Display(Name = "Sombrear zona entre cursores", Order = 40)]
        public bool ShadeSpan { get; set; } = true;

        [Display(Name = "Grosor de línea (px)", Order = 50)]
        public int CursorLineWidth { get; set; } = 2;

        [Display(Name = "Tolerancia de arrastre (px)", Order = 60)]
        public int CursorGrabTolerancePx { get; set; } = 7;

        [Display(Name = "Velas en posición home", Order = 70)]
        public int HomeSpanBars { get; set; } = 6;

        [Display(Name = "Color", Order = 80)]
        public Color CursorColor { get; set; } = Color.Orange;

        public BarCounterCursors()
        {
            Name = "Contador de velas (cursores A/B)";
            DrawAbovePrice = true;
            DenyToChangePanel = true;

            // Final, not LatestBar: this is a full-chart overlay that must repaint on
            // every scroll and zoom, not only when the newest candle changes.
            EnableCustomDrawing = true;
            SubscribeToDrawingEvents(DrawingLayouts.Final);
        }

        // Event-driven overlay; nothing to compute per bar.
        protected override void OnCalculate(int bar, decimal value) { }

        // ── Rendering ─────────────────────────────────────────────────────────

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (ChartInfo == null || Container == null)
                return;

            var container = ChartInfo.PriceChartContainer;
            if (container == null || container.TotalBars <= 0)
                return;

            SeedCursorsIfNeeded(container);

            var region = Container.Region;
            var xA = ChartInfo.GetXByBar(_cursorBarA, true);
            var xB = ChartInfo.GetXByBar(_cursorBarB, true);

            var first = Math.Min(_cursorBarA, _cursorBarB);
            var last = Math.Max(_cursorBarA, _cursorBarB);

            if (ShadeSpan)
            {
                var left = Math.Min(xA, xB);
                var width = Math.Abs(xB - xA);

                if (width > 0)
                {
                    context.FillRectangle(
                        Color.FromArgb(22, CursorColor.R, CursorColor.G, CursorColor.B),
                        new Rectangle(left, region.Top, width, region.Height));
                }
            }

            var pen = new RenderPen(CursorColor, Math.Max(1, CursorLineWidth));
            context.DrawLine(pen, xA, region.Top, xA, region.Bottom);
            context.DrawLine(pen, xB, region.Top, xB, region.Bottom);

            DrawCursorHandle(context, xA, region, "Cursor A");
            DrawCursorHandle(context, xB, region, "Cursor B");

            if (ShowBarNumbers)
                DrawBarNumbers(context, ChartInfo, container, region, first, last);

            if (ShowSummary)
                DrawSummary(context, region, first, last, Math.Min(xA, xB), Math.Max(xA, xB));
        }

        // Label anchored at the bottom of the panel, like a measuring-tool handle.
        private void DrawCursorHandle(RenderContext context, int x, Rectangle region, string text)
        {
            var size = context.MeasureString(text, _labelFont);
            var box = new Rectangle(x + 3, region.Bottom - size.Height - 6, size.Width + 8, size.Height + 4);

            if (box.Right > region.Right)
                box.X = x - box.Width - 3;

            context.FillRectangle(Color.FromArgb(200, 20, 20, 20), box);
            context.DrawString(text, _labelFont, CursorColor, box, _centerFormat);
        }

        // Numbers every candle in [first, last): the candles actually enclosed by the lines.
        private void DrawBarNumbers(
            RenderContext context, IChart chart, IChartContainer container,
            Rectangle region, int first, int last)
        {
            var span = last - first;
            if (span <= 0 || span > Math.Max(1, MaxNumberedBars))
                return;

            var from = Math.Max(first, container.FirstVisibleBarNumber);
            var to = Math.Min(last - 1, container.LastVisibleBarNumber);

            for (var bar = from; bar <= to; bar++)
            {
                if (bar < 0 || bar >= CurrentBar)
                    continue;

                var candle = GetCandle(bar);
                var number = (bar - first + 1).ToString();
                var size = context.MeasureString(number, _numberFont);

                // Midpoint between the bar's two edges: robust regardless of how the
                // isStartOfBar flag is interpreted.
                var center = (chart.GetXByBar(bar, true) + chart.GetXByBar(bar + 1, true)) / 2;
                var y = chart.GetYByPrice(candle.High, false) - size.Height - 4;

                if (y < region.Top)
                    y = region.Top;

                context.DrawString(
                    number,
                    _numberFont,
                    Color.White,
                    new Rectangle(center - size.Width / 2, y, size.Width, size.Height),
                    _centerFormat);
            }
        }

        private void DrawSummary(
            RenderContext context, Rectangle region, int first, int last, int leftX, int rightX)
        {
            var span = last - first;
            var text = span == 1 ? "1 vela" : $"{span} velas";

            // `last` is an edge anchor and may sit one past the final bar, so clamp it
            // back onto a real candle before reading its timestamp.
            var lastCandleBar = Math.Min(last, CurrentBar - 1);

            if (span > 0 && first >= 0 && lastCandleBar > first && lastCandleBar < CurrentBar)
            {
                var elapsed = GetCandle(lastCandleBar).Time - GetCandle(first).Time;
                if (elapsed > TimeSpan.Zero)
                    text += $"  ·  {FormatElapsed(elapsed)}";
            }

            var size = context.MeasureString(text, _labelFont);
            var box = new Rectangle(
                (leftX + rightX) / 2 - (size.Width + 10) / 2,
                region.Top + 4,
                size.Width + 10,
                size.Height + 4);

            if (box.Left < region.Left)
                box.X = region.Left;
            if (box.Right > region.Right)
                box.X = region.Right - box.Width;

            context.FillRectangle(Color.FromArgb(215, 20, 20, 20), box);
            context.DrawRectangle(new RenderPen(CursorColor, 1), box);
            context.DrawString(text, _labelFont, CursorColor, box, _centerFormat);
        }

        private static string FormatElapsed(TimeSpan elapsed)
        {
            return elapsed.TotalHours >= 1
                ? $"{(int)elapsed.TotalHours}h {elapsed.Minutes:00}m"
                : elapsed.TotalMinutes >= 1
                    ? $"{(int)elapsed.TotalMinutes}m {elapsed.Seconds:00}s"
                    : $"{(int)elapsed.TotalSeconds}s";
        }

        // ── Mouse interaction ─────────────────────────────────────────────────

        public override bool ProcessMouseDown(RenderControlMouseEventArgs e)
        {
            if (e == null)
                return false;

            if (e.Button != RenderControlMouseButtons.Left)
                return base.ProcessMouseDown(e);

            var hit = HitTestCursor(e.X, e.Y);
            if (hit == CursorNone)
                return base.ProcessMouseDown(e);

            _draggingCursor = hit;
            return true;                       // consume: stop the chart from panning
        }

        public override bool ProcessMouseMove(RenderControlMouseEventArgs e)
        {
            if (e == null)
                return false;

            if (_draggingCursor == CursorNone)
                return base.ProcessMouseMove(e);

            var bar = ResolveBarFromMouse(e.X);
            if (bar < 0)
                return true;

            if (_draggingCursor == CursorA)
                _cursorBarA = bar;
            else
                _cursorBarB = bar;

            RedrawChart();
            return true;
        }

        // Double-click on either cursor snaps the pair back to the home position.
        public override bool ProcessMouseDoubleClick(RenderControlMouseEventArgs e)
        {
            if (e == null)
                return false;

            if (HitTestCursor(e.X, e.Y) == CursorNone)
                return base.ProcessMouseDoubleClick(e);

            var container = ChartInfo?.PriceChartContainer;
            if (container == null || container.TotalBars < 2)
                return base.ProcessMouseDoubleClick(e);

            MoveCursorsHome(container);
            RedrawChart();
            return true;
        }

        public override bool ProcessMouseUp(RenderControlMouseEventArgs e)
        {
            if (_draggingCursor == CursorNone)
                return base.ProcessMouseUp(e);

            _draggingCursor = CursorNone;
            RedrawChart();
            return true;
        }

        public override StdCursor GetCursor(RenderControlMouseEventArgs e)
        {
            if (e == null)
                return StdCursor.NULL;

            if (_draggingCursor != CursorNone || HitTestCursor(e.X, e.Y) != CursorNone)
                return StdCursor.SizeWE;

            return base.GetCursor(e);
        }

        // Returns CursorA / CursorB when the pointer is within grab distance of a line.
        private int HitTestCursor(int x, int y)
        {
            if (ChartInfo == null || Container == null)
                return CursorNone;

            var container = ChartInfo.PriceChartContainer;
            if (container == null || container.TotalBars <= 0)
                return CursorNone;

            var region = Container.Region;
            if (y < region.Top || y > region.Bottom)
                return CursorNone;

            SeedCursorsIfNeeded(container);

            var tolerance = Math.Max(3, CursorGrabTolerancePx);
            var distanceA = Math.Abs(x - ChartInfo.GetXByBar(_cursorBarA, true));
            var distanceB = Math.Abs(x - ChartInfo.GetXByBar(_cursorBarB, true));

            if (distanceA > tolerance && distanceB > tolerance)
                return CursorNone;

            return distanceA <= distanceB ? CursorA : CursorB;
        }

        // Snaps to the nearest bar EDGE (not centre). Deliberately does NOT use
        // MouseLocationInfo.BarBelowMouse, which resolves to the bar the pointer is over
        // rather than the closest edge, and can never return the anchor one past the
        // last bar — which would make the home position unreachable.
        private int ResolveBarFromMouse(int x)
        {
            var chart = ChartInfo;
            var container = chart?.PriceChartContainer;
            if (chart == null || container == null || container.TotalBars <= 0)
                return -1;

            var from = Math.Max(0, container.FirstVisibleBarNumber);
            var to = Math.Min(MaxCursorAnchor(container), container.LastVisibleBarNumber + 1);

            var best = -1;
            var bestDistance = int.MaxValue;

            for (var bar = from; bar <= to; bar++)
            {
                var distance = Math.Abs(x - chart.GetXByBar(bar, true));
                if (distance >= bestDistance)
                    continue;

                bestDistance = distance;
                best = bar;
            }

            return best < 0 ? -1 : ClampBar(best, container);
        }

        // ── Home position ─────────────────────────────────────────────────────

        // B on the RIGHT edge of the newest bar, A HomeSpanBars back, so the span
        // encloses exactly the last HomeSpanBars candles (current bar included). Applied
        // on first render and whenever a data reload left the indices out of range —
        // never when new bars are born, otherwise the ruler would drift while measuring.
        private void SeedCursorsIfNeeded(IChartContainer container)
        {
            if (container.TotalBars < 2)
                return;

            var maxAnchor = MaxCursorAnchor(container);

            if (_cursorBarA >= 0 && _cursorBarB >= 0 &&
                _cursorBarA <= maxAnchor && _cursorBarB <= maxAnchor)
            {
                return;
            }

            MoveCursorsHome(container);
        }

        private void MoveCursorsHome(IChartContainer container)
        {
            var span = Math.Max(1, HomeSpanBars);

            _cursorBarB = MaxCursorAnchor(container);
            _cursorBarA = ClampBar(_cursorBarB - span, container);

            if (_cursorBarA == _cursorBarB)
                _cursorBarA = ClampBar(_cursorBarB - 1, container);
        }

        // Cursors anchor to bar LEFT edges, so the rightmost usable anchor is one past
        // the last bar — that is the right edge of the newest candle.
        private static int MaxCursorAnchor(IChartContainer container)
        {
            return container.TotalBars;
        }

        private static int ClampBar(int bar, IChartContainer container)
        {
            if (bar < 0)
                return 0;

            var maxAnchor = MaxCursorAnchor(container);
            return bar > maxAnchor ? maxAnchor : bar;
        }
    }
}
