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

            if (!_orReady || _tradeDrawn || closedBar <= _orBar)
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
            DrawTrade(trade, confirmationBar, continuationTicks);
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

        private void DrawTrade(TradeLevels trade, int confirmationBar, decimal continuationTicks)
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
                $"CONF +{continuationTicks:0}t | BODY {trade.BreakoutBodyTicks:0}t",
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
    }
}
