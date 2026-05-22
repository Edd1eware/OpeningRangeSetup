using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using ATAS.Indicators;
using ATAS.Indicators.Drawing;

namespace ATAS.Indicators.Technical
{
    [DisplayName("Metric No LookAhead Score TP SL Contracts")]
    public class MetricNoLookAheadScoreTpSlContracts : Indicator
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

        [DisplayName("Risk Ticks 60=2 contratos / 120=1 contrato")]
        public int RiskTicks { get; set; } = 60;

        [DisplayName("Line Length Bars")]
        public int LineLengthBars { get; set; } = 20;

        [DisplayName("Signal Only After Candle Close")]
        public bool SignalOnlyAfterCandleClose { get; set; } = false;

        [DisplayName("Draw Levels From Next Bar")]
        public bool DrawLevelsFromNextBar { get; set; } = false;

        [DisplayName("Show Live Score Debug")]
        public bool ShowLiveScoreDebug { get; set; } = true;

        [DisplayName("Live Score Offset Ticks")]
        public int LiveScoreOffsetTicks { get; set; } = 24;

        private decimal _orHigh;
        private decimal _orLow;
        private bool _orReady;
        private DateTime _currentNyDate;

        private readonly List<TradeLevels> _levels = new();
        private readonly HashSet<int> _signaledBars = new();

        private readonly ValueDataSeries _buy1Signals = new("BUY 1")
        {
            VisualType = VisualMode.UpArrow,
            Width = 4,
            RenderColor = Color.Blue
        };

        private readonly ValueDataSeries _buy2Signals = new("BUY 2")
        {
            VisualType = VisualMode.UpArrow,
            Width = 4,
            RenderColor = Color.Blue
        };

        private readonly ValueDataSeries _sell1Signals = new("SELL 1")
        {
            VisualType = VisualMode.DownArrow,
            Width = 4,
            RenderColor = Color.Red
        };

        private readonly ValueDataSeries _sell2Signals = new("SELL 2")
        {
            VisualType = VisualMode.DownArrow,
            Width = 4,
            RenderColor = Color.Red
        };

        private readonly ValueDataSeries _entryLine = new("ENTRY ORANGE")
        {
            VisualType = VisualMode.Line,
            Width = 2,
            RenderColor = Color.Orange
        };

        private readonly ValueDataSeries _tpLine = new("TP GREEN")
        {
            VisualType = VisualMode.Line,
            Width = 2,
            RenderColor = Color.Green
        };

        private readonly ValueDataSeries _slLine = new("SL RED")
        {
            VisualType = VisualMode.Line,
            Width = 2,
            RenderColor = Color.Red
        };

        public MetricNoLookAheadScoreTpSlContracts()
        {
            DataSeries[0] = _buy1Signals;
            DataSeries.Add(_buy2Signals);
            DataSeries.Add(_sell1Signals);
            DataSeries.Add(_sell2Signals);
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

            if (!IsSignalTime(nyTime))
                return;

            var setup = CalculateSetup(candle, bar, nyTime, nyDate);

            if (ShowLiveScoreDebug)
                DrawLiveScoreDebug(bar, candle, setup);

            if (SignalOnlyAfterCandleClose && bar == CurrentBar - 1)
                return;

            if (!setup.IsBreakout || setup.Score < MinScore || _signaledBars.Contains(bar))
                return;

            var signalNumber = GetSignalNumber();

            if (signalNumber == 0)
                return;

            var tickSize = GetTickSize();
            var entry = candle.Close;

            var tpTicks = RiskTicks;
            var slTicks = RiskTicks;

            decimal tp;
            decimal sl;

            if (setup.IsLong)
            {
                tp = entry + tickSize * tpTicks;
                sl = entry - tickSize * slTicks;

                var labelPrice = candle.Low - tickSize * 10;

                if (signalNumber == 1)
                    _buy1Signals[bar] = labelPrice;
                else
                    _buy2Signals[bar] = labelPrice;

                AddSignalLabel(bar, $"BUY {signalNumber}", labelPrice, false, Color.Blue);
            }
            else
            {
                tp = entry - tickSize * tpTicks;
                sl = entry + tickSize * slTicks;

                var labelPrice = candle.High + tickSize * 10;

                if (signalNumber == 1)
                    _sell1Signals[bar] = labelPrice;
                else
                    _sell2Signals[bar] = labelPrice;

                AddSignalLabel(bar, $"SELL {signalNumber}", labelPrice, true, Color.Red);
            }

            var levelsStartBar = DrawLevelsFromNextBar ? bar + 1 : bar;

            _levels.Add(new TradeLevels
            {
                StartBar = levelsStartBar,
                EndBar = levelsStartBar + LineLengthBars,
                Entry = entry,
                Tp = tp,
                Sl = sl
            });

            _signaledBars.Add(bar);
            PaintActiveLevels(bar);
        }

        private bool IsSignalTime(DateTime nyTime)
        {
            return
                nyTime.Hour == 9 &&
                nyTime.Minute >= 31 &&
                nyTime.Minute <= MaxSignalMinuteNy;
        }

        private SetupState CalculateSetup(dynamic candle, int bar, DateTime nyTime, DateTime nyDate)
        {
            var vwap = GetSessionVwap(bar, nyDate);
            var longBreakout = candle.Close > _orHigh;
            var shortBreakout = candle.Close < _orLow;
            var isBreakout = longBreakout || shortBreakout;
            var orRangeTicks = ToTicks(_orHigh - _orLow);

            var bodyBreakoutTicks = 0;

            if (longBreakout)
                bodyBreakoutTicks = ToTicks(candle.Close - Math.Max(candle.Open, _orHigh));

            if (shortBreakout)
                bodyBreakoutTicks = ToTicks(Math.Min(candle.Open, _orLow) - candle.Close);

            if (bodyBreakoutTicks < 0)
                bodyBreakoutTicks = 0;

            var state = new SetupState
            {
                IsBreakout = isBreakout,
                IsLong = longBreakout,
                IsShort = shortBreakout,
                Vwap = vwap,
                OrRangeTicks = orRangeTicks,
                BodyBreakoutTicks = bodyBreakoutTicks,
                RangeOk = orRangeTicks >= MinOrRangeTicks && orRangeTicks <= MaxOrRangeTicks,
                BodyOk = bodyBreakoutTicks >= MinBodyBreakoutTicks,
                VolumeOk = candle.Volume >= MinVolume,
                DeltaOk = Math.Abs(candle.Delta) >= MinAbsDelta,
                TimeOk = nyTime.Minute <= MaxSignalMinuteNy,
                VwapOk =
                    (longBreakout && candle.Close >= vwap) ||
                    (shortBreakout && candle.Close <= vwap)
            };

            if (state.VwapOk) state.Score += 2;
            if (state.RangeOk) state.Score += 1;
            if (state.BodyOk) state.Score += 1;
            if (state.VolumeOk) state.Score += 1;
            if (state.DeltaOk) state.Score += 1;
            if (state.TimeOk) state.Score += 1;

            return state;
        }

        private void DrawLiveScoreDebug(int bar, dynamic candle, SetupState setup)
        {
            var tickSize = GetTickSize();
            var price = candle.High + tickSize * LiveScoreOffsetTicks;
            var side = setup.IsLong ? "BUY" : setup.IsShort ? "SELL" : "NO BREAK";
            var status = setup.IsBreakout && setup.Score >= MinScore ? "READY" : "WAIT";
            var background = setup.IsBreakout && setup.Score >= MinScore
                ? Color.DarkGreen
                : setup.IsBreakout
                    ? Color.DarkOrange
                    : Color.DimGray;

            AddText(
                "metric-live-score",
                $"{status} {side} S{setup.Score}/7 | OR {setup.OrRangeTicks}t | BODY {setup.BodyBreakoutTicks}t | V{Flag(setup.VolumeOk)} D{Flag(setup.DeltaOk)} VW{Flag(setup.VwapOk)}",
                true,
                bar,
                price,
                0,
                0,
                Color.White,
                background,
                background,
                11,
                DrawingText.TextAlign.Center,
                true);
        }

        private string Flag(bool value)
        {
            return value ? "+" : "-";
        }

        private int GetSignalNumber()
        {
            if (RiskTicks == 120)
                return 1;

            if (RiskTicks == 60)
                return 2;

            return 0;
        }

        private void AddSignalLabel(int bar, string text, decimal price, bool isAbovePrice, Color color)
        {
            AddText(
                $"metric-signal-{bar}",
                text,
                isAbovePrice,
                bar,
                price,
                Color.White,
                Color.Black,
                color,
                10,
                DrawingText.TextAlign.Center,
                true);
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
            _levels.Clear();
            _signaledBars.Clear();
        }

        private decimal GetSessionVwap(int bar, DateTime nyDate)
        {
            decimal cumPv = 0;
            decimal cumVol = 0;

            for (var i = bar; i >= 0; i--)
            {
                var candle = GetCandle(i);
                var candleNyTime = ToNewYorkTime(candle.Time);

                if (candleNyTime.Date != nyDate)
                    break;

                var volume = candle.Volume;

                if (volume <= 0)
                    continue;

                var typical = (candle.High + candle.Low + candle.Close) / 3m;

                cumPv += typical * volume;
                cumVol += volume;
            }

            if (cumVol <= 0)
                return 0;

            return cumPv / cumVol;
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

        private class SetupState
        {
            public bool IsBreakout { get; set; }
            public bool IsLong { get; set; }
            public bool IsShort { get; set; }
            public decimal Vwap { get; set; }
            public int OrRangeTicks { get; set; }
            public int BodyBreakoutTicks { get; set; }
            public bool RangeOk { get; set; }
            public bool BodyOk { get; set; }
            public bool VolumeOk { get; set; }
            public bool DeltaOk { get; set; }
            public bool TimeOk { get; set; }
            public bool VwapOk { get; set; }
            public int Score { get; set; }
        }
    }
}
