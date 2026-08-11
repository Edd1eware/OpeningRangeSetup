using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Reusable volume-at-price profile. Accumulate bars (footprint price levels, fallback
    // to close x volume when a bar carries no levels), then Freeze() to compute POC, the
    // 70% value area (VAH/VAL), High/Low/Range, and HVN/LVN as local extrema of the smoothed
    // histogram. All values are absolute prices; the caller converts distances to ticks.
    public sealed class VolumeProfile
    {
        private readonly Dictionary<int, double> _bins = new();
        private double _tick = 0.25;
        private double _hi = double.NaN;
        private double _lo = double.NaN;

        public bool HasData { get; private set; }
        public double Poc = double.NaN;
        public double Vah = double.NaN;
        public double Val = double.NaN;
        public double High = double.NaN;
        public double Low = double.NaN;
        public double Range = double.NaN;
        public readonly List<double> Hvn = new();
        public readonly List<double> Lvn = new();

        public void Reset(double tick)
        {
            _bins.Clear();
            _tick = tick > 0 ? tick : 0.25;
            _hi = _lo = double.NaN;
            HasData = false;
            Poc = Vah = Val = High = Low = Range = double.NaN;
            Hvn.Clear();
            Lvn.Clear();
        }

        public void Add(BarData b)
        {
            if (double.IsNaN(_hi) || b.High > _hi) _hi = b.High;
            if (double.IsNaN(_lo) || b.Low < _lo) _lo = b.Low;

            if (b.Levels != null && b.Levels.Count > 0)
            {
                foreach (var l in b.Levels)
                {
                    var k = (int)Math.Round(l.Price / _tick);
                    _bins.TryGetValue(k, out var v);
                    _bins[k] = v + l.Buy + l.Sell;
                }
            }
            else
            {
                var k = (int)Math.Round(b.Close / _tick);
                _bins.TryGetValue(k, out var v);
                _bins[k] = v + b.Volume;
            }
        }

        // Snapshot RESULTS (not bins) from another profile, so a live builder can be frozen
        // into a stable slot and then Reset() to start accumulating the next window.
        public void CopyFrom(VolumeProfile s)
        {
            HasData = s.HasData;
            Poc = s.Poc; Vah = s.Vah; Val = s.Val;
            High = s.High; Low = s.Low; Range = s.Range;
            Hvn.Clear(); Hvn.AddRange(s.Hvn);
            Lvn.Clear(); Lvn.AddRange(s.Lvn);
        }

        public void Freeze()
        {
            if (_bins.Count == 0) { HasData = false; return; }

            int pocBin = 0; double pocVol = -1, tot = 0;
            int lo = int.MaxValue, hi = int.MinValue;
            foreach (var kv in _bins)
            {
                tot += kv.Value;
                if (kv.Value > pocVol) { pocVol = kv.Value; pocBin = kv.Key; }
                if (kv.Key < lo) lo = kv.Key;
                if (kv.Key > hi) hi = kv.Key;
            }

            // Value area: expand from POC, each step adding the richer adjacent side, until
            // the accumulated volume reaches 70% of total (standard market-profile method).
            double acc = pocVol; int up = pocBin, dn = pocBin;
            while (acc < 0.70 * tot && (up < hi || dn > lo))
            {
                double upVol = up < hi ? Get(up + 1) : -1;
                double dnVol = dn > lo ? Get(dn - 1) : -1;
                if (upVol < 0 && dnVol < 0) break;
                if (upVol >= dnVol) { up++; acc += Math.Max(0, upVol); }
                else { dn--; acc += Math.Max(0, dnVol); }
            }

            Poc = pocBin * _tick;
            Vah = up * _tick;
            Val = dn * _tick;
            High = _hi;
            Low = _lo;
            Range = (_hi - _lo) / _tick;
            ComputeNodes(lo, hi);
            HasData = true;
        }

        private double Get(int k) { _bins.TryGetValue(k, out var v); return v; }

        // HVN = local maxima above the mean bin volume; LVN = local minima below it, over a
        // 3-bin smoothed contiguous histogram spanning [lo, hi]. Needs a few bins to be meaningful.
        private void ComputeNodes(int lo, int hi)
        {
            var n = hi - lo + 1;
            if (n < 5) return;

            var raw = new double[n];
            for (int i = 0; i < n; i++) raw[i] = Get(lo + i);

            var sm = new double[n];
            double sum = 0;
            for (int i = 0; i < n; i++)
            {
                double s = raw[i]; int c = 1;
                if (i > 0) { s += raw[i - 1]; c++; }
                if (i < n - 1) { s += raw[i + 1]; c++; }
                sm[i] = s / c;
                sum += sm[i];
            }
            var mean = sum / n;

            for (int i = 1; i < n - 1; i++)
            {
                if (sm[i] > mean && sm[i] >= sm[i - 1] && sm[i] > sm[i + 1]) Hvn.Add((lo + i) * _tick);
                if (sm[i] < mean && sm[i] <= sm[i - 1] && sm[i] < sm[i + 1]) Lvn.Add((lo + i) * _tick);
            }
        }

        public double NearestHvn(double price) => Nearest(Hvn, price);
        public double NearestLvn(double price) => Nearest(Lvn, price);

        private static double Nearest(List<double> xs, double price)
        {
            if (xs.Count == 0) return double.NaN;
            double best = xs[0], bd = Math.Abs(xs[0] - price);
            for (int i = 1; i < xs.Count; i++)
            {
                var d = Math.Abs(xs[i] - price);
                if (d < bd) { bd = d; best = xs[i]; }
            }
            return best;
        }
    }
}
