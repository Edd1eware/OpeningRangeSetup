using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 21 — VWAP de sesión (acumulado hasta el break).
    public static class VwapFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var s = c.Ctx;
            var p = c.Bar.Close;
            var tick = c.Tick;
            var vwap = s.Vwap;
            var dist = double.IsNaN(vwap) ? double.NaN : (p - vwap) / tick;

            row.Add("vwap_above", !double.IsNaN(vwap) && p > vwap ? 1 : 0);
            row.Add("vwap_below", !double.IsNaN(vwap) && p < vwap ? 1 : 0);
            row.Add("vwap_cross", CrossedVwap(c) ? 1 : 0);
            row.Add("vwap_slope", VwapSlope(c, tick));
            row.Add("vwap_distance", dist);
        }

        // Did close cross the running VWAP between the prior bar and this one?
        private static bool CrossedVwap(FeatureCtx c)
        {
            if (c.I < 1) return false;
            var vwap = c.Ctx.Vwap;
            if (double.IsNaN(vwap)) return false;
            var prev = c.Session[c.I - 1].Close;
            var now = c.Bar.Close;
            return (prev - vwap) * (now - vwap) < 0;
        }

        // Proxy slope: change of (close - vwap) over the last 5 bars, since the
        // running VWAP itself is not stored per bar.
        private static double VwapSlope(FeatureCtx c, double tick)
        {
            var vwap = c.Ctx.Vwap;
            if (double.IsNaN(vwap) || c.I < 5) return double.NaN;
            return (c.Bar.Close - c.Session[c.I - 5].Close) / tick / 5.0;
        }
    }
}
