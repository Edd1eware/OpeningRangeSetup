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
        private const string ExporterVersion = "score-exporter-debug-2026-05-22-e-x10";

        private readonly TimeSpan _openingTimeNy = new TimeSpan(9, 30, 0);
        private readonly TimeSpan _signalStartNy = new TimeSpan(9, 31, 0);
        private const decimal HardMaxTradeTicks = 120m;
        private const decimal APlusStopTicks = 100m;

        private DateTime _currentNyDate = DateTime.MinValue;
        private decimal _orHigh;
        private decimal _orLow;
        private int _orBar = -1;
        private bool _orReady;
        private bool _tradeCreated;
        private int _speedBar = -1;
        private DateTime _speedBarStartedAtUtc = DateTime.MinValue;
        private TradeState? _trade;

        public int MinScore { get; set; } = 5;
        public decimal MinOrRangeTicks { get; set; } = 40;
        public decimal MaxOrRangeTicks { get; set; } = 350;
        public decimal MinBodyBreakoutTicks { get; set; } = 10;
        public decimal MinVolume { get; set; } = 800;
        public decimal MinAbsDelta { get; set; } = 25;
        public int MaxSignalMinuteNy { get; set; } = 50;
        public decimal MinNormalSpeedTicksPerSecond { get; set; } = 2;
        public decimal APlusSpeedTicksPerSecond { get; set; } = 5;
        public decimal ReplaySpeedMultiplier { get; set; } = 10;
        public decimal MinTradeTicks { get; set; } = 60;
        public decimal MaxTradeTicks { get; set; } = 120;
        public decimal HalfMfeExitMinMfeTicks { get; set; } = 40;
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

            UpdateSpeedClock(bar);

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
            var tpTicks = score.SpeedLabel == "A+ speed"
                ? HardMaxTradeTicks
                : score.Side == "BUY"
                    ? ClampTicks(RoundToTicks(score.EntryPrice - _orLow))
                    : ClampTicks(RoundToTicks(_orHigh - score.EntryPrice));

            var slTicks = score.SpeedLabel == "A+ speed"
                ? APlusStopTicks
                : MinTradeTicks;

            var sl = score.Side == "BUY"
                ? score.EntryPrice - slTicks * SetupTickSize
                : score.EntryPrice + slTicks * SetupTickSize;

            var tp = score.Side == "BUY"
                ? score.EntryPrice + tpTicks * SetupTickSize
                : score.EntryPrice - tpTicks * SetupTickSize;

            sl = ClampExitDistance(score.EntryPrice, sl, score.Side == "BUY" ? -1 : 1);
            tp = ClampExitDistance(score.EntryPrice, tp, score.Side == "BUY" ? 1 : -1);
            slTicks = RoundToTicks(Math.Abs(score.EntryPrice - sl));
            tpTicks = RoundToTicks(Math.Abs(score.EntryPrice - tp));

            _trade = new TradeState
            {
                EntryBar = bar,
                EntryDate = nyTime.Date,
                EntryTimeNy = nyTime,
                Side = score.Side,
                OrLow = score.OrLow,
                OrHigh = score.OrHigh,
                OrRangeTicks = score.OrRangeTicks,
                Vwap = score.Vwap,
                BodyBreakoutTicks = score.BodyBreakoutTicks,
                BreakoutSpeed = score.BreakoutSpeed,
                SpeedElapsedSeconds = score.SpeedElapsedSeconds,
                SpeedUsedReplayFallback = score.SpeedUsedReplayFallback,
                SpeedTimingSource = score.SpeedTimingSource,
                SpeedLabel = score.SpeedLabel,
                Volume = score.Volume,
                Delta = score.Delta,
                RangeOk = score.RangeOk,
                BodyOk = score.BodyOk,
                VolumeOk = score.VolumeOk,
                DeltaOk = score.DeltaOk,
                TimeOk = score.TimeOk,
                VwapOk = score.VwapOk,
                SpeedValid = score.SpeedValid,
                Score = score.Score,
                Entry = score.EntryPrice,
                Sl = sl,
                Tp = tp,
                SlTicks = slTicks,
                TpTicks = tpTicks,
                BestFavorablePrice = score.EntryPrice,
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

            UpdateTradeExcursion(candle);
            UpdateBestFavorablePrice(candle);

            var hitTp = _trade.Side == "BUY"
                ? candle.High >= _trade.Tp
                : candle.Low <= _trade.Tp;

            var hitSl = _trade.Side == "BUY"
                ? candle.Low <= _trade.Sl
                : candle.High >= _trade.Sl;

            if (!hitTp && !hitSl)
            {
                if (TryApplyHalfMfeExit(candle))
                    WriteTradeFile(_currentNyDate);

                return;
            }

            _trade.Result = hitTp ? "TP" : "SL";
            _trade.ExitPrice = hitTp ? _trade.Tp : _trade.Sl;
            WriteTradeFile(_currentNyDate);
        }

        private decimal TradeResultTicks()
        {
            if (_trade == null)
                return 0;

            if (_trade.Result == "TP")
                return _trade.TpTicks;

            if (_trade.Result == "SL")
                return -_trade.SlTicks;

            if (_trade.Result == "EXIT" && _trade.ExitPrice != 0)
                return RoundToTicks(Math.Abs(_trade.ExitPrice - _trade.Entry));

            if (_trade.Result == "BE")
                return 0;

            return 0;
        }

        private void UpdateBestFavorablePrice(dynamic candle)
        {
            if (_trade == null)
                return;

            if (_trade.Side == "BUY")
            {
                if (candle.High > _trade.BestFavorablePrice)
                    _trade.BestFavorablePrice = candle.High;
            }
            else
            {
                if (_trade.BestFavorablePrice == 0 || candle.Low < _trade.BestFavorablePrice)
                    _trade.BestFavorablePrice = candle.Low;
            }
        }

        private bool TryApplyHalfMfeExit(dynamic candle)
        {
            if (_trade == null || _trade.Result != "OPEN")
                return false;

            if (_trade.SpeedLabel == "A+ speed")
                return false;

            var mfeTicks = _trade.Side == "BUY"
                ? RoundToTicks(_trade.BestFavorablePrice - _trade.Entry)
                : RoundToTicks(_trade.Entry - _trade.BestFavorablePrice);

            if (mfeTicks < HalfMfeExitMinMfeTicks)
                return false;

            var halfMfeExit = _trade.Side == "BUY"
                ? _trade.Entry + (_trade.BestFavorablePrice - _trade.Entry) / 2m
                : _trade.Entry - (_trade.Entry - _trade.BestFavorablePrice) / 2m;

            var touched = _trade.Side == "BUY"
                ? candle.Low <= halfMfeExit
                : candle.High >= halfMfeExit;

            if (!touched)
                return false;

            _trade.Result = "EXIT";
            _trade.ExitPrice = halfMfeExit;
            return true;
        }

        private void UpdateTradeExcursion(dynamic candle)
        {
            if (_trade == null)
                return;

            decimal favorableTicks;
            decimal adverseTicks;

            if (_trade.Side == "BUY")
            {
                favorableTicks = RoundToTicks(candle.High - _trade.Entry);
                adverseTicks = RoundToTicks(_trade.Entry - candle.Low);
            }
            else
            {
                favorableTicks = RoundToTicks(_trade.Entry - candle.Low);
                adverseTicks = RoundToTicks(candle.High - _trade.Entry);
            }

            if (favorableTicks > _trade.MfeTicks)
                _trade.MfeTicks = Math.Max(0, favorableTicks);

            if (adverseTicks > _trade.MaeTicks)
                _trade.MaeTicks = Math.Max(0, adverseTicks);
        }

        private ScoreState CalculateLiveScore(dynamic candle, int bar, DateTime nyTime)
        {
            var bullishBreakout = candle.Close > _orHigh;
            var bearishBreakout = candle.Close < _orLow;
            var vwap = GetSessionVwap(bar, nyTime.Date);
            var orRangeTicks = RoundToTicks(_orHigh - _orLow);
            decimal bodyBreakoutTicks = 0;

            if (bullishBreakout)
                bodyBreakoutTicks = RoundToTicks(candle.Close - Math.Max(candle.Open, _orHigh));

            if (bearishBreakout)
                bodyBreakoutTicks = RoundToTicks(Math.Min(candle.Open, _orLow) - candle.Close);

            if (bodyBreakoutTicks < 0)
                bodyBreakoutTicks = 0;

            var speedState = CalculateBreakoutSpeed(candle, bodyBreakoutTicks);

            var state = new ScoreState
            {
                IsBreakout = bullishBreakout || bearishBreakout,
                Side = bullishBreakout ? "BUY" : bearishBreakout ? "SELL" : "",
                EntryPrice = candle.Close,
                OrLow = _orLow,
                OrHigh = _orHigh,
                OrRangeTicks = orRangeTicks,
                Vwap = vwap,
                BodyBreakoutTicks = bodyBreakoutTicks,
                BreakoutSpeed = speedState.TicksPerSecond,
                SpeedElapsedSeconds = speedState.ElapsedSeconds,
                SpeedUsedReplayFallback = speedState.UsedReplayFallback,
                SpeedTimingSource = speedState.TimingSource,
                Volume = candle.Volume,
                Delta = candle.Delta,
                RangeOk = orRangeTicks >= MinOrRangeTicks && orRangeTicks <= MaxOrRangeTicks,
                BodyOk = bodyBreakoutTicks >= MinBodyBreakoutTicks,
                VolumeOk = candle.Volume >= MinVolume,
                DeltaOk = Math.Abs(candle.Delta) >= MinAbsDelta,
                TimeOk = IsSignalWindow(nyTime),
                VwapOk =
                    (bullishBreakout && candle.Close >= vwap) ||
                    (bearishBreakout && candle.Close <= vwap)
            };

            state.SpeedLabel = GetSpeedLabel(state.BreakoutSpeed);
            state.SpeedValid = state.SpeedLabel == "normal speed" || state.SpeedLabel == "A+ speed";

            if (state.VwapOk) state.Score += 2;
            if (state.RangeOk) state.Score += 1;
            if (state.BodyOk) state.Score += 1;
            if (state.VolumeOk) state.Score += 1;
            if (state.DeltaOk) state.Score += 1;
            if (state.SpeedValid) state.Score += 1;

            state.IsReady =
                state.IsBreakout &&
                state.Score >= MinScore &&
                state.SpeedValid &&
                (!RequireBodyOkForTrade || state.BodyOk) &&
                (!RequireVwapOkForTrade || state.VwapOk);

            return state;
        }

        private void UpdateSpeedClock(int bar)
        {
            if (bar == _speedBar)
                return;

            _speedBar = bar;
            _speedBarStartedAtUtc = DateTime.UtcNow;
        }

        private SpeedState CalculateBreakoutSpeed(dynamic candle, decimal bodyBreakoutTicks)
        {
            if (bodyBreakoutTicks <= 0)
                return new SpeedState();

            string timingSource;
            var currentTime = TryGetCandleUpdateTime(candle, out timingSource);
            var startTime = candle.Time;
            var elapsedSeconds = (currentTime - startTime).TotalSeconds;
            var usedReplayFallback = false;

            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
            {
                elapsedSeconds = (DateTime.UtcNow - _speedBarStartedAtUtc).TotalSeconds;
                usedReplayFallback = true;
                timingSource = ReplaySpeedMultiplier > 0
                    ? $"replay-fallback-x{ReplaySpeedMultiplier.ToString("0.##", CultureInfo.InvariantCulture)}"
                    : "replay-fallback";
            }

            if (elapsedSeconds <= 0)
                elapsedSeconds = 1;

            if (usedReplayFallback && ReplaySpeedMultiplier > 0)
                elapsedSeconds *= (double)ReplaySpeedMultiplier;

            return new SpeedState
            {
                TicksPerSecond = bodyBreakoutTicks / (decimal)elapsedSeconds,
                ElapsedSeconds = (decimal)elapsedSeconds,
                UsedReplayFallback = usedReplayFallback,
                TimingSource = timingSource
            };
        }

        private DateTime TryGetCandleUpdateTime(dynamic candle, out string timingSource)
        {
            try { timingSource = "LastTime"; return candle.LastTime; } catch { }
            try { timingSource = "LastTradeTime"; return candle.LastTradeTime; } catch { }
            try { timingSource = "TimeLast"; return candle.TimeLast; } catch { }
            try { timingSource = "CloseTime"; return candle.CloseTime; } catch { }
            try { timingSource = "LastUpdateTime"; return candle.LastUpdateTime; } catch { }

            timingSource = "UtcNow";
            return DateTime.UtcNow;
        }

        private string GetSpeedLabel(decimal speedTicksPerSecond)
        {
            if (speedTicksPerSecond <= MinNormalSpeedTicksPerSecond)
                return "invalid speed";

            if (speedTicksPerSecond <= APlusSpeedTicksPerSecond)
                return "normal speed";

            return "A+ speed";
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
                "Exporter_VERSION,fecha,EntryTime_NY,EntryBar,or_low,or_high,range,VWAP_entry,Body,Volume_entry,Delta_entry,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS,Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK,score total,Side,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label,result TP SL BE,MAE_ticks,MFE_ticks" + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    _trade.EntryDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _trade.EntryTimeNy.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    _trade.EntryBar.ToString(CultureInfo.InvariantCulture),
                    FormatPrice(_trade.OrLow),
                    FormatPrice(_trade.OrHigh),
                    FormatTicks(_trade.OrRangeTicks),
                    FormatPrice(_trade.Vwap),
                    FormatTicks(_trade.BodyBreakoutTicks),
                    FormatTicks(_trade.Volume),
                    FormatTicks(_trade.Delta),
                    _trade.SpeedLabel,
                    FormatTicks(_trade.BreakoutSpeed),
                    FormatSeconds(_trade.SpeedElapsedSeconds),
                    _trade.SpeedUsedReplayFallback ? "TRUE" : "FALSE",
                    _trade.SpeedTimingSource,
                    FormatBool(_trade.RangeOk),
                    FormatBool(_trade.BodyOk),
                    FormatBool(_trade.VolumeOk),
                    FormatBool(_trade.DeltaOk),
                    FormatBool(_trade.TimeOk),
                    FormatBool(_trade.VwapOk),
                    FormatBool(_trade.SpeedValid),
                    _trade.Score.ToString(CultureInfo.InvariantCulture),
                    _trade.Side,
                    GetEntryProfile(_trade.Side, _trade.SpeedLabel),
                    FormatPrice(_trade.Sl),
                    FormatPrice(_trade.Entry),
                    FormatPrice(_trade.Tp),
                    FormatTicks(_trade.SlTicks),
                    FormatTicks(_trade.TpTicks),
                    _trade.Result,
                    FormatSignedTicks(TradeResultTicks()),
                    FormatTicks(_trade.MaeTicks),
                    FormatTicks(_trade.MfeTicks)
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
            _speedBar = -1;
            _speedBarStartedAtUtc = DateTime.MinValue;
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

        private decimal ClampExitDistance(decimal entry, decimal exit, int direction)
        {
            var currentDistance = Math.Abs(exit - entry);
            var minDistance = MinTradeTicks * SetupTickSize;
            var maxDistance = MaxTradeTicks * SetupTickSize;

            if (currentDistance >= minDistance && currentDistance <= maxDistance)
                return exit;

            if (currentDistance < minDistance)
                return entry + direction * minDistance;

            return entry + direction * maxDistance;
        }

        private string GetEntryProfile(string side, string speedLabel)
        {
            if (speedLabel == "normal speed")
                return $"{side}1";

            return side;
        }

        private string FormatPrice(decimal price)
        {
            return price.ToString("0.00", CultureInfo.InvariantCulture);
        }

        private string FormatTicks(decimal ticks)
        {
            return ticks.ToString("0.##", CultureInfo.InvariantCulture);
        }

        private string FormatSeconds(decimal seconds)
        {
            return seconds.ToString("0.####", CultureInfo.InvariantCulture);
        }

        private string FormatBool(bool value)
        {
            return value ? "TRUE" : "FALSE";
        }

        private string FormatSignedTicks(decimal ticks)
        {
            return ticks.ToString("+0.##;-0.##;0", CultureInfo.InvariantCulture);
        }

        private class ScoreState
        {
            public bool IsBreakout { get; set; }
            public bool IsReady { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public decimal OrLow { get; set; }
            public decimal OrHigh { get; set; }
            public decimal OrRangeTicks { get; set; }
            public decimal Vwap { get; set; }
            public decimal BodyBreakoutTicks { get; set; }
            public decimal BreakoutSpeed { get; set; }
            public decimal SpeedElapsedSeconds { get; set; }
            public bool SpeedUsedReplayFallback { get; set; }
            public string SpeedTimingSource { get; set; } = "";
            public string SpeedLabel { get; set; } = "";
            public decimal Volume { get; set; }
            public decimal Delta { get; set; }
            public bool RangeOk { get; set; }
            public bool BodyOk { get; set; }
            public bool VolumeOk { get; set; }
            public bool DeltaOk { get; set; }
            public bool TimeOk { get; set; }
            public bool VwapOk { get; set; }
            public bool SpeedValid { get; set; }
            public int Score { get; set; }
        }

        private class TradeState
        {
            public int EntryBar { get; set; }
            public DateTime EntryDate { get; set; }
            public DateTime EntryTimeNy { get; set; }
            public string Side { get; set; } = "";
            public decimal OrLow { get; set; }
            public decimal OrHigh { get; set; }
            public decimal OrRangeTicks { get; set; }
            public decimal Vwap { get; set; }
            public decimal BodyBreakoutTicks { get; set; }
            public decimal BreakoutSpeed { get; set; }
            public decimal SpeedElapsedSeconds { get; set; }
            public bool SpeedUsedReplayFallback { get; set; }
            public string SpeedTimingSource { get; set; } = "";
            public string SpeedLabel { get; set; } = "";
            public decimal Volume { get; set; }
            public decimal Delta { get; set; }
            public bool RangeOk { get; set; }
            public bool BodyOk { get; set; }
            public bool VolumeOk { get; set; }
            public bool DeltaOk { get; set; }
            public bool TimeOk { get; set; }
            public bool VwapOk { get; set; }
            public bool SpeedValid { get; set; }
            public int Score { get; set; }
            public decimal Entry { get; set; }
            public decimal Sl { get; set; }
            public decimal Tp { get; set; }
            public decimal SlTicks { get; set; }
            public decimal TpTicks { get; set; }
            public decimal ExitPrice { get; set; }
            public decimal BestFavorablePrice { get; set; }
            public string Result { get; set; } = "";
            public decimal MaeTicks { get; set; }
            public decimal MfeTicks { get; set; }
        }

        private class SpeedState
        {
            public decimal TicksPerSecond { get; set; }
            public decimal ElapsedSeconds { get; set; }
            public bool UsedReplayFallback { get; set; }
            public string TimingSource { get; set; } = "";
        }
    }
}
