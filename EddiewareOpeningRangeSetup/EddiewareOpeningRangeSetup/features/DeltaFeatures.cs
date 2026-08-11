using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Group 7 — Delta (ventanas en barras). cum_delta = sesión hasta el break.
    public static class DeltaFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            foreach (var n in new[] { 1, 2, 5, 10 })
                row.Add($"delta_{n}b", c.Sum(n, b => b.Delta));

            var ds = c.Ctx.DeltaSeries;
            row.Add("delta_cum", c.Ctx.CumDelta);
            row.Add("delta_change", ds.Last - ds.Lag(1));
            row.Add("delta_slope", ds.Slope(10));
            row.Add("delta_acceleration", Accel(ds));
            row.Add("delta_zscore", ds.ZScore(30));
        }

        private static double Accel(RollingSeries s)
        {
            var win = s.Window(10);
            if (win.Count < 6) return double.NaN;
            // slope of the earlier half vs later half -> change of slope
            var half = win.Count / 2;
            var early = new List<double>(half);
            var late = new List<double>(win.Count - half);
            for (var i = 0; i < win.Count; i++)
                (i < half ? early : late).Add(win[i]);
            return Stats.Slope(late) - Stats.Slope(early);
        }
    }
}
