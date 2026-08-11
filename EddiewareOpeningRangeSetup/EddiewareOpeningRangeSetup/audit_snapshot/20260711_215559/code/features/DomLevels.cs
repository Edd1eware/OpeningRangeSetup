using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Drawing;
using ATAS.DataFeedsCore;          // MarketDataArg, MarketDataType
using OFT.Rendering.Context;       // RenderContext
using OFT.Rendering.Tools;         // RenderPen, RenderFont

namespace ATAS.Indicators
{
    // DOM Levels overlay (live). Paints each resting order-book level as an ORANGE
    // horizontal line labelled with the number of contracts at that price, refreshing
    // whenever the size at a level changes. Drawn ONLY inside the execution window
    // (09:30–09:50 NY by default).
    //
    // LIVE-ONLY: replay does not reconstruct the order book, so nothing draws in the
    // featsweep — the lines appear only when trading live (or on a live-connected chart).
    // Separate research/overlay indicator: touches NOTHING of the exporter, scanner,
    // exec strategy, or replay-sync.
    [DisplayName("DOM Levels (orange)")]
    public class DomLevels : Indicator
    {
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        [Display(Name = "Ventana inicio NY (HH:mm:ss)", Order = 1)]
        public string StartNy { get; set; } = "09:30:00";

        [Display(Name = "Ventana fin NY (HH:mm:ss)", Order = 2)]
        public string EndNy { get; set; } = "09:50:00";

        [Display(Name = "Contratos mínimos (filtro ruido)", Order = 3)]
        public int MinContracts { get; set; } = 0;

        [Display(Name = "Mostrar etiqueta de contratos", Order = 4)]
        public bool ShowLabels { get; set; } = true;

        // Live book: price -> resting size, rebuilt from incremental depth updates.
        private readonly SortedDictionary<decimal, decimal> _bids = new();
        private readonly SortedDictionary<decimal, decimal> _asks = new();
        private DateTime _lastNy = DateTime.MinValue;

        private static readonly Color OrangeColor = Color.Orange;
        private readonly RenderFont _font = new("Arial", 9);

        public DomLevels()
        {
            Name = "DOM Levels (orange)";
            EnableCustomDrawing = true;
            SubscribeToDrawingEvents(DrawingLayouts.LatestBar);
            DenyToChangePanel = true;
        }

        // Event-driven; nothing to compute per bar.
        protected override void OnCalculate(int bar, decimal value) { }

        // Per-level resting-size updates (DOM). Volume is the NEW resting size at that price;
        // 0 removes the level. Rebuilds the live book and requests a redraw.
        protected override void MarketDepthChanged(MarketDataArg depth)
        {
            base.MarketDepthChanged(depth);
            if (depth == null) return;
            _lastNy = ToNy(depth.Time);

            var book = depth.DataType == MarketDataType.Bid ? _bids : _asks;
            if (depth.Volume <= 0) book.Remove(depth.Price);
            else book[depth.Price] = depth.Volume;

            RedrawChart();
        }

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (ChartInfo == null) return;
            if (!InWindow(_lastNy)) return;

            var region = Container.Region;
            var left = region.Left;
            var right = region.Right;
            var pen = new RenderPen(OrangeColor, 1);

            DrawBook(context, _bids, pen, left, right, region.Top, region.Bottom);
            DrawBook(context, _asks, pen, left, right, region.Top, region.Bottom);
        }

        private void DrawBook(RenderContext context, SortedDictionary<decimal, decimal> book,
            RenderPen pen, int left, int right, int top, int bottom)
        {
            foreach (var kv in book)
            {
                if (kv.Value < MinContracts) continue;
                var y = ChartInfo.GetYByPrice(kv.Key, false);
                if (y < top || y > bottom) continue;              // off-screen
                context.DrawLine(pen, left, y, right, y);
                if (ShowLabels)
                {
                    var text = ((int)kv.Value).ToString();
                    context.DrawString(text, _font, OrangeColor, right - 48, y - 12);
                }
            }
        }

        private bool InWindow(DateTime ny)
        {
            if (ny == DateTime.MinValue) return false;
            var tod = ny.TimeOfDay;
            return tod >= ParseNy(StartNy, new TimeSpan(9, 30, 0))
                && tod < ParseNy(EndNy, new TimeSpan(9, 50, 0));
        }

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        private static TimeSpan ParseNy(string value, TimeSpan fallback)
            => TimeSpan.TryParse(value, out var ts) ? ts : fallback;
    }
}
