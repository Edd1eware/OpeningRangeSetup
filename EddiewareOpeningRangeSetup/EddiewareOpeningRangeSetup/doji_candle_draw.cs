using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Drawing;
using OFT.Rendering.Context;       // RenderContext
using OFT.Rendering.Tools;         // RenderPen

namespace ATAS.Indicators
{
    // Draws a vertical line down the middle of bodyless candles, spanning high to low.
    //
    // A doji has open == close, so the platform renders no body at all. On a footprint
    // chart that leaves the cluster cells without the usual body outline, and the candle's
    // price extent becomes hard to read. This overlay paints that missing vertical span.
    //
    // Pure read-only overlay: no orders, no files, no alerts.
    [DisplayName("Doji Candle Draw")]
    public class DojiCandleDraw : Indicator
    {
        private const decimal FallbackTickSize = 0.25m;

        public DojiCandleDraw()
        {
            Name = "Doji Candle Draw";
            EnableCustomDrawing = true;
            SubscribeToDrawingEvents(DrawingLayouts.Final);
            DrawAbovePrice = true;
            DenyToChangePanel = true;
            Panel = IndicatorDataProvider.CandlesPanel;
        }

        #region Settings

        // 0 = strict doji (open == close). Raising it also catches candles whose body is
        // technically non-zero but still renders too thin to see.
        [Display(Name = "Cuerpo maximo para considerar doji (ticks)", GroupName = "Deteccion", Order = 1)]
        [Range(0, 20)]
        public decimal MaxBodyTicks { get; set; } = 0;

        [Display(Name = "Color de la linea", GroupName = "Dibujo", Order = 10)]
        public Color LineColor { get; set; } = Color.Yellow;

        [Display(Name = "Grosor de la linea", GroupName = "Dibujo", Order = 11)]
        [Range(1, 10)]
        public int LineWidth { get; set; } = 2;

        // Lets the mark stick out past the high/low so it stays readable on short candles.
        [Display(Name = "Extension arriba y abajo (pixeles)", GroupName = "Dibujo", Order = 12)]
        [Range(0, 50)]
        public int ExtraLengthPixels { get; set; } = 0;

        #endregion

        // Nothing to compute per bar: the overlay is derived entirely at render time.
        protected override void OnCalculate(int bar, decimal value) { }

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (ChartInfo == null || Container == null || CurrentBar <= 0)
                return;

            var chart = ChartInfo;
            var container = chart.PriceChartContainer;
            var region = Container.Region;
            var pen = new RenderPen(LineColor, LineWidth);
            var tickSize = GetTickSize();
            var tolerance = MaxBodyTicks * tickSize;

            var first = Math.Max(0, container.FirstVisibleBarNumber);
            var last = Math.Min(CurrentBar - 1, container.LastVisibleBarNumber);

            for (var bar = first; bar <= last; bar++)
            {
                var candle = GetCandle(bar);
                if (Math.Abs(candle.Open - candle.Close) > tolerance)
                    continue;

                // isStartOfPriceLevel: true = top edge of that price level's cell.
                // The bottom edge of the low cell is, by definition, the top edge of the cell
                // one tick below it. Deriving it that way makes the span cover whole cells,
                // matching how a real candle body is drawn.
                var yTop = chart.GetYByPrice(candle.High, true);
                var yBottom = chart.GetYByPrice(candle.Low - tickSize, true);
                if (yBottom < region.Top || yTop > region.Bottom)
                    continue;

                // Clamp so a candle running off the panel still draws its visible part.
                yTop = Math.Max(yTop, region.Top);
                yBottom = Math.Min(yBottom, region.Bottom);

                // isStartOfBar: true = left edge of the bar. Half a bar past it is the
                // horizontal center of the footprint cluster.
                var x = chart.GetXByBar(bar, true) + (int)(container.BarsWidth / 2);
                context.DrawLine(pen, x, yTop - ExtraLengthPixels, x, yBottom + ExtraLengthPixels);
            }
        }

        private decimal GetTickSize()
        {
            var tickSize = InstrumentInfo?.TickSize ?? 0m;
            return tickSize > 0 ? tickSize : FallbackTickSize;
        }
    }
}
