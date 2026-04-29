using System;
using System.ComponentModel;
using ATAS.Indicators;

namespace ATAS.Indicators
{
    public class EddiewareOpeningRangeSetup : Indicator
    {
        private readonly ValueDataSeries _highLine = new ValueDataSeries("OR_HIGH", "OR High 9:30 UTC-4");
        private readonly ValueDataSeries _lowLine = new ValueDataSeries("OR_LOW", "OR Low 9:30 UTC-4");

        private DateTime _currentDate = DateTime.MinValue;

        private decimal _orHigh;
        private decimal _orLow;

        private bool _rangeReady;
        private bool _sessionEnded;

        [DisplayName("Opening Time UTC Internal")]
        public TimeSpan OpeningTimeUtcInternal { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Session End UTC Internal")]
        public TimeSpan SessionEndUtcInternal { get; set; } = new TimeSpan(20, 0, 0);

        public EddiewareOpeningRangeSetup()
        {
            DataSeries[0] = _highLine;
            DataSeries.Add(_lowLine);

            _highLine.ShowZeroValue = false;
            _lowLine.ShowZeroValue = false;

            _highLine.Width = 1;
            _lowLine.Width = 1;

            DrawAbovePrice = true;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            var candle = GetCandle(bar);
            var time = candle.Time;
            var clock = time.TimeOfDay;

            if (time.Date != _currentDate)
            {
                _currentDate = time.Date;

                _orHigh = 0;
                _orLow = 0;

                _rangeReady = false;
                _sessionEnded = false;

                _highLine.SetPointOfEndLine(bar - 1);
                _lowLine.SetPointOfEndLine(bar - 1);
            }

            if (clock > SessionEndUtcInternal)
            {
                if (!_sessionEnded)
                {
                    _sessionEnded = true;
                    _highLine.SetPointOfEndLine(bar - 1);
                    _lowLine.SetPointOfEndLine(bar - 1);
                }

                return;
            }

            var prevCandle = GetCandle(bar - 1);
            var prevTime = prevCandle.Time;
            var prevClock = prevTime.TimeOfDay;

            bool previousBarWasOpening =
                prevClock.Hours == OpeningTimeUtcInternal.Hours &&
                prevClock.Minutes == OpeningTimeUtcInternal.Minutes;

            if (!_rangeReady && previousBarWasOpening)
            {
                _highLine.SetPointOfEndLine(bar - 1);
                _lowLine.SetPointOfEndLine(bar - 1);

                // Aquí ya está cerrada la vela 9:30.
                // Se toma el rango completo: mecha superior + mecha inferior.
                _orHigh = prevCandle.High;
                _orLow = prevCandle.Low;

                _rangeReady = true;
            }

            if (_rangeReady)
            {
                _highLine[bar] = _orHigh;
                _lowLine[bar] = _orLow;
            }
        }
    }
}