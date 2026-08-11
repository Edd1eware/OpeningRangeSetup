using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 25 — Derivadas construibles en 1-min. Las que dependen de book/tape
    // (book_pressure, liquidity_vacuum, queue_*, iceberg_ratio, ...) van en la fase 2
    // (grabador tick) y NO se emiten aquí para no crear columnas fantasma.
    public static class DerivedFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var b = c.Bar;
            var tick = c.Tick;
            var moveTicks = Math.Abs(b.Close - b.Open) / tick;
            var rangeTicks = (b.High - b.Low) / tick;

            row.Add("d_price_efficiency", b.Volume > 0 ? moveTicks / b.Volume : double.NaN);
            row.Add("d_delta_efficiency",
                Math.Abs(b.Delta) > 0 ? moveTicks / Math.Abs(b.Delta) : double.NaN);
            row.Add("d_volume_per_tick", rangeTicks > 0 ? b.Volume / rangeTicks : double.NaN);
            row.Add("d_delta_per_tick", rangeTicks > 0 ? b.Delta / rangeTicks : double.NaN);
            row.Add("d_aggression_ratio", b.Volume > 0 ? b.Delta / b.Volume : double.NaN);
            row.Add("d_large_trade_ratio", LargeTradeRatio(b));
            row.Add("d_rotation_efficiency",
                b.Volume > 0 ? Math.Abs(b.Delta) / b.Volume * rangeTicks : double.NaN);
            row.Add("d_volume_acceleration", c.Ctx.VolumeSeries.Slope(5));
            row.Add("d_delta_acceleration", c.Ctx.DeltaSeries.Slope(5));
            row.Add("d_micro_trend_score", MicroTrend(c));
            row.Add("d_initiative_score", Initiative(c));
            row.Add("d_responsive_score", -Initiative(c));
        }

        // Share of bar volume concentrated in the single heaviest footprint level
        // (proxy for outsized activity when no per-trade stream exists).
        private static double LargeTradeRatio(BarData b)
        {
            if (b.Levels.Count == 0 || b.Volume <= 0) return double.NaN;
            double maxLvl = 0;
            foreach (var l in b.Levels)
            {
                var v = l.Buy + l.Sell;
                if (v > maxLvl) maxLvl = v;
            }
            return maxLvl / b.Volume;
        }

        // Sign of close slope * volume z-score: strong directional participation.
        private static double MicroTrend(FeatureCtx c)
        {
            var slope = c.Ctx.CloseSeries.Slope(5);
            var z = c.Ctx.VolumeSeries.ZScore(30);
            if (double.IsNaN(slope) || double.IsNaN(z)) return double.NaN;
            return Math.Sign(slope) * z;
        }

        // Initiative (Dalton): trading away from prior value with aligned delta.
        private static double Initiative(FeatureCtx c)
        {
            var s = c.Ctx;
            if (!s.HasPrev) return double.NaN;
            var p = c.Bar.Close;
            var awayFromValue = p > s.PrevVah ? 1 : p < s.PrevVal ? -1 : 0;
            var deltaSign = Math.Sign(c.Bar.Delta);
            return awayFromValue * deltaSign;
        }
    }
}
