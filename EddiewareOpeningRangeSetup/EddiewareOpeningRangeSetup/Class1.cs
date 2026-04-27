using System;
using ATAS.Indicators;

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

        // 9:30 NY UTC-4 = 13:30 UTC
        private const int TargetHourUtc = 13;
        private const int TargetMinuteUtc = 30;

        public EddiewareOpeningRangeSetup()
        {
            DataSeries[0] = _highLine;
            DataSeries.Add(_lowLine);

            _highLine.ShowZeroValue = false;
            _lowLine.ShowZeroValue = false;
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

                // Rellena desde el inicio del día hasta 9:30 para evitar el trazo vertical
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