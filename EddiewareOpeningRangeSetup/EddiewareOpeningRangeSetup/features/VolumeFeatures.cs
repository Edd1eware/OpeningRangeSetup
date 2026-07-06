using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 6 — Volumen (ventanas en barras). Percentile/zscore vs session history.
    public static class VolumeFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            foreach (var n in new[] { 1, 2, 5, 10 })
                row.Add($"volume_{n}b", c.Sum(n, b => b.Volume));

            var vs = c.Ctx.VolumeSeries;
            row.Add("volume_rolling", vs.Mean(10));
            row.Add("volume_percentile", vs.Percentile(60));
            row.Add("volume_zscore", vs.ZScore(30));
            var mean = vs.Mean(20);
            row.Add("volume_ratio",
                mean == 0 || double.IsNaN(mean) ? double.NaN : c.Bar.Volume / mean);
        }
    }
}
