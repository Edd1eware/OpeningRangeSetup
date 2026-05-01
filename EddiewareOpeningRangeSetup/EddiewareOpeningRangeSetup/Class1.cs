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
        private bool _smallBodyLabelDrawn;
        private bool _sellTwoContractsLineDrawn;
        private bool _buyTwoContractsLineDrawn;
        private bool _sellOneContractLineDrawn;
        private bool _buyOneContractLineDrawn;

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

        [DisplayName("Min Body Quality %")]
        public decimal MinBodyQualityPercent { get; set; } = 50;

        [DisplayName("Min OR Body Quality %")]
        public decimal MinORBodyQualityPercent { get; set; } = 50;

        [DisplayName("Label Offset Bars Left")]
        public int LabelOffsetBarsLeft { get; set; } = 2;

        [DisplayName("2 Contracts Distance Ticks")]
        public decimal TwoContractsDistanceTicks { get; set; } = 60;

        [DisplayName("1 Contract Distance Ticks")]
        public decimal OneContractDistanceTicks { get; set; } = 120;

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
                _smallBodyLabelDrawn = false;
                _sellTwoContractsLineDrawn = false;
                _buyTwoContractsLineDrawn = false;
                _sellOneContractLineDrawn = false;
                _buyOneContractLineDrawn = false;

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

                DrawOR(time, prev);

                _rangeDrawn = true;
            }

            if (_rangeDrawn)
                CheckBreakoutOnClosedBar(bar - 1);
        }

        private void DrawOR(DateTime time, dynamic orCandle)
        {
            int startBar = _orBar;
            int endBar = _orBar + LineLength;

            var pen = new Pen(Color.Red, 1);

            TrendLines.Add(new TrendLine(startBar, _orHigh, endBar, _orHigh, pen));
            TrendLines.Add(new TrendLine(startBar, _orLow, endBar, _orLow, pen));

            DrawRangeLabel(time);
            DrawSmallBodyLabel(time, orCandle);
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

        private void DrawSmallBodyLabel(DateTime time, dynamic orCandle)
        {
            if (_smallBodyLabelDrawn)
                return;

            decimal candleRange = orCandle.High - orCandle.Low;

            if (candleRange <= 0)
                return;

            decimal body = Math.Abs(orCandle.Close - orCandle.Open);
            decimal bodyPercent = body / candleRange * 100m;

            if (bodyPercent >= MinORBodyQualityPercent)
                return;

            _smallBodyLabelDrawn = true;

            string label = $"SMALL BODY | Body {bodyPercent:0}%";

            AddText(
                $"SMALL_BODY_LABEL_{time:yyyyMMdd}",
                label,
                true,
                _orBar,
                _orHigh,
                -60,
                0,
                Color.White,
                Color.DarkRed,
                Color.DarkRed,
                16,
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

            decimal candleRange = candle.High - candle.Low;

            if (candleRange <= 0)
                return;

            decimal body = Math.Abs(candle.Close - candle.Open);
            decimal bodyPercent = body / candleRange * 100m;

            if (bodyPercent < MinBodyQualityPercent)
                return;

            if (_breakoutSide == "")
                _breakoutSide = side;

            if (breakoutTicks <= _bestBreakoutTicks)
                return;

            _bestBreakoutTicks = breakoutTicks;

            if (_breakoutLabelBar < 0)
                _breakoutLabelBar = closedBar;

            string classification =
                breakoutTicks >= ExtremeMinTicks ? "A+ EXTREMO" :
                breakoutTicks >= APlusMinTicks ? "A+" :
                "B+";

            if (classification == _lastBreakoutClassification && breakoutTicks < ExtremeMinTicks)
                return;

            _lastBreakoutClassification = classification;

            string label =
                $"{side} {classification} | BO {breakoutTicks:0} ticks | Body {bodyPercent:0}%";

            Color bgColor =
                classification.Contains("EXTREMO") ? Color.OrangeRed :
                classification.Contains("A+") ? Color.Purple :
                Color.Goldenrod;

            decimal textPrice = side == "BUY" ? candle.High : candle.Low;
            int verticalOffset = side == "BUY" ? -45 : 45;

            int labelBar = Math.Max(0, _breakoutLabelBar - LabelOffsetBarsLeft);

            AddText(
                $"BREAKOUT_LABEL_{candle.Time:yyyyMMdd}",
                label,
                true,
                labelBar,
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

            if (side == "SELL")
            {
                DrawSellTwoContractsLine(candle, closedBar);
                DrawSellOneContractLine(candle, closedBar);
            }

            if (side == "BUY")
            {
                DrawBuyTwoContractsLine(candle, closedBar);
                DrawBuyOneContractLine(candle, closedBar);
            }
        }

        private void DrawSellTwoContractsLine(dynamic candle, int closedBar)
        {
            if (_sellTwoContractsLineDrawn)
                return;

            _sellTwoContractsLineDrawn = true;

            decimal targetPrice = candle.Close + (TwoContractsDistanceTicks * TickSize);

            var pen = new Pen(Color.LimeGreen, 2);
            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddText($"SELL_2_CONTRACTS_LABEL_{candle.Time:yyyyMMdd}", "2 contratos", true,
                closedBar, targetPrice, -25, 0,
                Color.White, Color.Green, Color.Green, 16,
                DrawingText.TextAlign.Center, true);
        }

        private void DrawSellOneContractLine(dynamic candle, int closedBar)
        {
            if (_sellOneContractLineDrawn)
                return;

            _sellOneContractLineDrawn = true;

            decimal targetPrice = candle.Close + (OneContractDistanceTicks * TickSize);

            var pen = new Pen(Color.Yellow, 2);
            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddText($"SELL_1_CONTRACT_LABEL_{candle.Time:yyyyMMdd}", "1 contrato", true,
                closedBar, targetPrice, -25, 0,
                Color.Black, Color.Yellow, Color.Yellow, 16,
                DrawingText.TextAlign.Center, true);
        }

        private void DrawBuyTwoContractsLine(dynamic candle, int closedBar)
        {
            if (_buyTwoContractsLineDrawn)
                return;

            _buyTwoContractsLineDrawn = true;

            decimal targetPrice = candle.Close - (TwoContractsDistanceTicks * TickSize);

            var pen = new Pen(Color.DodgerBlue, 2);
            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddText($"BUY_2_CONTRACTS_LABEL_{candle.Time:yyyyMMdd}", "2 contratos", true,
                closedBar, targetPrice, 25, 0,
                Color.White, Color.Blue, Color.Blue, 16,
                DrawingText.TextAlign.Center, true);
        }

        private void DrawBuyOneContractLine(dynamic candle, int closedBar)
        {
            if (_buyOneContractLineDrawn)
                return;

            _buyOneContractLineDrawn = true;

            decimal targetPrice = candle.Close - (OneContractDistanceTicks * TickSize);

            var pen = new Pen(Color.Yellow, 2);
            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddText($"BUY_1_CONTRACT_LABEL_{candle.Time:yyyyMMdd}", "1 contrato", true,
                closedBar, targetPrice, 25, 0,
                Color.Black, Color.Yellow, Color.Yellow, 16,
                DrawingText.TextAlign.Center, true);
        }
    }
}