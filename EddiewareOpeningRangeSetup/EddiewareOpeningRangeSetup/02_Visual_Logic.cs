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

        [DisplayName("Imbalance Compare Min Volume")]
        public decimal ImbalanceCompareMinVolume { get; set; } = 5m;

        [DisplayName("Show A+ Structure Label")]
        public bool ShowAPlusStructureLabel { get; set; } = true;

        [DisplayName("Show A+ Structure Debug Label")]
        public bool ShowAPlusStructureDebugLabel { get; set; } = false;

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
            TryDrawAPlusStructureLabel(bar, candle, score.Side);

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
                ImbalanceCompareMinVolume = ImbalanceCompareMinVolume
            });
        }

        private void TryDrawAPlusStructureLabel(int bar, dynamic candle, string setupSide)
        {
            if (!ShowAPlusStructureLabel)
                return;

            var state = ImbalanceDetector.Detect(candle, new ImbalanceDetectorRequest
            {
                Ratio = ImbalanceRatio,
                CompareMinVolume = ImbalanceCompareMinVolume
            });

            var tickSize = GetTickSize();

            var sideToDraw = ResolveAPlusStructureSide(candle, state, setupSide);

            TryDrawAPlusStructureDebugLabel(bar, candle, state, sideToDraw);

            if (sideToDraw == "BUY")
            {
                var price = state.Buy3_ImbalanceGroupPrice ?? candle.Low;
                var labelPrice = Math.Min(price, candle.Low) - tickSize * APlusStructureLabelOffsetTicks;

                AddText(
                    $"EW_APLUS_IMBALANCE_BUY_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                    "A+ STRUCTURE",
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
                var price = state.Sell3_ImbalanceGroupPrice ?? candle.High;
                var labelPrice = Math.Max(price, candle.High) + tickSize * APlusStructureLabelOffsetTicks;

                AddText(
                    $"EW_APLUS_IMBALANCE_SELL_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                    "A+ STRUCTURE",
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

        private void TryDrawAPlusStructureDebugLabel(int bar, dynamic candle, ImbalanceState state, string sideToDraw)
        {
            if (!ShowAPlusStructureDebugLabel)
                return;

            if (!state.HasBuy3_ImbalanceGroup && !state.HasSell3_ImbalanceGroup)
                return;

            var debug = CalculateImbalanceDebugInfo(candle);
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
                $"DBG IMB | BUY3={state.HasBuy3_ImbalanceGroup}({debug.MaxBuyStreak}) @{FormatNullablePrice(state.Buy3_ImbalanceGroupPrice)} | SELL3={state.HasSell3_ImbalanceGroup}({debug.MaxSellStreak}) @{FormatNullablePrice(state.Sell3_ImbalanceGroupPrice)} | DRAW={sideToDraw} | BODY={bodySide}",
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

        private ImbalanceDebugInfo CalculateImbalanceDebugInfo(dynamic candle)
        {
            var info = new ImbalanceDebugInfo();
            var levels = GetSortedPriceLevels(candle);

            if (levels.Count < 2)
                return info;

            var buyStreak = 0;
            var sellStreak = 0;

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];
                var buyImbalance = false;
                var sellImbalance = false;

                if (i > 0)
                {
                    var lowerLevel = levels[i - 1];
                    buyImbalance =
                        lowerLevel.Bid >= ImbalanceCompareMinVolume &&
                        level.Ask >= lowerLevel.Bid * ImbalanceRatio;
                }

                if (i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];
                    sellImbalance =
                        upperLevel.Ask >= ImbalanceCompareMinVolume &&
                        level.Bid >= upperLevel.Ask * ImbalanceRatio;
                }

                if (buyImbalance)
                {
                    buyStreak++;
                    if (buyStreak > info.MaxBuyStreak)
                        info.MaxBuyStreak = buyStreak;
                }
                else
                {
                    buyStreak = 0;
                }

                if (sellImbalance)
                {
                    sellStreak++;
                    if (sellStreak > info.MaxSellStreak)
                        info.MaxSellStreak = sellStreak;
                }
                else
                {
                    sellStreak = 0;
                }
            }

            return info;
        }

        private string FormatNullablePrice(decimal? price)
        {
            return price.HasValue ? price.Value.ToString("0.00") : "NA";
        }

        private string ResolveAPlusStructureSide(dynamic candle, ImbalanceState state, string setupSide)
        {
            if (string.IsNullOrWhiteSpace(setupSide))
                return "";

            setupSide = setupSide.Trim().ToUpperInvariant();

            // Only print the A+ Structure label when the 3+ imbalance group
            // matches the current setup/entry side.
            if (setupSide == "BUY" && state.HasBuy3_ImbalanceGroup)
                return "BUY";

            if (setupSide == "SELL" && state.HasSell3_ImbalanceGroup)
                return "SELL";

            return "";
        }

        private void DrawTrade(int bar, dynamic candle, ScoreTradeSignal score)
        {
            if (!ShowEntrySlTp || score.Side == "")
                return;

            var tickSize = GetTickSize();
            var rawImbalanceStop = score.SpeedLabel == "A+ speed" || score.SpeedLabel == "normal speed"
                ? null
                : TryGetImbalanceStop(candle, score.Side);
            var plan = TradeManagerTpSlBeExit.CreateInitialPlan(new TradeManagerTpSlBeExit.TradePlanRequest
            {
                Side = score.Side,
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
            var labelPrice = score.Side == "BUY"
                ? candle.Low - tickSize * 10
                : candle.High + tickSize * 10;

            AddText(
                $"EW_SCORE_ENTRY_{candle.Time:yyyyMMdd_HHmm}_{bar}",
                $"{plan.EntryProfile} ENTRY {entry:0.00} | S{score.Score} | {score.SpeedLabel}",
                score.Side == "SELL",
                bar,
                labelPrice,
                Color.White,
                score.Side == "BUY" ? Color.Blue : Color.Red,
                score.Side == "BUY" ? Color.Blue : Color.Red,
                12,
                DrawingText.TextAlign.Center,
                true);

            var endBar = bar + LineLength;

            TrendLines.Add(new TrendLine(bar, entry, endBar, entry, new Pen(Color.Gold, 3)));
            TrendLines.Add(new TrendLine(bar, sl, endBar, sl, new Pen(Color.Red, 3)));
            TrendLines.Add(new TrendLine(bar, tp, endBar, tp, new Pen(Color.LimeGreen, 3)));

            DrawTradeLabel($"EW_ENTRY_{candle.Time:yyyyMMdd_HHmm}_{bar}", $"ENTRY {entry:0.00}", bar, entry, Color.Black, Color.Gold, -30);
            DrawTradeLabel($"EW_SL_{candle.Time:yyyyMMdd_HHmm}_{bar}", $"SL {sl:0.00} | {plan.SlTicks:0}t{(plan.UsesImbalanceStop ? " IMB" : "")}", bar + 1, sl, Color.White, Color.Red, -38);
            DrawTradeLabel($"EW_TP_{candle.Time:yyyyMMdd_HHmm}_{bar}", $"TP {tp:0.00} | {plan.TpTicks:0}t", bar + 1, tp, Color.White, Color.Green, 16);

            _tradeBar = bar;
            _tradeSide = score.Side;
            _tradeEntry = entry;
            _entryBarHighAtEntry = score.EntryBarHighAtEntry;
            _entryBarLowAtEntry = score.EntryBarLowAtEntry;
            _tradeSl = sl;
            _tradeTp = tp;
            _bestFavorablePrice = entry;
            _lastManagePrice = entry;
            _lastManageTimeUtc = TryGetCandleUpdateTime(candle);
            _bestFavorableTimeUtc = _lastManageTimeUtc;
            _tradeIsAPlusSpeed = plan.IsAPlusSpeed;

            if (!_tradeIsAPlusSpeed)
                DrawLiveExitSpeed(bar, candle, 0);
        }

        private ImbalanceStop TryGetImbalanceStop(dynamic candle, string side)
        {
            var tickSize = GetTickSize();
            var levels = GetSortedPriceLevels(candle);

            if (levels.Count < 2)
                return null;

            decimal? imbalancePrice = null;

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];

                if (side == "BUY" && i > 0)
                {
                    var lowerLevel = levels[i - 1];

                    if (lowerLevel.Bid >= ImbalanceCompareMinVolume &&
                        level.Ask >= lowerLevel.Bid * ImbalanceRatio)
                    {
                        if (!imbalancePrice.HasValue || level.Price > imbalancePrice.Value)
                            imbalancePrice = level.Price;
                    }
                }

                if (side == "SELL" && i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    if (upperLevel.Ask >= ImbalanceCompareMinVolume &&
                        level.Bid >= upperLevel.Ask * ImbalanceRatio)
                    {
                        if (!imbalancePrice.HasValue || level.Price < imbalancePrice.Value)
                            imbalancePrice = level.Price;
                    }
                }
            }

            if (!imbalancePrice.HasValue)
                return null;

            return new ImbalanceStop
            {
                ImbalancePrice = imbalancePrice.Value,
                StopPrice = side == "BUY"
                    ? imbalancePrice.Value - tickSize
                    : imbalancePrice.Value + tickSize
            };
        }

        private List<FootprintLevel> GetSortedPriceLevels(dynamic candle)
        {
            var result = new List<FootprintLevel>();

            try
            {
                foreach (var level in candle.GetAllPriceLevels())
                {
                    result.Add(new FootprintLevel
                    {
                        Price = Convert.ToDecimal(level.Price),
                        Bid = Convert.ToDecimal(level.Bid),
                        Ask = Convert.ToDecimal(level.Ask)
                    });
                }
            }
            catch
            {
                return result;
            }

            result.Sort((left, right) => left.Price.CompareTo(right.Price));

            return result;
        }

        private void ManageActiveTrade(int bar, dynamic candle)
        {
            if (_tradeSide == "")
                return;

            if (_tradeHitDrawn)
                return;

            if (_tradeIsAPlusSpeed)
            {
                TryDrawFirstTradeHit(bar, candle);
                return;
            }

            var tickSize = GetTickSize();
            var currentPrice = candle.Close;
            string timingSource;
            var currentTime = TryGetCandleUpdateTime(candle, out timingSource);
            var elapsedSeconds = (currentTime - _lastManageTimeUtc).TotalSeconds;

            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
                elapsedSeconds = 1;
            else if (timingSource == "UtcNow" || elapsedSeconds < 1)
                elapsedSeconds *= (double)NormalizeReplaySpeedMultiplier();

            if (_tradeSide == "BUY")
            {
                if (candle.High > _bestFavorablePrice)
                {
                    _bestFavorablePrice = candle.High;
                    _bestFavorableTimeUtc = currentTime;
                }
            }
            else
            {
                if (_bestFavorablePrice == 0 || candle.Low < _bestFavorablePrice)
                {
                    _bestFavorablePrice = candle.Low;
                    _bestFavorableTimeUtc = currentTime;
                }
            }

            var adversePrice = _tradeSide == "BUY" ? candle.Low : candle.High;
            var adverseElapsedSeconds = (currentTime - _bestFavorableTimeUtc).TotalSeconds;

            if (adverseElapsedSeconds <= 0 || adverseElapsedSeconds > 300)
                adverseElapsedSeconds = elapsedSeconds;
            else if (timingSource == "UtcNow" || adverseElapsedSeconds < 1)
                adverseElapsedSeconds *= (double)NormalizeReplaySpeedMultiplier();

            var mfeTicks = _tradeSide == "BUY"
                ? RoundToTicks(_bestFavorablePrice - _tradeEntry)
                : RoundToTicks(_tradeEntry - _bestFavorablePrice);

            var pullbackTicks = _tradeSide == "BUY"
                ? RoundToTicks(_bestFavorablePrice - adversePrice)
                : RoundToTicks(adversePrice - _bestFavorablePrice);

            var adverseMoveTicks = _tradeSide == "BUY"
                ? RoundToTicks(Math.Max(0, _lastManagePrice - adversePrice))
                : RoundToTicks(Math.Max(0, adversePrice - _lastManagePrice));

            var adverseSpeed = Math.Max(
                adverseMoveTicks / (decimal)elapsedSeconds,
                pullbackTicks / (decimal)adverseElapsedSeconds);

            DrawLiveExitSpeed(bar, candle, adverseSpeed);

            _lastManagePrice = adversePrice;
            _lastManageTimeUtc = currentTime;

            decimal hitHigh;
            decimal hitLow;
            GetPostEntryHitRange(bar, candle, out hitHigh, out hitLow);
            var exitTouchPrice = _tradeSide == "BUY" ? hitLow : hitHigh;
            var speedPanic = adverseSpeed > PanicAdverseSpeedTicksPerSecond;

            TryDrawFirstTradeHit(bar, candle);

            if (_tradeHitDrawn)
                return;

            if (_panicDrawn)
                return;

            var weakDelta = candle.Delta <= 0 && candle.Delta > -MinAbsDelta;
            var weakVolume = candle.Volume >= 0 && candle.Volume < MinVolume;
            var vwapFailed = HasVwapFailed(bar, candle);
            var weakFlowPanic = weakDelta && weakVolume && vwapFailed;

            if (mfeTicks < PanicMfeTriggerTicks ||
                pullbackTicks < PanicPullbackTicks ||
                !speedPanic ||
                !weakFlowPanic)
                return;

            var panicTriggerPrice = _tradeSide == "BUY"
                ? _bestFavorablePrice - PanicPullbackTicks * GetTickSize()
                : _bestFavorablePrice + PanicPullbackTicks * GetTickSize();
            var panicReason = "SPEED+FLOW";

            DrawPanicBreakEven(bar, panicTriggerPrice, mfeTicks, pullbackTicks, adverseSpeed, panicReason);
            _panicDrawn = true;
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
            if (bar != _tradeBar)
            {
                hitHigh = candle.High;
                hitLow = candle.Low;
                return;
            }

            hitHigh = candle.Close;
            hitLow = candle.Close;

            if (candle.High > _entryBarHighAtEntry)
                hitHigh = candle.High;

            if (candle.Low < _entryBarLowAtEntry)
                hitLow = candle.Low;
        }

        private bool HasVwapFailed(int bar, dynamic candle)
        {
            var vwap = GetSessionVwap(bar, candle.Time.Date);

            return _tradeSide == "BUY"
                ? candle.Close < vwap
                : candle.Close > vwap;
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
                $"{status} {side} S{score.Score}/11 | OR {score.OrRangeTicks:0}t BODY {score.BodyBreakoutTicks:0}t | {score.SpeedLabel} {score.BreakoutSpeed:0.00}t/s | R{Flag(score.RangeOk)} B{Flag(score.BodyOk)} V{Flag(score.VolumeOk)} D{Flag(score.DeltaOk)} VW{Flag(score.VwapOk)} S{Flag(score.SpeedValid)} I{score.ImbalanceScore}",
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
            return ReplaySpeedMultiplier <= 0 ? 1 : ReplaySpeedMultiplier;
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

        private decimal GetSessionVwap(int bar, DateTime date)
        {
            decimal cumPv = 0;
            decimal cumVol = 0;

            for (var i = bar; i >= 0; i--)
            {
                var candle = GetCandle(i);

                if (candle.Time.Date != date)
                    break;

                var volume = candle.Volume;

                if (volume <= 0)
                    continue;

                var typical = (candle.High + candle.Low + candle.Close) / 3m;

                cumPv += typical * volume;
                cumVol += volume;
            }

            return cumVol <= 0 ? 0 : cumPv / cumVol;
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
            _tradeHitDrawn = false;
            _timeOverDrawn = false;
        }

        private decimal RoundToTicks(decimal points)
        {
            return Math.Round(points / GetTickSize(), 2);
        }

        private decimal ClampTicks(decimal ticks)
        {
            var maxTicks = Math.Min(MaxTradeTicks, HardMaxTradeTicks);

            return Math.Max(MinTradeTicks, Math.Min(ticks, maxTicks));
        }

        private decimal ClampExitDistance(decimal entry, decimal exit, int direction)
        {
            var tickSize = GetTickSize();
            var maxDistance = HardMaxTradeTicks * tickSize;
            var currentDistance = Math.Abs(exit - entry);

            if (currentDistance <= maxDistance)
                return exit;

            return entry + direction * maxDistance;
        }

        private decimal GetTickSize()
        {
            return FallbackTickSize;
        }

        private string Flag(bool value)
        {
            return value ? "+" : "-";
        }

        private sealed class ImbalanceDebugInfo
        {
            public int MaxBuyStreak { get; set; }
            public int MaxSellStreak { get; set; }
        }

        private class FootprintLevel
        {
            public decimal Price { get; set; }
            public decimal Bid { get; set; }
            public decimal Ask { get; set; }
        }

        private class ImbalanceStop
        {
            public decimal ImbalancePrice { get; set; }
            public decimal StopPrice { get; set; }
        }
    }
}
