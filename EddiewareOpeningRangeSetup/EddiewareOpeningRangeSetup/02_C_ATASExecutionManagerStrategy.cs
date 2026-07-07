using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using ATAS.DataFeedsCore;
using ATAS.Strategies;
using ATAS.Strategies.Chart;

namespace ATAS.Indicators
{
    // Execution Manager - Nucleo Robusto (Fase 4). Coloca las ordenes reales.
    // Consume la senal A+ Speed publicada por el exporter (ExecutionSignalBus),
    // entra a mercado, pone SL fijo y aplica TRAILING (activa al +N ticks, sale a
    // pico - M ticks). Probar PRIMERO en Replay; en live coloca ordenes reales.
    [DisplayName("EW Opening Range Execution Manager (claude_version)")]
    public class EddiewareOpeningRangeSetup_claude_version : ChartStrategy
    {
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private DateTime _currentNyDate = DateTime.MinValue;
        private bool _enteredToday;
        private Order? _stopOrder;
        private string _openSide = "";
        private decimal _entryPrice;
        private decimal _peakFavorableTicks;
        private bool _trailActive;

        // Trade logging via OnCalculate position monitoring (OnNewMyTrade unreliable in Replay).
        private bool _tradeOpen;
        private decimal _entryFillPrice;
        private string _entryFillSide = "";
        private DateTime _entryFillTimeNy;
        private int _prevPosition;
        private int _activeContracts;

        // Risk Governor: tracks challenge equity across ATAS restarts via file.
        private decimal _challengeEquity;
        private decimal _challengePeakEquity;
        private bool _stateLoaded;

        // Kill-switch graduated sizer (validated 2026-07-07, see 12_KillSwitchSizer.cs).
        private KillSwitchSizer _killSwitch;

        // Rolling WR regime filter: shadow queue updated for every valid setup signal.
        // Shadow outcome uses label thresholds TP=60t SL=30t, not the actual strategy SL.
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
        private string KillSwitchStateFile => Path.Combine(TraderLogDir, "killswitch_state.txt");

        // ── Properties ────────────────────────────────────────────────────────

        [Display(Name = "Auto-start (replay/demo/live)", Order = 5)]
        public bool AutoStart { get; set; } = true;

        [Display(Name = "Contratos", Order = 10)]
        public int Contracts { get; set; } = 3;

        [Display(Name = "SL ticks", Order = 20)]
        public decimal SlTicks { get; set; } = 50;

        [Display(Name = "Trailing activa (+ticks)", Order = 30)]
        public decimal TrailActivateTicks { get; set; } = 20;

        [Display(Name = "Trailing distancia (ticks)", Order = 40)]
        public decimal TrailTicks { get; set; } = 10;

        // TEMP 2026-07-07: default OFF para la validación del kill-switch (toma toda señal
        // canónica = las 174 del modelo). REVERTIR a true antes de producción (el edge vivo
        // es solo A+ Speed).
        [Display(Name = "Solo A+ Speed", Order = 50)]
        public bool OnlyAPlusSpeed { get; set; } = false;

        [Display(Name = "Entrada desde (HH:mm NY)", Order = 60)]
        public string EntryFromNy { get; set; } = "09:30";

        [Display(Name = "Entrada hasta (HH:mm NY)", Order = 61)]
        public string EntryToNy { get; set; } = "09:40";

        [Display(Name = "Cierre forzado (HH:mm NY)", Order = 62)]
        public string HardCloseNy { get; set; } = "09:50";

        // ── Risk Governor (Lucid $150k) ────────────────────────────────────
        // Before each entry: contracts = clamp(floor((MaxDD - Reserve - DD) / LossPerContract), 0, Contracts)
        // When result = 0: skip the trade and freeze. State persists across restarts via challenge_equity.txt.
        // Formula (Codex, 2026-06-29): headroom = MaxDD - Reserve - current_DD; nc = floor((headroom-0.01) / loss1c)

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
            GroupName = "Risk Governor",
            Description = "0 = calcular automaticamente: (SlTicks+1)*$5 + $9 comision")]
        public decimal GovernorLossPerContract { get; set; } = 0m;

        // ── Kill-switch graduated sizer (validated 2026-07-07) ─────────────
        // When ON, sizing follows the graduated tier design (full/half/min on
        // DD-from-peak + losing-streak override) instead of the headroom formula.
        // Cushion = GovernorMaxDD. Base steps up (3->4) only after forward validation.
        // The hard headroom governor still caps it (never exceeds the cliff limit).

        [Display(Name = "Kill-switch activado", Order = 110, GroupName = "Kill-switch")]
        public bool UseKillSwitch { get; set; } = true;

        [Display(Name = "Base contratos (3 arranque, 4 tras forward)", Order = 111,
            GroupName = "Kill-switch")]
        public int KillSwitchBase { get; set; } = 3;

        [Display(Name = "Resetear equity del challenge", Order = 104,
            GroupName = "Risk Governor",
            Description = "Activa para borrar el estado guardado y empezar challenge nuevo. Desactiva despues.")]
        public bool ResetChallengeState { get; set; } = false;

        // ── Rolling WR Regime Filter (Codex 2026-06-29, N=11, hysteresis 1/3) ─
        // Shadow queue updated for EVERY valid setup signal, even when paused.
        // Outcome uses label thresholds: TP=60t, SL=30t, timeout=09:50.
        // State persists across ATAS restarts via regime_state.txt.

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

        // Shadow TP/SL thresholds (label thresholds, not strategy SL).
        [Display(Name = "Shadow TP ticks", Order = 204,
            GroupName = "Rolling WR Filter")]
        public decimal ShadowTpTicks { get; set; } = 60m;

        [Display(Name = "Shadow SL ticks", Order = 205,
            GroupName = "Rolling WR Filter")]
        public decimal ShadowSlTicks { get; set; } = 30m;

        // ── Internals ──────────────────────────────────────────────────────

        private decimal Tick => InstrumentInfo?.TickSize ?? 0.25m;

        // Loss per 1 contract: uses GovernorLossPerContract if set, else derives from SlTicks.
        private decimal EffectiveLossPerContract =>
            GovernorLossPerContract > 0
                ? GovernorLossPerContract
                : (SlTicks + 1m) * 5m + 9m;

        private static TimeSpan ParseNy(string value, TimeSpan fallback)
        {
            return TimeSpan.TryParse(value, out var ts) ? ts : fallback;
        }

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        // ── Risk Governor: state persistence ──────────────────────────────

        private void EnsureStateLoaded()
        {
            if (_stateLoaded) return;
            _stateLoaded = true;

            _killSwitch = new KillSwitchSizer(
                baseSize: Math.Max(1, KillSwitchBase),
                cushion: GovernorMaxDD);

            if (ResetChallengeState)
            {
                _challengeEquity = 0m;
                _challengePeakEquity = 0m;
                _killSwitch.Reset();
                SaveChallengeState();
                SaveKillSwitchState();
                return;
            }
            LoadChallengeState();
            LoadKillSwitchState();
            // Persist right away so killswitch_state.txt / challenge_equity.txt EXIST from
            // the first bar (before trade #1). Confirms the strategy loaded the kill-switch
            // and is generating state, instead of leaving empty until the first close.
            SaveChallengeState();
            SaveKillSwitchState();
        }

        private void LoadKillSwitchState()
        {
            try
            {
                if (File.Exists(KillSwitchStateFile))
                    _killSwitch.Deserialize(File.ReadAllText(KillSwitchStateFile).Trim());
            }
            catch { }
        }

        private void SaveKillSwitchState()
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                File.WriteAllText(KillSwitchStateFile, _killSwitch.Serialize());
            }
            catch { }
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
                {
                    _challengeEquity = eq;
                    _challengePeakEquity = pk;
                }
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
            if (_challengeEquity > _challengePeakEquity)
                _challengePeakEquity = _challengeEquity;
            SaveChallengeState();

            // Feed the graduated kill-switch the closed-trade PnL (updates tier/streak).
            if (_killSwitch != null)
            {
                _killSwitch.OnTradeClosed(pnlUsd);
                SaveKillSwitchState();
            }
        }

        private int AllowedContracts()
        {
            // Hard headroom cliff (always applies as a last-resort cap).
            var dd = Math.Max(0m, _challengePeakEquity - _challengeEquity);
            var headroom = GovernorMaxDD - GovernorReserve - dd;
            var hardCap = (int)Math.Floor((headroom - 0.01m) / EffectiveLossPerContract);

            if (UseKillSwitch && _killSwitch != null)
            {
                // Graduated tier size, but never above the hard cliff cap.
                return Math.Max(0, Math.Min(_killSwitch.CurrentSize, hardCap));
            }
            if (!UseRiskGovernor) return Contracts;
            return Math.Clamp(hardCap, 0, Contracts);
        }

        // ── Rolling WR Regime Filter: state persistence ────────────────────

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

        // Must be called BEFORE each potential trade. Updates pause/resume state.
        private bool RegimeAllowsTrade()
        {
            if (!UseRollingWrFilter) return true;
            if (_shadowQueue.Count < RollingWrLookback) return true; // warm-up period

            var wins = _shadowQueue.Count(x => x);
            if (!_regimePaused && wins <= RollingWrPauseAt)
                _regimePaused = true;
            else if (_regimePaused && wins >= RollingWrResumeAt)
                _regimePaused = false;

            return !_regimePaused;
        }

        // Called once per setup completion: adds outcome and persists state.
        private void RecordShadowOutcome(bool hitTp)
        {
            if (!UseRollingWrFilter) return;
            _shadowQueue.Enqueue(hitTp);
            while (_shadowQueue.Count > RollingWrLookback)
                _shadowQueue.Dequeue();
            SaveRegimeState();
        }

        // ── Main cycle ────────────────────────────────────────────────────

        protected override void OnCalculate(int bar, decimal value)
        {
            // Re-arranque automatico SIN latch. Parar/cambiar de fecha en el Replay
            // deja la ChartStrategy en [Stopped]; sin esto la siguiente fecha no
            // opera aunque se le de Play manual. Re-arranca en cada calculo si quedo
            // detenida (no toca Error: ese requiere intervencion manual).
            if (AutoStart &&
                State != StrategyStates.Started && State != StrategyStates.Error)
            {
                Start();
            }

            EnsureStateLoaded();
            EnsureRegimeStateLoaded();

            var candle = GetCandle(bar);
            var ny = ToNy((DateTime)candle.Time);

            if (ny.Date != _currentNyDate)
            {
                _currentNyDate = ny.Date;
                _enteredToday = false;
                _stopOrder = null;
                _openSide = "";
                _trailActive = false;
                _peakFavorableTicks = 0;
                _setupActive = false;
                _setupSide = "";
                _setupOutcomeRecorded = false;
            }

            var tod = ny.TimeOfDay;
            var entryFrom = ParseNy(EntryFromNy, new TimeSpan(9, 30, 0));
            var entryTo = ParseNy(EntryToNy, new TimeSpan(9, 40, 0));
            var hardClose = ParseNy(HardCloseNy, new TimeSpan(9, 50, 0));
            var currentPrice = (decimal)candle.Close;

            // Per-bar: track setup outcome for shadow queue (label TP=60t, SL=30t).
            // Runs for both real trades and paused-day shadow monitoring.
            if (_setupActive && !_setupOutcomeRecorded)
            {
                var isBuySetup = _setupSide == "BUY";
                var move = isBuySetup
                    ? (currentPrice - _setupEntry) / Tick
                    : (_setupEntry - currentPrice) / Tick;

                bool done = false, outcome = false;
                if (move >= ShadowTpTicks)  { outcome = true; done = true; }
                else if (move <= -ShadowSlTicks) { done = true; }
                else if (tod >= hardClose)   { done = true; }

                if (done)
                {
                    _setupOutcomeRecorded = true;
                    _setupActive = false;
                    RecordShadowOutcome(outcome);
                }
            }

            // Detecta cierre de posicion en OnCalculate (OnNewMyTrade no dispara en Replay).
            int curPos = (int)CurrentPosition;
            if (_tradeOpen && _prevPosition != 0 && curPos == 0)
            {
                var exitPrice = currentPrice;
                var tickMove = _entryFillSide == "BUY"
                    ? (exitPrice - _entryFillPrice) / Tick
                    : (_entryFillPrice - exitPrice) / Tick;
                var pnlUsd = tickMove * _activeContracts * 5m;
                UpdateChallengeEquity(pnlUsd);
                LogTrade(_entryFillTimeNy, _entryFillSide, _entryFillPrice, exitPrice, pnlUsd, "CLOSE");
                _tradeOpen = false;
            }
            _prevPosition = curPos;

            // En posicion -> gestionar trailing. Cierre forzado al pasar el horario
            // limite (margen para trades lentos), aunque no haya tocado SL/trailing.
            if (CurrentPosition != 0 && _openSide != "")
            {
                if (tod >= hardClose)
                {
                    // Contabiliza el trade AQUI (precio actual = salida), de forma
                    // determinista: en Replay el recorrido puede terminar antes de que
                    // una barra posterior detecte curPos==0, y entonces OnTradeClosed
                    // nunca correria. _tradeOpen=false evita doble conteo con el bloque
                    // de deteccion de cierre de arriba.
                    if (_tradeOpen)
                    {
                        var tickMove = _entryFillSide == "BUY"
                            ? (currentPrice - _entryFillPrice) / Tick
                            : (_entryFillPrice - currentPrice) / Tick;
                        var pnlUsd = tickMove * _activeContracts * 5m;
                        UpdateChallengeEquity(pnlUsd);
                        LogTrade(_entryFillTimeNy, _entryFillSide, _entryFillPrice,
                                 currentPrice, pnlUsd, "HARDCLOSE");
                        _tradeOpen = false;
                    }
                    Flatten();
                    return;
                }
                ManageTrailing(currentPrice);
                return;
            }

            // Posicion cerrada tras haber entrado -> limpiar el stop remanente.
            if (CurrentPosition == 0 && _openSide != "")
            {
                if (_stopOrder != null && _stopOrder.State == OrderStates.Active)
                    CancelOrder(_stopOrder);
                _stopOrder = null;
                _openSide = "";
                _trailActive = false;
                return;
            }

            if (_enteredToday)
                return;

            // Ventana de entrada: solo entra entre EntryFrom y EntryTo (NY).
            if (tod < entryFrom)
                return;                       // aun no abre la ventana; esperar
            if (tod > entryTo)
            {
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                return;                       // ventana cerrada; no entrar tarde
            }

            // Lee senal del archivo (canal cross-DLL confiable).
            var fileSig = StrategySignalFile.Read(_currentNyDate);
            var busSig  = ExecutionSignalBus.Peek(_currentNyDate);

            var side       = fileSig?.Side       ?? busSig?.Side       ?? "";
            var entry      = fileSig?.EntryPrice  ?? busSig?.EntryPrice  ?? 0m;
            var sl         = fileSig?.SlPrice      ?? busSig?.SlPrice      ?? 0m;
            var isAPlus    = fileSig?.IsAPlusSpeed ?? busSig?.IsAPlusSpeed ?? false;
            var barSignal  = fileSig?.Bar          ?? busSig?.Bar          ?? -1;

            if (side == "")
                return;
            if (OnlyAPlusSpeed && !isAPlus)
            {
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                return;
            }

            // Activate setup outcome tracking for this signal (shadow queue always updated).
            _setupActive = true;
            _setupSide = side;
            _setupEntry = entry;
            _setupOutcomeRecorded = false;

            // Rolling WR regime filter: pause if recent WR is too low.
            if (!RegimeAllowsTrade())
            {
                var wins = _shadowQueue.Count(x => x);
                LogRegimePause(_currentNyDate, wins);
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                _enteredToday = true;
                return; // shadow monitoring continues via _setupActive above
            }

            // Risk Governor: calculate allowed contracts before entering.
            // If 0 contracts allowed, skip and freeze today's session.
            var allowedContracts = AllowedContracts();
            if (allowedContracts == 0)
            {
                var dd = Math.Max(0m, _challengePeakEquity - _challengeEquity);
                LogGovernorSkip(_currentNyDate, dd);
                StrategySignalFile.MarkConsumed(_currentNyDate);
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                _enteredToday = true;
                return; // shadow monitoring continues via _setupActive above
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
            var isBuy = e.Side == "BUY";
            var entryDir = isBuy ? OrderDirections.Buy : OrderDirections.Sell;
            var exitDir = isBuy ? OrderDirections.Sell : OrderDirections.Buy;

            _activeContracts = contracts;
            // Report the REAL executed size back to the bus so the exporter's Telegram
            // shows the true kill-switch contracts, not the nominal TelegramContracts.
            ExecutionSignalBus.ReportExecuted(e.SessionDate, contracts);

            // Set all state before OpenOrder (OnNewMyTrade unreliable in Replay).
            _openSide = e.Side;
            _entryPrice = e.EntryPrice;
            _enteredToday = true;
            _trailActive = false;
            _peakFavorableTicks = 0;
            _tradeOpen = true;
            _entryFillPrice = e.EntryPrice;
            _entryFillSide = e.Side;
            _entryFillTimeNy = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, _nyZone);

            var entryOrder = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = entryDir,
                Type = OrderTypes.Market,
                QuantityToFill = contracts,
                Comment = $"EW_claude_entry_{contracts}c"
            };
            OpenOrder(entryOrder);

            var slPrice = isBuy
                ? e.EntryPrice - SlTicks * Tick
                : e.EntryPrice + SlTicks * Tick;

            var stop = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = exitDir,
                Type = OrderTypes.Stop,
                TriggerPrice = slPrice,
                QuantityToFill = contracts,
                Comment = "EW_claude_SL"
            };
            OpenOrder(stop);

            _stopOrder = stop;
        }

        private void Flatten()
        {
            // Cierra la posicion a mercado y cancela el stop remanente.
            var qty = Math.Abs(CurrentPosition);
            if (qty > 0)
            {
                var exitDir = _openSide == "BUY" ? OrderDirections.Sell : OrderDirections.Buy;
                var close = new Order
                {
                    Portfolio = Portfolio,
                    Security = Security,
                    Direction = exitDir,
                    Type = OrderTypes.Market,
                    QuantityToFill = qty,
                    Comment = "EW_claude_hardclose"
                };
                OpenOrder(close);
            }
            if (_stopOrder != null && _stopOrder.State == OrderStates.Active)
                CancelOrder(_stopOrder);
            _stopOrder = null;
            _openSide = "";
            _trailActive = false;
        }

        private void ManageTrailing(decimal currentPrice)
        {
            if (_stopOrder == null || _entryPrice == 0)
                return;

            var isBuy = _openSide == "BUY";
            var favorableTicks = isBuy
                ? (currentPrice - _entryPrice) / Tick
                : (_entryPrice - currentPrice) / Tick;

            if (favorableTicks > _peakFavorableTicks)
                _peakFavorableTicks = favorableTicks;

            if (!_trailActive && _peakFavorableTicks >= TrailActivateTicks)
                _trailActive = true;

            if (!_trailActive)
                return;

            // Nuevo stop = pico - TrailTicks (solo se mueve a favor).
            var newStopPrice = isBuy
                ? _entryPrice + (_peakFavorableTicks - TrailTicks) * Tick
                : _entryPrice - (_peakFavorableTicks - TrailTicks) * Tick;

            var improves = isBuy
                ? newStopPrice > _stopOrder.TriggerPrice
                : newStopPrice < _stopOrder.TriggerPrice;
            if (!improves)
                return;

            var modified = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = _stopOrder.Direction,
                Type = OrderTypes.Stop,
                TriggerPrice = newStopPrice,
                QuantityToFill = _activeContracts,
                Comment = "EW_claude_trail"
            };
            ModifyOrder(_stopOrder, modified);
            _stopOrder = modified;
        }

        // Override entry fill price with real fill if ATAS fires this (not reliable in Replay).
        protected override void OnNewMyTrade(MyTrade myTrade)
        {
            if (_openSide == "" || !_tradeOpen) return;
            var fillDir = myTrade.OrderDirection == OrderDirections.Buy ? "BUY" : "SELL";
            if (fillDir == _openSide)
                _entryFillPrice = myTrade.Price; // refine with actual fill
        }

        private void LogTrade(DateTime ny, string side, decimal entryFill, decimal exitFill, decimal pnlUsd, string exitComment)
        {
            try
            {
                Directory.CreateDirectory(TraderLogDir);
                var path = Path.Combine(TraderLogDir, "strategy_tester_trades.csv");
                if (!File.Exists(path))
                {
                    File.AppendAllText(path,
                        "fecha,side,contratos,entry_fill,exit_fill,ticks,pnl_usd,exit_motivo,challenge_equity,challenge_dd,regime_paused,queue_wins,queue_size\n");
                }
                var tickMove = side == "BUY"
                    ? (exitFill - entryFill) / Tick
                    : (entryFill - exitFill) / Tick;
                var motivo = exitComment.Contains("hardclose") ? "HARD_CLOSE"
                    : exitComment.Contains("trail") ? "TRAIL"
                    : exitComment.Contains("SL") ? "SL" : "EXIT";
                var dd = Math.Max(0m, _challengePeakEquity - _challengeEquity);
                var wins = _shadowQueue.Count(x => x);
                File.AppendAllText(path, string.Format(CultureInfo.InvariantCulture,
                    "{0:yyyy-MM-dd},{1},{2},{3},{4},{5:0.##},{6:0.00},{7},{8:0.00},{9:0.00},{10},{11},{12}\n",
                    ny.Date, side, _activeContracts, entryFill, exitFill,
                    tickMove, pnlUsd, motivo, _challengeEquity, dd,
                    _regimePaused, wins, _shadowQueue.Count));
            }
            catch
            {
                // logging best-effort; no romper la estrategia.
            }
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
