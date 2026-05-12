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
        private bool _imbalanceLineDrawn;
        private bool _exhaustionDayLabelDrawn;

        private bool _sellTwoContractsLineDrawn;
        private bool _buyTwoContractsLineDrawn;
        private bool _sellOneContractLineDrawn;
        private bool _buyOneContractLineDrawn;

        private bool _isNoTradeNoiseOR;
        private bool _isFakeBreakoutOR;
        private bool _isWarningAbsorptionOR;
        private bool _fakeInitialOutsideDetected;
        private bool _waitingForFakeReentry;
        private bool _fakeBreakoutReentered;
        private bool _isFakeNoTradeOR;
        private bool _isExhaustionDay;
        private bool _isORTicksTooLarge;

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

        [DisplayName("2 Contracts Distance Ticks")]
        public decimal TwoContractsDistanceTicks { get; set; } = 60;

        [DisplayName("1 Contract Distance Ticks")]
        public decimal OneContractDistanceTicks { get; set; } = 120;

        [DisplayName("Imbalance Ratio")]
        public decimal ImbalanceRatio { get; set; } = 3;

        [DisplayName("Imbalance Volume Filter")]
        public decimal ImbalanceVolumeFilter { get; set; } = 30;

        [DisplayName("Imbalance Line Length")]
        public int ImbalanceLineLength { get; set; } = 10;

        [DisplayName("Show Exhaustion Debug Labels")]
        public bool ShowExhaustionDebugLabels { get; set; } = true;

        [DisplayName("Show Warning Absorption Debug Labels")]
        public bool ShowWarningAbsorptionDebugLabels { get; set; } = true;

        [DisplayName("Absorption Wick Tolerance Ticks")]
        public decimal AbsorptionWickToleranceTicks { get; set; } = 1;

        [DisplayName("Min Signal Body Ticks")]
        public decimal MinSignalBodyTicks { get; set; } = 1;

        [DisplayName("Max OR Range Ticks")]
        public decimal MaxORRangeTicks { get; set; } = 210;



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
                _imbalanceLineDrawn = false;
                _exhaustionDayLabelDrawn = false;

                _sellTwoContractsLineDrawn = false;
                _buyTwoContractsLineDrawn = false;
                _sellOneContractLineDrawn = false;
                _buyOneContractLineDrawn = false;

                _isNoTradeNoiseOR = false;
                _isFakeBreakoutOR = false;
                _isWarningAbsorptionOR = false;
                _fakeInitialOutsideDetected = false;
                _waitingForFakeReentry = false;
                _fakeBreakoutReentered = false;
                _isFakeNoTradeOR = false;
                _isExhaustionDay = false;
                _isORTicksTooLarge = false;

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

            DrawExhaustionDayLabel(time, orCandle);
            DrawSmallBodyLabel(time, orCandle);
            DrawRangeLabel(time);
        }

        private void DrawExhaustionDayLabel(DateTime time, dynamic orCandle)
        {
            if (_exhaustionDayLabelDrawn)
                return;

            decimal bodyHigh = Math.Max(orCandle.Open, orCandle.Close);
            decimal bodyLow = Math.Min(orCandle.Open, orCandle.Close);

            decimal upperWickTicks = (orCandle.High - bodyHigh) / TickSize;
            decimal lowerWickTicks = (bodyLow - orCandle.Low) / TickSize;

            bool noUpperWick = upperWickTicks <= 0;
            bool noLowerWick = lowerWickTicks <= 0;

            decimal orRangeTicks =
                                (orCandle.High - orCandle.Low) / TickSize;

            // EXHAUSTION DAY:
            // - sin mecha superior O inferior
            // - y OR menor a 100 ticks
            bool isExhaustionStructure =
                (noUpperWick || noLowerWick) &&
                orRangeTicks < 100;

            if (!isExhaustionStructure)
                return;

            _isExhaustionDay = true;
            _exhaustionDayLabelDrawn = true;

            decimal candleRange = orCandle.High - orCandle.Low;

            if (candleRange <= 0)
                return;

            decimal body = Math.Abs(orCandle.Close - orCandle.Open);
            decimal bodyTicks = body / TickSize;
            decimal bodyPercent = body / candleRange * 100m;
            decimal rangeTicks = candleRange / TickSize;

            string label =
                $"EXHAUSTION DAY | B{bodyPercent:0}% | {bodyTicks:0}t / OR {rangeTicks:0}t";

            AddText(
                $"EXHAUSTION_DAY_LABEL_{time:yyyyMMdd}",
                label,
                true,
                _orBar,
                _orHigh,
                -85,
                0,
                Color.White,
                Color.Purple,
                Color.Purple,
                18,
                DrawingText.TextAlign.Center,
                true
            );
        }

        private void DrawRangeLabel(DateTime time)
        {
            if (_orLabelDrawn)
                return;

            if (_isExhaustionDay)
                return;

            _orLabelDrawn = true;

            decimal rangeTicks = (_orHigh - _orLow) / TickSize;

            _isORTicksTooLarge = rangeTicks > MaxORRangeTicks;

            string classification =
                _isNoTradeNoiseOR ? "NO TRADE" :
                rangeTicks <= 100 ? "A+" :
                rangeTicks <= MaxORRangeTicks ? "B FUERTE" :
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

            if (_isExhaustionDay)
                return;

            decimal candleRange = orCandle.High - orCandle.Low;

            if (candleRange <= 0)
                return;

            decimal body = Math.Abs(orCandle.Close - orCandle.Open);
            decimal bodyTicks = body / TickSize;
            decimal bodyPercent = body / candleRange * 100m;

            _smallBodyLabelDrawn = true;

            string label;
            Color bgColor;

            if (bodyPercent < MinORBodyQualityPercent)
            {
                _isWarningAbsorptionOR = true;

                label = $"WARNING ABSORPTION | B{bodyPercent:0}% | {bodyTicks:0}t";
                bgColor = Color.DarkOrange;

                if (bodyTicks <= 7m)
                {
                    _isNoTradeNoiseOR = true;
                }
                else if (bodyTicks <= 14m)
                {
                    _isFakeBreakoutOR = true;
                    _fakeInitialOutsideDetected = false;
                    _waitingForFakeReentry = false;
                    _fakeBreakoutReentered = false;
                }
            }
            else
            {
                _isWarningAbsorptionOR = false;

                label = $"HEALTHY BODY | B{bodyPercent:0}% | {bodyTicks:0}t";
                bgColor = Color.DarkGreen;
            }

            AddText(
                $"BODY_QUALITY_LABEL_{time:yyyyMMdd}",
                label,
                true,
                _orBar,
                _orHigh,
                -60,
                0,
                Color.White,
                bgColor,
                bgColor,
                16,
                DrawingText.TextAlign.Center,
                true
            );
        }

        private void CheckBreakoutOnClosedBar(int closedBar)
        {
            if (_breakoutLabelDrawn)
                return;

            if (_orBar < 0 || closedBar <= _orBar)
                return;

            int barsAfterOR = closedBar - _orBar;

            if (barsAfterOR > BreakoutScanBars)
                return;

            if (_isORTicksTooLarge)
                return;

            if (_isExhaustionDay)
            {
                CheckExhaustionAbsorptionOnClosedBar(closedBar);
                return;
            }

            if (_isNoTradeNoiseOR || _isFakeNoTradeOR)
                return;

            var candle = GetCandle(closedBar);

            if (_isWarningAbsorptionOR && ShowWarningAbsorptionDebugLabels)
                DrawWarningAbsorptionDebugLabel(candle, closedBar);


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

            if (!HasEnoughBodyForSignal(candle))
                return;

            decimal imbalancePrice;
            decimal imbalanceAggressive;
            decimal imbalancePassive;

            bool hasValidImbalance =
                side == "BUY"
                    ? TryGetLowestBuyImbalance(candle, out imbalancePrice, out imbalanceAggressive, out imbalancePassive)
                    : TryGetHighestSellImbalance(candle, out imbalancePrice, out imbalanceAggressive, out imbalancePassive);

            if (!hasValidImbalance)
                return;

            DrawOrangeImbalanceLine(closedBar, imbalancePrice, imbalanceAggressive, imbalancePassive);
            _imbalanceLineDrawn = true;

            _breakoutSide = side;
            _breakoutLabelDrawn = true;

            int recommendedContracts = GetRecommendedContracts(side, candle, imbalancePrice);
            DrawPositionSizeDecisionLabel(side, recommendedContracts, candle, closedBar);

            string label = $"{side} A+ TRADE | {realBodyOutsideTicks:0}t";

            decimal textPrice = side == "BUY" ? candle.High : candle.Low;
            int verticalOffset = side == "BUY" ? -45 : 45;

            AddText(
                $"BREAKOUT_LABEL_{candle.Time:yyyyMMdd}",
                label,
                true,
                closedBar,
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

        private void CheckExhaustionAbsorptionOnClosedBar(int closedBar)
        {
            if (_imbalanceLineDrawn)
                return;

            var candle = GetCandle(closedBar);


            bool brokeAboveOR = candle.High > _orHigh;
            bool brokeBelowOR = candle.Low < _orLow;

            decimal absorptionPrice = 0;
            decimal aggressive = 0;
            decimal passive = 0;

            bool hasAbsorption = false;
            string side = "";

            if (brokeBelowOR)
            {
                hasAbsorption = TryGetLowestBuyImbalanceInLowerZone(
                    candle,
                    out absorptionPrice,
                    out aggressive,
                    out passive
                );

                side = "SELL";
            }
            else if (brokeAboveOR)
            {
                hasAbsorption = TryGetHighestSellImbalanceInUpperZone(
                    candle,
                    out absorptionPrice,
                    out aggressive,
                    out passive
                );

                side = "BUY";
            }

            if (ShowExhaustionDebugLabels)
            {
                string debugText;

                if (!brokeAboveOR && !brokeBelowOR)
                    debugText = "NO BREAK OR";
                else if (hasAbsorption)
                    debugText = $"ABSORPTION {side} | {aggressive:0}/{passive:0}";
                else
                {
                    decimal strongestAggressive;
                    decimal strongestPassive;

                    if (TryGetStrongestAnyDiagonalImbalance(
                        candle,
                        out strongestAggressive,
                        out strongestPassive
                    ))
                        debugText = $"NO ABS | {strongestAggressive:0}/{strongestPassive:0}";
                    else
                        debugText = "NO ABS | NONE";
                }

                AddText(
                    $"EXH_DEBUG_{candle.Time:yyyyMMdd_HHmm}_{closedBar}",
                    debugText,
                    true,
                    closedBar,
                    candle.High,
                    -25,
                    0,
                    Color.White,
                    hasAbsorption ? Color.DarkOrange : Color.DarkRed,
                    hasAbsorption ? Color.DarkOrange : Color.DarkRed,
                    10,
                    DrawingText.TextAlign.Center,
                    true
                );
            }

            if (!brokeAboveOR && !brokeBelowOR)
                return;

            if (!hasAbsorption)
                return;

            if (!HasEnoughBodyForSignal(candle))
            {
                if (ShowExhaustionDebugLabels)
                {
                    AddText(
                        $"NO_BODY_FILTER_{candle.Time:yyyyMMdd_HHmm}_{closedBar}",
                        $"NO BODY | {GetBodyTicks(candle):0}t",
                        true,
                        closedBar,
                        candle.Low,
                        25,
                        0,
                        Color.White,
                        Color.DarkRed,
                        Color.DarkRed,
                        10,
                        DrawingText.TextAlign.Center,
                        true
                    );
                }

                return;
            }

            DrawOrangeImbalanceLine(closedBar, absorptionPrice, aggressive, passive);
            _imbalanceLineDrawn = true;
            _breakoutLabelDrawn = true;
            _breakoutSide = side;

            int recommendedContracts = GetRecommendedContracts(side, candle, absorptionPrice);
            DrawPositionSizeDecisionLabel(side, recommendedContracts, candle, closedBar);

            string label = $"{side} EXH ABS | {aggressive:0}/{passive:0}";

            AddText(
                $"EXHAUSTION_ABSORPTION_LABEL_{candle.Time:yyyyMMdd}",
                label,
                true,
                closedBar,
                absorptionPrice,
                side == "SELL" ? 35 : -35,
                0,
                Color.Black,
                Color.Orange,
                Color.Orange,
                14,
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
                var levels = GetClusterLevels(candle);

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

                    if (!IsValidDirectionalImbalanceLocation(candle, current.Price, "BUY"))
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

        private bool TryGetHighestSellImbalance(dynamic candle, out decimal selectedPrice, out decimal selectedBid, out decimal selectedAsk)
        {
            selectedPrice = 0;
            selectedBid = 0;
            selectedAsk = 0;

            try
            {
                var levels = GetClusterLevels(candle);

                if (levels.Count < 2)
                    return false;

                bool found = false;

                for (int i = 0; i < levels.Count - 1; i++)
                {
                    var current = levels[i];
                    var upper = levels[i + 1];

                    if (upper.Ask <= 0)
                        continue;

                    bool isSellImbalance =
                        current.Bid >= ImbalanceVolumeFilter &&
                        current.Bid >= upper.Ask * ImbalanceRatio;

                    if (!isSellImbalance)
                        continue;

                    if (!IsValidDirectionalImbalanceLocation(candle, current.Price, "SELL"))
                        continue;

                    if (!found || current.Price > selectedPrice)
                    {
                        found = true;
                        selectedPrice = current.Price;
                        selectedBid = current.Bid;
                        selectedAsk = upper.Ask;
                    }
                }

                return found;
            }
            catch
            {
                return false;
            }
        }

        private bool TryGetLowestBuyImbalanceInLowerZone(dynamic candle, out decimal selectedPrice, out decimal selectedAsk, out decimal selectedBid)
        {
            selectedPrice = 0;
            selectedAsk = 0;
            selectedBid = 0;

            try
            {
                var levels = GetClusterLevels(candle);

                if (levels.Count < 2)
                    return false;

                decimal bodyLow = Math.Min(candle.Open, candle.Close);
                decimal tolerance = AbsorptionWickToleranceTicks * TickSize;

                bool found = false;

                for (int i = 1; i < levels.Count; i++)
                {
                    var current = levels[i];
                    var lower = levels[i - 1];

                    decimal diagonalBid = lower.Bid;

                    bool diagonalBuyImbalance =
                        diagonalBid > 0 &&
                        current.Ask >= ImbalanceVolumeFilter &&
                        current.Ask >= diagonalBid * ImbalanceRatio;

                    if (!diagonalBuyImbalance)
                        continue;

                    bool isValidAbsorptionZone =
                        current.Price <= bodyLow + tolerance &&
                        current.Price >= candle.Low;

                    if (!isValidAbsorptionZone)
                        continue;

                    if (!found || current.Price < selectedPrice)
                    {
                        found = true;
                        selectedPrice = current.Price;
                        selectedAsk = current.Ask;
                        selectedBid = diagonalBid;
                    }
                }

                return found;
            }
            catch
            {
                return false;
            }
        }



        private bool TryGetHighestSellImbalanceInUpperZone(dynamic candle, out decimal selectedPrice, out decimal selectedBid, out decimal selectedAsk)
        {
            selectedPrice = 0;
            selectedBid = 0;
            selectedAsk = 0;

            try
            {
                var levels = GetClusterLevels(candle);

                if (levels.Count < 2)
                    return false;

                decimal bodyHigh = Math.Max(candle.Open, candle.Close);
                decimal tolerance = AbsorptionWickToleranceTicks * TickSize;

                bool found = false;

                for (int i = 0; i < levels.Count - 1; i++)
                {
                    var current = levels[i];
                    var upper = levels[i + 1];

                    decimal diagonalAsk = upper.Ask;

                    bool diagonalSellImbalance =
                        diagonalAsk > 0 &&
                        current.Bid >= ImbalanceVolumeFilter &&
                        current.Bid >= diagonalAsk * ImbalanceRatio;

                    if (!diagonalSellImbalance)
                        continue;

                    bool isValidAbsorptionZone =
                        current.Price >= bodyHigh - tolerance &&
                        current.Price <= candle.High;

                    if (!isValidAbsorptionZone)
                        continue;

                    if (!found || current.Price > selectedPrice)
                    {
                        found = true;
                        selectedPrice = current.Price;
                        selectedBid = current.Bid;
                        selectedAsk = diagonalAsk;
                    }
                }

                return found;
            }
            catch
            {
                return false;
            }
        }



        private bool IsValidDirectionalImbalanceLocation(dynamic candle, decimal price, string side)
        {
            decimal bodyHigh = Math.Max(candle.Open, candle.Close);
            decimal bodyLow = Math.Min(candle.Open, candle.Close);

            if (_isWarningAbsorptionOR)
            {
                if (side == "BUY")
                    return price < bodyLow;

                if (side == "SELL")
                    return price > bodyHigh;

                return false;
            }

            if (side == "BUY")
                return price >= _orHigh || price < bodyLow;

            if (side == "SELL")
                return price <= _orLow || price > bodyHigh;

            return false;
        }

        private List<ClusterLevel> GetClusterLevels(dynamic candle)
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

            return levels;
        }

        private void DrawOrangeImbalanceLine(int bar, decimal price, decimal aggressive, decimal passive)
        {
            if (_imbalanceLineDrawn)
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
                $"IMB_BREAKOUT_{bar}_{price}",
                $"{aggressive:0}/{passive:0}",
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


        private decimal GetBodyTicks(dynamic candle)
        {
            return Math.Abs(candle.Close - candle.Open) / TickSize;
        }

        private bool HasEnoughBodyForSignal(dynamic candle)
        {
            return GetBodyTicks(candle) >= MinSignalBodyTicks;
        }

        private bool TryGetStrongestAnyDiagonalImbalance(
            dynamic candle,
            out decimal selectedAggressive,
            out decimal selectedPassive)
        {
            selectedAggressive = 0;
            selectedPassive = 0;

            try
            {
                var levels = GetClusterLevels(candle);

                if (levels.Count < 2)
                    return false;

                bool found = false;

                for (int i = 0; i < levels.Count; i++)
                {
                    var current = levels[i];

                    // BUY diagonal: Ask actual / Bid del nivel inferior
                    if (i > 0)
                    {
                        var lower = levels[i - 1];

                        if (lower.Bid > 0 &&
                            current.Ask >= ImbalanceVolumeFilter &&
                            current.Ask >= lower.Bid * ImbalanceRatio)
                        {
                            if (!found || current.Ask > selectedAggressive)
                            {
                                found = true;
                                selectedAggressive = current.Ask;
                                selectedPassive = lower.Bid;
                            }
                        }
                    }

                    // SELL diagonal: Bid actual / Ask del nivel superior
                    if (i < levels.Count - 1)
                    {
                        var upper = levels[i + 1];

                        if (upper.Ask > 0 &&
                            current.Bid >= ImbalanceVolumeFilter &&
                            current.Bid >= upper.Ask * ImbalanceRatio)
                        {
                            if (!found || current.Bid > selectedAggressive)
                            {
                                found = true;
                                selectedAggressive = current.Bid;
                                selectedPassive = upper.Ask;
                            }
                        }
                    }
                }

                return found;
            }
            catch
            {
                return false;
            }
        }

        private class ClusterLevel
        {
            public decimal Price { get; set; }
            public decimal Bid { get; set; }
            public decimal Ask { get; set; }
        }

        private int GetRecommendedContracts(string side, dynamic signalCandle, decimal imbalancePrice)
        {
            decimal distanceTicks = GetImbalanceDistanceFromSignalCloseTicks(side, signalCandle, imbalancePrice);

            // BUY:
            //   2 contratos = la línea naranja quedó dentro de la zona azul, es decir,
            //                a máximo 60 ticks debajo del close de señal.
            //   1 contrato  = la línea naranja quedó debajo de la azul,
            //                pero todavía dentro de la zona de 1 contrato.
            //
            // SELL:
            //   misma lógica inversa: 2 contratos si el imbalance está a máximo
            //   60 ticks arriba del close de señal.
            if (distanceTicks <= TwoContractsDistanceTicks)
                return 2;

            return 1;
        }

        private decimal GetImbalanceDistanceFromSignalCloseTicks(string side, dynamic signalCandle, decimal imbalancePrice)
        {
            decimal distance = 0;

            if (side == "BUY")
                distance = signalCandle.Close - imbalancePrice;

            if (side == "SELL")
                distance = imbalancePrice - signalCandle.Close;

            if (distance < 0)
                distance = 0;

            return distance / TickSize;
        }

        private void DrawPositionSizeDecisionLabel(string side, int contracts, dynamic candle, int closedBar)
        {
            string label = $"{side} {contracts}";
            decimal textPrice = side == "BUY" ? candle.High : candle.Low;
            int verticalOffset = side == "BUY" ? -65 : 65;

            AddText(
                $"POSITION_SIZE_DECISION_{candle.Time:yyyyMMdd_HHmm}_{closedBar}",
                label,
                true,
                closedBar,
                textPrice,
                verticalOffset,
                0,
                Color.White,
                contracts == 2 ? Color.Green : Color.DarkOrange,
                contracts == 2 ? Color.Green : Color.DarkOrange,
                32,
                DrawingText.TextAlign.Center,
                true
            );
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


        private void DrawWarningAbsorptionDebugLabel(dynamic candle, int closedBar)
        {
            decimal bodyHigh = Math.Max(candle.Open, candle.Close);
            decimal bodyLow = Math.Min(candle.Open, candle.Close);

            decimal tolerance =
                AbsorptionWickToleranceTicks * TickSize;

            var levels = GetClusterLevels(candle);

            var lower = new WickDebugCandidate();
            var upper = new WickDebugCandidate();

            for (int i = 0; i < levels.Count; i++)
            {
                var current = levels[i];

                bool inLowerWick =
                    current.Price >= candle.Low &&
                    current.Price <= bodyLow + tolerance;

                bool inUpperWick =
                    current.Price <= candle.High &&
                    current.Price >= bodyHigh - tolerance;

                if (!inLowerWick && !inUpperWick)
                    continue;

                // =========================
                // DIAGONAL BUY ONLY
                // Ask actual / Bid del nivel inferior
                // =========================

                if (i > 0)
                {
                    var lowerLevel = levels[i - 1];

                    if (lowerLevel.Bid > 0 &&
                        current.Ask >= ImbalanceVolumeFilter &&
                        current.Ask >= lowerLevel.Bid * ImbalanceRatio)
                    {
                        if (inLowerWick)
                        {
                            UpdateWickDebugCandidate(
                                lower,
                                current.Price,
                                current.Ask,
                                lowerLevel.Bid
                            );
                        }

                        if (inUpperWick)
                        {
                            UpdateWickDebugCandidate(
                                upper,
                                current.Price,
                                current.Ask,
                                lowerLevel.Bid
                            );
                        }
                    }
                }

                // =========================
                // DIAGONAL SELL ONLY
                // Bid actual / Ask del nivel superior
                // =========================

                if (i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    if (upperLevel.Ask > 0 &&
                        current.Bid >= ImbalanceVolumeFilter &&
                        current.Bid >= upperLevel.Ask * ImbalanceRatio)
                    {
                        if (inLowerWick)
                        {
                            UpdateWickDebugCandidate(
                                lower,
                                current.Price,
                                current.Bid,
                                upperLevel.Ask
                            );
                        }

                        if (inUpperWick)
                        {
                            UpdateWickDebugCandidate(
                                upper,
                                current.Price,
                                current.Bid,
                                upperLevel.Ask
                            );
                        }
                    }
                }
            }

            bool hasAnyDebugImbalance = lower.Found || upper.Found;

            decimal strongestAggressive = 0;
            decimal strongestPassive = 0;

            if (lower.Found)
            {
                strongestAggressive = lower.Aggressive;
                strongestPassive = lower.Passive;
            }

            if (upper.Found && upper.Aggressive > strongestAggressive)
            {
                strongestAggressive = upper.Aggressive;
                strongestPassive = upper.Passive;
            }

            string debugText = hasAnyDebugImbalance
                ? $"NO ABS | {strongestAggressive:0}/{strongestPassive:0}"
                : "NO ABS | NONE";

            AddText(
                $"WARN_ABS_DEBUG_{candle.Time:yyyyMMdd_HHmm}_{closedBar}",
                debugText,
                true,
                closedBar,
                candle.High,
                -30,
                0,
                Color.White,
                hasAnyDebugImbalance
                    ? Color.DarkRed
                    : Color.DarkRed,
                hasAnyDebugImbalance
                    ? Color.DarkRed
                    : Color.DarkRed,
                10,
                DrawingText.TextAlign.Center,
                true
            );
        }



        private void UpdateWickDebugCandidate(
            WickDebugCandidate candidate,
            decimal price,
            decimal aggressive,
            decimal passive)
        {
            if (!candidate.Found ||
                aggressive > candidate.Aggressive)
            {
                candidate.Found = true;
                candidate.Price = price;
                candidate.Aggressive = aggressive;
                candidate.Passive = passive;
            }
        }

        private class WickDebugCandidate
        {
            public bool Found { get; set; }

            public decimal Price { get; set; }

            public decimal Aggressive { get; set; }

            public decimal Passive { get; set; }
        }

    }

}