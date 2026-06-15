using System;

namespace ATAS.Indicators
{
    internal sealed class ScoreTradeSignalEngine
    {
        private const int MinAPlusImbalanceCount = 3;
        private const decimal ValueAcceptanceTicks = 10m;

        private int _speedBar = -1;
        private DateTime _speedBarStartedAtUtc = DateTime.MinValue;
        private int _aPlusStructureBar = -1;
        private string _aPlusStructureSide = "";
        private decimal? _aPlusStructurePrice;
        private int _buyAPlusStructureBar = -1;
        private decimal? _buyAPlusStructurePrice;
        private int _sellAPlusStructureBar = -1;
        private decimal? _sellAPlusStructurePrice;
        private int _judasStructureBar = -1;
        private string _judasStructureSide = "";
        private decimal? _judasStructurePrice;
        private bool _judasReturnedToRange;

        public void ResetDay()
        {
            _speedBar = -1;
            _speedBarStartedAtUtc = DateTime.MinValue;
            _aPlusStructureBar = -1;
            _aPlusStructureSide = "";
            _aPlusStructurePrice = null;
            _buyAPlusStructureBar = -1;
            _buyAPlusStructurePrice = null;
            _sellAPlusStructureBar = -1;
            _sellAPlusStructurePrice = null;
            _judasStructureBar = -1;
            _judasStructureSide = "";
            _judasStructurePrice = null;
            _judasReturnedToRange = false;
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

            state.SpeedLabel = SpeedClasification.GetSpeedLabel(
                state.BreakoutSpeed,
                request.MinNormalSpeedTicksPerSecond,
                request.APlusSpeedTicksPerSecond);
            state.SpeedValid = IsSpeedValidForSignalTime(
                state.SpeedLabel,
                signalTime.TimeOfDay,
                request.NormalSpeedAllowedUntilTime);
            UpdateAPlusStructureMemory(candle, request);

            if (state.Side == "")
            {
                var rejectedStructureSide = ResolveRejectedAPlusStructureSide(candle, request);

                if (rejectedStructureSide != "")
                {
                    state.Side = rejectedStructureSide;
                    state.IsBreakout = true;
                }
            }

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

            var hasAPlusStructureForSignal = HasAPlusStructureForSide(state.Side);
            var aPlusStructurePrice = GetAPlusStructurePriceForSide(state.Side);
            state.HasBuy_ImbalanceUnTouched = imbalance.HasBuy_ImbalanceUnTouched;
            state.HasSell_ImbalanceUnTouched = imbalance.HasSell_ImbalanceUnTouched;
            state.HasBuy3_ImbalanceGroup = imbalance.HasBuy3_ImbalanceGroup;
            state.HasSell3_ImbalanceGroup = imbalance.HasSell3_ImbalanceGroup;
            state.BuyImbalanceCount = imbalance.BuyImbalanceCount;
            state.SellImbalanceCount = imbalance.SellImbalanceCount;
            state.BreakoutSideImbalanceStopPrice = ResolveBreakoutSideImbalanceStopPrice(state.Side, imbalance, request.TickSize);
            ApplyValueAcceptanceSignal(candle, request, state, imbalance);
            hasAPlusStructureForSignal = HasAPlusStructureForSide(state.Side);
            aPlusStructurePrice = GetAPlusStructurePriceForSide(state.Side);
            state.HasSide3_ImbalanceGroup =
                (state.Side == "BUY" && state.HasBuy3_ImbalanceGroup) ||
                (state.Side == "SELL" && state.HasSell3_ImbalanceGroup);
            state.HasSide3_Imbalances =
                (state.Side == "BUY" && state.BuyImbalanceCount >= MinAPlusImbalanceCount) ||
                (state.Side == "SELL" && state.SellImbalanceCount >= MinAPlusImbalanceCount);
            state.HasAny3_ImbalanceGroup =
                state.HasBuy3_ImbalanceGroup ||
                state.HasSell3_ImbalanceGroup;
            state.HasAPlusStructure = hasAPlusStructureForSignal;
            state.APlusStructureSide = hasAPlusStructureForSignal ? state.Side : "";
            state.APlusStructurePrice = hasAPlusStructureForSignal ? aPlusStructurePrice : null;
            state.DeltaWithSide =
                (state.Side == "BUY" && state.Delta > 0 && state.DeltaChange >= 0) ||
                (state.Side == "SELL" && state.Delta < 0 && state.DeltaChange <= 0);
            state.PriceAcceptedAfterImbalance =
                state.HasAPlusStructure &&
                state.APlusStructurePrice.HasValue &&
                ((state.Side == "BUY" && candle.High >= state.APlusStructurePrice.Value + request.APlusPriceAcceptanceTicks * request.TickSize) ||
                 (state.Side == "SELL" && candle.Low <= state.APlusStructurePrice.Value - request.APlusPriceAcceptanceTicks * request.TickSize));
            state.PriceAcceptedAfterSpeed =
                state.SpeedLabel == "A+ speed" &&
                ((state.Side == "BUY" && candle.High >= state.EntryPrice + request.APlusPriceAcceptanceTicks * request.TickSize) ||
                 (state.Side == "SELL" && candle.Low <= state.EntryPrice - request.APlusPriceAcceptanceTicks * request.TickSize));
            state.ImbalanceScore = imbalance.Score;
            AbsorptionDetector.ApplySignalSource(state);
            ApplyJudasSwingState(bar, candle, request, state);
            state.ExecutionSide = ResolveExecutionSide(state);
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

            var isAPlusAbsorptionReady =
                state.HasAPlusAbsorption &&
                state.TimeOk &&
                state.VolumeOk &&
                !string.IsNullOrWhiteSpace(state.ExecutionSide);
            var isValueAcceptanceReady =
                state.IsValueAcceptance &&
                state.TimeOk &&
                state.VolumeOk &&
                state.ValueAcceptanceStopPrice.HasValue &&
                !string.IsNullOrWhiteSpace(state.ExecutionSide);

            state.IsReady =
                isAPlusAbsorptionReady ||
                isValueAcceptanceReady ||
                (
                state.IsBreakout &&
                state.TimeOk &&
                state.Score >= request.MinScore &&
                state.SpeedValid &&
                (state.SpeedLabel != "A+ speed" || state.HasAPlusStructure || state.PriceAcceptedAfterSpeed || state.HasAPlusAbsorption) &&
                (state.SpeedLabel != "normal speed" || HasBreakoutSideImbalance(state)) &&
                state.VolumeOk &&
                (!request.RequireBodyOkForTrade || state.BodyOk) &&
                (!request.RequireVwapOkForTrade || state.VwapOk)
                );

            ApplyCvdAtEntryFeatures(bar, getCandle, request, state);

            return state;
        }

        /// <summary>
        /// Calcula el estado del CVD de la sesion AL MOMENTO DE LA SENAL usando
        /// solo barras hasta la barra actual inclusive. Esta es la version
        /// legitima (sin lookahead) del Cvd_Pullback que antes solo existia como
        /// metrica intra-trade actualizada hasta el cierre de la operacion.
        /// </summary>
        private static void ApplyCvdAtEntryFeatures(
            int bar,
            Func<int, dynamic> getCandle,
            ScoreTradeSignalRequest request,
            ScoreTradeSignal state)
        {
            var sessionStats = CumulativeDeltaDetector.DetectSessionStats(
                bar,
                getCandle,
                request.SessionDate,
                request.GetSessionTime,
                3);

            if (!sessionStats.HasData)
                return;

            var sideForCvd = !string.IsNullOrWhiteSpace(state.ExecutionSide)
                ? state.ExecutionSide
                : state.Side;

            state.CvdSessionMaxAtEntry = sessionStats.SessionMax;
            state.CvdSessionMinAtEntry = sessionStats.SessionMin;
            state.CvdSlope3AtEntry = sessionStats.CvdSlope;
            state.CvdPullbackPctAtEntry = CumulativeDeltaDetector.CalculateAtEntryPullbackPercent(
                sideForCvd,
                sessionStats.CvdAtBar,
                sessionStats.SessionMax,
                sessionStats.SessionMin);
            state.CvdPullbackLabelAtEntry = CumulativeDeltaDetector.ClassifyPullback(state.CvdPullbackPctAtEntry);
            state.BarsSinceCvdExtremeAtEntry = sideForCvd == "SELL"
                ? sessionStats.BarsSinceMin
                : sessionStats.BarsSinceMax;
        }

        private void ApplyJudasSwingState(int bar, dynamic candle, ScoreTradeSignalRequest request, ScoreTradeSignal state)
        {
            if (state == null)
                return;

            TryArmJudasSwing(bar, candle, state);

            if (!IsJudasArmed())
                return;

            _judasReturnedToRange = _judasReturnedToRange || IsReturnedToRange(candle, state.OrHigh, state.OrLow);

            if (!_judasReturnedToRange)
                return;

            state.IsJudasSwing = true;
            state.IsFakeBreakout = true;
            state.HasAPlusStructure = true;
            state.APlusStructureSide = _judasStructureSide;
            state.APlusStructurePrice = _judasStructurePrice;
            state.Side = _judasStructureSide;
            state.IsBreakout = true;
            state.PriceAcceptedAfterImbalance =
                _judasStructurePrice.HasValue &&
                ((_judasStructureSide == "BUY" && candle.High >= _judasStructurePrice.Value + request.APlusPriceAcceptanceTicks * request.TickSize) ||
                 (_judasStructureSide == "SELL" && candle.Low <= _judasStructurePrice.Value - request.APlusPriceAcceptanceTicks * request.TickSize));

            if (state.PriceAcceptedAfterImbalance)
            {
                state.HasAPlusAbsorption = false;
                state.SignalSource = "JUDAS SWING";
                return;
            }

            state.HasAPlusAbsorption = true;
            state.SignalSource = "A+ ABSORTION";
        }

        private void TryArmJudasSwing(int bar, dynamic candle, ScoreTradeSignal state)
        {
            if (!state.IsBreakout)
                return;

            if (state.Side == "BUY" && state.HasBuy3_ImbalanceGroup && candle.High > state.OrHigh)
            {
                _judasStructureBar = bar;
                _judasStructureSide = "BUY";
                _judasStructurePrice = GetAPlusStructurePriceForSide("BUY");
                _judasReturnedToRange = false;
                return;
            }

            if (state.Side == "SELL" && state.HasSell3_ImbalanceGroup && candle.Low < state.OrLow)
            {
                _judasStructureBar = bar;
                _judasStructureSide = "SELL";
                _judasStructurePrice = GetAPlusStructurePriceForSide("SELL");
                _judasReturnedToRange = false;
            }
        }

        private bool IsJudasArmed()
        {
            return _judasStructureBar >= 0 &&
                !string.IsNullOrWhiteSpace(_judasStructureSide) &&
                _judasStructurePrice.HasValue;
        }

        private static bool IsReturnedToRange(dynamic candle, decimal orHigh, decimal orLow)
        {
            return candle.Close <= orHigh && candle.Close >= orLow;
        }

        private void UpdateAPlusStructureMemory(dynamic candle, ScoreTradeSignalRequest request)
        {
            var buyState = ImbalanceDetector.Detect(candle, new ImbalanceDetectorRequest
            {
                Side = "BUY",
                Ratio = request.ImbalanceRatio,
                CompareMinVolume = request.ImbalanceCompareMinVolume
            });

            if (buyState.HasBuy3_ImbalanceGroup)
            {
                _aPlusStructureBar = _speedBar;
                _aPlusStructureSide = "BUY";
                _aPlusStructurePrice = buyState.Buy3_ImbalanceGroupPrice;
                _buyAPlusStructureBar = _speedBar;
                _buyAPlusStructurePrice = buyState.Buy3_ImbalanceGroupPrice;
            }

            var sellState = ImbalanceDetector.Detect(candle, new ImbalanceDetectorRequest
            {
                Side = "SELL",
                Ratio = request.ImbalanceRatio,
                CompareMinVolume = request.ImbalanceCompareMinVolume
            });

            if (sellState.HasSell3_ImbalanceGroup)
            {
                _aPlusStructureBar = _speedBar;
                _aPlusStructureSide = "SELL";
                _aPlusStructurePrice = sellState.Sell3_ImbalanceGroupPrice;
                _sellAPlusStructureBar = _speedBar;
                _sellAPlusStructurePrice = sellState.Sell3_ImbalanceGroupPrice;
            }
        }

        private string ResolveRejectedAPlusStructureSide(dynamic candle, ScoreTradeSignalRequest request)
        {
            var tickDistance = request.APlusPriceAcceptanceTicks * request.TickSize;
            var buyRejected = _buyAPlusStructureBar >= 0 &&
                _buyAPlusStructurePrice.HasValue &&
                candle.High < _buyAPlusStructurePrice.Value + tickDistance;
            var sellRejected = _sellAPlusStructureBar >= 0 &&
                _sellAPlusStructurePrice.HasValue &&
                candle.Low > _sellAPlusStructurePrice.Value - tickDistance;

            if (buyRejected && sellRejected)
                return _buyAPlusStructureBar >= _sellAPlusStructureBar ? "BUY" : "SELL";

            if (buyRejected)
                return "BUY";

            if (sellRejected)
                return "SELL";

            return "";
        }

        private bool HasAPlusStructureForSide(string side)
        {
            side = string.IsNullOrWhiteSpace(side) ? "" : side.Trim().ToUpperInvariant();

            if (side == "BUY")
                return _buyAPlusStructureBar >= 0 && _buyAPlusStructurePrice.HasValue;

            if (side == "SELL")
                return _sellAPlusStructureBar >= 0 && _sellAPlusStructurePrice.HasValue;

            return false;
        }

        private decimal? GetAPlusStructurePriceForSide(string side)
        {
            side = string.IsNullOrWhiteSpace(side) ? "" : side.Trim().ToUpperInvariant();

            if (side == "BUY")
                return _buyAPlusStructurePrice;

            if (side == "SELL")
                return _sellAPlusStructurePrice;

            return null;
        }

        internal static string ResolveExecutionSide(ScoreTradeSignal state)
        {
            if (state == null)
                return "";

            if (!state.HasAPlusAbsorption)
                return state.Side;

            var absorbedSide = string.IsNullOrWhiteSpace(state.APlusStructureSide)
                ? state.Side
                : state.APlusStructureSide;

            return OppositeSide(absorbedSide);
        }

        internal static string OppositeSide(string side)
        {
            side = string.IsNullOrWhiteSpace(side) ? "" : side.Trim().ToUpperInvariant();

            if (side == "BUY")
                return "SELL";

            if (side == "SELL")
                return "BUY";

            return "";
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

        private static void ApplyValueAcceptanceSignal(
            dynamic candle,
            ScoreTradeSignalRequest request,
            ScoreTradeSignal state,
            ImbalanceState imbalance)
        {
            var buyPrice = TryGetLastBuyImbalancePrice(imbalance);
            var sellPrice = TryGetLastSellImbalancePrice(imbalance);
            var buyAcceptanceTicks = buyPrice.HasValue
                ? RoundToTicks(candle.High - buyPrice.Value, request.TickSize)
                : 0;
            var sellAcceptanceTicks = sellPrice.HasValue
                ? RoundToTicks(sellPrice.Value - candle.Low, request.TickSize)
                : 0;
            var hasBuyAcceptance = buyAcceptanceTicks >= ValueAcceptanceTicks;
            var hasSellAcceptance = sellAcceptanceTicks >= ValueAcceptanceTicks;

            if (!hasBuyAcceptance && !hasSellAcceptance)
                return;

            var side = hasBuyAcceptance && (!hasSellAcceptance || buyAcceptanceTicks >= sellAcceptanceTicks)
                ? "BUY"
                : "SELL";
            var imbalancePrice = side == "BUY" ? buyPrice : sellPrice;

            if (!imbalancePrice.HasValue)
                return;

            state.Side = side;
            state.ExecutionSide = side;
            state.IsBreakout = true;
            state.IsValueAcceptance = true;
            state.SignalSource = "VALUE_ACCEPTANCE";
            state.SpeedLabel = "normal speed";
            state.SpeedValid = true;
            state.SpeedTimingSource = "VALUE_ACCEPTANCE";
            state.ValueAcceptanceStopPrice = side == "BUY"
                ? imbalancePrice.Value - request.TickSize
                : imbalancePrice.Value + request.TickSize;
            state.BreakoutSideImbalanceStopPrice = state.ValueAcceptanceStopPrice;
            state.PriceAcceptedAfterImbalance = true;
        }

        private static bool HasBreakoutSideImbalance(ScoreTradeSignal state)
        {
            if (state.Side == "BUY")
                return state.BuyImbalanceCount > 0;

            if (state.Side == "SELL")
                return state.SellImbalanceCount > 0;

            return false;
        }

        private static decimal? ResolveBreakoutSideImbalanceStopPrice(string side, ImbalanceState imbalance, decimal tickSize)
        {
            var buyPrice = TryGetLastBuyImbalancePrice(imbalance);
            var sellPrice = TryGetLastSellImbalancePrice(imbalance);

            if (side == "BUY" && buyPrice.HasValue)
                return buyPrice.Value - tickSize;

            if (side == "SELL" && sellPrice.HasValue)
                return sellPrice.Value + tickSize;

            return null;
        }

        private static decimal? TryGetLastBuyImbalancePrice(ImbalanceState imbalance)
        {
            if (imbalance.BuyImbalancePrices.Count == 0)
                return null;

            return imbalance.BuyImbalancePrices[imbalance.BuyImbalancePrices.Count - 1];
        }

        private static decimal? TryGetLastSellImbalancePrice(ImbalanceState imbalance)
        {
            if (imbalance.SellImbalancePrices.Count == 0)
                return null;

            return imbalance.SellImbalancePrices[0];
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
        public decimal APlusPriceAcceptanceTicks { get; set; } = 20m;
        public bool RequireBodyOkForTrade { get; set; }
        public bool RequireVwapOkForTrade { get; set; }
    }

    internal sealed class ScoreTradeSignal
    {
        public bool IsBreakout { get; set; }
        public bool IsAPlusStructureSignal { get; set; }
        public bool IsReady { get; set; }
        public string Side { get; set; } = "";
        public string ExecutionSide { get; set; } = "";
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
        public bool PriceAcceptedAfterSpeed { get; set; }
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
        public decimal? BreakoutSideImbalanceStopPrice { get; set; }
        public decimal? ValueAcceptanceStopPrice { get; set; }
        public bool IsValueAcceptance { get; set; }
        public bool HasAPlusStructure { get; set; }
        public bool HasAPlusAbsorption { get; set; }
        public bool HasAPlusSpeed { get; set; }
        public bool IsFakeBreakout { get; set; }
        public bool IsJudasSwing { get; set; }
        public string APlusStructureSide { get; set; } = "";
        public decimal? APlusStructurePrice { get; set; }
        public string SignalSource { get; set; } = "";
        public bool SpeedIgnoredByStructure { get; set; }
        public int ImbalanceScore { get; set; }
        public int Score { get; set; }

        // --- Features de CVD calculadas con datos PRE-ENTRADA (sin lookahead) ---
        public decimal CvdSessionMaxAtEntry { get; set; }
        public decimal CvdSessionMinAtEntry { get; set; }
        public decimal CvdPullbackPctAtEntry { get; set; }
        public string CvdPullbackLabelAtEntry { get; set; } = "";
        public decimal CvdSlope3AtEntry { get; set; }
        public int BarsSinceCvdExtremeAtEntry { get; set; }
    }
}
