using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    [DisplayName("02_Visual_Logic")]
    public class EddiewareOpeningRangeVisual : Indicator
    {
        private const decimal FallbackTickSize = 0.25m;
        private const decimal HardMaxTradeTicks = 60m;
        private const decimal APlusStopTicks = 60m;
        private const decimal ValueAcceptanceMinTradeTicks = 30m;
        private const decimal NormalScalpMaxTradeTicks = 120m;
        private readonly ScoreTradeSignalEngine _signalEngine = new ScoreTradeSignalEngine();

        private DateTime _currentDate = DateTime.MinValue;
        private decimal _orHigh;
        private decimal _orLow;
        private int _orBar = -1;
        private bool _orReady;
        private bool _tradeDrawn;
        private bool _panicDrawn;
        private int _tradeBar = -1;
        private string _tradeSide = "";
        private decimal _tradeEntry;
        private decimal _entryBarHighAtEntry;
        private decimal _entryBarLowAtEntry;
        private decimal _tradeCvdEntry;
        private decimal _tradeCvdPeak;
        private decimal _bestFavorablePrice;
        private decimal _lastManagePrice;
        private DateTime _tradeEntryCandleTime = DateTime.MinValue;
        private DateTime _tradeEntryTimeUtc = DateTime.MinValue;
        private DateTime _lastManageTimeUtc = DateTime.MinValue;
        private DateTime _bestFavorableTimeUtc = DateTime.MinValue;
        private bool _tradeIsAPlusSpeed;
        private bool _tradeIsNormalSpeed;
        private decimal _tradeSl;
        private decimal _tradeTp;
        private bool _cvdProfitLockArmed;
        private decimal _cvdProfitLockExitPrice;
        private decimal _cvdProfitLockTicks;
        private decimal _cvdProfitLockBestMfeTicks;
        private bool _cvdRiskBracketActive;
        private bool _tradeHitDrawn;
        private bool _timeOverDrawn;
        private int _activeMarketUpdateBar = -1;
        private DateTime _activeMarketUpdateTime = DateTime.MinValue;
        private DateTime _activeMarketCandleTime = DateTime.MinValue;
        private int _lastProcessedMarketBar = -1;
        private DateTime _lastProcessedMarketTime = DateTime.MinValue;
        private decimal _lastProcessedMarketClose;
        private decimal _lastProcessedMarketVolume;
        private decimal _lastProcessedMarketDelta;
        private readonly HashSet<string> _drawnLiquidityBurstLabels = new HashSet<string>(StringComparer.Ordinal);

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Chart Time Offset Minutes")]
        public int ChartTimeOffsetMinutes { get; set; } = 0;

        [DisplayName("Max Signal Time UTC")]
        public TimeSpan MaxSignalTimeUtc { get; set; } = new TimeSpan(13, 41, 0);

        [DisplayName("Signal End Time UTC")]
        public TimeSpan SignalEndTimeUtc { get; set; } = new TimeSpan(13, 40, 0);

        [DisplayName("Min Score / Cutoff Score")]
        public int MinScore { get; set; } = 5;

        [DisplayName("Min OR Range Ticks")]
        public decimal MinOrRangeTicks { get; set; } = 40;

        [DisplayName("Max OR Range Ticks")]
        public decimal MaxOrRangeTicks { get; set; } = 125;

        [DisplayName("Min Body Breakout Ticks")]
        public decimal MinBodyBreakoutTicks { get; set; } = 10;

        [DisplayName("Min Volume")]
        public decimal MinVolume { get; set; } = 800;

        [DisplayName("Min Abs Delta")]
        public decimal MinAbsDelta { get; set; } = 25;

        [DisplayName("Min SL/TP Ticks")]
        public decimal MinTradeTicks { get; set; } = 60;

        [DisplayName("Max SL/TP Ticks")]
        public decimal MaxTradeTicks { get; set; } = 60;

        [DisplayName("Line Length (bars)")]
        public int LineLength { get; set; } = 80;

        [DisplayName("Show Opening Range")]
        public bool ShowOpeningRange { get; set; } = true;

        [DisplayName("Show Entry SL TP")]
        public bool ShowEntrySlTp { get; set; } = true;

        [DisplayName("Min Normal Speed Ticks/Sec")]
        public decimal MinNormalSpeedTicksPerSecond { get; set; } = 2;

        [DisplayName("Min A+ Speed Ticks/Sec")]
        public decimal APlusSpeedTicksPerSecond { get; set; } = 5;

        [DisplayName("Replay Speed Multiplier")]
        public decimal ReplaySpeedMultiplier { get; set; } = 10;

        [DisplayName("Panic MFE Trigger Ticks")]
        public decimal PanicMfeTriggerTicks { get; set; } = 20;

        [DisplayName("Panic Pullback Ticks")]
        public decimal PanicPullbackTicks { get; set; } = 10;

        [DisplayName("CVD Profit Lock Pullback Ticks")]
        public decimal CvdProfitLockPullbackTicks { get; set; } = 10;

        [DisplayName("Panic Adverse Speed Ticks/Sec")]
        public decimal PanicAdverseSpeedTicksPerSecond { get; set; } = 6;

        [DisplayName("Half MFE Exit Min MFE Ticks")]
        public decimal HalfMfeExitMinMfeTicks { get; set; } = 40;

        [DisplayName("Imbalance Ratio")]
        public decimal ImbalanceRatio { get; set; } = 3m;

        [DisplayName("Volume filter")]
        public decimal ImbalanceCompareMinVolume { get; set; } = 70m;

        [DisplayName("A+ Price Acceptance Ticks")]
        public decimal APlusPriceAcceptanceTicks { get; set; } = 15m;

        [DisplayName("Show Liquidity Burst Labels")]
        public bool ShowLiquidityBurstLabels { get; set; } = true;

        [DisplayName("Liquidity Burst Max Age Seconds")]
        public int LiquidityBurstMaxAgeSeconds { get; set; } = 3;

        [DisplayName("Liquidity Burst Label Offset Ticks")]
        public decimal LiquidityBurstLabelOffsetTicks { get; set; } = 18m;

        [DisplayName("Block Macro Events (FOMC/CPI/NFP/JH)")]
        public bool BlockMacroEvents { get; set; } = true;

        public EddiewareOpeningRangeVisual()
        {
            Name = "02_Visual_Logic";
            DrawAbovePrice = true;
        }

        protected override void OnNewTrade(MarketDataArg trade)
        {
            base.OnNewTrade(trade);

            var bar = CurrentBar - 1;
            if (bar < 1)
                return;

            ProcessMarketUpdate(bar, trade.Price, trade.Time);
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            var candle = GetCandle(bar);
            ProcessMarketUpdate(bar, value, ResolveMarketUpdateTime(bar, candle));
        }

        private void ProcessMarketUpdate(int bar, decimal value, DateTime marketUpdateTime)
        {
            if (bar < 1)
                return;

            var candle = GetCandle(bar);

            if (_lastProcessedMarketTime != DateTime.MinValue &&
                marketUpdateTime < _lastProcessedMarketTime &&
                candle.Time.Date == _currentDate)
            {
                ResetDay(candle.Time.Date);
            }

            if (!ShouldProcessMarketState(bar, candle, marketUpdateTime))
                return;

            _activeMarketUpdateBar = bar;
            _activeMarketUpdateTime = marketUpdateTime;
            _activeMarketCandleTime = candle.Time;

            if (candle.Time.Date != _currentDate)
                ResetDay(candle.Time.Date);

            if (BlockMacroEvents && MacroEventFilter.IsBlockedDate(_currentDate))
                return;

            UpdateSpeedClock(bar, candle.Time);
            TryDrawLiquidityBurstLabel(bar, candle, marketUpdateTime);

            if (_tradeDrawn)
            {
                ManageActiveTrade(bar, candle, value);
                return;
            }

            var closedBar = bar - 1;

            if (!_orReady && closedBar >= 0)
            {
                var closedCandle = GetCandle(closedBar);

                if (IsOpeningCandle(closedCandle))
                {
                    _orHigh = closedCandle.High;
                    _orLow = closedCandle.Low;
                    _orBar = closedBar;
                    _orReady = true;

                    if (ShowOpeningRange)
                        DrawOpeningRange();
                }
            }

            if (TryRegisterTimeOver(candle))
                return;

            if (!_orReady)
                return;

            if (_tradeDrawn || bar <= _orBar || !IsSignalWindow(candle))
                return;

            var score = CalculateScore(candle, bar, marketUpdateTime, value);
            var signalTime = marketUpdateTime;
            var sharedSnapshot = SharedTradeSignalSnapshot.CaptureOrGet(
                candle.Time.Date,
                _orLow,
                _orHigh,
                bar,
                signalTime,
                score);

            if (sharedSnapshot == null)
                return;

            var snapshotCandle = GetCandle(sharedSnapshot.Bar);
            _tradeDrawn = DrawTrade(sharedSnapshot.Bar, snapshotCandle, sharedSnapshot.Signal);
        }

        private ScoreTradeSignal CalculateScore(
            dynamic candle,
            int bar,
            DateTime marketUpdateTime,
            decimal currentPrice)
        {
            return _signalEngine.Calculate(bar, candle, new Func<int, dynamic>(GetCandle), new ScoreTradeSignalRequest
            {
                OrLow = _orLow,
                OrHigh = _orHigh,
                CurrentTime = marketUpdateTime,
                MarketUpdateTime = marketUpdateTime,
                CurrentPrice = currentPrice,
                SessionDate = candle.Time.Date,
                GetSessionTime = c => c.Time,
                SignalStartTime = OpeningTimeUtc,
                SignalEndTime = SignalEndTimeUtc,
                NormalSpeedAllowedUntilTime = OpeningTimeUtc.Add(new TimeSpan(0, 3, 59)),
                TickSize = GetTickSize(),
                MinScore = MinScore,
                MinOrRangeTicks = MinOrRangeTicks,
                MaxOrRangeTicks = MaxOrRangeTicks,
                MinBodyBreakoutTicks = MinBodyBreakoutTicks,
                MinVolume = MinVolume,
                MinAbsDelta = MinAbsDelta,
                MinNormalSpeedTicksPerSecond = MinNormalSpeedTicksPerSecond,
                APlusSpeedTicksPerSecond = APlusSpeedTicksPerSecond,
                ReplaySpeedMultiplier = ReplaySpeedMultiplier,
                ImbalanceRatio = ImbalanceRatio,
                ImbalanceCompareMinVolume = ImbalanceCompareMinVolume,
                APlusPriceAcceptanceTicks = APlusPriceAcceptanceTicks
            });
        }

        private string FormatNullablePrice(decimal? price)
        {
            return price.HasValue ? price.Value.ToString("0.00") : "NA";
        }

        private static string FormatSpeedLabel(string speedLabel)
        {
            if (speedLabel == "A+ speed")
                return "A+SPD";

            if (speedLabel == "normal speed")
                return "SPD";

            if (speedLabel == "invalid speed")
                return "NO SPD";

            return string.IsNullOrWhiteSpace(speedLabel) ? "SPD NA" : speedLabel;
        }

        private static Color GetTradeSideColor(string side)
        {
            return side == "BUY" ? Color.Blue : Color.Orange;
        }

        private static Color GetOpenTradeLabelColor(string side)
        {
            return side == "BUY" ? Color.Blue : Color.Red;
        }

        private bool DrawTrade(int bar, dynamic candle, ScoreTradeSignal score)
        {
            var executionSide = string.IsNullOrWhiteSpace(score.ExecutionSide)
                ? score.Side
                : score.ExecutionSide;

            if (!ShowEntrySlTp || executionSide == "")
                return false;

            var tickSize = GetTickSize();
            var rawImbalanceStop = score.SpeedLabel == "A+ speed" || score.SpeedLabel == "normal speed"
                ? null
                : TradeManagerTpSlBeExit.TryGetImbalanceStop(
                    candle,
                    executionSide,
                    tickSize,
                    ImbalanceRatio,
                    ImbalanceCompareMinVolume);
            var plan = TradeManagerTpSlBeExit.CreateInitialPlan(new TradeManagerTpSlBeExit.TradePlanRequest
            {
                Side = executionSide,
                SpeedLabel = score.SpeedLabel,
                Entry = score.EntryPrice,
                OrLow = _orLow,
                OrHigh = _orHigh,
                TickSize = tickSize,
                MinTradeTicks = MinTradeTicks,
                MaxTradeTicks = Math.Min(MaxTradeTicks, HardMaxTradeTicks),
                HardMaxTradeTicks = HardMaxTradeTicks,
                APlusStopTicks = APlusStopTicks,
                NormalSpeedMaxTradeTicks = NormalScalpMaxTradeTicks,
                ValueAcceptanceMinTradeTicks = ValueAcceptanceMinTradeTicks,
                ImbalanceStopPrice = rawImbalanceStop?.StopPrice,
                NormalSpeedImbalanceStopPrice = score.BreakoutSideImbalanceStopPrice,
                ValueAcceptanceStopPrice = score.ValueAcceptanceStopPrice,
                CapSellStopAtOrHigh = true,
                EnforceMinExitDistance = false
            });

            if (!plan.IsValid)
                return false;
            var entry = plan.Entry;

            _tradeBar = bar;
            _tradeSide = executionSide;
            _tradeEntry = entry;
            _entryBarHighAtEntry = score.EntryBarHighAtEntry;
            _entryBarLowAtEntry = score.EntryBarLowAtEntry;
            _tradeCvdEntry = score.CumulativeDelta;
            _tradeCvdPeak = score.CumulativeDelta;
            _tradeSl = 0;
            _tradeTp = 0;
            _cvdProfitLockArmed = false;
            _cvdProfitLockExitPrice = 0;
            _cvdProfitLockTicks = 0;
            _cvdProfitLockBestMfeTicks = 0;
            _cvdRiskBracketActive = false;
            _bestFavorablePrice = entry;
            _lastManagePrice = entry;
            _tradeEntryCandleTime = candle.Time;
            _tradeEntryTimeUtc = TryGetCandleUpdateTime(candle);
            _lastManageTimeUtc = _tradeEntryTimeUtc;
            _bestFavorableTimeUtc = _lastManageTimeUtc;
            _tradeIsAPlusSpeed = plan.IsAPlusSpeed;
            _tradeIsNormalSpeed = plan.IsNormalSpeed;

            if (_tradeIsNormalSpeed || _tradeIsAPlusSpeed)
                ApplyInitialNormalScalpBracket(plan);

            return true;
        }

        private void ApplyInitialNormalScalpBracket(TradeManagerTpSlBeExit.TradePlan plan)
        {
            if (plan.Sl == 0 || plan.Tp == 0)
                return;

            _tradeSl = plan.Sl;
            _tradeTp = plan.Tp;
        }

        private void ManageActiveTrade(int bar, dynamic candle, decimal livePrice)
        {
            if (_tradeSide == "")
                return;

            if (_tradeHitDrawn)
                return;

            UpdateActiveTradeStopFromLastImbalance(candle);
            if (!_tradeIsNormalSpeed)
            {
                UpdateCvdProfitLock(bar, candle);
                if (TryApplyCvdRiskBracket(bar, candle))
                    return;
            }

            if (_tradeIsAPlusSpeed)
            {
                TryRegisterFirstTradeHit(livePrice);
                return;
            }

            var tickSize = GetTickSize();
            var currentPrice = candle.Close;
            decimal hitHigh;
            decimal hitLow;
            GetPostEntryHitRange(bar, candle, out hitHigh, out hitLow);
            string timingSource;
            var currentTime = TryGetCandleUpdateTime(candle, out timingSource);
            var elapsedSeconds = TradeManagerTpSlBeExit.NormalizeElapsedSeconds(
                (currentTime - _lastManageTimeUtc).TotalSeconds,
                timingSource,
                ReplaySpeedMultiplier);
            var previousBestFavorablePrice = _bestFavorablePrice;
            _bestFavorablePrice = TradeManagerTpSlBeExit.UpdateBestFavorablePrice(
                _tradeSide,
                _bestFavorablePrice,
                hitHigh,
                hitLow);

            if (_bestFavorablePrice != previousBestFavorablePrice)
                _bestFavorableTimeUtc = currentTime;

            var adverseElapsedSeconds = TradeManagerTpSlBeExit.NormalizeAdverseElapsedSeconds(
                (currentTime - _bestFavorableTimeUtc).TotalSeconds,
                elapsedSeconds,
                timingSource,
                ReplaySpeedMultiplier);

            var metrics = TradeManagerTpSlBeExit.CalculatePanicMetrics(
                _tradeSide,
                _tradeEntry,
                _bestFavorablePrice,
                _lastManagePrice,
                hitHigh,
                hitLow,
                (decimal)elapsedSeconds,
                (decimal)adverseElapsedSeconds,
                PanicPullbackTicks,
                tickSize);

            _lastManagePrice = metrics.AdversePrice;
            _lastManageTimeUtc = currentTime;

            var speedPanic = metrics.AdverseSpeed > PanicAdverseSpeedTicksPerSecond;

            TryRegisterFirstTradeHit(livePrice);

            if (_tradeHitDrawn)
                return;

            if (_panicDrawn)
                return;

            var weakDelta = candle.Delta <= 0 && candle.Delta > -MinAbsDelta;
            var weakVolume = candle.Volume >= 0 && candle.Volume < MinVolume;
            var vwapFailed = HasVwapFailed(bar, candle);
            var weakFlowPanic = weakDelta && weakVolume && vwapFailed;

            if (metrics.MfeTicks < PanicMfeTriggerTicks ||
                metrics.PullbackTicks < PanicPullbackTicks ||
                !speedPanic ||
                !weakFlowPanic)
                return;

            _panicDrawn = true;
        }

        private void UpdateActiveTradeStopFromLastImbalance(dynamic candle)
        {
            if (_tradeSide == "" || _tradeEntry == 0)
                return;

            if (_tradeSl != 0)
                return;

            var tickSize = GetTickSize();
            var imbalanceStop = TradeManagerTpSlBeExit.TryGetImbalanceStop(
                candle,
                _tradeSide,
                tickSize,
                ImbalanceRatio,
                ImbalanceCompareMinVolume);
            var nextSl = imbalanceStop?.StopPrice ?? (_tradeSide == "BUY"
                ? _tradeEntry - 60m * tickSize
                : _tradeEntry + 60m * tickSize);

            if (_tradeSl == nextSl)
                return;

            _tradeSl = nextSl;

            var slTicks = RoundToTicks(Math.Abs(_tradeEntry - _tradeSl));
            _tradeTp = _tradeSide == "BUY"
                ? _tradeEntry + slTicks * tickSize
                : _tradeEntry - slTicks * tickSize;
        }

        private void TryRegisterFirstTradeHit(decimal livePrice)
        {
            if (_tradeHitDrawn)
                return;

            if (_tradeSide != "BUY" && _tradeSide != "SELL")
                return;

            var hitHigh = livePrice;
            var hitLow = livePrice;

            if (_tradeTp != 0 && TradeManagerTpSlBeExit.IsTpHit(_tradeSide, hitHigh, hitLow, _tradeTp))
            {
                _tradeHitDrawn = true;
                return;
            }

            if (_tradeSl != 0 && TradeManagerTpSlBeExit.IsSlHit(_tradeSide, hitHigh, hitLow, _tradeSl))
                _tradeHitDrawn = true;
        }

        private void GetPostEntryHitRange(int bar, dynamic candle, out decimal hitHigh, out decimal hitLow)
        {
            TradeManagerTpSlBeExit.GetPostEntryHitRange(
                bar == _tradeBar,
                candle.High,
                candle.Low,
                candle.Close,
                _entryBarHighAtEntry,
                _entryBarLowAtEntry,
                out hitHigh,
                out hitLow);
        }

        private bool HasVwapFailed(int bar, dynamic candle)
        {
            var vwap = TradeManagerTpSlBeExit.GetSessionVwap(bar, candle.Time.Date, new Func<int, dynamic>(GetCandle));

            return TradeManagerTpSlBeExit.HasVwapFailed(_tradeSide, candle.Close, vwap);
        }

        private bool TryApplyCvdRiskBracket(int bar, dynamic candle)
        {
            if (_cvdRiskBracketActive || _tradeSide == "" || _tradeEntry == 0 || _tradeTp == 0)
                return false;

            var pullback = UpdateCvdPullbackState(bar, candle);

            if (pullback.PullbackLabel != "Riesgo de reversion")
                return false;

            var tickSize = GetTickSize();
            var originalTpTicks = RoundToTicks(Math.Abs(_tradeTp - _tradeEntry));
            var tp50Ticks = Math.Max(1, Math.Floor(originalTpTicks * 0.50m));
            _tradeTp = _tradeSide == "BUY"
                ? _tradeEntry + tp50Ticks * tickSize
                : _tradeEntry - tp50Ticks * tickSize;

            _cvdRiskBracketActive = true;
            return true;
        }

        private CumulativeDeltaPullbackState UpdateCvdPullbackState(int bar, dynamic candle)
        {
            var currentCvd = CumulativeDeltaDetector.Detect(
                bar,
                candle,
                new Func<int, dynamic>(GetCandle),
                _currentDate,
                new Func<dynamic, DateTime>(c => c.Time));
            var pullback = CumulativeDeltaDetector.CalculatePullback(
                _tradeSide,
                _tradeCvdEntry,
                currentCvd.Value,
                _tradeCvdPeak);

            _tradeCvdPeak = pullback.PeakCvd;
            return pullback;
        }

        private decimal CalculateFavorableProgressTicks(int bar, dynamic candle)
        {
            decimal hitHigh;
            decimal hitLow;
            GetPostEntryHitRange(bar, candle, out hitHigh, out hitLow);

            if (_tradeSide == "BUY")
                return RoundToTicks(Math.Max(0, hitHigh - _tradeEntry));

            if (_tradeSide == "SELL")
                return RoundToTicks(Math.Max(0, _tradeEntry - hitLow));

            return 0;
        }

        private decimal CalculateFavorableCloseTicks(dynamic candle)
        {
            if (_tradeSide == "BUY")
                return RoundToTicks(Math.Max(0, candle.Close - _tradeEntry));

            if (_tradeSide == "SELL")
                return RoundToTicks(Math.Max(0, _tradeEntry - candle.Close));

            return 0;
        }

        private void UpdateCvdProfitLock(int bar, dynamic candle)
        {
            if (_tradeTp == 0 || _tradeEntry == 0)
                return;

            var progressTicks = CalculateFavorableProgressTicks(bar, candle);
            if (progressTicks > _cvdProfitLockBestMfeTicks)
                _cvdProfitLockBestMfeTicks = progressTicks;

            var armTicks = CalculateCvdProfitLockArmTicks();
            if (_cvdProfitLockBestMfeTicks < armTicks)
                return;

            _cvdProfitLockArmed = true;
            var lockedTicks = CalculateCvdProfitLockTicks(armTicks);
            if (lockedTicks <= _cvdProfitLockTicks)
                return;

            _cvdProfitLockTicks = lockedTicks;
            var tickSize = GetTickSize();
            _cvdProfitLockExitPrice = _tradeSide == "BUY"
                ? _tradeEntry + lockedTicks * tickSize
                : _tradeEntry - lockedTicks * tickSize;
        }

        private decimal CalculateCvdProfitLockArmTicks()
        {
            if (_tradeTp == 0 || _tradeEntry == 0)
                return decimal.MaxValue;

            return RoundToTicks(Math.Abs(_tradeTp - _tradeEntry)) * 0.50m;
        }

        private decimal CalculateCvdProfitLockTicks(decimal armTicks)
        {
            if (_tradeTp == 0 || _tradeEntry == 0)
                return 0;

            var tpTicks = RoundToTicks(Math.Abs(_tradeTp - _tradeEntry));
            var trailingTicks = _cvdProfitLockBestMfeTicks - CvdProfitLockPullbackTicks;
            var lockedTicks = Math.Max(armTicks, trailingTicks);
            return Math.Min(tpTicks, lockedTicks);
        }

        private bool HasCvdProfitLockRetrace(dynamic candle)
        {
            if (!_cvdProfitLockArmed || _cvdProfitLockTicks <= 0)
                return false;

            if (_cvdProfitLockBestMfeTicks <= _cvdProfitLockTicks)
                return false;

            return CalculateFavorableCloseTicks(candle) <= _cvdProfitLockTicks;
        }

        private decimal CalculateEntryMoveTicks(dynamic candle, decimal tickSize)
        {
            if (_tradeSide == "BUY")
                return RoundToTicks(candle.Close - _tradeEntry);

            if (_tradeSide == "SELL")
                return RoundToTicks(_tradeEntry - candle.Close);

            return 0;
        }

        private decimal CalculateEntryElapsedSeconds(dynamic candle, DateTime currentTime, double fallbackElapsedSeconds)
        {
            var barElapsedSeconds = (candle.Time - _tradeEntryCandleTime).TotalSeconds;
            if (barElapsedSeconds > 0 && barElapsedSeconds <= 300)
                return (decimal)barElapsedSeconds;

            var updateElapsedSeconds = (currentTime - _tradeEntryTimeUtc).TotalSeconds;
            if (updateElapsedSeconds > 0 && updateElapsedSeconds <= 300)
                return (decimal)Math.Max(0.001, updateElapsedSeconds);

            return (decimal)Math.Max(1, fallbackElapsedSeconds);
        }

        private void TryDrawLiquidityBurstLabel(int bar, dynamic candle, DateTime marketUpdateTime)
        {
            if (!ShowLiquidityBurstLabels)
                return;

            var burst = LiquidityBurstSignalBus.GetLatest(
                candle.Time.Date,
                marketUpdateTime,
                LiquidityBurstMaxAgeSeconds);

            if (burst == null)
                return;

            var burstId = burst.BurstId;
            if (!_drawnLiquidityBurstLabels.Add(burstId))
                return;

            var tickSize = GetTickSize();
            var isSellPosition = burst.Side == "BUY";
            var candleHigh = Convert.ToDecimal(candle.High);
            var candleLow = Convert.ToDecimal(candle.Low);
            var labelPrice = isSellPosition
                ? Math.Max(candleHigh, burst.Price) + tickSize * LiquidityBurstLabelOffsetTicks
                : Math.Min(candleLow, burst.Price) - tickSize * LiquidityBurstLabelOffsetTicks;
            var background = isSellPosition ? Color.Red : Color.ForestGreen;
            var label = isSellPosition
                ? "BUY ABSORPTION | SELL POSITION"
                : "SELL ABSORPTION | BUY POSITION";

            AddText(
                $"EW_LIQUIDITY_BURST_{burstId}",
                $"{label} | px {burst.Price:0.00} | d1 {burst.Delta1s:0} z {burst.DeltaChangeZScore:0.00} v {burst.Velocity1s:0.00}t/s",
                isSellPosition,
                bar,
                labelPrice,
                0,
                0,
                Color.White,
                background,
                background,
                11,
                DrawingText.TextAlign.Center,
                true);
        }

        private void DrawOpeningRange()
        {
            var pen = new Pen(Color.Red, 1);
            var endBar = _orBar + LineLength;

            TrendLines.Add(new TrendLine(_orBar, _orHigh, endBar, _orHigh, pen));
            TrendLines.Add(new TrendLine(_orBar, _orLow, endBar, _orLow, pen));

            AddText(
                $"EW_OR_{_currentDate:yyyyMMdd}",
                $"OR {RoundToTicks(_orHigh - _orLow):0}t",
                true,
                _orBar,
                _orHigh,
                -45,
                0,
                Color.White,
                Color.DarkRed,
                Color.DarkRed,
                14,
                DrawingText.TextAlign.Center,
                true);
        }

        private bool TryRegisterTimeOver(dynamic candle)
        {
            var time = EffectiveTimeOfDay(candle.Time);

            if (_timeOverDrawn ||
                _tradeDrawn ||
                time < MaxSignalTimeUtc)
            {
                return false;
            }

            _timeOverDrawn = true;
            return true;
        }

        private bool IsOpeningCandle(dynamic candle)
        {
            var time = EffectiveTimeOfDay(candle.Time);
            return time.Hours == OpeningTimeUtc.Hours && time.Minutes == OpeningTimeUtc.Minutes;
        }

        // Chart candles arrive in the chart's own time zone. When that zone is
        // not UTC the exact match above never fires and the whole visual stays
        // blank without any message, which is exactly how this indicator went
        // silent. The offset realigns it from the settings panel.
        private TimeSpan EffectiveTimeOfDay(DateTime chartTime)
        {
            var shifted = chartTime.AddMinutes(ChartTimeOffsetMinutes).TimeOfDay;
            if (shifted < TimeSpan.Zero)
                shifted += TimeSpan.FromDays(1);
            return shifted;
        }

        private void UpdateSpeedClock(int bar, DateTime barStartMarketTime)
        {
            _signalEngine.UpdateSpeedClock(bar, barStartMarketTime);
        }

        private DateTime TryGetCandleUpdateTime(dynamic candle)
        {
            if (IsActiveMarketCandle(candle))
                return _activeMarketUpdateTime;

            return SpeedClasification.TryGetCandleUpdateTime(candle);
        }

        private DateTime TryGetCandleUpdateTime(dynamic candle, out string timingSource)
        {
            if (IsActiveMarketCandle(candle))
            {
                timingSource = "MarketTradeTime";
                return _activeMarketUpdateTime;
            }

            return SpeedClasification.TryGetCandleUpdateTime(candle, out timingSource);
        }

        private DateTime ResolveMarketUpdateTime(int bar, dynamic candle)
        {
            string timingSource;
            var candleUpdateTime = SpeedClasification.TryGetCandleUpdateTime(candle, out timingSource);
            if (timingSource != "UtcNow" && IsPlausibleMarketTime(candle.Time, candleUpdateTime))
                return candleUpdateTime;

            if (bar == CurrentBar - 1)
            {
                var marketTime = MarketTime;
                if (IsPlausibleMarketTime(candle.Time, marketTime))
                    return marketTime;
            }

            return candle.Time;
        }

        private bool IsActiveMarketCandle(dynamic candle)
        {
            if (_activeMarketUpdateBar < 0 ||
                _activeMarketUpdateTime == DateTime.MinValue)
            {
                return false;
            }

            try
            {
                return candle.Time == _activeMarketCandleTime;
            }
            catch
            {
                return false;
            }
        }

        private static bool IsPlausibleMarketTime(DateTime candleTime, DateTime marketTime)
        {
            if (marketTime == DateTime.MinValue || marketTime < candleTime)
                return false;

            return marketTime - candleTime <= TimeSpan.FromDays(1);
        }

        private bool ShouldProcessMarketState(int bar, dynamic candle, DateTime marketUpdateTime)
        {
            var close = Convert.ToDecimal(candle.Close);
            var volume = Convert.ToDecimal(candle.Volume);
            var delta = Convert.ToDecimal(candle.Delta);

            if (bar == _lastProcessedMarketBar &&
                marketUpdateTime == _lastProcessedMarketTime &&
                close == _lastProcessedMarketClose &&
                volume == _lastProcessedMarketVolume &&
                delta == _lastProcessedMarketDelta)
            {
                return false;
            }

            _lastProcessedMarketBar = bar;
            _lastProcessedMarketTime = marketUpdateTime;
            _lastProcessedMarketClose = close;
            _lastProcessedMarketVolume = volume;
            _lastProcessedMarketDelta = delta;
            return true;
        }

        private decimal NormalizeReplaySpeedMultiplier()
        {
            return TradeManagerTpSlBeExit.NormalizeReplaySpeedMultiplier(ReplaySpeedMultiplier);
        }

        private string GetSpeedLabel(decimal speedTicksPerSecond)
        {
            return SpeedClasification.GetSpeedLabel(
                speedTicksPerSecond,
                MinNormalSpeedTicksPerSecond,
                APlusSpeedTicksPerSecond);
        }

        private bool IsSignalWindow(dynamic candle)
        {
            var time = EffectiveTimeOfDay(candle.Time);
            return
                time > OpeningTimeUtc &&
                time <= SignalEndTimeUtc;
        }

        private void ResetDay(DateTime date)
        {
            _currentDate = date;
            _orHigh = 0;
            _orLow = 0;
            _orBar = -1;
            _orReady = false;
            _tradeDrawn = false;
            _signalEngine.ResetDay();
            _panicDrawn = false;
            _tradeBar = -1;
            _tradeSide = "";
            _tradeEntry = 0;
            _entryBarHighAtEntry = 0;
            _entryBarLowAtEntry = 0;
            _tradeCvdEntry = 0;
            _tradeCvdPeak = 0;
            _bestFavorablePrice = 0;
            _lastManagePrice = 0;
            _lastManageTimeUtc = DateTime.MinValue;
            _bestFavorableTimeUtc = DateTime.MinValue;
            _tradeIsAPlusSpeed = false;
            _tradeIsNormalSpeed = false;
            _tradeSl = 0;
            _tradeTp = 0;
            _cvdRiskBracketActive = false;
            _cvdProfitLockArmed = false;
            _cvdProfitLockExitPrice = 0;
            _cvdProfitLockTicks = 0;
            _cvdProfitLockBestMfeTicks = 0;
            _tradeHitDrawn = false;
            _timeOverDrawn = false;
            _activeMarketUpdateBar = -1;
            _activeMarketUpdateTime = DateTime.MinValue;
            _activeMarketCandleTime = DateTime.MinValue;
            _lastProcessedMarketBar = -1;
            _lastProcessedMarketTime = DateTime.MinValue;
            _lastProcessedMarketClose = 0;
            _lastProcessedMarketVolume = 0;
            _lastProcessedMarketDelta = 0;
            _drawnLiquidityBurstLabels.Clear();
        }

        private decimal RoundToTicks(decimal points)
        {
            return TradeManagerTpSlBeExit.RoundToTicks(points, GetTickSize());
        }

        private decimal GetTickSize()
        {
            return FallbackTickSize;
        }

        private string Flag(bool value)
        {
            return value ? "+" : "-";
        }

    }
}
