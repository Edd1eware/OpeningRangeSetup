using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 5 — Velocidad, en ticks por MINUTO (1 barra 1-min = 1 min). Sin infra HFT
    // ni datos tick: la velocidad es la del precio por vela, no sub-segundo.
    public static class SpeedFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var tick = c.Tick;
            row.Add("speed_ticks_per_min", Math.Abs(ChangeTicks(c, 1, tick)));
            foreach (var n in new[] { 2, 5, 10 })
                row.Add($"speed_ticks_last_{n}min", Math.Abs(ChangeTicks(c, n, tick)));

            var v1 = ChangeTicks(c, 1, tick);
            var v2 = ChangeTicks2(c, 1, 2, tick);   // change between t-1 and t-2
            row.Add("speed_velocity", v1);                 // signed ticks/min
            row.Add("speed_velocity_change", v1 - v2);
            row.Add("speed_acceleration", c.Ctx.VelocitySeries.Slope(5));
        }

        private static double ChangeTicks(FeatureCtx c, int n, double tick)
        {
            var idx = c.I - n;
            if (idx < 0) return double.NaN;
            return (c.Bar.Close - c.Session[idx].Close) / tick;
        }

        private static double ChangeTicks2(FeatureCtx c, int a, int b, double tick)
        {
            var ia = c.I - a; var ib = c.I - b;
            if (ia < 0 || ib < 0) return double.NaN;
            return (c.Session[ia].Close - c.Session[ib].Close) / tick;
        }
    }
}
