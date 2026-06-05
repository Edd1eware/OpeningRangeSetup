using System;
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
        private decimal _bestFavorablePrice;
        private decimal _lastManagePrice;
        private DateTime _lastManageTimeUtc = DateTime.MinValue;
        private DateTime _bestFavorableTimeUtc = DateTime.MinValue;
        private bool _tradeIsAPlusSpeed;
        private decimal _tradeSl;
        private decimal _tradeTp;
        private TrendLine? _activeSlLine;
        private bool _tradeHitDrawn;
        private bool _timeOverDrawn;

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Max Signal Time UTC")]
        public TimeSpan MaxSignalTimeUtc { get; set; } = new TimeSpan(13, 41, 0);

        [DisplayName("Signal End Time UTC")]
        public TimeSpan SignalEndTimeUtc { get; set; } = new TimeSpan(13, 40, 0);

        [DisplayName("Min Score / Cutoff Score")]
        public int MinScore { get; set; } = 5;

        [DisplayName("Min OR Range Ticks")]
        public decimal MinOrRangeTicks { get; set; } = 40;

        [DisplayName("Max OR Range Ticks")]
        public decimal MaxOrRangeTicks { get; set; } = 350;

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

        [DisplayName("Show Score Label")]
        public bool ShowScoreLabel { get; set; } = true;

        [DisplayName("Score Label Offset Ticks")]
        public decimal ScoreLabelOffsetTicks { get; set; } = 35;

        [DisplayName("Min Normal Speed Ticks/Sec")]
        public decimal MinNormalSpeedTicksPerSecond { get; set; } = 2;

        [DisplayName("Min A+ Speed Ticks/Sec")]
        public decimal APlusSpeedTicksPerSecond { get; set; } = 5;

        [DisplayName("Replay Speed Multiplier")]
        public decimal ReplaySpeedMultiplier { get; set; } = 1;

        [DisplayName("Panic MFE Trigger Ticks")]
        public decimal PanicMfeTriggerTicks { get; set; } = 20;

        [DisplayName("Panic Pullback Ticks")]
        public decimal PanicPullbackTicks { get; set; } = 10;

        [DisplayName("Panic Adverse Speed Ticks/Sec")]
        public decimal PanicAdverseSpeedTicksPerSecond { get; set; } = 6;

        [DisplayName("Half MFE Exit Min MFE Ticks")]
        public decimal HalfMfeExitMinMfeTicks { get; set; } = 40;

        [DisplayName("Imbalance Ratio")]
        public decimal ImbalanceRatio { get; set; } = 3m;

        [DisplayName("Volume filter")]
        public decimal ImbalanceCompareMinVolume { get; set; } = 70m;

        [DisplayName("A+ Price Acceptance Ticks")]
        public decimal APlusPriceAcceptanceTicks { get; set; } = 20m;

        [DisplayName("Show A+ Structure Label")]
        public bool ShowAPlusStructureLabel { get; set; } = true;

        [DisplayName("Show A+ Structure Debug Label")]
        public bool ShowAPlusStructureDebugLabel { get; set; } = false;

        [DisplayName("Show A+ Absorption Debug Label")]
        public bool ShowAPlusAbsorptionDebugLabel { get; set; } = false;

        [DisplayName("Show A+ Imbalance Debug Lines")]
        public bool ShowAPlusImbalanceDebugLines { get; set; } = true;

        [DisplayName("Show No A+ Structure Ready Debug Label")]
        public bool ShowNoAPlusStructureReadyDebugLabel { get; set; } = true;

        [DisplayName("No A+ Structure Ready Debug Label Offset Ticks")]
        public decimal NoAPlusStructureReadyDebugLabelOffsetTicks { get; set; } = 95m;

        [DisplayName("A+ Structure Debug Label Offset Ticks")]
        public decimal APlusStructureDebugLabelOffsetTicks { get; set; } = 65m;

        [DisplayName("A+ Structure Label Offset Ticks")]
        public decimal APlusStructureLabelOffsetTicks { get; set; } = 25m;

        public EddiewareOpeningRangeVisual()
        {
            Name = "02_Visual_Logic";
            DrawAbovePrice = true;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            var candle = GetCandle(bar);

            if (candle.Time.Date != _currentDate)
                ResetDay(candle.Time.Date);

            UpdateSpeedClock(bar);

            if (_tradeDrawn)
            {
                ManageActiveTrade(bar, candle);
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

            if (TryDrawTimeOver(bar, candle))
                return;

            if (!_orReady)
                return;

            if (_tradeDrawn || bar <= _orBar || !IsSignalWindow(candle))
                return;

            var score = CalculateScore(candle, bar);

            // A+ Structure visual label is now filtered by the current setup side.
            // This prevents opposite-side imbalance groups from printing before/around the trade.
            TryDrawAPlusStructureLabel(bar, candle, score);
            TryDrawNoAPlusStructureReadyDebugLabel(bar, candle, score);
            TryDrawAPlusAbsorptionDebugLabel(bar, candle, score);

            if (ShowScoreLabel)
                DrawScoreLabel(bar, candle, score);

            if (!score.IsReady)
                return;

            DrawTrade(bar, candle, score);
            _tradeDrawn = true;
        }

        private ScoreTradeSignal CalculateScore(dynamic candle, int bar)
        {
            return _signalEngine.Calculate(bar, candle, new Func<int, dynamic>(GetCandle), new ScoreTradeSignalRequest
            {
                OrLow = _orLow,
                OrHigh = _orHigh,
                CurrentTime = candle.Time,
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

        private void TryDrawNoAPlusStructureReadyDebugLabel(int bar, dynamic candle, ScoreTradeSignal score)
        {
            if (!ShowNoAPlusStructureReadyDebugLabel)
                return;

            if (score == null || !score.IsReady || string.IsNullOrWhiteSpace(score.Side))
                return;

            if (score.HasAPlusStructure)
                return;

            var tickSize = GetTickSize();
            var labelPrice = score.Side == "BUY"
                ? candle.Low - tickSize * NoAPlusStructureReadyDebugLabelOffsetTicks
                : candle.High + tickSize * NoAPlusStructureReadyDebugLabelOffsetTicks;

            AddText(
                $"EW_NO_APLUS_READY_DEBUG_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                $"READY | {score.SignalSource} | {score.Side} | S{score.Score}",
                true,
                bar,
                labelPrice,
                0,
                0,
                Color.White,
                Color.DarkRed,
                Color.DarkRed,
                12,
                DrawingText.TextAlign.Center,
                true);
        }

        private void TryDrawAPlusStructureLabel(int bar, dynamic candle, ScoreTradeSignal score)
        {
            if (!ShowAPlusStructureLabel)
                return;

            if (score == null || !score.IsReady || !score.HasAPlusStructure)
                return;

            var state = ImbalanceDetector.Detect(candle, new ImbalanceDetectorRequest
            {
                Side = score.Side,
                Ratio = ImbalanceRatio,
                CompareMinVolume = ImbalanceCompareMinVolume
            });

            var tickSize = GetTickSize();
            var sideToDraw = score.APlusStructureSide;

            TryDrawAPlusStructureDebugLabel(bar, candle, state, sideToDraw);
            DrawAPlusImbalanceDebugLines(bar, state);

            if (sideToDraw == "BUY")
            {
                var price = score.APlusStructurePrice ?? candle.Low;
                var labelPrice = Math.Min(price, candle.Low) - tickSize * APlusStructureLabelOffsetTicks;
                var group = state.MaxBuyImbalanceGroup;
                var groupPrice = state.MaxBuyImbalanceGroupPrice ?? score.APlusStructurePrice;

                AddText(
                    $"EW_APLUS_IMBALANCE_BUY_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                    $"{score.SignalSource} | BUY | IMBALANCE_Buy{state.BuyImbalanceCount} | IMBALANCE_Sell{state.SellImbalanceCount} | Group{group} @{FormatNullablePrice(groupPrice)}",
                    true,
                    bar,
                    labelPrice,
                    0,
                    0,
                    Color.White,
                    Color.Blue,
                    Color.Blue,
                    12,
                    DrawingText.TextAlign.Center,
                    true);
            }
            else if (sideToDraw == "SELL")
            {
                var price = score.APlusStructurePrice ?? candle.High;
                var labelPrice = Math.Max(price, candle.High) + tickSize * APlusStructureLabelOffsetTicks;
                var group = state.MaxSellImbalanceGroup;
                var groupPrice = state.MaxSellImbalanceGroupPrice ?? score.APlusStructurePrice;

                AddText(
                    $"EW_APLUS_IMBALANCE_SELL_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                    $"{score.SignalSource} | SELL | IMBALANCE_Buy{state.BuyImbalanceCount} | IMBALANCE_Sell{state.SellImbalanceCount} | Group{group} @{FormatNullablePrice(groupPrice)}",
                    true,
                    bar,
                    labelPrice,
                    0,
                    0,
                    Color.White,
                    Color.DeepPink,
                    Color.DeepPink,
                    12,
                    DrawingText.TextAlign.Center,
                    true);
            }
        }

        private void DrawAPlusImbalanceDebugLines(int bar, ImbalanceState state)
        {
            if (!ShowAPlusImbalanceDebugLines)
                return;

            var endBar = bar + 1;
            var buyPen = new Pen(Color.DodgerBlue, 4);
            var sellPen = new Pen(Color.Cyan, 3);

            foreach (var price in state.BuyImbalancePrices)
                TrendLines.Add(new TrendLine(bar, price, endBar, price, buyPen));

            foreach (var price in state.SellImbalancePrices)
                TrendLines.Add(new TrendLine(bar, price, endBar, price, sellPen));
        }

        private void TryDrawAPlusStructureDebugLabel(int bar, dynamic candle, ImbalanceState state, string sideToDraw)
        {
            if (!ShowAPlusStructureDebugLabel)
                return;

            if (!state.HasBuy3_ImbalanceGroup && !state.HasSell3_ImbalanceGroup)
                return;

            var debug = TradeManagerTpSlBeExit.CalculateImbalanceDebugInfo(
                candle,
                ImbalanceRatio,
                ImbalanceCompareMinVolume);
            var tickSize = GetTickSize();
            var labelPrice = candle.High + tickSize * APlusStructureDebugLabelOffsetTicks;
            var bodySide = "DOJI";

            try
            {
                if (candle.Close > candle.Open)
                    bodySide = "BUY";
                else if (candle.Close < candle.Open)
                    bodySide = "SELL";
            }
            catch
            {
                bodySide = "?";
            }

            AddText(
                $"EW_APLUS_IMBALANCE_DEBUG_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                $"DBG IMB | BUY={state.BuyImbalanceCount} G{state.MaxBuyImbalanceGroup} @{FormatNullablePrice(state.MaxBuyImbalanceGroupPrice)} | SELL={state.SellImbalanceCount} G{state.MaxSellImbalanceGroup} @{FormatNullablePrice(state.MaxSellImbalanceGroupPrice)} | DRAW={sideToDraw} | BODY={bodySide}",
                true,
                bar,
                labelPrice,
                0,
                0,
                Color.Black,
                Color.Yellow,
                Color.Yellow,
                10,
                DrawingText.TextAlign.Center,
                true);
        }

        private string FormatNullablePrice(decimal? price)
        {
            return price.HasValue ? price.Value.ToString("0.00") : "NA";
        }

        private void DrawTrade(int bar, dynamic candle, ScoreTradeSignal score)
        {
            var executionSide = string.IsNullOrWhiteSpace(score.ExecutionSide)
                ? score.Side
                : score.ExecutionSide;

            if (!ShowEntrySlTp || executionSide == "")
                return;

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
                ImbalanceStopPrice = rawImbalanceStop?.StopPrice,
                CapSellStopAtOrHigh = true,
                EnforceMinExitDistance = false
            });
            var entry = plan.Entry;
            var sl = plan.Sl;
            var tp = plan.Tp;
            var labelPrice = executionSide == "BUY"
                ? candle.Low - tickSize * 10
                : candle.High + tickSize * 10;

            AddText(
                $"EW_SCORE_ENTRY_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                $"{score.SignalSource} ENTRY {entry:0.00} | S{score.Score} | {score.SpeedLabel}",
                executionSide == "SELL",
                bar,
                labelPrice,
                Color.White,
                executionSide == "BUY" ? Color.Blue : Color.Red,
                executionSide == "BUY" ? Color.Blue : Color.Red,
                12,
                DrawingText.TextAlign.Center,
                true);

            var endBar = bar + LineLength;

            TrendLines.Add(new TrendLine(bar, entry, endBar, entry, new Pen(Color.Gold, 3)));
            TrendLines.Add(new TrendLine(bar, tp, endBar, tp, new Pen(Color.LimeGreen, 3)));

            DrawTradeLabel($"EW_ENTRY_{candle.Time:yyyyMMdd_HHmm}_{bar}", $"ENTRY {entry:0.00}", bar, entry, Color.Black, Color.Gold, -30);
            DrawTradeLabel($"EW_TP_{candle.Time:yyyyMMdd_HHmm}_{bar}", $"TP {tp:0.00} | {plan.TpTicks:0}t", bar + 1, tp, Color.White, Color.Green, 16);

            _tradeBar = bar;
            _tradeSide = executionSide;
            _tradeEntry = entry;
            _entryBarHighAtEntry = score.EntryBarHighAtEntry;
            _entryBarLowAtEntry = score.EntryBarLowAtEntry;
            _tradeSl = 0;
            _tradeTp = tp;
            _bestFavorablePrice = entry;
            _lastManagePrice = entry;
            _lastManageTimeUtc = TryGetCandleUpdateTime(candle);
            _bestFavorableTimeUtc = _lastManageTimeUtc;
            _tradeIsAPlusSpeed = plan.IsAPlusSpeed;

            if (!_tradeIsAPlusSpeed)
                DrawLiveExitSpeed(bar, candle, 0);
        }

        private void TryDrawAPlusAbsorptionDebugLabel(int bar, dynamic candle, ScoreTradeSignal score)
        {
            if (!ShowAPlusAbsorptionDebugLabel || score == null)
                return;

            var tickSize = GetTickSize();
            var labelPrice = candle.Low - tickSize * 55m;
            var source = string.IsNullOrWhiteSpace(score.SignalSource) ? "NA" : score.SignalSource;
            var side = string.IsNullOrWhiteSpace(score.Side) ? "NA" : score.Side;
            var executionSide = string.IsNullOrWhiteSpace(score.ExecutionSide) ? "NA" : score.ExecutionSide;
            var structureSide = string.IsNullOrWhiteSpace(score.APlusStructureSide) ? "NA" : score.APlusStructureSide;

            AddText(
                $"EW_APLUS_ABS_DBG_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                $"ABS DBG | SRC={source} | ABS={Flag(score.HasAPlusAbsorption)} | STRUCT={Flag(score.HasAPlusStructure)} {structureSide}@{FormatNullablePrice(score.APlusStructurePrice)} | SIDE={side} EXEC={executionSide} | ACC_IMB={Flag(score.PriceAcceptedAfterImbalance)} ACC_SPD={Flag(score.PriceAcceptedAfterSpeed)} | READY={Flag(score.IsReady)}",
                true,
                bar,
                labelPrice,
                0,
                0,
                Color.Black,
                score.HasAPlusAbsorption ? Color.Gold : Color.Silver,
                score.HasAPlusAbsorption ? Color.Gold : Color.Silver,
                10,
                DrawingText.TextAlign.Center,
                true);
        }

        private void ManageActiveTrade(int bar, dynamic candle)
        {
            if (_tradeSide == "")
                return;

            if (_tradeHitDrawn)
                return;

            UpdateActiveTradeStopFromLastImbalance(bar, candle);

            if (_tradeIsAPlusSpeed)
            {
                TryDrawFirstTradeHit(bar, candle);
                return;
            }

            var tickSize = GetTickSize();
            var currentPrice = candle.Close;
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
                candle.High,
                candle.Low);

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
                candle.High,
                candle.Low,
                (decimal)elapsedSeconds,
                (decimal)adverseElapsedSeconds,
                PanicPullbackTicks,
                tickSize);

            DrawLiveExitSpeed(bar, candle, metrics.AdverseSpeed);

            _lastManagePrice = metrics.AdversePrice;
            _lastManageTimeUtc = currentTime;

            decimal hitHigh;
            decimal hitLow;
            GetPostEntryHitRange(bar, candle, out hitHigh, out hitLow);
            var speedPanic = metrics.AdverseSpeed > PanicAdverseSpeedTicksPerSecond;

            TryDrawFirstTradeHit(bar, candle);

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

            var panicReason = "SPEED+FLOW";

            DrawPanicBreakEven(bar, metrics.PanicTriggerPrice, metrics.MfeTicks, metrics.PullbackTicks, metrics.AdverseSpeed, panicReason);
            _panicDrawn = true;
        }

        private void UpdateActiveTradeStopFromLastImbalance(int bar, dynamic candle)
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
            var endBar = bar + LineLength;
            if (_activeSlLine != null)
                TrendLines.Remove(_activeSlLine);

            _activeSlLine = new TrendLine(bar, _tradeSl, endBar, _tradeSl, new Pen(Color.Red, 3));
            TrendLines.Add(_activeSlLine);
            DrawTradeLabel(
                $"EW_ACTIVE_SL_{_currentDate:yyyyMMdd}",
                $"SL {_tradeSl:0.00} | {slTicks:0}t{(imbalanceStop != null ? " IMB" : "")}",
                bar + 1,
                _tradeSl,
                Color.White,
                Color.Red,
                -38);
        }

        private void TryDrawFirstTradeHit(int bar, dynamic candle)
        {
            if (_tradeHitDrawn)
                return;

            decimal hitHigh;
            decimal hitLow;
            GetPostEntryHitRange(bar, candle, out hitHigh, out hitLow);

            if (_tradeSide == "BUY")
            {
                if (_tradeTp != 0 && TradeManagerTpSlBeExit.IsTpHit(_tradeSide, hitHigh, hitLow, _tradeTp))
                {
                    DrawTradeHit(bar, "TP HIT", _tradeTp, Color.LimeGreen, Color.White, 18);
                    _tradeHitDrawn = true;
                    return;
                }

                if (_tradeSl != 0 && TradeManagerTpSlBeExit.IsSlHit(_tradeSide, hitHigh, hitLow, _tradeSl))
                {
                    DrawTradeHit(bar, "SL HIT", _tradeSl, Color.Red, Color.White, -54);
                    _tradeHitDrawn = true;
                    return;
                }
            }
            else if (_tradeSide == "SELL")
            {
                if (_tradeTp != 0 && TradeManagerTpSlBeExit.IsTpHit(_tradeSide, hitHigh, hitLow, _tradeTp))
                {
                    DrawTradeHit(bar, "TP HIT", _tradeTp, Color.LimeGreen, Color.White, 18);
                    _tradeHitDrawn = true;
                    return;
                }

                if (_tradeSl != 0 && TradeManagerTpSlBeExit.IsSlHit(_tradeSide, hitHigh, hitLow, _tradeSl))
                {
                    DrawTradeHit(bar, "SL HIT", _tradeSl, Color.Red, Color.White, -54);
                    _tradeHitDrawn = true;
                    return;
                }
            }

        }

        private void DrawTradeHit(int bar, string text, decimal price, Color bgColor, Color textColor, int yOffset)
        {
            DrawTradeLabel(
                $"EW_{text.Replace(" ", "_")}_{_currentDate:yyyyMMdd}",
                $"{text} {price:0.00}",
                bar + 2,
                price,
                textColor,
                bgColor,
                yOffset);
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

        private void DrawLiveExitSpeed(int bar, dynamic candle, decimal adverseSpeed)
        {
            var tickSize = GetTickSize();
            var price = _tradeSide == "BUY"
                ? candle.Close - tickSize * 14
                : candle.Close + tickSize * 14;
            var isValidSpeed = adverseSpeed >= PanicAdverseSpeedTicksPerSecond;

            AddText(
                "EW_SCORE_STATUS",
                $"LIVE EXIT SPEED {_tradeSide} {adverseSpeed:0.00}t/s | PRICE {candle.Close:0.00} | SL {(isValidSpeed ? "VALID" : "WAIT")}",
                true,
                bar,
                price,
                _tradeSide == "BUY" ? 18 : -18,
                0,
                Color.White,
                isValidSpeed ? Color.Purple : Color.DimGray,
                isValidSpeed ? Color.Purple : Color.DimGray,
                12,
                DrawingText.TextAlign.Center,
                true);
        }

        private void DrawPanicBreakEven(int bar, decimal panicPrice, decimal mfeTicks, decimal pullbackTicks, decimal adverseSpeed, string reason)
        {
            var endBar = bar + LineLength;
            var purple = Color.MediumPurple;

            TrendLines.Add(new TrendLine(bar, panicPrice, endBar, panicPrice, new Pen(purple, 3)));
            TrendLines.Add(new TrendLine(bar, _tradeEntry, endBar, _tradeEntry, new Pen(Color.Red, 4)));

            DrawTradeLabel(
                $"EW_PANIC_{_currentDate:yyyyMMdd}_{bar}",
                $"PANIC {panicPrice:0.00} | {reason} | MFE {mfeTicks:0}t PB {pullbackTicks:0}t {adverseSpeed:0.00}t/s",
                bar - 1,
                panicPrice,
                Color.White,
                purple,
                -52);

            DrawTradeLabel(
                $"EW_SL_BE_{_currentDate:yyyyMMdd}_{bar}",
                $"SL BE {_tradeEntry:0.00}",
                bar + 1,
                _tradeEntry,
                Color.White,
                Color.Red,
                20);
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

        private void DrawScoreLabel(int bar, dynamic candle, ScoreTradeSignal score)
        {
            var tickSize = GetTickSize();
            var price = candle.High + ScoreLabelOffsetTicks * tickSize;
            var status = score.IsReady ? "VALID" : "WAIT";
            var side = score.Side == "" ? "NO BREAK" : score.Side;
            var background = score.IsReady
                ? Color.DarkGreen
                : score.IsBreakout && score.Score >= MinScore
                    ? Color.DarkRed
                    : score.IsBreakout
                    ? Color.DarkOrange
                    : Color.DimGray;

            AddText(
                "EW_SCORE_STATUS",
                $"{status} {side} {score.SignalSource} S{score.Score}/11 | OR {score.OrRangeTicks:0}t BODY {score.BodyBreakoutTicks:0}t | {score.SpeedLabel} {score.BreakoutSpeed:0.00}t/s | R{Flag(score.RangeOk)} B{Flag(score.BodyOk)} V{Flag(score.VolumeOk)} D{Flag(score.DeltaOk)} VW{Flag(score.VwapOk)} S{Flag(score.SpeedValid)} I{score.ImbalanceScore}",
                true,
                bar,
                price,
                0,
                0,
                Color.White,
                background,
                background,
                12,
                DrawingText.TextAlign.Center,
                true);
        }

        private void DrawTradeLabel(string id, string text, int bar, decimal price, Color textColor, Color bgColor)
        {
            DrawTradeLabel(id, text, bar, price, textColor, bgColor, -18);
        }

        private void DrawTradeLabel(string id, string text, int bar, decimal price, Color textColor, Color bgColor, int yOffset)
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

        private bool TryDrawTimeOver(int bar, dynamic candle)
        {
            var time = candle.Time.TimeOfDay;

            if (_timeOverDrawn ||
                _tradeDrawn ||
                time < MaxSignalTimeUtc)
            {
                return false;
            }

            _timeOverDrawn = true;
            DrawTimeOverLabel(bar, candle);
            return true;
        }

        private void DrawTimeOverLabel(int bar, dynamic candle)
        {
            AddText(
                $"EW_TIME_OVER_{_currentDate:yyyyMMdd}_{bar}",
                "TIME OVER",
                true,
                bar,
                candle.High + GetTickSize() * ScoreLabelOffsetTicks,
                0,
                0,
                Color.White,
                Color.Blue,
                Color.Blue,
                14,
                DrawingText.TextAlign.Center,
                true);
        }

        private bool IsOpeningCandle(dynamic candle)
        {
            var time = candle.Time.TimeOfDay;
            return time.Hours == OpeningTimeUtc.Hours && time.Minutes == OpeningTimeUtc.Minutes;
        }

        private void UpdateSpeedClock(int bar)
        {
            _signalEngine.UpdateSpeedClock(bar);
        }

        private decimal CalculateBreakoutSpeed(dynamic candle, decimal bodyBreakoutTicks)
        {
            return SpeedClasification.CalculateBreakoutSpeed(candle, bodyBreakoutTicks, DateTime.UtcNow, ReplaySpeedMultiplier);
        }

        private DateTime TryGetCandleUpdateTime(dynamic candle)
        {
            return SpeedClasification.TryGetCandleUpdateTime(candle);
        }

        private DateTime TryGetCandleUpdateTime(dynamic candle, out string timingSource)
        {
            return SpeedClasification.TryGetCandleUpdateTime(candle, out timingSource);
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
            var time = candle.Time.TimeOfDay;
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
            _bestFavorablePrice = 0;
            _lastManagePrice = 0;
            _lastManageTimeUtc = DateTime.MinValue;
            _bestFavorableTimeUtc = DateTime.MinValue;
            _tradeIsAPlusSpeed = false;
            _tradeSl = 0;
            _tradeTp = 0;
            _activeSlLine = null;
            _tradeHitDrawn = false;
            _timeOverDrawn = false;
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
