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

        private readonly string _replayStartedFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\replay_trade_result_started_at.txt";

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private const decimal SetupTickSize = 0.25m;
        private const string ExporterVersion = "score-exporter-2026-05-30-aplus-structure-export";

        private readonly TimeSpan _openingTimeNy = new TimeSpan(9, 30, 0);
        private readonly TimeSpan _signalStartNy = new TimeSpan(9, 31, 0);
        private readonly TimeSpan _signalEndNy = new TimeSpan(9, 38, 0);
        private readonly TimeSpan _normalSpeedAllowedUntilNy = new TimeSpan(9, 33, 59); // time limit
        private const decimal HardMaxTradeTicks = 60m;
        private const decimal APlusStopTicks = 60m;
        private readonly ScoreTradeSignalEngine _signalEngine = new ScoreTradeSignalEngine();

        private DateTime _currentNyDate = DateTime.MinValue;
        private decimal _orHigh;
        private decimal _orLow;
        private int _orBar = -1;
        private bool _orReady;
        private bool _tradeCreated;
        private bool _timeOverWritten;
        private bool _isRecalculating;
        private bool _hasAPlusStructure;
        private string _aPlusStructureSide = "";
        private decimal? _aPlusStructurePrice;
        private int _aPlusStructureCount;

        private bool _hasBuyAPlusStructure;
        private decimal? _buyAPlusStructurePrice;
        private int _buyAPlusStructureCount;

        private bool _hasSellAPlusStructure;
        private decimal? _sellAPlusStructurePrice;
        private int _sellAPlusStructureCount;
        private TradeState? _trade;
        private ScoreTradeSignal? _pendingScore;
        private int _pendingScoreBar = -1;
        private DateTime _pendingScoreNyTime = DateTime.MinValue;
        private ScoreTradeSignal? _bestRejectedScore;
        private int _bestRejectedScoreBar = -1;
        private DateTime _bestRejectedScoreNyTime = DateTime.MinValue;
        private decimal _lastManagePrice;
        private DateTime _lastManageTimeUtc = DateTime.MinValue;

        public int MinScore { get; set; } = 5;
        public decimal MinOrRangeTicks { get; set; } = 40;
        public decimal MaxOrRangeTicks { get; set; } = 350;
        public decimal MinBodyBreakoutTicks { get; set; } = 10;
        public decimal MinVolume { get; set; } = 800;
        public decimal MinAbsDelta { get; set; } = 25;
        public decimal MinNormalSpeedTicksPerSecond { get; set; } = 2;
        public decimal APlusSpeedTicksPerSecond { get; set; } = 5;
        public decimal ReplaySpeedMultiplier { get; set; } = 1;
        public decimal ImbalanceRatio { get; set; } = 3m;
        public decimal ImbalanceCompareMinVolume { get; set; } = 70m;
        public decimal APlusPriceAcceptanceTicks { get; set; } = 20m;
        public decimal MinTradeTicks { get; set; } = 60;
        public decimal MaxTradeTicks { get; set; } = 60;
        public decimal HalfMfeExitMinMfeTicks { get; set; } = 40;
        public decimal FastExitMinMfeTicks { get; set; } = 40;
        public decimal FastExitPullbackTicks { get; set; } = 10;
        public decimal FastExitAdverseSpeedTicksPerSecond { get; set; } = 6;
        public TimeSpan TimeOverTimeNy { get; set; } = new TimeSpan(9, 40, 0);
        public int MinTimeOverRealtimeSeconds { get; set; } = 5;
        public bool RequireBodyOkForTrade { get; set; } = false;
        public bool RequireVwapOkForTrade { get; set; } = false;

        public ATASScoreTradeResultExporter()
        {
            Name = "ATAS Score Trade Result Exporter ENTRY SL TP RESULT";
            EnableCustomDrawing = false;
        }

        protected override void OnRecalculate()
        {
            _isRecalculating = true;
            base.OnRecalculate();
        }

        protected override void OnFinishRecalculate()
        {
            base.OnFinishRecalculate();
            _isRecalculating = false;
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

            UpdateAPlusStructureFromBar(bar, current, currentNyTime);

            var closedBar = bar - 1;
            var closedCandle = GetCandle(closedBar);
            var closedNyTime = ConvertToNewYorkTime(closedCandle.Time);

            UpdateAPlusStructureFromBar(closedBar, closedCandle, closedNyTime);

            if (!_orReady && closedNyTime.TimeOfDay == _openingTimeNy)
            {
                _orHigh = closedCandle.High;
                _orLow = closedCandle.Low;
                _orBar = closedBar;
                _orReady = true;
                return;
            }

            UpdateTradeResult(bar, current);

            if (TryWriteTimeOver(bar, current, currentNyTime))
                return;

            if (!_orReady)
                return;

            if (_tradeCreated || bar <= _orBar || !IsSignalWindow(currentNyTime))
                return;

            var score = CalculateLiveScore(current, bar, currentNyTime);

            if (!score.IsReady)
            {
                TrackRejectedScore(bar, currentNyTime, score);
                return;
            }

            ClearPendingScore();
            CreateTrade(bar, currentNyTime, score);
        }

        private void CreateTrade(int bar, DateTime nyTime, ScoreTradeSignal score)
        {
            if (!ScoreTradeSignalEngine.IsSpeedValidForSignalTime(score.SpeedLabel, nyTime.TimeOfDay, _normalSpeedAllowedUntilNy))
                return;

            var executionSide = string.IsNullOrWhiteSpace(score.ExecutionSide)
                ? score.Side
                : score.ExecutionSide;

            var plan = TradeManagerTpSlBeExit.CreateInitialPlan(new TradeManagerTpSlBeExit.TradePlanRequest
            {
                Side = executionSide,
                SpeedLabel = score.SpeedLabel,
                Entry = score.EntryPrice,
                OrLow = _orLow,
                OrHigh = _orHigh,
                TickSize = SetupTickSize,
                MinTradeTicks = MinTradeTicks,
                MaxTradeTicks = MaxTradeTicks,
                HardMaxTradeTicks = HardMaxTradeTicks,
                APlusStopTicks = APlusStopTicks,
                CapSellStopAtOrHigh = false,
                EnforceMinExitDistance = true
            });

            var hasMatchingAPlusStructure = score.HasAPlusStructure;
            var matchingAPlusSide = score.APlusStructureSide;
            var matchingAPlusPrice = score.APlusStructurePrice;
            var matchingAPlusCount = hasMatchingAPlusStructure ? 4 : 0;

            _trade = new TradeState
            {
                EntryBar = bar,
                EntryDate = nyTime.Date,
                EntryTimeNy = nyTime,
                Side = executionSide,
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
                CumulativeDelta = score.CumulativeDelta,
                CumulativeDeltaSource = score.CumulativeDeltaSource,
                CvdEntry = score.CumulativeDelta,
                CvdPeak = score.CumulativeDelta,
                CvdCurrent = score.CumulativeDelta,
                CvdPullbackPercent = 0,
                CvdPullbackLabel = "Excelente",
                PreviousVolume = score.PreviousVolume,
                PreviousDelta = score.PreviousDelta,
                VolumeIncreasing = score.VolumeIncreasing,
                DeltaChange = score.DeltaChange,
                DeltaWithSide = score.DeltaWithSide,
                PriceAcceptedAfterImbalance = score.PriceAcceptedAfterImbalance,
                RangeOk = score.RangeOk,
                BodyOk = score.BodyOk,
                VolumeOk = score.VolumeOk,
                DeltaOk = score.DeltaOk,
                TimeOk = score.TimeOk,
                VwapOk = score.VwapOk,
                SpeedValid = score.SpeedValid,
                SpeedIgnoredByStructure = score.SpeedIgnoredByStructure,
                Score = score.Score,
                Entry = score.EntryPrice,
                Sl = plan.Sl,
                Tp = plan.Tp,
                SlTicks = plan.SlTicks,
                TpTicks = plan.TpTicks,
                EntryBarHighAtEntry = score.EntryBarHighAtEntry,
                EntryBarLowAtEntry = score.EntryBarLowAtEntry,
                BestFavorablePrice = score.EntryPrice,
                Result = "OPEN",
                APlusStructure = hasMatchingAPlusStructure,
                APlusAbsorption = score.HasAPlusAbsorption,
                APlusSpeed = score.HasAPlusSpeed,
                SignalSource = score.SignalSource,
                ImbalanceGroup3 = matchingAPlusSide,
                ImbalanceGroupPrice = matchingAPlusPrice,
                ImbalanceCount = matchingAPlusCount
            };

            _lastManagePrice = score.EntryPrice;
            _lastManageTimeUtc = DateTime.MinValue;
            _tradeCreated = true;
            WriteTradeFile(nyTime.Date);
        }

        private bool UpdateEntryBarTradeResult(int bar, dynamic candle)
        {
            if (_trade == null || _trade.Result != "OPEN" || bar != _trade.EntryBar)
                return false;

            decimal tradeHigh;
            decimal tradeLow;
            GetPostEntryTradeRange(bar, candle, out tradeHigh, out tradeLow);

            UpdateTradeExcursion(tradeHigh, tradeLow);
            UpdateBestFavorablePrice(tradeHigh, tradeLow);
            UpdateCvdPullback(bar, candle);

            var decision = TradeManagerTpSlBeExit.EvaluateExit(new TradeManagerTpSlBeExit.TradeExitRequest
            {
                Side = _trade.Side,
                SpeedLabel = _trade.SpeedLabel,
                Entry = _trade.Entry,
                Sl = _trade.Sl,
                Tp = _trade.Tp,
                SlTicks = _trade.SlTicks,
                TpTicks = _trade.TpTicks,
                BestFavorablePrice = _trade.BestFavorablePrice,
                CandleHigh = tradeHigh,
                CandleLow = tradeLow,
                CurrentPrice = candle.Close,
                HalfMfeExitMinMfeTicks = HalfMfeExitMinMfeTicks,
                FastExitMinMfeTicks = FastExitMinMfeTicks,
                FastExitPullbackTicks = FastExitPullbackTicks,
                FastExitAdverseSpeedTicksPerSecond = FastExitAdverseSpeedTicksPerSecond,
                AdverseSpeedTicksPerSecond = 0,
                TickSize = SetupTickSize
            });

            if (!decision.IsClosed)
            {
                _lastManagePrice = candle.Close;
                _lastManageTimeUtc = SpeedClasification.TryGetCandleUpdateTime(candle);
                return false;
            }

            _trade.Result = decision.Result;
            _trade.ExitPrice = ResolveExitPrice(decision);
            WriteTradeFile(_currentNyDate);
            return true;
        }

        private void UpdateTradeResult(int bar, dynamic candle)
        {
            if (_trade == null || _trade.Result != "OPEN")
                return;

            if (bar < _trade.EntryBar)
                return;

            string manageTimingSource;
            var manageTimeUtc = SpeedClasification.TryGetCandleUpdateTime(candle, out manageTimingSource);
            decimal tradeHigh;
            decimal tradeLow;
            GetPostEntryTradeRange(bar, candle, out tradeHigh, out tradeLow);

            UpdateTradeExcursion(tradeHigh, tradeLow);
            UpdateBestFavorablePrice(tradeHigh, tradeLow);
            UpdateCvdPullback(bar, candle);

            var adverseSpeed = CalculateAdverseSpeed(candle.Close, manageTimeUtc, manageTimingSource);

            var decision = TradeManagerTpSlBeExit.EvaluateExit(new TradeManagerTpSlBeExit.TradeExitRequest
            {
                Side = _trade.Side,
                SpeedLabel = _trade.SpeedLabel,
                Entry = _trade.Entry,
                Sl = _trade.Sl,
                Tp = _trade.Tp,
                SlTicks = _trade.SlTicks,
                TpTicks = _trade.TpTicks,
                BestFavorablePrice = _trade.BestFavorablePrice,
                CandleHigh = tradeHigh,
                CandleLow = tradeLow,
                CurrentPrice = candle.Close,
                HalfMfeExitMinMfeTicks = HalfMfeExitMinMfeTicks,
                FastExitMinMfeTicks = FastExitMinMfeTicks,
                FastExitPullbackTicks = FastExitPullbackTicks,
                FastExitAdverseSpeedTicksPerSecond = FastExitAdverseSpeedTicksPerSecond,
                AdverseSpeedTicksPerSecond = adverseSpeed,
                TickSize = SetupTickSize
            });

            if (!decision.IsClosed)
            {
                _lastManagePrice = candle.Close;
                _lastManageTimeUtc = manageTimeUtc;
                return;
            }

            _trade.Result = decision.Result;
            _trade.ExitPrice = ResolveExitPrice(decision);
            WriteTradeFile(_currentNyDate);
        }

        private decimal ResolveExitPrice(TradeManagerTpSlBeExit.TradeExitDecision decision)
        {
            if (_trade == null || !decision.IsFastExit)
                return decision.ExitPrice;

            return TradeManagerTpSlBeExit.CalculateHalfMfeExit(
                _trade.Side,
                _trade.Entry,
                _trade.BestFavorablePrice);
        }

        private decimal CalculateAdverseSpeed(decimal currentPrice, DateTime manageTimeUtc, string timingSource)
        {
            if (_trade == null)
                return 0;

            if (_lastManageTimeUtc == DateTime.MinValue)
            {
                _lastManagePrice = currentPrice;
                _lastManageTimeUtc = manageTimeUtc;
                return 0;
            }

            var elapsedSeconds = (manageTimeUtc - _lastManageTimeUtc).TotalSeconds;

            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
                elapsedSeconds = 1;
            else if (timingSource == "UtcNow" || elapsedSeconds < 1)
                elapsedSeconds *= (double)NormalizeReplaySpeedMultiplier();

            var adverseTicks = _trade.Side == "BUY"
                ? RoundToTicks(_lastManagePrice - currentPrice)
                : RoundToTicks(currentPrice - _lastManagePrice);

            if (adverseTicks <= 0)
                return 0;

            return adverseTicks / (decimal)elapsedSeconds;
        }

        private decimal TradeResultTicks()
        {
            if (_trade == null)
                return 0;

            return TradeManagerTpSlBeExit.TradeResultTicks(
                _trade.Result,
                _trade.Entry,
                _trade.TpTicks,
                _trade.SlTicks,
                _trade.ExitPrice,
                SetupTickSize);
        }

        private bool TryWriteTimeOver(int bar, dynamic candle, DateTime nyTime)
        {
            var hasOpenTrade = _trade != null && _trade.Result == "OPEN";

            if (_timeOverWritten ||
                _isRecalculating ||
                !HasReplayStartDelayElapsed() ||
                _tradeCreated ||
                hasOpenTrade ||
                nyTime.TimeOfDay < TimeOverTimeNy)
            {
                return false;
            }

            _timeOverWritten = true;
            WriteTimeOverFile(nyTime.Date, nyTime);
            return true;
        }

        private bool HasReplayStartDelayElapsed()
        {
            if (!File.Exists(_replayStartedFile))
                return true;

            try
            {
                var startedAt = File.GetLastWriteTime(_replayStartedFile);
                return DateTime.Now - startedAt >= TimeSpan.FromSeconds(MinTimeOverRealtimeSeconds);
            }
            catch
            {
                return false;
            }
        }

        private void UpdateBestFavorablePrice(decimal high, decimal low)
        {
            if (_trade == null)
                return;

            if (_trade.Side == "BUY")
            {
                if (high > _trade.BestFavorablePrice)
                    _trade.BestFavorablePrice = high;
            }
            else
            {
                if (_trade.BestFavorablePrice == 0 || low < _trade.BestFavorablePrice)
                    _trade.BestFavorablePrice = low;
            }
        }

        private void UpdateCvdPullback(int bar, dynamic candle)
        {
            if (_trade == null)
                return;

            var currentCvd = CumulativeDeltaDetector.Detect(
                bar,
                candle,
                new Func<int, dynamic>(GetCandle),
                _currentNyDate,
                new Func<dynamic, DateTime>(c => ConvertToNewYorkTime(c.Time)));

            _trade.CumulativeDelta = currentCvd.Value;
            _trade.CumulativeDeltaSource = currentCvd.Source;

            var pullback = CumulativeDeltaDetector.CalculatePullback(
                _trade.Side,
                _trade.CvdEntry,
                currentCvd.Value,
                _trade.CvdPeak);

            _trade.CvdPeak = pullback.PeakCvd;
            _trade.CvdCurrent = pullback.CurrentCvd;
            _trade.CvdPullbackPercent = pullback.PullbackPercent;
            _trade.CvdPullbackLabel = pullback.PullbackLabel;
        }

        private void UpdateTradeExcursion(decimal high, decimal low)
        {
            if (_trade == null)
                return;

            decimal favorableTicks;
            decimal adverseTicks;

            if (_trade.Side == "BUY")
            {
                favorableTicks = RoundToTicks(high - _trade.Entry);
                adverseTicks = RoundToTicks(_trade.Entry - low);
            }
            else
            {
                favorableTicks = RoundToTicks(_trade.Entry - low);
                adverseTicks = RoundToTicks(high - _trade.Entry);
            }

            if (favorableTicks > _trade.MfeTicks)
                _trade.MfeTicks = Math.Max(0, favorableTicks);

            if (adverseTicks > _trade.MaeTicks)
                _trade.MaeTicks = Math.Max(0, adverseTicks);
        }

        private void GetPostEntryTradeRange(int bar, dynamic candle, out decimal tradeHigh, out decimal tradeLow)
        {
            if (_trade == null || bar != _trade.EntryBar)
            {
                tradeHigh = candle.High;
                tradeLow = candle.Low;
                return;
            }

            tradeHigh = candle.Close;
            tradeLow = candle.Close;

            if (candle.High > _trade.EntryBarHighAtEntry)
                tradeHigh = candle.High;

            if (candle.Low < _trade.EntryBarLowAtEntry)
                tradeLow = candle.Low;
        }

        private ScoreTradeSignal CalculateLiveScore(dynamic candle, int bar, DateTime nyTime)
        {
            return _signalEngine.Calculate(bar, candle, new Func<int, dynamic>(GetCandle), new ScoreTradeSignalRequest
            {
                OrLow = _orLow,
                OrHigh = _orHigh,
                CurrentTime = nyTime,
                SessionDate = nyTime.Date,
                GetSessionTime = c => ConvertToNewYorkTime(c.Time),
                SignalStartTime = _signalStartNy,
                SignalEndTime = _signalEndNy,
                NormalSpeedAllowedUntilTime = _normalSpeedAllowedUntilNy,
                TickSize = SetupTickSize,
                MinScore = MinScore,
                MinOrRangeTicks = MinOrRangeTicks,
                MaxOrRangeTicks = MaxOrRangeTicks,
                MinBodyBreakoutTicks = MinBodyBreakoutTicks,
                MinVolume = MinVolume,
                MinAbsDelta = MinAbsDelta,
                MinNormalSpeedTicksPerSecond = MinNormalSpeedTicksPerSecond,
                APlusSpeedTicksPerSecond = APlusSpeedTicksPerSecond,
                ReplaySpeedMultiplier = ReplaySpeedMultiplier,
                ImbalanceRatio = ImbalanceRatio,
                ImbalanceCompareMinVolume = ImbalanceCompareMinVolume,
                APlusPriceAcceptanceTicks = APlusPriceAcceptanceTicks,
                RequireBodyOkForTrade = RequireBodyOkForTrade,
                RequireVwapOkForTrade = RequireVwapOkForTrade
            });
        }

        private void UpdateSpeedClock(int bar)
        {
            _signalEngine.UpdateSpeedClock(bar);
        }

        private DateTime TryGetCandleUpdateTime(dynamic candle, out string timingSource)
        {
            return SpeedClasification.TryGetCandleUpdateTime(candle, out timingSource);
        }

        private decimal NormalizeReplaySpeedMultiplier()
        {
            return ReplaySpeedMultiplier <= 0 ? 1 : ReplaySpeedMultiplier;
        }

        private bool IsSignalWindow(DateTime nyTime)
        {
            var time = nyTime.TimeOfDay;

            return time >= _signalStartNy &&
                   time <= _signalEndNy;
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
                "Exporter_VERSION,fecha,EntryTime_NY,EntryBar,or_low,or_high,range,VWAP_entry,Body,Volume_entry,Delta_entry,Cumulative_Delta_entry,Cumulative_Delta_Source,Cvd_Peak,Cvd_Current,Cvd_Pullback_Pct,Cvd_Pullback_Label,Previous_Volume,Previous_Delta,Volume_Increasing,Delta_Change,Delta_With_Side,Price_Accepted_After_Imbalance,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS,Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK,score total,Side,Signal_Source,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label,Exit_price,result TP SL BE,MAE_ticks,MFE_ticks,APlus_Structure,APlus_Absorption,APlus_Speed,Imbalance_Group_3,Imbalance_Group_Price,Imbalance_Count,Speed_Ignored_By_Structure" + Environment.NewLine +
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
                    FormatTicks(_trade.CumulativeDelta),
                    _trade.CumulativeDeltaSource,
                    FormatTicks(_trade.CvdPeak),
                    FormatTicks(_trade.CvdCurrent),
                    FormatTicks(_trade.CvdPullbackPercent),
                    _trade.CvdPullbackLabel,
                    FormatTicks(_trade.PreviousVolume),
                    FormatTicks(_trade.PreviousDelta),
                    FormatBool(_trade.VolumeIncreasing),
                    FormatTicks(_trade.DeltaChange),
                    FormatBool(_trade.DeltaWithSide),
                    FormatBool(_trade.PriceAcceptedAfterImbalance),
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
                    _trade.SignalSource,
                    GetEntryProfile(_trade.Side, _trade.SpeedLabel),
                    FormatPrice(_trade.Sl),
                    FormatPrice(_trade.Entry),
                    FormatPrice(_trade.Tp),
                    FormatTicks(_trade.SlTicks),
                    FormatTicks(_trade.TpTicks),
                    _trade.Result,
                    FormatExitPrice(),
                    FormatSignedTicks(TradeResultTicks()),
                    FormatTicks(_trade.MaeTicks),
                    FormatTicks(_trade.MfeTicks),
                    FormatBool(_trade.APlusStructure),
                    FormatBool(_trade.APlusAbsorption),
                    FormatBool(_trade.APlusSpeed),
                    _trade.ImbalanceGroup3,
                    FormatNullablePrice(_trade.ImbalanceGroupPrice),
                    _trade.ImbalanceCount.ToString(CultureInfo.InvariantCulture),
                    FormatBool(_trade.SpeedIgnoredByStructure)
                ) + Environment.NewLine
            );
        }

        private void WriteTimeOverFile(DateTime nyDate, DateTime nyTime)
        {
            if (_bestRejectedScore != null)
            {
                WriteRejectedScoreFile(nyDate);
                return;
            }

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var filePath = Path.Combine(
                _exportFolder,
                $"score_trade_result_{nyDate:yyyy-MM-dd}_NY.csv"
            );

            File.WriteAllText(
                filePath,
                "Exporter_VERSION,fecha,EntryTime_NY,EntryBar,or_low,or_high,range,VWAP_entry,Body,Volume_entry,Delta_entry,Cumulative_Delta_entry,Cumulative_Delta_Source,Cvd_Peak,Cvd_Current,Cvd_Pullback_Pct,Cvd_Pullback_Label,Previous_Volume,Previous_Delta,Volume_Increasing,Delta_Change,Delta_With_Side,Price_Accepted_After_Imbalance,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS,Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK,score total,Side,Signal_Source,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label,Exit_price,result TP SL BE,MAE_ticks,MFE_ticks,APlus_Structure,APlus_Absorption,APlus_Speed,Imbalance_Group_3,Imbalance_Group_Price,Imbalance_Count,Speed_Ignored_By_Structure" + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    nyTime.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    "", // EntryBar
                    FormatPrice(_orLow),
                    FormatPrice(_orHigh),
                    FormatTicks(RoundToTicks(_orHigh - _orLow)),
                    "", // VWAP_entry
                    "", // Body
                    "", // Volume_entry
                    "", // Delta_entry
                    "", // Cumulative_Delta_entry
                    "", // Cumulative_Delta_Source
                    "", // Cvd_Peak
                    "", // Cvd_Current
                    "", // Cvd_Pullback_Pct
                    "", // Cvd_Pullback_Label
                    "", // Previous_Volume
                    "", // Previous_Delta
                    "", // Volume_Increasing
                    "", // Delta_Change
                    "", // Delta_With_Side
                    "", // Price_Accepted_After_Imbalance
                    "", // BreakOut_SPEED
                    "", // BreakOut_TICKS_PER_SEC
                    "", // Speed_Elapsed_SECONDS
                    "", // Speed_Replay_Fallback
                    "", // Speed_Timing_Source
                    "", // Range_OK
                    "", // Body_OK
                    "", // Volume_OK
                    "", // Delta_OK
                    "TRUE",
                    "", // VWAP_OK
                    "", // Speed_OK
                    "", // score total
                    "", // Side
                    "TIME_OVER",
                    "", // Speed_Profile
                    "", // SL_price
                    "", // Entry_price
                    "", // TP_price
                    "", // SL_ticks
                    "", // TP_ticks
                    "TIME_OVER",
                    "", // Exit_price
                    "TIME_OVER",
                    "", // MAE_ticks
                    "", // MFE_ticks
                    FormatBool(_hasAPlusStructure),
                    "FALSE",
                    "FALSE",
                    _aPlusStructureSide,
                    FormatNullablePrice(_aPlusStructurePrice),
                    _aPlusStructureCount.ToString(CultureInfo.InvariantCulture),
                    "FALSE"
                ) + Environment.NewLine
            );
        }

        private void TrackRejectedScore(int bar, DateTime nyTime, ScoreTradeSignal score)
        {
            if (!score.IsBreakout || string.IsNullOrWhiteSpace(score.Side))
                return;

            if (_bestRejectedScore != null &&
                score.Score < _bestRejectedScore.Score)
            {
                return;
            }

            _bestRejectedScore = score;
            _bestRejectedScoreBar = bar;
            _bestRejectedScoreNyTime = nyTime;
            WriteRejectedScoreFile(nyTime.Date);
        }

        private void WriteRejectedScoreFile(DateTime nyDate)
        {
            if (_bestRejectedScore == null)
                return;

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var score = _bestRejectedScore;
            var filePath = Path.Combine(
                _exportFolder,
                $"score_trade_result_{nyDate:yyyy-MM-dd}_NY.csv"
            );

            File.WriteAllText(
                filePath,
                "Exporter_VERSION,fecha,EntryTime_NY,EntryBar,or_low,or_high,range,VWAP_entry,Body,Volume_entry,Delta_entry,Cumulative_Delta_entry,Cumulative_Delta_Source,Cvd_Peak,Cvd_Current,Cvd_Pullback_Pct,Cvd_Pullback_Label,Previous_Volume,Previous_Delta,Volume_Increasing,Delta_Change,Delta_With_Side,Price_Accepted_After_Imbalance,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS,Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK,score total,Side,Signal_Source,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label,Exit_price,result TP SL BE,MAE_ticks,MFE_ticks,APlus_Structure,APlus_Absorption,APlus_Speed,Imbalance_Group_3,Imbalance_Group_Price,Imbalance_Count,Speed_Ignored_By_Structure" + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _bestRejectedScoreNyTime.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    _bestRejectedScoreBar.ToString(CultureInfo.InvariantCulture),
                    FormatPrice(score.OrLow),
                    FormatPrice(score.OrHigh),
                    FormatTicks(score.OrRangeTicks),
                    FormatPrice(score.Vwap),
                    FormatTicks(score.BodyBreakoutTicks),
                    FormatTicks(score.Volume),
                    FormatTicks(score.Delta),
                    FormatTicks(score.CumulativeDelta),
                    score.CumulativeDeltaSource,
                    FormatTicks(score.CumulativeDelta),
                    FormatTicks(score.CumulativeDelta),
                    "0",
                    "Excelente",
                    FormatTicks(score.PreviousVolume),
                    FormatTicks(score.PreviousDelta),
                    FormatBool(score.VolumeIncreasing),
                    FormatTicks(score.DeltaChange),
                    FormatBool(score.DeltaWithSide),
                    FormatBool(score.PriceAcceptedAfterImbalance),
                    score.SpeedLabel,
                    FormatTicks(score.BreakoutSpeed),
                    FormatSeconds(score.SpeedElapsedSeconds),
                    score.SpeedUsedReplayFallback ? "TRUE" : "FALSE",
                    score.SpeedTimingSource,
                    FormatBool(score.RangeOk),
                    FormatBool(score.BodyOk),
                    FormatBool(score.VolumeOk),
                    FormatBool(score.DeltaOk),
                    FormatBool(score.TimeOk),
                    FormatBool(score.VwapOk),
                    FormatBool(score.SpeedValid),
                    score.Score.ToString(CultureInfo.InvariantCulture),
                    score.Side,
                    score.SignalSource,
                    GetEntryProfile(score.Side, score.SpeedLabel),
                    "",
                    FormatPrice(score.EntryPrice),
                    "",
                    "",
                    "",
                    "NO_PROFILE",
                    "",
                    "NO_PROFILE",
                    "",
                    "",
                    FormatBool(score.HasAPlusStructure),
                    FormatBool(score.HasAPlusAbsorption),
                    FormatBool(score.HasAPlusSpeed),
                    score.APlusStructureSide,
                    FormatNullablePrice(score.APlusStructurePrice),
                    (score.HasAPlusStructure ? 4 : 0).ToString(CultureInfo.InvariantCulture),
                    FormatBool(score.SpeedIgnoredByStructure)
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
            _timeOverWritten = false;
            _signalEngine.ResetDay();
            _hasAPlusStructure = false;
            _aPlusStructureSide = "";
            _aPlusStructurePrice = null;
            _aPlusStructureCount = 0;
            _hasBuyAPlusStructure = false;
            _buyAPlusStructurePrice = null;
            _buyAPlusStructureCount = 0;
            _hasSellAPlusStructure = false;
            _sellAPlusStructurePrice = null;
            _sellAPlusStructureCount = 0;
            _trade = null;
            _lastManagePrice = 0;
            _lastManageTimeUtc = DateTime.MinValue;
            ClearPendingScore();
            ClearRejectedScore();
        }

        private void ClearPendingScore()
        {
            _pendingScore = null;
            _pendingScoreBar = -1;
            _pendingScoreNyTime = DateTime.MinValue;
        }

        private void ClearRejectedScore()
        {
            _bestRejectedScore = null;
            _bestRejectedScoreBar = -1;
            _bestRejectedScoreNyTime = DateTime.MinValue;
        }

        private void UpdateAPlusStructureFromBar(int bar, dynamic candle, DateTime nyTime)
        {
            if (!_orReady || bar <= _orBar)
                return;

            if (_hasBuyAPlusStructure && _hasSellAPlusStructure)
                return;

            if (nyTime.TimeOfDay < _signalStartNy || nyTime.TimeOfDay > TimeOverTimeNy)
                return;

            var state = ImbalanceDetector.Detect(candle, new ImbalanceDetectorRequest
            {
                Side = "",
                Ratio = ImbalanceRatio,
                CompareMinVolume = ImbalanceCompareMinVolume
            });

            if (state.HasBuy3_ImbalanceGroup && !_hasBuyAPlusStructure)
            {
                _hasBuyAPlusStructure = true;
                _buyAPlusStructurePrice = state.Buy3_ImbalanceGroupPrice;
                _buyAPlusStructureCount = 4;
            }

            if (state.HasSell3_ImbalanceGroup && !_hasSellAPlusStructure)
            {
                _hasSellAPlusStructure = true;
                _sellAPlusStructurePrice = state.Sell3_ImbalanceGroupPrice;
                _sellAPlusStructureCount = 4;
            }

            SyncAnyAPlusStructure();
        }

        private void GetAPlusStructureForSide(string side, out bool hasStructure, out string structureSide, out decimal? price, out int count)
        {
            var normalizedSide = (side ?? "").Trim().ToUpperInvariant();

            if (normalizedSide == "BUY" && _hasBuyAPlusStructure)
            {
                hasStructure = true;
                structureSide = "BUY";
                price = _buyAPlusStructurePrice;
                count = _buyAPlusStructureCount;
                return;
            }

            if (normalizedSide == "SELL" && _hasSellAPlusStructure)
            {
                hasStructure = true;
                structureSide = "SELL";
                price = _sellAPlusStructurePrice;
                count = _sellAPlusStructureCount;
                return;
            }

            hasStructure = false;
            structureSide = "";
            price = null;
            count = 0;
        }

        private void SyncAnyAPlusStructure()
        {
            if (_hasBuyAPlusStructure)
            {
                _hasAPlusStructure = true;
                _aPlusStructureSide = "BUY";
                _aPlusStructurePrice = _buyAPlusStructurePrice;
                _aPlusStructureCount = _buyAPlusStructureCount;
                return;
            }

            if (_hasSellAPlusStructure)
            {
                _hasAPlusStructure = true;
                _aPlusStructureSide = "SELL";
                _aPlusStructurePrice = _sellAPlusStructurePrice;
                _aPlusStructureCount = _sellAPlusStructureCount;
                return;
            }

            _hasAPlusStructure = false;
            _aPlusStructureSide = "";
            _aPlusStructurePrice = null;
            _aPlusStructureCount = 0;
        }

        private void CreatePendingScoreIfExpired(int bar, dynamic candle)
        {
            if (_tradeCreated || _pendingScore == null || bar <= _pendingScoreBar)
                return;

            var entryBar = _pendingScoreBar;
            var entryCandle = GetCandle(entryBar);

            CreateTrade(entryBar, _pendingScoreNyTime, _pendingScore);
            ClearPendingScore();

            if (UpdateEntryBarTradeResult(entryBar, entryCandle))
                return;

            UpdateTradeResult(bar, candle);
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
            return TradeManagerTpSlBeExit.GetEntryProfile(side, speedLabel);
        }

        private string FormatPrice(decimal price)
        {
            return price.ToString("0.00", CultureInfo.InvariantCulture);
        }

        private string FormatNullablePrice(decimal? price)
        {
            return price.HasValue
                ? price.Value.ToString("0.00", CultureInfo.InvariantCulture)
                : "";
        }

        private string FormatExitPrice()
        {
            if (_trade == null || _trade.Result == "OPEN" || _trade.Result == "NO_TRADE" || _trade.ExitPrice == 0)
                return "";

            return FormatPrice(_trade.ExitPrice);
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
            public decimal CumulativeDelta { get; set; }
            public string CumulativeDeltaSource { get; set; } = "";
            public decimal CvdEntry { get; set; }
            public decimal CvdPeak { get; set; }
            public decimal CvdCurrent { get; set; }
            public decimal CvdPullbackPercent { get; set; }
            public string CvdPullbackLabel { get; set; } = "";
            public decimal PreviousVolume { get; set; }
            public decimal PreviousDelta { get; set; }
            public bool VolumeIncreasing { get; set; }
            public decimal DeltaChange { get; set; }
            public bool DeltaWithSide { get; set; }
            public bool PriceAcceptedAfterImbalance { get; set; }
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
            public decimal EntryBarHighAtEntry { get; set; }
            public decimal EntryBarLowAtEntry { get; set; }
            public decimal BestFavorablePrice { get; set; }
            public string Result { get; set; } = "";
            public decimal MaeTicks { get; set; }
            public decimal MfeTicks { get; set; }
            public bool APlusStructure { get; set; }
            public bool APlusAbsorption { get; set; }
            public bool APlusSpeed { get; set; }
            public string SignalSource { get; set; } = "";
            public string ImbalanceGroup3 { get; set; } = "";
            public decimal? ImbalanceGroupPrice { get; set; }
            public int ImbalanceCount { get; set; }
            public bool SpeedIgnoredByStructure { get; set; }
        }

    }
}
