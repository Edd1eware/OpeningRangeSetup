using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 4 — Distancias (todas en ticks, con signo: precio - referencia).
    public static class DistanceFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var s = c.Ctx;
            var p = c.Bar.Close;
            var tick = c.Tick;

            row.Add("dist_or_high", D(p, s.OrHigh, tick));
            row.Add("dist_or_low", D(p, s.OrLow, tick));
            row.Add("dist_vwap", D(p, s.Vwap, tick));
            row.Add("dist_session_high", D(p, s.SessionHigh, tick));
            row.Add("dist_session_low", D(p, s.SessionLow, tick));
            row.Add("dist_prev_close", s.HasPrev ? D(p, s.PrevClose, tick) : double.NaN);
            row.Add("dist_prev_high", s.HasPrev ? D(p, s.PrevHigh, tick) : double.NaN);
            row.Add("dist_prev_low", s.HasPrev ? D(p, s.PrevLow, tick) : double.NaN);
            row.Add("dist_ib_high", D(p, s.IbHigh, tick));
            row.Add("dist_ib_low", D(p, s.IbLow, tick));
            row.Add("dist_poc", s.HasPrev ? D(p, s.PrevPoc, tick) : double.NaN);
            row.Add("dist_value_area_high", s.HasPrev ? D(p, s.PrevVah, tick) : double.NaN);
            row.Add("dist_value_area_low", s.HasPrev ? D(p, s.PrevVal, tick) : double.NaN);
        }

        private static double D(double price, double reference, double tick) =>
            double.IsNaN(reference) ? double.NaN : (price - reference) / tick;
    }
}
