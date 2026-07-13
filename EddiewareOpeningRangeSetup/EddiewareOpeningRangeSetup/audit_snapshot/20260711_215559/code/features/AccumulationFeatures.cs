using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Group 18 — Acumulación sobre la ventana OR->break (rango, vol, delta, eficiencia).
    public static class AccumulationFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var win = c.Window(20);
            var tick = c.Tick;

            double hi = double.MinValue, lo = double.MaxValue, vol = 0, delta = 0;
            foreach (var b in win)
            {
                if (b.High > hi) hi = b.High;
                if (b.Low < lo) lo = b.Low;
                vol += b.Volume;
                delta += b.Delta;
            }
            var rangeTicks = (hi - lo) / tick;
            var netMove = Math.Abs(win[win.Count - 1].Close - win[0].Open) / tick;

            row.Add("range_ticks", rangeTicks);
            row.Add("range_bars", win.Count);
            row.Add("range_volume", vol);
            row.Add("range_delta", delta);
            row.Add("range_efficiency", rangeTicks > 0 ? netMove / rangeTicks : double.NaN);
            row.Add("range_rotation", vol > 0 ? delta / vol : double.NaN);
        }
    }
}
