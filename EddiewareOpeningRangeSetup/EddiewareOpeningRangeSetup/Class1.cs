using System;
using System.ComponentModel;
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

        private int _orBar = -1;

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Line Length (bars)")]
        public int LineLength { get; set; } = 100;

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
            var clock = time.TimeOfDay;

            if (time.Date != _currentDate)
            {
                _currentDate = time.Date;

                _rangeDrawn = false;
                _orBar = -1;
            }

            var prev = GetCandle(bar - 1);

            bool is930Closed =
                prev.Time.TimeOfDay.Hours == OpeningTimeUtc.Hours &&
                prev.Time.TimeOfDay.Minutes == OpeningTimeUtc.Minutes;

            if (!_rangeDrawn && is930Closed)
            {
                // 🔥 Tomamos la vela 9:30 ya cerrada (bar - 1)
                _orHigh = prev.High;
                _orLow = prev.Low;

                _orBar = bar - 1;

                DrawOR(bar);

                _rangeDrawn = true;
            }
        }

        private void DrawOR(int bar)
        {
            int startBar = _orBar;
            int endBar = _orBar + LineLength;

            var pen = new System.Drawing.Pen(System.Drawing.Color.Red, 1);

            // Línea superior
            var highLine = new TrendLine(startBar, _orHigh, endBar, _orHigh, pen);
            TrendLines.Add(highLine);

            // Línea inferior
            var lowLine = new TrendLine(startBar, _orLow, endBar, _orLow, pen);
            TrendLines.Add(lowLine);
        }
    }
}