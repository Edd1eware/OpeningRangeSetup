using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Group 19 — Volatilidad (ATR, realized vol, std de retornos, tick vol).
    public static class VolatilityFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var tick = c.Tick;
            row.Add("atr_1m", Atr(c, 1, tick));       // last bar true range
            row.Add("atr_5m", Atr(c, 5, tick));
            row.Add("realized_volatility", RealizedVol(c, 30, tick));
            row.Add("std_returns", StdReturns(c, 30, tick));
            row.Add("tick_volatility", c.Ctx.RangeSeries.Std(30));
        }

        private static double Atr(FeatureCtx c, int n, double tick)
        {
            var win = c.Window(n + 1);
            if (win.Count < 2) return double.NaN;
            double sum = 0; int count = 0;
            for (var i = 1; i < win.Count; i++)
            {
                var h = win[i].High; var l = win[i].Low; var pc = win[i - 1].Close;
                var tr = Math.Max(h - l, Math.Max(Math.Abs(h - pc), Math.Abs(l - pc)));
                sum += tr / tick; count++;
            }
            return count > 0 ? sum / count : double.NaN;
        }

        private static double RealizedVol(FeatureCtx c, int n, double tick)
        {
            var rets = Returns(c, n, tick);
            double s = 0;
            foreach (var r in rets) s += r * r;
            return rets.Count > 0 ? Math.Sqrt(s) : double.NaN;
        }

        private static double StdReturns(FeatureCtx c, int n, double tick) =>
            Stats.Std(Returns(c, n, tick));

        private static List<double> Returns(FeatureCtx c, int n, double tick)
        {
            var win = c.Window(n + 1);
            var outp = new List<double>();
            for (var i = 1; i < win.Count; i++)
                outp.Add((win[i].Close - win[i - 1].Close) / tick);
            return outp;
        }
    }
}
