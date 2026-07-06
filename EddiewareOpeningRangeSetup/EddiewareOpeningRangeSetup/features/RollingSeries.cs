using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Bar-based ring buffer for a single scalar (group 23 stats + group 24 lags).
    // Pushed once per RTH bar by the scanner; read at the breakout bar.
    public sealed class RollingSeries
    {
        private readonly List<double> _buf = new();
        private readonly int _cap;

        public RollingSeries(int capacity = 400) => _cap = Math.Max(64, capacity);

        public int Count => _buf.Count;

        public void Push(double v)
        {
            _buf.Add(v);
            if (_buf.Count > _cap) _buf.RemoveAt(0);
        }

        public double Last => _buf.Count == 0 ? double.NaN : _buf[_buf.Count - 1];

        // Lag(0) = last, Lag(1) = one bar back, ...
        public double Lag(int k)
        {
            var idx = _buf.Count - 1 - k;
            return idx < 0 ? double.NaN : _buf[idx];
        }

        // Last n values (or fewer if not enough history).
        public IReadOnlyList<double> Window(int n)
        {
            if (n <= 0 || _buf.Count == 0) return Array.Empty<double>();
            var start = Math.Max(0, _buf.Count - n);
            return _buf.GetRange(start, _buf.Count - start);
        }

        public double Mean(int n) => Stats.Mean(Window(n));
        public double Std(int n) => Stats.Std(Window(n));
        public double Min(int n) => Stats.Min(Window(n));
        public double Max(int n) => Stats.Max(Window(n));
        public double Slope(int n) => Stats.Slope(Window(n));
        public double Percentile(int n) => Stats.PercentileOfLast(Window(n));
        public double ZScore(int n) => Stats.ZScoreOfLast(Window(n));

        // Exponential moving average of the last `period` bars (simple recursive).
        public double Ema(int period)
        {
            var w = Window(period * 3);
            if (w.Count == 0) return double.NaN;
            var alpha = 2.0 / (period + 1);
            var ema = w[0];
            for (var i = 1; i < w.Count; i++) ema = alpha * w[i] + (1 - alpha) * ema;
            return ema;
        }

        // Emits the standard statistical block for this series under `prefix`.
        public void EmitStats(FeatureRow row, string prefix)
        {
            row.Add($"{prefix}_mean_5b", Mean(5));
            row.Add($"{prefix}_mean_10b", Mean(10));
            row.Add($"{prefix}_mean_30b", Mean(30));
            row.Add($"{prefix}_mean_60b", Mean(60));
            row.Add($"{prefix}_std_5b", Std(5));
            row.Add($"{prefix}_std_10b", Std(10));
            row.Add($"{prefix}_std_30b", Std(30));
            row.Add($"{prefix}_min_30b", Min(30));
            row.Add($"{prefix}_max_30b", Max(30));
            row.Add($"{prefix}_percentile", Percentile(60));
            row.Add($"{prefix}_zscore", ZScore(30));
            row.Add($"{prefix}_slope", Slope(10));
            var ema = Ema(10);
            row.Add($"{prefix}_ema", ema);
            row.Add($"{prefix}_ema_ratio",
                ema == 0 || double.IsNaN(ema) ? double.NaN : Last / ema);
        }

        private static readonly int[] LagSet = { 1, 2, 3, 5, 10, 20, 30, 60 };

        public void EmitLags(FeatureRow row, string prefix)
        {
            row.Add($"{prefix}_t", Last);
            foreach (var k in LagSet)
                row.Add($"{prefix}_t{k}", Lag(k));
        }
    }
}
