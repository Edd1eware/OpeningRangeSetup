using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 2 — Opening Range. Computed from the locked OR in SessionContext.
    public static class OpeningRangeFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var s = c.Ctx;
            var tick = c.Tick;
            var range = (s.OrHigh - s.OrLow);
            var rangeTicks = range / tick;
            var body = Math.Abs(s.OrClose - s.OrOpen) / tick;
            var upperWick = (s.OrHigh - Math.Max(s.OrOpen, s.OrClose)) / tick;
            var lowerWick = (Math.Min(s.OrOpen, s.OrClose) - s.OrLow) / tick;

            row.Add("or_size_ticks", rangeTicks);
            row.Add("or_body_ticks", body);
            row.Add("or_upper_wick", upperWick);
            row.Add("or_lower_wick", lowerWick);
            row.Add("or_delta", s.OrDelta);
            row.Add("or_volume", s.OrVolume);
            row.Add("or_vwap_distance",
                double.IsNaN(s.OrVwap) ? double.NaN : (s.OrClose - s.OrVwap) / tick);
            row.Add("or_duration", s.OrBars);
            row.Add("or_speed", s.OrBars > 0 ? rangeTicks / s.OrBars : double.NaN);
            row.Add("or_balance", s.OrVolume > 0 ? s.OrDelta / s.OrVolume : double.NaN);
        }
    }
}
