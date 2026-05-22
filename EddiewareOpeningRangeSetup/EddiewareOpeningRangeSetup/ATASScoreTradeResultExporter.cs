using System;
using System.Globalization;
using System.IO;
using ATAS.Indicators;

namespace ATAS.Indicators
{
    public class ATASScoreTradeResultExporter : Indicator
    {
        private readonly string _exportFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";

        private readonly string _targetDateFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\target_trade_result_date.txt";

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private const decimal SetupTickSize = 0.25m;

        private readonly TimeSpan _openingTimeNy = new TimeSpan(9, 30, 0);
        private readonly TimeSpan _signalStartNy = new TimeSpan(9, 31, 0);

        private DateTime _currentNyDate = DateTime.MinValue;
        private decimal _orHigh;
        private decimal _orLow;
        private int _orBar = -1;
        private bool _orReady;
        private bool _tradeCreated;
        private TradeState? _trade;

        public int MinScore { get; set; } = 5;
        public decimal MinOrRangeTicks { get; set; } = 40;
        public decimal MaxOrRangeTicks { get; set; } = 350;
        public decimal MinBodyBreakoutTicks { get; set; } = 10;
        public decimal MinVolume { get; set; } = 800;
        public decimal MinAbsDelta { get; set; } = 25;
        public int MaxSignalMinuteNy { get; set; } = 50;
        public decimal MinTradeTicks { get; set; } = 60;
        public decimal MaxTradeTicks { get; set; } = 120;
        public bool RequireBodyOkForTrade { get; set; } = true;
        public bool RequireVwapOkForTrade { get; set; } = false;

        public ATASScoreTradeResultExporter()
        {
            Name = "ATAS Score Trade Result Exporter ENTRY SL TP RESULT";
            EnableCustomDrawing = false;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 2)
                return;

            var current = GetCandle(bar);
            var currentNyTime = ConvertToNewYorkTime(current.Time);
            var targetDate = ReadTargetDate();

            if (targetDate == null)
                return;

            if (currentNyTime.Date != _currentNyDate)
                ResetDay(currentNyTime.Date);

            if (currentNyTime.Date != targetDate.Value.Date)
                return;

            var closedBar = bar - 1;
            var closedCandle = GetCandle(closedBar);
            var closedNyTime = ConvertToNewYorkTime(closedCandle.Time);

            if (!_orReady && closedNyTime.TimeOfDay == _openingTimeNy)
            {
                _orHigh = closedCandle.High;
                _orLow = closedCandle.Low;
                _orBar = closedBar;
                _orReady = true;
                return;
            }

            if (!_orReady)
                return;

            UpdateTradeResult(bar, current);

            if (_tradeCreated || bar <= _orBar || !IsSignalWindow(currentNyTime))
                return;

            var score = CalculateLiveScore(current, bar, currentNyTime);

            if (!score.IsReady)
                return;

            CreateTrade(bar, currentNyTime, score);
        }

        private void CreateTrade(int bar, DateTime nyTime, ScoreState score)
        {
            var tradeTicks = score.Side == "BUY"
                ? ClampTicks(RoundToTicks(score.EntryPrice - _orLow))
                : ClampTicks(RoundToTicks(_orHigh - score.EntryPrice));

            var tradePoints = tradeTicks * SetupTickSize;

            var sl = score.Side == "BUY"
                ? score.EntryPrice - tradePoints
                : score.EntryPrice + tradePoints;

            var tp = score.Side == "BUY"
                ? score.EntryPrice + tradePoints
                : score.EntryPrice - tradePoints;

            _trade = new TradeState
            {
                EntryBar = bar,
                Side = score.Side,
                Entry = score.EntryPrice,
                Sl = sl,
                Tp = tp,
                Result = "OPEN"
            };

            _tradeCreated = true;
            WriteTradeFile(nyTime.Date);
        }

        private void UpdateTradeResult(int bar, dynamic candle)
        {
            if (_trade == null || _trade.Result != "OPEN")
                return;

            if (bar < _trade.EntryBar)
                return;

            var hitTp = _trade.Side == "BUY"
                ? candle.High >= _trade.Tp
                : candle.Low <= _trade.Tp;

            var hitSl = _trade.Side == "BUY"
                ? candle.Low <= _trade.Sl
                : candle.High >= _trade.Sl;

            if (!hitTp && !hitSl)
                return;

            _trade.Result = hitSl ? "SL" : "TP";
            WriteTradeFile(_currentNyDate);
        }

        private ScoreState CalculateLiveScore(dynamic candle, int bar, DateTime nyTime)
        {
            var bodyHigh = Math.Max(candle.Open, candle.Close);
            var bodyLow = Math.Min(candle.Open, candle.Close);
            var bullishBreakout = bodyHigh > _orHigh;
            var bearishBreakout = bodyLow < _orLow;
            var vwap = GetSessionVwap(bar, nyTime.Date);
            var orRangeTicks = RoundToTicks(_orHigh - _orLow);
            decimal bodyBreakoutTicks = 0;

            if (bullishBreakout)
                bodyBreakoutTicks = RoundToTicks(bodyHigh - _orHigh);

            if (bearishBreakout)
                bodyBreakoutTicks = RoundToTicks(_orLow - bodyLow);

            if (bodyBreakoutTicks < 0)
                bodyBreakoutTicks = 0;

            var state = new ScoreState
            {
                IsBreakout = bullishBreakout || bearishBreakout,
                Side = bullishBreakout ? "BUY" : bearishBreakout ? "SELL" : "",
                EntryPrice = bullishBreakout ? bodyHigh : bearishBreakout ? bodyLow : candle.Close,
                RangeOk = orRangeTicks >= MinOrRangeTicks && orRangeTicks <= MaxOrRangeTicks,
                BodyOk = bodyBreakoutTicks >= MinBodyBreakoutTicks,
                VolumeOk = candle.Volume >= MinVolume,
                DeltaOk = Math.Abs(candle.Delta) >= MinAbsDelta,
                TimeOk = IsSignalWindow(nyTime),
                VwapOk =
                    (bullishBreakout && candle.Close >= vwap) ||
                    (bearishBreakout && candle.Close <= vwap)
            };

            if (state.VwapOk) state.Score += 2;
            if (state.RangeOk) state.Score += 1;
            if (state.BodyOk) state.Score += 1;
            if (state.VolumeOk) state.Score += 1;
            if (state.DeltaOk) state.Score += 1;
            if (state.TimeOk) state.Score += 1;

            state.IsReady =
                state.IsBreakout &&
                state.Score >= MinScore &&
                (!RequireBodyOkForTrade || state.BodyOk) &&
                (!RequireVwapOkForTrade || state.VwapOk);

            return state;
        }

        private bool IsSignalWindow(DateTime nyTime)
        {
            var time = nyTime.TimeOfDay;

            return time >= _signalStartNy &&
                   nyTime.Hour == 9 &&
                   nyTime.Minute <= MaxSignalMinuteNy;
        }

        private decimal GetSessionVwap(int bar, DateTime nyDate)
        {
            decimal cumPv = 0;
            decimal cumVol = 0;

            for (var i = bar; i >= 0; i--)
            {
                var candle = GetCandle(i);
                var candleNyTime = ConvertToNewYorkTime(candle.Time);

                if (candleNyTime.Date != nyDate)
                    break;

                decimal volume = candle.Volume;

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

        private DateTime ConvertToNewYorkTime(DateTime candleTime)
        {
            var utcTime = candleTime.Kind == DateTimeKind.Utc
                ? candleTime
                : DateTime.SpecifyKind(candleTime, DateTimeKind.Utc);

            return TimeZoneInfo.ConvertTimeFromUtc(utcTime, _nyZone);
        }

        private DateTime? ReadTargetDate()
        {
            if (!File.Exists(_targetDateFile))
                return null;

            var txt = File.ReadAllText(_targetDateFile).Trim();

            if (DateTime.TryParseExact(
                txt,
                "yyyy-MM-dd",
                CultureInfo.InvariantCulture,
                DateTimeStyles.None,
                out var parsed))
            {
                return parsed.Date;
            }

            return null;
        }

        private void WriteTradeFile(DateTime nyDate)
        {
            if (_trade == null)
                return;

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var filePath = Path.Combine(
                _exportFolder,
                $"score_trade_result_{nyDate:yyyy-MM-dd}_NY.csv"
            );

            File.WriteAllText(
                filePath,
                "ENTRY,SL,TP,RESULT" + Environment.NewLine +
                string.Join(",",
                    FormatPrice(_trade.Entry),
                    FormatPrice(_trade.Sl),
                    FormatPrice(_trade.Tp),
                    _trade.Result
                ) + Environment.NewLine
            );
        }

        private void ResetDay(DateTime nyDate)
        {
            _currentNyDate = nyDate;
            _orHigh = 0;
            _orLow = 0;
            _orBar = -1;
            _orReady = false;
            _tradeCreated = false;
            _trade = null;
        }

        private decimal RoundToTicks(decimal points)
        {
            return Math.Round(points / SetupTickSize, 2);
        }

        private decimal ClampTicks(decimal ticks)
        {
            if (ticks < MinTradeTicks)
                return MinTradeTicks;

            if (ticks > MaxTradeTicks)
                return MaxTradeTicks;

            return ticks;
        }

        private string FormatPrice(decimal price)
        {
            return price.ToString("0.00", CultureInfo.InvariantCulture);
        }

        private class ScoreState
        {
            public bool IsBreakout { get; set; }
            public bool IsReady { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public bool RangeOk { get; set; }
            public bool BodyOk { get; set; }
            public bool VolumeOk { get; set; }
            public bool DeltaOk { get; set; }
            public bool TimeOk { get; set; }
            public bool VwapOk { get; set; }
            public int Score { get; set; }
        }

        private class TradeState
        {
            public int EntryBar { get; set; }
            public string Side { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal Sl { get; set; }
            public decimal Tp { get; set; }
            public string Result { get; set; } = "";
        }
    }
}
