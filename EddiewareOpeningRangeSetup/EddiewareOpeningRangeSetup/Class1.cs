using System;
using System.Drawing;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    public class EddiewareOpeningRangeSetup : Indicator
    {
        private readonly ValueDataSeries _highLine = new ValueDataSeries("OR High 9:30 NY");
        private readonly ValueDataSeries _lowLine = new ValueDataSeries("OR Low 9:30 NY");

        private DateTime _currentDate = DateTime.MinValue;
        private int _dayStartBar;
        private decimal _orHigh;
        private decimal _orLow;
        private bool _rangeReady;
        private bool _labelDrawn;

        private const int TargetHourUtc = 13;
        private const int TargetMinuteUtc = 30;
        private const decimal TickSize = 0.25m;

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
                _dayStartBar = bar;
                _rangeReady = false;
                _labelDrawn = false;
                _orHigh = 0;
                _orLow = 0;
            }

            _highLine[bar] = 0;
            _lowLine[bar] = 0;

            bool isTargetBar =
                time.Hour == TargetHourUtc &&
                time.Minute == TargetMinuteUtc;

            if (isTargetBar && !_rangeReady)
            {
                _orHigh = candle.High;
                _orLow = candle.Low;
                _rangeReady = true;

                decimal rangeTicks = (_orHigh - _orLow) / TickSize;

                string label =
                    rangeTicks < 150 ? $"A+  {rangeTicks:0} ticks" :
                    rangeTicks <= 210 ? $"B FUERTE  {rangeTicks:0} ticks" :
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
                        -35,
                        0,
                        Color.White,
                        Color.Black,
                        Color.Black,
                        20,
                        DrawingText.TextAlign.Center,
                        true
                    );
                }

                for (int i = _dayStartBar; i <= bar; i++)
                {
                    _highLine[i] = _orHigh;
                    _lowLine[i] = _orLow;
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
        }
    }
}