using System;
using System.Collections.Generic;
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
        private bool _breakoutLabelDrawn;
        private bool _fakeNoTradeLabelDrawn;
        private bool _buyImbalanceLineDrawn;

        private bool _sellTwoContractsLineDrawn;
        private bool _buyTwoContractsLineDrawn;
        private bool _sellOneContractLineDrawn;
        private bool _buyOneContractLineDrawn;

        private bool _isNoTradeNoiseOR;
        private bool _isFakeBreakoutOR;
        private bool _fakeInitialOutsideDetected;
        private bool _waitingForFakeReentry;
        private bool _fakeBreakoutReentered;
        private bool _isFakeNoTradeOR;

        private int _orBar = -1;
        private string _breakoutSide = "";

        private const decimal TickSize = 0.25m;

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Line Length (bars)")]
        public int LineLength { get; set; } = 100;

        [DisplayName("Breakout Scan Bars")]
        public int BreakoutScanBars { get; set; } = 30;

        [DisplayName("Max Fake Initial Breakout Bars")]
        public int MaxFakeInitialBreakoutBars { get; set; } = 3;

        [DisplayName("Min Fake Initial Breakout Ticks")]
        public decimal MinFakeInitialBreakoutTicks { get; set; } = 40;

        [DisplayName("Min OR Body Quality %")]
        public decimal MinORBodyQualityPercent { get; set; } = 50;

        [DisplayName("Min Body Outside OR Ticks")]
        public decimal MinBodyOutsideORTicks { get; set; } = 35;

        [DisplayName("Label Offset Bars Left")]
        public int LabelOffsetBarsLeft { get; set; } = 2;

        [DisplayName("2 Contracts Distance Ticks")]
        public decimal TwoContractsDistanceTicks { get; set; } = 60;

        [DisplayName("1 Contract Distance Ticks")]
        public decimal OneContractDistanceTicks { get; set; } = 120;

        [DisplayName("Imbalance Ratio")]
        public decimal ImbalanceRatio { get; set; } = 3;

        [DisplayName("Imbalance Volume Filter")]
        public decimal ImbalanceVolumeFilter { get; set; } = 50;

        [DisplayName("Imbalance Line Length")]
        public int ImbalanceLineLength { get; set; } = 10;

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
                _breakoutLabelDrawn = false;
                _fakeNoTradeLabelDrawn = false;
                _buyImbalanceLineDrawn = false;

                _sellTwoContractsLineDrawn = false;
                _buyTwoContractsLineDrawn = false;
                _sellOneContractLineDrawn = false;
                _buyOneContractLineDrawn = false;

                _isNoTradeNoiseOR = false;
                _isFakeBreakoutOR = false;
                _fakeInitialOutsideDetected = false;
                _waitingForFakeReentry = false;
                _fakeBreakoutReentered = false;
                _isFakeNoTradeOR = false;

                _orBar = -1;
                _breakoutSide = "";
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

            DrawSmallBodyLabel(time, orCandle);
            DrawRangeLabel(time);
        }

        private void DrawRangeLabel(DateTime time)
        {
            if (_orLabelDrawn)
                return;

            _orLabelDrawn = true;

            decimal rangeTicks = (_orHigh - _orLow) / TickSize;

            string classification =
                _isNoTradeNoiseOR ? "NO TRADE" :
                rangeTicks <= 100 ? "A+" :
                rangeTicks <= 210 ? "B FUERTE" :
                "NO TRADE";

            string label = $"{classification} | OR {rangeTicks:0}t";

            Color bgColor =
                classification == "NO TRADE" ? Color.Red : Color.DarkGreen;

            AddText(
                $"OR_LABEL_{time:yyyyMMdd}",
                label,
                true,
                _orBar,
                _orHigh,
                -35,
                0,
                Color.White,
                bgColor,
                bgColor,
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
            decimal bodyTicks = body / TickSize;
            decimal bodyPercent = body / candleRange * 100m;

            if (bodyPercent >= MinORBodyQualityPercent)
                return;

            _smallBodyLabelDrawn = true;

            string label;

            if (bodyTicks <= 7m)
            {
                label = $"NO TRADE NOISE | {bodyTicks:0}t";
                _isNoTradeNoiseOR = true;
            }
            else if (bodyTicks <= 14m)
            {
                label = $"FAKE BREAKOUT | {bodyTicks:0}t";
                _isFakeBreakoutOR = true;
                _fakeInitialOutsideDetected = false;
                _waitingForFakeReentry = false;
                _fakeBreakoutReentered = false;
            }
            else
            {
                label = $"SMALL BODY | {bodyTicks:0}t";
            }

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
            if (_breakoutLabelDrawn)
                return;

            if (_isNoTradeNoiseOR || _isFakeNoTradeOR)
                return;

            if (_orBar < 0 || closedBar <= _orBar)
                return;

            int barsAfterOR = closedBar - _orBar;

            if (barsAfterOR > BreakoutScanBars)
                return;

            var candle = GetCandle(closedBar);

            if (_isFakeBreakoutOR && !_fakeBreakoutReentered)
            {
                bool closeAboveOR = candle.Close > _orHigh;
                bool closeBelowOR = candle.Close < _orLow;

                if (!_fakeInitialOutsideDetected)
                {
                    bool validFakeInitialBreakout = false;

                    if (barsAfterOR <= MaxFakeInitialBreakoutBars && (closeAboveOR || closeBelowOR))
                    {
                        string fakeSide = closeAboveOR ? "BUY" : "SELL";
                        decimal fakeBodyOutsideTicks = CalculateBodyOutsideORTicks(candle, fakeSide);

                        if (fakeBodyOutsideTicks >= MinFakeInitialBreakoutTicks)
                            validFakeInitialBreakout = true;
                    }

                    if (validFakeInitialBreakout)
                    {
                        _fakeInitialOutsideDetected = true;
                        _waitingForFakeReentry = true;
                        return;
                    }

                    if (barsAfterOR >= MaxFakeInitialBreakoutBars)
                    {
                        _isFakeNoTradeOR = true;
                        DrawFakeNoTradeLabel(candle, closedBar);
                        return;
                    }

                    return;
                }

                if (_waitingForFakeReentry)
                {
                    bool closedBackInsideOR =
                        candle.Close <= _orHigh &&
                        candle.Close >= _orLow;

                    if (!closedBackInsideOR)
                        return;

                    _fakeBreakoutReentered = true;
                    _waitingForFakeReentry = false;

                    return;
                }
            }

            bool breakoutCloseAboveOR = candle.Close > _orHigh;
            bool breakoutCloseBelowOR = candle.Close < _orLow;

            if (!breakoutCloseAboveOR && !breakoutCloseBelowOR)
                return;

            string side = breakoutCloseAboveOR ? "BUY" : "SELL";

            if (_breakoutSide != "" && side != _breakoutSide)
                return;

            decimal realBodyOutsideTicks = CalculateBodyOutsideORTicks(candle, side);

            if (realBodyOutsideTicks < MinBodyOutsideORTicks)
                return;

            decimal imbalancePrice = 0;
            decimal imbalanceAsk = 0;
            decimal imbalanceBid = 0;

            if (side == "BUY")
            {
                bool hasValidImbalance = TryGetLowestBuyImbalance(
                    candle,
                    out imbalancePrice,
                    out imbalanceAsk,
                    out imbalanceBid
                );

                if (!hasValidImbalance)
                    return;

                DrawOrangeImbalanceLine(closedBar, imbalancePrice, imbalanceAsk, imbalanceBid);
                _buyImbalanceLineDrawn = true;
            }

            _breakoutSide = side;
            _breakoutLabelDrawn = true;

            string label = $"{side} A+ TRADE | {realBodyOutsideTicks:0}t";

            decimal textPrice = side == "BUY" ? candle.High : candle.Low;
            int verticalOffset = side == "BUY" ? -45 : 45;

            // MEJORA: el label se pinta sobre la vela del imbalance / breakout válido.
            int labelBar = closedBar;

            AddText(
                $"BREAKOUT_LABEL_{candle.Time:yyyyMMdd}",
                label,
                true,
                labelBar,
                textPrice,
                verticalOffset,
                0,
                Color.White,
                Color.Green,
                Color.Green,
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

        private bool TryGetLowestBuyImbalance(dynamic candle, out decimal selectedPrice, out decimal selectedAsk, out decimal selectedBid)
        {
            selectedPrice = 0;
            selectedAsk = 0;
            selectedBid = 0;

            try
            {
                var levels = new List<ClusterLevel>();

                foreach (var lvl in candle.GetAllPriceLevels())
                {
                    levels.Add(new ClusterLevel
                    {
                        Price = Convert.ToDecimal(lvl.Price),
                        Bid = Convert.ToDecimal(lvl.Bid),
                        Ask = Convert.ToDecimal(lvl.Ask)
                    });
                }

                levels.Sort((a, b) => a.Price.CompareTo(b.Price));

                if (levels.Count < 2)
                    return false;

                bool found = false;

                for (int i = 1; i < levels.Count; i++)
                {
                    var current = levels[i];
                    var lower = levels[i - 1];

                    if (lower.Bid <= 0)
                        continue;

                    bool isBuyImbalance =
                        current.Ask >= ImbalanceVolumeFilter &&
                        current.Ask >= lower.Bid * ImbalanceRatio;

                    if (!isBuyImbalance)
                        continue;

                    if (!found || current.Price < selectedPrice)
                    {
                        found = true;
                        selectedPrice = current.Price;
                        selectedAsk = current.Ask;
                        selectedBid = lower.Bid;
                    }
                }

                return found;
            }
            catch
            {
                return false;
            }
        }

        private void DrawOrangeImbalanceLine(int bar, decimal price, decimal ask, decimal bid)
        {
            if (_buyImbalanceLineDrawn)
                return;

            var pen = new Pen(Color.Orange, 5);

            TrendLines.Add(
                new TrendLine(
                    bar,
                    price,
                    bar + ImbalanceLineLength,
                    price,
                    pen
                )
            );

            AddText(
                $"BUY_IMB_BREAKOUT_{bar}_{price}",
                $"{ask:0}/{bid:0}",
                true,
                bar + 1,
                price,
                -15,
                0,
                Color.Black,
                Color.Orange,
                Color.Orange,
                12,
                DrawingText.TextAlign.Center,
                true
            );
        }

        private class ClusterLevel
        {
            public decimal Price { get; set; }
            public decimal Bid { get; set; }
            public decimal Ask { get; set; }
        }

        private void DrawFakeNoTradeLabel(dynamic candle, int closedBar)
        {
            if (_fakeNoTradeLabelDrawn)
                return;

            _fakeNoTradeLabelDrawn = true;

            AddText(
                $"FAKE_NO_TRADE_LABEL_{candle.Time:yyyyMMdd}",
                $"NO TRADE | NO 40t IN {MaxFakeInitialBreakoutBars} BARS",
                true,
                closedBar,
                _orHigh,
                -85,
                0,
                Color.White,
                Color.Red,
                Color.Red,
                16,
                DrawingText.TextAlign.Center,
                true
            );
        }

        private decimal CalculateBodyOutsideORTicks(dynamic candle, string side)
        {
            decimal bodyHigh = Math.Max(candle.Open, candle.Close);
            decimal bodyLow = Math.Min(candle.Open, candle.Close);

            decimal bodyOutside = 0;

            if (side == "BUY")
                bodyOutside = bodyHigh - Math.Max(bodyLow, _orHigh);

            if (side == "SELL")
                bodyOutside = Math.Min(bodyHigh, _orLow) - bodyLow;

            if (bodyOutside < 0)
                bodyOutside = 0;

            return bodyOutside / TickSize;
        }

        private void DrawSellTwoContractsLine(dynamic candle, int closedBar)
        {
            if (_sellTwoContractsLineDrawn)
                return;

            _sellTwoContractsLineDrawn = true;

            decimal targetPrice = candle.Close + (TwoContractsDistanceTicks * TickSize);
            var pen = new Pen(Color.LimeGreen, 2);

            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddContractsLabel(
                $"SELL_TWO_CONTRACTS_LABEL_{candle.Time:yyyyMMdd}",
                "2 contratos",
                closedBar,
                targetPrice,
                Color.White,
                Color.LimeGreen
            );
        }

        private void DrawSellOneContractLine(dynamic candle, int closedBar)
        {
            if (_sellOneContractLineDrawn)
                return;

            _sellOneContractLineDrawn = true;

            decimal targetPrice = candle.Close + (OneContractDistanceTicks * TickSize);
            var pen = new Pen(Color.Yellow, 2);

            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddContractsLabel(
                $"SELL_ONE_CONTRACT_LABEL_{candle.Time:yyyyMMdd}",
                "1 contrato",
                closedBar,
                targetPrice,
                Color.Black,
                Color.Yellow
            );
        }

        private void DrawBuyTwoContractsLine(dynamic candle, int closedBar)
        {
            if (_buyTwoContractsLineDrawn)
                return;

            _buyTwoContractsLineDrawn = true;

            decimal targetPrice = candle.Close - (TwoContractsDistanceTicks * TickSize);
            var pen = new Pen(Color.DodgerBlue, 2);

            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddContractsLabel(
                $"BUY_TWO_CONTRACTS_LABEL_{candle.Time:yyyyMMdd}",
                "2 contratos",
                closedBar,
                targetPrice,
                Color.White,
                Color.DodgerBlue
            );
        }

        private void DrawBuyOneContractLine(dynamic candle, int closedBar)
        {
            if (_buyOneContractLineDrawn)
                return;

            _buyOneContractLineDrawn = true;

            decimal targetPrice = candle.Close - (OneContractDistanceTicks * TickSize);
            var pen = new Pen(Color.Yellow, 2);

            TrendLines.Add(new TrendLine(closedBar, targetPrice, closedBar + LineLength, targetPrice, pen));

            AddContractsLabel(
                $"BUY_ONE_CONTRACT_LABEL_{candle.Time:yyyyMMdd}",
                "1 contrato",
                closedBar,
                targetPrice,
                Color.Black,
                Color.Yellow
            );
        }

        private void AddContractsLabel(string id, string text, int bar, decimal price, Color textColor, Color bgColor)
        {
            AddText(
                id,
                text,
                true,
                bar,
                price,
                -20,
                0,
                textColor,
                bgColor,
                bgColor,
                14,
                DrawingText.TextAlign.Center,
                true
            );
        }
    }
}