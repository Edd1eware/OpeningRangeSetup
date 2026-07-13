using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.Json;
using ATAS.DataFeedsCore;
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

        private readonly string _replaySyncSignalsFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\replay_sync_signals";

        private readonly string _replaySyncResultsFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\replay_sync_results";

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private const decimal SetupTickSize = 0.25m;
        private const decimal ValueAcceptanceMinTradeTicks = 30m;
        private const decimal NormalScalpMaxTradeTicks = 120m;
        private const decimal DynamicAlarmMaePullbackTicks = 15m;
        private const decimal DynamicAlarmMaeSpeedTicksPerSecond = 10m;
        // Piso minimo del intervalo (segundos) para velocidades instantaneas
        // ticks/seg. Con timestamps de milisegundos reales, dos updates del mismo
        // instante quedan a ~nanosegundos y la division explota (p.ej. 5e7 t/s).
        // Flooring a 0.25s mata el ruido sub-milisegundo sin tocar movimientos
        // reales rapidos (>=2.5 ticks en 0.25s siguen disparando la alarma).
        private const double MinSpeedIntervalSeconds = 0.25d;
        private const int DynamicAlarmFieldCount = 37;
        private const int ExtendedTelemetryFieldCount = 27;
        private const decimal DynamicTimelineSampleIntervalSeconds = 0.25m;
        private const int DynamicTimelineFlushRowCount = 100;
        // FROZEN — DO NOT CHANGE. Sync guards depend on this version string matching
        // persisted snapshots. Changing it invalidates all existing X1/X10 sync files.
        private const string ExporterVersion = "score-exporter-2026-07-12-v20-causal-terminal-results";
        private const string DynamicTimelineVersion = "dynamic-timeline-2026-06-23-v11-canonical-sync-guards";
        private static readonly JsonSerializerOptions ReplaySyncJsonOptions = new JsonSerializerOptions
        {
            WriteIndented = true
        };
        private const string DynamicTimelineCsvHeader =
            "Timeline_VERSION,Trade_ID,Sequence,Event,Timestamp_NY,Seconds_From_Entry,Timing_Source," +
            "Replay_Speed_Multiplier,Raw_Elapsed_Seconds,Normalized_Elapsed_Seconds,Bar,fecha," +
            "EntryTime_NY,Side,Entry_Score,Balanced_Filter_Eligible,Entry_price,SL_price,TP_price,Current_price," +
            "Open_PnL_Ticks,Current_Favorable_Ticks,Current_Adverse_Ticks,MAE_ticks_To_Now,MFE_ticks_To_Now," +
            "Drawdown_From_MFE_Ticks,Current_MAE_Pullback_Ticks,Current_MAE_Speed_TPS," +
            "Largest_MAE_Pullback_Ticks_To_Now,Max_MAE_Speed_TPS_To_Now,Distance_To_SL_Ticks," +
            "Distance_To_TP_Ticks,Seconds_Since_Last_MFE,Cvd_Current,Cvd_Peak,Cvd_Pullback_Pct,Cvd_Label," +
            "Cvd_NonExcellent_Seconds,Cvd_NonExcellent_Consecutive_Samples,Cvd_Excelente_Count,Cvd_Normal_Count," +
            "Cvd_Advertencia_Count,Cvd_Riesgo_Reversion_Count,Cvd_Total_Samples,Cvd_Excelente_Time_Pct_To_Now," +
            "Cvd_Negative_Episodes,Cvd_Label_Changes,Cvd_Worst_Label_To_Now,Current_Pullback_GE_15," +
            "Current_MAE_Speed_GE_10,Causal_Alarm_Candidate,Legacy_Max_Alarm_Candidate,Causal_Alarm_Episode," +
            "Dynamic_Alarm_Triggered,Dynamic_Alarm_Reason,Result,Current_Delta,Max_Delta_during_trade," +
            "Min_Delta_during_trade,Current_Volume,Volume_Increasing_From_Previous_Update," +
            "MAE_Speed_500ms_TPS,MAE_Speed_1s_TPS,MAE_Speed_2s_TPS,TP_And_SL_Hit_Same_Update," +
            "No_Gestionable_Por_Latencia";
        private const string DynamicAlarmCsvHeader =
            "Dynamic_Alarm_Triggered,Dynamic_Alarm_Time_NY,Dynamic_Alarm_Seconds_From_Entry,Dynamic_Alarm_Reason," +
            "Cvd_Label_At_Alarm,Cvd_Pullback_Pct_At_Alarm,MAE_Pullback_Ticks_At_Alarm,MAE_Speed_TPS_At_Alarm," +
            "Current_MAE_Pullback_Ticks_At_Alarm,Current_MAE_Speed_TPS_At_Alarm,Open_PnL_Ticks_At_Alarm," +
            "MFE_Ticks_At_Alarm,Drawdown_From_MFE_Ticks_At_Alarm,MFE_TP_Pct_At_Alarm," +
            "Distance_To_SL_Ticks_At_Alarm,Distance_To_TP_Ticks_At_Alarm,Seconds_Since_Last_MFE," +
            "Cvd_NonExcellent_Seconds_At_Alarm,Cvd_NonExcellent_Consecutive_Samples," +
            "Cvd_Excelente_Time_Pct_Before_Alarm,Cvd_Worst_Label_Before_Alarm," +
            "Cvd_Excelente_Count_At_Alarm,Cvd_Normal_Count_At_Alarm,Cvd_Advertencia_Count_At_Alarm," +
            "Cvd_Riesgo_Reversion_Count_At_Alarm,Cvd_Total_Samples_At_Alarm," +
            "Future_MFE_After_Alarm,Future_MAE_After_Alarm,Result_Trail_10,Result_Trail_15,Result_Trail_20," +
            "Result_Breakeven_At_Alarm,Ticks_Saved_Trail_10_Vs_Baseline,Ticks_Saved_Trail_15_Vs_Baseline," +
            "Ticks_Saved_Trail_20_Vs_Baseline,Ticks_Saved_Breakeven_Vs_Baseline,Ticks_Saved_Vs_Baseline";
        private const string CsvHeader =
            "Exporter_VERSION,fecha,EntryTime_NY,ExitTime_NY,Trade_Duration,EntrySecond_NY,EntryBar,or_low,or_high,range," +
            "VWAP_entry,Body,Volume_entry,Delta_entry,Cumulative_Delta_entry,Cumulative_Delta_Source,Cvd_Peak,Cvd_Current," +
            "Cvd_Pullback_Pct,Cvd_Pullback_Label,Cvd_Excelente_Count,Cvd_Normal_Count,Cvd_Advertencia_Count," +
            "Cvd_Riesgo_Reversion_Count,Cvd_Total_Samples,Cvd_Excelente_Pct,Cvd_Negative_Episodes,Cvd_Label_Changes," +
            "Cvd_Worst_Label," + DynamicAlarmCsvHeader + ",Previous_Volume,Previous_Delta,Volume_Increasing,Delta_Change," +
            "Delta_With_Side,Price_Accepted_After_Imbalance,BreakOut_SPEED,BreakOut_TICKS_PER_SEC,Speed_Elapsed_SECONDS," +
            "Speed_Replay_Fallback,Speed_Timing_Source,Range_OK,Body_OK,Volume_OK,Delta_OK,Time_OK,VWAP_OK,Speed_OK," +
            "score total,Side,Signal_Source,Speed_Profile,SL_price,Entry_price,TP_price,SL_ticks,TP_ticks,Result_Label," +
            "Exit_price,result TP SL BE,MAE_ticks,MFE_ticks,Largest_MAE_pullback_ticks,Largest_MFE_pullup_ticks," +
            "Number_of_Pullbacks_during_Trade,Number_of_PullUps_during_Trade,Max_Speed_MAE_during_trade," +
            "Max_Speed_MFE_during_trade,APlus_Structure,APlus_Absorption,APlus_Speed,Imbalance_Group_3," +
            "Imbalance_Group_Price,Imbalance_Count,Speed_Ignored_By_Structure," +
            "EntryTime_NY_Milliseconds,ExitTime_NY_Milliseconds,Trade_Duration_Milliseconds,Subsecond_Trade," +
            "Latency_Threshold_Milliseconds,No_Gestionable_Por_Latencia,Alarm_To_Exit_Milliseconds," +
            "Dynamic_Alarm_No_Gestionable_Por_Latencia,Slippage_Ticks_Per_Fill,Result_After_Slippage_Ticks," +
            "TP_And_SL_Hit_Same_Update,Raw_Speed_Label,APlus_Speed_Threshold_TPS," +
            "APlus_Speed_Setup_Confirmed,Price_Rejected_After_Imbalance," +
            "Buy_Imbalance_Count,Sell_Imbalance_Count," +
            "Execution_Side_Imbalance_Count,Max_Delta_during_trade,Min_Delta_during_trade," +
            "Volume_Increased_During_Trade,Volume_Increase_Samples,Volume_Observed_Samples," +
            "Volume_Increasing_Pct_During_Trade,Max_MAE_Speed_500ms,Max_MAE_Speed_1s,Max_MAE_Speed_2s";
        private const string TradeInputCsvFileName = "trade_inputs.csv";
        private const string TradeResultCsvFileName = "trade_results.csv";
        private const string TradeInputCsvHeader =
            "Input_VERSION,fecha,decision_timestamp,feature_timestamp,entry_timestamp,EntryBar,Side,Signal_Source,Speed_Profile," +
            "Entry_price,SL_price_AtEntry,TP_price_AtEntry,SL_ticks_AtEntry,TP_ticks_AtEntry,or_low,or_high,range," +
            "VWAP_AtEntry,Body_AtEntry,Volume_AtEntry,Delta_AtEntry,Cumulative_Delta_AtEntry,Cumulative_Delta_Source_AtEntry," +
            "Cvd_Current_AtEntry,Cvd_Peak_AtEntry,Cvd_Pullback_Pct_AtEntry,Cvd_Label_AtEntry,Cvd_Total_Samples_AtEntry," +
            "Previous_Volume_AtEntry,Previous_Delta_AtEntry,Volume_Increasing_AtEntry,Delta_Change_AtEntry,Delta_With_Side_AtEntry," +
            "Price_Accepted_After_Imbalance_AtEntry,Price_Rejected_After_Imbalance_AtEntry,BreakOut_SPEED_AtEntry," +
            "BreakOut_TICKS_PER_SEC_AtEntry,Speed_Elapsed_SECONDS_AtEntry,Speed_Replay_Fallback_AtEntry,Speed_Timing_Source_AtEntry," +
            "Range_OK_AtEntry,Body_OK_AtEntry,Volume_OK_AtEntry,Delta_OK_AtEntry,Time_OK_AtEntry,VWAP_OK_AtEntry,Speed_OK_AtEntry," +
            "Score_AtEntry,Raw_Speed_Label_AtEntry,APlus_Structure_AtEntry,APlus_Absorption_AtEntry,APlus_Speed_AtEntry," +
            "APlus_Speed_Setup_Confirmed_AtEntry,Buy_Imbalance_Count_AtEntry," +
            "Sell_Imbalance_Count_AtEntry,Execution_Side_Imbalance_Count_AtEntry,Imbalance_Group_3_AtEntry," +
            "Imbalance_Group_Price_AtEntry,Imbalance_Count_AtEntry,Speed_Ignored_By_Structure_AtEntry,feature_timestamp_utc,entry_timestamp_utc";
        private const string TradeResultCsvHeader =
            "Result_VERSION,fecha,entry_timestamp,outcome_timestamp,ExitTime_NY,Trade_Duration,EntryBar,Side,Entry_price," +
            "Result_Label,Exit_price,result_ticks,MAE_ticks,MFE_ticks,Largest_MAE_pullback_ticks,Largest_MFE_pullup_ticks," +
            "Number_of_Pullbacks_during_Trade,Number_of_PullUps_during_Trade,Max_Speed_MAE_during_trade,Max_Speed_MFE_during_trade," +
            "SL_price_Final,TP_price_Final,SL_ticks_Final,TP_ticks_Final,Cvd_Current_Final,Cvd_Peak_Final,Cvd_Pullback_Pct_Final," +
            "Cvd_Label_Final,Cvd_Worst_Label_Final,Cvd_Excelente_Count_Final,Cvd_Normal_Count_Final,Cvd_Advertencia_Count_Final," +
            "Cvd_Riesgo_Reversion_Count_Final,Cvd_Total_Samples_Final,Cvd_Excelente_Pct_Final,Cvd_Negative_Episodes_Final," +
            "Cvd_Label_Changes_Final,Dynamic_Alarm_Triggered,TP_And_SL_Hit_Same_Update,Result_After_Slippage_Ticks," +
            "Volume_Increased_During_Trade,Volume_Increase_Samples,Volume_Observed_Samples,Volume_Increasing_Pct_During_Trade," +
            "Max_Delta_during_trade,Min_Delta_during_trade";

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
        private ScoreTradeSignal? _bestObservedScore;
        private int _bestObservedScoreBar = -1;
        private DateTime _bestObservedScoreNyTime = DateTime.MinValue;
        private string _bestObservedScoreSource = "";
        private bool _bestObservedScoreIsTradeEvent;
        private decimal _lastManagePrice;
        private DateTime _lastManageTimeUtc = DateTime.MinValue;
        private int _lastSignalReadyBar = -1;
        private int _activeMarketUpdateBar = -1;
        private DateTime _activeMarketUpdateTime = DateTime.MinValue;
        private DateTime _activeMarketCandleTime = DateTime.MinValue;
        private long _marketUpdateSequence;
        private int _lastProcessedMarketBar = -1;
        private DateTime _lastProcessedMarketTime = DateTime.MinValue;
        private decimal _lastProcessedMarketClose;
        private decimal _lastProcessedMarketHigh;
        private decimal _lastProcessedMarketLow;
        private decimal _lastProcessedMarketVolume;
        private decimal _lastProcessedMarketDelta;
        private string _lastProcessedMarketSource = "";
        private bool _firstCalculateDiagnosticWritten;
        private bool _marketByOrderSubscriptionAttempted;
        private bool _marketByOrderSubscriptionRequested;
        private int _diagOnNewTradeCount;
        private int _diagOnNewTradesBatchCount;
        private int _diagOnNewTradesItemCount;
        private int _diagOnCumulativeTradeCount;
        private int _diagOnUpdateCumulativeTradeCount;
        private int _diagOnCumulativeTradeTickCount;
        private int _diagMarketDepthChangedCount;
        private int _diagMarketDepthsChangedBatchCount;
        private int _diagMarketDepthsChangedItemCount;
        private int _diagMarketByOrdersChangedBatchCount;
        private int _diagMarketByOrdersChangedItemCount;
        private DateTime _diagLastTradeTimeUtc = DateTime.MinValue;
        private decimal _diagLastTradePrice;
        private decimal _diagLastTradeVolume;
        private DateTime _diagLastCumulativeTradeTimeUtc = DateTime.MinValue;
        private decimal _diagLastCumulativeTradePrice;
        private decimal _diagLastCumulativeTradeVolume;
        private DateTime _diagLastMarketDepthTimeUtc = DateTime.MinValue;
        private decimal _diagLastMarketDepthPrice;
        private decimal _diagLastMarketDepthVolume;
        private string _diagLastMarketDepthType = "";

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
        public decimal APlusPriceAcceptanceTicks { get; set; } = 15m;
        public decimal MinTradeTicks { get; set; } = 60;
        public decimal MaxTradeTicks { get; set; } = 60;
        public decimal HalfMfeExitMinMfeTicks { get; set; } = 40;
        public decimal FastExitMinMfeTicks { get; set; } = 40;
        public decimal FastExitPullbackTicks { get; set; } = 10;
        public decimal CvdProfitLockPullbackTicks { get; set; } = 10;
        public decimal FastExitAdverseSpeedTicksPerSecond { get; set; } = 6;
        public decimal SlippageTicksPerFill { get; set; } = 1;
        public int MaxExpectedLatencyMilliseconds { get; set; } = 20;
        public TimeSpan TimeOverTimeNy { get; set; } = new TimeSpan(9, 40, 0);
        public int MinTimeOverRealtimeSeconds { get; set; } = 5;
        public bool RequireBodyOkForTrade { get; set; } = false;
        public bool RequireVwapOkForTrade { get; set; } = false;
        // Para el PnL en $ del Telegram (NQ = $5/tick). Contratos = sizing Lucid.
        public int TelegramContracts { get; set; } = 6;
        public decimal TickValueUsd { get; set; } = 5m;
        // Balance corrido en Telegram: arranca en esta cuenta y suma/resta cada PnL.
        public decimal TelegramStartingBalance { get; set; } = 150000m;

        public ATASScoreTradeResultExporter()
        {
            Name = "ATAS Score Trade Result Exporter ENTRY SL TP RESULT";
            EnableCustomDrawing = false;
            WriteLifecycleDiagnostic("constructor", -1, DateTime.Now);
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

        protected override void OnNewTrade(MarketDataArg trade)
        {
            base.OnNewTrade(trade);
            RecordTradeCallback(trade, false);

            var bar = CurrentBar - 1;
            if (bar < 2)
                return;

            ProcessMarketUpdate(CreateTradeMarketUpdate(bar, trade));
        }

        protected override void OnNewTrades(IEnumerable<MarketDataArg> trades)
        {
            base.OnNewTrades(trades);

            if (trades == null)
                return;

            _diagOnNewTradesBatchCount++;
            foreach (var trade in trades)
            {
                RecordTradeCallback(trade, true);
                var bar = CurrentBar - 1;
                if (bar < 2)
                    continue;

                ProcessMarketUpdate(CreateTradeMarketUpdate(bar, trade));
            }
        }

        protected override void OnCumulativeTrade(CumulativeTrade trade)
        {
            base.OnCumulativeTrade(trade);
            RecordCumulativeTradeCallback(trade, false);
        }

        protected override void OnUpdateCumulativeTrade(CumulativeTrade trade)
        {
            base.OnUpdateCumulativeTrade(trade);
            RecordCumulativeTradeCallback(trade, true);
        }

        protected override void MarketDepthChanged(MarketDataArg depth)
        {
            base.MarketDepthChanged(depth);
            RecordMarketDepthCallback(depth, false);
        }

        protected override void MarketDepthsChanged(IEnumerable<MarketDataArg> depths)
        {
            base.MarketDepthsChanged(depths);

            if (depths == null)
                return;

            _diagMarketDepthsChangedBatchCount++;
            foreach (var depth in depths)
                RecordMarketDepthCallback(depth, true);
        }

        protected override void OnMarketByOrdersChanged(IEnumerable<MarketByOrder> values)
        {
            base.OnMarketByOrdersChanged(values);

            if (values == null)
                return;

            _diagMarketByOrdersChangedBatchCount++;
            foreach (var _ in values)
                _diagMarketByOrdersChangedItemCount++;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 2)
                return;

            if (!_firstCalculateDiagnosticWritten)
            {
                WriteLifecycleDiagnostic("oncalculate", bar, DateTime.Now);
                _firstCalculateDiagnosticWritten = true;
            }

            ProcessMarketUpdate(CreateCandleMarketUpdate(bar));
        }

        private void ProcessMarketUpdate(MarketUpdate update)
        {
            var bar = update.Bar;
            if (bar < 2)
                return;

            var current = update.Candle;
            var marketUpdateTime = update.MarketTimeUtc;
            var marketPrice = update.Price;

            if (_lastProcessedMarketTime != DateTime.MinValue &&
                marketUpdateTime < _lastProcessedMarketTime &&
                ConvertToNewYorkTime(current.Time).Date == _currentNyDate)
            {
                ResetDay(ConvertToNewYorkTime(current.Time).Date);
            }

            if (!ShouldProcessMarketState(update))
                return;

            _activeMarketUpdateBar = bar;
            _activeMarketUpdateTime = marketUpdateTime;
            _activeMarketCandleTime = current.Time;

            var currentNyTime = ConvertToNewYorkTime(current.Time);
            var currentSignalNyTime = ConvertToNewYorkTime(marketUpdateTime);
            var closedBar = bar - 1;
            var closedCandle = GetCandle(closedBar);
            var closedNyTime = ConvertToNewYorkTime(closedCandle.Time);
            var targetDate = ReadTargetDate();

            if (targetDate == null)
                return;

            if (currentNyTime.Date != _currentNyDate)
                ResetDay(currentNyTime.Date);

            if (currentNyTime.Date != targetDate.Value.Date)
                return;

            TryEnsureOpeningRangeReady(bar, currentNyTime.Date);

            UpdateTradeResult(update);

            if (TryWriteTimeOver(update, currentSignalNyTime))
                return;

            UpdateSpeedClock(bar, current.Time);

            UpdateAPlusStructureFromBar(closedBar, closedCandle, closedNyTime);

            if (!_orReady)
                return;

            if (_tradeCreated || bar <= _orBar || !IsSignalWindow(currentSignalNyTime))
                return;

            UpdateAPlusStructureFromBar(bar, current, currentSignalNyTime);

            var score = CalculateLiveScore(
                current,
                bar,
                currentSignalNyTime,
                marketUpdateTime,
                marketPrice);
            TrackObservedScore(bar, currentSignalNyTime, update, score);
            var sharedSnapshot = SharedTradeSignalSnapshot.CaptureOrGet(
                currentNyTime.Date,
                _orLow,
                _orHigh,
                bar,
                marketUpdateTime,
                score,
                GetReplaySyncSignalPath(currentNyTime.Date),
                ExporterVersion);

            if (sharedSnapshot == null)
            {
                TrackRejectedScore(bar, currentSignalNyTime, score);
                return;
            }

            if (sharedSnapshot.Bar <= _lastSignalReadyBar)
                return;

            _lastSignalReadyBar = sharedSnapshot.Bar;
            ClearPendingScore();
            var snapshotCandle = GetCandle(sharedSnapshot.Bar);
            var snapshotNyTime = ConvertToNewYorkTime(sharedSnapshot.SignalTime);
            CreateTrade(sharedSnapshot.Bar, snapshotCandle, snapshotNyTime, sharedSnapshot.Signal);
            UpdateTradeResult(CreateSnapshotMarketUpdate(sharedSnapshot, snapshotCandle));

            if (update.Bar > sharedSnapshot.Bar ||
                update.MarketTimeUtc > sharedSnapshot.SignalTime ||
                update.Price != sharedSnapshot.Signal.EntryPrice)
            {
                UpdateTradeResult(update);
            }
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

            if (!plan.IsNormalSpeed && !plan.IsAPlusSpeed)
                ApplyDynamicImbalanceStop(candle, executionSide, plan);

            var hasMatchingAPlusStructure = score.HasAPlusStructure;
            var matchingAPlusSide = score.APlusStructureSide;
            var matchingAPlusPrice = score.APlusStructurePrice;
            var executionSideImbalanceCount = executionSide == "BUY"
                ? score.BuyImbalanceCount
                : score.SellImbalanceCount;
            var entryTimingSource = "SignalSnapshotTime";
            var entryUpdateTimeUtc = ConvertNewYorkTimeToUtc(nyTime);

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
                RawSpeedLabel = score.RawSpeedLabel,
                Volume = score.Volume,
                Delta = score.Delta,
                CumulativeDelta = score.CumulativeDelta,
                CumulativeDeltaSource = score.CumulativeDeltaSource,
                CvdEntry = score.CumulativeDelta,
                CvdPeak = score.CumulativeDelta,
                CvdCurrent = score.CumulativeDelta,
                CvdPullbackPercent = 0,
                CvdPullbackLabel = "Excelente",
                CvdExcellentCount = 1,
                CvdTotalSamples = 1,
                CvdLastSampleBar = bar,
                CvdLastSampleValue = score.CumulativeDelta,
                CvdLastCountedLabel = "Excelente",
                CvdWorstLabel = "Excelente",
                CvdLastStateTimeUtc = entryUpdateTimeUtc,
                CvdLastTimingSource = entryTimingSource,
                PreviousVolume = score.PreviousVolume,
                PreviousDelta = score.PreviousDelta,
                VolumeIncreasing = score.VolumeIncreasing,
                DeltaChange = score.DeltaChange,
                DeltaWithSide = score.DeltaWithSide,
                PriceAcceptedAfterImbalance = score.PriceAcceptedAfterImbalance,
                PriceRejectedAfterImbalance = score.PriceRejectedAfterImbalance,
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
                LastMfeTimeUtc = entryUpdateTimeUtc,
                Result = "OPEN",
                APlusStructure = hasMatchingAPlusStructure,
                APlusAbsorption = score.HasAPlusAbsorption,
                APlusSpeed = score.HasAPlusSpeedThreshold,
                APlusSpeedSetupConfirmed = score.HasAPlusSpeed,
                APlusSpeedThresholdTicksPerSecond = APlusSpeedTicksPerSecond,
                SignalSource = score.SignalSource,
                ImbalanceGroup3 = matchingAPlusSide,
                ImbalanceGroupPrice = matchingAPlusPrice,
                ImbalanceCount = Math.Max(score.BuyImbalanceCount, score.SellImbalanceCount),
                BuyImbalanceCount = score.BuyImbalanceCount,
                SellImbalanceCount = score.SellImbalanceCount,
                ExecutionSideImbalanceCount = executionSideImbalanceCount,
                InputSnapshot = new TradeInputSnapshot
                {
                    Version = ExporterVersion,
                    EntryDate = nyTime.Date,
                    DecisionTimestampNy = nyTime,
                    FeatureTimestampNy = nyTime,
                    EntryTimestampNy = nyTime,
                    FeatureTimestampUtc = entryUpdateTimeUtc,
                    EntryTimestampUtc = entryUpdateTimeUtc,
                    EntryBar = bar,
                    Side = executionSide,
                    SignalSource = score.SignalSource,
                    SpeedProfile = GetEntryProfile(executionSide, score.SpeedLabel),
                    EntryPrice = score.EntryPrice,
                    SlPriceAtEntry = plan.Sl,
                    TpPriceAtEntry = plan.Tp,
                    SlTicksAtEntry = plan.SlTicks,
                    TpTicksAtEntry = plan.TpTicks,
                    OrLow = score.OrLow,
                    OrHigh = score.OrHigh,
                    OrRangeTicks = score.OrRangeTicks,
                    VwapAtEntry = score.Vwap,
                    BodyAtEntry = score.BodyBreakoutTicks,
                    VolumeAtEntry = score.Volume,
                    DeltaAtEntry = score.Delta,
                    CumulativeDeltaAtEntry = score.CumulativeDelta,
                    CumulativeDeltaSourceAtEntry = score.CumulativeDeltaSource,
                    CvdCurrentAtEntry = score.CumulativeDelta,
                    CvdPeakAtEntry = score.CumulativeDelta,
                    CvdPullbackPctAtEntry = 0,
                    CvdLabelAtEntry = "Excelente",
                    CvdTotalSamplesAtEntry = 1,
                    PreviousVolumeAtEntry = score.PreviousVolume,
                    PreviousDeltaAtEntry = score.PreviousDelta,
                    VolumeIncreasingAtEntry = score.VolumeIncreasing,
                    DeltaChangeAtEntry = score.DeltaChange,
                    DeltaWithSideAtEntry = score.DeltaWithSide,
                    PriceAcceptedAfterImbalanceAtEntry = score.PriceAcceptedAfterImbalance,
                    PriceRejectedAfterImbalanceAtEntry = score.PriceRejectedAfterImbalance,
                    BreakoutSpeedAtEntry = score.SpeedLabel,
                    BreakoutTicksPerSecondAtEntry = score.BreakoutSpeed,
                    SpeedElapsedSecondsAtEntry = score.SpeedElapsedSeconds,
                    SpeedReplayFallbackAtEntry = score.SpeedUsedReplayFallback,
                    SpeedTimingSourceAtEntry = score.SpeedTimingSource,
                    RangeOkAtEntry = score.RangeOk,
                    BodyOkAtEntry = score.BodyOk,
                    VolumeOkAtEntry = score.VolumeOk,
                    DeltaOkAtEntry = score.DeltaOk,
                    TimeOkAtEntry = score.TimeOk,
                    VwapOkAtEntry = score.VwapOk,
                    SpeedOkAtEntry = score.SpeedValid,
                    ScoreAtEntry = score.Score,
                    RawSpeedLabelAtEntry = score.RawSpeedLabel,
                    APlusStructureAtEntry = hasMatchingAPlusStructure,
                    APlusAbsorptionAtEntry = score.HasAPlusAbsorption,
                    APlusSpeedAtEntry = score.HasAPlusSpeedThreshold,
                    APlusSpeedSetupConfirmedAtEntry = score.HasAPlusSpeed,
                    BuyImbalanceCountAtEntry = score.BuyImbalanceCount,
                    SellImbalanceCountAtEntry = score.SellImbalanceCount,
                    ExecutionSideImbalanceCountAtEntry = executionSideImbalanceCount,
                    ImbalanceGroup3AtEntry = matchingAPlusSide,
                    ImbalanceGroupPriceAtEntry = matchingAPlusPrice,
                    ImbalanceCountAtEntry = Math.Max(score.BuyImbalanceCount, score.SellImbalanceCount),
                    SpeedIgnoredByStructureAtEntry = score.SpeedIgnoredByStructure
                }
            };

            UpdateIntratradeOrderFlow(bar, score.Volume, score.Delta);
            _lastManagePrice = score.EntryPrice;
            _lastManageTimeUtc = DateTime.MinValue;
            _tradeCreated = true;
            // Side-channel para el Execution Manager (ChartStrategy). Aditivo:
            // no altera la operativa ni los CSV. La estrategia coloca las ordenes.
            // Usa archivo en disco para cruzar el limite de doble carga del DLL
            // (ATAS carga el mismo DLL desde Indicators/ y Strategies/ por separado,
            // lo que genera dos instancias estaticas distintas; el archivo es el
            // unico canal confiable entre ambas instancias).
            // FROZEN EXECUTION FILTER — DO NOT CHANGE.
            // Validated on 669 DST sessions (2022-06-21 to 2026-06-28):
            // A+ Speed alone: WR ~70% | A+ Speed + Range >= 140: WR 87.5%, PF 4.38, MaxDD $900.
            // OR < 140 ticks = insufficient momentum; 12 SL eliminated vs only 11 TP lost.
            if (score.OrRangeTicks >= 140m)
            {
                ExecutionSignalBus.Publish(new ExecutionSignalBus.PendingEntry
                {
                    SessionDate = nyTime.Date,
                    SignalTimeNy = nyTime,
                    Side = _trade.Side,
                    EntryPrice = _trade.Entry,
                    SlPrice = _trade.Sl,
                    IsAPlusSpeed = score.HasAPlusSpeedThreshold,
                    SpeedLabel = score.SpeedLabel,
                    OrRangeTicks = score.OrRangeTicks,
                    Bar = bar
                });
                StrategySignalFile.Write(new StrategySignalFile.SignalData
                {
                    SessionDate = nyTime.Date,
                    Side = _trade.Side,
                    EntryPrice = _trade.Entry,
                    SlPrice = _trade.Sl,
                    IsAPlusSpeed = score.HasAPlusSpeedThreshold,
                    Bar = bar
                });
            }
            InitializeDynamicTimeline(
                bar,
                score.EntryPrice,
                entryUpdateTimeUtc,
                entryTimingSource,
                nyTime);
            WriteTradeInputFile(nyTime.Date);
            WriteTradeFile(nyTime.Date);
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

            TradeManagerTpSlBeExit.EnforceMinimumOneToOneBracket(
                plan,
                executionSide,
                SetupTickSize);
        }

        private void UpdateTradeResult(MarketUpdate update)
        {
            if (_trade == null || _trade.Result != "OPEN")
                return;

            var bar = update.Bar;
            var candle = update.Candle;
            var marketUpdateTime = update.MarketTimeUtc;
            var marketPrice = update.Price;

            if (bar < _trade.EntryBar)
                return;

            var persistedExit = TryGetMatchingPersistedTradeExit();
            if (persistedExit != null &&
                TryApplyPersistedTradeExit(update, persistedExit))
            {
                return;
            }

            var manageTimingSource = update.Source;
            var manageTimeUtc = marketUpdateTime;
            decimal tradeHigh;
            decimal tradeLow;
            if (update.IsTradeEvent || update.IsSyntheticSnapshot)
            {
                tradeHigh = update.High;
                tradeLow = update.Low;
            }
            else
            {
                GetPostEntryTradeRange(bar, candle, out tradeHigh, out tradeLow);
            }

            UpdateIntratradeOrderFlow(bar, candle.Volume, candle.Delta);
            UpdateTradeExcursion(tradeHigh, tradeLow, manageTimeUtc);
            UpdateTradePathMetrics(marketPrice, manageTimeUtc, manageTimingSource);
            UpdateBestFavorablePrice(tradeHigh, tradeLow);
            UpdateCvdProfitLock();
            UpdateCvdPullback(bar, candle, manageTimeUtc, manageTimingSource);
            var manageNyTime = ConvertToNewYorkTime(manageTimeUtc);
            UpdateDynamicAlarmAnalytics(marketPrice, manageTimeUtc, manageTimingSource, manageNyTime);
            RecordDynamicTimelineSample(
                bar,
                marketPrice,
                manageTimeUtc,
                manageTimingSource,
                manageNyTime,
                "UPDATE");

            if (persistedExit != null && manageTimeUtc < persistedExit.ExitTimeUtc)
            {
                _lastManagePrice = marketPrice;
                _lastManageTimeUtc = manageTimeUtc;
                return;
            }

            if (TryApplyCvdRiskBracket())
                return;

            var adverseSpeed = CalculateAdverseSpeed(marketPrice, manageTimeUtc, manageTimingSource);

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
                CurrentPrice = marketPrice,
                HalfMfeExitMinMfeTicks = HalfMfeExitMinMfeTicks,
                FastExitMinMfeTicks = FastExitMinMfeTicks,
                FastExitPullbackTicks = FastExitPullbackTicks,
                FastExitAdverseSpeedTicksPerSecond = FastExitAdverseSpeedTicksPerSecond,
                AdverseSpeedTicksPerSecond = adverseSpeed,
                TickSize = SetupTickSize
            });

            if (!decision.IsClosed)
            {
                _lastManagePrice = marketPrice;
                _lastManageTimeUtc = manageTimeUtc;
                return;
            }

            _trade.Result = decision.Result;
            _trade.ExitPrice = ResolveExitPrice(decision);
            _trade.ExitTimeNy = manageNyTime;
            _trade.TpAndSlHitSameUpdate |= decision.HitTpAndSlSameUpdate;
            FinalizeDynamicAlarmAnalytics();
            RecordDynamicTimelineSample(
                bar,
                _trade.ExitPrice,
                manageTimeUtc,
                manageTimingSource,
                _trade.ExitTimeNy.Value,
                $"EXIT_{_trade.Result}",
                true);
            FlushDynamicTimelineBuffer();
            TryWritePersistedTradeExit(_currentNyDate);
            WriteTradeFile(_currentNyDate);
        }

        private bool TryApplyCvdRiskBracket()
        {
            if (_trade == null || _trade.Result != "OPEN")
                return false;

            if (_trade.CvdRiskBracketActive)
                return false;

            if (_trade.SpeedLabel == "normal speed")
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
                    CvdRiskBracketActive = _trade.CvdRiskBracketActive
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

            if (_trade.SpeedLabel == "normal speed")
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
                    CvdPullbackLabel = _trade.CvdPullbackLabel
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
                    PullbackTicks = CvdProfitLockPullbackTicks
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

            var elapsedSeconds = (double)NormalizeObservationElapsedSeconds(
                _lastManageTimeUtc,
                manageTimeUtc,
                timingSource);
            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
                elapsedSeconds = 1;
            // Floor sub-millisecond gaps so speed cannot explode to millions.
            elapsedSeconds = Math.Max(elapsedSeconds, MinSpeedIntervalSeconds);

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

        private void RecordTradeCallback(MarketDataArg trade, bool fromBatch)
        {
            if (trade == null)
                return;

            if (fromBatch)
                _diagOnNewTradesItemCount++;
            else
                _diagOnNewTradeCount++;

            _diagLastTradeTimeUtc = trade.Time;
            _diagLastTradePrice = trade.Price;
            _diagLastTradeVolume = trade.Volume;
        }

        private void RecordCumulativeTradeCallback(CumulativeTrade trade, bool isUpdate)
        {
            if (trade == null)
                return;

            if (isUpdate)
                _diagOnUpdateCumulativeTradeCount++;
            else
                _diagOnCumulativeTradeCount++;

            var tickCount = trade.Ticks == null ? 0 : trade.Ticks.Count;
            _diagOnCumulativeTradeTickCount += tickCount;
            _diagLastCumulativeTradeTimeUtc = trade.Time;
            _diagLastCumulativeTradePrice = trade.Lastprice;
            _diagLastCumulativeTradeVolume = trade.Volume;
        }

        private void RecordMarketDepthCallback(MarketDataArg depth, bool fromBatch)
        {
            if (depth == null)
                return;

            if (fromBatch)
                _diagMarketDepthsChangedItemCount++;
            else
                _diagMarketDepthChangedCount++;

            _diagLastMarketDepthTimeUtc = depth.Time;
            _diagLastMarketDepthPrice = depth.Price;
            _diagLastMarketDepthVolume = depth.Volume;
            _diagLastMarketDepthType = depth.DataType.ToString();
        }

        private void TrySubscribeMarketByOrderDataOnce()
        {
            if (_marketByOrderSubscriptionAttempted)
            {
                UnsubscribeFromTimer(TimeSpan.FromSeconds(1), TrySubscribeMarketByOrderDataOnce);
                return;
            }

            _marketByOrderSubscriptionAttempted = true;
            WriteLifecycleDiagnostic("mbo_subscribe_attempt", CurrentBar, DateTime.Now);

            try
            {
                _ = SubscribeMarketByOrderData();
                _marketByOrderSubscriptionRequested = true;
                WriteLifecycleDiagnostic("mbo_subscribe_called", CurrentBar, DateTime.Now);
            }
            catch
            {
                WriteLifecycleDiagnostic("mbo_subscribe_error", CurrentBar, DateTime.Now);
            }

            try
            {
                UnsubscribeFromTimer(TimeSpan.FromSeconds(1), TrySubscribeMarketByOrderDataOnce);
            }
            catch
            {
                // Timer cleanup is best-effort.
            }
        }

        private void WriteLifecycleDiagnostic(string eventName, int bar, DateTime localTime)
        {
            try
            {
                if (!Directory.Exists(_exportFolder))
                    Directory.CreateDirectory(_exportFolder);

                var filePath = Path.Combine(_exportFolder, "exporter_lifecycle_diagnostics.csv");
                var writeHeader = !File.Exists(filePath);
                using var writer = new StreamWriter(filePath, append: true);

                if (writeHeader)
                {
                    writer.WriteLine(string.Join(",",
                        "Exporter_VERSION",
                        "Event",
                        "LocalTime",
                        "Bar"));
                }

                writer.WriteLine(string.Join(",",
                    ExporterVersion,
                    eventName,
                    localTime.ToString("yyyy-MM-dd HH:mm:ss.fff", CultureInfo.InvariantCulture),
                    bar.ToString(CultureInfo.InvariantCulture)));
            }
            catch
            {
                // Lifecycle diagnostics are best-effort only.
            }
        }

        private bool TryWriteTimeOver(MarketUpdate update, DateTime nyTime)
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

            WriteFeedDiagnosticFile(nyTime.Date, nyTime);

            if (TryRecoverMissedReadyTradeBeforeTimeOver(update, nyTime))
                return false;

            _timeOverWritten = true;
            WriteTimeOverFile(nyTime.Date, nyTime);
            return true;
        }

        private bool TryRecoverMissedReadyTradeBeforeTimeOver(MarketUpdate currentUpdate, DateTime currentNyTime)
        {
            if (!_orReady || _tradeCreated || _trade != null)
                return false;

            var startBar = Math.Max(_orBar + 1, 0);

            for (var scanBar = startBar; scanBar <= currentUpdate.Bar; scanBar++)
            {
                var scanCandle = GetCandle(scanBar);
                var scanNyTime = ConvertToNewYorkTime(scanCandle.Time);

                if (scanNyTime.Date != currentNyTime.Date)
                    continue;

                if (!IsSignalWindow(scanNyTime))
                    continue;

                UpdateAPlusStructureFromBar(scanBar, scanCandle, scanNyTime);

                var scanUpdateTime = TryGetCandleUpdateTime(scanCandle, out _);
                var score = CalculateLiveScore(
                    scanCandle,
                    scanBar,
                    scanNyTime,
                    scanUpdateTime);
                TrackObservedScore(scanBar, scanNyTime, null, score);
                var sharedSnapshot = SharedTradeSignalSnapshot.CaptureOrGet(
                    scanNyTime.Date,
                    _orLow,
                    _orHigh,
                    scanBar,
                    scanUpdateTime,
                    score,
                    GetReplaySyncSignalPath(scanNyTime.Date),
                    ExporterVersion);

                if (sharedSnapshot == null)
                    continue;

                var snapshotCandle = GetCandle(sharedSnapshot.Bar);
                var signalNyTime = ConvertToNewYorkTime(sharedSnapshot.SignalTime);

                _lastSignalReadyBar = sharedSnapshot.Bar;
                ClearPendingScore();
                CreateTrade(sharedSnapshot.Bar, snapshotCandle, signalNyTime, sharedSnapshot.Signal);

                if (_trade == null)
                    return false;

                UpdateTradeResult(CreateSnapshotMarketUpdate(sharedSnapshot, snapshotCandle));
                UpdateTradeResult(currentUpdate);
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

        private void UpdateCvdPullback(int bar, dynamic candle, DateTime updateTimeUtc, string timingSource)
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
            RegisterCvdStateSample(bar, update.CvdCurrent, update.CvdPullbackLabel, updateTimeUtc, timingSource);
            _trade.CvdPullbackLabel = update.CvdPullbackLabel;
        }

        private void RegisterCvdStateSample(
            int bar,
            decimal currentCvd,
            string label,
            DateTime updateTimeUtc,
            string timingSource)
        {
            if (_trade == null || string.IsNullOrWhiteSpace(label))
                return;

            if (_trade.CvdLastSampleBar == bar &&
                _trade.CvdLastSampleValue == currentCvd &&
                string.Equals(_trade.CvdLastCountedLabel, label, StringComparison.Ordinal))
            {
                return;
            }

            var previousLabel = _trade.CvdLastCountedLabel;
            var elapsedSeconds = NormalizeObservationElapsedSeconds(
                _trade.CvdLastStateTimeUtc,
                updateTimeUtc,
                timingSource);

            if (elapsedSeconds > 0)
            {
                _trade.CvdObservedSeconds += elapsedSeconds;

                if (string.Equals(previousLabel, "Excelente", StringComparison.Ordinal))
                    _trade.CvdExcellentSeconds += elapsedSeconds;
            }

            _trade.CvdTotalSamples++;

            switch (label)
            {
                case "Excelente":
                    _trade.CvdExcellentCount++;
                    break;
                case "Normal":
                    _trade.CvdNormalCount++;
                    break;
                case "Advertencia":
                    _trade.CvdWarningCount++;
                    break;
                case "Riesgo de reversion":
                    _trade.CvdRiskReversalCount++;
                    break;
            }

            if (!string.Equals(previousLabel, label, StringComparison.Ordinal))
            {
                _trade.CvdLabelChanges++;

                if (string.Equals(previousLabel, "Excelente", StringComparison.Ordinal) &&
                    !string.Equals(label, "Excelente", StringComparison.Ordinal))
                {
                    _trade.CvdNegativeEpisodes++;
                }
            }

            if (GetCvdLabelSeverity(label) > GetCvdLabelSeverity(_trade.CvdWorstLabel))
                _trade.CvdWorstLabel = label;

            if (string.Equals(label, "Excelente", StringComparison.Ordinal))
            {
                _trade.CvdNonExcellentStartTimeUtc = DateTime.MinValue;
                _trade.CvdNonExcellentConsecutiveSamples = 0;
            }
            else
            {
                if (string.Equals(previousLabel, "Excelente", StringComparison.Ordinal) ||
                    _trade.CvdNonExcellentStartTimeUtc == DateTime.MinValue)
                {
                    _trade.CvdNonExcellentStartTimeUtc = updateTimeUtc;
                    _trade.CvdNonExcellentConsecutiveSamples = 1;
                }
                else
                {
                    _trade.CvdNonExcellentConsecutiveSamples++;
                }
            }

            _trade.CvdLastSampleBar = bar;
            _trade.CvdLastSampleValue = currentCvd;
            _trade.CvdLastCountedLabel = label;
            _trade.CvdLastStateTimeUtc = updateTimeUtc;
            _trade.CvdLastTimingSource = timingSource;
        }

        private static int GetCvdLabelSeverity(string label)
        {
            return label switch
            {
                "Normal" => 1,
                "Advertencia" => 2,
                "Riesgo de reversion" => 3,
                _ => 0
            };
        }

        private void UpdateDynamicAlarmAnalytics(
            decimal currentPrice,
            DateTime updateTimeUtc,
            string timingSource,
            DateTime alarmTimeNy)
        {
            if (_trade == null)
                return;

            var signedPnlTicks = CalculateSignedTradeTicks(currentPrice);

            if (_trade.DynamicAlarmTriggered)
            {
                UpdatePostAlarmAnalytics(signedPnlTicks);
                return;
            }

            var cvdIsNotExcellent =
                !string.Equals(_trade.CvdPullbackLabel, "Excelente", StringComparison.Ordinal);
            var pullbackThresholdReached =
                _trade.CurrentMaePullbackTicks >= DynamicAlarmMaePullbackTicks;
            var speedThresholdReached =
                _trade.CurrentMaeSpeedTicksPerSecond >= DynamicAlarmMaeSpeedTicksPerSecond;

            if (!cvdIsNotExcellent || (!pullbackThresholdReached && !speedThresholdReached))
                return;

            _trade.DynamicAlarmTriggered = true;
            _trade.DynamicAlarmTimeNy = alarmTimeNy;
            _trade.DynamicAlarmSecondsFromEntry = Math.Max(
                0,
                (decimal)(alarmTimeNy - _trade.EntryTimeNy).TotalSeconds);
            _trade.DynamicAlarmReason = pullbackThresholdReached && speedThresholdReached
                ? "BOTH"
                : pullbackThresholdReached
                    ? "CVD+PULLBACK"
                    : "CVD+SPEED";
            _trade.CvdLabelAtAlarm = _trade.CvdPullbackLabel;
            _trade.CvdPullbackPercentAtAlarm = _trade.CvdPullbackPercent;
            _trade.MaePullbackTicksAtAlarm = _trade.LargestMaePullbackTicks;
            _trade.MaeSpeedTicksPerSecondAtAlarm = _trade.MaxSpeedMaeDuringTrade;
            _trade.CurrentMaePullbackTicksAtAlarm = _trade.CurrentMaePullbackTicks;
            _trade.CurrentMaeSpeedTicksPerSecondAtAlarm = _trade.CurrentMaeSpeedTicksPerSecond;
            _trade.OpenPnlTicksAtAlarm = signedPnlTicks;
            _trade.MfeTicksAtAlarm = _trade.MfeTicks;
            _trade.DrawdownFromMfeTicksAtAlarm = Math.Max(0, _trade.MfeTicks - signedPnlTicks);
            _trade.MfeTpPercentAtAlarm = _trade.TpTicks > 0
                ? _trade.MfeTicks / _trade.TpTicks
                : 0;
            _trade.DistanceToSlTicksAtAlarm = CalculateDistanceToStopTicks(currentPrice);
            _trade.DistanceToTpTicksAtAlarm = CalculateDistanceToTargetTicks(currentPrice);
            _trade.SecondsSinceLastMfeAtAlarm = NormalizeObservationElapsedSeconds(
                _trade.LastMfeTimeUtc,
                updateTimeUtc,
                timingSource);
            _trade.CvdNonExcellentSecondsAtAlarm = NormalizeObservationElapsedSeconds(
                _trade.CvdNonExcellentStartTimeUtc,
                updateTimeUtc,
                timingSource);
            _trade.CvdNonExcellentConsecutiveSamplesAtAlarm =
                _trade.CvdNonExcellentConsecutiveSamples;
            _trade.CvdExcellentTimePercentBeforeAlarm = _trade.CvdObservedSeconds > 0
                ? _trade.CvdExcellentSeconds / _trade.CvdObservedSeconds
                : null;
            _trade.CvdWorstLabelBeforeAlarm = _trade.CvdWorstLabel;
            _trade.CvdExcellentCountAtAlarm = _trade.CvdExcellentCount;
            _trade.CvdNormalCountAtAlarm = _trade.CvdNormalCount;
            _trade.CvdWarningCountAtAlarm = _trade.CvdWarningCount;
            _trade.CvdRiskReversalCountAtAlarm = _trade.CvdRiskReversalCount;
            _trade.CvdTotalSamplesAtAlarm = _trade.CvdTotalSamples;
            _trade.AlarmOpenPnlTicks = signedPnlTicks;
            _trade.DynamicTrailHighWaterTicks = Math.Max(_trade.MfeTicks, signedPnlTicks);

            _trade.ResultTrail10 = InitializeTrailingSimulation(10m, signedPnlTicks);
            _trade.ResultTrail15 = InitializeTrailingSimulation(15m, signedPnlTicks);
            _trade.ResultTrail20 = InitializeTrailingSimulation(20m, signedPnlTicks);
            _trade.ResultBreakevenAtAlarm = signedPnlTicks <= 0
                ? signedPnlTicks
                : null;
        }

        private void UpdatePostAlarmAnalytics(decimal signedPnlTicks)
        {
            if (_trade == null || !_trade.DynamicAlarmTriggered)
                return;

            _trade.FutureMfeAfterAlarm = Math.Max(
                _trade.FutureMfeAfterAlarm,
                Math.Max(0, signedPnlTicks - _trade.AlarmOpenPnlTicks));
            _trade.FutureMaeAfterAlarm = Math.Max(
                _trade.FutureMaeAfterAlarm,
                Math.Max(0, _trade.AlarmOpenPnlTicks - signedPnlTicks));
            _trade.DynamicTrailHighWaterTicks = Math.Max(
                _trade.DynamicTrailHighWaterTicks,
                signedPnlTicks);

            _trade.ResultTrail10 = UpdateTrailingSimulation(
                _trade.ResultTrail10,
                10m,
                signedPnlTicks);
            _trade.ResultTrail15 = UpdateTrailingSimulation(
                _trade.ResultTrail15,
                15m,
                signedPnlTicks);
            _trade.ResultTrail20 = UpdateTrailingSimulation(
                _trade.ResultTrail20,
                20m,
                signedPnlTicks);

            if (!_trade.ResultBreakevenAtAlarm.HasValue && signedPnlTicks <= 0)
                _trade.ResultBreakevenAtAlarm = 0;
        }

        private decimal? InitializeTrailingSimulation(decimal trailingTicks, decimal signedPnlTicks)
        {
            if (_trade == null)
                return null;

            var trailingStopTicks = _trade.DynamicTrailHighWaterTicks - trailingTicks;

            return signedPnlTicks <= trailingStopTicks
                ? signedPnlTicks
                : null;
        }

        private decimal? UpdateTrailingSimulation(
            decimal? currentResult,
            decimal trailingTicks,
            decimal signedPnlTicks)
        {
            if (_trade == null || currentResult.HasValue)
                return currentResult;

            var trailingStopTicks = _trade.DynamicTrailHighWaterTicks - trailingTicks;

            return signedPnlTicks <= trailingStopTicks
                ? trailingStopTicks
                : null;
        }

        private void FinalizeDynamicAlarmAnalytics()
        {
            if (_trade == null ||
                !_trade.DynamicAlarmTriggered ||
                _trade.Result == "OPEN")
            {
                return;
            }

            var baselineTicks = TradeResultTicks();
            _trade.ResultTrail10 ??= baselineTicks;
            _trade.ResultTrail15 ??= baselineTicks;
            _trade.ResultTrail20 ??= baselineTicks;
            _trade.ResultBreakevenAtAlarm ??= baselineTicks;
        }

        private void InitializeDynamicTimeline(
            int bar,
            decimal currentPrice,
            DateTime updateTimeUtc,
            string timingSource,
            DateTime sampleTimeNy)
        {
            if (_trade == null)
                return;

            try
            {
                var timelineFolder = Path.Combine(_exportFolder, "dynamic_management_timeline");
                Directory.CreateDirectory(timelineFolder);

                _trade.TimelineFilePath = Path.Combine(
                    timelineFolder,
                    $"dynamic_timeline_{_trade.EntryDate:yyyy-MM-dd}_NY.csv");
                _trade.TimelineTradeId =
                    $"{_trade.EntryDate:yyyy-MM-dd}_{_trade.EntryTimeNy:HHmmss}_{_trade.Side}";
                _trade.TimelineLastObservationTimeUtc = updateTimeUtc;

                File.WriteAllText(
                    _trade.TimelineFilePath,
                    DynamicTimelineCsvHeader + Environment.NewLine);

                RecordDynamicTimelineSample(
                    bar,
                    currentPrice,
                    updateTimeUtc,
                    timingSource,
                    sampleTimeNy,
                    "ENTRY",
                    true);
                FlushDynamicTimelineBuffer();
            }
            catch
            {
                // Timeline analytics must never interrupt the trade exporter.
            }
        }

        private void RecordDynamicTimelineSample(
            int bar,
            decimal currentPrice,
            DateTime updateTimeUtc,
            string timingSource,
            DateTime sampleTimeNy,
            string requestedEvent,
            bool force = false)
        {
            if (_trade == null || string.IsNullOrWhiteSpace(_trade.TimelineFilePath))
                return;

            try
            {
                var rawElapsedSeconds =
                    _trade.TimelineLastObservationTimeUtc == DateTime.MinValue ||
                    updateTimeUtc == DateTime.MinValue
                        ? 0
                        : Math.Max(
                            0,
                            (decimal)(updateTimeUtc - _trade.TimelineLastObservationTimeUtc).TotalSeconds);
                var elapsedSinceObservation = NormalizeObservationElapsedSeconds(
                    _trade.TimelineLastObservationTimeUtc,
                    updateTimeUtc,
                    timingSource);

                if (elapsedSinceObservation > 0 && elapsedSinceObservation <= 300)
                    _trade.TimelineElapsedSeconds += elapsedSinceObservation;

                if (updateTimeUtc != DateTime.MinValue)
                    _trade.TimelineLastObservationTimeUtc = updateTimeUtc;

                var signedPnlTicks = CalculateSignedTradeTicks(currentPrice);
                var currentFavorableTicks = Math.Max(0, signedPnlTicks);
                var currentAdverseTicks = Math.Max(0, -signedPnlTicks);
                var drawdownFromMfeTicks = Math.Max(0, _trade.MfeTicks - signedPnlTicks);
                var cvdIsNotExcellent =
                    !string.Equals(_trade.CvdPullbackLabel, "Excelente", StringComparison.Ordinal);
                var currentPullbackThresholdReached =
                    _trade.CurrentMaePullbackTicks >= DynamicAlarmMaePullbackTicks;
                var currentSpeedThresholdReached =
                    _trade.CurrentMaeSpeedTicksPerSecond >= DynamicAlarmMaeSpeedTicksPerSecond;
                var causalAlarmCandidate =
                    cvdIsNotExcellent &&
                    (currentPullbackThresholdReached || currentSpeedThresholdReached);
                var legacyMaxAlarmCandidate =
                    cvdIsNotExcellent &&
                    (_trade.LargestMaePullbackTicks >= DynamicAlarmMaePullbackTicks ||
                     _trade.MaxSpeedMaeDuringTrade >= DynamicAlarmMaeSpeedTicksPerSecond);

                if (causalAlarmCandidate && !_trade.TimelineCausalAlarmCandidateActive)
                    _trade.TimelineCausalAlarmEpisode++;

                var cvdLabelChanged =
                    !string.Equals(
                        _trade.TimelineLastWrittenCvdLabel,
                        _trade.CvdPullbackLabel,
                        StringComparison.Ordinal);
                var causalAlarmChanged =
                    causalAlarmCandidate != _trade.TimelineLastWrittenCausalAlarmCandidate;
                var legacyAlarmChanged =
                    legacyMaxAlarmCandidate != _trade.TimelineLastWrittenLegacyAlarmCandidate;
                var dynamicAlarmChanged =
                    _trade.DynamicAlarmTriggered != _trade.TimelineLastWrittenDynamicAlarmTriggered;
                var resultChanged =
                    !string.Equals(
                        _trade.TimelineLastWrittenResult,
                        _trade.Result,
                        StringComparison.Ordinal);
                var enoughTimeElapsed =
                    _trade.TimelineElapsedSeconds - _trade.TimelineLastWrittenElapsedSeconds >=
                    DynamicTimelineSampleIntervalSeconds;

                if (!force &&
                    !cvdLabelChanged &&
                    !causalAlarmChanged &&
                    !legacyAlarmChanged &&
                    !dynamicAlarmChanged &&
                    !resultChanged &&
                    !enoughTimeElapsed)
                {
                    _trade.TimelineCausalAlarmCandidateActive = causalAlarmCandidate;
                    return;
                }

                var eventName = ResolveDynamicTimelineEvent(
                    requestedEvent,
                    cvdLabelChanged,
                    causalAlarmChanged,
                    causalAlarmCandidate,
                    dynamicAlarmChanged);
                var effectiveTimeNy = string.Equals(timingSource, "UtcNow", StringComparison.Ordinal)
                    ? _trade.EntryTimeNy.AddSeconds((double)_trade.TimelineElapsedSeconds)
                    : sampleTimeNy;
                var cvdNonExcellentSeconds = cvdIsNotExcellent
                    ? NormalizeObservationElapsedSeconds(
                        _trade.CvdNonExcellentStartTimeUtc,
                        updateTimeUtc,
                        timingSource)
                    : 0;
                var secondsSinceLastMfe = NormalizeObservationElapsedSeconds(
                    _trade.LastMfeTimeUtc,
                    updateTimeUtc,
                    timingSource);
                var cvdExcellentTimePercent = CalculateCvdExcellentTimePercentToNow(
                    updateTimeUtc,
                    timingSource);

                _trade.TimelineSequence++;
                _trade.TimelineBuffer.Add(string.Join(",",
                    EscapeCsv(DynamicTimelineVersion),
                    EscapeCsv(_trade.TimelineTradeId),
                    _trade.TimelineSequence.ToString(CultureInfo.InvariantCulture),
                    EscapeCsv(eventName),
                    effectiveTimeNy.ToString("yyyy-MM-dd HH:mm:ss.fff", CultureInfo.InvariantCulture),
                    FormatSeconds(_trade.TimelineElapsedSeconds),
                    EscapeCsv(timingSource),
                    FormatSeconds(NormalizeReplaySpeedMultiplier()),
                    FormatSeconds(rawElapsedSeconds),
                    FormatSeconds(elapsedSinceObservation),
                    bar.ToString(CultureInfo.InvariantCulture),
                    _trade.EntryDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _trade.EntryTimeNy.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    EscapeCsv(_trade.Side),
                    _trade.Score.ToString(CultureInfo.InvariantCulture),
                    FormatBool(IsBalancedFilterEligible()),
                    FormatPrice(_trade.Entry),
                    FormatPrice(_trade.Sl),
                    FormatPrice(_trade.Tp),
                    FormatPrice(currentPrice),
                    FormatSignedTicks(signedPnlTicks),
                    FormatTicks(currentFavorableTicks),
                    FormatTicks(currentAdverseTicks),
                    FormatTicks(_trade.MaeTicks),
                    FormatTicks(_trade.MfeTicks),
                    FormatTicks(drawdownFromMfeTicks),
                    FormatTicks(_trade.CurrentMaePullbackTicks),
                    FormatSeconds(_trade.CurrentMaeSpeedTicksPerSecond),
                    FormatTicks(_trade.LargestMaePullbackTicks),
                    FormatSeconds(_trade.MaxSpeedMaeDuringTrade),
                    FormatTicks(CalculateDistanceToStopTicks(currentPrice)),
                    FormatTicks(CalculateDistanceToTargetTicks(currentPrice)),
                    FormatSeconds(secondsSinceLastMfe),
                    FormatTicks(_trade.CvdCurrent),
                    FormatTicks(_trade.CvdPeak),
                    FormatTicks(_trade.CvdPullbackPercent),
                    EscapeCsv(_trade.CvdPullbackLabel),
                    FormatSeconds(cvdNonExcellentSeconds),
                    _trade.CvdNonExcellentConsecutiveSamples.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdExcellentCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdNormalCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdWarningCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdRiskReversalCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdTotalSamples.ToString(CultureInfo.InvariantCulture),
                    FormatNullableRatio(cvdExcellentTimePercent),
                    _trade.CvdNegativeEpisodes.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdLabelChanges.ToString(CultureInfo.InvariantCulture),
                    EscapeCsv(_trade.CvdWorstLabel),
                    FormatBool(currentPullbackThresholdReached),
                    FormatBool(currentSpeedThresholdReached),
                    FormatBool(causalAlarmCandidate),
                    FormatBool(legacyMaxAlarmCandidate),
                    _trade.TimelineCausalAlarmEpisode.ToString(CultureInfo.InvariantCulture),
                    FormatBool(_trade.DynamicAlarmTriggered),
                    EscapeCsv(_trade.DynamicAlarmReason),
                    EscapeCsv(_trade.Result),
                    FormatTicks(_trade.CurrentDelta),
                    FormatNullableTicks(_trade.MaxDeltaDuringTrade),
                    FormatNullableTicks(_trade.MinDeltaDuringTrade),
                    FormatTicks(_trade.CurrentVolume),
                    FormatBool(_trade.CurrentVolumeIncreasing),
                    FormatSeconds(_trade.CurrentMaeSpeed500Milliseconds),
                    FormatSeconds(_trade.CurrentMaeSpeed1Second),
                    FormatSeconds(_trade.CurrentMaeSpeed2Seconds),
                    FormatBool(_trade.TpAndSlHitSameUpdate),
                    FormatBool(IsTradeNotManageableByLatency())));

                _trade.TimelineLastWrittenElapsedSeconds = _trade.TimelineElapsedSeconds;
                _trade.TimelineLastWrittenCvdLabel = _trade.CvdPullbackLabel;
                _trade.TimelineLastWrittenCausalAlarmCandidate = causalAlarmCandidate;
                _trade.TimelineLastWrittenLegacyAlarmCandidate = legacyMaxAlarmCandidate;
                _trade.TimelineLastWrittenDynamicAlarmTriggered = _trade.DynamicAlarmTriggered;
                _trade.TimelineLastWrittenResult = _trade.Result;
                _trade.TimelineCausalAlarmCandidateActive = causalAlarmCandidate;

                if (_trade.TimelineBuffer.Count >= DynamicTimelineFlushRowCount)
                    FlushDynamicTimelineBuffer();
            }
            catch
            {
                // Timeline analytics must never interrupt trade management or CSV export.
            }
        }

        private static string ResolveDynamicTimelineEvent(
            string requestedEvent,
            bool cvdLabelChanged,
            bool causalAlarmChanged,
            bool causalAlarmCandidate,
            bool dynamicAlarmChanged)
        {
            if (!string.Equals(requestedEvent, "UPDATE", StringComparison.Ordinal))
                return requestedEvent;

            if (dynamicAlarmChanged)
                return "DYNAMIC_ALARM_TRIGGERED";

            if (causalAlarmChanged)
                return causalAlarmCandidate
                    ? "CAUSAL_ALARM_START"
                    : "CAUSAL_ALARM_END";

            if (cvdLabelChanged)
                return "CVD_LABEL_CHANGE";

            return "SAMPLE";
        }

        private decimal? CalculateCvdExcellentTimePercentToNow(
            DateTime updateTimeUtc,
            string timingSource)
        {
            if (_trade == null)
                return null;

            var observedSeconds = _trade.CvdObservedSeconds;
            var excellentSeconds = _trade.CvdExcellentSeconds;
            var currentStateSeconds = NormalizeObservationElapsedSeconds(
                _trade.CvdLastStateTimeUtc,
                updateTimeUtc,
                timingSource);

            observedSeconds += currentStateSeconds;

            if (string.Equals(_trade.CvdPullbackLabel, "Excelente", StringComparison.Ordinal))
                excellentSeconds += currentStateSeconds;

            return observedSeconds > 0
                ? excellentSeconds / observedSeconds
                : null;
        }

        private bool IsBalancedFilterEligible()
        {
            if (_trade == null)
                return false;

            var fridayAndHighScore =
                _trade.EntryDate.DayOfWeek == DayOfWeek.Friday &&
                _trade.Score >= 7;
            var sellInPreferredWindow =
                string.Equals(_trade.Side, "SELL", StringComparison.Ordinal) &&
                _trade.EntryTimeNy.TimeOfDay >= new TimeSpan(9, 33, 0) &&
                _trade.EntryTimeNy.TimeOfDay < new TimeSpan(9, 36, 0);

            return fridayAndHighScore || sellInPreferredWindow;
        }

        private void FlushDynamicTimelineBuffer()
        {
            if (_trade == null ||
                string.IsNullOrWhiteSpace(_trade.TimelineFilePath) ||
                _trade.TimelineBuffer.Count == 0)
            {
                return;
            }

            try
            {
                File.AppendAllLines(_trade.TimelineFilePath, _trade.TimelineBuffer);
                _trade.TimelineBuffer.Clear();
            }
            catch
            {
                // Preserve buffered samples for a later flush attempt.
            }
        }

        private static string EscapeCsv(string? value)
        {
            if (string.IsNullOrEmpty(value))
                return "";

            if (!value.Contains(',') &&
                !value.Contains('"') &&
                !value.Contains('\r') &&
                !value.Contains('\n'))
            {
                return value;
            }

            return $"\"{value.Replace("\"", "\"\"")}\"";
        }

        private decimal CalculateSignedTradeTicks(decimal currentPrice)
        {
            if (_trade == null)
                return 0;

            return _trade.Side == "BUY"
                ? RoundToTicks(currentPrice - _trade.Entry)
                : RoundToTicks(_trade.Entry - currentPrice);
        }

        private decimal CalculateDistanceToStopTicks(decimal currentPrice)
        {
            if (_trade == null)
                return 0;

            var distance = _trade.Side == "BUY"
                ? RoundToTicks(currentPrice - _trade.Sl)
                : RoundToTicks(_trade.Sl - currentPrice);

            return Math.Max(0, distance);
        }

        private decimal CalculateDistanceToTargetTicks(decimal currentPrice)
        {
            if (_trade == null)
                return 0;

            var distance = _trade.Side == "BUY"
                ? RoundToTicks(_trade.Tp - currentPrice)
                : RoundToTicks(currentPrice - _trade.Tp);

            return Math.Max(0, distance);
        }

        private decimal NormalizeObservationElapsedSeconds(
            DateTime previousTimeUtc,
            DateTime currentTimeUtc,
            string timingSource)
        {
            if (previousTimeUtc == DateTime.MinValue || currentTimeUtc == DateTime.MinValue)
                return 0;

            var elapsedSeconds = (currentTimeUtc - previousTimeUtc).TotalSeconds;

            if (elapsedSeconds <= 0)
                return 0;

            // Historical candle timestamps already advance in market time at
            // Replay X10. Only the UtcNow fallback measures wall-clock time and
            // therefore needs the replay multiplier.
            if (timingSource == "UtcNow")
                elapsedSeconds *= (double)NormalizeReplaySpeedMultiplier();

            return (decimal)elapsedSeconds;
        }

        private void UpdateTradeExcursion(decimal high, decimal low, DateTime updateTimeUtc)
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
            {
                _trade.MfeTicks = Math.Max(0, favorableTicks);
                _trade.LastMfeTimeUtc = updateTimeUtc;
            }

            if (adverseTicks > _trade.MaeTicks)
                _trade.MaeTicks = Math.Max(0, adverseTicks);
        }

        private void UpdateIntratradeOrderFlow(int bar, decimal volume, decimal delta)
        {
            if (_trade == null)
                return;

            _trade.CurrentVolume = volume;
            _trade.CurrentDelta = delta;
            UpdateDirectionalDeltaExtremes(delta);

            if (!_trade.HasOrderFlowSample)
            {
                _trade.HasOrderFlowSample = true;
                _trade.LastOrderFlowBar = bar;
                _trade.LastObservedVolume = volume;
                _trade.CurrentVolumeIncreasing = false;
                return;
            }

            if (_trade.LastOrderFlowBar == bar)
            {
                _trade.VolumeObservedSamples++;
                _trade.CurrentVolumeIncreasing = volume > _trade.LastObservedVolume;

                if (_trade.CurrentVolumeIncreasing)
                {
                    _trade.VolumeIncreaseSamples++;
                    _trade.VolumeIncreasedDuringTrade = true;
                }
            }
            else
            {
                // Candle volume resets when a new bar starts, so comparisons
                // are only meaningful between updates of the same candle.
                _trade.CurrentVolumeIncreasing = false;
            }

            _trade.LastOrderFlowBar = bar;
            _trade.LastObservedVolume = volume;
        }

        private void UpdateDirectionalDeltaExtremes(decimal delta)
        {
            if (_trade == null)
                return;

            if (_trade.Side == "BUY")
            {
                if (delta <= 0)
                    return;

                if (!_trade.MaxDeltaDuringTrade.HasValue ||
                    delta > _trade.MaxDeltaDuringTrade.Value)
                {
                    _trade.MaxDeltaDuringTrade = delta;
                }

                if (!_trade.MinDeltaDuringTrade.HasValue ||
                    delta < _trade.MinDeltaDuringTrade.Value)
                {
                    _trade.MinDeltaDuringTrade = delta;
                }

                return;
            }

            if (delta >= 0)
                return;

            // For SELL, "Max" is the strongest aligned negative delta
            // (for example -800) and "Min" is the weakest (-100).
            if (!_trade.MaxDeltaDuringTrade.HasValue ||
                delta < _trade.MaxDeltaDuringTrade.Value)
            {
                _trade.MaxDeltaDuringTrade = delta;
            }

            if (!_trade.MinDeltaDuringTrade.HasValue ||
                delta > _trade.MinDeltaDuringTrade.Value)
            {
                _trade.MinDeltaDuringTrade = delta;
            }
        }

        private void UpdateTradePathMetrics(decimal currentPrice, DateTime updateTimeUtc, string timingSource)
        {
            if (_trade == null)
                return;

            var favorableTicks = _trade.Side == "BUY"
                ? RoundToTicks(currentPrice - _trade.Entry)
                : RoundToTicks(_trade.Entry - currentPrice);
            var adverseTicks = _trade.Side == "BUY"
                ? RoundToTicks(_trade.Entry - currentPrice)
                : RoundToTicks(currentPrice - _trade.Entry);

            favorableTicks = Math.Max(0, favorableTicks);
            adverseTicks = Math.Max(0, adverseTicks);

            if (!_trade.HasPathSample)
            {
                _trade.HasPathSample = true;
                _trade.LastPathFavorableTicks = favorableTicks;
                _trade.LastPathAdverseTicks = adverseTicks;
                _trade.MfePullupStartTicks = favorableTicks;
                _trade.MaePullbackStartTicks = adverseTicks;
                _trade.LastPathUpdateTimeUtc = updateTimeUtc;
                _trade.PathObservations.Add(new PathObservation
                {
                    ElapsedSeconds = 0,
                    AdverseTicks = adverseTicks
                });
                return;
            }

            var normalizedElapsedSeconds = NormalizeObservationElapsedSeconds(
                _trade.LastPathUpdateTimeUtc,
                updateTimeUtc,
                timingSource);
            var elapsedSeconds = (double)normalizedElapsedSeconds;
            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
                elapsedSeconds = 1;
            // Floor sub-millisecond gaps: with real-ms timestamps two same-instant
            // updates are ~nanoseconds apart and MAE/MFE speed would blow up to
            // millions of ticks/sec. Only the speed divisor is floored; the
            // accumulated PathElapsedSeconds below keeps the raw normalized value.
            elapsedSeconds = Math.Max(elapsedSeconds, MinSpeedIntervalSeconds);

            if (normalizedElapsedSeconds > 0 && normalizedElapsedSeconds <= 300)
            {
                _trade.PathElapsedSeconds += normalizedElapsedSeconds;
                UpdateRollingMaeSpeeds(adverseTicks);
            }

            var favorableIncrease = favorableTicks - _trade.LastPathFavorableTicks;
            _trade.CurrentMaeSpeedTicksPerSecond = 0;

            if (favorableIncrease > 0)
            {
                if (!_trade.IsMfePullupActive)
                {
                    _trade.IsMfePullupActive = true;
                    _trade.MfePullupStartTicks = _trade.LastPathFavorableTicks;
                    _trade.NumberOfPullUpsDuringTrade++;
                }

                _trade.LargestMfePullupTicks = Math.Max(
                    _trade.LargestMfePullupTicks,
                    favorableTicks - _trade.MfePullupStartTicks);
                _trade.MaxSpeedMfeDuringTrade = Math.Max(
                    _trade.MaxSpeedMfeDuringTrade,
                    favorableIncrease / (decimal)elapsedSeconds);
            }
            else if (favorableIncrease < 0)
            {
                _trade.IsMfePullupActive = false;
            }

            var adverseIncrease = adverseTicks - _trade.LastPathAdverseTicks;
            if (adverseIncrease > 0)
            {
                if (!_trade.IsMaePullbackActive)
                {
                    _trade.IsMaePullbackActive = true;
                    _trade.MaePullbackStartTicks = _trade.LastPathAdverseTicks;
                    _trade.NumberOfPullbacksDuringTrade++;
                }

                _trade.LargestMaePullbackTicks = Math.Max(
                    _trade.LargestMaePullbackTicks,
                    adverseTicks - _trade.MaePullbackStartTicks);
                _trade.CurrentMaePullbackTicks = Math.Max(
                    0,
                    adverseTicks - _trade.MaePullbackStartTicks);
                _trade.CurrentMaeSpeedTicksPerSecond =
                    adverseIncrease / (decimal)elapsedSeconds;
                _trade.MaxSpeedMaeDuringTrade = Math.Max(
                    _trade.MaxSpeedMaeDuringTrade,
                    _trade.CurrentMaeSpeedTicksPerSecond);
            }
            else if (adverseIncrease < 0)
            {
                _trade.IsMaePullbackActive = false;
                _trade.CurrentMaePullbackTicks = 0;
            }

            _trade.LastPathFavorableTicks = favorableTicks;
            _trade.LastPathAdverseTicks = adverseTicks;
            _trade.LastPathUpdateTimeUtc = updateTimeUtc;
        }

        private void UpdateRollingMaeSpeeds(decimal adverseTicks)
        {
            if (_trade == null)
                return;

            _trade.PathObservations.Add(new PathObservation
            {
                ElapsedSeconds = _trade.PathElapsedSeconds,
                AdverseTicks = adverseTicks
            });

            var keepFrom = _trade.PathElapsedSeconds - 3m;
            while (_trade.PathObservations.Count > 1 &&
                   _trade.PathObservations[1].ElapsedSeconds < keepFrom)
            {
                _trade.PathObservations.RemoveAt(0);
            }

            _trade.CurrentMaeSpeed500Milliseconds =
                CalculateRollingMaeSpeed(adverseTicks, 0.5m);
            _trade.CurrentMaeSpeed1Second =
                CalculateRollingMaeSpeed(adverseTicks, 1m);
            _trade.CurrentMaeSpeed2Seconds =
                CalculateRollingMaeSpeed(adverseTicks, 2m);

            _trade.MaxMaeSpeed500Milliseconds = Math.Max(
                _trade.MaxMaeSpeed500Milliseconds,
                _trade.CurrentMaeSpeed500Milliseconds);
            _trade.MaxMaeSpeed1Second = Math.Max(
                _trade.MaxMaeSpeed1Second,
                _trade.CurrentMaeSpeed1Second);
            _trade.MaxMaeSpeed2Seconds = Math.Max(
                _trade.MaxMaeSpeed2Seconds,
                _trade.CurrentMaeSpeed2Seconds);
        }

        private decimal CalculateRollingMaeSpeed(decimal currentAdverseTicks, decimal windowSeconds)
        {
            if (_trade == null || _trade.PathElapsedSeconds < windowSeconds)
                return 0;

            var targetTime = _trade.PathElapsedSeconds - windowSeconds;
            PathObservation? baseline = null;

            for (var i = _trade.PathObservations.Count - 1; i >= 0; i--)
            {
                var observation = _trade.PathObservations[i];
                if (observation.ElapsedSeconds <= targetTime)
                {
                    baseline = observation;
                    break;
                }
            }

            if (baseline == null)
                return 0;

            var elapsedSeconds = _trade.PathElapsedSeconds - baseline.ElapsedSeconds;
            if (elapsedSeconds <= 0)
                return 0;

            return Math.Max(
                0,
                (currentAdverseTicks - baseline.AdverseTicks) / elapsedSeconds);
        }

        private void GetPostEntryTradeRange(int bar, dynamic candle, out decimal tradeHigh, out decimal tradeLow)
        {
            if (_trade == null)
            {
                tradeHigh = candle.High;
                tradeLow = candle.Low;
                return;
            }

            TradeManagerTpSlBeExit.GetPostEntryHitRange(
                bar == _trade.EntryBar,
                candle.High,
                candle.Low,
                candle.Close,
                _trade.EntryBarHighAtEntry,
                _trade.EntryBarLowAtEntry,
                out tradeHigh,
                out tradeLow);
        }

        private ScoreTradeSignal CalculateLiveScore(
            dynamic candle,
            int bar,
            DateTime nyTime,
            DateTime marketUpdateTime,
            decimal? currentPrice = null)
        {
            return _signalEngine.Calculate(bar, candle, new Func<int, dynamic>(GetCandle), new ScoreTradeSignalRequest
            {
                OrLow = _orLow,
                OrHigh = _orHigh,
                CurrentTime = nyTime,
                MarketUpdateTime = marketUpdateTime,
                CurrentPrice = currentPrice,
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

        private void UpdateSpeedClock(int bar, DateTime barStartMarketTime)
        {
            _signalEngine.UpdateSpeedClock(bar, barStartMarketTime);
        }

        private bool TryEnsureOpeningRangeReady(int currentBar, DateTime nyDate)
        {
            if (_orReady)
                return true;

            var startBar = Math.Max(currentBar - 1, 0);
            for (var scanBar = startBar; scanBar >= 0; scanBar--)
            {
                var scanCandle = GetCandle(scanBar);
                var scanNyTime = ConvertToNewYorkTime(scanCandle.Time);

                if (scanNyTime.Date < nyDate)
                    break;

                if (scanNyTime.Date != nyDate)
                    continue;

                if (scanNyTime.TimeOfDay != _openingTimeNy)
                    continue;

                _orHigh = scanCandle.High;
                _orLow = scanCandle.Low;
                _orBar = scanBar;
                _orReady = true;
                return true;
            }

            return false;
        }

        private MarketUpdate CreateTradeMarketUpdate(int bar, MarketDataArg trade)
        {
            var candle = GetCandle(bar);
            return CreateMarketUpdate(
                bar,
                candle,
                trade.Time,
                trade.Price,
                trade.Price,
                trade.Price,
                "MarketTradeTime",
                true,
                false);
        }

        private MarketUpdate CreateCandleMarketUpdate(int bar)
        {
            var candle = GetCandle(bar);
            var marketUpdateTime = ResolveMarketUpdateTime(bar, candle, out var timingSource);
            return CreateMarketUpdate(
                bar,
                candle,
                marketUpdateTime,
                Convert.ToDecimal(candle.Close),
                Convert.ToDecimal(candle.High),
                Convert.ToDecimal(candle.Low),
                timingSource,
                false,
                false);
        }

        private MarketUpdate CreateSnapshotMarketUpdate(SharedTradeSignalSnapshot.Snapshot snapshot, dynamic candle)
        {
            return CreateSignalMarketUpdate(
                snapshot.Bar,
                candle,
                snapshot.SignalTime,
                snapshot.Signal,
                "SignalSnapshotTime");
        }

        private MarketUpdate CreateSignalMarketUpdate(
            int bar,
            dynamic candle,
            DateTime signalTimeUtc,
            ScoreTradeSignal signal,
            string source)
        {
            var entryPrice = signal.EntryPrice != 0
                ? signal.EntryPrice
                : Convert.ToDecimal(candle.Close);

            return CreateMarketUpdate(
                bar,
                candle,
                signalTimeUtc,
                entryPrice,
                entryPrice,
                entryPrice,
                source,
                false,
                true);
        }

        private MarketUpdate CreateMarketUpdate(
            int bar,
            dynamic candle,
            DateTime marketUpdateTimeUtc,
            decimal price,
            decimal high,
            decimal low,
            string source,
            bool isTradeEvent,
            bool isSyntheticSnapshot)
        {
            return new MarketUpdate(
                bar,
                candle,
                marketUpdateTimeUtc,
                price,
                high,
                low,
                Convert.ToDecimal(candle.Volume),
                Convert.ToDecimal(candle.Delta),
                source,
                isTradeEvent,
                isSyntheticSnapshot,
                ++_marketUpdateSequence);
        }

        private DateTime TryGetCandleUpdateTime(dynamic candle, out string timingSource)
        {
            if (IsActiveMarketCandle(candle))
            {
                timingSource = "MarketTradeTime";
                return _activeMarketUpdateTime;
            }

            return SpeedClasification.TryGetCandleUpdateTime(candle, out timingSource);
        }

        private DateTime ResolveMarketUpdateTime(int bar, dynamic candle)
        {
            string timingSource;
            return ResolveMarketUpdateTime(bar, candle, out timingSource);
        }

        private DateTime ResolveMarketUpdateTime(int bar, dynamic candle, out string timingSource)
        {
            var candleUpdateTime = SpeedClasification.TryGetCandleUpdateTime(candle, out timingSource);
            if (timingSource != "UtcNow" && IsPlausibleMarketTime(candle.Time, candleUpdateTime))
                return candleUpdateTime;

            if (bar == CurrentBar - 1)
            {
                var marketTime = MarketTime;
                if (IsPlausibleMarketTime(candle.Time, marketTime))
                {
                    timingSource = "MarketTime";
                    return marketTime;
                }
            }

            timingSource = "CandleTime";
            return candle.Time;
        }

        private bool IsActiveMarketCandle(dynamic candle)
        {
            if (_activeMarketUpdateBar < 0 ||
                _activeMarketUpdateTime == DateTime.MinValue)
            {
                return false;
            }

            try
            {
                return candle.Time == _activeMarketCandleTime;
            }
            catch
            {
                return false;
            }
        }

        private static bool IsPlausibleMarketTime(DateTime candleTime, DateTime marketTime)
        {
            if (marketTime == DateTime.MinValue || marketTime < candleTime)
                return false;

            return marketTime - candleTime <= TimeSpan.FromDays(1);
        }

        private bool ShouldProcessMarketState(MarketUpdate update)
        {
            if (update.Bar == _lastProcessedMarketBar &&
                update.MarketTimeUtc == _lastProcessedMarketTime &&
                update.Price == _lastProcessedMarketClose &&
                update.High == _lastProcessedMarketHigh &&
                update.Low == _lastProcessedMarketLow &&
                update.Volume == _lastProcessedMarketVolume &&
                update.Delta == _lastProcessedMarketDelta &&
                string.Equals(update.Source, _lastProcessedMarketSource, StringComparison.Ordinal))
            {
                return false;
            }

            _lastProcessedMarketBar = update.Bar;
            _lastProcessedMarketTime = update.MarketTimeUtc;
            _lastProcessedMarketClose = update.Price;
            _lastProcessedMarketHigh = update.High;
            _lastProcessedMarketLow = update.Low;
            _lastProcessedMarketVolume = update.Volume;
            _lastProcessedMarketDelta = update.Delta;
            _lastProcessedMarketSource = update.Source;
            return true;
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

        private DateTime ConvertNewYorkTimeToUtc(DateTime newYorkTime)
        {
            var unspecified = DateTime.SpecifyKind(
                newYorkTime,
                DateTimeKind.Unspecified);
            return TimeZoneInfo.ConvertTimeToUtc(unspecified, _nyZone);
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

        private string GetReplaySyncSignalPath(DateTime nyDate)
        {
            return Path.Combine(
                _replaySyncSignalsFolder,
                $"score_trade_signal_snapshot_{nyDate:yyyy-MM-dd}_NY.json");
        }

        private string GetReplaySyncResultPath(DateTime nyDate)
        {
            return Path.Combine(
                _replaySyncResultsFolder,
                $"score_trade_result_snapshot_{nyDate:yyyy-MM-dd}_NY.json");
        }

        private PersistedTradeExit? TryGetMatchingPersistedTradeExit()
        {
            if (_trade == null || _trade.Result != "OPEN")
                return null;

            var snapshot = TryReadPersistedTradeExit(_trade.EntryDate);
            if (snapshot == null)
                return null;

            if (!IsPersistedTradeExitMatch(snapshot))
                return null;

            return snapshot;
        }

        private bool TryApplyPersistedTradeExit(
            MarketUpdate update,
            PersistedTradeExit snapshot)
        {
            if (_trade == null || _trade.Result != "OPEN")
                return false;

            if (update.MarketTimeUtc < snapshot.ExitTimeUtc)
                return false;

            // Adopt X1's canonical bracket so in-memory state matches the canonical
            // CSV row that is written below (snapshot.CsvRow). This keeps Telegram and
            // any later read consistent with the persisted X1 result.
            _trade.Sl = snapshot.Sl;
            _trade.Tp = snapshot.Tp;
            _trade.SlTicks = snapshot.SlTicks;
            _trade.TpTicks = snapshot.TpTicks;
            _trade.Result = snapshot.Result;
            _trade.ExitPrice = snapshot.ExitPrice;
            _trade.ExitTimeNy = snapshot.ExitTimeNy;
            _trade.TpAndSlHitSameUpdate |= snapshot.TpAndSlHitSameUpdate;
            _lastManagePrice = snapshot.ExitPrice;
            _lastManageTimeUtc = snapshot.ExitTimeUtc;
            FinalizeDynamicAlarmAnalytics();
            RecordDynamicTimelineSample(
                update.Bar,
                _trade.ExitPrice,
                snapshot.ExitTimeUtc,
                "PersistedExitSync",
                _trade.ExitTimeNy.Value,
                $"EXIT_{_trade.Result}",
                true);
            FlushDynamicTimelineBuffer();
            WriteTradeFile(_currentNyDate, snapshot.CsvRow);
            return true;
        }

        private PersistedTradeExit? TryReadPersistedTradeExit(DateTime nyDate)
        {
            var path = GetReplaySyncResultPath(nyDate);
            if (!File.Exists(path))
                return null;

            try
            {
                return JsonSerializer.Deserialize<PersistedTradeExit>(
                    File.ReadAllText(path),
                    ReplaySyncJsonOptions);
            }
            catch
            {
                return null;
            }
        }

        private bool IsPersistedTradeExitMatch(PersistedTradeExit snapshot)
        {
            if (_trade == null)
                return false;

            // Match on the entry identity only (date, bar, entry price, side, version).
            // The live Sl/Tp must NOT be part of the match: X1's dynamic management
            // (e.g. the CVD risk bracket) can move the bracket during the trade, so the
            // persisted X1 bracket legitimately differs from X10's live bracket. Matching
            // on Sl/Tp made X10 reject the canonical X1 exit and diverge (TpTicks 30 vs 60).
            return string.Equals(snapshot.ExporterVersion, ExporterVersion, StringComparison.Ordinal) &&
                snapshot.EntryDate.Date == _trade.EntryDate.Date &&
                snapshot.EntryBar == _trade.EntryBar &&
                snapshot.Entry == _trade.Entry &&
                string.Equals(snapshot.Side, _trade.Side, StringComparison.Ordinal) &&
                !string.IsNullOrWhiteSpace(snapshot.Result) &&
                snapshot.Result != "OPEN" &&
                snapshot.ExitTimeUtc != DateTime.MinValue;
        }

        private void TryWritePersistedTradeExit(DateTime nyDate)
        {
            if (_trade == null ||
                _trade.Result == "OPEN" ||
                _trade.ExitTimeNy == null)
            {
                return;
            }

            try
            {
                if (!Directory.Exists(_replaySyncResultsFolder))
                    Directory.CreateDirectory(_replaySyncResultsFolder);

                var path = GetReplaySyncResultPath(nyDate);
                if (File.Exists(path))
                    return;

                var snapshot = new PersistedTradeExit
                {
                    ExporterVersion = ExporterVersion,
                    EntryDate = _trade.EntryDate.Date,
                    EntryBar = _trade.EntryBar,
                    EntryTimeNy = _trade.EntryTimeNy,
                    Entry = _trade.Entry,
                    Sl = _trade.Sl,
                    Tp = _trade.Tp,
                    SlTicks = _trade.SlTicks,
                    TpTicks = _trade.TpTicks,
                    Side = _trade.Side,
                    Result = _trade.Result,
                    ExitPrice = _trade.ExitPrice,
                    ExitTimeNy = _trade.ExitTimeNy.Value,
                    ExitTimeUtc = ConvertNewYorkTimeToUtc(_trade.ExitTimeNy.Value),
                    TpAndSlHitSameUpdate = _trade.TpAndSlHitSameUpdate,
                    CsvRow = BuildTradeCsvRow()
                };

                File.WriteAllText(
                    path,
                    JsonSerializer.Serialize(snapshot, ReplaySyncJsonOptions));
            }
            catch
            {
                // Best-effort replay synchronizer. The live trade result is still exported.
            }
        }

        private void WriteTradeFile(DateTime nyDate, string? csvRowOverride = null)
        {
            if (_trade == null)
                return;

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var filePath = Path.Combine(
                _exportFolder,
                $"score_trade_result_{nyDate:yyyy-MM-dd}_NY.csv"
            );

            var csvRow = string.IsNullOrWhiteSpace(csvRowOverride)
                ? BuildTradeCsvRow()
                : csvRowOverride.TrimEnd('\r', '\n');

            File.WriteAllText(
                filePath,
                CsvHeader + Environment.NewLine +
                csvRow + Environment.NewLine
            );

            WriteTradeResultFile(nyDate);
            WriteFeedDiagnosticFile(nyDate, _trade.ExitTimeNy ?? _trade.EntryTimeNy);

            if (_trade.Result != "OPEN")
            {
                TelegramTradeNotifier.QueueTerminalResult(
                    _exportFolder,
                    nyDate,
                    BuildTelegramTradeMessage());
            }
        }

        private void WriteTradeInputFile(DateTime nyDate)
        {
            if (_trade?.InputSnapshot == null)
                return;

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var filePath = Path.Combine(_exportFolder, TradeInputCsvFileName);
            UpsertCsvRow(
                filePath,
                TradeInputCsvHeader,
                BuildTradeInputCsvRow(_trade.InputSnapshot),
                1,
                4);
        }

        private void WriteTradeResultFile(DateTime nyDate)
        {
            if (_trade == null)
                return;

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var filePath = Path.Combine(_exportFolder, TradeResultCsvFileName);
            UpsertCsvRow(
                filePath,
                TradeResultCsvHeader,
                BuildTradeResultCsvRow(),
                1,
                2);
        }

        private static void UpsertCsvRow(
            string filePath,
            string header,
            string row,
            int keyColumnA,
            int keyColumnB)
        {
            var newParts = SplitCsvRow(row);
            if (newParts.Count <= Math.Max(keyColumnA, keyColumnB))
                return;

            var newKeyA = newParts[keyColumnA];
            var newKeyB = newParts[keyColumnB];
            var lines = new List<string> { header };
            var replaced = false;

            if (File.Exists(filePath))
            {
                var existing = File.ReadAllLines(filePath);
                if (existing.Length > 0 && string.Equals(existing[0], header, StringComparison.Ordinal))
                {
                    for (var i = 1; i < existing.Length; i++)
                    {
                        var line = existing[i];
                        if (string.IsNullOrWhiteSpace(line))
                            continue;

                        var parts = SplitCsvRow(line);
                        var isSameKey =
                            parts.Count > Math.Max(keyColumnA, keyColumnB) &&
                            string.Equals(parts[keyColumnA], newKeyA, StringComparison.Ordinal) &&
                            string.Equals(parts[keyColumnB], newKeyB, StringComparison.Ordinal);

                        if (isSameKey)
                        {
                            if (!replaced)
                            {
                                lines.Add(row);
                                replaced = true;
                            }
                        }
                        else
                        {
                            lines.Add(line);
                        }
                    }
                }
            }

            if (!replaced)
                lines.Add(row);

            File.WriteAllLines(filePath, lines);
        }

        private static List<string> SplitCsvRow(string row)
        {
            var values = new List<string>();
            var current = "";
            var inQuotes = false;

            for (var i = 0; i < row.Length; i++)
            {
                var ch = row[i];
                if (ch == '"')
                {
                    if (inQuotes && i + 1 < row.Length && row[i + 1] == '"')
                    {
                        current += '"';
                        i++;
                    }
                    else
                    {
                        inQuotes = !inQuotes;
                    }

                    continue;
                }

                if (ch == ',' && !inQuotes)
                {
                    values.Add(current);
                    current = "";
                    continue;
                }

                current += ch;
            }

            values.Add(current);
            return values;
        }

        private string BuildTradeInputCsvRow(TradeInputSnapshot input)
        {
            return string.Join(",",
                ExporterVersion,
                input.EntryDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                input.DecisionTimestampNy.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                input.FeatureTimestampNy.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                input.EntryTimestampNy.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                input.EntryBar.ToString(CultureInfo.InvariantCulture),
                EscapeCsv(input.Side),
                EscapeCsv(input.SignalSource),
                EscapeCsv(input.SpeedProfile),
                FormatPrice(input.EntryPrice),
                FormatPrice(input.SlPriceAtEntry),
                FormatPrice(input.TpPriceAtEntry),
                FormatTicks(input.SlTicksAtEntry),
                FormatTicks(input.TpTicksAtEntry),
                FormatPrice(input.OrLow),
                FormatPrice(input.OrHigh),
                FormatTicks(input.OrRangeTicks),
                FormatPrice(input.VwapAtEntry),
                FormatTicks(input.BodyAtEntry),
                FormatTicks(input.VolumeAtEntry),
                FormatTicks(input.DeltaAtEntry),
                FormatTicks(input.CumulativeDeltaAtEntry),
                EscapeCsv(input.CumulativeDeltaSourceAtEntry),
                FormatTicks(input.CvdCurrentAtEntry),
                FormatTicks(input.CvdPeakAtEntry),
                FormatTicks(input.CvdPullbackPctAtEntry),
                EscapeCsv(input.CvdLabelAtEntry),
                input.CvdTotalSamplesAtEntry.ToString(CultureInfo.InvariantCulture),
                FormatTicks(input.PreviousVolumeAtEntry),
                FormatTicks(input.PreviousDeltaAtEntry),
                FormatBool(input.VolumeIncreasingAtEntry),
                FormatTicks(input.DeltaChangeAtEntry),
                FormatBool(input.DeltaWithSideAtEntry),
                FormatBool(input.PriceAcceptedAfterImbalanceAtEntry),
                FormatBool(input.PriceRejectedAfterImbalanceAtEntry),
                EscapeCsv(input.BreakoutSpeedAtEntry),
                FormatTicks(input.BreakoutTicksPerSecondAtEntry),
                FormatSeconds(input.SpeedElapsedSecondsAtEntry),
                FormatBool(input.SpeedReplayFallbackAtEntry),
                EscapeCsv(input.SpeedTimingSourceAtEntry),
                FormatBool(input.RangeOkAtEntry),
                FormatBool(input.BodyOkAtEntry),
                FormatBool(input.VolumeOkAtEntry),
                FormatBool(input.DeltaOkAtEntry),
                FormatBool(input.TimeOkAtEntry),
                FormatBool(input.VwapOkAtEntry),
                FormatBool(input.SpeedOkAtEntry),
                input.ScoreAtEntry.ToString(CultureInfo.InvariantCulture),
                EscapeCsv(input.RawSpeedLabelAtEntry),
                FormatBool(input.APlusStructureAtEntry),
                FormatBool(input.APlusAbsorptionAtEntry),
                FormatBool(input.APlusSpeedAtEntry),
                FormatBool(input.APlusSpeedSetupConfirmedAtEntry),
                input.BuyImbalanceCountAtEntry.ToString(CultureInfo.InvariantCulture),
                input.SellImbalanceCountAtEntry.ToString(CultureInfo.InvariantCulture),
                input.ExecutionSideImbalanceCountAtEntry.ToString(CultureInfo.InvariantCulture),
                EscapeCsv(input.ImbalanceGroup3AtEntry),
                FormatNullablePrice(input.ImbalanceGroupPriceAtEntry),
                input.ImbalanceCountAtEntry.ToString(CultureInfo.InvariantCulture),
                FormatBool(input.SpeedIgnoredByStructureAtEntry),
                input.FeatureTimestampUtc.ToString("o", CultureInfo.InvariantCulture),
                input.EntryTimestampUtc.ToString("o", CultureInfo.InvariantCulture));
        }

        private string BuildTradeResultCsvRow()
        {
            if (_trade == null)
                return "";

            var outcome = new TradeOutcome();
            outcome.CsvFields.AddRange(new[]
            {
                ExporterVersion,
                _trade.EntryDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                _trade.EntryTimeNy.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                _trade.ExitTimeNy.HasValue
                    ? _trade.ExitTimeNy.Value.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture)
                    : "",
                FormatExitTimeNy(),
                FormatTradeDuration(),
                _trade.EntryBar.ToString(CultureInfo.InvariantCulture),
                EscapeCsv(_trade.Side),
                FormatPrice(_trade.Entry),
                EscapeCsv(_trade.Result),
                FormatExitPrice(),
                _trade.Result == "OPEN" ? "" : FormatSignedTicks(TradeResultTicks()),
                FormatTicks(_trade.MaeTicks),
                FormatTicks(_trade.MfeTicks),
                FormatTicks(_trade.LargestMaePullbackTicks),
                FormatTicks(_trade.LargestMfePullupTicks),
                _trade.NumberOfPullbacksDuringTrade.ToString(CultureInfo.InvariantCulture),
                _trade.NumberOfPullUpsDuringTrade.ToString(CultureInfo.InvariantCulture),
                FormatSeconds(_trade.MaxSpeedMaeDuringTrade),
                FormatSeconds(_trade.MaxSpeedMfeDuringTrade),
                FormatPrice(_trade.Sl),
                FormatPrice(_trade.Tp),
                FormatTicks(_trade.SlTicks),
                FormatTicks(_trade.TpTicks),
                FormatTicks(_trade.CvdCurrent),
                FormatTicks(_trade.CvdPeak),
                FormatTicks(_trade.CvdPullbackPercent),
                EscapeCsv(_trade.CvdPullbackLabel),
                EscapeCsv(_trade.CvdWorstLabel),
                _trade.CvdExcellentCount.ToString(CultureInfo.InvariantCulture),
                _trade.CvdNormalCount.ToString(CultureInfo.InvariantCulture),
                _trade.CvdWarningCount.ToString(CultureInfo.InvariantCulture),
                _trade.CvdRiskReversalCount.ToString(CultureInfo.InvariantCulture),
                _trade.CvdTotalSamples.ToString(CultureInfo.InvariantCulture),
                FormatCvdExcellentPercent(),
                _trade.CvdNegativeEpisodes.ToString(CultureInfo.InvariantCulture),
                _trade.CvdLabelChanges.ToString(CultureInfo.InvariantCulture),
                FormatBool(_trade.DynamicAlarmTriggered),
                FormatBool(_trade.TpAndSlHitSameUpdate),
                CalculateResultAfterSlippage().HasValue
                    ? FormatSignedTicks(CalculateResultAfterSlippage()!.Value)
                    : "",
                FormatBool(_trade.VolumeIncreasedDuringTrade),
                _trade.VolumeIncreaseSamples.ToString(CultureInfo.InvariantCulture),
                _trade.VolumeObservedSamples.ToString(CultureInfo.InvariantCulture),
                FormatNullableRatio(CalculateVolumeIncreasingPercent()),
                FormatNullableTicks(_trade.MaxDeltaDuringTrade),
                FormatNullableTicks(_trade.MinDeltaDuringTrade)
            });

            return string.Join(",", outcome.CsvFields);
        }

        private string BuildTradeCsvRow()
        {
            if (_trade == null)
                return "";

            return string.Join(",",
                    ExporterVersion,
                    _trade.EntryDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _trade.EntryTimeNy.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    FormatExitTimeNy(),
                    FormatTradeDuration(),
                    _trade.EntryTimeNy.Second.ToString(CultureInfo.InvariantCulture),
                    _trade.EntryBar.ToString(CultureInfo.InvariantCulture),
                    FormatPrice(_trade.OrLow),
                    FormatPrice(_trade.OrHigh),
                    FormatTicks(_trade.OrRangeTicks),
                    FormatPrice(_trade.Vwap),
                    FormatTicks(_trade.BodyBreakoutTicks),
                    FormatTicks(_trade.Volume),
                    FormatTicks(_trade.Delta),
                    FormatTicks(_trade.CvdEntry),
                    _trade.CumulativeDeltaSource,
                    FormatTicks(_trade.CvdPeak),
                    FormatTicks(_trade.CvdCurrent),
                    FormatTicks(_trade.CvdPullbackPercent),
                    _trade.CvdPullbackLabel,
                    _trade.CvdExcellentCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdNormalCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdWarningCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdRiskReversalCount.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdTotalSamples.ToString(CultureInfo.InvariantCulture),
                    FormatCvdExcellentPercent(),
                    _trade.CvdNegativeEpisodes.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdLabelChanges.ToString(CultureInfo.InvariantCulture),
                    _trade.CvdWorstLabel,
                    BuildDynamicAlarmCsvFields(),
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
                    FormatTicks(_trade.LargestMaePullbackTicks),
                    FormatTicks(_trade.LargestMfePullupTicks),
                    _trade.NumberOfPullbacksDuringTrade.ToString(CultureInfo.InvariantCulture),
                    _trade.NumberOfPullUpsDuringTrade.ToString(CultureInfo.InvariantCulture),
                    FormatSeconds(_trade.MaxSpeedMaeDuringTrade),
                    FormatSeconds(_trade.MaxSpeedMfeDuringTrade),
                    FormatBool(_trade.APlusStructure),
                    FormatBool(_trade.APlusAbsorption),
                    FormatBool(_trade.APlusSpeed),
                    _trade.ImbalanceGroup3,
                    FormatNullablePrice(_trade.ImbalanceGroupPrice),
                    _trade.ImbalanceCount.ToString(CultureInfo.InvariantCulture),
                    FormatBool(_trade.SpeedIgnoredByStructure),
                    BuildExtendedTelemetryCsvFields()
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
                CsvHeader + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    nyTime.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    "", // ExitTime_NY
                    "", // Trade_Duration
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
                    "", // Cvd_Excelente_Count
                    "", // Cvd_Normal_Count
                    "", // Cvd_Advertencia_Count
                    "", // Cvd_Riesgo_Reversion_Count
                    "", // Cvd_Total_Samples
                    "", // Cvd_Excelente_Pct
                    "", // Cvd_Negative_Episodes
                    "", // Cvd_Label_Changes
                    "", // Cvd_Worst_Label
                    BuildEmptyDynamicAlarmCsvFields(),
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
                    "", // Largest_MAE_pullback_ticks
                    "", // Largest_MFE_pullup_ticks
                    "", // Number_of_Pullbacks_during_Trade
                    "", // Number_of_PullUps_during_Trade
                    "", // Max_Speed_MAE_during_trade
                    "", // Max_Speed_MFE_during_trade
                    FormatBool(_hasAPlusStructure),
                    "FALSE",
                    "FALSE",
                    _aPlusStructureSide,
                    FormatNullablePrice(_aPlusStructurePrice),
                    _aPlusStructureCount.ToString(CultureInfo.InvariantCulture),
                    "FALSE",
                    BuildEmptyExtendedTelemetryCsvFields()
                ) + Environment.NewLine
            );

            var timeOverBalance = UpdateAndGetTelegramBalance(nyDate.Date, 0m);
            TelegramTradeNotifier.QueueTerminalResult(
                _exportFolder,
                nyDate,
                $"EW ORB NQ | {nyDate:yyyy-MM-dd}\nTIME OVER\nBalance: {timeOverBalance:$#,##0}");
        }

        private string BuildTelegramTradeMessage()
        {
            if (_trade == null)
                return "";

            var offset = _nyZone.GetUtcOffset(_trade.EntryDate);
            var utcLabel = (int)offset.TotalHours == -4 ? "UTC-4 (EDT)" : "UTC-5 (EST)";
            var pnl = TradeResultTicks() * TickValueUsd * TelegramContracts;
            var balance = UpdateAndGetTelegramBalance(_trade.EntryDate.Date, pnl);

            return string.Join(
                Environment.NewLine,
                $"EW ORB NQ | {_trade.EntryDate:yyyy-MM-dd}",
                $"{_trade.Result} {_trade.Side} | {_trade.EntryTimeNy:HH:mm:ss} NY ({utcLabel})",
                $"PnL: {pnl:+$0;-$0} | {TelegramContracts}c",
                $"Balance: {balance:$#,##0}",
                $"Duración: {FormatTradeDuration()}");
        }

        // Balance corrido persistido por fecha (idempotente: X1/X10/re-runs de la
        // misma fecha sobrescriben su entrada, no doble-cuentan). Balance =
        // TelegramStartingBalance + suma de PnL de todas las fechas registradas.
        private string TelegramBalanceFile =>
            System.IO.Path.Combine(_exportFolder, "telegram_balance.json");

        private decimal UpdateAndGetTelegramBalance(DateTime nyDate, decimal pnl)
        {
            var key = nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            try
            {
                var map = new Dictionary<string, decimal>();
                if (File.Exists(TelegramBalanceFile))
                {
                    var json = File.ReadAllText(TelegramBalanceFile);
                    if (!string.IsNullOrWhiteSpace(json))
                        map = JsonSerializer.Deserialize<Dictionary<string, decimal>>(json)
                              ?? new Dictionary<string, decimal>();
                }

                map[key] = pnl;   // overwrite => idempotente por fecha

                if (!Directory.Exists(_exportFolder))
                    Directory.CreateDirectory(_exportFolder);
                File.WriteAllText(TelegramBalanceFile, JsonSerializer.Serialize(map));

                decimal sum = 0m;
                foreach (var v in map.Values) sum += v;
                return TelegramStartingBalance + sum;
            }
            catch
            {
                // Si falla la persistencia, al menos refleja este trade.
                return TelegramStartingBalance + pnl;
            }
        }

        private void WriteFeedDiagnosticFile(DateTime nyDate, DateTime sampleNyTime)
        {
            try
            {
                if (!Directory.Exists(_exportFolder))
                    Directory.CreateDirectory(_exportFolder);

                var cacheStats = ReadTradeCacheStats(nyDate);
                var filePath = Path.Combine(
                    _exportFolder,
                    $"market_feed_diagnostics_{nyDate:yyyy-MM-dd}_NY.csv");

                File.WriteAllText(
                    filePath,
                    string.Join(",",
                        "Exporter_VERSION",
                        "fecha",
                        "SampleTime_NY",
                        "OnNewTrade_Count",
                        "OnNewTrades_Batches",
                        "OnNewTrades_Items",
                        "OnCumulativeTrade_Count",
                        "OnUpdateCumulativeTrade_Count",
                        "CumulativeTrade_Tick_Count",
                        "MBO_Subscription_Attempted",
                        "MBO_Subscription_Requested",
                        "MarketDepthChanged_Count",
                        "MarketDepthsChanged_Batches",
                        "MarketDepthsChanged_Items",
                        "MarketByOrdersChanged_Batches",
                        "MarketByOrdersChanged_Items",
                        "TradeCache_Count",
                        "TradeCache_SignalWindow_Count",
                        "TradeCache_First_NY",
                        "TradeCache_Last_NY",
                        "LastTradeCallback_NY",
                        "LastTradeCallback_Price",
                        "LastTradeCallback_Volume",
                        "LastCumulativeCallback_NY",
                        "LastCumulativeCallback_Price",
                        "LastCumulativeCallback_Volume",
                        "LastMarketDepthCallback_NY",
                        "LastMarketDepthCallback_Price",
                        "LastMarketDepthCallback_Volume",
                        "LastMarketDepthCallback_Type") +
                    Environment.NewLine +
                    string.Join(",",
                        ExporterVersion,
                        nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                        sampleNyTime == DateTime.MinValue
                            ? ""
                            : sampleNyTime.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                        _diagOnNewTradeCount.ToString(CultureInfo.InvariantCulture),
                        _diagOnNewTradesBatchCount.ToString(CultureInfo.InvariantCulture),
                        _diagOnNewTradesItemCount.ToString(CultureInfo.InvariantCulture),
                        _diagOnCumulativeTradeCount.ToString(CultureInfo.InvariantCulture),
                        _diagOnUpdateCumulativeTradeCount.ToString(CultureInfo.InvariantCulture),
                        _diagOnCumulativeTradeTickCount.ToString(CultureInfo.InvariantCulture),
                        FormatBool(_marketByOrderSubscriptionAttempted),
                        FormatBool(_marketByOrderSubscriptionRequested),
                        _diagMarketDepthChangedCount.ToString(CultureInfo.InvariantCulture),
                        _diagMarketDepthsChangedBatchCount.ToString(CultureInfo.InvariantCulture),
                        _diagMarketDepthsChangedItemCount.ToString(CultureInfo.InvariantCulture),
                        _diagMarketByOrdersChangedBatchCount.ToString(CultureInfo.InvariantCulture),
                        _diagMarketByOrdersChangedItemCount.ToString(CultureInfo.InvariantCulture),
                        cacheStats.TotalCount.ToString(CultureInfo.InvariantCulture),
                        cacheStats.SignalWindowCount.ToString(CultureInfo.InvariantCulture),
                        FormatCallbackNyTime(cacheStats.FirstTradeTimeUtc),
                        FormatCallbackNyTime(cacheStats.LastTradeTimeUtc),
                        FormatCallbackNyTime(_diagLastTradeTimeUtc),
                        FormatNullablePrice(_diagLastTradePrice),
                        FormatTicks(_diagLastTradeVolume),
                        FormatCallbackNyTime(_diagLastCumulativeTradeTimeUtc),
                        FormatNullablePrice(_diagLastCumulativeTradePrice),
                        FormatTicks(_diagLastCumulativeTradeVolume),
                        FormatCallbackNyTime(_diagLastMarketDepthTimeUtc),
                        FormatNullablePrice(_diagLastMarketDepthPrice),
                        FormatTicks(_diagLastMarketDepthVolume),
                        _diagLastMarketDepthType) +
                    Environment.NewLine);
            }
            catch
            {
                // Diagnostics must never block export or Telegram.
            }
        }

        private FeedCacheStats ReadTradeCacheStats(DateTime nyDate)
        {
            var stats = new FeedCacheStats();

            try
            {
                var cache = GetTradesCache(TimeSpan.FromMinutes(30));
                var items = cache?.CachedItems;
                if (items == null)
                    return stats;

                foreach (var item in items)
                {
                    if (item == null)
                        continue;

                    stats.TotalCount++;

                    if (stats.FirstTradeTimeUtc == DateTime.MinValue ||
                        item.Time < stats.FirstTradeTimeUtc)
                    {
                        stats.FirstTradeTimeUtc = item.Time;
                    }

                    if (stats.LastTradeTimeUtc == DateTime.MinValue ||
                        item.Time > stats.LastTradeTimeUtc)
                    {
                        stats.LastTradeTimeUtc = item.Time;
                    }

                    var itemNyTime = ConvertToNewYorkTime(item.Time);
                    if (itemNyTime.Date == nyDate.Date &&
                        itemNyTime.TimeOfDay >= _openingTimeNy &&
                        itemNyTime.TimeOfDay <= TimeOverTimeNy)
                    {
                        stats.SignalWindowCount++;
                    }
                }
            }
            catch
            {
                return stats;
            }

            return stats;
        }

        private string FormatCallbackNyTime(DateTime utcTime)
        {
            if (utcTime == DateTime.MinValue)
                return "";

            return ConvertToNewYorkTime(utcTime)
                .ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture);
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

        private void TrackObservedScore(int bar, DateTime nyTime, MarketUpdate? update, ScoreTradeSignal score)
        {
            if (score == null)
                return;

            AppendScoreCandidateDebugFile(nyTime.Date, bar, nyTime, update, score);

            if (_bestObservedScore != null)
            {
                var currentRank = ScoreDebugRank(score, bar);
                var bestRank = ScoreDebugRank(_bestObservedScore, _bestObservedScoreBar);
                if (currentRank < bestRank)
                    return;
            }

            _bestObservedScore = score;
            _bestObservedScoreBar = bar;
            _bestObservedScoreNyTime = nyTime;
            _bestObservedScoreSource = update?.Source ?? "RecoveryScan";
            _bestObservedScoreIsTradeEvent = update?.IsTradeEvent ?? false;
            WriteObservedScoreDebugFile(nyTime.Date);
        }

        private decimal ScoreDebugRank(ScoreTradeSignal score, int bar)
        {
            var rank = score.Score * 1000m + bar;
            if (score.IsReady)
                rank += 10000000m;
            if (score.IsBreakout && !string.IsNullOrWhiteSpace(score.Side))
                rank += 1000000m;
            if (score.TimeOk)
                rank += 100000m;
            return rank;
        }

        private void WriteObservedScoreDebugFile(DateTime nyDate)
        {
            if (_bestObservedScore == null)
                return;

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var score = _bestObservedScore;
            var filePath = Path.Combine(
                _exportFolder,
                $"score_rejection_debug_{nyDate:yyyy-MM-dd}_NY.csv");

            File.WriteAllText(
                filePath,
                string.Join(",",
                    "Exporter_VERSION",
                    "fecha",
                    "SignalTime_NY",
                    "Bar",
                    "Source",
                    "IsTradeEvent",
                    "IsReady",
                    "RejectReason",
                    "IsBreakout",
                    "Side",
                    "ExecutionSide",
                    "EntryPrice",
                    "or_low",
                    "or_high",
                    "range",
                    "VWAP",
                    "Body",
                    "Volume",
                    "Delta",
                    "CumulativeDelta",
                    "PreviousVolume",
                    "PreviousDelta",
                    "Range_OK",
                    "Body_OK",
                    "Volume_OK",
                    "Delta_OK",
                    "Time_OK",
                    "VWAP_OK",
                    "Speed_OK",
                    "SpeedLabel",
                    "RawSpeedLabel",
                    "BreakOut_TICKS_PER_SEC",
                    "Speed_Elapsed_SECONDS",
                    "Score",
                    "MinScore",
                    "Signal_Source",
                    "APlus_Structure",
                    "APlus_Absorption",
                    "APlus_Speed",
                    "HasSide3_ImbalanceGroup",
                    "HasSide3_Imbalances",
                    "Buy_Imbalance_Count",
                    "Sell_Imbalance_Count",
                    "Price_Accepted_After_Imbalance",
                    "Price_Accepted_After_Speed",
                    "IsValueAcceptance") +
                Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _bestObservedScoreNyTime.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    _bestObservedScoreBar.ToString(CultureInfo.InvariantCulture),
                    _bestObservedScoreSource,
                    FormatBool(_bestObservedScoreIsTradeEvent),
                    FormatBool(score.IsReady),
                    DescribeScoreRejectReason(score),
                    FormatBool(score.IsBreakout),
                    score.Side,
                    score.ExecutionSide,
                    FormatPrice(score.EntryPrice),
                    FormatPrice(score.OrLow),
                    FormatPrice(score.OrHigh),
                    FormatTicks(score.OrRangeTicks),
                    FormatPrice(score.Vwap),
                    FormatTicks(score.BodyBreakoutTicks),
                    FormatTicks(score.Volume),
                    FormatTicks(score.Delta),
                    FormatTicks(score.CumulativeDelta),
                    FormatTicks(score.PreviousVolume),
                    FormatTicks(score.PreviousDelta),
                    FormatBool(score.RangeOk),
                    FormatBool(score.BodyOk),
                    FormatBool(score.VolumeOk),
                    FormatBool(score.DeltaOk),
                    FormatBool(score.TimeOk),
                    FormatBool(score.VwapOk),
                    FormatBool(score.SpeedValid),
                    score.SpeedLabel,
                    score.RawSpeedLabel,
                    FormatTicks(score.BreakoutSpeed),
                    FormatSeconds(score.SpeedElapsedSeconds),
                    score.Score.ToString(CultureInfo.InvariantCulture),
                    MinScore.ToString(CultureInfo.InvariantCulture),
                    score.SignalSource,
                    FormatBool(score.HasAPlusStructure),
                    FormatBool(score.HasAPlusAbsorption),
                    FormatBool(score.HasAPlusSpeedThreshold),
                    FormatBool(score.HasSide3_ImbalanceGroup),
                    FormatBool(score.HasSide3_Imbalances),
                    score.BuyImbalanceCount.ToString(CultureInfo.InvariantCulture),
                    score.SellImbalanceCount.ToString(CultureInfo.InvariantCulture),
                    FormatBool(score.PriceAcceptedAfterImbalance),
                    FormatBool(score.PriceAcceptedAfterSpeed),
                    FormatBool(score.IsValueAcceptance)) +
                Environment.NewLine);
        }

        private void AppendScoreCandidateDebugFile(
            DateTime nyDate,
            int bar,
            DateTime nyTime,
            MarketUpdate? update,
            ScoreTradeSignal score)
        {
            if (!score.IsBreakout || string.IsNullOrWhiteSpace(score.Side))
                return;

            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var filePath = Path.Combine(
                _exportFolder,
                $"score_signal_candidates_debug_{nyDate:yyyy-MM-dd}_NY.csv");
            var writeHeader = !File.Exists(filePath);
            using var writer = new StreamWriter(filePath, append: true);

            if (writeHeader)
            {
                writer.WriteLine(string.Join(",",
                    "Exporter_VERSION",
                    "fecha",
                    "SignalTime_NY",
                    "Bar",
                    "Source",
                    "IsTradeEvent",
                    "IsReady",
                    "RejectReason",
                    "Side",
                    "EntryPrice",
                    "Body",
                    "Volume",
                    "Delta",
                    "SpeedLabel",
                    "BreakOut_TICKS_PER_SEC",
                    "Speed_Elapsed_SECONDS",
                    "Speed_OK",
                    "Score",
                    "Buy_Imbalance_Count",
                    "Sell_Imbalance_Count",
                    "Signal_Source"));
            }

            writer.WriteLine(string.Join(",",
                ExporterVersion,
                nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                nyTime.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                bar.ToString(CultureInfo.InvariantCulture),
                update?.Source ?? "RecoveryScan",
                FormatBool(update?.IsTradeEvent ?? false),
                FormatBool(score.IsReady),
                DescribeScoreRejectReason(score),
                score.Side,
                FormatPrice(score.EntryPrice),
                FormatTicks(score.BodyBreakoutTicks),
                FormatTicks(score.Volume),
                FormatTicks(score.Delta),
                score.SpeedLabel,
                FormatTicks(score.BreakoutSpeed),
                FormatSeconds(score.SpeedElapsedSeconds),
                FormatBool(score.SpeedValid),
                score.Score.ToString(CultureInfo.InvariantCulture),
                score.BuyImbalanceCount.ToString(CultureInfo.InvariantCulture),
                score.SellImbalanceCount.ToString(CultureInfo.InvariantCulture),
                score.SignalSource));
        }

        private string DescribeScoreRejectReason(ScoreTradeSignal score)
        {
            var reasons = new List<string>();

            if (!score.IsReady)
            {
                if (!score.IsBreakout)
                    reasons.Add("NO_BREAKOUT");
                if (string.IsNullOrWhiteSpace(score.Side))
                    reasons.Add("NO_SIDE");
                if (score.EntryPrice <= score.OrHigh && score.EntryPrice >= score.OrLow)
                    reasons.Add("ENTRY_INSIDE_OR");
                if (!score.RangeOk)
                    reasons.Add("RANGE");
                if (!score.TimeOk)
                    reasons.Add("TIME");
                if (score.Score < MinScore)
                    reasons.Add("SCORE");
                if (!score.SpeedValid)
                    reasons.Add("SPEED");
                if (score.SpeedLabel == "A+ speed" &&
                    !score.HasAPlusStructure &&
                    !score.PriceAcceptedAfterSpeed &&
                    !score.HasAPlusAbsorption)
                {
                    reasons.Add("APLUS_CONFIRMATION");
                }
                if (score.SpeedLabel == "normal speed" &&
                    !((score.Side == "BUY" && score.BuyImbalanceCount > 0) ||
                      (score.Side == "SELL" && score.SellImbalanceCount > 0)))
                {
                    reasons.Add("SIDE_IMBALANCE");
                }
                if (!score.VolumeOk)
                    reasons.Add("VOLUME");
                if (RequireBodyOkForTrade && !score.BodyOk)
                    reasons.Add("BODY");
                if (RequireVwapOkForTrade && !score.VwapOk)
                    reasons.Add("VWAP");
            }

            return reasons.Count == 0 ? "READY" : string.Join("|", reasons);
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
                $"score_best_rejected_{nyDate:yyyy-MM-dd}_NY.csv"
            );

            File.WriteAllText(
                filePath,
                CsvHeader + Environment.NewLine +
                string.Join(",",
                    ExporterVersion,
                    nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    _bestRejectedScoreNyTime.ToString("HH:mm:ss", CultureInfo.InvariantCulture),
                    "", // ExitTime_NY
                    "", // Trade_Duration
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
                    "", // Cvd_Excelente_Count
                    "", // Cvd_Normal_Count
                    "", // Cvd_Advertencia_Count
                    "", // Cvd_Riesgo_Reversion_Count
                    "", // Cvd_Total_Samples
                    "", // Cvd_Excelente_Pct
                    "", // Cvd_Negative_Episodes
                    "", // Cvd_Label_Changes
                    "", // Cvd_Worst_Label
                    BuildEmptyDynamicAlarmCsvFields(),
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
                    "", // Largest_MAE_pullback_ticks
                    "", // Largest_MFE_pullup_ticks
                    "", // Number_of_Pullbacks_during_Trade
                    "", // Number_of_PullUps_during_Trade
                    "", // Max_Speed_MAE_during_trade
                    "", // Max_Speed_MFE_during_trade
                    FormatBool(score.HasAPlusStructure),
                    FormatBool(score.HasAPlusAbsorption),
                    FormatBool(score.HasAPlusSpeedThreshold),
                    score.APlusStructureSide,
                    FormatNullablePrice(score.APlusStructurePrice),
                    Math.Max(score.BuyImbalanceCount, score.SellImbalanceCount)
                        .ToString(CultureInfo.InvariantCulture),
                    FormatBool(score.SpeedIgnoredByStructure),
                    BuildEmptyExtendedTelemetryCsvFields()
                ) + Environment.NewLine
            );
        }

        private void ResetDay(DateTime nyDate)
        {
            FlushDynamicTimelineBuffer();
            DeleteScoreDebugFiles(nyDate);
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
            _lastSignalReadyBar = -1;
            _activeMarketUpdateBar = -1;
            _activeMarketUpdateTime = DateTime.MinValue;
            _activeMarketCandleTime = DateTime.MinValue;
            _marketUpdateSequence = 0;
            _lastProcessedMarketBar = -1;
            _lastProcessedMarketTime = DateTime.MinValue;
            _lastProcessedMarketClose = 0;
            _lastProcessedMarketHigh = 0;
            _lastProcessedMarketLow = 0;
            _lastProcessedMarketVolume = 0;
            _lastProcessedMarketDelta = 0;
            _lastProcessedMarketSource = "";
            _diagOnNewTradeCount = 0;
            _diagOnNewTradesBatchCount = 0;
            _diagOnNewTradesItemCount = 0;
            _diagOnCumulativeTradeCount = 0;
            _diagOnUpdateCumulativeTradeCount = 0;
            _diagOnCumulativeTradeTickCount = 0;
            _diagMarketDepthChangedCount = 0;
            _diagMarketDepthsChangedBatchCount = 0;
            _diagMarketDepthsChangedItemCount = 0;
            _diagMarketByOrdersChangedBatchCount = 0;
            _diagMarketByOrdersChangedItemCount = 0;
            _diagLastTradeTimeUtc = DateTime.MinValue;
            _diagLastTradePrice = 0;
            _diagLastTradeVolume = 0;
            _diagLastCumulativeTradeTimeUtc = DateTime.MinValue;
            _diagLastCumulativeTradePrice = 0;
            _diagLastCumulativeTradeVolume = 0;
            _diagLastMarketDepthTimeUtc = DateTime.MinValue;
            _diagLastMarketDepthPrice = 0;
            _diagLastMarketDepthVolume = 0;
            _diagLastMarketDepthType = "";
            ClearPendingScore();
            ClearRejectedScore();
            ClearObservedScore();
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

        private void ClearObservedScore()
        {
            _bestObservedScore = null;
            _bestObservedScoreBar = -1;
            _bestObservedScoreNyTime = DateTime.MinValue;
            _bestObservedScoreSource = "";
            _bestObservedScoreIsTradeEvent = false;
        }

        private void DeleteScoreDebugFiles(DateTime nyDate)
        {
            try
            {
                File.Delete(Path.Combine(
                    _exportFolder,
                    $"score_rejection_debug_{nyDate:yyyy-MM-dd}_NY.csv"));
                File.Delete(Path.Combine(
                    _exportFolder,
                    $"score_signal_candidates_debug_{nyDate:yyyy-MM-dd}_NY.csv"));
                File.Delete(Path.Combine(
                    _exportFolder,
                    $"score_best_rejected_{nyDate:yyyy-MM-dd}_NY.csv"));
                File.Delete(Path.Combine(
                    _exportFolder,
                    $"market_feed_diagnostics_{nyDate:yyyy-MM-dd}_NY.csv"));
            }
            catch
            {
                // Diagnostic sidecars only. Do not affect replay/export flow.
            }
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

        private void CreatePendingScoreIfExpired(MarketUpdate update)
        {
            var bar = update.Bar;
            if (_tradeCreated || _pendingScore == null || bar <= _pendingScoreBar)
                return;

            var entryBar = _pendingScoreBar;
            var entryCandle = GetCandle(entryBar);
            var pendingScore = _pendingScore;
            var pendingScoreNyTime = _pendingScoreNyTime;

            CreateTrade(entryBar, entryCandle, pendingScoreNyTime, pendingScore);
            ClearPendingScore();

            if (_trade == null)
                return;

            UpdateTradeResult(CreateSignalMarketUpdate(
                entryBar,
                entryCandle,
                ConvertNewYorkTimeToUtc(pendingScoreNyTime),
                pendingScore,
                "PendingSignalSnapshot"));
            UpdateTradeResult(update);
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

        private string FormatExitTimeNy()
        {
            if (_trade == null || _trade.Result == "OPEN" || !_trade.ExitTimeNy.HasValue)
                return "";

            return _trade.ExitTimeNy.Value.ToString("HH:mm:ss", CultureInfo.InvariantCulture);
        }

        private string FormatTradeDuration()
        {
            if (_trade == null || _trade.Result == "OPEN" || !_trade.ExitTimeNy.HasValue)
                return "";

            var duration = _trade.ExitTimeNy.Value - _trade.EntryTimeNy;
            if (duration < TimeSpan.Zero)
                duration = TimeSpan.Zero;

            return $"{(int)duration.TotalMinutes:00}:{duration.Seconds:00}";
        }

        private decimal? GetTradeDurationMilliseconds()
        {
            if (_trade == null || _trade.Result == "OPEN" || !_trade.ExitTimeNy.HasValue)
                return null;

            return Math.Max(
                0,
                (decimal)(_trade.ExitTimeNy.Value - _trade.EntryTimeNy).TotalMilliseconds);
        }

        private string FormatTradeDurationMilliseconds()
        {
            var durationMilliseconds = GetTradeDurationMilliseconds();
            return durationMilliseconds.HasValue
                ? $"{durationMilliseconds.Value:0.###} ms"
                : "N/A ms";
        }

        private decimal? GetAlarmToExitMilliseconds()
        {
            if (_trade == null ||
                !_trade.DynamicAlarmTriggered ||
                !_trade.ExitTimeNy.HasValue)
            {
                return null;
            }

            return Math.Max(
                0,
                (decimal)(_trade.ExitTimeNy.Value - _trade.DynamicAlarmTimeNy).TotalMilliseconds);
        }

        private bool IsTradeNotManageableByLatency()
        {
            var durationMilliseconds = GetTradeDurationMilliseconds();
            return durationMilliseconds.HasValue &&
                durationMilliseconds.Value < Math.Max(0, MaxExpectedLatencyMilliseconds);
        }

        private bool? IsDynamicAlarmNotManageableByLatency()
        {
            var alarmToExitMilliseconds = GetAlarmToExitMilliseconds();
            if (!alarmToExitMilliseconds.HasValue)
                return null;

            return alarmToExitMilliseconds.Value <
                Math.Max(0, MaxExpectedLatencyMilliseconds);
        }

        private decimal? CalculateResultAfterSlippage()
        {
            if (_trade == null || _trade.Result == "OPEN")
                return null;

            return TradeResultTicks() -
                Math.Max(0, SlippageTicksPerFill) * 2m;
        }

        private decimal? CalculateVolumeIncreasingPercent()
        {
            if (_trade == null || _trade.VolumeObservedSamples <= 0)
                return null;

            return (decimal)_trade.VolumeIncreaseSamples /
                _trade.VolumeObservedSamples;
        }

        private string BuildExtendedTelemetryCsvFields()
        {
            if (_trade == null)
                return BuildEmptyExtendedTelemetryCsvFields();

            var durationMilliseconds = GetTradeDurationMilliseconds();
            var alarmToExitMilliseconds = GetAlarmToExitMilliseconds();
            var dynamicAlarmNotManageable = IsDynamicAlarmNotManageableByLatency();
            var resultAfterSlippage = CalculateResultAfterSlippage();

            return string.Join(",",
                _trade.EntryTimeNy.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                _trade.ExitTimeNy.HasValue
                    ? _trade.ExitTimeNy.Value.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture)
                    : "",
                FormatNullableMilliseconds(durationMilliseconds),
                durationMilliseconds.HasValue
                    ? FormatBool(durationMilliseconds.Value < 1000m)
                    : "",
                Math.Max(0, MaxExpectedLatencyMilliseconds).ToString(CultureInfo.InvariantCulture),
                durationMilliseconds.HasValue
                    ? FormatBool(IsTradeNotManageableByLatency())
                    : "",
                FormatNullableMilliseconds(alarmToExitMilliseconds),
                dynamicAlarmNotManageable.HasValue
                    ? FormatBool(dynamicAlarmNotManageable.Value)
                    : "",
                FormatTicks(Math.Max(0, SlippageTicksPerFill)),
                resultAfterSlippage.HasValue
                    ? FormatSignedTicks(resultAfterSlippage.Value)
                    : "",
                FormatBool(_trade.TpAndSlHitSameUpdate),
                EscapeCsv(_trade.RawSpeedLabel),
                FormatSeconds(_trade.APlusSpeedThresholdTicksPerSecond),
                FormatBool(_trade.APlusSpeedSetupConfirmed),
                FormatBool(_trade.PriceRejectedAfterImbalance),
                _trade.BuyImbalanceCount.ToString(CultureInfo.InvariantCulture),
                _trade.SellImbalanceCount.ToString(CultureInfo.InvariantCulture),
                _trade.ExecutionSideImbalanceCount.ToString(CultureInfo.InvariantCulture),
                FormatNullableTicks(_trade.MaxDeltaDuringTrade),
                FormatNullableTicks(_trade.MinDeltaDuringTrade),
                FormatBool(_trade.VolumeIncreasedDuringTrade),
                _trade.VolumeIncreaseSamples.ToString(CultureInfo.InvariantCulture),
                _trade.VolumeObservedSamples.ToString(CultureInfo.InvariantCulture),
                FormatNullableRatio(CalculateVolumeIncreasingPercent()),
                FormatSeconds(_trade.MaxMaeSpeed500Milliseconds),
                FormatSeconds(_trade.MaxMaeSpeed1Second),
                FormatSeconds(_trade.MaxMaeSpeed2Seconds));
        }

        private static string BuildEmptyExtendedTelemetryCsvFields()
        {
            return new string(',', ExtendedTelemetryFieldCount - 1);
        }

        private string FormatCvdExcellentPercent()
        {
            if (_trade == null || _trade.CvdTotalSamples <= 0)
                return "";

            return ((decimal)_trade.CvdExcellentCount / _trade.CvdTotalSamples)
                .ToString("0.####", CultureInfo.InvariantCulture);
        }

        private string BuildDynamicAlarmCsvFields()
        {
            if (_trade == null)
                return BuildEmptyDynamicAlarmCsvFields();

            if (!_trade.DynamicAlarmTriggered)
                return "FALSE" + new string(',', DynamicAlarmFieldCount - 1);

            return string.Join(",",
                "TRUE",
                _trade.DynamicAlarmTimeNy.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture),
                FormatSeconds(_trade.DynamicAlarmSecondsFromEntry),
                _trade.DynamicAlarmReason,
                _trade.CvdLabelAtAlarm,
                FormatTicks(_trade.CvdPullbackPercentAtAlarm),
                FormatTicks(_trade.MaePullbackTicksAtAlarm),
                FormatSeconds(_trade.MaeSpeedTicksPerSecondAtAlarm),
                FormatTicks(_trade.CurrentMaePullbackTicksAtAlarm),
                FormatSeconds(_trade.CurrentMaeSpeedTicksPerSecondAtAlarm),
                FormatSignedTicks(_trade.OpenPnlTicksAtAlarm),
                FormatTicks(_trade.MfeTicksAtAlarm),
                FormatTicks(_trade.DrawdownFromMfeTicksAtAlarm),
                FormatTicks(_trade.MfeTpPercentAtAlarm),
                FormatTicks(_trade.DistanceToSlTicksAtAlarm),
                FormatTicks(_trade.DistanceToTpTicksAtAlarm),
                FormatSeconds(_trade.SecondsSinceLastMfeAtAlarm),
                FormatSeconds(_trade.CvdNonExcellentSecondsAtAlarm),
                _trade.CvdNonExcellentConsecutiveSamplesAtAlarm.ToString(CultureInfo.InvariantCulture),
                FormatNullableRatio(_trade.CvdExcellentTimePercentBeforeAlarm),
                _trade.CvdWorstLabelBeforeAlarm,
                _trade.CvdExcellentCountAtAlarm.ToString(CultureInfo.InvariantCulture),
                _trade.CvdNormalCountAtAlarm.ToString(CultureInfo.InvariantCulture),
                _trade.CvdWarningCountAtAlarm.ToString(CultureInfo.InvariantCulture),
                _trade.CvdRiskReversalCountAtAlarm.ToString(CultureInfo.InvariantCulture),
                _trade.CvdTotalSamplesAtAlarm.ToString(CultureInfo.InvariantCulture),
                FormatTicks(_trade.FutureMfeAfterAlarm),
                FormatTicks(_trade.FutureMaeAfterAlarm),
                FormatNullableSignedTicks(_trade.ResultTrail10),
                FormatNullableSignedTicks(_trade.ResultTrail15),
                FormatNullableSignedTicks(_trade.ResultTrail20),
                FormatNullableSignedTicks(_trade.ResultBreakevenAtAlarm),
                FormatTicksSavedVsBaseline(_trade.ResultTrail10),
                FormatTicksSavedVsBaseline(_trade.ResultTrail15),
                FormatTicksSavedVsBaseline(_trade.ResultTrail20),
                FormatTicksSavedVsBaseline(_trade.ResultBreakevenAtAlarm),
                FormatTicksSavedVsBaseline(_trade.ResultTrail15));
        }

        private static string BuildEmptyDynamicAlarmCsvFields()
        {
            return new string(',', DynamicAlarmFieldCount - 1);
        }

        private string FormatNullableRatio(decimal? value)
        {
            return value.HasValue
                ? value.Value.ToString("0.####", CultureInfo.InvariantCulture)
                : "";
        }

        private string FormatNullableTicks(decimal? value)
        {
            return value.HasValue
                ? FormatTicks(value.Value)
                : "";
        }

        private string FormatNullableMilliseconds(decimal? value)
        {
            return value.HasValue
                ? value.Value.ToString("0.###", CultureInfo.InvariantCulture)
                : "";
        }

        private string FormatNullableSignedTicks(decimal? value)
        {
            return value.HasValue
                ? FormatSignedTicks(value.Value)
                : "";
        }

        private string FormatTicksSavedVsBaseline(decimal? managedResultTicks)
        {
            if (_trade == null ||
                _trade.Result == "OPEN" ||
                !managedResultTicks.HasValue)
            {
                return "";
            }

            return FormatSignedTicks(managedResultTicks.Value - TradeResultTicks());
        }

        private string FormatDynamicAlarmOpenPnl()
        {
            if (_trade == null || !_trade.DynamicAlarmTriggered)
                return "N/A";

            return $"{FormatSignedTicks(_trade.OpenPnlTicksAtAlarm)}t";
        }

        private string FormatDynamicAlarmReason()
        {
            if (_trade == null || !_trade.DynamicAlarmTriggered)
                return "N/A";

            return _trade.DynamicAlarmReason;
        }

        private string FormatTelegramCvdWorstState()
        {
            if (_trade == null ||
                string.Equals(_trade.CvdWorstLabel, "Excelente", StringComparison.Ordinal))
            {
                return "CVD se mantuvo Excelente";
            }

            return $"Peor estado CVD: {_trade.CvdWorstLabel}";
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

        private sealed class FeedCacheStats
        {
            public int TotalCount { get; set; }
            public int SignalWindowCount { get; set; }
            public DateTime FirstTradeTimeUtc { get; set; } = DateTime.MinValue;
            public DateTime LastTradeTimeUtc { get; set; } = DateTime.MinValue;
        }

        private sealed class MarketUpdate
        {
            public MarketUpdate(
                int bar,
                dynamic candle,
                DateTime marketTimeUtc,
                decimal price,
                decimal high,
                decimal low,
                decimal volume,
                decimal delta,
                string source,
                bool isTradeEvent,
                bool isSyntheticSnapshot,
                long sequence)
            {
                Bar = bar;
                Candle = candle;
                MarketTimeUtc = marketTimeUtc;
                Price = price;
                High = high;
                Low = low;
                Volume = volume;
                Delta = delta;
                Source = source;
                IsTradeEvent = isTradeEvent;
                IsSyntheticSnapshot = isSyntheticSnapshot;
                Sequence = sequence;
            }

            public int Bar { get; }
            public dynamic Candle { get; }
            public DateTime MarketTimeUtc { get; }
            public decimal Price { get; }
            public decimal High { get; }
            public decimal Low { get; }
            public decimal Volume { get; }
            public decimal Delta { get; }
            public string Source { get; }
            public bool IsTradeEvent { get; }
            public bool IsSyntheticSnapshot { get; }
            public long Sequence { get; }
        }

        private sealed class PersistedTradeExit
        {
            public string ExporterVersion { get; set; } = "";
            public DateTime EntryDate { get; set; }
            public int EntryBar { get; set; }
            public DateTime EntryTimeNy { get; set; }
            public decimal Entry { get; set; }
            public decimal Sl { get; set; }
            public decimal Tp { get; set; }
            public decimal SlTicks { get; set; }
            public decimal TpTicks { get; set; }
            public string Side { get; set; } = "";
            public string Result { get; set; } = "";
            public decimal ExitPrice { get; set; }
            public DateTime ExitTimeNy { get; set; }
            public DateTime ExitTimeUtc { get; set; }
            public bool TpAndSlHitSameUpdate { get; set; }
            public string CsvRow { get; set; } = "";
        }

        private sealed class TradeInputSnapshot
        {
            public string Version { get; init; } = "";
            public DateTime EntryDate { get; init; }
            public DateTime DecisionTimestampNy { get; init; }
            public DateTime FeatureTimestampNy { get; init; }
            public DateTime EntryTimestampNy { get; init; }
            public DateTime FeatureTimestampUtc { get; init; }
            public DateTime EntryTimestampUtc { get; init; }
            public int EntryBar { get; init; }
            public string Side { get; init; } = "";
            public string SignalSource { get; init; } = "";
            public string SpeedProfile { get; init; } = "";
            public decimal EntryPrice { get; init; }
            public decimal SlPriceAtEntry { get; init; }
            public decimal TpPriceAtEntry { get; init; }
            public decimal SlTicksAtEntry { get; init; }
            public decimal TpTicksAtEntry { get; init; }
            public decimal OrLow { get; init; }
            public decimal OrHigh { get; init; }
            public decimal OrRangeTicks { get; init; }
            public decimal VwapAtEntry { get; init; }
            public decimal BodyAtEntry { get; init; }
            public decimal VolumeAtEntry { get; init; }
            public decimal DeltaAtEntry { get; init; }
            public decimal CumulativeDeltaAtEntry { get; init; }
            public string CumulativeDeltaSourceAtEntry { get; init; } = "";
            public decimal CvdCurrentAtEntry { get; init; }
            public decimal CvdPeakAtEntry { get; init; }
            public decimal CvdPullbackPctAtEntry { get; init; }
            public string CvdLabelAtEntry { get; init; } = "";
            public int CvdTotalSamplesAtEntry { get; init; }
            public decimal PreviousVolumeAtEntry { get; init; }
            public decimal PreviousDeltaAtEntry { get; init; }
            public bool VolumeIncreasingAtEntry { get; init; }
            public decimal DeltaChangeAtEntry { get; init; }
            public bool DeltaWithSideAtEntry { get; init; }
            public bool PriceAcceptedAfterImbalanceAtEntry { get; init; }
            public bool PriceRejectedAfterImbalanceAtEntry { get; init; }
            public string BreakoutSpeedAtEntry { get; init; } = "";
            public decimal BreakoutTicksPerSecondAtEntry { get; init; }
            public decimal SpeedElapsedSecondsAtEntry { get; init; }
            public bool SpeedReplayFallbackAtEntry { get; init; }
            public string SpeedTimingSourceAtEntry { get; init; } = "";
            public bool RangeOkAtEntry { get; init; }
            public bool BodyOkAtEntry { get; init; }
            public bool VolumeOkAtEntry { get; init; }
            public bool DeltaOkAtEntry { get; init; }
            public bool TimeOkAtEntry { get; init; }
            public bool VwapOkAtEntry { get; init; }
            public bool SpeedOkAtEntry { get; init; }
            public int ScoreAtEntry { get; init; }
            public string RawSpeedLabelAtEntry { get; init; } = "";
            public bool APlusStructureAtEntry { get; init; }
            public bool APlusAbsorptionAtEntry { get; init; }
            public bool APlusSpeedAtEntry { get; init; }
            public bool APlusSpeedSetupConfirmedAtEntry { get; init; }
            public int BuyImbalanceCountAtEntry { get; init; }
            public int SellImbalanceCountAtEntry { get; init; }
            public int ExecutionSideImbalanceCountAtEntry { get; init; }
            public string ImbalanceGroup3AtEntry { get; init; } = "";
            public decimal? ImbalanceGroupPriceAtEntry { get; init; }
            public int ImbalanceCountAtEntry { get; init; }
            public bool SpeedIgnoredByStructureAtEntry { get; init; }
        }

        private sealed class TradeOutcome
        {
            public List<string> CsvFields { get; } = new();
        }

        private class TradeState
        {
            public TradeInputSnapshot? InputSnapshot { get; set; }
            public int EntryBar { get; set; }
            public DateTime EntryDate { get; set; }
            public DateTime EntryTimeNy { get; set; }
            public DateTime? ExitTimeNy { get; set; }
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
            public string RawSpeedLabel { get; set; } = "";
            public decimal Volume { get; set; }
            public decimal Delta { get; set; }
            public decimal CumulativeDelta { get; set; }
            public string CumulativeDeltaSource { get; set; } = "";
            public decimal CvdEntry { get; set; }
            public decimal CvdPeak { get; set; }
            public decimal CvdCurrent { get; set; }
            public decimal CvdPullbackPercent { get; set; }
            public string CvdPullbackLabel { get; set; } = "";
            public int CvdExcellentCount { get; set; }
            public int CvdNormalCount { get; set; }
            public int CvdWarningCount { get; set; }
            public int CvdRiskReversalCount { get; set; }
            public int CvdTotalSamples { get; set; }
            public int CvdNegativeEpisodes { get; set; }
            public int CvdLabelChanges { get; set; }
            public int CvdLastSampleBar { get; set; } = -1;
            public decimal CvdLastSampleValue { get; set; }
            public string CvdLastCountedLabel { get; set; } = "";
            public string CvdWorstLabel { get; set; } = "Excelente";
            public DateTime CvdLastStateTimeUtc { get; set; }
            public string CvdLastTimingSource { get; set; } = "";
            public decimal CvdObservedSeconds { get; set; }
            public decimal CvdExcellentSeconds { get; set; }
            public DateTime CvdNonExcellentStartTimeUtc { get; set; }
            public int CvdNonExcellentConsecutiveSamples { get; set; }
            public bool DynamicAlarmTriggered { get; set; }
            public DateTime DynamicAlarmTimeNy { get; set; }
            public decimal DynamicAlarmSecondsFromEntry { get; set; }
            public string DynamicAlarmReason { get; set; } = "";
            public string CvdLabelAtAlarm { get; set; } = "";
            public decimal CvdPullbackPercentAtAlarm { get; set; }
            public decimal MaePullbackTicksAtAlarm { get; set; }
            public decimal MaeSpeedTicksPerSecondAtAlarm { get; set; }
            public decimal CurrentMaePullbackTicksAtAlarm { get; set; }
            public decimal CurrentMaeSpeedTicksPerSecondAtAlarm { get; set; }
            public decimal OpenPnlTicksAtAlarm { get; set; }
            public decimal MfeTicksAtAlarm { get; set; }
            public decimal DrawdownFromMfeTicksAtAlarm { get; set; }
            public decimal MfeTpPercentAtAlarm { get; set; }
            public decimal DistanceToSlTicksAtAlarm { get; set; }
            public decimal DistanceToTpTicksAtAlarm { get; set; }
            public decimal SecondsSinceLastMfeAtAlarm { get; set; }
            public decimal CvdNonExcellentSecondsAtAlarm { get; set; }
            public int CvdNonExcellentConsecutiveSamplesAtAlarm { get; set; }
            public decimal? CvdExcellentTimePercentBeforeAlarm { get; set; }
            public string CvdWorstLabelBeforeAlarm { get; set; } = "";
            public int CvdExcellentCountAtAlarm { get; set; }
            public int CvdNormalCountAtAlarm { get; set; }
            public int CvdWarningCountAtAlarm { get; set; }
            public int CvdRiskReversalCountAtAlarm { get; set; }
            public int CvdTotalSamplesAtAlarm { get; set; }
            public decimal AlarmOpenPnlTicks { get; set; }
            public decimal DynamicTrailHighWaterTicks { get; set; }
            public decimal FutureMfeAfterAlarm { get; set; }
            public decimal FutureMaeAfterAlarm { get; set; }
            public decimal? ResultTrail10 { get; set; }
            public decimal? ResultTrail15 { get; set; }
            public decimal? ResultTrail20 { get; set; }
            public decimal? ResultBreakevenAtAlarm { get; set; }
            public string TimelineFilePath { get; set; } = "";
            public string TimelineTradeId { get; set; } = "";
            public List<string> TimelineBuffer { get; } = new List<string>();
            public int TimelineSequence { get; set; }
            public DateTime TimelineLastObservationTimeUtc { get; set; }
            public decimal TimelineElapsedSeconds { get; set; }
            public decimal TimelineLastWrittenElapsedSeconds { get; set; }
            public string TimelineLastWrittenCvdLabel { get; set; } = "";
            public bool TimelineLastWrittenCausalAlarmCandidate { get; set; }
            public bool TimelineLastWrittenLegacyAlarmCandidate { get; set; }
            public bool TimelineLastWrittenDynamicAlarmTriggered { get; set; }
            public string TimelineLastWrittenResult { get; set; } = "";
            public bool TimelineCausalAlarmCandidateActive { get; set; }
            public int TimelineCausalAlarmEpisode { get; set; }
            public decimal PreviousVolume { get; set; }
            public decimal PreviousDelta { get; set; }
            public bool VolumeIncreasing { get; set; }
            public bool HasOrderFlowSample { get; set; }
            public int LastOrderFlowBar { get; set; } = -1;
            public decimal LastObservedVolume { get; set; }
            public decimal CurrentVolume { get; set; }
            public decimal CurrentDelta { get; set; }
            public bool CurrentVolumeIncreasing { get; set; }
            public bool VolumeIncreasedDuringTrade { get; set; }
            public int VolumeIncreaseSamples { get; set; }
            public int VolumeObservedSamples { get; set; }
            public decimal? MaxDeltaDuringTrade { get; set; }
            public decimal? MinDeltaDuringTrade { get; set; }
            public decimal DeltaChange { get; set; }
            public bool DeltaWithSide { get; set; }
            public bool PriceAcceptedAfterImbalance { get; set; }
            public bool PriceRejectedAfterImbalance { get; set; }
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
            public bool HasPathSample { get; set; }
            public DateTime LastPathUpdateTimeUtc { get; set; }
            public decimal LastPathFavorableTicks { get; set; }
            public decimal LastPathAdverseTicks { get; set; }
            public bool IsMaePullbackActive { get; set; }
            public bool IsMfePullupActive { get; set; }
            public decimal MaePullbackStartTicks { get; set; }
            public decimal MfePullupStartTicks { get; set; }
            public decimal LargestMaePullbackTicks { get; set; }
            public decimal LargestMfePullupTicks { get; set; }
            public int NumberOfPullbacksDuringTrade { get; set; }
            public int NumberOfPullUpsDuringTrade { get; set; }
            public decimal MaxSpeedMaeDuringTrade { get; set; }
            public decimal MaxSpeedMfeDuringTrade { get; set; }
            public decimal CurrentMaePullbackTicks { get; set; }
            public decimal CurrentMaeSpeedTicksPerSecond { get; set; }
            public decimal PathElapsedSeconds { get; set; }
            public List<PathObservation> PathObservations { get; } = new List<PathObservation>();
            public decimal CurrentMaeSpeed500Milliseconds { get; set; }
            public decimal CurrentMaeSpeed1Second { get; set; }
            public decimal CurrentMaeSpeed2Seconds { get; set; }
            public decimal MaxMaeSpeed500Milliseconds { get; set; }
            public decimal MaxMaeSpeed1Second { get; set; }
            public decimal MaxMaeSpeed2Seconds { get; set; }
            public DateTime LastMfeTimeUtc { get; set; }
            public bool CvdProfitLockArmed { get; set; }
            public decimal CvdProfitLockExitPrice { get; set; }
            public decimal CvdProfitLockTicks { get; set; }
            public decimal CvdProfitLockBestMfeTicks { get; set; }
            public bool CvdRiskBracketActive { get; set; }
            public bool APlusStructure { get; set; }
            public bool APlusAbsorption { get; set; }
            public bool APlusSpeed { get; set; }
            public bool APlusSpeedSetupConfirmed { get; set; }
            public decimal APlusSpeedThresholdTicksPerSecond { get; set; }
            public string SignalSource { get; set; } = "";
            public string ImbalanceGroup3 { get; set; } = "";
            public decimal? ImbalanceGroupPrice { get; set; }
            public int ImbalanceCount { get; set; }
            public int BuyImbalanceCount { get; set; }
            public int SellImbalanceCount { get; set; }
            public int ExecutionSideImbalanceCount { get; set; }
            public bool SpeedIgnoredByStructure { get; set; }
            public bool TpAndSlHitSameUpdate { get; set; }
        }

        private sealed class PathObservation
        {
            public decimal ElapsedSeconds { get; set; }
            public decimal AdverseTicks { get; set; }
        }

    }
}
