using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using ATAS.DataFeedsCore;
using ATAS.Strategies.Chart;
using System.Globalization;
using System.IO;
using ATAS.Indicators;

namespace ATAS.Indicators
{
    public class EwOpeningRangeExecutionStrategy : ChartStrategy
    {
        private static readonly HttpClient TelegramHttpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(10)
        };

        private Task _lastTelegramSendTask = Task.CompletedTask;

        private readonly string _exportFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";

        private readonly string _targetDateFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\target_trade_result_date.txt";

        private readonly string _replayStartedFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\replay_trade_result_started_at.txt";

        private readonly string _telegramCredentialsFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\telegram_credentials.txt";

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private const decimal SetupTickSize = 0.25m;
        private const decimal ValueAcceptanceMinTradeTicks = 30m;
        private const decimal NormalScalpMaxTradeTicks = 120m;
        private const string ExporterVersion = "ew-strategy-2026-06-13-v4-recover-signal-time-sl";

        private readonly TimeSpan _openingTimeNy = new TimeSpan(9, 30, 0);
        private readonly TimeSpan _signalStartNy = new TimeSpan(9, 30, 0);
        private readonly TimeSpan _signalEndNy = new TimeSpan(9, 40, 0);
        private readonly TimeSpan _normalSpeedAllowedUntilNy = new TimeSpan(9, 33, 59); // time limit
        private const decimal HardMaxTradeTicks = 60m;
        private const decimal APlusStopTicks = 60m;
        private readonly ScoreTradeSignalEngine _signalEngine = new ScoreTradeSignalEngine();
        private readonly CancellationTokenSource _autoStartCancellation = new CancellationTokenSource();

        private DateTime _currentNyDate = DateTime.MinValue;
        private DateTime _lastAutoStartNyDate = DateTime.MinValue;
        private DateTime _lastReplayAutoStartMarkerUtc = DateTime.MinValue;
        private DateTime _autoStartRetryUntilUtc = DateTime.MinValue;
        private DateTime _lastAutoStartAttemptUtc = DateTime.MinValue;
        private bool _terminalAutoStopRequested;
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
        private bool _cvdFilterSkippedDay;
        private ScoreTradeSignal? _bestRejectedScore;
        private int _bestRejectedScoreBar = -1;
        private DateTime _bestRejectedScoreNyTime = DateTime.MinValue;
        private decimal _lastManagePrice;
        private DateTime _lastManageTimeUtc = DateTime.MinValue;
        private int _lastSignalReadyBar = -1;

        public int MinScore { get; set; } = 5;
        public decimal MinOrRangeTicks { get; set; } = 40;
        public decimal MaxOrRangeTicks { get; set; } = 350;
        public decimal MinBodyBreakoutTicks { get; set; } = 10;
        public decimal MinVolume { get; set; } = 800;
        public decimal MinAbsDelta { get; set; } = 25;
        public decimal MinNormalSpeedTicksPerSecond { get; set; } = 2;
        public decimal APlusSpeedTicksPerSecond { get; set; } = 5;
        public decimal ReplaySpeedMultiplier { get; set; } = 10;
        public decimal ImbalanceRatio { get; set; } = 3m;
        public decimal ImbalanceCompareMinVolume { get; set; } = 70m;
        public decimal APlusPriceAcceptanceTicks { get; set; } = 20m;
        public decimal MinTradeTicks { get; set; } = 60;
        public decimal MaxTradeTicks { get; set; } = 60;
        public decimal HalfMfeExitMinMfeTicks { get; set; } = 40;
        public decimal FastExitMinMfeTicks { get; set; } = 40;
        public decimal FastExitPullbackTicks { get; set; } = 10;
        public decimal CvdProfitLockPullbackTicks { get; set; } = 10;

        /// <summary>
        /// Si esta activo, la gestion de riesgo por CVD (risk bracket, profit lock
        /// y salida por riesgo) tambien aplica a trades "normal speed".
        /// Por defecto OFF: primero hay que medir con la instrumentacion
        /// CvdRisk_First_* antes de cambiar el comportamiento del sistema.
        /// </summary>
        public bool EnableCvdRiskManagementForNormalSpeed { get; set; } = false;

        /// <summary>
        /// MODO FILTRO: si esta activo, solo se toma el trade del dia cuando
        /// Cvd_Pullback_Pct_AtEntry >= CvdAtEntryThreshold (entrada contrarian:
        /// CVD cerca del extremo opuesto a la direccion del trade). Si la senal
        /// del dia no califica, el dia se omite (igual que en la validacion
        /// historica). Backtest 2025-2026: n=50, WR 84%, PF 4.64, maxDD 120 ticks.
        /// </summary>
        public bool EnableCvdAtEntryFilter { get; set; } = true;

        /// <summary>
        /// Umbral del pullback at-entry para el filtro y el sizing. Usar los
        /// cortes naturales de etiqueta (0.75 = "Riesgo de reversion").
        /// No optimizar al decimal: eso seria sobreajuste.
        /// </summary>
        public decimal CvdAtEntryThreshold { get; set; } = 0.75m;

        /// <summary>
        /// MODO SIZING: contratos cuando la senal califica (pct >= umbral).
        /// 1 = desactivado. La columna Trade_Contracts registra el tamano.
        /// El PnL del CSV sigue siendo por contrato; el tamano se pondera
        /// en el analisis.
        /// </summary>
        public int CvdAtEntrySizeMultiplier { get; set; } = 1;

        // ===================== EJECUCION REAL =====================
        /// <summary>
        /// Interruptor maestro. En OFF la estrategia solo simula (CSV +
        /// Telegram) sin colocar ordenes. Enciendelo SOLO en cuenta demo
        /// hasta completar el protocolo de validacion.
        /// </summary>
        public bool EnableExecution { get; set; } = false;

        /// <summary>Contratos base por operacion.</summary>
        public int Contracts { get; set; } = 1;

        // ===================== TELEGRAM =====================
        public bool EnableTelegramAlerts { get; set; } = true;
        public string TelegramBotToken { get; set; } = "";
        public string TelegramChatId { get; set; } = "";
        public bool EnableAutoStartAtOpening { get; set; } = true;
        public bool EnableAutoStartOnReplayMarker { get; set; } = true;
        public TimeSpan AutoStartTimeNy { get; set; } = new TimeSpan(9, 30, 0);
        public int AutoStartCheckIntervalSeconds { get; set; } = 1;
        public int AutoStartRetrySeconds { get; set; } = 60;
        public int AutoStartAttemptIntervalSeconds { get; set; } = 2;
        public bool EnableAutoStopAfterTerminalResult { get; set; } = true;
        public decimal FastExitAdverseSpeedTicksPerSecond { get; set; } = 6;
        public TimeSpan TimeOverTimeNy { get; set; } = new TimeSpan(9, 40, 0);
        public int MinTimeOverRealtimeSeconds { get; set; } = 5;
        public bool RequireBodyOkForTrade { get; set; } = false;
        public bool RequireVwapOkForTrade { get; set; } = false;

        public EwOpeningRangeExecutionStrategy()
        {
            Name = "EW OpeningRange Execution Strategy";
            EnableCustomDrawing = false;
            StartAutoStartWatcher();
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

        protected override void OnDispose()
        {
            _autoStartCancellation.Cancel();
            _autoStartCancellation.Dispose();
            base.OnDispose();
        }

        private void StartAutoStartWatcher()
        {
            Task.Run(() => AutoStartAtOpeningLoopAsync(_autoStartCancellation.Token));
        }

        private async Task AutoStartAtOpeningLoopAsync(CancellationToken cancellationToken)
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    if (EnableAutoStartAtOpening)
                    {
                        var nowUtc = DateTime.UtcNow;
                        var nowNy = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, _nyZone);

                        if (nowNy.TimeOfDay >= AutoStartTimeNy && _lastAutoStartNyDate != nowNy.Date)
                        {
                            _lastAutoStartNyDate = nowNy.Date;
                            BeginAutoStartRetryWindow(nowUtc, $"hora NY {nowNy:yyyy-MM-dd HH:mm:ss}");
                        }

                        if (EnableAutoStartOnReplayMarker)
                            TryBeginReplayMarkerAutoStart(nowUtc);

                        if (nowUtc <= _autoStartRetryUntilUtc &&
                            (nowUtc - _lastAutoStartAttemptUtc).TotalSeconds >= Math.Max(1, AutoStartAttemptIntervalSeconds))
                        {
                            _lastAutoStartAttemptUtc = nowUtc;
                            System.Diagnostics.Debug.WriteLine($"EW Strategy: intentando StartAsync auto-start a las {nowUtc:yyyy-MM-dd HH:mm:ss} UTC.");
                            await StartAsync().ConfigureAwait(false);
                        }
                    }

                    var interval = Math.Max(1, AutoStartCheckIntervalSeconds);
                    await Task.Delay(TimeSpan.FromSeconds(interval), cancellationToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    return;
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"EW Strategy: error en auto-start: {ex.Message}");
                    await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken).ConfigureAwait(false);
                }
            }
        }

        private void BeginAutoStartRetryWindow(DateTime nowUtc, string reason)
        {
            var retrySeconds = Math.Max(1, AutoStartRetrySeconds);
            var retryUntil = nowUtc.AddSeconds(retrySeconds);

            if (retryUntil > _autoStartRetryUntilUtc)
                _autoStartRetryUntilUtc = retryUntil;

            System.Diagnostics.Debug.WriteLine($"EW Strategy: auto-start activado por {reason}; reintentando hasta {_autoStartRetryUntilUtc:yyyy-MM-dd HH:mm:ss} UTC.");
        }

        private void TryBeginReplayMarkerAutoStart(DateTime nowUtc)
        {
            if (!File.Exists(_replayStartedFile))
                return;

            DateTime markerUtc;

            try
            {
                markerUtc = File.GetLastWriteTimeUtc(_replayStartedFile);
            }
            catch
            {
                return;
            }

            if (markerUtc == DateTime.MinValue || markerUtc == _lastReplayAutoStartMarkerUtc)
                return;

            if ((nowUtc - markerUtc).TotalMinutes > 5)
                return;

            _lastReplayAutoStartMarkerUtc = markerUtc;
            BeginAutoStartRetryWindow(nowUtc, $"marcador de replay {_replayStartedFile}");
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 2)
                return;

            var current = GetCandle(bar);
            var currentNyTime = ConvertToNewYorkTime(current.Time);
            var currentSignalNyTime = ResolveSignalNewYorkTime(current);
            var closedBar = bar - 1;
            var closedCandle = GetCandle(closedBar);
            var closedNyTime = ConvertToNewYorkTime(closedCandle.Time);
            // En replay, el runner escribe la fecha objetivo en un archivo.
            // En vivo ese archivo no existe: se opera la sesion actual.
            var targetDate = ReadTargetDate() ?? currentNyTime.Date;

            if (currentNyTime.Date != _currentNyDate)
                ResetDay(currentNyTime.Date);

            if (currentNyTime.Date != targetDate.Date)
                return;

            UpdateTradeResult(bar, current);

            if (TryWriteTimeOver(bar, current, currentNyTime))
                return;

            UpdateSpeedClock(bar);

            UpdateAPlusStructureFromBar(closedBar, closedCandle, closedNyTime);

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

            if (_tradeCreated || _cvdFilterSkippedDay || bar <= _orBar || !IsSignalWindow(currentNyTime))
                return;

            UpdateAPlusStructureFromBar(bar, current, currentNyTime);

            var score = CalculateLiveScore(current, bar, currentNyTime);

            if (!score.IsReady)
            {
                TrackRejectedScore(bar, currentSignalNyTime, score);
                return;
            }

            if (bar <= _lastSignalReadyBar)
                return;

            if (!PassesCvdAtEntryFilter(score))
            {
                _cvdFilterSkippedDay = true;
                TrackRejectedScore(bar, currentSignalNyTime, score);
                return;
            }

            _lastSignalReadyBar = bar;
            ClearPendingScore();
            CreateTrade(bar, current, currentSignalNyTime, score);
            UpdateEntryBarTradeResult(bar, current);
        }

        private void CreateTrade(int bar, dynamic candle, DateTime nyTime, ScoreTradeSignal score)
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
                NormalSpeedMaxTradeTicks = NormalScalpMaxTradeTicks,
                ValueAcceptanceMinTradeTicks = ValueAcceptanceMinTradeTicks,
                NormalSpeedImbalanceStopPrice = score.BreakoutSideImbalanceStopPrice,
                ValueAcceptanceStopPrice = score.ValueAcceptanceStopPrice,
                CapSellStopAtOrHigh = false,
                EnforceMinExitDistance = true
            });

            if (!plan.IsValid)
                return;

            if (!plan.IsNormalSpeed)
                ApplyDynamicImbalanceStop(candle, executionSide, plan);

            var hasMatchingAPlusStructure = score.HasAPlusStructure;
            var matchingAPlusSide = score.APlusStructureSide;
            var matchingAPlusPrice = score.APlusStructurePrice;
            var matchingAPlusCount = hasMatchingAPlusStructure ? 3 : 0;

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
                ImbalanceCount = matchingAPlusCount,
                CvdSessionMaxAtEntry = score.CvdSessionMaxAtEntry,
                CvdSessionMinAtEntry = score.CvdSessionMinAtEntry,
                CvdPullbackPctAtEntry = score.CvdPullbackPctAtEntry,
                CvdPullbackLabelAtEntry = score.CvdPullbackLabelAtEntry,
                CvdSlope3AtEntry = score.CvdSlope3AtEntry,
                BarsSinceCvdExtremeAtEntry = score.BarsSinceCvdExtremeAtEntry,
                Contracts = CvdAtEntrySizeMultiplier > 1 && score.CvdPullbackPctAtEntry >= CvdAtEntryThreshold
                    ? CvdAtEntrySizeMultiplier
                    : 1
            };

            _lastManagePrice = score.EntryPrice;
            _lastManageTimeUtc = DateTime.MinValue;
            _tradeCreated = true;
            WriteTradeFile(nyTime.Date);
            ExecuteEntryOrder();
        }

        private void ApplyDynamicImbalanceStop(dynamic candle, string executionSide, TradeManagerTpSlBeExit.TradePlan plan)
        {
            var imbalanceStop = TradeManagerTpSlBeExit.TryGetImbalanceStop(
                candle,
                executionSide,
                SetupTickSize,
                ImbalanceRatio,
                ImbalanceCompareMinVolume);

            plan.Sl = imbalanceStop?.StopPrice ?? (executionSide == "BUY"
                ? plan.Entry - 60m * SetupTickSize
                : plan.Entry + 60m * SetupTickSize);

            plan.SlTicks = RoundToTicks(Math.Abs(plan.Entry - plan.Sl));
            plan.Tp = executionSide == "BUY"
                ? plan.Entry + plan.SlTicks * SetupTickSize
                : plan.Entry - plan.SlTicks * SetupTickSize;
            plan.TpTicks = plan.SlTicks;
            plan.UsesImbalanceStop = imbalanceStop != null;
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
            UpdateCvdProfitLock();
            UpdateCvdPullback(bar, candle);

            if (TryApplyCvdRiskBracket())
                return false;

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
            HandleSimulatedClose();
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
            UpdateCvdProfitLock();
            UpdateCvdPullback(bar, candle);

            if (TryApplyCvdRiskBracket())
                return;

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
            HandleSimulatedClose();
        }

        private bool TryApplyCvdRiskBracket()
        {
            if (_trade == null || _trade.Result != "OPEN")
                return false;

            if (_trade.CvdRiskBracketActive)
                return false;

            if (_trade.SpeedLabel == "normal speed" && !EnableCvdRiskManagementForNormalSpeed)
                return false;

            if (_trade.TpTicks <= 0)
                return false;

            if (_trade.CvdPullbackLabel != "Riesgo de reversion")
                return false;

            var decision = ATASScoreTradeExecutionManager.TryApplyCvdRiskBracket(
                new ATASScoreTradeExecutionManager.CvdRiskBracketRequest
                {
                    Side = _trade.Side,
                    SpeedLabel = _trade.SpeedLabel,
                    Result = _trade.Result,
                    Entry = _trade.Entry,
                    TpTicks = _trade.TpTicks,
                    TickSize = SetupTickSize,
                    CvdPullbackLabel = _trade.CvdPullbackLabel,
                    CvdRiskBracketActive = _trade.CvdRiskBracketActive,
                    AllowNormalSpeed = EnableCvdRiskManagementForNormalSpeed
                });

            if (!decision.ShouldApply)
                return false;

            _trade.Tp = decision.Tp;
            _trade.TpTicks = decision.TpTicks;
            _trade.CvdRiskBracketActive = true;
            WriteTradeFile(_currentNyDate);
            return true;
        }

        private bool HasCvdRiskExitProgress(decimal currentPrice)
        {
            if (_trade == null)
                return false;

            if (_trade.SpeedLabel == "normal speed" && !EnableCvdRiskManagementForNormalSpeed)
                return false;

            if (_trade.TpTicks <= 0)
                return false;

            if (!_trade.CvdProfitLockArmed || _trade.CvdProfitLockExitPrice == 0)
                return false;

            if (_trade.CvdPullbackLabel != "Riesgo de reversion")
                return false;

            if (_trade.CvdProfitLockBestMfeTicks <= _trade.CvdProfitLockTicks)
                return false;

            return ATASScoreTradeExecutionManager.HasCvdRiskExitProgress(
                new ATASScoreTradeExecutionManager.CvdRiskExitProgressRequest
                {
                    Side = _trade.Side,
                    SpeedLabel = _trade.SpeedLabel,
                    Entry = _trade.Entry,
                    TpTicks = _trade.TpTicks,
                    TickSize = SetupTickSize,
                    CurrentPrice = currentPrice,
                    ProfitLockArmed = _trade.CvdProfitLockArmed,
                    ProfitLockExitPrice = _trade.CvdProfitLockExitPrice,
                    ProfitLockTicks = _trade.CvdProfitLockTicks,
                    ProfitLockBestMfeTicks = _trade.CvdProfitLockBestMfeTicks,
                    CvdPullbackLabel = _trade.CvdPullbackLabel,
                    AllowNormalSpeed = EnableCvdRiskManagementForNormalSpeed
                });
        }

        private void UpdateCvdProfitLock()
        {
            if (_trade == null)
                return;

            var update = ATASScoreTradeExecutionManager.UpdateCvdProfitLock(
                new ATASScoreTradeExecutionManager.CvdProfitLockRequest
                {
                    Side = _trade.Side,
                    SpeedLabel = _trade.SpeedLabel,
                    Entry = _trade.Entry,
                    TpTicks = _trade.TpTicks,
                    TickSize = SetupTickSize,
                    MfeTicks = _trade.MfeTicks,
                    CurrentBestMfeTicks = _trade.CvdProfitLockBestMfeTicks,
                    CurrentLockTicks = _trade.CvdProfitLockTicks,
                    PullbackTicks = CvdProfitLockPullbackTicks,
                    AllowNormalSpeed = EnableCvdRiskManagementForNormalSpeed
                });

            _trade.CvdProfitLockBestMfeTicks = update.BestMfeTicks;

            if (!update.Armed)
                return;

            _trade.CvdProfitLockArmed = true;

            if (update.ExitPrice == 0)
                return;

            _trade.CvdProfitLockTicks = update.LockTicks;
            _trade.CvdProfitLockExitPrice = update.ExitPrice;
        }

        private decimal CalculateCurrentFavorableTicks(decimal currentPrice)
        {
            if (_trade == null)
                return 0;

            if (_trade.Side == "BUY")
                return Math.Max(0, RoundToTicks(currentPrice - _trade.Entry));

            if (_trade.Side == "SELL")
                return Math.Max(0, RoundToTicks(_trade.Entry - currentPrice));

            return 0;
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

            if (TryRecoverMissedReadyTradeBeforeTimeOver(bar, candle, nyTime))
                return false;

            _timeOverWritten = true;
            WriteTimeOverFile(nyTime.Date, nyTime);
            SendTelegramNoTradeMessage();
            RequestAutoStopAfterTerminalResult("TIME_OVER sin trade");
            return true;
        }

        private bool TryRecoverMissedReadyTradeBeforeTimeOver(int currentBar, dynamic currentCandle, DateTime currentNyTime)
        {
            if (!_orReady || _tradeCreated || _trade != null)
                return false;

            var startBar = Math.Max(_orBar + 1, 0);

            for (var scanBar = startBar; scanBar <= currentBar; scanBar++)
            {
                var scanCandle = GetCandle(scanBar);
                var scanNyTime = ConvertToNewYorkTime(scanCandle.Time);

                if (scanNyTime.Date != currentNyTime.Date)
                    continue;

                if (!IsSignalWindow(scanNyTime))
                    continue;

                UpdateAPlusStructureFromBar(scanBar, scanCandle, scanNyTime);

                var score = CalculateLiveScore(scanCandle, scanBar, scanNyTime);

                if (!score.IsReady)
                    continue;

                if (!PassesCvdAtEntryFilter(score))
                {
                    _cvdFilterSkippedDay = true;
                    return false;
                }

                _lastSignalReadyBar = scanBar;
                ClearPendingScore();
                CreateTrade(scanBar, scanCandle, scanNyTime, score);

                if (_trade == null)
                    return false;

                if (UpdateEntryBarTradeResult(scanBar, scanCandle))
                    return true;

                UpdateTradeResult(currentBar, currentCandle);
                return true;
            }

            return false;
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

            var update = ATASScoreTradeExecutionManager.UpdateCvdPullback(
                new ATASScoreTradeExecutionManager.CvdPullbackUpdateRequest
                {
                    Side = _trade.Side,
                    EntryCvd = _trade.CvdEntry,
                    PreviousPeakCvd = _trade.CvdPeak,
                    Bar = bar,
                    Candle = candle,
                    GetCandle = new Func<int, dynamic>(GetCandle),
                    SessionDate = _currentNyDate,
                    GetSessionTime = new Func<dynamic, DateTime>(c => ConvertToNewYorkTime(c.Time))
                });

            _trade.CumulativeDelta = update.CumulativeDelta;
            _trade.CumulativeDeltaSource = update.CumulativeDeltaSource;
            _trade.CvdPeak = update.CvdPeak;
            _trade.CvdCurrent = update.CvdCurrent;
            _trade.CvdPullbackPercent = update.CvdPullbackPercent;
            _trade.CvdPullbackLabel = update.CvdPullbackLabel;

            RecordCvdLabelTransitions(bar, candle);
        }

        /// <summary>
        /// Registra la PRIMERA vez que la etiqueta CVD intra-trade alcanza
        /// "Advertencia" y "Riesgo de reversion", junto con el contexto del
        /// trade en ese instante. Esto permite cuantificar offline cuanto se
        /// ahorraria una salida anticipada por riesgo CVD, sin cambiar todavia
        /// el comportamiento del sistema.
        /// </summary>
        private void RecordCvdLabelTransitions(int bar, dynamic candle)
        {
            if (_trade == null)
                return;

            var label = _trade.CvdPullbackLabel;
            var isWarn = label == "Advertencia" || label == "Riesgo de reversion";
            var isRisk = label == "Riesgo de reversion";

            if (!isWarn)
                return;

            var favTicks = CalculateSignedFavorableTicks(candle.Close);
            var barOffset = bar - _trade.EntryBar;

            if (_trade.CvdWarnFirstBarOffset < 0)
            {
                _trade.CvdWarnFirstBarOffset = barOffset;
                _trade.CvdWarnFirstFavTicks = favTicks;
            }

            if (isRisk && _trade.CvdRiskFirstBarOffset < 0)
            {
                _trade.CvdRiskFirstBarOffset = barOffset;
                _trade.CvdRiskFirstFavTicks = favTicks;
                _trade.CvdRiskFirstMaeTicks = _trade.MaeTicks;
                _trade.CvdRiskFirstMfeTicks = _trade.MfeTicks;
            }
        }

        private decimal CalculateSignedFavorableTicks(decimal currentPrice)
        {
            if (_trade == null || SetupTickSize <= 0)
                return 0;

            if (_trade.Side == "BUY")
                return Math.Round((currentPrice - _trade.Entry) / SetupTickSize, 0);

            if (_trade.Side == "SELL")
                return Math.Round((_trade.Entry - currentPrice) / SetupTickSize, 0);

            return 0;
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

            if (_trade.Side == "BUY")
            {
                if (candle.High > _trade.EntryBarHighAtEntry || candle.High >= _trade.Tp)
                    tradeHigh = candle.High;

                if (candle.Low < _trade.EntryBarLowAtEntry)
                    tradeLow = candle.Low;
            }
            else if (_trade.Side == "SELL")
            {
                if (candle.High > _trade.EntryBarHighAtEntry)
                    tradeHigh = candle.High;

                if (candle.Low < _trade.EntryBarLowAtEntry || candle.Low <= _trade.Tp)
                    tradeLow = candle.Low;
            }
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

        private DateTime ResolveSignalNewYorkTime(dynamic candle)
        {
            string timingSource;
            var updateTime = TryGetCandleUpdateTime(candle, out timingSource);

            if (timingSource == "UtcNow")
                return ConvertToNewYorkTime(candle.Time);

            return ConvertToNewYorkTime(updateTime);
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
                "Exporter_VERSION,fecha,EntryTime_NY,EntrySecond_NY,EntryBar,or_low,or_high,range,VWAP_entry,Body,Volume_entry,Delta_entry,Cumulative_Delta_entry,Cumulative_Delta_Source,Cvd_Peak,Cvd_Current,Cvd_Pullback_Pct,Cvd_Pullback_Label,Previous_Volume,Previous_Delta,Volume_Increasing,Delta_Change,Delta_With_Side,Price_Accepted_After_Imbalance,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS,Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK,score total,Side,Signal_Source,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label,Exit_price,result TP SL BE,MAE_ticks,MFE_ticks,APlus_Structure,APlus_Absorption,APlus_Speed,Imbalance_Group_3,Imbalance_Group_Price,Imbalance_Count,Speed_Ignored_By_Structure,Cvd_SessMax_AtEntry,Cvd_SessMin_AtEntry,Cvd_Pullback_Pct_AtEntry,Cvd_Pullback_Label_AtEntry,Cvd_Slope3_AtEntry,Bars_Since_Cvd_Extreme_AtEntry,CvdWarn_First_BarOffset,CvdWarn_First_FavTicks,CvdRisk_First_BarOffset,CvdRisk_First_FavTicks,CvdRisk_First_MAE,CvdRisk_First_MFE,Trade_Contracts" + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    _trade.EntryDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _trade.EntryTimeNy.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    _trade.EntryTimeNy.Second.ToString(CultureInfo.InvariantCulture),
                    _trade.EntryBar.ToString(CultureInfo.InvariantCulture),
                    FormatPrice(_trade.OrLow),
                    FormatPrice(_trade.OrHigh),
                    FormatTicks(_trade.OrRangeTicks),
                    FormatPrice(_trade.Vwap),
                    FormatTicks(_trade.BodyBreakoutTicks),
                    FormatTicks(_trade.Volume),
                    FormatTicks(_trade.Delta),
                    FormatTicks(_trade.CvdEntry), // CVD real al momento de la entrada (CumulativeDelta se sobrescribe intra-trade)
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
                    FormatBool(_trade.SpeedIgnoredByStructure),
                    FormatTicks(_trade.CvdSessionMaxAtEntry),
                    FormatTicks(_trade.CvdSessionMinAtEntry),
                    FormatSeconds(_trade.CvdPullbackPctAtEntry),
                    _trade.CvdPullbackLabelAtEntry,
                    FormatTicks(_trade.CvdSlope3AtEntry),
                    _trade.BarsSinceCvdExtremeAtEntry.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdWarnFirstBarOffset.ToString(CultureInfo.InvariantCulture),
                    FormatSignedTicks(_trade.CvdWarnFirstFavTicks),
                    _trade.CvdRiskFirstBarOffset.ToString(CultureInfo.InvariantCulture),
                    FormatSignedTicks(_trade.CvdRiskFirstFavTicks),
                    FormatTicks(_trade.CvdRiskFirstMaeTicks),
                    FormatTicks(_trade.CvdRiskFirstMfeTicks),
                    _trade.Contracts.ToString(CultureInfo.InvariantCulture)
                ) + Environment.NewLine
            );
        }

        private void WriteTimeOverFile(DateTime nyDate, DateTime nyTime)
        {
            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var filePath = Path.Combine(
                _exportFolder,
                $"score_trade_result_{nyDate:yyyy-MM-dd}_NY.csv"
            );

            File.WriteAllText(
                filePath,
                "Exporter_VERSION,fecha,EntryTime_NY,EntrySecond_NY,EntryBar,or_low,or_high,range,VWAP_entry,Body,Volume_entry,Delta_entry,Cumulative_Delta_entry,Cumulative_Delta_Source,Cvd_Peak,Cvd_Current,Cvd_Pullback_Pct,Cvd_Pullback_Label,Previous_Volume,Previous_Delta,Volume_Increasing,Delta_Change,Delta_With_Side,Price_Accepted_After_Imbalance,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS,Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK,score total,Side,Signal_Source,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label,Exit_price,result TP SL BE,MAE_ticks,MFE_ticks,APlus_Structure,APlus_Absorption,APlus_Speed,Imbalance_Group_3,Imbalance_Group_Price,Imbalance_Count,Speed_Ignored_By_Structure,Cvd_SessMax_AtEntry,Cvd_SessMin_AtEntry,Cvd_Pullback_Pct_AtEntry,Cvd_Pullback_Label_AtEntry,Cvd_Slope3_AtEntry,Bars_Since_Cvd_Extreme_AtEntry,CvdWarn_First_BarOffset,CvdWarn_First_FavTicks,CvdRisk_First_BarOffset,CvdRisk_First_FavTicks,CvdRisk_First_MAE,CvdRisk_First_MFE,Trade_Contracts" + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    nyTime.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    nyTime.Second.ToString(CultureInfo.InvariantCulture),
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
                    "FALSE",
                    "", "", "", "", "", "", // Cvd at-entry (sin trade)
                    "", "", "", "", "", "", // CvdWarn/CvdRisk (sin trade)
                    "" // Trade_Contracts
                ) + Environment.NewLine
            );
        }

        /// <summary>
        /// True si la senal califica segun el filtro CVD at-entry (o si el
        /// filtro esta apagado). La decision usa solo datos pre-entrada.
        /// </summary>
        private bool PassesCvdAtEntryFilter(ScoreTradeSignal score)
        {
            if (!EnableCvdAtEntryFilter)
                return true;

            return score.CvdPullbackPctAtEntry >= CvdAtEntryThreshold;
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
                "Exporter_VERSION,fecha,EntryTime_NY,EntrySecond_NY,EntryBar,or_low,or_high,range,VWAP_entry,Body,Volume_entry,Delta_entry,Cumulative_Delta_entry,Cumulative_Delta_Source,Cvd_Peak,Cvd_Current,Cvd_Pullback_Pct,Cvd_Pullback_Label,Previous_Volume,Previous_Delta,Volume_Increasing,Delta_Change,Delta_With_Side,Price_Accepted_After_Imbalance,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS,Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK,score total,Side,Signal_Source,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label,Exit_price,result TP SL BE,MAE_ticks,MFE_ticks,APlus_Structure,APlus_Absorption,APlus_Speed,Imbalance_Group_3,Imbalance_Group_Price,Imbalance_Count,Speed_Ignored_By_Structure,Cvd_SessMax_AtEntry,Cvd_SessMin_AtEntry,Cvd_Pullback_Pct_AtEntry,Cvd_Pullback_Label_AtEntry,Cvd_Slope3_AtEntry,Bars_Since_Cvd_Extreme_AtEntry,CvdWarn_First_BarOffset,CvdWarn_First_FavTicks,CvdRisk_First_BarOffset,CvdRisk_First_FavTicks,CvdRisk_First_MAE,CvdRisk_First_MFE,Trade_Contracts" + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _bestRejectedScoreNyTime.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    _bestRejectedScoreNyTime.Second.ToString(CultureInfo.InvariantCulture),
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
                    (score.HasAPlusStructure ? 3 : 0).ToString(CultureInfo.InvariantCulture),
                    FormatBool(score.SpeedIgnoredByStructure),
                    FormatTicks(score.CvdSessionMaxAtEntry),
                    FormatTicks(score.CvdSessionMinAtEntry),
                    FormatSeconds(score.CvdPullbackPctAtEntry),
                    score.CvdPullbackLabelAtEntry,
                    FormatTicks(score.CvdSlope3AtEntry),
                    score.BarsSinceCvdExtremeAtEntry.ToString(CultureInfo.InvariantCulture),
                    "", "", "", "", "", "", // instrumentacion intra-trade no aplica
                    "" // Trade_Contracts
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
            _terminalAutoStopRequested = false;
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
            _lastSignalReadyBar = -1;
            _cvdFilterSkippedDay = false;
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
                _buyAPlusStructureCount = 3;
            }

            if (state.HasSell3_ImbalanceGroup && !_hasSellAPlusStructure)
            {
                _hasSellAPlusStructure = true;
                _sellAPlusStructurePrice = state.Sell3_ImbalanceGroupPrice;
                _sellAPlusStructureCount = 3;
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

            CreateTrade(entryBar, entryCandle, _pendingScoreNyTime, _pendingScore);
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


        // =====================================================================
        // EJECUCION REAL (v1 espejo): la simulacion interna es la fuente de
        // verdad; las ordenes reales la replican. Entrada a mercado cuando la
        // simulacion abre; flatten a mercado cuando la simulacion cierra.
        // LIMITACION CONOCIDA v1: el SL vive en la estrategia, no como orden
        // stop residente en el broker. Apto para DEMO. Antes de cuenta real
        // se implementa v2 con bracket de ordenes residentes.
        // =====================================================================

        private void ExecuteEntryOrder()
        {
            if (!EnableExecution || _trade == null)
                return;

            try
            {
                var qty = Math.Max(1, Contracts) * Math.Max(1, _trade.Contracts);
                var direction = _trade.Side == "BUY" ? OrderDirections.Buy : OrderDirections.Sell;

                var order = new Order
                {
                    Portfolio = Portfolio,
                    Security = Security,
                    Direction = direction,
                    Type = OrderTypes.Market,
                    QuantityToFill = qty
                };

                OpenOrder(order);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"EW Strategy: error al colocar entrada: {ex.Message}");
            }
        }

        private void HandleSimulatedClose()
        {
            if (_trade == null)
                return;

            var signedTicks = CalculateSignedTradeResultTicks();
            SendTelegramCloseMessage(_trade.Result, signedTicks);
            FlattenPosition();
            RequestAutoStopAfterTerminalResult($"resultado {_trade.Result}");
        }

        private void RequestAutoStopAfterTerminalResult(string reason)
        {
            if (!EnableAutoStopAfterTerminalResult || _terminalAutoStopRequested)
                return;

            _terminalAutoStopRequested = true;

            Task.Run(async () =>
            {
                try
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(500)).ConfigureAwait(false);
                    await WaitForTelegramSendAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
                    System.Diagnostics.Debug.WriteLine($"EW Strategy: auto-stop por {reason}.");
                    await StopAsync().ConfigureAwait(false);
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"EW Strategy: error en auto-stop: {ex.Message}");
                }
            });
        }

        private async Task WaitForTelegramSendAsync(TimeSpan timeout)
        {
            var sendTask = _lastTelegramSendTask ?? Task.CompletedTask;

            if (sendTask.IsCompleted)
                return;

            var timeoutTask = Task.Delay(timeout);
            var completedTask = await Task.WhenAny(sendTask, timeoutTask).ConfigureAwait(false);

            if (completedTask == timeoutTask)
                AppendTelegramLog($"Timeout esperando envio Telegram despues de {timeout.TotalSeconds:0}s.");
        }

        private decimal CalculateSignedTradeResultTicks()
        {
            if (_trade == null || SetupTickSize <= 0)
                return 0;

            var diff = _trade.Side == "BUY"
                ? _trade.ExitPrice - _trade.Entry
                : _trade.Entry - _trade.ExitPrice;

            return Math.Round(diff / SetupTickSize, 0);
        }

        private void FlattenPosition()
        {
            if (!EnableExecution)
                return;

            try
            {
                var position = CurrentPosition;

                if (position == 0)
                    return;

                var order = new Order
                {
                    Portfolio = Portfolio,
                    Security = Security,
                    Direction = position > 0 ? OrderDirections.Sell : OrderDirections.Buy,
                    Type = OrderTypes.Market,
                    QuantityToFill = Math.Abs(position)
                };

                OpenOrder(order);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"EW Strategy: error al cerrar posicion: {ex.Message}");
            }
        }

        private void SendTelegramNoTradeMessage()
        {
            var motivo = _cvdFilterSkippedDay ? " (senal filtrada por CVD)" : "";
            var dateText = FormatTelegramDate(DateTime.UtcNow);
            SendTelegramText($"\u26AA {dateText} NO TRADE TODAY{motivo}");
        }

        private void SendTelegramCloseMessage(string result, decimal signedTicks)
        {
            var emoji = result == "TP" ? "\U0001F7E2" : result == "SL" ? "\U0001F534" : "\u26AA";
            var signo = signedTicks >= 0 ? "+" : "";
            var dateText = FormatTelegramDate(_trade?.EntryDate ?? DateTime.UtcNow);
            SendTelegramText($"{emoji} {dateText} {result} {signo}{signedTicks:0} ticks");
        }

        private string FormatTelegramDate(DateTime dateTime)
        {
            var nyDate = dateTime.Kind == DateTimeKind.Utc
                ? ConvertToNewYorkTime(dateTime).Date
                : dateTime.Date;

            return nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        }

        private void SendTelegramText(string texto)
        {
            if (!EnableTelegramAlerts)
            {
                AppendTelegramLog($"No enviado: alertas Telegram desactivadas. Texto='{texto}'");
                return;
            }

            var token = ResolveTelegramSetting(TelegramBotToken, "TELEGRAM_BOT_TOKEN", "token");
            var chatId = ResolveTelegramSetting(TelegramChatId, "TELEGRAM_CHAT_ID", "chat_id");

            if (string.IsNullOrWhiteSpace(token) || string.IsNullOrWhiteSpace(chatId))
            {
                AppendTelegramLog(
                    $"No enviado: token/chat_id vacio. TokenSet={!string.IsNullOrWhiteSpace(token)}, ChatIdSet={!string.IsNullOrWhiteSpace(chatId)}. Texto='{texto}'");
                return;
            }

            var url = $"https://api.telegram.org/bot{token}/sendMessage";
            var payload = new Dictionary<string, string>
            {
                ["chat_id"] = chatId,
                ["text"] = texto,
                ["disable_web_page_preview"] = "true"
            };

            _lastTelegramSendTask = Task.Run(async () =>
            {
                try
                {
                    AppendTelegramLog($"Enviando Telegram. ChatId='{chatId}', Texto='{texto}'");
                    using var content = new FormUrlEncodedContent(payload);
                    using var response = await TelegramHttpClient.PostAsync(url, content).ConfigureAwait(false);

                    if (!response.IsSuccessStatusCode)
                    {
                        var body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                        AppendTelegramLog($"Telegram HTTP {(int)response.StatusCode} {response.ReasonPhrase}: {body}");
                        System.Diagnostics.Debug.WriteLine(
                            $"EW Strategy: Telegram HTTP {(int)response.StatusCode} {response.ReasonPhrase}: {body}");
                        return;
                    }

                    AppendTelegramLog($"Telegram enviado OK. Status={(int)response.StatusCode}");
                }
                catch (Exception ex)
                {
                    // Telegram caido jamas afecta la operativa.
                    AppendTelegramLog($"Error Telegram: {ex.GetType().Name}: {ex.Message}");
                    System.Diagnostics.Debug.WriteLine($"EW Strategy: error Telegram: {ex.Message}");
                }
            });
        }

        private void AppendTelegramLog(string message)
        {
            try
            {
                Directory.CreateDirectory(_exportFolder);
                var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {message}{Environment.NewLine}";
                File.AppendAllText(Path.Combine(_exportFolder, "telegram_debug.log"), line);
            }
            catch
            {
                // El log de Telegram no debe afectar la estrategia.
            }
        }

        private string ResolveTelegramSetting(string propertyValue, string environmentVariable, string credentialsKey)
        {
            if (!string.IsNullOrWhiteSpace(propertyValue))
                return propertyValue.Trim();

            var envValue = Environment.GetEnvironmentVariable(environmentVariable);
            if (!string.IsNullOrWhiteSpace(envValue))
                return envValue.Trim();

            try
            {
                if (!File.Exists(_telegramCredentialsFile))
                    return "";

                foreach (var rawLine in File.ReadAllLines(_telegramCredentialsFile))
                {
                    var line = rawLine.Trim();

                    if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal))
                        continue;

                    var separatorIndex = line.IndexOf('=');

                    if (separatorIndex <= 0)
                        continue;

                    var key = line.Substring(0, separatorIndex).Trim();

                    if (!string.Equals(key, credentialsKey, StringComparison.OrdinalIgnoreCase))
                        continue;

                    return line.Substring(separatorIndex + 1).Trim();
                }
            }
            catch (Exception ex)
            {
                AppendTelegramLog($"Error leyendo credenciales Telegram: {ex.Message}");
            }

            return "";
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
            public bool CvdProfitLockArmed { get; set; }
            public decimal CvdProfitLockExitPrice { get; set; }
            public decimal CvdProfitLockTicks { get; set; }
            public decimal CvdProfitLockBestMfeTicks { get; set; }
            public bool CvdRiskBracketActive { get; set; }
            public bool APlusStructure { get; set; }
            public bool APlusAbsorption { get; set; }
            public bool APlusSpeed { get; set; }
            public string SignalSource { get; set; } = "";
            public string ImbalanceGroup3 { get; set; } = "";
            public decimal? ImbalanceGroupPrice { get; set; }
            public int ImbalanceCount { get; set; }
            public bool SpeedIgnoredByStructure { get; set; }

            // --- Features pre-entrada (sin lookahead) ---
            public decimal CvdSessionMaxAtEntry { get; set; }
            public decimal CvdSessionMinAtEntry { get; set; }
            public decimal CvdPullbackPctAtEntry { get; set; }
            public string CvdPullbackLabelAtEntry { get; set; } = "";
            public decimal CvdSlope3AtEntry { get; set; }
            public int BarsSinceCvdExtremeAtEntry { get; set; }

            // --- Instrumentacion intra-trade: primera transicion de etiqueta CVD ---
            // BarOffset = barras despues de la entrada (-1 = nunca ocurrio).
            // FavTicks = ticks a favor (con signo) al momento de la transicion.
            public int CvdWarnFirstBarOffset { get; set; } = -1;
            public decimal CvdWarnFirstFavTicks { get; set; }
            public int Contracts { get; set; } = 1;
            public int CvdRiskFirstBarOffset { get; set; } = -1;
            public decimal CvdRiskFirstFavTicks { get; set; }
            public decimal CvdRiskFirstMaeTicks { get; set; }
            public decimal CvdRiskFirstMfeTicks { get; set; }
        }

    }
}
