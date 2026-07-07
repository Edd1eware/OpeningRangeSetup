using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    // Volume_Profile_Eddieware
    // -------------------------
    // Two NY-time (DST aware) session volume profiles for the NQ:
    //
    //  1) DIRECTION profile  (default 08:30-09:30 NY): a fixed profile that gives the
    //     likely direction. Draws POC + Value Area High/Low and prints a HIGH/LOW/INSIDE
    //     bias from where price sits relative to the value area.
    //
    //  2) LVN developing profile (default 08:30-09:40 NY): a profile that grows one bar
    //     at a time up to 09:40 max. On every new closed bar it is rebuilt, so the Low
    //     Volume Nodes settle minute by minute until a high-probability LVN is found.
    //     A 3-bin smoothed histogram finds interior local valleys, then scores each valley
    //     by depth, acceptance on both shoulders, balance and distance from the profile
    //     tails. Only the clearest qualifying LVN is drawn as one orange line.
    //
    // No file is written. The computed levels are exposed as public read-only OUTPUTS
    // (see the "OUTPUTS" region) so an external exporter/strategy can pull a value when
    // it needs it. Times are compared in America/New_York, so the same setting is correct
    // in EST (UTC-5) and EDT (UTC-4). Volume at price uses footprint levels (Ask+Bid);
    // when a feed carries no levels it falls back to the candle volume at its close.
    [DisplayName("Volume_Profile_Eddieware")]
    public class VolumeProfileEddieware : Indicator
    {
        private const decimal FallbackTickSize = 0.25m;

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private readonly List<TrendLine> _lines = new();
        private readonly List<decimal> _lvnLevels = new();

        private DateTime _currentDate = DateTime.MinValue;
        private int _lastBuiltBar = -1;

        // ---- Window inputs (NY time) ----

        [DisplayName("Direction Start (NY)")]
        [Category("Windows")]
        public TimeSpan DirectionStartNy { get; set; } = new TimeSpan(8, 30, 0);

        [DisplayName("Direction End (NY)")]
        [Category("Windows")]
        public TimeSpan DirectionEndNy { get; set; } = new TimeSpan(9, 30, 0);

        [DisplayName("LVN Start (NY)")]
        [Category("Windows")]
        public TimeSpan LvnStartNy { get; set; } = new TimeSpan(8, 30, 0);

        [DisplayName("LVN End (NY)")]
        [Category("Windows")]
        public TimeSpan LvnEndNy { get; set; } = new TimeSpan(9, 40, 0);

        // ---- Profile inputs ----

        [DisplayName("Value Area %")]
        [Category("Profile")]
        public decimal ValueAreaPct { get; set; } = 70m;

        [DisplayName("LVN Threshold % of POC")]
        [Category("Profile")]
        public decimal LvnThresholdPct { get; set; } = 30m;

        [DisplayName("LVN Shoulder Search (ticks)")]
        [Category("Profile")]
        public int LvnShoulderTicks { get; set; } = 8;

        [DisplayName("LVN Min Shoulder % of POC")]
        [Category("Profile")]
        public decimal LvnMinShoulderPct { get; set; } = 45m;

        [DisplayName("LVN Min Confidence %")]
        [Category("Profile")]
        public decimal LvnMinConfidencePct { get; set; } = 65m;

        [DisplayName("Extend Lines (bars)")]
        [Category("Profile")]
        public int ExtendBars { get; set; } = 120;

        // ---- Show toggles ----

        [DisplayName("Show Direction Profile")]
        [Category("Show")]
        public bool ShowDirection { get; set; } = true;

        [DisplayName("Show LVN Profile")]
        [Category("Show")]
        public bool ShowLvn { get; set; } = true;

        [DisplayName("Show Labels")]
        [Category("Show")]
        public bool ShowLabels { get; set; } = true;

        // ===================== OUTPUTS (read-only, pull on demand) =====================
        // Updated on every rebuild with the current frozen levels. NaN / empty until the
        // matching window has data. These are the price levels of the drawn lines.

        [Browsable(false)] public bool HasDirection { get; private set; }
        [Browsable(false)] public decimal DirPoc { get; private set; }
        [Browsable(false)] public decimal DirVah { get; private set; }
        [Browsable(false)] public decimal DirVal { get; private set; }
        [Browsable(false)] public decimal DirHigh { get; private set; }
        [Browsable(false)] public decimal DirLow { get; private set; }
        [Browsable(false)] public decimal DirRangeTicks { get; private set; }
        [Browsable(false)] public string Direction { get; private set; } = ""; // HIGH / LOW / INSIDE

        [Browsable(false)] public bool HasLvn { get; private set; }
        [Browsable(false)] public decimal LvnPoc { get; private set; }
        [Browsable(false)] public decimal LvnConfidencePct { get; private set; }
        [Browsable(false)] public IReadOnlyList<decimal> LvnLevels => _lvnLevels;

        // Nearest LVN above/below a given price (helper for a consumer).
        public decimal NearestLvnAbove(decimal price)
        {
            decimal best = decimal.MaxValue;
            foreach (var l in _lvnLevels) if (l > price && l < best) best = l;
            return best == decimal.MaxValue ? 0m : best;
        }

        public decimal NearestLvnBelow(decimal price)
        {
            decimal best = decimal.MinValue;
            foreach (var l in _lvnLevels) if (l < price && l > best) best = l;
            return best == decimal.MinValue ? 0m : best;
        }
        // ==============================================================================

        public VolumeProfileEddieware()
        {
            Name = "Volume_Profile_Eddieware";
            DrawAbovePrice = true;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            var candle = GetCandle(bar);
            var ny = ToNy(candle.Time);

            // New session: wipe drawings, outputs and state.
            if (ny.Date != _currentDate)
            {
                _currentDate = ny.Date;
                _lastBuiltBar = -1;
                ClearLines();
                ResetOutputs();
            }

            // Rebuild once per new bar (developing effect for the LVN profile).
            if (bar == _lastBuiltBar)
                return;

            _lastBuiltBar = bar;
            Rebuild(bar);
        }

        // Scan the current session's bars into the two windows, refresh the outputs and
        // redraw. Cheap: only a handful of intraday bars fall inside each window.
        private void Rebuild(int lastBar)
        {
            var dirBins = new Dictionary<int, double>();
            var lvnBins = new Dictionary<int, double>();
            int dirStartBar = -1, lvnStartBar = -1;
            double dirClose = double.NaN;
            var tick = GetTickSize();

            for (int j = lastBar; j >= 0; j--)
            {
                var c = GetCandle(j);
                var ny = ToNy(c.Time);

                if (ny.Date != _currentDate)
                    break; // reached the previous session; stop.

                var t = ny.TimeOfDay;

                if (t >= DirectionStartNy && t < DirectionEndNy)
                {
                    AddCandle(dirBins, c, tick);
                    dirStartBar = j;
                    if (double.IsNaN(dirClose))
                        dirClose = Convert.ToDouble(c.Close); // latest bar in window (loop high->low)
                }

                if (t >= LvnStartNy && t < LvnEndNy)
                {
                    AddCandle(lvnBins, c, tick);
                    lvnStartBar = j;
                }
            }

            UpdateDirectionOutputs(dirBins, tick, dirClose);
            UpdateLvnOutputs(lvnBins, tick);
            PublishOutputs();

            ClearLines();
            var endBar = lastBar + ExtendBars;

            if (ShowDirection && HasDirection)
                DrawDirection(dirStartBar < 0 ? lastBar : dirStartBar, endBar, lastBar);

            if (ShowLvn && HasLvn)
                DrawLvn(lvnStartBar < 0 ? lastBar : lvnStartBar, endBar);
        }

        private static void AddCandle(Dictionary<int, double> bins, dynamic c, decimal tick)
        {
            var t = (double)tick;
            bool any = false;

            try
            {
                foreach (var l in c.GetAllPriceLevels())
                {
                    var price = Convert.ToDouble(l.Price);
                    var vol = Convert.ToDouble(l.Ask) + Convert.ToDouble(l.Bid);
                    var k = (int)Math.Round(price / t);
                    bins.TryGetValue(k, out var v);
                    bins[k] = v + vol;
                    any = true;
                }
            }
            catch { any = false; }

            if (!any)
            {
                // Feed without footprint: dump the whole candle volume at its close.
                var k = (int)Math.Round(Convert.ToDouble(c.Close) / t);
                bins.TryGetValue(k, out var v);
                bins[k] = v + Convert.ToDouble(c.Volume);
            }
        }

        // ---- Compute + store OUTPUTS ----

        private void UpdateDirectionOutputs(Dictionary<int, double> bins, decimal tick, double dirClose)
        {
            if (bins.Count == 0)
            {
                HasDirection = false;
                DirPoc = DirVah = DirVal = DirHigh = DirLow = DirRangeTicks = 0m;
                Direction = "";
                return;
            }

            ComputeProfile(bins, out var pocBin, out var vahBin, out var valBin, out var lo, out var hi);
            DirPoc = (decimal)(pocBin * (double)tick);
            DirVah = (decimal)(vahBin * (double)tick);
            DirVal = (decimal)(valBin * (double)tick);
            DirHigh = (decimal)(hi * (double)tick);
            DirLow = (decimal)(lo * (double)tick);
            DirRangeTicks = hi - lo;
            Direction = double.IsNaN(dirClose)
                ? ""
                : (decimal)dirClose > DirVah ? "HIGH"
                : (decimal)dirClose < DirVal ? "LOW"
                : "INSIDE";
            HasDirection = true;
        }

        private void UpdateLvnOutputs(Dictionary<int, double> bins, decimal tick)
        {
            _lvnLevels.Clear();
            if (bins.Count == 0)
            {
                HasLvn = false;
                LvnPoc = 0m;
                LvnConfidencePct = 0m;
                return;
            }

            ComputeProfile(bins, out var pocBin, out _, out _, out _, out _);
            LvnPoc = (decimal)(pocBin * (double)tick);
            var best = FindBestLvn(bins, tick);
            if (best == null)
            {
                HasLvn = false;
                LvnConfidencePct = 0m;
                return;
            }

            _lvnLevels.Add((decimal)best.Value.Price);
            LvnConfidencePct = (decimal)(best.Value.Score * 100.0);
            HasLvn = true;
        }

        // ---- Drawing (uses the stored outputs) ----

        private void DrawDirection(int startBar, int endBar, int lastBar)
        {
            AddLine(startBar, DirPoc, endBar, DirPoc, Color.Gold, 3);
            AddLine(startBar, DirVah, endBar, DirVah, Color.DodgerBlue, 2);
            AddLine(startBar, DirVal, endBar, DirVal, Color.OrangeRed, 2);

            if (!ShowLabels)
                return;

            AddLabel($"VPE_POC_{_currentDate:yyyyMMdd}", $"POC {DirPoc:0.00}", startBar, DirPoc, Color.Black, Color.Gold);
            AddLabel($"VPE_VAH_{_currentDate:yyyyMMdd}", $"VAH {DirVah:0.00}", startBar, DirVah, Color.White, Color.DodgerBlue);
            AddLabel($"VPE_VAL_{_currentDate:yyyyMMdd}", $"VAL {DirVal:0.00}", startBar, DirVal, Color.White, Color.OrangeRed);

            var bg = Direction == "HIGH" ? Color.DarkGreen
                : Direction == "LOW" ? Color.DarkRed
                : Color.DimGray;
            AddLabel($"VPE_DIR_{_currentDate:yyyyMMdd}", $"DIR {Direction}", lastBar, DirVah, Color.White, bg, 55);
        }

        private void DrawLvn(int startBar, int endBar)
        {
            // FindBestLvn deliberately exposes exactly one level.
            var level = _lvnLevels[0];
            AddLine(startBar, level, endBar, level, Color.Orange, 3);

            if (ShowLabels)
                AddLabel(
                    $"VPE_LVN_{_currentDate:yyyyMMdd}",
                    $"LVN {level:0.00}  {LvnConfidencePct:0}%",
                    endBar - Math.Max(1, ExtendBars / 3),
                    level,
                    Color.Black,
                    Color.Orange);
        }

        private readonly struct LvnCandidate
        {
            public LvnCandidate(double price, double score)
            {
                Price = price;
                Score = score;
            }

            public double Price { get; }
            public double Score { get; }
        }

        // A useful LVN is an interior local minimum, not merely any low-volume tail.
        // Smooth over three bins (the same VP convention used by FeatureScanner), require
        // meaningful accepted volume on both sides, then retain only the highest score.
        private LvnCandidate? FindBestLvn(Dictionary<int, double> bins, decimal tick)
        {
            ComputeProfile(bins, out var pocBin, out _, out _, out var lo, out var hi);
            var n = hi - lo + 1;
            if (n < 7)
                return null;

            var raw = new double[n];
            var smoothed = new double[n];
            for (int i = 0; i < n; i++)
                raw[i] = Get(bins, lo + i);

            double smoothedPeak = 0;
            for (int i = 0; i < n; i++)
            {
                double sum = raw[i];
                int count = 1;
                if (i > 0) { sum += raw[i - 1]; count++; }
                if (i < n - 1) { sum += raw[i + 1]; count++; }
                smoothed[i] = sum / count;
                smoothedPeak = Math.Max(smoothedPeak, smoothed[i]);
            }

            if (smoothedPeak <= 0)
                return null;

            var valleyThreshold = smoothedPeak * Clamp01((double)(LvnThresholdPct / 100m));
            var minShoulder = smoothedPeak * Clamp01((double)(LvnMinShoulderPct / 100m));
            var minScore = Clamp01((double)(LvnMinConfidencePct / 100m));
            var search = Math.Max(2, LvnShoulderTicks);
            var edgeGuard = Math.Min(2, Math.Max(1, (n - 3) / 4));

            LvnCandidate? best = null;
            for (int i = edgeGuard; i < n - edgeGuard; i++)
            {
                var valley = smoothed[i];
                bool localMinimum = valley <= smoothed[i - 1] && valley < smoothed[i + 1];
                if (!localMinimum || valley > valleyThreshold)
                    continue;

                var leftPeak = 0.0;
                var rightPeak = 0.0;
                for (int j = Math.Max(0, i - search); j < i; j++)
                    leftPeak = Math.Max(leftPeak, smoothed[j]);
                for (int j = i + 1; j <= Math.Min(n - 1, i + search); j++)
                    rightPeak = Math.Max(rightPeak, smoothed[j]);

                // Both sides must show accepted volume. This rejects profile tails and
                // one-sided drop-offs that look low only because price stopped trading.
                if (leftPeak < minShoulder || rightPeak < minShoulder)
                    continue;

                var weakShoulder = Math.Min(leftPeak, rightPeak);
                var strongShoulder = Math.Max(leftPeak, rightPeak);
                var depth = Clamp01(1.0 - valley / smoothedPeak);
                var localContrast = Clamp01(1.0 - valley / Math.Max(weakShoulder, 1e-9));
                var shoulderStrength = Clamp01(weakShoulder / smoothedPeak);
                var balance = Clamp01(weakShoulder / Math.Max(strongShoulder, 1e-9));
                var distanceToEdge = Math.Min(i, n - 1 - i);
                var interior = Clamp01(distanceToEdge / Math.Max(1.0, (n - 1) / 2.0));

                var score = 0.35 * depth
                    + 0.30 * localContrast
                    + 0.15 * shoulderStrength
                    + 0.10 * balance
                    + 0.10 * interior;

                // On an exact tie prefer the structural valley nearer the POC.
                var price = (lo + i) * (double)tick;
                if (score >= minScore &&
                    (best == null || score > best.Value.Score + 1e-9 ||
                     (Math.Abs(score - best.Value.Score) <= 1e-9 &&
                      Math.Abs(lo + i - pocBin) < Math.Abs(best.Value.Price / (double)tick - pocBin))))
                {
                    best = new LvnCandidate(price, score);
                }
            }

            return best;
        }

        private static double Clamp01(double value) => Math.Max(0.0, Math.Min(1.0, value));

        // POC bin, value-area edges (expand from POC to ValueAreaPct of total),
        // and the min/max occupied bins.
        private void ComputeProfile(
            Dictionary<int, double> bins,
            out int pocBin, out int vaHighBin, out int vaLowBin,
            out int lo, out int hi)
        {
            pocBin = 0; vaHighBin = 0; vaLowBin = 0;
            lo = int.MaxValue; hi = int.MinValue;
            double pocVol = -1, tot = 0;

            foreach (var kv in bins)
            {
                tot += kv.Value;
                if (kv.Value > pocVol) { pocVol = kv.Value; pocBin = kv.Key; }
                if (kv.Key < lo) lo = kv.Key;
                if (kv.Key > hi) hi = kv.Key;
            }

            double target = (double)(ValueAreaPct / 100m) * tot;
            double acc = pocVol;
            int up = pocBin, dn = pocBin;

            while (acc < target && (up < hi || dn > lo))
            {
                double upVol = up < hi ? Get(bins, up + 1) : -1;
                double dnVol = dn > lo ? Get(bins, dn - 1) : -1;
                if (upVol < 0 && dnVol < 0) break;
                if (upVol >= dnVol) { up++; acc += Math.Max(0, upVol); }
                else { dn--; acc += Math.Max(0, dnVol); }
            }

            vaHighBin = up;
            vaLowBin = dn;
        }

        private static double Get(Dictionary<int, double> bins, int k)
        {
            bins.TryGetValue(k, out var v);
            return v;
        }

        // ---- Drawing helpers ----

        private void AddLine(int bar1, decimal p1, int bar2, decimal p2, Color color, int width)
        {
            var line = new TrendLine(bar1, p1, bar2, p2, new Pen(color, width));
            TrendLines.Add(line);
            _lines.Add(line);
        }

        private void ClearLines()
        {
            foreach (var l in _lines)
                TrendLines.Remove(l);
            _lines.Clear();
        }

        private void AddLabel(string id, string text, int bar, decimal price, Color textColor, Color bgColor, int yOffset = 0)
        {
            AddText(
                id,
                text,
                true,
                bar,
                price,
                yOffset,
                0,
                textColor,
                bgColor,
                bgColor,
                12,
                DrawingText.TextAlign.Center,
                true);
        }

        // Publish the current frozen levels so the exporter can read them by session date.
        private void PublishOutputs()
        {
            VolumeProfileStore.Publish(_currentDate, new VolumeProfileLevels
            {
                HasDirection = HasDirection,
                DirPoc = DirPoc,
                DirVah = DirVah,
                DirVal = DirVal,
                DirHigh = DirHigh,
                DirLow = DirLow,
                DirRangeTicks = DirRangeTicks,
                Direction = Direction,
                HasLvn = HasLvn,
                LvnPoc = LvnPoc,
                LvnLevels = _lvnLevels.ToArray()
            });
        }

        private void ResetOutputs()
        {
            HasDirection = false;
            DirPoc = DirVah = DirVal = DirHigh = DirLow = DirRangeTicks = 0m;
            Direction = "";
            HasLvn = false;
            LvnPoc = 0m;
            LvnConfidencePct = 0m;
            _lvnLevels.Clear();
        }

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        private decimal GetTickSize()
        {
            return FallbackTickSize;
        }
    }
}
