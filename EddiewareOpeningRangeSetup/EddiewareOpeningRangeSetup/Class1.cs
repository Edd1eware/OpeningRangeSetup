using System;
using System.Drawing;
using System.Linq;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    public class EddiewareOpeningRangeSetup : Indicator
    {
        private readonly ValueDataSeries _highLine = new ValueDataSeries("OR High 9:30 NY");
        private readonly ValueDataSeries _lowLine = new ValueDataSeries("OR Low 9:30 NY");

        private DateTime _currentDate = DateTime.MinValue;
        private int _orBar = -1;

        private decimal _orHigh;
        private decimal _orLow;

        private bool _rangeReady;
        private bool _labelDrawn;
        private bool _breakoutLabelDrawn;

        private const int TargetHourUtc = 13;
        private const int TargetMinuteUtc = 30;

        private const decimal TickSize = 0.25m;
        private const decimal ImbalanceRatio = 1.5m;
        private const decimal MinImbalanceVolume = 10m;

        private const decimal MaxSlSearchTicks = 250m;

        public EddiewareOpeningRangeSetup()
        {
            DataSeries[0] = _highLine;
            DataSeries.Add(_lowLine);

            _highLine.ShowZeroValue = false;
            _lowLine.ShowZeroValue = false;

            DrawAbovePrice = true;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            var candle = GetCandle(bar);
            var time = candle.Time;

            if (bar == 0 || time.Date != _currentDate)
            {
                _currentDate = time.Date;
                _orBar = -1;
                _orHigh = 0;
                _orLow = 0;

                _rangeReady = false;
                _labelDrawn = false;
                _breakoutLabelDrawn = false;
            }

            _highLine[bar] = 0;
            _lowLine[bar] = 0;

            bool isTargetBar = time.Hour == TargetHourUtc && time.Minute == TargetMinuteUtc;

            if (isTargetBar && !_rangeReady)
            {
                _orBar = bar;
                _orHigh = candle.High;
                _orLow = candle.Low;
                _rangeReady = true;

                decimal rangeTicks = (_orHigh - _orLow) / TickSize;

                string label =
                    rangeTicks < 60 ? $"A+  {rangeTicks:0} ticks" :
                    rangeTicks <= 80 ? $"B FUERTE  {rangeTicks:0} ticks" :
                    $"NO TRADE  {rangeTicks:0} ticks";

                if (!_labelDrawn)
                {
                    _labelDrawn = true;

                    AddText(
                        $"OR_LABEL_{time:yyyyMMdd}_{bar}",
                        label,
                        true,
                        bar,
                        _orHigh,
                        -40,
                        0,
                        Color.White,
                        Color.Black,
                        Color.Black,
                        20,
                        DrawingText.TextAlign.Center,
                        true
                    );
                }

                return;
            }

            bool afterTarget =
                time.Hour > TargetHourUtc ||
                (time.Hour == TargetHourUtc && time.Minute > TargetMinuteUtc);

            if (_rangeReady && afterTarget)
            {
                _highLine[bar] = _orHigh;
                _lowLine[bar] = _orLow;
            }

            bool isClosedBar = bar < CurrentBar - 1;

            if (_rangeReady && afterTarget && isClosedBar && !_breakoutLabelDrawn)
            {
                decimal breakoutTicks = 0;
                string direction = "";

                if (candle.Close > _orHigh)
                {
                    breakoutTicks = (candle.Close - _orHigh) / TickSize;
                    direction = "BUY";
                }
                else if (candle.Close < _orLow)
                {
                    breakoutTicks = (_orLow - candle.Close) / TickSize;
                    direction = "SELL";
                }

                if (breakoutTicks >= 20)
                {
                    _breakoutLabelDrawn = true;

                    string breakoutLabel;
                    string simpleLabel;

                    if (breakoutTicks <= 35)
                    {
                        breakoutLabel = $"BR VÁLIDO {direction}  {breakoutTicks:0} ticks";
                        simpleLabel = "VÁLIDO";
                    }
                    else if (breakoutTicks <= 60)
                    {
                        breakoutLabel = $"🔥 A+ {direction}  {breakoutTicks:0} ticks";
                        simpleLabel = "A+";
                    }
                    else
                    {
                        breakoutLabel = $"🚀 EXTREMO {direction}  {breakoutTicks:0} ticks";
                        simpleLabel = "EXTREMO";
                    }

                    decimal breakoutLabelPrice = direction == "BUY" ? candle.High : candle.Low;
                    int verticalOffset = direction == "BUY" ? -35 : 35;

                    AddText(
                        $"BREAKOUT_{time:yyyyMMdd}_{bar}",
                        breakoutLabel,
                        true,
                        bar,
                        breakoutLabelPrice,
                        verticalOffset,
                        0,
                        Color.White,
                        Color.Black,
                        Color.Black,
                        18,
                        DrawingText.TextAlign.Center,
                        true
                    );

                    AddText(
                        $"SIMPLE_{time:yyyyMMdd}_{bar}",
                        simpleLabel,
                        true,
                        bar,
                        breakoutLabelPrice,
                        verticalOffset - 20,
                        0,
                        Color.Yellow,
                        Color.Transparent,
                        Color.Transparent,
                        22,
                        DrawingText.TextAlign.Center,
                        true
                    );

                    decimal slLevel;
                    decimal slTicks;

                    bool foundImbalance = direction == "BUY"
                        ? TryFindBuySlFromBreakoutClose(bar, candle.Close, out slLevel, out slTicks)
                        : TryFindSellSlFromBreakoutClose(bar, candle.Close, out slLevel, out slTicks);

                    if (foundImbalance)
                    {
                        // 🔥 SOLO CAMBIO: SL DEBAJO DE LA VELA
                        AddText(
                            $"SL_{time:yyyyMMdd}_{bar}",
                            $"------ SL {slTicks:0} ticks",
                            true,
                            bar,
                            candle.Low,   // 👈 base en el low de la vela
                            40,           // 👈 lo baja
                            0,
                            Color.White,
                            Color.Transparent,
                            Color.Transparent,
                            14,
                            DrawingText.TextAlign.Center,
                            true
                        );
                    }
                }
            }
        }

        // 🔽 TODO LO DEMÁS IGUAL 🔽

        private bool TryFindBuySlFromBreakoutClose(int breakoutBar, decimal breakoutClose, out decimal slLevel, out decimal slTicks)
        {
            slLevel = 0;
            slTicks = 0;

            if (_orBar < 0)
                return false;

            decimal bestDistance = decimal.MaxValue;
            decimal bestLevel = 0;

            for (int bar = breakoutBar; bar >= _orBar + 1; bar--)
            {
                var candle = GetCandle(bar);

                if (candle.Time.Date != _currentDate)
                    break;

                var levels = candle.GetAllPriceLevels().OrderByDescending(x => x.Price).ToList();

                for (int i = 0; i < levels.Count - 1; i++)
                {
                    var current = levels[i];
                    var lower = levels[i + 1];

                    if (current.Price >= breakoutClose)
                        continue;

                    if (!IsBuyImbalance(current, lower))
                        continue;

                    decimal distanceTicks = (breakoutClose - current.Price) / TickSize;

                    if (distanceTicks <= 0 || distanceTicks > MaxSlSearchTicks)
                        continue;

                    if (bar < breakoutBar && WasBuyLevelTouchedAfter(bar + 1, breakoutBar, current.Price))
                        continue;

                    if (distanceTicks < bestDistance)
                    {
                        bestDistance = distanceTicks;
                        bestLevel = current.Price;
                    }
                }
            }

            if (bestLevel == 0)
                return false;

            slLevel = bestLevel;
            slTicks = Math.Round(bestDistance, 0);
            return true;
        }

        private bool TryFindSellSlFromBreakoutClose(int breakoutBar, decimal breakoutClose, out decimal slLevel, out decimal slTicks)
        {
            slLevel = 0;
            slTicks = 0;

            if (_orBar < 0)
                return false;

            decimal bestDistance = decimal.MaxValue;
            decimal bestLevel = 0;

            for (int bar = breakoutBar; bar >= _orBar + 1; bar--)
            {
                var candle = GetCandle(bar);

                if (candle.Time.Date != _currentDate)
                    break;

                var levels = candle.GetAllPriceLevels().OrderBy(x => x.Price).ToList();

                for (int i = 0; i < levels.Count - 1; i++)
                {
                    var current = levels[i];
                    var upper = levels[i + 1];

                    if (current.Price <= breakoutClose)
                        continue;

                    if (!IsSellImbalance(current, upper))
                        continue;

                    decimal distanceTicks = (current.Price - breakoutClose) / TickSize;

                    if (distanceTicks <= 0 || distanceTicks > MaxSlSearchTicks)
                        continue;

                    if (bar < breakoutBar && WasSellLevelTouchedAfter(bar + 1, breakoutBar, current.Price))
                        continue;

                    if (distanceTicks < bestDistance)
                    {
                        bestDistance = distanceTicks;
                        bestLevel = current.Price;
                    }
                }
            }

            if (bestLevel == 0)
                return false;

            slLevel = bestLevel;
            slTicks = Math.Round(bestDistance, 0);
            return true;
        }

        private bool WasBuyLevelTouchedAfter(int fromBar, int toBar, decimal price)
        {
            for (int i = fromBar; i <= toBar; i++)
            {
                if (i < 0 || i >= CurrentBar)
                    continue;

                if (GetCandle(i).Low <= price)
                    return true;
            }
            return false;
        }

        private bool WasSellLevelTouchedAfter(int fromBar, int toBar, decimal price)
        {
            for (int i = fromBar; i <= toBar; i++)
            {
                if (i < 0 || i >= CurrentBar)
                    continue;

                if (GetCandle(i).High >= price)
                    return true;
            }
            return false;
        }

        private bool IsBuyImbalance(PriceVolumeInfo current, PriceVolumeInfo lower)
        {
            if (current.Ask < MinImbalanceVolume)
                return false;

            if (lower.Bid <= 0)
                return current.Ask >= MinImbalanceVolume;

            return current.Ask >= lower.Bid * ImbalanceRatio;
        }

        private bool IsSellImbalance(PriceVolumeInfo current, PriceVolumeInfo upper)
        {
            if (current.Bid < MinImbalanceVolume)
                return false;

            if (upper.Ask <= 0)
                return current.Bid >= MinImbalanceVolume;

            return current.Bid >= upper.Ask * ImbalanceRatio;
        }
    }
}