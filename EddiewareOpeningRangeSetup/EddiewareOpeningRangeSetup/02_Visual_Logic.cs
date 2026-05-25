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
        private const decimal HardMaxTradeTicks = 120m;
        private const decimal APlusStopTicks = 100m;

        private DateTime _currentDate = DateTime.MinValue;
        private decimal _orHigh;
        private decimal _orLow;
        private int _orBar = -1;
        private bool _orReady;
        private bool _tradeDrawn;
        private int _speedBar = -1;
        private DateTime _speedBarStartedAtUtc = DateTime.MinValue;
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
        private decimal _trailingExitPrice;
        private decimal _lastDrawnTrailingExitPrice;
        private decimal _lastTrailingStepPrice;
        private TrendLine _trailingExitLine;
        private bool _tradeIsAPlusSpeed;
        private bool _trailingExitHit;
        private decimal _tradeSl;
        private decimal _tradeTp;
        private bool _tradeHitDrawn;

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Max Signal Time UTC")]
        public TimeSpan MaxSignalTimeUtc { get; set; } = new TimeSpan(14, 30, 0);

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
        public decimal MaxTradeTicks { get; set; } = 120;

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

        [DisplayName("Trailing Exit Ticks")]
        public decimal TrailingExitTicks { get; set; } = 10;

        [DisplayName("Half MFE Exit Min MFE Ticks")]
        public decimal HalfMfeExitMinMfeTicks { get; set; } = 40;

        [DisplayName("Imbalance Ratio")]
        public decimal ImbalanceRatio { get; set; } = 3m;

        [DisplayName("Imbalance Compare Min Volume")]
        public decimal ImbalanceCompareMinVolume { get; set; } = 5m;

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

            if (!_orReady || _tradeDrawn || bar <= _orBar || !IsSignalWindow(candle))
                return;

            var score = CalculateScore(candle, bar);

            if (ShowScoreLabel)
                DrawScoreLabel(bar, candle, score);

            if (!score.IsBreakout || score.Value < MinScore || !score.SpeedValid)
                return;

            DrawTrade(bar, candle, score);
            _tradeDrawn = true;
        }

        private ScoreState CalculateScore(dynamic candle, int bar)
        {
            var vwap = GetSessionVwap(bar, candle.Time.Date);
            var longBreakout = candle.Close > _orHigh;
            var shortBreakout = candle.Close < _orLow;
            var orRangeTicks = RoundToTicks(_orHigh - _orLow);
            decimal bodyBreakoutTicks = 0;

            if (longBreakout)
                bodyBreakoutTicks = RoundToTicks(candle.Close - Math.Max(candle.Open, _orHigh));

            if (shortBreakout)
                bodyBreakoutTicks = RoundToTicks(Math.Min(candle.Open, _orLow) - candle.Close);

            if (bodyBreakoutTicks < 0)
                bodyBreakoutTicks = 0;

            var state = new ScoreState
            {
                IsBreakout = longBreakout || shortBreakout,
                Side = longBreakout ? "BUY" : shortBreakout ? "SELL" : "",
                Entry = candle.Close,
                OrRangeTicks = orRangeTicks,
                BodyBreakoutTicks = bodyBreakoutTicks,
                RangeOk = orRangeTicks >= MinOrRangeTicks && orRangeTicks <= MaxOrRangeTicks,
                BodyOk = bodyBreakoutTicks >= MinBodyBreakoutTicks,
                VolumeOk = candle.Volume >= MinVolume,
                DeltaOk = Math.Abs(candle.Delta) >= MinAbsDelta,
                VwapOk =
                    (longBreakout && candle.Close >= vwap) ||
                    (shortBreakout && candle.Close <= vwap)
            };

            state.SpeedTicksPerSecond = CalculateBreakoutSpeed(candle, bodyBreakoutTicks);
            state.SpeedLabel = GetSpeedLabel(state.SpeedTicksPerSecond);
            state.SpeedValid = state.SpeedLabel == "normal speed" || state.SpeedLabel == "A+ speed";

            if (state.VwapOk) state.Value += 2;
            if (state.RangeOk) state.Value += 1;
            if (state.BodyOk) state.Value += 1;
            if (state.VolumeOk) state.Value += 1;
            if (state.DeltaOk) state.Value += 1;
            if (state.SpeedValid) state.Value += 1;

            return state;
        }

        private void DrawTrade(int bar, dynamic candle, ScoreState score)
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
                Entry = score.Entry,
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
                $"{plan.EntryProfile} ENTRY {entry:0.00} | S{score.Value} | {score.SpeedLabel}",
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
            _entryBarHighAtEntry = candle.High;
            _entryBarLowAtEntry = candle.Low;
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

            if (_trailingExitHit)
                return;

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
            var slTouched = _tradeSl != 0 && TradeManagerTpSlBeExit.IsSlHit(_tradeSide, hitHigh, hitLow, _tradeSl);

            if (TryDrawFastExit(bar, mfeTicks, pullbackTicks, speedPanic, slTouched))
                return;

            if (TryDrawHalfMfeExit(bar, exitTouchPrice, mfeTicks))
                return;

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

        private bool TryDrawFastExit(int bar, decimal mfeTicks, decimal pullbackTicks, bool speedPanic, bool slTouched)
        {
            if (_tradeHitDrawn)
                return false;

            if (mfeTicks < HalfMfeExitMinMfeTicks ||
                pullbackTicks < PanicPullbackTicks ||
                (!speedPanic && !slTouched))
                return false;

            var exitPrice = TradeManagerTpSlBeExit.CalculateHalfMfeExit(
                _tradeSide,
                _tradeEntry,
                _bestFavorablePrice);
            var resultTicks = TradeManagerTpSlBeExit.TradeResultTicks(
                "EXIT",
                _tradeEntry,
                RoundToTicks(Math.Abs(_tradeEntry - _tradeTp)),
                RoundToTicks(Math.Abs(_tradeEntry - _tradeSl)),
                exitPrice,
                GetTickSize());

            if (resultTicks <= 0)
                return false;

            _trailingExitPrice = exitPrice;
            DrawTrailingExit(bar, exitPrice);

            return false;
        }

        private bool TryDrawHalfMfeExit(int bar, decimal adversePrice, decimal mfeTicks)
        {
            if (_tradeHitDrawn)
                return false;

            if (mfeTicks < HalfMfeExitMinMfeTicks)
                return false;

            var halfMfeExit = TradeManagerTpSlBeExit.CalculateHalfMfeExit(
                _tradeSide,
                _tradeEntry,
                _bestFavorablePrice);

            var touched = TradeManagerTpSlBeExit.IsHalfMfeExitTouched(_tradeSide, adversePrice, halfMfeExit);

            if (!touched)
                return false;

            _trailingExitPrice = halfMfeExit;
            DrawTrailingExit(bar, halfMfeExit);
            DrawTradeHit(bar, "EXIT HIT", halfMfeExit, Color.Orange, Color.Black, 18);
            _trailingExitHit = true;
            _tradeHitDrawn = true;

            return true;
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

            if (_trailingExitPrice == 0)
                return;

            var exitTouched = _tradeSide == "BUY"
                ? hitLow <= _trailingExitPrice
                : hitHigh >= _trailingExitPrice;

            if (!exitTouched)
                return;

            DrawTradeHit(bar, "EXIT HIT", _trailingExitPrice, Color.Orange, Color.Black, 18);
            _tradeHitDrawn = true;
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

        private void UpdateTrailingExit(int bar)
        {
            var tickSize = GetTickSize();
            var stepPoints = TrailingExitTicks * tickSize;

            if (_lastTrailingStepPrice == 0)
            {
                _lastTrailingStepPrice = _bestFavorablePrice;
            }
            else
            {
                var favorableStepTicks = _tradeSide == "BUY"
                    ? RoundToTicks(_bestFavorablePrice - _lastTrailingStepPrice)
                    : RoundToTicks(_lastTrailingStepPrice - _bestFavorablePrice);

                if (favorableStepTicks < TrailingExitTicks)
                    return;

                _lastTrailingStepPrice = _bestFavorablePrice;
            }

            var nextExit = _tradeSide == "BUY"
                ? _bestFavorablePrice - stepPoints
                : _bestFavorablePrice + stepPoints;

            if (_trailingExitPrice == 0)
            {
                _trailingExitPrice = nextExit;
            }
            else if (_tradeSide == "BUY")
            {
                _trailingExitPrice = Math.Max(_trailingExitPrice, nextExit);
            }
            else
            {
                _trailingExitPrice = Math.Min(_trailingExitPrice, nextExit);
            }

            if (_lastDrawnTrailingExitPrice == _trailingExitPrice)
                return;

            _lastDrawnTrailingExitPrice = _trailingExitPrice;
            DrawTrailingExit(bar, _trailingExitPrice);
        }

        private void DrawTrailingExit(int bar, decimal exitPrice)
        {
            var endBar = bar + LineLength;
            var orange = Color.Orange;

            if (_trailingExitLine != null)
                TrendLines.Remove(_trailingExitLine);

            _trailingExitLine = new TrendLine(bar, exitPrice, endBar, exitPrice, new Pen(orange, 4));
            TrendLines.Add(_trailingExitLine);

            DrawTradeLabel(
                $"EW_TRAIL_EXIT_{_currentDate:yyyyMMdd}",
                $"EXIT {exitPrice:0.00}",
                bar + 2,
                exitPrice,
                Color.Black,
                orange,
                -16);
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

        private void DrawScoreLabel(int bar, dynamic candle, ScoreState score)
        {
            var tickSize = GetTickSize();
            var price = candle.High + ScoreLabelOffsetTicks * tickSize;
            var status = score.IsBreakout && score.Value >= MinScore && score.SpeedValid ? "VALID" : "WAIT";
            var side = score.Side == "" ? "NO BREAK" : score.Side;
            var background = score.IsBreakout && score.Value >= MinScore && score.SpeedValid
                ? Color.DarkGreen
                : score.IsBreakout && score.Value >= MinScore
                    ? Color.DarkRed
                    : score.IsBreakout
                    ? Color.DarkOrange
                    : Color.DimGray;

            AddText(
                "EW_SCORE_STATUS",
                $"{status} {side} S{score.Value}/7 | OR {score.OrRangeTicks:0}t BODY {score.BodyBreakoutTicks:0}t | {score.SpeedLabel} {score.SpeedTicksPerSecond:0.00}t/s | R{Flag(score.RangeOk)} B{Flag(score.BodyOk)} V{Flag(score.VolumeOk)} D{Flag(score.DeltaOk)} VW{Flag(score.VwapOk)} S{Flag(score.SpeedValid)}",
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

        private bool IsOpeningCandle(dynamic candle)
        {
            var time = candle.Time.TimeOfDay;
            return time.Hours == OpeningTimeUtc.Hours && time.Minutes == OpeningTimeUtc.Minutes;
        }

        private void UpdateSpeedClock(int bar)
        {
            if (bar == _speedBar)
                return;

            _speedBar = bar;
            _speedBarStartedAtUtc = DateTime.UtcNow;
        }

        private decimal CalculateBreakoutSpeed(dynamic candle, decimal bodyBreakoutTicks)
        {
            return SpeedClasification.CalculateBreakoutSpeed(candle, bodyBreakoutTicks, _speedBarStartedAtUtc, ReplaySpeedMultiplier);
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
                time <= MaxSignalTimeUtc;
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
            _speedBar = -1;
            _speedBarStartedAtUtc = DateTime.MinValue;
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
            _trailingExitPrice = 0;
            _lastDrawnTrailingExitPrice = 0;
            _lastTrailingStepPrice = 0;
            _trailingExitLine = null;
            _tradeIsAPlusSpeed = false;
            _trailingExitHit = false;
            _tradeSl = 0;
            _tradeTp = 0;
            _tradeHitDrawn = false;
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

        private class ScoreState
        {
            public bool IsBreakout { get; set; }
            public string Side { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal OrRangeTicks { get; set; }
            public decimal BodyBreakoutTicks { get; set; }
            public bool RangeOk { get; set; }
            public bool BodyOk { get; set; }
            public bool VolumeOk { get; set; }
            public bool DeltaOk { get; set; }
            public bool VwapOk { get; set; }
            public decimal SpeedTicksPerSecond { get; set; }
            public string SpeedLabel { get; set; } = "";
            public bool SpeedValid { get; set; }
            public int Value { get; set; }
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
