using System;

namespace ATAS.Indicators
{
    internal sealed class ScoreTradeSignalEngine
    {
        private const decimal HardMinAPlusSpeedTicksPerSecond = 12m;

        private int _speedBar = -1;
        private DateTime _speedBarStartedAtUtc = DateTime.MinValue;
        private int _aPlusStructureBar = -1;
        private string _aPlusStructureSide = "";
        private decimal? _aPlusStructurePrice;

        public void ResetDay()
        {
            _speedBar = -1;
            _speedBarStartedAtUtc = DateTime.MinValue;
            _aPlusStructureBar = -1;
            _aPlusStructureSide = "";
            _aPlusStructurePrice = null;
        }

        public void UpdateSpeedClock(int bar)
        {
            if (bar == _speedBar)
                return;

            _speedBar = bar;
            _speedBarStartedAtUtc = DateTime.UtcNow;
        }

        public ScoreTradeSignal Calculate(int bar, dynamic candle, Func<int, dynamic> getCandle, ScoreTradeSignalRequest request)
        {
            var signalTime = request.CurrentTime;
            var longBreakout = candle.Close > request.OrHigh;
            var shortBreakout = candle.Close < request.OrLow;
            var breakoutSide = longBreakout ? "BUY" : shortBreakout ? "SELL" : "";
            var orRangeTicks = RoundToTicks(request.OrHigh - request.OrLow, request.TickSize);
            var vwap = GetSessionVwap(bar, request.SessionDate, getCandle, request.GetSessionTime);
            var cumulativeDelta = CumulativeDeltaDetector.Detect(
                bar,
                candle,
                getCandle,
                request.SessionDate,
                request.GetSessionTime);
            var previousCandle = bar > 0 ? getCandle(bar - 1) : null;
            var previousVolume = TryGetDecimal(previousCandle, "Volume");
            var previousDelta = TryGetDecimal(previousCandle, "Delta");
            decimal bodyBreakoutTicks = 0;

            if (longBreakout)
                bodyBreakoutTicks = RoundToTicks(candle.Close - Math.Max(candle.Open, request.OrHigh), request.TickSize);

            if (shortBreakout)
                bodyBreakoutTicks = RoundToTicks(Math.Min(candle.Open, request.OrLow) - candle.Close, request.TickSize);

            if (bodyBreakoutTicks < 0)
                bodyBreakoutTicks = 0;

            var speedState = SpeedClasification.CalculateBreakoutSpeedState(
                candle,
                bodyBreakoutTicks,
                _speedBarStartedAtUtc,
                request.ReplaySpeedMultiplier);

            var state = new ScoreTradeSignal
            {
                IsBreakout = longBreakout || shortBreakout,
                Side = breakoutSide,
                EntryPrice = candle.Close,
                EntryBarHighAtEntry = candle.High,
                EntryBarLowAtEntry = candle.Low,
                OrLow = request.OrLow,
                OrHigh = request.OrHigh,
                OrRangeTicks = orRangeTicks,
                Vwap = vwap,
                BodyBreakoutTicks = bodyBreakoutTicks,
                BreakoutSpeed = speedState.TicksPerSecond,
                SpeedElapsedSeconds = speedState.ElapsedSeconds,
                SpeedUsedReplayFallback = speedState.UsedReplayFallback,
                SpeedTimingSource = speedState.TimingSource,
                Volume = candle.Volume,
                Delta = candle.Delta,
                CumulativeDelta = cumulativeDelta.Value,
                CumulativeDeltaSource = cumulativeDelta.Source,
                PreviousVolume = previousVolume,
                PreviousDelta = previousDelta,
                VolumeIncreasing = previousVolume <= 0 || candle.Volume > previousVolume,
                DeltaChange = candle.Delta - previousDelta,
                RangeOk = orRangeTicks >= request.MinOrRangeTicks && orRangeTicks <= request.MaxOrRangeTicks,
                BodyOk = bodyBreakoutTicks >= request.MinBodyBreakoutTicks,
                VolumeOk = candle.Volume >= request.MinVolume,
                DeltaOk = Math.Abs(candle.Delta) >= request.MinAbsDelta,
                TimeOk = IsSignalWindow(signalTime, request.SignalStartTime, request.SignalEndTime),
                VwapOk =
                    (longBreakout && candle.Close >= vwap) ||
                    (shortBreakout && candle.Close <= vwap)
            };

            var effectiveAPlusSpeedTicksPerSecond = Math.Max(
                request.APlusSpeedTicksPerSecond,
                HardMinAPlusSpeedTicksPerSecond);

            state.SpeedLabel = SpeedClasification.GetSpeedLabel(
                state.BreakoutSpeed,
                request.MinNormalSpeedTicksPerSecond,
                effectiveAPlusSpeedTicksPerSecond);
            state.SpeedValid = IsSpeedValidForSignalTime(
                state.SpeedLabel,
                signalTime.TimeOfDay,
                request.NormalSpeedAllowedUntilTime);
            var imbalance = ImbalanceDetector.Detect(candle, new ImbalanceDetectorRequest
            {
                Side = state.Side,
                Ratio = request.ImbalanceRatio,
                CompareMinVolume = request.ImbalanceCompareMinVolume
            });
            if (state.IsBreakout && imbalance.HasAPlusStructure)
            {
                _aPlusStructureBar = bar;
                _aPlusStructureSide = imbalance.APlusStructureSide;
                _aPlusStructurePrice = imbalance.APlusStructurePrice;
            }

            var hasAPlusStructureForSignal =
                _aPlusStructureBar == bar &&
                _aPlusStructureSide == state.Side;
            state.HasBuy_ImbalanceUnTouched = imbalance.HasBuy_ImbalanceUnTouched;
            state.HasSell_ImbalanceUnTouched = imbalance.HasSell_ImbalanceUnTouched;
            state.HasBuy3_ImbalanceGroup = imbalance.HasBuy3_ImbalanceGroup;
            state.HasSell3_ImbalanceGroup = imbalance.HasSell3_ImbalanceGroup;
            state.BuyImbalanceCount = imbalance.BuyImbalanceCount;
            state.SellImbalanceCount = imbalance.SellImbalanceCount;
            state.HasSide3_ImbalanceGroup =
                (state.Side == "BUY" && state.HasBuy3_ImbalanceGroup) ||
                (state.Side == "SELL" && state.HasSell3_ImbalanceGroup);
            state.HasSide3_Imbalances =
                (state.Side == "BUY" && state.BuyImbalanceCount >= 3) ||
                (state.Side == "SELL" && state.SellImbalanceCount >= 3);
            state.HasAny3_ImbalanceGroup =
                state.HasBuy3_ImbalanceGroup ||
                state.HasSell3_ImbalanceGroup;
            state.HasAPlusStructure = hasAPlusStructureForSignal;
            state.APlusStructureSide = hasAPlusStructureForSignal ? _aPlusStructureSide : "";
            state.APlusStructurePrice = hasAPlusStructureForSignal ? _aPlusStructurePrice : null;
            state.DeltaWithSide =
                (state.Side == "BUY" && state.Delta > 0 && state.DeltaChange >= 0) ||
                (state.Side == "SELL" && state.Delta < 0 && state.DeltaChange <= 0);
            state.PriceAcceptedAfterImbalance =
                state.HasAPlusStructure &&
                state.APlusStructurePrice.HasValue &&
                ((state.Side == "BUY" && candle.Close > state.APlusStructurePrice.Value) ||
                 (state.Side == "SELL" && candle.Close < state.APlusStructurePrice.Value));
            state.ImbalanceScore = imbalance.Score;
            AbsorptionDetector.ApplySignalSource(state);
            if (state.HasAPlusStructure && !state.SpeedValid)
            {
                state.SpeedIgnoredByStructure = true;
                state.SpeedLabel = "normal speed";
                state.SpeedValid = true;
                state.SpeedTimingSource = state.SignalSource;
            }

            if (state.VwapOk) state.Score += 2;
            if (state.RangeOk) state.Score += 1;
            if (state.BodyOk) state.Score += 1;
            if (state.VolumeOk) state.Score += 1;
            if (state.DeltaOk) state.Score += 1;
            if (state.SpeedValid) state.Score += state.SpeedLabel == "A+ speed" ? 2 : 1;
            state.Score += state.ImbalanceScore;

            state.IsReady =
                state.IsBreakout &&
                state.TimeOk &&
                state.Score >= request.MinScore &&
                state.SpeedValid &&
                (state.SpeedLabel != "normal speed" || state.HasSide3_Imbalances || state.HasAny3_ImbalanceGroup) &&
                state.VolumeOk &&
                (!request.RequireBodyOkForTrade || state.BodyOk) &&
                (!request.RequireVwapOkForTrade || state.VwapOk);

            return state;
        }

        private static bool IsSignalWindow(DateTime signalTime, TimeSpan signalStartTime, TimeSpan signalEndTime)
        {
            var time = signalTime.TimeOfDay;
            return time >= signalStartTime && time <= signalEndTime;
        }

        internal static bool IsSpeedValidForSignalTime(string speedLabel, TimeSpan signalTime, TimeSpan normalSpeedAllowedUntilTime)
        {
            return speedLabel == "normal speed" || speedLabel == "A+ speed";
        }

        private static decimal GetSessionVwap(int bar, DateTime sessionDate, Func<int, dynamic> getCandle, Func<dynamic, DateTime> getSessionTime)
        {
            decimal cumPv = 0;
            decimal cumVol = 0;

            for (var i = bar; i >= 0; i--)
            {
                var candle = getCandle(i);
                var candleSessionTime = getSessionTime(candle);

                if (candleSessionTime.Date != sessionDate.Date)
                    break;

                decimal volume = candle.Volume;

                if (volume <= 0)
                    continue;

                var typical = (candle.High + candle.Low + candle.Close) / 3m;

                cumPv += typical * volume;
                cumVol += volume;
            }

            return cumVol <= 0 ? 0 : cumPv / cumVol;
        }

        private static decimal RoundToTicks(decimal points, decimal tickSize)
        {
            return Math.Round(points / tickSize, 2);
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

                return Convert.ToDecimal(property.GetValue(source));
            }
            catch
            {
                return 0;
            }
        }
    }

    internal sealed class ScoreTradeSignalRequest
    {
        public decimal OrLow { get; set; }
        public decimal OrHigh { get; set; }
        public DateTime CurrentTime { get; set; }
        public DateTime SessionDate { get; set; }
        public Func<dynamic, DateTime> GetSessionTime { get; set; } = candle => candle.Time;
        public TimeSpan SignalStartTime { get; set; }
        public TimeSpan SignalEndTime { get; set; }
        public TimeSpan NormalSpeedAllowedUntilTime { get; set; }
        public decimal TickSize { get; set; }
        public int MinScore { get; set; }
        public decimal MinOrRangeTicks { get; set; }
        public decimal MaxOrRangeTicks { get; set; }
        public decimal MinBodyBreakoutTicks { get; set; }
        public decimal MinVolume { get; set; }
        public decimal MinAbsDelta { get; set; }
        public decimal MinNormalSpeedTicksPerSecond { get; set; }
        public decimal APlusSpeedTicksPerSecond { get; set; }
        public decimal ReplaySpeedMultiplier { get; set; }
        public decimal ImbalanceRatio { get; set; } = 3m;
        public decimal ImbalanceCompareMinVolume { get; set; } = 70m;
        public bool RequireBodyOkForTrade { get; set; }
        public bool RequireVwapOkForTrade { get; set; }
    }

    internal sealed class ScoreTradeSignal
    {
        public bool IsBreakout { get; set; }
        public bool IsAPlusStructureSignal { get; set; }
        public bool IsReady { get; set; }
        public string Side { get; set; } = "";
        public decimal EntryPrice { get; set; }
        public decimal EntryBarHighAtEntry { get; set; }
        public decimal EntryBarLowAtEntry { get; set; }
        public decimal OrLow { get; set; }
        public decimal OrHigh { get; set; }
        public decimal OrRangeTicks { get; set; }
        public decimal Vwap { get; set; }
        public decimal BodyBreakoutTicks { get; set; }
        public decimal BreakoutSpeed { get; set; }
        public decimal SpeedElapsedSeconds { get; set; }
        public bool SpeedUsedReplayFallback { get; set; }
        public string SpeedTimingSource { get; set; } = "";
        public string SpeedLabel { get; set; } = "";
        public decimal Volume { get; set; }
        public decimal Delta { get; set; }
        public decimal CumulativeDelta { get; set; }
        public string CumulativeDeltaSource { get; set; } = "";
        public decimal PreviousVolume { get; set; }
        public decimal PreviousDelta { get; set; }
        public bool VolumeIncreasing { get; set; }
        public decimal DeltaChange { get; set; }
        public bool DeltaWithSide { get; set; }
        public bool PriceAcceptedAfterImbalance { get; set; }
        public bool RangeOk { get; set; }
        public bool BodyOk { get; set; }
        public bool VolumeOk { get; set; }
        public bool DeltaOk { get; set; }
        public bool TimeOk { get; set; }
        public bool VwapOk { get; set; }
        public bool SpeedValid { get; set; }
        public bool HasBuy_ImbalanceUnTouched { get; set; }
        public bool HasSell_ImbalanceUnTouched { get; set; }
        public bool HasBuy3_ImbalanceGroup { get; set; }
        public bool HasSell3_ImbalanceGroup { get; set; }
        public bool HasSide3_ImbalanceGroup { get; set; }
        public bool HasSide3_Imbalances { get; set; }
        public bool HasAny3_ImbalanceGroup { get; set; }
        public int BuyImbalanceCount { get; set; }
        public int SellImbalanceCount { get; set; }
        public bool HasAPlusStructure { get; set; }
        public bool HasAPlusAbsorption { get; set; }
        public bool HasAPlusSpeed { get; set; }
        public string APlusStructureSide { get; set; } = "";
        public decimal? APlusStructurePrice { get; set; }
        public string SignalSource { get; set; } = "";
        public bool SpeedIgnoredByStructure { get; set; }
        public int ImbalanceScore { get; set; }
        public int Score { get; set; }
    }
}
