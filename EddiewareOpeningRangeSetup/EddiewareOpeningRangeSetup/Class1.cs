using System;
using System.ComponentModel;
using System.Drawing;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators
{
    public class EddiewareOpeningRangeSetup : Indicator
    {
        private readonly ValueDataSeries _highLine = new ValueDataSeries("OR_HIGH", "OR High 9:30 NY");
        private readonly ValueDataSeries _lowLine = new ValueDataSeries("OR_LOW", "OR Low 9:30 NY");

        private DateTime _currentDate = DateTime.MinValue;

        private decimal _orHigh;
        private decimal _orLow;

        private bool _rangeReady;
        private bool _labelDrawn;
        private bool _sessionEnded;

        private const decimal TickSize = 0.25m;

        [DisplayName("Session Begin NY")]
        public TimeSpan SessionBeginNY { get; set; } = new TimeSpan(9, 30, 0);

        [DisplayName("Session End NY")]
        public TimeSpan SessionEndNY { get; set; } = new TimeSpan(16, 0, 0);

        [DisplayName("NY to UTC Offset Hours")]
        public int NyToUtcOffsetHours { get; set; } = 4;

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
            var candle = GetCandle(bar);
            var time = candle.Time;
            var clock = time.TimeOfDay;

            var sessionBeginUtc = SessionBeginNY.Add(TimeSpan.FromHours(NyToUtcOffsetHours));
            var sessionEndUtc = SessionEndNY.Add(TimeSpan.FromHours(NyToUtcOffsetHours));

            if (bar == 0 || time.Date != _currentDate)
            {
                _currentDate = time.Date;

                _orHigh = 0;
                _orLow = 0;

                _rangeReady = false;
                _labelDrawn = false;
                _sessionEnded = false;

                if (bar > 0)
                {
                    _highLine.SetPointOfEndLine(bar - 1);
                    _lowLine.SetPointOfEndLine(bar - 1);
                }
            }

            bool beforeSession = clock < sessionBeginUtc;
            bool afterSession = clock > sessionEndUtc;

            if (beforeSession)
            {
                if (bar > 0)
                {
                    _highLine.SetPointOfEndLine(bar);
                    _lowLine.SetPointOfEndLine(bar);
                }

                return;
            }

            if (afterSession)
            {
                if (!_sessionEnded)
                {
                    _sessionEnded = true;

                    if (bar > 0)
                    {
                        _highLine.SetPointOfEndLine(bar - 1);
                        _lowLine.SetPointOfEndLine(bar - 1);
                    }
                }

                return;
            }

            bool isSessionBegin =
                clock.Hours == sessionBeginUtc.Hours &&
                clock.Minutes == sessionBeginUtc.Minutes;

            if (isSessionBegin && !_rangeReady)
            {
                if (bar > 0)
                {
                    _highLine.SetPointOfEndLine(bar - 1);
                    _lowLine.SetPointOfEndLine(bar - 1);
                }

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
            }

            if (_rangeReady)
            {
                _highLine[bar] = _orHigh;
                _lowLine[bar] = _orLow;
            }
        }
    }
}