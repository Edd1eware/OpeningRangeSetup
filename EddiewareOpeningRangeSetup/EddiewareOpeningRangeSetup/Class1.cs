using System;
using System.Collections.Generic;
using System.ComponentModel;
using ATAS.Indicators;

namespace ATAS.Indicators.Technical
{
    [DisplayName("Metric No LookAhead Score Manual TP SL")]
    public class MetricNoLookAheadScoreManualTpSl : Indicator
    {
        [DisplayName("Min Score / Cutoff Score")]
        public int MinScore { get; set; } = 5;

        [DisplayName("Min OR Range Ticks")]
        public int MinOrRangeTicks { get; set; } = 40;

        [DisplayName("Max OR Range Ticks")]
        public int MaxOrRangeTicks { get; set; } = 350;

        [DisplayName("Min Body Breakout Ticks")]
        public int MinBodyBreakoutTicks { get; set; } = 10;

        [DisplayName("Min Volume")]
        public decimal MinVolume { get; set; } = 800;

        [DisplayName("Min Abs Delta")]
        public decimal MinAbsDelta { get; set; } = 25;

        [DisplayName("Max Signal Minute NY")]
        public int MaxSignalMinuteNy { get; set; } = 50;

        [DisplayName("TP Ticks")]
        public int TpTicks { get; set; } = 60;

        [DisplayName("SL Ticks")]
        public int SlTicks { get; set; } = 60;

        [DisplayName("Line Length Bars")]
        public int LineLengthBars { get; set; } = 20;

        private decimal _orHigh;
        private decimal _orLow;
        private bool _orReady;
        private DateTime _currentNyDate;

        private decimal _cumPv;
        private decimal _cumVol;

        private readonly List<TradeLevels> _levels = new();

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

        private readonly ValueDataSeries _entryLine = new("ENTRY ORANGE")
        {
            VisualType = VisualMode.Line,
            Width = 2
        };

        private readonly ValueDataSeries _tpLine = new("TP GREEN")
        {
            VisualType = VisualMode.Line,
            Width = 2
        };

        private readonly ValueDataSeries _slLine = new("SL RED")
        {
            VisualType = VisualMode.Line,
            Width = 2
        };

        public MetricNoLookAheadScoreManualTpSl()
        {
            DataSeries[0] = _buySignals;
            DataSeries.Add(_sellSignals);
            DataSeries.Add(_entryLine);
            DataSeries.Add(_tpLine);
            DataSeries.Add(_slLine);
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            var candle = GetCandle(bar);
            var nyTime = ToNewYorkTime(candle.Time);
            var nyDate = nyTime.Date;

            if (bar == 0 || nyDate != _currentNyDate)
                ResetDay(nyDate);

            UpdateSessionVwap(candle);
            PaintActiveLevels(bar);

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

            if (nyTime.Minute < 31 || nyTime.Minute > MaxSignalMinuteNy)
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

            var bodyBreakoutTicks = 0;

            if (longBreakout)
                bodyBreakoutTicks = ToTicks(candle.Close - Math.Max(candle.Open, _orHigh));

            if (shortBreakout)
                bodyBreakoutTicks = ToTicks(Math.Min(candle.Open, _orLow) - candle.Close);

            if (bodyBreakoutTicks < 0)
                bodyBreakoutTicks = 0;

            var bodyOk = bodyBreakoutTicks >= MinBodyBreakoutTicks;
            var volumeOk = candle.Volume >= MinVolume;
            var deltaOk = Math.Abs(candle.Delta) >= MinAbsDelta;
            var timeOk = nyTime.Minute <= MaxSignalMinuteNy;

            var vwapOk =
                (longBreakout && candle.Close >= vwap) ||
                (shortBreakout && candle.Close <= vwap);

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

            if (timeOk)
                score += 1;

            if (score < MinScore)
                return;

            var tickSize = GetTickSize();
            var entry = candle.Close;

            decimal tp;
            decimal sl;

            if (longBreakout)
            {
                tp = entry + tickSize * TpTicks;
                sl = entry - tickSize * SlTicks;

                _buySignals[bar] = candle.Low - tickSize * 10;
            }
            else
            {
                tp = entry - tickSize * TpTicks;
                sl = entry + tickSize * SlTicks;

                _sellSignals[bar] = candle.High + tickSize * 10;
            }

            _levels.Add(new TradeLevels
            {
                StartBar = bar,
                EndBar = bar + LineLengthBars,
                Entry = entry,
                Tp = tp,
                Sl = sl
            });

            PaintActiveLevels(bar);
        }

        private void PaintActiveLevels(int bar)
        {
            foreach (var level in _levels)
            {
                if (bar < level.StartBar || bar > level.EndBar)
                    continue;

                _entryLine[bar] = level.Entry;
                _tpLine[bar] = level.Tp;
                _slLine[bar] = level.Sl;
            }
        }

        private void ResetDay(DateTime nyDate)
        {
            _currentNyDate = nyDate;
            _orHigh = 0;
            _orLow = 0;
            _orReady = false;
            _cumPv = 0;
            _cumVol = 0;
            _levels.Clear();
        }

        private void UpdateSessionVwap(dynamic candle)
        {
            var typical = (candle.High + candle.Low + candle.Close) / 3m;
            var volume = candle.Volume;

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

        private class TradeLevels
        {
            public int StartBar { get; set; }
            public int EndBar { get; set; }
            public decimal Entry { get; set; }
            public decimal Tp { get; set; }
            public decimal Sl { get; set; }
        }
    }
}