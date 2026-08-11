using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using ATAS.DataFeedsCore;

namespace ATAS.Indicators
{
    // Causal tape-based detector for liquidity bursts. It aggregates executions into
    // immutable one-second snapshots and never revises a label after it is emitted.
    [DisplayName("Liquidity Burst Detector")]
    public class LiquidityBurstDetector : Indicator
    {
        private const string Version = "liquidity-burst-detector-2026-07-14-v1";
        private const decimal DefaultTickSize = 0.25m;

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private readonly List<SecondBucket> _history = new();
        private readonly Dictionary<decimal, decimal> _volumeAtPrice = new();

        private SecondBucket? _activeBucket;
        private DateTime _currentNyDate = DateTime.MinValue;
        private decimal _lastTradePrice;
        private int _lastTradeDirection;
        private int _lastFallbackBar = -1;
        private int _tradeCallbacks;
        private int _burstSequence;
        private int _buyPersistence;
        private int _sellPersistence;
        private DateTime _lastBuyBurstUtc = DateTime.MinValue;
        private DateTime _lastSellBurstUtc = DateTime.MinValue;
        private decimal _sessionPv;
        private decimal _sessionVolume;
        private decimal _orHigh = decimal.MinValue;
        private decimal _orLow = decimal.MaxValue;
        private bool _orReady;
        private decimal _lastVelocity1s;
        private decimal _lastVelocity3s;

        [Display(Name = "Export CSV", Order = 1, GroupName = "Output")]
        public bool ExportCsv { get; set; } = true;

        [Display(Name = "Output folder", Order = 2, GroupName = "Output")]
        public string OutputFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";

        [Display(Name = "Gate by target date", Order = 3, GroupName = "Output")]
        public bool GateByTargetDate { get; set; } = false;

        [Display(Name = "Use candle fallback", Order = 4, GroupName = "Output",
            Description = "Use only when tape callbacks are unavailable and the chart is 1-second.")]
        public bool UseCandleFallback { get; set; } = false;

        [Display(Name = "Opening time NY", Order = 10, GroupName = "Session")]
        public string OpeningTimeNy { get; set; } = "09:30:00";

        [Display(Name = "Session end NY", Order = 11, GroupName = "Session")]
        public string SessionEndNy { get; set; } = "16:00:00";

        [Display(Name = "OR minutes", Order = 12, GroupName = "Session")]
        public int OpeningRangeMinutes { get; set; } = 1;

        [Display(Name = "History seconds", Order = 20, GroupName = "Detection")]
        public int HistorySeconds { get; set; } = 300;

        [Display(Name = "Min baseline seconds", Order = 21, GroupName = "Detection")]
        public int MinBaselineSeconds { get; set; } = 30;

        [Display(Name = "Delta zscore threshold", Order = 22, GroupName = "Detection")]
        public decimal DeltaChangeZScoreThreshold { get; set; } = 2.5m;

        [Display(Name = "Delta percentile threshold", Order = 23, GroupName = "Detection")]
        public decimal DeltaPercentileThreshold { get; set; } = 0.95m;

        [Display(Name = "Require percentile", Order = 24, GroupName = "Detection")]
        public bool RequirePercentile { get; set; } = true;

        [Display(Name = "Persistence seconds", Order = 25, GroupName = "Detection")]
        public int PersistenceSeconds { get; set; } = 1;

        [Display(Name = "Cumulative window seconds", Order = 26, GroupName = "Detection")]
        public int CumulativeWindowSeconds { get; set; } = 3;

        [Display(Name = "Min |delta 1s|", Order = 27, GroupName = "Detection")]
        public decimal MinAbsDelta1s { get; set; } = 100m;

        [Display(Name = "Min |delta change 1s|", Order = 28, GroupName = "Detection")]
        public decimal MinAbsDeltaChange1s { get; set; } = 75m;

        [Display(Name = "Min |cumulative delta|", Order = 29, GroupName = "Detection")]
        public decimal MinAbsCumulativeDelta { get; set; } = 150m;

        [Display(Name = "Min trades/sec", Order = 30, GroupName = "Detection")]
        public decimal MinTradesPerSecond { get; set; } = 5m;

        [Display(Name = "Min contracts/sec", Order = 31, GroupName = "Detection")]
        public decimal MinContractsPerSecond { get; set; } = 50m;

        [Display(Name = "Require price velocity", Order = 32, GroupName = "Detection")]
        public bool RequirePriceVelocity { get; set; } = false;

        [Display(Name = "Min velocity ticks/sec", Order = 33, GroupName = "Detection")]
        public decimal MinVelocityTicksPerSecond { get; set; } = 1m;

        [Display(Name = "Cooldown seconds", Order = 34, GroupName = "Detection")]
        public int CooldownSeconds { get; set; } = 5;

        [Display(Name = "Max gap fill seconds", Order = 35, GroupName = "Detection")]
        public int MaxGapFillSeconds { get; set; } = 10;

        [Display(Name = "Profile value area percent", Order = 40, GroupName = "Context")]
        public decimal ProfileValueAreaPercent { get; set; } = 0.70m;

        private decimal Tick => InstrumentInfo?.TickSize ?? DefaultTickSize;

        public LiquidityBurstDetector()
        {
            Name = "Liquidity Burst Detector";
            DrawAbovePrice = true;
            EnableCustomDrawing = false;
        }

        protected override void OnRecalculate()
        {
            base.OnRecalculate();
            ResetAll();
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (!UseCandleFallback || _tradeCallbacks > 0 || bar < 1 || bar == _lastFallbackBar)
                return;

            _lastFallbackBar = bar;
            dynamic candle = GetCandle(bar);
            var candleTimeUtc = ToUtc((DateTime)candle.Time);
            var ny = ToNy(candleTimeUtc);

            if (!IsEligibleDate(ny.Date))
                return;

            var volume = TryGetDecimal(candle, "Volume");
            var delta = TryGetDecimal(candle, "Delta");
            var close = Convert.ToDecimal(candle.Close);
            var high = Convert.ToDecimal(candle.High);
            var low = Convert.ToDecimal(candle.Low);

            ProcessAggregateSample(
                FloorToSecond(candleTimeUtc),
                ny,
                bar,
                close,
                high,
                low,
                volume,
                delta,
                "CandleFallback");
        }

        protected override void OnNewTrade(MarketDataArg trade)
        {
            base.OnNewTrade(trade);
            _tradeCallbacks++;

            var bar = CurrentBar - 1;
            if (bar < 0)
                return;

            var timeUtc = ToUtc(trade.Time);
            var ny = ToNy(timeUtc);

            if (!IsEligibleDate(ny.Date))
                return;

            var price = trade.Price;
            var volume = trade.Volume;
            if (volume <= 0)
                return;

            ProcessTrade(timeUtc, ny, bar, price, volume, trade);
        }

        private void ProcessTrade(DateTime timeUtc, DateTime ny, int bar, decimal price, decimal volume, MarketDataArg trade)
        {
            EnsureSession(ny.Date);
            UpdateSessionContext(ny, price, volume);

            var secondUtc = FloorToSecond(timeUtc);
            if (_activeBucket == null)
            {
                _activeBucket = new SecondBucket(secondUtc, bar, price);
            }
            else if (secondUtc < _activeBucket.SecondUtc)
            {
                ResetSession(ny.Date);
                _activeBucket = new SecondBucket(secondUtc, bar, price);
            }
            else if (secondUtc > _activeBucket.SecondUtc)
            {
                AdvanceToSecond(secondUtc, bar, price);
            }

            var direction = ResolveTradeDirection(trade, price);
            _activeBucket.ApplyTrade(price, volume, direction, bar, "Tape");
            _lastTradePrice = price;
            if (direction != 0)
                _lastTradeDirection = direction;
        }

        private void ProcessAggregateSample(
            DateTime secondUtc,
            DateTime ny,
            int bar,
            decimal close,
            decimal high,
            decimal low,
            decimal volume,
            decimal delta,
            string source)
        {
            if (volume <= 0)
                return;

            EnsureSession(ny.Date);
            UpdateSessionContext(ny, close, volume);

            if (_activeBucket != null && secondUtc > _activeBucket.SecondUtc)
                AdvanceToSecond(secondUtc, bar, close);
            else if (_activeBucket == null || secondUtc < _activeBucket.SecondUtc)
                _activeBucket = new SecondBucket(secondUtc, bar, close);

            _activeBucket.ApplyAggregate(close, high, low, volume, delta, bar, source);
            AdvanceToSecond(secondUtc.AddSeconds(1), bar, close);
        }

        private void AdvanceToSecond(DateTime targetSecondUtc, int bar, decimal carryPrice)
        {
            if (_activeBucket == null)
                return;

            var finished = _activeBucket;
            FinalizeSecond(finished);

            var nextSecond = finished.SecondUtc.AddSeconds(1);
            var gapCount = 0;
            while (nextSecond < targetSecondUtc && gapCount < Math.Max(0, MaxGapFillSeconds))
            {
                var gap = SecondBucket.Empty(nextSecond, bar, carryPrice);
                FinalizeSecond(gap);
                nextSecond = nextSecond.AddSeconds(1);
                gapCount++;
            }

            _activeBucket = new SecondBucket(targetSecondUtc, bar, carryPrice);
        }

        private void FinalizeSecond(SecondBucket bucket)
        {
            var ny = ToNy(bucket.SecondUtc);
            bucket.NyTime = ny;

            if (ny.Date != _currentNyDate)
                ResetSession(ny.Date);

            var features = BuildFeatures(bucket);
            bucket.DeltaChange1s = features.DeltaChange1s;

            if (IsDetectionWindow(ny) && bucket.Trades > 0)
                TryEmitBurst(bucket, features);

            _lastVelocity1s = features.Velocity1s;
            _lastVelocity3s = features.Velocity3s;

            _history.Add(bucket);
            TrimHistory(bucket.SecondUtc);
        }

        private BurstFeatures BuildFeatures(SecondBucket current)
        {
            var previous = _history.Count == 0 ? null : _history[_history.Count - 1];
            var deltaChange = current.Delta - (previous?.Delta ?? 0m);
            var zScore = CalculateZScore(deltaChange);
            var percentile = CalculateAbsPercentile(deltaChange);
            var delta1s = SumDelta(current, 1);
            var delta2s = SumDelta(current, 2);
            var delta3s = SumDelta(current, 3);
            var delta5s = SumDelta(current, 5);
            var delta10s = SumDelta(current, 10);
            var cumulativeDelta = SumDelta(current, Math.Max(1, CumulativeWindowSeconds));
            var velocity1s = CalculateVelocity(current, 1);
            var velocity3s = CalculateVelocity(current, 3);
            var velocity5s = CalculateVelocity(current, 5);
            var buySellRatio = current.SellVolume <= 0
                ? current.BuyVolume > 0 ? current.BuyVolume : 0m
                : current.BuyVolume / current.SellVolume;

            return new BurstFeatures
            {
                Delta1s = delta1s,
                Delta2s = delta2s,
                Delta3s = delta3s,
                Delta5s = delta5s,
                Delta10s = delta10s,
                PeakPositiveDelta = PeakDelta(current, 10, true),
                PeakNegativeDelta = PeakDelta(current, 10, false),
                DeltaChange1s = deltaChange,
                DeltaChangeZScore = zScore,
                DeltaPercentile = percentile,
                BuySellRatio = buySellRatio,
                TradesPerSecond = current.Trades,
                ContractsPerSecond = current.Volume,
                Velocity1s = velocity1s,
                Velocity3s = velocity3s,
                Velocity5s = velocity5s,
                Acceleration1s = velocity1s - _lastVelocity1s,
                Acceleration3s = velocity3s - _lastVelocity3s,
                TicksPerSecond = velocity1s,
                CumulativeDelta = cumulativeDelta
            };
        }

        private void TryEmitBurst(SecondBucket bucket, BurstFeatures features)
        {
            var baselineReady = _history.Count >= Math.Max(1, MinBaselineSeconds);
            var percentilePass = !RequirePercentile || features.DeltaPercentile >= DeltaPercentileThreshold;
            var activityPass =
                features.TradesPerSecond >= MinTradesPerSecond &&
                features.ContractsPerSecond >= MinContractsPerSecond;

            var buyVelocityPass = !RequirePriceVelocity || features.Velocity1s >= MinVelocityTicksPerSecond;
            var sellVelocityPass = !RequirePriceVelocity || features.Velocity1s <= -MinVelocityTicksPerSecond;
            var buyCumulativePass = MinAbsCumulativeDelta <= 0 || features.CumulativeDelta >= MinAbsCumulativeDelta;
            var sellCumulativePass = MinAbsCumulativeDelta <= 0 || features.CumulativeDelta <= -MinAbsCumulativeDelta;

            var buyCore =
                baselineReady &&
                features.Delta1s > MinAbsDelta1s &&
                features.DeltaChange1s > MinAbsDeltaChange1s &&
                features.DeltaChangeZScore >= DeltaChangeZScoreThreshold &&
                percentilePass &&
                activityPass &&
                buyCumulativePass &&
                buyVelocityPass;

            var sellCore =
                baselineReady &&
                features.Delta1s < -MinAbsDelta1s &&
                features.DeltaChange1s < -MinAbsDeltaChange1s &&
                features.DeltaChangeZScore <= -DeltaChangeZScoreThreshold &&
                percentilePass &&
                activityPass &&
                sellCumulativePass &&
                sellVelocityPass;

            _buyPersistence = buyCore ? _buyPersistence + 1 : 0;
            _sellPersistence = sellCore ? _sellPersistence + 1 : 0;

            var persistence = Math.Max(1, PersistenceSeconds);
            if (_buyPersistence >= persistence && !InCooldown("BUY", bucket.SecondUtc))
                EmitBurst(bucket, features, "BUY", "HIGH BUY AGGRESSION", "GREEN");

            if (_sellPersistence >= persistence && !InCooldown("SELL", bucket.SecondUtc))
                EmitBurst(bucket, features, "SELL", "HIGH SELL AGGRESSION", "RED");
        }

        private void EmitBurst(SecondBucket bucket, BurstFeatures features, string side, string label, string colorName)
        {
            _burstSequence++;
            var id = string.Format(
                CultureInfo.InvariantCulture,
                "LB_{0:yyyyMMdd_HHmmss}_{1}_{2:0000}",
                bucket.NyTime,
                side,
                _burstSequence);
            var profile = BuildProfileSnapshot(bucket.Close);
            var snapshot = new BurstSnapshot(
                id,
                bucket.SecondUtc,
                bucket.NyTime,
                bucket.Bar,
                side,
                label,
                colorName,
                bucket.Close,
                features,
                profile,
                Version,
                bucket.Source);

            if (side == "BUY")
                _lastBuyBurstUtc = bucket.SecondUtc;
            else
                _lastSellBurstUtc = bucket.SecondUtc;

            LiquidityBurstSignalBus.Publish(new LiquidityBurstSignalSnapshot(
                snapshot.BurstId,
                snapshot.TimestampNy.Date,
                snapshot.TimestampUtc,
                snapshot.TimestampNy,
                snapshot.Side,
                snapshot.Price,
                snapshot.Features.Delta1s,
                snapshot.Features.DeltaChange1s,
                snapshot.Features.DeltaChangeZScore,
                snapshot.Features.DeltaPercentile,
                snapshot.Features.Velocity1s,
                snapshot.Features.Acceleration1s,
                snapshot.Features.TradesPerSecond,
                snapshot.Features.ContractsPerSecond));

            if (ExportCsv)
                WriteBurstEvent(snapshot);
        }

        private void WriteBurstEvent(BurstSnapshot snapshot)
        {
            try
            {
                Directory.CreateDirectory(OutputFolder);
                var path = Path.Combine(OutputFolder, "burst_events.csv");
                var needsHeader = !File.Exists(path) || new FileInfo(path).Length == 0;
                if (needsHeader)
                    File.AppendAllText(path, BurstSnapshot.CsvHeader + Environment.NewLine);
                File.AppendAllText(path, snapshot.ToCsvRow() + Environment.NewLine);
            }
            catch
            {
                // Research export must never interrupt chart calculation.
            }
        }

        private bool InCooldown(string side, DateTime secondUtc)
        {
            var cooldown = Math.Max(0, CooldownSeconds);
            if (cooldown == 0)
                return false;

            var last = side == "BUY" ? _lastBuyBurstUtc : _lastSellBurstUtc;
            return last != DateTime.MinValue &&
                (secondUtc - last).TotalSeconds < cooldown;
        }

        private bool IsDetectionWindow(DateTime ny)
        {
            var start = ParseNy(OpeningTimeNy, new TimeSpan(9, 30, 0));
            var end = ParseNy(SessionEndNy, new TimeSpan(16, 0, 0));
            return ny.TimeOfDay >= start && ny.TimeOfDay <= end;
        }

        private bool IsEligibleDate(DateTime nyDate)
        {
            if (!GateByTargetDate)
                return true;

            var target = ReadTargetDate();
            return target.HasValue && target.Value.Date == nyDate.Date;
        }

        private void EnsureSession(DateTime nyDate)
        {
            if (nyDate != _currentNyDate)
                ResetSession(nyDate);
        }

        private void ResetSession(DateTime nyDate)
        {
            _currentNyDate = nyDate;
            _activeBucket = null;
            _history.Clear();
            _volumeAtPrice.Clear();
            _lastTradePrice = 0;
            _lastTradeDirection = 0;
            _buyPersistence = 0;
            _sellPersistence = 0;
            _lastBuyBurstUtc = DateTime.MinValue;
            _lastSellBurstUtc = DateTime.MinValue;
            _sessionPv = 0;
            _sessionVolume = 0;
            _orHigh = decimal.MinValue;
            _orLow = decimal.MaxValue;
            _orReady = false;
            _lastVelocity1s = 0;
            _lastVelocity3s = 0;
        }

        private void ResetAll()
        {
            _currentNyDate = DateTime.MinValue;
            _activeBucket = null;
            _history.Clear();
            _volumeAtPrice.Clear();
            _lastTradePrice = 0;
            _lastTradeDirection = 0;
            _lastFallbackBar = -1;
            _tradeCallbacks = 0;
            _burstSequence = 0;
            _buyPersistence = 0;
            _sellPersistence = 0;
            _lastBuyBurstUtc = DateTime.MinValue;
            _lastSellBurstUtc = DateTime.MinValue;
            _sessionPv = 0;
            _sessionVolume = 0;
            _orHigh = decimal.MinValue;
            _orLow = decimal.MaxValue;
            _orReady = false;
            _lastVelocity1s = 0;
            _lastVelocity3s = 0;
        }

        private void UpdateSessionContext(DateTime ny, decimal price, decimal volume)
        {
            var opening = ParseNy(OpeningTimeNy, new TimeSpan(9, 30, 0));
            var orEnd = opening.Add(TimeSpan.FromMinutes(Math.Max(1, OpeningRangeMinutes)));
            if (ny.TimeOfDay >= opening && ny.TimeOfDay < orEnd)
            {
                if (price > _orHigh) _orHigh = price;
                if (price < _orLow) _orLow = price;
            }
            else if (ny.TimeOfDay >= orEnd && _orHigh != decimal.MinValue && _orLow != decimal.MaxValue)
            {
                _orReady = true;
            }

            _sessionPv += price * volume;
            _sessionVolume += volume;

            var tick = Tick <= 0 ? DefaultTickSize : Tick;
            var priceKey = RoundToTick(price, tick);
            if (!_volumeAtPrice.ContainsKey(priceKey))
                _volumeAtPrice[priceKey] = 0;
            _volumeAtPrice[priceKey] += volume;
        }

        private decimal SumDelta(SecondBucket current, int seconds)
        {
            decimal sum = current.Delta;
            var from = current.SecondUtc.AddSeconds(-(Math.Max(1, seconds) - 1));
            for (var i = _history.Count - 1; i >= 0; i--)
            {
                var bucket = _history[i];
                if (bucket.SecondUtc < from)
                    break;
                sum += bucket.Delta;
            }
            return sum;
        }

        private decimal PeakDelta(SecondBucket current, int seconds, bool positive)
        {
            var peak = current.Delta;
            var from = current.SecondUtc.AddSeconds(-(Math.Max(1, seconds) - 1));
            for (var i = _history.Count - 1; i >= 0; i--)
            {
                var bucket = _history[i];
                if (bucket.SecondUtc < from)
                    break;
                if (positive && bucket.Delta > peak)
                    peak = bucket.Delta;
                if (!positive && bucket.Delta < peak)
                    peak = bucket.Delta;
            }
            return peak;
        }

        private decimal CalculateVelocity(SecondBucket current, int seconds)
        {
            if (Tick <= 0)
                return 0;

            var reference = FindReferenceBucket(current.SecondUtc.AddSeconds(-Math.Max(1, seconds)));
            if (reference == null || reference.Close == 0)
                return 0;

            return (current.Close - reference.Close) / Tick / Math.Max(1, seconds);
        }

        private SecondBucket? FindReferenceBucket(DateTime referenceSecondUtc)
        {
            for (var i = _history.Count - 1; i >= 0; i--)
            {
                if (_history[i].SecondUtc <= referenceSecondUtc)
                    return _history[i];
            }
            return null;
        }

        private decimal CalculateZScore(decimal deltaChange)
        {
            if (_history.Count < Math.Max(1, MinBaselineSeconds))
                return 0;

            var count = 0;
            decimal sum = 0;
            var start = Math.Max(0, _history.Count - Math.Max(1, HistorySeconds));
            for (var i = start; i < _history.Count; i++)
            {
                sum += _history[i].DeltaChange1s;
                count++;
            }
            if (count < 2)
                return 0;

            var mean = sum / count;
            decimal variance = 0;
            for (var i = start; i < _history.Count; i++)
            {
                var d = _history[i].DeltaChange1s - mean;
                variance += d * d;
            }

            var std = (decimal)Math.Sqrt((double)(variance / count));
            if (std <= 0)
                return 0;
            return (deltaChange - mean) / std;
        }

        private decimal CalculateAbsPercentile(decimal deltaChange)
        {
            if (_history.Count < Math.Max(1, MinBaselineSeconds))
                return 0;

            var value = Math.Abs(deltaChange);
            var count = 0;
            var lessOrEqual = 0;
            var start = Math.Max(0, _history.Count - Math.Max(1, HistorySeconds));
            for (var i = start; i < _history.Count; i++)
            {
                var prior = Math.Abs(_history[i].DeltaChange1s);
                if (prior <= value)
                    lessOrEqual++;
                count++;
            }
            return count == 0 ? 0 : (decimal)lessOrEqual / count;
        }

        private void TrimHistory(DateTime currentSecondUtc)
        {
            var keepSeconds = Math.Max(HistorySeconds, Math.Max(10, CumulativeWindowSeconds)) + 15;
            var minTime = currentSecondUtc.AddSeconds(-keepSeconds);
            var removeCount = 0;
            while (removeCount < _history.Count && _history[removeCount].SecondUtc < minTime)
                removeCount++;
            if (removeCount > 0)
                _history.RemoveRange(0, removeCount);
        }

        private ProfileSnapshot BuildProfileSnapshot(decimal currentPrice)
        {
            var snapshot = new ProfileSnapshot
            {
                OrHigh = _orReady ? _orHigh : null,
                OrLow = _orReady ? _orLow : null,
                OrWidthTicks = _orReady && Tick > 0 ? (_orHigh - _orLow) / Tick : null,
                Vwap = _sessionVolume > 0 ? _sessionPv / _sessionVolume : null
            };

            if (snapshot.OrHigh.HasValue && Tick > 0)
                snapshot.DistanceToOrHighTicks = (currentPrice - snapshot.OrHigh.Value) / Tick;
            if (snapshot.OrLow.HasValue && Tick > 0)
                snapshot.DistanceToOrLowTicks = (currentPrice - snapshot.OrLow.Value) / Tick;
            if (snapshot.Vwap.HasValue && Tick > 0)
                snapshot.DistanceToVwapTicks = (currentPrice - snapshot.Vwap.Value) / Tick;

            if (_volumeAtPrice.Count == 0)
                return snapshot;

            var prices = new List<decimal>(_volumeAtPrice.Keys);
            prices.Sort();

            var pocIndex = 0;
            var totalVolume = 0m;
            for (var i = 0; i < prices.Count; i++)
            {
                var volume = _volumeAtPrice[prices[i]];
                totalVolume += volume;
                if (volume > _volumeAtPrice[prices[pocIndex]])
                    pocIndex = i;
            }

            snapshot.Poc = prices[pocIndex];

            var target = totalVolume * Math.Clamp(ProfileValueAreaPercent, 0.10m, 0.95m);
            var lo = pocIndex;
            var hi = pocIndex;
            var cumulative = _volumeAtPrice[prices[pocIndex]];
            while (cumulative < target && (lo > 0 || hi < prices.Count - 1))
            {
                var leftVolume = lo > 0 ? _volumeAtPrice[prices[lo - 1]] : -1m;
                var rightVolume = hi < prices.Count - 1 ? _volumeAtPrice[prices[hi + 1]] : -1m;
                if (rightVolume >= leftVolume)
                {
                    hi++;
                    cumulative += _volumeAtPrice[prices[hi]];
                }
                else
                {
                    lo--;
                    cumulative += _volumeAtPrice[prices[lo]];
                }
            }

            snapshot.Val = prices[lo];
            snapshot.Vah = prices[hi];
            snapshot.NearestHvn = FindNearestNode(prices, currentPrice, true);
            snapshot.NearestLvn = FindNearestNode(prices, currentPrice, false);

            if (Tick > 0)
            {
                snapshot.DistanceToPocTicks = snapshot.Poc.HasValue ? (currentPrice - snapshot.Poc.Value) / Tick : null;
                snapshot.DistanceToVahTicks = snapshot.Vah.HasValue ? (currentPrice - snapshot.Vah.Value) / Tick : null;
                snapshot.DistanceToValTicks = snapshot.Val.HasValue ? (currentPrice - snapshot.Val.Value) / Tick : null;
                snapshot.DistanceToHvnTicks = snapshot.NearestHvn.HasValue ? (currentPrice - snapshot.NearestHvn.Value) / Tick : null;
                snapshot.DistanceToLvnTicks = snapshot.NearestLvn.HasValue ? (currentPrice - snapshot.NearestLvn.Value) / Tick : null;
            }

            return snapshot;
        }

        private decimal? FindNearestNode(List<decimal> prices, decimal currentPrice, bool highVolumeNode)
        {
            decimal? bestPrice = null;
            decimal bestDistance = decimal.MaxValue;

            for (var i = 0; i < prices.Count; i++)
            {
                var volume = _volumeAtPrice[prices[i]];
                var left = i > 0 ? _volumeAtPrice[prices[i - 1]] : volume;
                var right = i < prices.Count - 1 ? _volumeAtPrice[prices[i + 1]] : volume;
                var isNode = highVolumeNode
                    ? volume >= left && volume >= right
                    : volume <= left && volume <= right;

                if (!isNode)
                    continue;

                var distance = Math.Abs(currentPrice - prices[i]);
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    bestPrice = prices[i];
                }
            }

            return bestPrice;
        }

        private int ResolveTradeDirection(MarketDataArg trade, decimal price)
        {
            var fromProperty = TryResolveDirectionFromProperties(trade);
            if (fromProperty != 0)
                return fromProperty;

            if (_lastTradePrice > 0)
            {
                if (price > _lastTradePrice)
                    return 1;
                if (price < _lastTradePrice)
                    return -1;
            }

            return _lastTradeDirection;
        }

        private static int TryResolveDirectionFromProperties(object source)
        {
            var names = new[]
            {
                "Direction",
                "AggressorSide",
                "Aggressor",
                "Side",
                "TradeDirection",
                "OrderDirection"
            };

            foreach (var name in names)
            {
                try
                {
                    var property = source.GetType().GetProperty(name);
                    if (property == null)
                        continue;
                    var value = property.GetValue(source);
                    if (value == null)
                        continue;

                    if (value is int intValue)
                        return Math.Sign(intValue);

                    var text = value.ToString() ?? "";
                    if (text.IndexOf("buy", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        text.IndexOf("ask", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        text.IndexOf("up", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        return 1;
                    }

                    if (text.IndexOf("sell", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        text.IndexOf("bid", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        text.IndexOf("down", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        return -1;
                    }
                }
                catch
                {
                    // Fall back to tick rule.
                }
            }

            return 0;
        }

        private DateTime? ReadTargetDate()
        {
            try
            {
                var path = Path.Combine(
                    @"C:\Users\k_99_\Desktop\codding\data_footprint_generator",
                    "target_trade_result_date.txt");
                if (!File.Exists(path))
                    return null;
                var text = File.ReadAllText(path).Trim();
                if (DateTime.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.None, out var date))
                    return date.Date;
            }
            catch
            {
            }

            return null;
        }

        private DateTime ToNy(DateTime timeUtc)
        {
            var utc = timeUtc.Kind == DateTimeKind.Utc
                ? timeUtc
                : DateTime.SpecifyKind(timeUtc, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        private static DateTime ToUtc(DateTime value)
        {
            if (value.Kind == DateTimeKind.Utc)
                return value;
            return DateTime.SpecifyKind(value, DateTimeKind.Utc);
        }

        private static DateTime FloorToSecond(DateTime value)
        {
            var ticks = value.Ticks - value.Ticks % TimeSpan.TicksPerSecond;
            return new DateTime(ticks, DateTimeKind.Utc);
        }

        private static TimeSpan ParseNy(string value, TimeSpan fallback)
        {
            return TimeSpan.TryParse(value, out var result) ? result : fallback;
        }

        private static decimal RoundToTick(decimal price, decimal tick)
        {
            if (tick <= 0)
                return price;
            return Math.Round(price / tick, 0, MidpointRounding.AwayFromZero) * tick;
        }

        private static decimal TryGetDecimal(dynamic source, string propertyName)
        {
            if (source == null)
                return 0;

            try
            {
                var property = source.GetType().GetProperty(propertyName);
                if (property == null)
                    return 0;
                var value = property.GetValue(source);
                return value == null ? 0 : Convert.ToDecimal(value, CultureInfo.InvariantCulture);
            }
            catch
            {
                return 0;
            }
        }

        private sealed class SecondBucket
        {
            public SecondBucket(DateTime secondUtc, int bar, decimal price)
            {
                SecondUtc = secondUtc;
                Bar = bar;
                Open = price;
                High = price;
                Low = price;
                Close = price;
                Source = "Tape";
            }

            public DateTime SecondUtc { get; }
            public DateTime NyTime { get; set; }
            public int Bar { get; private set; }
            public decimal Open { get; private set; }
            public decimal High { get; private set; }
            public decimal Low { get; private set; }
            public decimal Close { get; private set; }
            public decimal BuyVolume { get; private set; }
            public decimal SellVolume { get; private set; }
            public decimal Volume { get; private set; }
            public decimal Delta { get; private set; }
            public int Trades { get; private set; }
            public decimal DeltaChange1s { get; set; }
            public string Source { get; private set; }

            public static SecondBucket Empty(DateTime secondUtc, int bar, decimal carryPrice)
            {
                return new SecondBucket(secondUtc, bar, carryPrice)
                {
                    Source = "GapFill"
                };
            }

            public void ApplyTrade(decimal price, decimal volume, int direction, int bar, string source)
            {
                if (Trades == 0)
                    Open = price;
                if (price > High) High = price;
                if (price < Low) Low = price;
                Close = price;
                Volume += volume;
                Trades++;
                Bar = bar;
                Source = source;

                if (direction > 0)
                {
                    BuyVolume += volume;
                    Delta += volume;
                }
                else if (direction < 0)
                {
                    SellVolume += volume;
                    Delta -= volume;
                }
            }

            public void ApplyAggregate(
                decimal close,
                decimal high,
                decimal low,
                decimal volume,
                decimal delta,
                int bar,
                string source)
            {
                Open = Trades == 0 ? close : Open;
                High = high;
                Low = low;
                Close = close;
                Volume = volume;
                Delta = delta;
                BuyVolume = Math.Max(0, (volume + delta) / 2m);
                SellVolume = Math.Max(0, (volume - delta) / 2m);
                Trades = Math.Max(1, Trades);
                Bar = bar;
                Source = source;
            }
        }

        private sealed class BurstFeatures
        {
            public decimal Delta1s { get; set; }
            public decimal Delta2s { get; set; }
            public decimal Delta3s { get; set; }
            public decimal Delta5s { get; set; }
            public decimal Delta10s { get; set; }
            public decimal PeakPositiveDelta { get; set; }
            public decimal PeakNegativeDelta { get; set; }
            public decimal DeltaChange1s { get; set; }
            public decimal DeltaChangeZScore { get; set; }
            public decimal DeltaPercentile { get; set; }
            public decimal BuySellRatio { get; set; }
            public decimal TradesPerSecond { get; set; }
            public decimal ContractsPerSecond { get; set; }
            public decimal Velocity1s { get; set; }
            public decimal Velocity3s { get; set; }
            public decimal Velocity5s { get; set; }
            public decimal Acceleration1s { get; set; }
            public decimal Acceleration3s { get; set; }
            public decimal TicksPerSecond { get; set; }
            public decimal CumulativeDelta { get; set; }
        }

        private sealed class ProfileSnapshot
        {
            public decimal? OrHigh { get; set; }
            public decimal? OrLow { get; set; }
            public decimal? OrWidthTicks { get; set; }
            public decimal? Vwap { get; set; }
            public decimal? Poc { get; set; }
            public decimal? Vah { get; set; }
            public decimal? Val { get; set; }
            public decimal? NearestHvn { get; set; }
            public decimal? NearestLvn { get; set; }
            public decimal? DistanceToOrHighTicks { get; set; }
            public decimal? DistanceToOrLowTicks { get; set; }
            public decimal? DistanceToVwapTicks { get; set; }
            public decimal? DistanceToPocTicks { get; set; }
            public decimal? DistanceToVahTicks { get; set; }
            public decimal? DistanceToValTicks { get; set; }
            public decimal? DistanceToHvnTicks { get; set; }
            public decimal? DistanceToLvnTicks { get; set; }
        }

        private sealed class BurstSnapshot
        {
            public const string CsvHeader =
                "Detector_VERSION,BurstId,Timestamp_UTC,Timestamp_NY,Bar,Side,AggressionLabel,LabelColor,Price," +
                "Delta1s,Delta2s,Delta3s,Delta5s,Delta10s,PeakPositiveDelta,PeakNegativeDelta,DeltaChange1s," +
                "DeltaChangeZScore,DeltaPercentile,BuySellRatio,TradesPerSecond,ContractsPerSecond,Velocity1s," +
                "Velocity3s,Velocity5s,Acceleration1s,Acceleration3s,TicksPerSecond,CumulativeDeltaWindow," +
                "OR_High,OR_Low,OR_WidthTicks,VWAP,POC,VAH,VAL,Nearest_HVN,Nearest_LVN,Dist_OR_High_Ticks," +
                "Dist_OR_Low_Ticks,Dist_VWAP_Ticks,Dist_POC_Ticks,Dist_VAH_Ticks,Dist_VAL_Ticks,Dist_HVN_Ticks," +
                "Dist_LVN_Ticks,Source,Window,AvailableBeforeEntry";

            public BurstSnapshot(
                string burstId,
                DateTime timestampUtc,
                DateTime timestampNy,
                int bar,
                string side,
                string aggressionLabel,
                string labelColor,
                decimal price,
                BurstFeatures features,
                ProfileSnapshot profile,
                string version,
                string source)
            {
                BurstId = burstId;
                TimestampUtc = timestampUtc;
                TimestampNy = timestampNy;
                Bar = bar;
                Side = side;
                AggressionLabel = aggressionLabel;
                LabelColor = labelColor;
                Price = price;
                Features = features;
                Profile = profile;
                DetectorVersion = version;
                Source = source;
            }

            public string BurstId { get; }
            public DateTime TimestampUtc { get; }
            public DateTime TimestampNy { get; }
            public int Bar { get; }
            public string Side { get; }
            public string AggressionLabel { get; }
            public string LabelColor { get; }
            public decimal Price { get; }
            public BurstFeatures Features { get; }
            public ProfileSnapshot Profile { get; }
            public string DetectorVersion { get; }
            public string Source { get; }

            public string ToCsvRow()
            {
                return string.Join(",",
                    Csv(DetectorVersion),
                    Csv(BurstId),
                    Csv(TimestampUtc.ToString("O", CultureInfo.InvariantCulture)),
                    Csv(TimestampNy.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture)),
                    Bar.ToString(CultureInfo.InvariantCulture),
                    Csv(Side),
                    Csv(AggressionLabel),
                    Csv(LabelColor),
                    Num(Price),
                    Num(Features.Delta1s),
                    Num(Features.Delta2s),
                    Num(Features.Delta3s),
                    Num(Features.Delta5s),
                    Num(Features.Delta10s),
                    Num(Features.PeakPositiveDelta),
                    Num(Features.PeakNegativeDelta),
                    Num(Features.DeltaChange1s),
                    Num(Features.DeltaChangeZScore),
                    Num(Features.DeltaPercentile),
                    Num(Features.BuySellRatio),
                    Num(Features.TradesPerSecond),
                    Num(Features.ContractsPerSecond),
                    Num(Features.Velocity1s),
                    Num(Features.Velocity3s),
                    Num(Features.Velocity5s),
                    Num(Features.Acceleration1s),
                    Num(Features.Acceleration3s),
                    Num(Features.TicksPerSecond),
                    Num(Features.CumulativeDelta),
                    Num(Profile.OrHigh),
                    Num(Profile.OrLow),
                    Num(Profile.OrWidthTicks),
                    Num(Profile.Vwap),
                    Num(Profile.Poc),
                    Num(Profile.Vah),
                    Num(Profile.Val),
                    Num(Profile.NearestHvn),
                    Num(Profile.NearestLvn),
                    Num(Profile.DistanceToOrHighTicks),
                    Num(Profile.DistanceToOrLowTicks),
                    Num(Profile.DistanceToVwapTicks),
                    Num(Profile.DistanceToPocTicks),
                    Num(Profile.DistanceToVahTicks),
                    Num(Profile.DistanceToValTicks),
                    Num(Profile.DistanceToHvnTicks),
                    Num(Profile.DistanceToLvnTicks),
                    Csv(Source),
                    Csv("1s causal snapshot"),
                    "1");
            }

            private static string Csv(string value)
            {
                value = value ?? "";
                if (value.IndexOfAny(new[] { ',', '"', '\r', '\n' }) < 0)
                    return value;
                return "\"" + value.Replace("\"", "\"\"") + "\"";
            }

            private static string Num(decimal value)
            {
                return value.ToString("0.###############", CultureInfo.InvariantCulture);
            }

            private static string Num(decimal? value)
            {
                return value.HasValue ? Num(value.Value) : "";
            }
        }
    }
}
