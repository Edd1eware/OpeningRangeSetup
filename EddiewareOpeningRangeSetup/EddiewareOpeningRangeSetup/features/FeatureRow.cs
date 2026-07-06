using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace ATAS.Indicators.Atrapados
{
    // One footprint price level (aggregated). Buy = executed at ask, Sell = at bid.
    public sealed class Lvl
    {
        public double Price;
        public double Buy;
        public double Sell;
    }

    // Plain snapshot of a 1-min bar, decoupled from ATAS types so feature modules
    // compile and unit-test without the platform API surface.
    public sealed class BarData
    {
        public int Bar;
        public DateTime TimeNy;
        public double Open;
        public double High;
        public double Low;
        public double Close;
        public double Volume;
        public double Delta;
        public double BuyVolume;
        public double SellVolume;
        public double SecondsFromOpen;
        public IReadOnlyList<Lvl> Levels = Array.Empty<Lvl>();
    }

    // Everything a feature module needs at the breakout bar.
    public sealed class FeatureCtx
    {
        public IReadOnlyList<BarData> Session = Array.Empty<BarData>();
        public int I;                 // index of the breakout bar inside Session
        public SessionContext Ctx = null!;
        public double Tick = 0.25;
        public string BreakDir = "";  // "up" | "down"
        public BarData Bar => Session[I];
        public bool IsUp => BreakDir == "up";

        // Last n bars ending at (and including) the breakout bar I.
        public List<BarData> Window(int n)
        {
            var end = I + 1;
            var start = Math.Max(0, end - n);
            var outp = new List<BarData>(end - start);
            for (var k = start; k < end; k++) outp.Add(Session[k]);
            return outp;
        }

        public double Sum(int n, Func<BarData, double> sel)
        {
            double s = 0;
            foreach (var b in Window(n)) s += sel(b);
            return s;
        }
    }

    // Ordered (name,value) columns. NaN renders as an empty cell. Column order is
    // stable because every module Adds the same features in the same order.
    public sealed class FeatureRow
    {
        private readonly List<string> _names = new();
        private readonly List<string> _cells = new();

        public IReadOnlyList<string> Names => _names;
        public int Count => _cells.Count;

        public void Add(string name, double v)
        {
            _names.Add(name);
            _cells.Add(double.IsNaN(v) || double.IsInfinity(v)
                ? ""
                : v.ToString("0.###############", CultureInfo.InvariantCulture));
        }

        public void Add(string name, bool b) => Add(name, b ? 1d : 0d);
        public void Add(string name, int i) => Add(name, (double)i);

        // Text column (e.g. the `fecha` join key). Commas are stripped to keep CSV flat.
        public void AddText(string name, string s)
        {
            _names.Add(name);
            _cells.Add((s ?? "").Replace(',', ' '));
        }

        public string Header() => string.Join(",", _names);

        public string Line() => string.Join(",", _cells);
    }

    // Small numeric helpers over windows of a session (bar-based).
    public static class Stats
    {
        public static double Ticks(double priceDelta, double tick) =>
            tick <= 0 ? double.NaN : priceDelta / tick;

        public static double Mean(IReadOnlyList<double> xs)
        {
            if (xs.Count == 0) return double.NaN;
            double s = 0;
            for (var i = 0; i < xs.Count; i++) s += xs[i];
            return s / xs.Count;
        }

        public static double Std(IReadOnlyList<double> xs)
        {
            if (xs.Count < 2) return double.NaN;
            var m = Mean(xs);
            double s = 0;
            for (var i = 0; i < xs.Count; i++)
            {
                var d = xs[i] - m;
                s += d * d;
            }
            return Math.Sqrt(s / xs.Count);
        }

        public static double Min(IReadOnlyList<double> xs)
        {
            if (xs.Count == 0) return double.NaN;
            var m = xs[0];
            for (var i = 1; i < xs.Count; i++) if (xs[i] < m) m = xs[i];
            return m;
        }

        public static double Max(IReadOnlyList<double> xs)
        {
            if (xs.Count == 0) return double.NaN;
            var m = xs[0];
            for (var i = 1; i < xs.Count; i++) if (xs[i] > m) m = xs[i];
            return m;
        }

        // Ordinary least squares slope of xs against index 0..n-1.
        public static double Slope(IReadOnlyList<double> xs)
        {
            var n = xs.Count;
            if (n < 3) return double.NaN;
            double mx = (n - 1) / 2.0, my = Mean(xs), num = 0, den = 0;
            for (var i = 0; i < n; i++)
            {
                var dx = i - mx;
                num += dx * (xs[i] - my);
                den += dx * dx;
            }
            return den == 0 ? double.NaN : num / den;
        }

        // Fraction of the window <= the last value (0..1).
        public static double PercentileOfLast(IReadOnlyList<double> xs)
        {
            if (xs.Count == 0) return double.NaN;
            var last = xs[xs.Count - 1];
            var c = 0;
            for (var i = 0; i < xs.Count; i++) if (xs[i] <= last) c++;
            return (double)c / xs.Count;
        }

        public static double ZScoreOfLast(IReadOnlyList<double> xs)
        {
            if (xs.Count < 2) return double.NaN;
            var s = Std(xs);
            if (s == 0 || double.IsNaN(s)) return 0;
            return (xs[xs.Count - 1] - Mean(xs)) / s;
        }
    }
}
