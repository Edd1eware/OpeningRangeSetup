using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.Linq;
using System.Reflection;
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
        private bool _validImbalancesDrawn;

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

        [DisplayName("Imbalance Ratio")]
        public decimal ImbalanceRatio { get; set; } = 3m;

        [DisplayName("Imbalance Min Volume")]
        public decimal ImbalanceMinVolume { get; set; } = 40m;

        [DisplayName("Valid Imbalance Line Length Bars")]
        public int ValidImbalanceLineLengthBars { get; set; } = 20;

        [DisplayName("Show Valid Imbalance Labels")]
        public bool ShowValidImbalanceLabels { get; set; } = true;

        [DisplayName("Show Debug If No Valid Imbalance")]
        public bool ShowDebugIfNoValidImbalance { get; set; } = true;

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
                _validImbalancesDrawn = false;

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
            var pen = new Pen(Color.Red, 1);

            TrendLines.Add(new TrendLine(_orBar, _orHigh, _orBar + LineLength, _orHigh, pen));
            TrendLines.Add(new TrendLine(_orBar, _orLow, _orBar + LineLength, _orLow, pen));

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

            AddText(
                $"OR_LABEL_{time:yyyyMMdd}",
                $"{classification} | OR {rangeTicks:0} ticks",
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

            AddText(
                $"SMALL_BODY_LABEL_{time:yyyyMMdd}",
                $"SMALL BODY | Body {bodyPercent:0}%",
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

            Color bgColor =
                classification.Contains("EXTREMO") ? Color.OrangeRed :
                classification.Contains("A+") ? Color.Purple :
                Color.Goldenrod;

            decimal textPrice = side == "BUY" ? candle.High : candle.Low;
            int verticalOffset = side == "BUY" ? -45 : 45;

            int labelBar = Math.Max(0, _breakoutLabelBar - LabelOffsetBarsLeft);

            AddText(
                $"BREAKOUT_LABEL_{candle.Time:yyyyMMdd}",
                $"{side} {classification} | BO {breakoutTicks:0} ticks | Body {bodyPercent:0}%",
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

            DrawValidUntouchedImbalances(closedBar, side, candle.Close);
        }

        private void DrawValidUntouchedImbalances(int breakoutBar, string side, decimal breakoutClose)
        {
            if (_validImbalancesDrawn)
                return;

            _validImbalancesDrawn = true;

            var candidates = new List<ValidImbalanceCandidate>();

            int totalLevelsRead = 0;
            int barsWithLevels = 0;
            int totalValidImbalances = 0;
            int totalTouched = 0;

            for (int scanBar = breakoutBar; scanBar >= _orBar; scanBar--)
            {
                var levels = GetPriceLevelsSafe(scanBar);

                if (levels.Count > 0)
                {
                    totalLevelsRead += levels.Count;
                    barsWithLevels++;
                }

                foreach (var level in levels)
                {
                    bool isValid = side == "BUY"
                        ? IsBuyImbalance(level, levels)
                        : IsSellImbalance(level, levels);

                    if (!isValid)
                        continue;

                    totalValidImbalances++;

                    decimal distanceTicks = side == "BUY"
                        ? (breakoutClose - level.Price) / TickSize
                        : (level.Price - breakoutClose) / TickSize;

                    if (distanceTicks <= 0)
                        continue;

                    bool touched = WasTouchedAfterCreation(scanBar, breakoutBar, side, level.Price);

                    if (touched)
                    {
                        totalTouched++;
                        continue;
                    }

                    candidates.Add(new ValidImbalanceCandidate
                    {
                        Bar = scanBar,
                        Price = level.Price,
                        Bid = level.Bid,
                        Ask = level.Ask,
                        DistanceTicks = distanceTicks
                    });
                }
            }

            if (candidates.Count == 0)
            {
                if (ShowDebugIfNoValidImbalance)
                {
                    string debugText;

                    if (totalLevelsRead == 0)
                        debugText = "VALID IMB: NO LEYÓ NIVELES BID/ASK";
                    else if (totalValidImbalances == 0)
                        debugText = $"VALID IMB: LEYÓ {totalLevelsRead} NIVELES, SIN IMBALANCES";
                    else
                        debugText = $"VALID IMB: {totalValidImbalances} IMB, {totalTouched} TOCADOS, 0 NO TOCADOS";

                    AddText(
                        $"VALID_IMB_NONE_{_currentDate:yyyyMMdd}",
                        debugText,
                        true,
                        breakoutBar,
                        breakoutClose,
                        side == "BUY" ? 35 : -35,
                        0,
                        Color.White,
                        Color.DarkOrange,
                        Color.DarkOrange,
                        14,
                        DrawingText.TextAlign.Center,
                        true
                    );
                }

                return;
            }

            var ordered = candidates
                .OrderBy(x => x.DistanceTicks)
                .ThenByDescending(x => x.Bar)
                .ToList();

            int counter = 0;

            foreach (var imb in ordered)
            {
                Color lineColor = side == "BUY" ? Color.DeepSkyBlue : Color.Magenta;

                TrendLines.Add(new TrendLine(
                    imb.Bar,
                    imb.Price,
                    imb.Bar + ValidImbalanceLineLengthBars,
                    imb.Price,
                    new Pen(lineColor, 3)
                ));

                if (ShowValidImbalanceLabels)
                {
                    AddText(
                        $"VALID_IMB_{_currentDate:yyyyMMdd}_{counter}",
                        $"{side} VALID IMB | {imb.Price:0.00} | {imb.DistanceTicks:0}t | B{imb.Bid:0}/A{imb.Ask:0} | OK",
                        true,
                        imb.Bar,
                        imb.Price,
                        side == "BUY" ? 25 : -25,
                        0,
                        Color.White,
                        lineColor,
                        lineColor,
                        11,
                        DrawingText.TextAlign.Left,
                        true
                    );
                }

                counter++;
            }
        }

        private bool IsBuyImbalance(PriceLevelData level, List<PriceLevelData> levels)
        {
            if (level.Ask < ImbalanceMinVolume)
                return false;

            var opposite = levels.FirstOrDefault(x => x.Price == level.Price - TickSize);
            decimal oppositeBid = opposite == null ? 0 : opposite.Bid;

            if (oppositeBid <= 0)
                return true;

            return level.Ask >= oppositeBid * ImbalanceRatio;
        }

        private bool IsSellImbalance(PriceLevelData level, List<PriceLevelData> levels)
        {
            if (level.Bid < ImbalanceMinVolume)
                return false;

            var opposite = levels.FirstOrDefault(x => x.Price == level.Price + TickSize);
            decimal oppositeAsk = opposite == null ? 0 : opposite.Ask;

            if (oppositeAsk <= 0)
                return true;

            return level.Bid >= oppositeAsk * ImbalanceRatio;
        }

        private bool WasTouchedAfterCreation(int imbalanceBar, int breakoutBar, string side, decimal price)
        {
            for (int bar = imbalanceBar + 1; bar <= breakoutBar; bar++)
            {
                var candle = GetCandle(bar);

                if (side == "BUY" && candle.Low <= price)
                    return true;

                if (side == "SELL" && candle.High >= price)
                    return true;
            }

            return false;
        }

        private List<PriceLevelData> GetPriceLevelsSafe(int bar)
        {
            var result = new List<PriceLevelData>();

            try
            {
                var candle = GetCandle(bar);
                object candleObj = candle;

                MethodInfo method = candleObj.GetType()
                    .GetMethods()
                    .FirstOrDefault(m =>
                        (m.Name == "GetAllPriceLevels" || m.Name == "GetPriceLevels") &&
                        m.GetParameters().Length == 0);

                if (method == null)
                    return result;

                var rawLevels = method.Invoke(candleObj, null) as System.Collections.IEnumerable;

                if (rawLevels == null)
                    return result;

                foreach (var raw in rawLevels)
                {
                    decimal price = GetFirstDecimalProperty(raw,
                        "Price",
                        "Value",
                        "Level",
                        "PriceLevel");

                    decimal bid = GetFirstDecimalProperty(raw,
                        "Bid",
                        "BidVolume",
                        "SellVolume",
                        "VolumeBid",
                        "BidVol");

                    decimal ask = GetFirstDecimalProperty(raw,
                        "Ask",
                        "AskVolume",
                        "BuyVolume",
                        "VolumeAsk",
                        "AskVol");

                    if (price <= 0)
                        continue;

                    if (bid <= 0 && ask <= 0)
                        continue;

                    result.Add(new PriceLevelData
                    {
                        Price = price,
                        Bid = bid,
                        Ask = ask
                    });
                }
            }
            catch
            {
                return result;
            }

            return result.OrderBy(x => x.Price).ToList();
        }

        private decimal GetFirstDecimalProperty(object obj, params string[] propertyNames)
        {
            foreach (var propertyName in propertyNames)
            {
                decimal value = GetDecimalProperty(obj, propertyName);

                if (value != 0)
                    return value;
            }

            return 0;
        }

        private decimal GetDecimalProperty(object obj, string propertyName)
        {
            try
            {
                var prop = obj.GetType().GetProperty(propertyName);

                if (prop == null)
                    return 0;

                var value = prop.GetValue(obj);

                if (value == null)
                    return 0;

                return Convert.ToDecimal(value);
            }
            catch
            {
                return 0;
            }
        }

        private class PriceLevelData
        {
            public decimal Price { get; set; }
            public decimal Bid { get; set; }
            public decimal Ask { get; set; }
        }

        private class ValidImbalanceCandidate
        {
            public int Bar { get; set; }
            public decimal Price { get; set; }
            public decimal Bid { get; set; }
            public decimal Ask { get; set; }
            public decimal DistanceTicks { get; set; }
        }
    }
}