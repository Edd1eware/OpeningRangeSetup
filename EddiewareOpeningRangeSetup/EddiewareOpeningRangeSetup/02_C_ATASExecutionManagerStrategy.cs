using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using ATAS.DataFeedsCore;
using ATAS.Strategies;
using ATAS.Strategies.Chart;

namespace ATAS.Indicators
{
    // Execution Manager - Nucleo Robusto + Runner Split (Fase 4).
    // Split: TpContracts salen a TP fijo; el resto corre con trailing 30t post-TP.
    // Si EnableRunnerSplit=false: comportamiento original (trail activa al +N ticks).
    [DisplayName("EW Opening Range Execution Manager (claude_version)")]
    public class EddiewareOpeningRangeSetup_claude_version : ChartStrategy
    {
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private DateTime _currentNyDate = DateTime.MinValue;
        private bool _enteredToday;
        private Order? _entryOrder;
        private Order? _stopOrder;
        private Order? _tpLimitOrder;
        private Order? _tpStopOrder;
        private string _openSide = "";
        private decimal _entryPrice;
        private decimal _peakFavorableTicks;
        private bool _trailActive;
        private bool _bracketsPlaced;
        private bool _bracketPlacementInProgress;
        private bool _flattenInProgress;
        private bool _cleanupInProgress;

        // Runner split state
        private bool _tpFilled;
        private decimal _runnerPeakTicks;
        private int _tpContractsActual;
        private int _runnerContractsActual;
        private decimal _entryFillVolume;
        private decimal _entryFillNotional;
        private decimal _tpFillVolume;

        // Trade logging
        private bool _tradeOpen;
        private decimal _entryFillPrice;
        private string _entryFillSide = "";
        private DateTime _entryFillTimeNy;
        private int _prevPosition;
        private int _activeContracts;

        // Risk Governor
        private decimal _challengeEquity;
        private decimal _challengePeakEquity;
        private bool _stateLoaded;

        // Rolling WR regime filter
        private readonly Queue<bool> _shadowQueue = new();
        private bool _regimePaused;
        private bool _setupActive;
        private string _setupSide = "";
        private decimal _setupEntry;
        private bool _setupOutcomeRecorded;
        private bool _regimeStateLoaded;

        private const string TraderLogDir =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\strategy_tester_results";

        private string ChallengeStateFile => Path.Combine(TraderLogDir, "challenge_equity.txt");
        private string RegimeStateFile    => Path.Combine(TraderLogDir, "regime_state.txt");
        private string SessionStatusFile  => Path.Combine(TraderLogDir, "strategy_session_status.txt");

        // ── Properties ────────────────────────────────────────────────────────

        [Display(Name = "Auto-start (replay/demo/live)", Order = 5)]
        public bool AutoStart { get; set; } = true;

        [Display(Name = "Contratos total", Order = 10)]
        public int Contracts { get; set; } = 5;

        [Display(Name = "SL ticks", Order = 20)]
        public decimal SlTicks { get; set; } = 30m;

        // ── Runner Split (Lucid plan: 3 TP fijo + 2 trail 30t post-TP) ───────

        [Display(Name = "Runner split activo", Order = 25,
            GroupName = "Runner Split",
            Description = "true = TpContracts salen a TP fijo; resto corre con trail RunnerTrailTicks post-TP")]
        public bool EnableRunnerSplit { get; set; } = true;

        [Display(Name = "Contratos TP fijo", Order = 26,
            GroupName = "Runner Split")]
        public int TpContracts { get; set; } = 3;

        [Display(Name = "TP ticks (fijo)", Order = 27,
            GroupName = "Runner Split")]
        public decimal TpTicks { get; set; } = 60m;

        [Display(Name = "Runner trail ticks (post-TP)", Order = 28,
            GroupName = "Runner Split",
            Description = "Stop del runner = pico_post_TP - RunnerTrailTicks")]
        public decimal RunnerTrailTicks { get; set; } = 30m;

        // ── Trail original (solo si EnableRunnerSplit=false) ──────────────────

        [Display(Name = "Trailing activa (+ticks) [sin split]", Order = 30)]
        public decimal TrailActivateTicks { get; set; } = 20m;

        [Display(Name = "Trailing distancia (ticks) [sin split]", Order = 40)]
        public decimal TrailTicks { get; set; } = 10m;

        [Display(Name = "Solo A+ Speed", Order = 50)]
        public bool OnlyAPlusSpeed { get; set; } = true;

        [Display(Name = "Entrada desde (HH:mm NY)", Order = 60)]
        public string EntryFromNy { get; set; } = "09:30";

        [Display(Name = "Entrada hasta (HH:mm NY)", Order = 61)]
        public string EntryToNy { get; set; } = "09:40";

        [Display(Name = "Cierre forzado (HH:mm NY)", Order = 62)]
        public string HardCloseNy { get; set; } = "09:50";

        // ── Risk Governor ──────────────────────────────────────────────────────

        [Display(Name = "Risk Governor activado", Order = 100,
            GroupName = "Risk Governor")]
        public bool UseRiskGovernor { get; set; } = true;

        [Display(Name = "DD maximo cuenta ($)", Order = 101,
            GroupName = "Risk Governor")]
        public decimal GovernorMaxDD { get; set; } = 4500m;

        [Display(Name = "Reserva de seguridad ($)", Order = 102,
            GroupName = "Risk Governor")]
        public decimal GovernorReserve { get; set; } = 300m;

        [Display(Name = "Perdida max por contrato ($) [0=auto]", Order = 103,
            GroupName = "Risk Governor")]
        public decimal GovernorLossPerContract { get; set; } = 0m;

        [Display(Name = "Resetear equity del challenge", Order = 104,
            GroupName = "Risk Governor")]
        public bool ResetChallengeState { get; set; } = false;

        // ── Rolling WR Filter ──────────────────────────────────────────────────

        [Display(Name = "Rolling WR Filter activado", Order = 200,
            GroupName = "Rolling WR Filter")]
        public bool UseRollingWrFilter { get; set; } = true;

        [Display(Name = "Lookback N (numero de setups)", Order = 201,
            GroupName = "Rolling WR Filter")]
        public int RollingWrLookback { get; set; } = 11;

        [Display(Name = "Pausa si TPs <=", Order = 202,
            GroupName = "Rolling WR Filter")]
        public int RollingWrPauseAt { get; set; } = 1;

        [Display(Name = "Reanuda si TPs >=", Order = 203,
            GroupName = "Rolling WR Filter")]
        public int RollingWrResumeAt { get; set; } = 3;

        [Display(Name = "Shadow TP ticks", Order = 204,
            GroupName = "Rolling WR Filter")]
        public decimal ShadowTpTicks { get; set; } = 60m;

        [Display(Name = "Shadow SL ticks", Order = 205,
            GroupName = "Rolling WR Filter")]
        public decimal ShadowSlTicks { get; set; } = 30m;

        // ── Internals ──────────────────────────────────────────────────────────

        private decimal Tick => InstrumentInfo?.TickSize ?? 0.25m;

        private decimal EffectiveLossPerContract =>
            GovernorLossPerContract > 0
                ? GovernorLossPerContract
                : (SlTicks + 1m) * 5m + 9m;

        private bool HasRunnerSplit =>
            EnableRunnerSplit && _tpContractsActual > 0 && _runnerContractsActual > 0;

        private static TimeSpan ParseNy(string value, TimeSpan fallback) =>
            TimeSpan.TryParse(value, out var ts) ? ts : fallback;

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        // ── Risk Governor: state persistence ──────────────────────────────────

        private void EnsureStateLoaded()
        {
            if (_stateLoaded) return;
            _stateLoaded = true;
            if (ResetChallengeState)
            {
                _challengeEquity = 0m; _challengePeakEquity = 0m;
                SaveChallengeState(); return;
            }
            LoadChallengeState();
        }

        private void LoadChallengeState()
        {
            try
            {
                if (!File.Exists(ChallengeStateFile)) return;
                var lines = File.ReadAllLines(ChallengeStateFile);
                if (lines.Length >= 2
                    && decimal.TryParse(lines[0], NumberStyles.Any, CultureInfo.InvariantCulture, out var eq)
                    && decimal.TryParse(lines[1], NumberStyles.Any, CultureInfo.InvariantCulture, out var pk))
                { _challengeEquity = eq; _challengePeakEquity = pk; }
            }
            catch { }
        }

        private void SaveChallengeState()
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                File.WriteAllLines(ChallengeStateFile, new[]
                {
                    _challengeEquity.ToString(CultureInfo.InvariantCulture),
                    _challengePeakEquity.ToString(CultureInfo.InvariantCulture)
                });
            }
            catch { }
        }

        private void UpdateChallengeEquity(decimal pnlUsd)
        {
            _challengeEquity += pnlUsd;
            if (_challengeEquity > _challengePeakEquity) _challengePeakEquity = _challengeEquity;
            SaveChallengeState();
        }

        private int AllowedContracts()
        {
            if (!UseRiskGovernor) return Contracts;
            var dd = Math.Max(0m, _challengePeakEquity - _challengeEquity);
            var headroom = GovernorMaxDD - GovernorReserve - dd;
            var nc = (int)Math.Floor((headroom - 0.01m) / EffectiveLossPerContract);
            return Math.Clamp(nc, 0, Contracts);
        }

        // ── Rolling WR: state persistence ─────────────────────────────────────

        private void EnsureRegimeStateLoaded()
        {
            if (_regimeStateLoaded) return;
            _regimeStateLoaded = true;
            LoadRegimeState();
        }

        private void LoadRegimeState()
        {
            try
            {
                if (!File.Exists(RegimeStateFile)) return;
                foreach (var line in File.ReadAllLines(RegimeStateFile))
                {
                    if (line.StartsWith("paused="))
                        _regimePaused = line.Substring(7) == "true";
                    else if (line.StartsWith("queue=") && line.Length > 6)
                    {
                        _shadowQueue.Clear();
                        foreach (var p in line.Substring(6).Split(','))
                        {
                            if (p == "1") _shadowQueue.Enqueue(true);
                            else if (p == "0") _shadowQueue.Enqueue(false);
                        }
                    }
                }
            }
            catch { }
        }

        private void SaveRegimeState()
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                var qStr = string.Join(",", _shadowQueue.Select(x => x ? "1" : "0"));
                File.WriteAllLines(RegimeStateFile, new[]
                {
                    $"paused={(_regimePaused ? "true" : "false")}",
                    $"queue={qStr}"
                });
            }
            catch { }
        }

        private bool RegimeAllowsTrade()
        {
            if (!UseRollingWrFilter) return true;
            if (_shadowQueue.Count < RollingWrLookback) return true;
            var wins = _shadowQueue.Count(x => x);
            if (!_regimePaused && wins <= RollingWrPauseAt) _regimePaused = true;
            else if (_regimePaused && wins >= RollingWrResumeAt) _regimePaused = false;
            return !_regimePaused;
        }

        private void RecordShadowOutcome(bool hitTp)
        {
            if (!UseRollingWrFilter) return;
            _shadowQueue.Enqueue(hitTp);
            while (_shadowQueue.Count > RollingWrLookback) _shadowQueue.Dequeue();
            SaveRegimeState();
        }

        // ── Main cycle ─────────────────────────────────────────────────────────

        protected override void OnCalculate(int bar, decimal value)
        {
            if (AutoStart &&
                State != StrategyStates.Started && State != StrategyStates.Error)
                Start();

            EnsureStateLoaded();
            EnsureRegimeStateLoaded();

            var candle = GetCandle(bar);
            var ny = ToNy((DateTime)candle.Time);

            if (ny.Date != _currentNyDate)
            {
                _currentNyDate = ny.Date;
                _enteredToday = false;
                _entryOrder = null;
                _stopOrder = null;
                _tpLimitOrder = null;
                _tpStopOrder = null;
                _openSide = "";
                _trailActive = false;
                _peakFavorableTicks = 0;
                _setupActive = false;
                _setupSide = "";
                _setupOutcomeRecorded = false;
                _tpFilled = false;
                _runnerPeakTicks = 0;
                _tpContractsActual = 0;
                _runnerContractsActual = 0;
                _entryFillVolume = 0;
                _entryFillNotional = 0;
                _tpFillVolume = 0;
                _bracketsPlaced = false;
                _bracketPlacementInProgress = false;
                _flattenInProgress = false;
                _cleanupInProgress = false;
            }

            var tod = ny.TimeOfDay;
            var entryFrom = ParseNy(EntryFromNy, new TimeSpan(9, 30, 0));
            var entryTo   = ParseNy(EntryToNy,   new TimeSpan(9, 40, 0));
            var hardClose = ParseNy(HardCloseNy,  new TimeSpan(9, 50, 0));
            var currentPrice = (decimal)candle.Close;

            // Shadow queue: track setup outcome (always, even when paused).
            if (_setupActive && !_setupOutcomeRecorded)
            {
                var isBuySetup = _setupSide == "BUY";
                var move = isBuySetup
                    ? (currentPrice - _setupEntry) / Tick
                    : (_setupEntry - currentPrice) / Tick;
                bool done = false, outcome = false;
                if (move >= ShadowTpTicks)       { outcome = true; done = true; }
                else if (move <= -ShadowSlTicks)  { done = true; }
                else if (tod >= hardClose)         { done = true; }
                if (done) { _setupOutcomeRecorded = true; _setupActive = false; RecordShadowOutcome(outcome); }
            }

            // Position monitoring: detect closes.
            int curPos = (int)CurrentPosition;
            int curAbs = Math.Abs(curPos);
            int prevAbs = Math.Abs(_prevPosition);

            // The market entry is sent without exits. Build protection only after
            // ATAS confirms the real fill/average price. OnNewMyTrade normally does
            // this immediately; this is the Replay fallback.
            if (_tradeOpen && !_bracketsPlaced && !_bracketPlacementInProgress
                && curAbs >= _activeContracts)
            {
                if (_entryFillPrice <= 0)
                    _entryFillPrice = AveragePrice > 0 ? AveragePrice : currentPrice;
                TryPlaceInitialProtection();
            }

            // Detect TP fill (split mode): position drops from full to runner size.
            // Use absolute position so BUY (+5 -> +2) and SELL (-5 -> -2) work.
            // OnNewMyTrade is the primary path; this condition is the Replay fallback.
            if (_tradeOpen && HasRunnerSplit && !_tpFilled
                && _tpContractsActual > 0 && _runnerContractsActual > 0
                && _tpLimitOrder != null
                && _tpLimitOrder.State == OrderStates.Done
                && !_tpLimitOrder.Canceled
                && prevAbs > _runnerContractsActual
                && curAbs == _runnerContractsActual)
            {
                ActivateRunnerAfterTp(
                    _entryFillSide == "BUY"
                        ? _entryFillPrice + TpTicks * Tick
                        : _entryFillPrice - TpTicks * Tick);
            }

            // Detect full close (position → 0).
            if (_tradeOpen && _prevPosition != 0 && curPos == 0)
            {
                var exitPrice = currentPrice;
                int closedContracts = _tpFilled ? _runnerContractsActual : _activeContracts;
                var tickMove = _entryFillSide == "BUY"
                    ? (exitPrice - _entryFillPrice) / Tick
                    : (_entryFillPrice - exitPrice) / Tick;
                var pnlUsd = tickMove * closedContracts * 5m;
                UpdateChallengeEquity(pnlUsd);
                var motivo = _tpFilled ? "RUNNER_CLOSE" : "CLOSE";
                LogTrade(_entryFillTimeNy, _entryFillSide, _entryFillPrice, exitPrice, pnlUsd, motivo, closedContracts);
                _tradeOpen = false;
                WriteSessionStatus("COMPLETE");
            }
            _prevPosition = curPos;

            // In position: manage trailing or hard close.
            if (CurrentPosition != 0 && _openSide != "")
            {
                if (tod >= hardClose) { Flatten(); return; }
                ManageTrailing(currentPrice);
                return;
            }

            // Position just closed: clean up.
            if (CurrentPosition == 0 && _openSide != "")
            {
                CleanupAfterClose();
                return;
            }

            if (_enteredToday) return;

            if (tod < entryFrom) return;
            if (tod > entryTo)
            {
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                _enteredToday = true;
                WriteSessionStatus("NO_SIGNAL");
                return;
            }

            var fileSig = StrategySignalFile.Read(_currentNyDate);
            var busSig  = ExecutionSignalBus.Peek(_currentNyDate);

            var side      = fileSig?.Side       ?? busSig?.Side       ?? "";
            var entry     = fileSig?.EntryPrice  ?? busSig?.EntryPrice  ?? 0m;
            var sl        = fileSig?.SlPrice      ?? busSig?.SlPrice      ?? 0m;
            var isAPlus   = fileSig?.IsAPlusSpeed ?? busSig?.IsAPlusSpeed ?? false;
            var barSignal = fileSig?.Bar          ?? busSig?.Bar          ?? -1;

            if (side == "") return;
            if (OnlyAPlusSpeed && !isAPlus)
            {
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                _enteredToday = true;
                WriteSessionStatus("SKIPPED_NOT_APLUS");
                return;
            }

            _setupActive = true; _setupSide = side; _setupEntry = entry; _setupOutcomeRecorded = false;

            if (!RegimeAllowsTrade())
            {
                LogRegimePause(_currentNyDate, _shadowQueue.Count(x => x));
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                _enteredToday = true;
                WriteSessionStatus("SKIPPED_REGIME");
                return;
            }

            var allowedContracts = AllowedContracts();
            if (allowedContracts == 0)
            {
                LogGovernorSkip(_currentNyDate, Math.Max(0m, _challengePeakEquity - _challengeEquity));
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                _enteredToday = true;
                WriteSessionStatus("SKIPPED_GOVERNOR");
                return;
            }

            var synthetic = new ExecutionSignalBus.PendingEntry
            {
                SessionDate  = _currentNyDate,
                Side         = side,
                EntryPrice   = entry,
                SlPrice      = sl,
                IsAPlusSpeed = isAPlus,
                Bar          = barSignal
            };
            EnterTrade(synthetic, allowedContracts);
            StrategySignalFile.MarkConsumed(_currentNyDate);
            ExecutionSignalBus.MarkConsumed(_currentNyDate);
        }

        private void EnterTrade(ExecutionSignalBus.PendingEntry e, int contracts)
        {
            var isBuy   = e.Side == "BUY";
            var entryDir = isBuy ? OrderDirections.Buy  : OrderDirections.Sell;

            _activeContracts = contracts;
            _openSide        = e.Side;
            _entryPrice      = e.EntryPrice;
            _enteredToday    = true;
            _trailActive     = false;
            _peakFavorableTicks = 0;
            _tradeOpen       = true;
            _entryFillPrice  = 0;
            _entryFillSide   = e.Side;
            _entryFillTimeNy = DateTime.MinValue;
            _tpFilled        = false;
            _runnerPeakTicks = 0;
            _entryFillVolume = 0;
            _entryFillNotional = 0;
            _tpFillVolume = 0;
            _bracketsPlaced = false;
            _bracketPlacementInProgress = false;
            _flattenInProgress = false;
            _entryOrder = null;
            _stopOrder = null;
            _tpLimitOrder = null;
            _tpStopOrder = null;

            // Clamp the split to the contracts allowed by the Governor. If it
            // allows <= TpContracts, every contract gets the fixed TP/SL and
            // there is no runner; we never fall back to the old pre-TP trail.
            if (EnableRunnerSplit && TpContracts > 0)
            {
                _tpContractsActual     = Math.Min(TpContracts, contracts);
                _runnerContractsActual = Math.Max(0, contracts - _tpContractsActual);
            }
            else
            {
                _tpContractsActual     = 0;
                _runnerContractsActual = 0;
            }

            // Send ONLY the market entry now. Protective orders are created
            // after the real fill so TP/SL are not anchored to the signal price.
            _entryOrder = new Order
            {
                Portfolio      = Portfolio,
                Security       = Security,
                Direction      = entryDir,
                Type           = OrderTypes.Market,
                QuantityToFill = contracts,
                Comment        = $"EW_entry_{contracts}c"
            };
            OpenOrder(_entryOrder);
        }

        private void TryPlaceInitialProtection()
        {
            if (!_tradeOpen || _bracketsPlaced || _bracketPlacementInProgress)
                return;
            if (_entryFillPrice <= 0 || _activeContracts <= 0 || _openSide == "")
                return;

            _bracketPlacementInProgress = true;
            try
            {
                _entryPrice = _entryFillPrice;
                var isBuy = _openSide == "BUY";
                var exitDir = isBuy ? OrderDirections.Sell : OrderDirections.Buy;
                var slPrice = isBuy
                    ? _entryFillPrice - SlTicks * Tick
                    : _entryFillPrice + SlTicks * Tick;

                if (_tpContractsActual > 0)
                {
                    var tpPrice = isBuy
                        ? _entryFillPrice + TpTicks * Tick
                        : _entryFillPrice - TpTicks * Tick;
                    var ocoGroup = $"EW_FIXED_{_currentNyDate:yyyyMMdd}_{Guid.NewGuid():N}";

                    // Fixed portion: independent OCO pair. Its stop never covers
                    // the runner contracts, so a delayed cancellation cannot
                    // reverse the remaining position after TP.
                    _tpStopOrder = new Order
                    {
                        Portfolio      = Portfolio,
                        Security       = Security,
                        Direction      = exitDir,
                        Type           = OrderTypes.Stop,
                        TriggerPrice   = slPrice,
                        QuantityToFill = _tpContractsActual,
                        OCOGroup       = ocoGroup,
                        Comment        = "EW_TP_leg_SL"
                    };
                    OpenOrder(_tpStopOrder);

                    _tpLimitOrder = new Order
                    {
                        Portfolio      = Portfolio,
                        Security       = Security,
                        Direction      = exitDir,
                        Type           = OrderTypes.Limit,
                        Price          = tpPrice,
                        QuantityToFill = _tpContractsActual,
                        OCOGroup       = ocoGroup,
                        Comment        = $"EW_TP_{_tpContractsActual}c"
                    };
                    OpenOrder(_tpLimitOrder);
                }

                var stopContracts = EnableRunnerSplit
                    ? _runnerContractsActual
                    : _activeContracts;
                if (stopContracts > 0)
                {
                    // Runner/non-split protection is separate from the fixed OCO.
                    _stopOrder = new Order
                    {
                        Portfolio      = Portfolio,
                        Security       = Security,
                        Direction      = exitDir,
                        Type           = OrderTypes.Stop,
                        TriggerPrice   = slPrice,
                        QuantityToFill = stopContracts,
                        Comment        = _runnerContractsActual > 0 ? "EW_runner_initial_SL" : "EW_SL"
                    };
                    OpenOrder(_stopOrder);
                }

                _bracketsPlaced = true;
            }
            finally
            {
                _bracketPlacementInProgress = false;
            }
        }

        private void ActivateRunnerAfterTp(decimal tpFillPrice)
        {
            if (_tpFilled || !HasRunnerSplit)
                return;

            _tpFilled = true;
            _runnerPeakTicks = Math.Max(
                TpTicks,
                _entryFillSide == "BUY"
                    ? (tpFillPrice - _entryFillPrice) / Tick
                    : (_entryFillPrice - tpFillPrice) / Tick);

            var tpTickMove = _entryFillSide == "BUY"
                ? (tpFillPrice - _entryFillPrice) / Tick
                : (_entryFillPrice - tpFillPrice) / Tick;
            var tpPnl = _tpContractsActual * tpTickMove * 5m;
            UpdateChallengeEquity(tpPnl);
            LogTrade(_entryFillTimeNy, _entryFillSide, _entryFillPrice,
                tpFillPrice, tpPnl, "TP_SPLIT", _tpContractsActual);

            // The runner stop has protected only runner quantity since entry.
            // Move that same order from -SL to peak-RunnerTrail; no cancel/open
            // transition and therefore no over-sized stop race.
            if (_stopOrder?.State != OrderStates.Active)
                return;

            var isBuy = _openSide == "BUY";
            var newStop = isBuy
                ? _entryFillPrice + (_runnerPeakTicks - RunnerTrailTicks) * Tick
                : _entryFillPrice - (_runnerPeakTicks - RunnerTrailTicks) * Tick;
            var modified = new Order
            {
                Portfolio      = Portfolio,
                Security       = Security,
                Direction      = _stopOrder.Direction,
                Type           = OrderTypes.Stop,
                TriggerPrice   = newStop,
                QuantityToFill = _runnerContractsActual,
                Comment        = "EW_runner_trail"
            };
            ModifyOrder(_stopOrder, modified);
            _stopOrder = modified;
        }

        private void ManageTrailing(decimal currentPrice)
        {
            if (_stopOrder == null || _entryPrice == 0) return;

            var isBuy = _openSide == "BUY";
            var favorableTicks = isBuy
                ? (currentPrice - _entryPrice) / Tick
                : (_entryPrice - currentPrice) / Tick;

            // In split/fixed-TP mode the initial SL must remain at -SlTicks until
            // the fixed TP fills. Never apply the legacy +20/-10 trail pre-TP.
            if (EnableRunnerSplit && !_tpFilled)
                return;

            // Runner split mode: trail from peak post-TP (immediate, no activation threshold).
            if (_tpFilled)
            {
                if (favorableTicks > _runnerPeakTicks) _runnerPeakTicks = favorableTicks;

                var newStop = isBuy
                    ? _entryPrice + (_runnerPeakTicks - RunnerTrailTicks) * Tick
                    : _entryPrice - (_runnerPeakTicks - RunnerTrailTicks) * Tick;

                var improves = isBuy
                    ? newStop > _stopOrder.TriggerPrice
                    : newStop < _stopOrder.TriggerPrice;
                if (!improves) return;

                var modified = new Order
                {
                    Portfolio      = Portfolio,
                    Security       = Security,
                    Direction      = _stopOrder.Direction,
                    Type           = OrderTypes.Stop,
                    TriggerPrice   = newStop,
                    QuantityToFill = _runnerContractsActual,
                    Comment        = "EW_runner_trail"
                };
                ModifyOrder(_stopOrder, modified);
                _stopOrder = modified;
                return;
            }

            // Original trail mode (no split or split not yet triggered).
            if (favorableTicks > _peakFavorableTicks) _peakFavorableTicks = favorableTicks;
            if (!_trailActive && _peakFavorableTicks >= TrailActivateTicks) _trailActive = true;
            if (!_trailActive) return;

            var newStopPrice = isBuy
                ? _entryPrice + (_peakFavorableTicks - TrailTicks) * Tick
                : _entryPrice - (_peakFavorableTicks - TrailTicks) * Tick;

            var imp = isBuy
                ? newStopPrice > _stopOrder.TriggerPrice
                : newStopPrice < _stopOrder.TriggerPrice;
            if (!imp) return;

            var mod = new Order
            {
                Portfolio      = Portfolio,
                Security       = Security,
                Direction      = _stopOrder.Direction,
                Type           = OrderTypes.Stop,
                TriggerPrice   = newStopPrice,
                QuantityToFill = _activeContracts,
                Comment        = "EW_trail"
            };
            ModifyOrder(_stopOrder, mod);
            _stopOrder = mod;
        }

        private async void Flatten()
        {
            if (_flattenInProgress)
                return;
            _flattenInProgress = true;
            try
            {
                // ATAS order operations are asynchronous. Confirm every protective
                // cancellation before sending the market close so an old stop cannot
                // fill afterwards and reverse the account position.
                await CancelIfActiveAsync(_tpLimitOrder);
                await CancelIfActiveAsync(_tpStopOrder);
                await CancelIfActiveAsync(_stopOrder);

                var qty = Math.Abs(CurrentPosition);
                if (qty > 0)
                {
                    var exitDir = _openSide == "BUY" ? OrderDirections.Sell : OrderDirections.Buy;
                    await OpenOrderAsync(new Order
                    {
                        Portfolio      = Portfolio,
                        Security       = Security,
                        Direction      = exitDir,
                        Type           = OrderTypes.Market,
                        QuantityToFill = qty,
                        Comment        = "EW_hardclose"
                    });
                }

                _stopOrder = null;
                _tpLimitOrder = null;
                _tpStopOrder = null;
            }
            finally
            {
                _flattenInProgress = false;
            }
        }

        private async Task CancelIfActiveAsync(Order? order)
        {
            if (order?.State != OrderStates.Active)
                return;
            try
            {
                await CancelOrderAsync(order);
            }
            catch
            {
                // OCO may have canceled the peer between the state check and call.
                if (order.State == OrderStates.Active)
                    throw;
            }
        }

        private async void CleanupAfterClose()
        {
            if (_cleanupInProgress)
                return;
            _cleanupInProgress = true;
            try
            {
                await CancelIfActiveAsync(_tpLimitOrder);
                await CancelIfActiveAsync(_tpStopOrder);
                await CancelIfActiveAsync(_stopOrder);
                _entryOrder = null;
                _stopOrder = null;
                _tpLimitOrder = null;
                _tpStopOrder = null;
                _openSide = "";
                _trailActive = false;
            }
            finally
            {
                _cleanupInProgress = false;
            }
        }

        protected override void OnNewMyTrade(MyTrade myTrade)
        {
            if (_openSide == "" || !_tradeOpen) return;

            var comment = myTrade.Order?.Comment ?? "";
            if (comment.StartsWith("EW_entry_", StringComparison.Ordinal))
            {
                _entryFillNotional += myTrade.Price * myTrade.Volume;
                _entryFillVolume += myTrade.Volume;
                if (_entryFillVolume > 0)
                    _entryFillPrice = _entryFillNotional / _entryFillVolume;
                _entryFillTimeNy = ToNy(myTrade.Time);

                if (_entryFillVolume >= _activeContracts)
                    TryPlaceInitialProtection();
                return;
            }

            if (comment.StartsWith("EW_TP_", StringComparison.Ordinal)
                && !comment.StartsWith("EW_TP_leg_SL", StringComparison.Ordinal))
            {
                _tpFillVolume += myTrade.Volume;
                if (_tpFillVolume >= _tpContractsActual)
                    ActivateRunnerAfterTp(myTrade.Price);
            }
        }

        protected override void OnCurrentPositionChanged()
        {
            base.OnCurrentPositionChanged();
            if (!_tradeOpen || _bracketsPlaced || Math.Abs(CurrentPosition) < _activeContracts)
                return;

            if (_entryFillPrice <= 0 && AveragePrice > 0)
                _entryFillPrice = AveragePrice;
            if (_entryFillTimeNy == DateTime.MinValue)
                _entryFillTimeNy = ToNy(UtcTime);
            TryPlaceInitialProtection();
        }

        private void LogTrade(DateTime ny, string side, decimal entryFill, decimal exitFill,
            decimal pnlUsd, string exitComment, int contracts)
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                var path = Path.Combine(TraderLogDir, "strategy_tester_trades.csv");
                if (!File.Exists(path))
                    File.AppendAllText(path,
                        "fecha,side,contratos,entry_fill,exit_fill,ticks,pnl_usd,exit_motivo," +
                        "challenge_equity,challenge_dd,regime_paused,queue_wins,queue_size\n");

                var tickMove = side == "BUY"
                    ? (exitFill - entryFill) / Tick
                    : (entryFill - exitFill) / Tick;
                var dd   = Math.Max(0m, _challengePeakEquity - _challengeEquity);
                var wins = _shadowQueue.Count(x => x);
                File.AppendAllText(path, string.Format(CultureInfo.InvariantCulture,
                    "{0:yyyy-MM-dd},{1},{2},{3},{4},{5:0.##},{6:0.00},{7},{8:0.00},{9:0.00},{10},{11},{12}\n",
                    ny.Date, side, contracts, entryFill, exitFill,
                    tickMove, pnlUsd, exitComment, _challengeEquity, dd,
                    _regimePaused, wins, _shadowQueue.Count));
            }
            catch { }
        }

        private void WriteSessionStatus(string status)
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                File.WriteAllText(
                    SessionStatusFile,
                    $"{_currentNyDate:yyyy-MM-dd},{status},{DateTime.UtcNow:O}");
            }
            catch { }
        }

        private void LogGovernorSkip(DateTime nyDate, decimal currentDD)
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                var path = Path.Combine(TraderLogDir, "governor_skips.csv");
                if (!File.Exists(path))
                    File.AppendAllText(path, "fecha,razon,challenge_equity,challenge_dd,headroom\n");
                var headroom = GovernorMaxDD - GovernorReserve - currentDD;
                File.AppendAllText(path, string.Format(CultureInfo.InvariantCulture,
                    "{0:yyyy-MM-dd},GOVERNOR_DD_FREEZE,{1:0.00},{2:0.00},{3:0.00}\n",
                    nyDate, _challengeEquity, currentDD, headroom));
            }
            catch { }
        }

        private void LogRegimePause(DateTime nyDate, int queueWins)
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                var path = Path.Combine(TraderLogDir, "regime_pauses.csv");
                if (!File.Exists(path))
                    File.AppendAllText(path, "fecha,razon,queue_wins,queue_size\n");
                File.AppendAllText(path, string.Format(CultureInfo.InvariantCulture,
                    "{0:yyyy-MM-dd},REGIME_PAUSE,{1},{2}\n",
                    nyDate, queueWins, _shadowQueue.Count));
            }
            catch { }
        }
    }
}
