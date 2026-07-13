using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 3 — Precio. close/high/low + bar-window changes. bid/ask/spread are NOT
    // available in 1-min history -> emitted as NaN (populated by the tick recorder).
    public static class PriceFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var b = c.Bar;
            var tick = c.Tick;
            row.Add("price_last", b.Close);
            row.Add("price_mid", (b.High + b.Low) / 2.0);

            foreach (var n in new[] { 1, 2, 3, 5, 10 })
                row.Add($"price_change_{n}b", ChangeTicks(c, n, tick));

            row.Add("price_tick_direction", Math.Sign(ChangeTicks(c, 1, tick)));

            // Not reconstructable from 1-min history:
            row.Add("price_bid", double.NaN);
            row.Add("price_ask", double.NaN);
            row.Add("price_spread", double.NaN);
        }

        private static double ChangeTicks(FeatureCtx c, int n, double tick)
        {
            var idx = c.I - n;
            if (idx < 0) return double.NaN;
            return (c.Bar.Close - c.Session[idx].Close) / tick;
        }
    }
}
