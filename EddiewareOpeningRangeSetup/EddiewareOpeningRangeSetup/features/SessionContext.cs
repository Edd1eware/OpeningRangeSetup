using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Session-level running state, updated once per RTH bar by the scanner. Holds
    // the opening range, session VWAP / hi-lo / initial balance, cumulative delta,
    // the prior session's value area, and rolling series for stats/lags.
    public sealed class SessionContext
    {
        public double Tick = 0.25;
        public DateTime SessionDateNy;

        // Opening range (locked after OR window).
        public bool OrLocked;
        public int OrBars;
        public double OrHigh = double.NaN;
        public double OrLow = double.NaN;
        public double OrOpen = double.NaN;
        public double OrClose = double.NaN;
        public double OrVolume;
        public double OrDelta;
        public double OrVwapNum;
        public double OrVwapDen;
        public double OrVwap => OrVwapDen > 0 ? OrVwapNum / OrVwapDen : double.NaN;

        // Session running aggregates.
        public double SessionHigh = double.NaN;
        public double SessionLow = double.NaN;
        public double VwapNum;
        public double VwapDen;
        public double Vwap => VwapDen > 0 ? VwapNum / VwapDen : double.NaN;
        public double IbHigh = double.NaN;   // 09:30-10:30
        public double IbLow = double.NaN;
        public double CumDelta;

        // Prior session context.
        public bool HasPrev;
        public double PrevClose = double.NaN;
        public double PrevHigh = double.NaN;
        public double PrevLow = double.NaN;
        public double PrevPoc = double.NaN;
        public double PrevVah = double.NaN;
        public double PrevVal = double.NaN;

        // Core rolling series (stats + lags).
        public readonly RollingSeries VelocitySeries = new();   // (close-close[-1])/tick
        public readonly RollingSeries VolumeSeries = new();
        public readonly RollingSeries DeltaSeries = new();
        public readonly RollingSeries RangeSeries = new();       // (high-low)/tick
        public readonly RollingSeries CloseSeries = new();

        private double _prevClose = double.NaN;

        public void ResetForNewSession(DateTime nyDate, double tick)
        {
            SessionDateNy = nyDate;
            Tick = tick;
            OrLocked = false;
            OrBars = 0;
            OrHigh = OrLow = OrOpen = OrClose = double.NaN;
            OrVolume = OrDelta = OrVwapNum = OrVwapDen = 0;
            SessionHigh = SessionLow = double.NaN;
            VwapNum = VwapDen = 0;
            IbHigh = IbLow = double.NaN;
            CumDelta = 0;
            _prevClose = double.NaN;
            // rolling series intentionally NOT cleared: keep cross-session history
            // for lags/stats continuity (bar-based, capped internally).
        }

        // Fold one RTH bar into the running session aggregates + rolling series.
        public void UpdateWithBar(BarData b, bool inInitialBalance)
        {
            if (double.IsNaN(SessionHigh) || b.High > SessionHigh) SessionHigh = b.High;
            if (double.IsNaN(SessionLow) || b.Low < SessionLow) SessionLow = b.Low;

            var typical = (b.High + b.Low + b.Close) / 3.0;
            VwapNum += typical * b.Volume;
            VwapDen += b.Volume;

            if (inInitialBalance)
            {
                if (double.IsNaN(IbHigh) || b.High > IbHigh) IbHigh = b.High;
                if (double.IsNaN(IbLow) || b.Low < IbLow) IbLow = b.Low;
            }

            CumDelta += b.Delta;

            var vel = double.IsNaN(_prevClose) ? 0 : (b.Close - _prevClose) / Tick;
            _prevClose = b.Close;

            VelocitySeries.Push(vel);
            VolumeSeries.Push(b.Volume);
            DeltaSeries.Push(b.Delta);
            RangeSeries.Push((b.High - b.Low) / Tick);
            CloseSeries.Push(b.Close);
        }

        public void UpdateOpeningRange(BarData b)
        {
            if (OrBars == 0)
            {
                OrOpen = b.Open;
                OrHigh = b.High;
                OrLow = b.Low;
            }
            else
            {
                if (b.High > OrHigh) OrHigh = b.High;
                if (b.Low < OrLow) OrLow = b.Low;
            }
            OrClose = b.Close;
            OrVolume += b.Volume;
            OrDelta += b.Delta;
            var typical = (b.High + b.Low + b.Close) / 3.0;
            OrVwapNum += typical * b.Volume;
            OrVwapDen += b.Volume;
            OrBars++;
        }

        // Prior-session value area from a 1-tick volume profile of closes
        // (mirrors the Python `_value_area`, greedy 70%).
        public void FinalizePrevSession(IReadOnlyList<BarData> bars, double tick)
        {
            if (bars.Count == 0) { HasPrev = false; return; }

            var bins = new Dictionary<int, double>();
            double tot = 0;
            foreach (var b in bars)
            {
                var k = (int)Math.Round(b.Close / tick);
                bins.TryGetValue(k, out var v);
                bins[k] = v + b.Volume;
                tot += b.Volume;
            }

            var pocBin = 0; double pocVol = -1;
            foreach (var kv in bins)
                if (kv.Value > pocVol) { pocVol = kv.Value; pocBin = kv.Key; }

            // greedy: add highest-volume bins until >= 70% of total, keep min/max bin.
            var ordered = new List<KeyValuePair<int, double>>(bins);
            ordered.Sort((a, c) => c.Value.CompareTo(a.Value));
            double acc = 0; int lo = int.MaxValue, hi = int.MinValue;
            foreach (var kv in ordered)
            {
                if (kv.Key < lo) lo = kv.Key;
                if (kv.Key > hi) hi = kv.Key;
                acc += kv.Value;
                if (acc >= 0.70 * tot) break;
            }

            PrevPoc = pocBin * tick;
            PrevVal = lo * tick;
            PrevVah = hi * tick;
            PrevClose = bars[bars.Count - 1].Close;
            PrevHigh = Stats.Max(ClosesHighs(bars, true));
            PrevLow = Stats.Min(ClosesHighs(bars, false));
            HasPrev = true;
        }

        private static IReadOnlyList<double> ClosesHighs(IReadOnlyList<BarData> bars, bool high)
        {
            var xs = new List<double>(bars.Count);
            foreach (var b in bars) xs.Add(high ? b.High : b.Low);
            return xs;
        }
    }
}
