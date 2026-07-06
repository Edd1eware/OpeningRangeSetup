using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 17 — Absorción (proxy delta/precio por vela). Absorción = mucho volumen
    // firmado contra poco movimiento de precio.
    public static class AbsorptionFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var b = c.Bar;
            var tick = c.Tick;
            var moveTicks = Math.Abs(b.Close - b.Open) / tick;
            var rangeTicks = (b.High - b.Low) / tick;
            var buy = b.BuyVolume;
            var sell = b.SellVolume;

            // buy absorption: heavy buying but price capped (small up move);
            // sell absorption: heavy selling but price held.
            row.Add("absorption_buy", moveTicks > 0 ? buy / (moveTicks + 1) : buy);
            row.Add("absorption_sell", moveTicks > 0 ? sell / (moveTicks + 1) : sell);
            row.Add("absorption_volume", b.Volume);
            row.Add("absorption_ratio",
                rangeTicks > 0 ? b.Volume / rangeTicks : double.NaN);
            row.Add("absorption_duration", double.NaN);   // needs tick timing
            row.Add("price_efficiency",
                b.Volume > 0 ? rangeTicks / b.Volume : double.NaN);
            row.Add("volume_per_tick",
                rangeTicks > 0 ? b.Volume / rangeTicks : double.NaN);
            row.Add("delta_per_tick",
                rangeTicks > 0 ? b.Delta / rangeTicks : double.NaN);
        }
    }
}
