using System;
using System.Collections.Generic;
using System.ComponentModel;
using ATAS.Indicators;

namespace ATAS.Indicators.Technical
{
    [DisplayName("Metric Results No LookAhead Filter")]
    public class MetricResultsNoLookAheadFilter : Indicator
    {
        private readonly HashSet<string> ValidDates = new()
        {
            // "2023-11-07",
            // "2023-11-08",
        };

        [DisplayName("Only Valid Dates")]
        public bool OnlyValidDates { get; set; } = true;

        [DisplayName("Min Score")]
        public int MinScore { get; set; } = 3;

        [DisplayName("Min OR Range Ticks")]
        public int MinOrRangeTicks { get; set; } = 40;

        [DisplayName("Max OR Range Ticks")]
        public int MaxOrRangeTicks { get; set; } = 350;

        [DisplayName("Min Breakout Body Ticks")]
        public int MinBreakoutBodyTicks { get; set; } = 10;

        [DisplayName("Min Volume")]
        public decimal MinVolume { get; set; } = 800;

        [DisplayName("Min Abs Delta")]
        public decimal MinAbsDelta { get; set; } = 25;

        [DisplayName("Max Signal Minute")]
        public int MaxSignalMinute { get; set; } = 50;

        private decimal _orHigh;
        private decimal _orLow;
        private bool _orReady;
        private DateTime _currentNyDate;

        private decimal _cumPv;
        private decimal _cumVol;

        private readonly ValueDataSeries _buySignals = new("BUY VALID")
        {
            VisualType = VisualMode.UpArrow,
            Width = 3
        };

        private readonly ValueDataSeries _sellSignals = new("SELL VALID")
        {
            VisualType = VisualMode.DownArrow,
            Width = 3
        };

        public MetricResultsNoLookAheadFilter()
        {
            DataSeries[0] = _buySignals;
            DataSeries.Add(_sellSignals);
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            var candle = GetCandle(bar);
            var nyTime = ToNewYorkTime(candle.Time);
            var nyDate = nyTime.Date;
            var dateKey = nyDate.ToString("yyyy-MM-dd");

            if (OnlyValidDates && ValidDates.Count > 0 && !ValidDates.Contains(dateKey))
                return;

            if (bar == 0 || nyDate != _currentNyDate)
                ResetDay(nyDate);

            UpdateSessionVwap(candle);

            if (nyTime.Hour == 9 && nyTime.Minute == 30)
            {
                _orHigh = candle.High;
                _orLow = candle.Low;
                _orReady = true;
                return;
            }

            if (!_orReady)
                return;

            if (nyTime.Hour != 9)
                return;

            if (nyTime.Minute < 31 || nyTime.Minute > MaxSignalMinute)
                return;

            var vwap = GetVwap();

            var longBreakout = candle.Close > _orHigh;
            var shortBreakout = candle.Close < _orLow;

            if (!longBreakout && !shortBreakout)
                return;

            var orRangeTicks = ToTicks(_orHigh - _orLow);

            var rangeOk =
                orRangeTicks >= MinOrRangeTicks &&
                orRangeTicks <= MaxOrRangeTicks;

            var breakoutBodyTicks = 0;

            if (longBreakout)
                breakoutBodyTicks = ToTicks(candle.Close - Math.Max(candle.Open, _orHigh));

            if (shortBreakout)
                breakoutBodyTicks = ToTicks(Math.Min(candle.Open, _orLow) - candle.Close);

            if (breakoutBodyTicks < 0)
                breakoutBodyTicks = 0;

            var bodyOk = breakoutBodyTicks >= MinBreakoutBodyTicks;

            var vwapOk =
                (longBreakout && candle.Close >= vwap) ||
                (shortBreakout && candle.Close <= vwap);

            var volumeOk = candle.Volume >= MinVolume;
            var deltaOk = Math.Abs(candle.Delta) >= MinAbsDelta;

            var score = 0;

            if (vwapOk)
                score += 2;

            if (rangeOk)
                score += 1;

            if (bodyOk)
                score += 1;

            if (volumeOk)
                score += 1;

            if (deltaOk)
                score += 1;

            if (score < MinScore)
                return;

            var tickSize = GetTickSize();

            if (longBreakout)
                _buySignals[bar] = candle.Low - tickSize * 10;

            if (shortBreakout)
                _sellSignals[bar] = candle.High + tickSize * 10;
        }

        private void ResetDay(DateTime nyDate)
        {
            _currentNyDate = nyDate;
            _orHigh = 0;
            _orLow = 0;
            _orReady = false;
            _cumPv = 0;
            _cumVol = 0;
        }

        private void UpdateSessionVwap(dynamic candle)
        {
            decimal typical = (candle.High + candle.Low + candle.Close) / 3m;
            decimal volume = candle.Volume;

            if (volume <= 0)
                return;

            _cumPv += typical * volume;
            _cumVol += volume;
        }

        private decimal GetVwap()
        {
            if (_cumVol <= 0)
                return 0;

            return _cumPv / _cumVol;
        }

        private int ToTicks(decimal priceDistance)
        {
            var tickSize = GetTickSize();

            if (tickSize <= 0)
                return 0;

            return (int)Math.Round(priceDistance / tickSize);
        }

        private decimal GetTickSize()
        {
            if (InstrumentInfo != null && InstrumentInfo.TickSize > 0)
                return InstrumentInfo.TickSize;

            return 0.25m;
        }

        private DateTime ToNewYorkTime(DateTime time)
        {
            try
            {
                var nyZone = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

                if (time.Kind == DateTimeKind.Utc)
                    return TimeZoneInfo.ConvertTimeFromUtc(time, nyZone);

                return TimeZoneInfo.ConvertTime(time, nyZone);
            }
            catch
            {
                return time;
            }
        }
    }
}