using System;
using System.ComponentModel;
using System.Drawing;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    public class EddiewareOpeningRangeSetup : Indicator
    {
        private DateTime _currentDate = DateTime.MinValue;

        private decimal _orHigh;
        private decimal _orLow;

        private bool _rangeDrawn;
        private bool _orLabelDrawn;

        private int _orBar = -1;

        private string _breakoutSide = "";
        private decimal _bestBreakoutTicks = 0;
        private int _breakoutLabelBar = -1;
        private string _lastBreakoutClassification = "";

        private const decimal TickSize = 0.25m;

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Line Length (bars)")]
        public int LineLength { get; set; } = 100;

        [DisplayName("Breakout Scan Bars")]
        public int BreakoutScanBars { get; set; } = 30;

        [DisplayName("B+ Min Ticks")]
        public decimal BPlusMinTicks { get; set; } = 20;

        [DisplayName("A+ Min Ticks")]
        public decimal APlusMinTicks { get; set; } = 35;

        [DisplayName("Extreme Min Ticks")]
        public decimal ExtremeMinTicks { get; set; } = 60;

        public EddiewareOpeningRangeSetup()
        {
            DrawAbovePrice = true;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            var candle = GetCandle(bar);
            var time = candle.Time;

            if (time.Date != _currentDate)
            {
                _currentDate = time.Date;

                _rangeDrawn = false;
                _orLabelDrawn = false;

                _orBar = -1;

                _breakoutSide = "";
                _bestBreakoutTicks = 0;
                _breakoutLabelBar = -1;
                _lastBreakoutClassification = "";
            }

            var prev = GetCandle(bar - 1);

            bool is930Closed =
                prev.Time.TimeOfDay.Hours == OpeningTimeUtc.Hours &&
                prev.Time.TimeOfDay.Minutes == OpeningTimeUtc.Minutes;

            if (!_rangeDrawn && is930Closed)
            {
                _orHigh = prev.High;
                _orLow = prev.Low;

                _orBar = bar - 1;

                DrawOR(time);

                _rangeDrawn = true;
            }

            if (_rangeDrawn)
                CheckBreakoutOnClosedBar(bar - 1);
        }

        private void DrawOR(DateTime time)
        {
            int startBar = _orBar;
            int endBar = _orBar + LineLength;

            var pen = new Pen(Color.Red, 1);

            TrendLines.Add(new TrendLine(startBar, _orHigh, endBar, _orHigh, pen));
            TrendLines.Add(new TrendLine(startBar, _orLow, endBar, _orLow, pen));

            DrawRangeLabel(time);
        }

        private void DrawRangeLabel(DateTime time)
        {
            if (_orLabelDrawn)
                return;

            _orLabelDrawn = true;

            decimal rangeTicks = (_orHigh - _orLow) / TickSize;

            string classification =
                rangeTicks <= 100 ? "A+" :
                rangeTicks <= 210 ? "B FUERTE" :
                "NO TRADE";

            string label = $"{classification} | OR {rangeTicks:0} ticks";

            AddText(
                $"OR_LABEL_{time:yyyyMMdd}",
                label,
                true,
                _orBar,
                _orHigh,
                -35,
                0,
                Color.White,
                Color.Black,
                Color.Black,
                18,
                DrawingText.TextAlign.Center,
                true
            );
        }

        private void CheckBreakoutOnClosedBar(int closedBar)
        {
            if (_orBar < 0 || closedBar <= _orBar)
                return;

            int barsAfterOR = closedBar - _orBar;

            if (barsAfterOR > BreakoutScanBars)
                return;

            var candle = GetCandle(closedBar);

            bool closeAboveOR = candle.Close > _orHigh;
            bool closeBelowOR = candle.Close < _orLow;

            if (!closeAboveOR && !closeBelowOR)
                return;

            string side = closeAboveOR ? "BUY" : "SELL";

            if (_breakoutSide != "" && side != _breakoutSide)
                return;

            decimal breakoutTicks = side == "BUY"
                ? (candle.High - _orHigh) / TickSize
                : (_orLow - candle.Low) / TickSize;

            if (breakoutTicks < BPlusMinTicks)
                return;

            if (_breakoutSide == "")
                _breakoutSide = side;

            if (breakoutTicks <= _bestBreakoutTicks)
                return;

            _bestBreakoutTicks = breakoutTicks;
            _breakoutLabelBar = closedBar;

            string classification =
                breakoutTicks >= ExtremeMinTicks ? "A+ EXTREMO" :
                breakoutTicks >= APlusMinTicks ? "A+" :
                "B+";

            if (classification == _lastBreakoutClassification && breakoutTicks < ExtremeMinTicks)
                return;

            _lastBreakoutClassification = classification;

            decimal candleRange = candle.High - candle.Low;
            decimal body = Math.Abs(candle.Close - candle.Open);
            decimal bodyPercent = candleRange > 0 ? body / candleRange * 100m : 0;

            string label =
                $"{side} {classification} | BO {breakoutTicks:0} ticks | Body {bodyPercent:0}%";

            Color bgColor =
                classification.Contains("EXTREMO") ? Color.OrangeRed :
                classification.Contains("A+") ? Color.Purple :
                Color.Goldenrod;

            decimal textPrice = side == "BUY" ? candle.High : candle.Low;
            int verticalOffset = side == "BUY" ? -45 : 45;

            AddText(
                $"BREAKOUT_LABEL_{candle.Time:yyyyMMdd}",
                label,
                true,
                _breakoutLabelBar,
                textPrice,
                verticalOffset,
                0,
                Color.White,
                bgColor,
                bgColor,
                16,
                DrawingText.TextAlign.Center,
                true
            );
        }
    }
}