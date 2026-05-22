using System;
using System.ComponentModel;
using System.Drawing;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    public class EddiewareOpeningRangeVisual : Indicator
    {
        private const decimal SetupTickSize = 0.25m;

        private DateTime _currentDate = DateTime.MinValue;
        private decimal _orHigh;
        private decimal _orLow;
        private int _orBar = -1;

        private bool _orReady;
        private bool _tradeDrawn;
        private PendingBreakout? _pendingBreakout;

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Line Length (bars)")]
        public int LineLength { get; set; } = 80;

        [DisplayName("Min Continuation Ticks")]
        public decimal MinContinuationTicks { get; set; } = 60;

        [DisplayName("Min SL/TP Ticks")]
        public decimal MinTradeTicks { get; set; } = 60;

        [DisplayName("Max SL/TP Ticks")]
        public decimal MaxTradeTicks { get; set; } = 120;

        [DisplayName("Show Opening Range")]
        public bool ShowOpeningRange { get; set; } = true;

        [DisplayName("Show Entry SL TP")]
        public bool ShowEntrySlTp { get; set; } = true;

        [DisplayName("Show Live Score Debug")]
        public bool ShowLiveScoreDebug { get; set; } = true;

        [DisplayName("Use Live Score For Trade")]
        public bool UseLiveScoreForTrade { get; set; } = true;

        [DisplayName("Use Continuation Confirmation")]
        public bool UseContinuationConfirmation { get; set; } = false;

        [DisplayName("Require Body Ok For Trade")]
        public bool RequireBodyOkForTrade { get; set; } = true;

        [DisplayName("Require VWAP Ok For Trade")]
        public bool RequireVwapOkForTrade { get; set; } = false;

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

        [DisplayName("Max Signal Minute UTC")]
        public int MaxSignalMinuteUtc { get; set; } = 50;

        [DisplayName("Live Score Offset Ticks")]
        public decimal LiveScoreOffsetTicks { get; set; } = 35;

        public EddiewareOpeningRangeVisual()
        {
            Name = "Eddieware Opening Range Visual";
            DrawAbovePrice = true;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 2)
                return;

            var current = GetCandle(bar);

            if (current.Time.Date != _currentDate)
            {
                _currentDate = current.Time.Date;
                _orHigh = 0;
                _orLow = 0;
                _orBar = -1;
                _orReady = false;
                _tradeDrawn = false;
                _pendingBreakout = null;
            }

            int closedBar = bar - 1;
            var candle = GetCandle(closedBar);

            if (!_orReady && IsOpeningCandle(candle))
            {
                _orHigh = candle.High;
                _orLow = candle.Low;
                _orBar = closedBar;
                _orReady = true;

                if (ShowOpeningRange)
                    DrawOpeningRange(candle);

                return;
            }

            ScoreState? liveScore = null;

            if (_orReady && bar > _orBar && IsSignalWindow(current))
            {
                liveScore = CalculateLiveScore(current, bar);

                if (ShowLiveScoreDebug)
                    DrawLiveScoreDebug(bar, current, liveScore);

                if (UseLiveScoreForTrade && !_tradeDrawn && liveScore.IsReady)
                {
                    DrawLiveScoreTrade(bar, current, liveScore);
                    _tradeDrawn = true;
                    return;
                }
            }

            if (!_orReady || _tradeDrawn || closedBar <= _orBar)
                return;

            if (!UseContinuationConfirmation)
                return;

            if (_pendingBreakout != null)
            {
                CheckContinuationAndDraw(closedBar, candle);
                _pendingBreakout = null;

                if (_tradeDrawn)
                    return;
            }

            TryCreatePendingBreakout(closedBar, candle);
        }

        private bool IsOpeningCandle(dynamic candle)
        {
            var time = candle.Time.TimeOfDay;
            return time.Hours == OpeningTimeUtc.Hours &&
                   time.Minutes == OpeningTimeUtc.Minutes;
        }

        private bool IsSignalWindow(dynamic candle)
        {
            var time = candle.Time.TimeOfDay;

            return time.Hours == OpeningTimeUtc.Hours &&
                   time.Minutes > OpeningTimeUtc.Minutes &&
                   time.Minutes <= MaxSignalMinuteUtc;
        }

        private ScoreState CalculateLiveScore(dynamic candle, int bar)
        {
            decimal bodyHigh = Math.Max(candle.Open, candle.Close);
            decimal bodyLow = Math.Min(candle.Open, candle.Close);
            bool bullishBreakout = bodyHigh > _orHigh;
            bool bearishBreakout = bodyLow < _orLow;
            decimal vwap = GetSessionVwap(bar, candle.Time.Date);
            decimal orRangeTicks = RoundToTicks(_orHigh - _orLow);
            decimal bodyBreakoutTicks = 0;

            if (bullishBreakout)
                bodyBreakoutTicks = RoundToTicks(bodyHigh - _orHigh);

            if (bearishBreakout)
                bodyBreakoutTicks = RoundToTicks(_orLow - bodyLow);

            if (bodyBreakoutTicks < 0)
                bodyBreakoutTicks = 0;

            var state = new ScoreState
            {
                IsBreakout = bullishBreakout || bearishBreakout,
                Side = bullishBreakout ? "BUY" : bearishBreakout ? "SELL" : "NO BREAK",
                EntryPrice = bullishBreakout ? bodyHigh : bearishBreakout ? bodyLow : candle.Close,
                OrRangeTicks = orRangeTicks,
                BodyBreakoutTicks = bodyBreakoutTicks,
                RangeOk = orRangeTicks >= MinOrRangeTicks && orRangeTicks <= MaxOrRangeTicks,
                BodyOk = bodyBreakoutTicks >= MinBodyBreakoutTicks,
                VolumeOk = candle.Volume >= MinVolume,
                DeltaOk = Math.Abs(candle.Delta) >= MinAbsDelta,
                TimeOk = IsSignalWindow(candle),
                VwapOk =
                    (bullishBreakout && candle.Close >= vwap) ||
                    (bearishBreakout && candle.Close <= vwap)
            };

            if (state.VwapOk) state.Score += 2;
            if (state.RangeOk) state.Score += 1;
            if (state.BodyOk) state.Score += 1;
            if (state.VolumeOk) state.Score += 1;
            if (state.DeltaOk) state.Score += 1;
            if (state.TimeOk) state.Score += 1;

            state.IsReady =
                state.IsBreakout &&
                state.Score >= MinScore &&
                (!RequireBodyOkForTrade || state.BodyOk) &&
                (!RequireVwapOkForTrade || state.VwapOk);

            return state;
        }

        private void DrawLiveScoreDebug(int bar, dynamic candle, ScoreState score)
        {
            var price = candle.High + LiveScoreOffsetTicks * SetupTickSize;
            var status = score.IsReady
                ? "READY"
                : score.IsBreakout && score.Score >= MinScore
                    ? "BLOCK"
                    : "WAIT";
            var background = score.IsReady
                ? Color.DarkGreen
                : score.IsBreakout && score.Score >= MinScore
                    ? Color.DarkRed
                    : score.IsBreakout
                    ? Color.DarkOrange
                    : Color.DimGray;

            AddText(
                "EW_LIVE_SCORE",
                $"{status} {score.Side} S{score.Score}/7 | OR {score.OrRangeTicks:0}t BODY {score.BodyBreakoutTicks:0}t | R{Flag(score.RangeOk)} B{Flag(score.BodyOk)} V{Flag(score.VolumeOk)} D{Flag(score.DeltaOk)} T{Flag(score.TimeOk)} VW{Flag(score.VwapOk)}",
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
                true
            );
        }

        private void DrawLiveScoreTrade(int bar, dynamic candle, ScoreState score)
        {
            if (!ShowEntrySlTp)
                return;

            var breakout = new PendingBreakout
            {
                Bar = bar,
                Time = candle.Time,
                Side = score.Side,
                EntryPrice = score.EntryPrice,
                BreakoutBodyTicks = score.BodyBreakoutTicks
            };

            var trade = BuildTradeLevels(breakout);
            DrawTrade(trade, bar, 0, "SCORE");
        }

        private string Flag(bool value)
        {
            return value ? "+" : "-";
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

                decimal volume = candle.Volume;

                if (volume <= 0)
                    continue;

                decimal typical = (candle.High + candle.Low + candle.Close) / 3m;

                cumPv += typical * volume;
                cumVol += volume;
            }

            if (cumVol <= 0)
                return 0;

            return cumPv / cumVol;
        }

        private void TryCreatePendingBreakout(int closedBar, dynamic candle)
        {
            decimal bodyHigh = Math.Max(candle.Open, candle.Close);
            decimal bodyLow = Math.Min(candle.Open, candle.Close);
            bool bullishBody = candle.Close >= candle.Open;
            bool bearishBody = candle.Close < candle.Open;

            if (bullishBody && bodyHigh > _orHigh)
            {
                _pendingBreakout = new PendingBreakout
                {
                    Bar = closedBar,
                    Time = candle.Time,
                    Side = "BUY",
                    EntryPrice = bodyHigh,
                    BreakoutBodyTicks = RoundToTicks(bodyHigh - _orHigh)
                };
                return;
            }

            if (bearishBody && bodyLow < _orLow)
            {
                _pendingBreakout = new PendingBreakout
                {
                    Bar = closedBar,
                    Time = candle.Time,
                    Side = "SELL",
                    EntryPrice = bodyLow,
                    BreakoutBodyTicks = RoundToTicks(_orLow - bodyLow)
                };
            }
        }

        private void CheckContinuationAndDraw(int confirmationBar, dynamic nextCandle)
        {
            if (_pendingBreakout == null)
                return;

            decimal continuationTicks;

            if (_pendingBreakout.Side == "BUY")
                continuationTicks = RoundToTicks(nextCandle.High - _pendingBreakout.EntryPrice);
            else
                continuationTicks = RoundToTicks(_pendingBreakout.EntryPrice - nextCandle.Low);

            if (continuationTicks < MinContinuationTicks)
                return;

            var trade = BuildTradeLevels(_pendingBreakout);
            DrawTrade(trade, confirmationBar, continuationTicks, "CONF");
            _tradeDrawn = true;
        }

        private TradeLevels BuildTradeLevels(PendingBreakout breakout)
        {
            decimal tradeTicks;

            if (breakout.Side == "BUY")
                tradeTicks = ClampTicks(RoundToTicks(breakout.EntryPrice - _orLow));
            else
                tradeTicks = ClampTicks(RoundToTicks(_orHigh - breakout.EntryPrice));

            decimal tradePoints = tradeTicks * SetupTickSize;

            decimal sl = breakout.Side == "BUY"
                ? breakout.EntryPrice - tradePoints
                : breakout.EntryPrice + tradePoints;

            decimal tp = breakout.Side == "BUY"
                ? breakout.EntryPrice + tradePoints
                : breakout.EntryPrice - tradePoints;

            return new TradeLevels
            {
                Bar = breakout.Bar,
                Time = breakout.Time,
                Side = breakout.Side,
                EntryPrice = breakout.EntryPrice,
                StopLossPrice = sl,
                TakeProfitPrice = tp,
                TradeTicks = tradeTicks,
                BreakoutBodyTicks = breakout.BreakoutBodyTicks
            };
        }

        private decimal RoundToTicks(decimal points)
        {
            return Math.Round(points / SetupTickSize, 2);
        }

        private decimal ClampTicks(decimal ticks)
        {
            if (ticks < MinTradeTicks)
                return MinTradeTicks;
            if (ticks > MaxTradeTicks)
                return MaxTradeTicks;
            return ticks;
        }

        private void DrawOpeningRange(dynamic candle)
        {
            var pen = new Pen(Color.Red, 1);
            int endBar = _orBar + LineLength;

            TrendLines.Add(new TrendLine(_orBar, _orHigh, endBar, _orHigh, pen));
            TrendLines.Add(new TrendLine(_orBar, _orLow, endBar, _orLow, pen));

            decimal rangeTicks = RoundToTicks(_orHigh - _orLow);

            AddText(
                $"EW_OR_{candle.Time:yyyyMMdd}",
                $"OR {rangeTicks:0}t",
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
                true
            );
        }

        private void DrawTrade(TradeLevels trade, int confirmationBar, decimal continuationTicks, string signalSource)
        {
            if (!ShowEntrySlTp)
                return;

            int endBar = trade.Bar + LineLength;

            TrendLines.Add(new TrendLine(
                trade.Bar,
                trade.EntryPrice,
                endBar,
                trade.EntryPrice,
                new Pen(Color.Gold, 3)
            ));

            TrendLines.Add(new TrendLine(
                trade.Bar,
                trade.StopLossPrice,
                endBar,
                trade.StopLossPrice,
                new Pen(Color.Red, 3)
            ));

            TrendLines.Add(new TrendLine(
                trade.Bar,
                trade.TakeProfitPrice,
                endBar,
                trade.TakeProfitPrice,
                new Pen(Color.LimeGreen, 3)
            ));

            DrawTradeLabel(
                $"EW_ENTRY_{trade.Time:yyyyMMdd_HHmm}",
                $"{trade.Side} ENTRY {trade.EntryPrice:0.00}",
                trade.Bar,
                trade.EntryPrice,
                Color.Black,
                Color.Gold
            );

            DrawTradeLabel(
                $"EW_SL_{trade.Time:yyyyMMdd_HHmm}",
                $"SL {trade.StopLossPrice:0.00} | {trade.TradeTicks:0}t",
                trade.Bar,
                trade.StopLossPrice,
                Color.White,
                Color.Red
            );

            DrawTradeLabel(
                $"EW_TP_{trade.Time:yyyyMMdd_HHmm}",
                $"TP {trade.TakeProfitPrice:0.00} | {trade.TradeTicks:0}t",
                trade.Bar,
                trade.TakeProfitPrice,
                Color.White,
                Color.Green
            );

            AddText(
                $"EW_CONFIRM_{trade.Time:yyyyMMdd_HHmm}",
                signalSource == "SCORE"
                    ? $"SCORE ENTRY | BODY {trade.BreakoutBodyTicks:0}t"
                    : $"CONF +{continuationTicks:0}t | BODY {trade.BreakoutBodyTicks:0}t",
                true,
                confirmationBar,
                trade.Side == "BUY" ? trade.TakeProfitPrice : trade.StopLossPrice,
                trade.Side == "BUY" ? -35 : 35,
                0,
                Color.White,
                Color.Purple,
                Color.Purple,
                12,
                DrawingText.TextAlign.Center,
                true
            );
        }

        private void DrawTradeLabel(
            string id,
            string text,
            int bar,
            decimal price,
            Color textColor,
            Color bgColor)
        {
            AddText(
                id,
                text,
                true,
                bar,
                price,
                -18,
                0,
                textColor,
                bgColor,
                bgColor,
                12,
                DrawingText.TextAlign.Center,
                true
            );
        }

        private class PendingBreakout
        {
            public int Bar { get; set; }
            public DateTime Time { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public decimal BreakoutBodyTicks { get; set; }
        }

        private class TradeLevels
        {
            public int Bar { get; set; }
            public DateTime Time { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public decimal StopLossPrice { get; set; }
            public decimal TakeProfitPrice { get; set; }
            public decimal TradeTicks { get; set; }
            public decimal BreakoutBodyTicks { get; set; }
        }

        private class ScoreState
        {
            public bool IsBreakout { get; set; }
            public bool IsReady { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public decimal OrRangeTicks { get; set; }
            public decimal BodyBreakoutTicks { get; set; }
            public bool RangeOk { get; set; }
            public bool BodyOk { get; set; }
            public bool VolumeOk { get; set; }
            public bool DeltaOk { get; set; }
            public bool TimeOk { get; set; }
            public bool VwapOk { get; set; }
            public int Score { get; set; }
        }
    }
}
