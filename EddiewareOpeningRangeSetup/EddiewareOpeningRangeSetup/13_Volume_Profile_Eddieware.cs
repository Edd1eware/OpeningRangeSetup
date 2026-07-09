using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Text;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    // Volume_Profile_Eddieware
    // -------------------------
    // Two NY-time (DST aware) session volume profiles for the NQ:
    //
    //  1) CONTEXT profile (default 08:30-09:30 NY): fixed POC/VAH/VAL plus a fully
    //     quantitative D/P/b/double/trend shape classification. P suggests bullish
    //     directional context, b bearish, and D neutral/balanced.
    //
    //  2) FIRST-MINUTE LVN profile (default 09:30-09:31 NY): frozen exactly at 09:31.
    //     A level qualifies only when its volume is lower than both configurable neighbor
    //     groups and below the configured neighbor/POC ratios. The clearest qualifying
    //     level is revealed at 09:31 as one green line; later bars never alter its inputs.
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
        private readonly HashSet<int> _researchExportedBars = new();

        private DateTime _currentDate = DateTime.MinValue;
        private int _lastBuiltBar = -1;
        private DateTime _researchExportDate = DateTime.MinValue;
        private bool _researchFileKnownCreated;
        private int _researchExportedRowCount;

        private const string ResearchTargetDateFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\target_trade_result_date.txt";

        // ---- Window inputs (NY time) ----

        [DisplayName("Direction Start (NY)")]
        [Category("Windows")]
        public TimeSpan DirectionStartNy { get; set; } = new TimeSpan(8, 30, 0);

        [DisplayName("Direction End (NY)")]
        [Category("Windows")]
        public TimeSpan DirectionEndNy { get; set; } = new TimeSpan(9, 30, 0);

        [DisplayName("LVN Start (NY)")]
        [Category("Windows")]
        public TimeSpan LvnStartNy { get; set; } = new TimeSpan(9, 30, 0);

        [DisplayName("LVN End (NY)")]
        [Category("Windows")]
        public TimeSpan LvnEndNy { get; set; } = new TimeSpan(9, 31, 0);

        // ---- Profile inputs ----

        [DisplayName("Value Area %")]
        [Category("Profile")]
        public decimal ValueAreaPct { get; set; } = 70m;

        [DisplayName("LVN Neighbor Levels")]
        [Category("Profile")]
        public int LvnNeighborLevels { get; set; } = 2;

        [DisplayName("LVN Max % of Neighbors")]
        [Category("Profile")]
        public decimal LvnMaxPercentOfNeighbors { get; set; } = 50m;

        [DisplayName("LVN Min Volume")]
        [Category("Profile")]
        public decimal MinLvnVolume { get; set; } = 1m;

        [DisplayName("LVN Max % of POC")]
        [Category("Profile")]
        public decimal MaxLvnVolumePercentOfPoc { get; set; } = 50m;

        [DisplayName("LVN Min Profile Volume")]
        [Category("Profile")]
        public decimal MinTotalVolumeAtLvnProfile { get; set; } = 1m;

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

        // ---- Research export (closed footprint bars only) ----

        [DisplayName("Enable LVN Research Export")]
        [Category("Research Export")]
        public bool EnableResearchExport { get; set; } = true;

        [DisplayName("Research Export Folder")]
        [Category("Research Export")]
        public string ResearchExportFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\lvn_research_raw";

        [DisplayName("Research Symbol")]
        [Category("Research Export")]
        public string ResearchSymbol { get; set; } = "NQ";

        [DisplayName("Research End (NY)")]
        [Category("Research Export")]
        public TimeSpan ResearchEndNy { get; set; } = new TimeSpan(9, 40, 0);

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
        [Browsable(false)] public string ProfileShape { get; private set; } = "UNKNOWN";
        [Browsable(false)] public string ShapeBias { get; private set; } = "NEUTRAL";
        [Browsable(false)] public decimal ShapeConfidencePct { get; private set; }
        [Browsable(false)] public decimal ShapeProbD { get; private set; }
        [Browsable(false)] public decimal ShapeProbP { get; private set; }
        [Browsable(false)] public decimal ShapeProbB { get; private set; }
        [Browsable(false)] public decimal ShapeProbDouble { get; private set; }
        [Browsable(false)] public decimal ShapeProbTrendUp { get; private set; }
        [Browsable(false)] public decimal ShapeProbTrendDown { get; private set; }
        [Browsable(false)] public decimal ShapeProbUnknown { get; private set; }

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

            // Export bar-1 only: its footprint is closed and cannot be revised by future
            // ticks. target_trade_result_date.txt gates the export to the runner's date.
            if (bar > 0)
                ExportClosedResearchBar(bar - 1);
            if (ny.TimeOfDay >= ResearchEndNy)
                WriteResearchDoneMarker(ny.Date);

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
            int dirStartBar = -1, lvnRevealBar = -1;
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
                }

                if (t >= LvnEndNy)
                    lvnRevealBar = j;
            }

            UpdateDirectionOutputs(dirBins, tick, dirClose);
            var lastNyTime = ToNy(GetCandle(lastBar).Time).TimeOfDay;
            if (lastNyTime >= LvnEndNy)
                UpdateLvnOutputs(lvnBins, tick);
            else
                ResetLvnOutputs();
            PublishOutputs();

            ClearLines();
            var endBar = lastBar + ExtendBars;

            if (ShowDirection && HasDirection)
                DrawDirection(dirStartBar < 0 ? lastBar : dirStartBar, endBar, lastBar);

            if (ShowLvn && HasLvn)
                DrawLvn(lvnRevealBar < 0 ? lastBar : lvnRevealBar, endBar);
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
                ResetShapeOutputs();
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
            ClassifyProfileShape(bins, pocBin, lo, hi);
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

            var bg = ShapeBias == "BULLISH" ? Color.DarkGreen
                : ShapeBias == "BEARISH" ? Color.DarkRed
                : Color.DimGray;
            AddLabel(
                $"VPE_SHAPE_{_currentDate:yyyyMMdd}",
                $"SHAPE {ProfileShape}  {ShapeBias}  {ShapeConfidencePct:0}%",
                lastBar,
                DirVah,
                Color.White,
                bg,
                55);
        }

        private void DrawLvn(int startBar, int endBar)
        {
            // FindBestLvn deliberately exposes exactly one level.
            var level = _lvnLevels[0];
            AddLine(startBar, level, endBar, level, Color.LimeGreen, 3);

            if (ShowLabels)
                AddLabel(
                    $"VPE_LVN_{_currentDate:yyyyMMdd}",
                    $"LVN 09:30-09:31  {level:0.00}  Q{LvnConfidencePct:0}",
                    endBar - Math.Max(1, ExtendBars / 3),
                    level,
                    Color.Black,
                    Color.LimeGreen);
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

        // Same candidate definition as the Python research engine. Every qualifying node
        // is exported there; this visual overlay retains the deepest one to keep one line.
        private LvnCandidate? FindBestLvn(Dictionary<int, double> bins, decimal tick)
        {
            ComputeProfile(bins, out var pocBin, out _, out _, out var lo, out var hi);
            var neighbors = Math.Max(1, LvnNeighborLevels);
            if (hi - lo + 1 < neighbors * 2 + 1)
                return null;

            var pocVolume = Get(bins, pocBin);
            double totalVolume = 0;
            for (int k = lo; k <= hi; k++)
                totalVolume += Get(bins, k);
            if (pocVolume <= 0 || totalVolume < (double)MinTotalVolumeAtLvnProfile)
                return null;

            LvnCandidate? best = null;
            for (int k = lo + neighbors; k <= hi - neighbors; k++)
            {
                var volume = Get(bins, k);
                double leftMean = 0, rightMean = 0;
                for (int offset = 1; offset <= neighbors; offset++)
                {
                    leftMean += Get(bins, k - offset);
                    rightMean += Get(bins, k + offset);
                }
                leftMean /= neighbors;
                rightMean /= neighbors;
                var weakerMean = Math.Min(leftMean, rightMean);
                if (weakerMean <= 0 || volume < (double)MinLvnVolume)
                    continue;
                var neighborRatio = volume / weakerMean;
                var pocRatio = volume / pocVolume;
                if (volume >= leftMean || volume >= rightMean ||
                    neighborRatio > Clamp01((double)(LvnMaxPercentOfNeighbors / 100m)) ||
                    pocRatio > Clamp01((double)(MaxLvnVolumePercentOfPoc / 100m)))
                    continue;

                var depth = Clamp01(1.0 - neighborRatio);
                var pocDepth = Clamp01(1.0 - pocRatio);
                var distanceToEdge = Math.Min(k - lo, hi - k);
                var interior = Clamp01(distanceToEdge / Math.Max(1.0, (hi - lo) / 2.0));
                var score = 0.70 * depth + 0.20 * pocDepth + 0.10 * interior;

                // On an exact tie prefer the structural valley nearer the POC.
                var price = k * (double)tick;
                if (best == null || score > best.Value.Score + 1e-9 ||
                     (Math.Abs(score - best.Value.Score) <= 1e-9 &&
                      Math.Abs(k - pocBin) < Math.Abs(best.Value.Price / (double)tick - pocBin)))
                {
                    best = new LvnCandidate(price, score);
                }
            }

            return best;
        }

        private static double Clamp01(double value) => Math.Max(0.0, Math.Min(1.0, value));

        // Mathematical prototype probabilities, not outcome-calibrated probabilities.
        // The same features/formulas are used by detect_lvn_retest_events.py.
        private void ClassifyProfileShape(Dictionary<int, double> bins, int pocBin, int lo, int hi)
        {
            var n = hi - lo + 1;
            if (n < 3)
            {
                ResetShapeOutputs();
                return;
            }

            var raw = new double[n];
            double total = 0, weighted = 0, maximum = 0;
            for (int i = 0; i < n; i++)
            {
                raw[i] = Get(bins, lo + i);
                total += raw[i];
                weighted += (lo + i) * raw[i];
                maximum = Math.Max(maximum, raw[i]);
            }
            if (total <= 0 || maximum <= 0)
            {
                ResetShapeOutputs();
                return;
            }

            var meanBin = weighted / total;
            double variance = 0, thirdMoment = 0;
            for (int i = 0; i < n; i++)
            {
                var centered = lo + i - meanBin;
                variance += raw[i] * centered * centered;
            }
            variance /= total;
            var sigma = Math.Sqrt(Math.Max(variance, 1e-12));
            for (int i = 0; i < n; i++)
            {
                var standardized = (lo + i - meanBin) / sigma;
                thirdMoment += raw[i] * standardized * standardized * standardized;
            }
            var skew = variance <= 0 ? 0 : thirdMoment / total;

            double upperVolume = 0, lowerVolume = 0, entropy = 0;
            for (int i = 0; i < n; i++)
            {
                var bin = lo + i;
                if (bin > pocBin) upperVolume += raw[i];
                if (bin < pocBin) lowerVolume += raw[i];
                if (raw[i] > 0)
                {
                    var probability = raw[i] / total;
                    entropy -= probability * Math.Log(probability);
                }
            }
            entropy = n > 1 ? entropy / Math.Log(n) : 0;
            var upperShare = upperVolume / total;
            var lowerShare = lowerVolume / total;
            var pocPosition = (double)(pocBin - lo) / Math.Max(1, hi - lo);
            var meanPosition = (meanBin - lo) / Math.Max(1, hi - lo);

            double slopeNumerator = 0, slopeDenominator = 0;
            for (int i = 0; i < n; i++)
            {
                var x = -1.0 + 2.0 * i / Math.Max(1, n - 1);
                slopeNumerator += x * (raw[i] / maximum);
                slopeDenominator += x * x;
            }
            var slope = slopeDenominator > 0 ? slopeNumerator / slopeDenominator : 0;

            var smoothed = new double[n];
            double smoothedMax = 0;
            for (int i = 0; i < n; i++)
            {
                smoothed[i] = 0.50 * raw[i]
                    + (i > 0 ? 0.25 * raw[i - 1] : 0)
                    + (i < n - 1 ? 0.25 * raw[i + 1] : 0);
                smoothedMax = Math.Max(smoothedMax, smoothed[i]);
            }
            var peaks = new List<int>();
            var peakFloor = smoothedMax * 0.35;
            for (int i = 1; i < n - 1; i++)
                if (smoothed[i] >= smoothed[i - 1] && smoothed[i] > smoothed[i + 1] && smoothed[i] >= peakFloor)
                    peaks.Add(i);
            if (peaks.Count == 0)
            {
                int maxIndex = 0;
                for (int i = 1; i < n; i++)
                    if (smoothed[i] > smoothed[maxIndex]) maxIndex = i;
                peaks.Add(maxIndex);
            }
            peaks.Sort((a, b) =>
            {
                var volumeCompare = smoothed[b].CompareTo(smoothed[a]);
                return volumeCompare != 0 ? volumeCompare : a.CompareTo(b);
            });
            if (peaks.Count > 3)
                peaks.RemoveRange(3, peaks.Count - 3);

            double separation = 0, valleyDepth = 0;
            if (peaks.Count >= 2)
            {
                var a = Math.Min(peaks[0], peaks[1]);
                var b = Math.Max(peaks[0], peaks[1]);
                separation = (double)(b - a) / Math.Max(1, n - 1);
                var valley = smoothed[a];
                for (int i = a + 1; i <= b; i++) valley = Math.Min(valley, smoothed[i]);
                var weakerPeak = Math.Min(smoothed[a], smoothed[b]);
                valleyDepth = Clamp01(1.0 - valley / Math.Max(weakerPeak, 1e-12));
            }

            var balance = Math.Exp(-Math.Abs(Math.Log((upperShare + 1e-9) / (lowerShare + 1e-9))));
            var centeredScore = Math.Exp(-Math.Abs(pocPosition - 0.5) / 0.20);
            var symmetric = Math.Exp(-Math.Abs(skew) / 0.85);
            var singleMode = peaks.Count == 1 ? 1.0 : peaks.Count == 2 ? 0.35 : 0.10;
            var upperHeavy = Sigmoid((upperShare - lowerShare - 0.08) / 0.06);
            var lowerHeavy = Sigmoid((lowerShare - upperShare - 0.08) / 0.06);
            var topLocation = Sigmoid((pocPosition - 0.57) / 0.08);
            var bottomLocation = Sigmoid((0.43 - pocPosition) / 0.08);
            var positiveSlope = Sigmoid((slope - 0.08) / 0.08);
            var negativeSlope = Sigmoid((-slope - 0.08) / 0.08);

            var scores = new[]
            {
                Clamp01(balance * centeredScore * symmetric * singleMode),
                Clamp01(upperHeavy * topLocation * (0.55 + 0.45 * Clamp01(-skew / 2.0)) * singleMode),
                Clamp01(lowerHeavy * bottomLocation * (0.55 + 0.45 * Clamp01(skew / 2.0)) * singleMode),
                Clamp01((peaks.Count >= 2 ? 1.0 : 0.0) * separation * 2.0 * valleyDepth),
                Clamp01(positiveSlope * Sigmoid((meanPosition - 0.53) / 0.08) * (0.6 + 0.4 * entropy)),
                Clamp01(negativeSlope * Sigmoid((0.47 - meanPosition) / 0.08) * (0.6 + 0.4 * entropy)),
                0.0
            };
            double strongest = 0;
            for (int i = 0; i < 6; i++) strongest = Math.Max(strongest, scores[i]);
            scores[6] = Clamp01(0.65 - strongest + 0.25 * (1.0 - entropy));

            const double temperature = 0.22;
            var probabilities = new double[scores.Length];
            double logitMax = double.MinValue, denominator = 0;
            for (int i = 0; i < scores.Length; i++) logitMax = Math.Max(logitMax, scores[i] / temperature);
            for (int i = 0; i < scores.Length; i++)
            {
                probabilities[i] = Math.Exp(scores[i] / temperature - logitMax);
                denominator += probabilities[i];
            }
            int winner = 0;
            for (int i = 0; i < probabilities.Length; i++)
            {
                probabilities[i] /= denominator;
                if (probabilities[i] > probabilities[winner]) winner = i;
            }

            var names = new[] { "D", "P", "b", "DOUBLE", "TREND_UP", "TREND_DOWN", "UNKNOWN" };
            ProfileShape = names[winner];
            ShapeBias = winner == 1 || winner == 4 ? "BULLISH"
                : winner == 2 || winner == 5 ? "BEARISH"
                : "NEUTRAL";
            ShapeConfidencePct = (decimal)(probabilities[winner] * 100.0);
            ShapeProbD = (decimal)probabilities[0];
            ShapeProbP = (decimal)probabilities[1];
            ShapeProbB = (decimal)probabilities[2];
            ShapeProbDouble = (decimal)probabilities[3];
            ShapeProbTrendUp = (decimal)probabilities[4];
            ShapeProbTrendDown = (decimal)probabilities[5];
            ShapeProbUnknown = (decimal)probabilities[6];
        }

        private static double Sigmoid(double value)
        {
            if (value >= 0)
            {
                var z = Math.Exp(-value);
                return 1.0 / (1.0 + z);
            }
            var negativeZ = Math.Exp(value);
            return negativeZ / (1.0 + negativeZ);
        }

        private void ResetShapeOutputs()
        {
            ProfileShape = "UNKNOWN";
            ShapeBias = "NEUTRAL";
            ShapeConfidencePct = 0m;
            ShapeProbD = ShapeProbP = ShapeProbB = ShapeProbDouble = 0m;
            ShapeProbTrendUp = ShapeProbTrendDown = ShapeProbUnknown = 0m;
        }

        private void ResetLvnOutputs()
        {
            HasLvn = false;
            LvnPoc = 0m;
            LvnConfidencePct = 0m;
            _lvnLevels.Clear();
        }

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

        private bool IsResearchTargetDate(DateTime nyDate)
        {
            if (!EnableResearchExport)
                return false;
            try
            {
                if (!File.Exists(ResearchTargetDateFile))
                    return false;
                var target = File.ReadAllText(ResearchTargetDateFile).Trim();
                return target == nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            }
            catch
            {
                return false;
            }
        }

        private string ResearchCsvPath(DateTime nyDate) => Path.Combine(
            ResearchExportFolder,
            $"lvn_research_raw_{nyDate:yyyy-MM-dd}_NY.csv");

        private string ResearchDonePath(DateTime nyDate) => Path.Combine(
            ResearchExportFolder,
            $"lvn_research_done_{nyDate:yyyy-MM-dd}.txt");

        private void PrepareResearchDate(DateTime nyDate, string csvPath)
        {
            if (_researchExportDate != nyDate.Date)
            {
                _researchExportDate = nyDate.Date;
                _researchExportedBars.Clear();
                _researchFileKnownCreated = File.Exists(csvPath);
                _researchExportedRowCount = 0;
                return;
            }

            // The runner deletes the target file before a forced same-date replay.
            if (_researchFileKnownCreated && !File.Exists(csvPath))
            {
                _researchExportedBars.Clear();
                _researchFileKnownCreated = false;
                _researchExportedRowCount = 0;
            }
        }

        private void ExportClosedResearchBar(int closedBar)
        {
            try
            {
                var candle = GetCandle(closedBar);
                var ny = ToNy(candle.Time);
                if (!IsResearchTargetDate(ny.Date) ||
                    ny.TimeOfDay < DirectionStartNy || ny.TimeOfDay >= ResearchEndNy)
                    return;

                Directory.CreateDirectory(ResearchExportFolder);
                var path = ResearchCsvPath(ny.Date);
                PrepareResearchDate(ny.Date, path);
                if (_researchExportedBars.Contains(closedBar))
                    return;

                var builder = new StringBuilder();
                if (!File.Exists(path))
                {
                    builder.AppendLine(
                        "timestamp,symbol,price,bid_volume,ask_volume,volume," +
                        "open,high,low,close,input_granularity,source_bar");
                }

                var timestamp = ny.ToString("yyyy-MM-dd HH:mm:ss.fff", CultureInfo.InvariantCulture);
                var open = Convert.ToDecimal(candle.Open).ToString(CultureInfo.InvariantCulture);
                var high = Convert.ToDecimal(candle.High).ToString(CultureInfo.InvariantCulture);
                var low = Convert.ToDecimal(candle.Low).ToString(CultureInfo.InvariantCulture);
                var close = Convert.ToDecimal(candle.Close).ToString(CultureInfo.InvariantCulture);
                var anyLevels = false;

                try
                {
                    foreach (var level in candle.GetAllPriceLevels())
                    {
                        var price = Convert.ToDecimal(level.Price);
                        var bid = Convert.ToDecimal(level.Bid);
                        var ask = Convert.ToDecimal(level.Ask);
                        var volume = bid + ask;
                        builder.Append(timestamp).Append(',')
                            .Append(ResearchSymbol).Append(',')
                            .Append(price.ToString(CultureInfo.InvariantCulture)).Append(',')
                            .Append(bid.ToString(CultureInfo.InvariantCulture)).Append(',')
                            .Append(ask.ToString(CultureInfo.InvariantCulture)).Append(',')
                            .Append(volume.ToString(CultureInfo.InvariantCulture)).Append(',')
                            .Append(open).Append(',').Append(high).Append(',')
                            .Append(low).Append(',').Append(close).Append(',')
                            .Append("FOOTPRINT_BAR,").Append(closedBar).AppendLine();
                        anyLevels = true;
                        _researchExportedRowCount++;
                    }
                }
                catch
                {
                    anyLevels = false;
                }

                if (!anyLevels)
                {
                    var price = Convert.ToDecimal(candle.Close);
                    var volume = Convert.ToDecimal(candle.Volume);
                    builder.Append(timestamp).Append(',')
                        .Append(ResearchSymbol).Append(',')
                        .Append(price.ToString(CultureInfo.InvariantCulture)).Append(",0,0,")
                        .Append(volume.ToString(CultureInfo.InvariantCulture)).Append(',')
                        .Append(open).Append(',').Append(high).Append(',')
                        .Append(low).Append(',').Append(close).Append(',')
                        .Append("BAR_CLOSE_FALLBACK,").Append(closedBar).AppendLine();
                    _researchExportedRowCount++;
                }

                File.AppendAllText(path, builder.ToString(), new UTF8Encoding(false));
                _researchExportedBars.Add(closedBar);
                _researchFileKnownCreated = true;
            }
            catch
            {
                // Research export must never break chart calculation.
            }
        }

        private void WriteResearchDoneMarker(DateTime nyDate)
        {
            try
            {
                if (!IsResearchTargetDate(nyDate) || _researchExportDate != nyDate.Date)
                    return;
                var csvPath = ResearchCsvPath(nyDate);
                if (!File.Exists(csvPath) || _researchExportedRowCount <= 0)
                    return;
                Directory.CreateDirectory(ResearchExportFolder);
                File.WriteAllText(
                    ResearchDonePath(nyDate),
                    $"date={nyDate:yyyy-MM-dd}\nrows={_researchExportedRowCount}\ncompleted_at_ny={DateTime.Now:O}\n",
                    new UTF8Encoding(false));
            }
            catch
            {
                // Marker is diagnostic only.
            }
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
            ResetShapeOutputs();
            ResetLvnOutputs();
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
