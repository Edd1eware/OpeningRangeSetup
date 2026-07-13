using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 22 — Market Profile vs value area del DÍA PREVIO.
    public static class MarketProfileFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var s = c.Ctx;
            var p = c.Bar.Close;
            var tick = c.Tick;

            if (!s.HasPrev)
            {
                row.Add("mp_inside_value", double.NaN);
                row.Add("mp_outside_value", double.NaN);
                row.Add("mp_above_value", double.NaN);
                row.Add("mp_below_value", double.NaN);
                row.Add("mp_distance_poc", double.NaN);
                row.Add("mp_distance_vah", double.NaN);
                row.Add("mp_distance_val", double.NaN);
                return;
            }

            var inside = p >= s.PrevVal && p <= s.PrevVah;
            var above = p > s.PrevVah;
            var below = p < s.PrevVal;

            row.Add("mp_inside_value", inside ? 1 : 0);
            row.Add("mp_outside_value", inside ? 0 : 1);
            row.Add("mp_above_value", above ? 1 : 0);
            row.Add("mp_below_value", below ? 1 : 0);
            row.Add("mp_distance_poc", (p - s.PrevPoc) / tick);
            row.Add("mp_distance_vah", (p - s.PrevVah) / tick);
            row.Add("mp_distance_val", (p - s.PrevVal) / tick);
        }
    }
}
