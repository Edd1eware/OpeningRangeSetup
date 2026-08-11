using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Drawing;
using System.Globalization;
using System.IO;
using ATAS.DataFeedsCore;
using ATAS.Strategies;
using ATAS.Strategies.Chart;
using OFT.Rendering.Context;
using OFT.Rendering.Tools;

namespace ATAS.Indicators
{
    // TRAPPED v1 (frozen 02/07/2026) - self-detecting fade of the NQ opening-range
    // breakdown. Chart MUST be 1-second bars. OR = 09:30:00-09:30:59 NY, locked at
    // 09:31. First CLOSED 1s bar with close < OR low -> BUY market (fade). Initial
    // SL 50t; trailing activates at +20t and follows peak-40t; hard close 15:59 NY.
    // Sizing ladder v1: 5 if ADN & inside prev-day VA, 3 if inside VA, 1 otherwise.
    // VA bounds and ADN flag come from a premarket file written by the Python logger
    // (or manual properties). Replay-safe patterns copied from the claude_version
    // strategy (auto-restart, OnCalculate position monitoring). Does NOT use the
    // signal bus nor the speed-classification module.
    [DisplayName("EW Trapped Fade v1")]
    public class TrappedFadeStrategy : ChartStrategy
    {
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private DateTime _currentNyDate = DateTime.MinValue;
        private bool _enteredToday;
        private bool _skipToday;
        private decimal _orLow = decimal.MaxValue;
        private decimal _orHigh = decimal.MinValue;
        private bool _orLocked;
        private int _lastSeenBar = -1;

        private Order? _stopOrder;
        private bool _inTrade;
        private decimal _entryPrice;
        private decimal _peakFavorableTicks;
        private bool _trailActive;
        private int _activeContracts;
        private int _prevPosition;
        private DateTime _entryNyTime;

        // premarket sizing info (read once per day)
        private decimal _vaLow, _vaHigh;
        private bool _adnToday;
        private bool _sizingLoaded;

        private const string SizingDir =
            @"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\features";
        private const string ReplayLogFile =
            @"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\features\atrapados_atas_replay.csv";
        // Own Telegram folder: separate sent-dates dedupe from the exporter's.
        private const string TelegramParentDir =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";
        private const string TelegramDir =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\atrapados";

        // ── Properties ────────────────────────────────────────────────────

        [Display(Name = "Auto-start (replay/demo/live)", Order = 5)]
        public bool AutoStart { get; set; } = true;

        [Display(Name = "Notificar a Telegram", Order = 6)]
        public bool UseTelegram { get; set; } = true;

        [Display(Name = "SL inicial (ticks)", Order = 10)]
        public decimal SlTicks { get; set; } = 50;

        [Display(Name = "Trailing activa (+ticks)", Order = 11)]
        public decimal TrailActivateTicks { get; set; } = 20;

        [Display(Name = "Trailing distancia (ticks)", Order = 12)]
        public decimal TrailTicks { get; set; } = 40;

        [Display(Name = "Cierre forzado (HH:mm NY)", Order = 20)]
        public string HardCloseNy { get; set; } = "15:59";

        [Display(Name = "Ultima entrada (HH:mm NY)", Order = 21)]
        public string LastEntryNy { get; set; } = "15:50";

        [Display(Name = "Contratos base", Order = 30, GroupName = "Escalera v1")]
        public int ContractsBase { get; set; } = 1;

        [Display(Name = "Contratos dentro-VA", Order = 31, GroupName = "Escalera v1")]
        public int ContractsVa { get; set; } = 3;

        [Display(Name = "Contratos ADN+VA", Order = 32, GroupName = "Escalera v1")]
        public int ContractsAdnVa { get; set; } = 5;

        [Display(Name = "VA low manual (0=usar archivo)", Order = 33, GroupName = "Escalera v1")]
        public decimal ManualVaLow { get; set; } = 0m;

        [Display(Name = "VA high manual (0=usar archivo)", Order = 34, GroupName = "Escalera v1")]
        public decimal ManualVaHigh { get; set; } = 0m;

        [Display(Name = "ADN hoy (manual)", Order = 35, GroupName = "Escalera v1",
            Description = "Solo se usa si no hay archivo de sizing del dia")]
        public bool ManualAdn { get; set; } = false;

        [Display(Name = "Dibujar VA previo", Order = 40, GroupName = "Visual",
            Description = "Lineas horizontales del value area del dia previo (VAL/VAH)")]
        public bool DrawPrevVa { get; set; } = true;

        [Display(Name = "Dibujar OR", Order = 41, GroupName = "Visual",
            Description = "Lineas horizontales del opening range (09:30-09:31)")]
        public bool DrawOr { get; set; } = true;

        private decimal Tick => InstrumentInfo?.TickSize ?? 0.25m;

        private static TimeSpan ParseNy(string value, TimeSpan fallback)
            => TimeSpan.TryParse(value, out var ts) ? ts : fallback;

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        // ── Premarket sizing file: atrapados_sizing_YYYY-MM-DD.txt ─────────
        // Format (one line): va_low,va_high,adn   e.g. "30011.25,30097.50,1"

        private void LoadSizingForDay(DateTime nyDate)
        {
            if (_sizingLoaded) return;
            _sizingLoaded = true;
            _vaLow = ManualVaLow;
            _vaHigh = ManualVaHigh;
            _adnToday = ManualAdn;
            if (_vaLow > 0 && _vaHigh > 0) return;
            try
            {
                var path = Path.Combine(SizingDir,
                    $"atrapados_sizing_{nyDate:yyyy-MM-dd}.txt");
                if (!File.Exists(path)) return;
                var parts = File.ReadAllText(path).Trim().Split(',');
                if (parts.Length >= 2
                    && decimal.TryParse(parts[0], NumberStyles.Any, CultureInfo.InvariantCulture, out var lo)
                    && decimal.TryParse(parts[1], NumberStyles.Any, CultureInfo.InvariantCulture, out var hi))
                {
                    _vaLow = lo;
                    _vaHigh = hi;
                }
                if (parts.Length >= 3)
                    _adnToday = parts[2].Trim() == "1";
            }
            catch { }
        }

        private int LadderContracts(decimal entryPrice)
        {
            var vaIn = _vaLow > 0 && _vaHigh > 0
                       && entryPrice >= _vaLow && entryPrice <= _vaHigh;
            if (vaIn && _adnToday) return ContractsAdnVa;
            if (vaIn) return ContractsVa;
            return ContractsBase;
        }

        // ── Main cycle ─────────────────────────────────────────────────────

        protected override void OnCalculate(int bar, decimal value)
        {
            if (AutoStart &&
                State != StrategyStates.Started && State != StrategyStates.Error)
            {
                Start();
            }

            var candle = GetCandle(bar);
            var ny = ToNy((DateTime)candle.Time);

            if (ny.Date != _currentNyDate)
            {
                _currentNyDate = ny.Date;
                _enteredToday = false;
                _skipToday = false;
                _orLow = decimal.MaxValue;
                _orHigh = decimal.MinValue;
                _orLocked = false;
                _stopOrder = null;
                _inTrade = false;
                _trailActive = false;
                _peakFavorableTicks = 0;
                _sizingLoaded = false;
            }
            LoadSizingForDay(ny.Date);

            var tod = ny.TimeOfDay;
            var orStart = new TimeSpan(9, 30, 0);
            var orEnd = new TimeSpan(9, 31, 0);
            var hardClose = ParseNy(HardCloseNy, new TimeSpan(15, 59, 0));
            var lastEntry = ParseNy(LastEntryNy, new TimeSpan(15, 50, 0));
            var currentPrice = (decimal)candle.Close;

            // Build the OR from 09:30:00-09:30:59 bars (current values update live;
            // the OR only locks once a bar at/after 09:31 arrives).
            if (tod >= orStart && tod < orEnd)
            {
                if ((decimal)candle.Low < _orLow) _orLow = (decimal)candle.Low;
                if ((decimal)candle.High > _orHigh) _orHigh = (decimal)candle.High;
                return;
            }
            if (tod >= orEnd && !_orLocked && _orLow != decimal.MaxValue)
                _orLocked = true;

            // position-close detection (OnNewMyTrade unreliable in Replay)
            int curPos = (int)CurrentPosition;
            if (_inTrade && _prevPosition != 0 && curPos == 0)
            {
                var tickMove = (currentPrice - _entryPrice) / Tick;
                var pnlUsd = tickMove * _activeContracts * 5m;
                LogReplayTrade(ny, _entryPrice, currentPrice, tickMove, pnlUsd, "CLOSE");
                NotifyTelegram(BuildTradeMessage(ny, currentPrice, tickMove, pnlUsd));
                _inTrade = false;
            }
            _prevPosition = curPos;

            // manage open position
            if (CurrentPosition != 0 && _inTrade)
            {
                if (tod >= hardClose)
                {
                    FlattenAll();
                    return;
                }
                ManageTrailing(currentPrice);
                return;
            }

            // cleanup after flat
            if (CurrentPosition == 0 && _inTrade == false && _stopOrder != null)
            {
                if (_stopOrder.State == OrderStates.Active)
                    CancelOrder(_stopOrder);
                _stopOrder = null;
            }

            if (_enteredToday || _skipToday || !_orLocked)
                return;
            if (tod > lastEntry)
                return;

            // Evaluate only CLOSED bars: when a new bar index appears, judge bar-1.
            if (bar == _lastSeenBar)
                return;
            _lastSeenBar = bar;
            if (bar < 1)
                return;
            var prev = GetCandle(bar - 1);
            var prevNy = ToNy((DateTime)prev.Time);
            if (prevNy.Date != _currentNyDate || prevNy.TimeOfDay < orEnd)
                return;

            var prevClose = (decimal)prev.Close;
            // First closed 1s bar OUTSIDE the OR decides the day:
            if (prevClose > _orHigh)
            {
                _skipToday = true;   // first break was UP -> no fade today
                NotifyTelegram(
                    $"TRAPPED {_currentNyDate:yyyy-MM-dd}\n" +
                    $"SKIP: primer breakout fue ALCISTA ({prevClose}) — sin fade hoy.\n" +
                    $"OR: [{_orLow} , {_orHigh}]");
                return;
            }
            if (prevClose < _orLow)
            {
                var contracts = LadderContracts(prevClose);
                EnterFade(prevClose, contracts, ny);
            }
        }

        private void EnterFade(decimal signalClose, int contracts, DateTime ny)
        {
            _enteredToday = true;
            _inTrade = true;
            _entryPrice = signalClose;      // refined by OnNewMyTrade when it fires
            _activeContracts = contracts;
            _trailActive = false;
            _peakFavorableTicks = 0;
            _entryNyTime = ny;

            var entryOrder = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = OrderDirections.Buy,
                Type = OrderTypes.Market,
                QuantityToFill = contracts,
                Comment = $"TRAPPED_entry_{contracts}c"
            };
            OpenOrder(entryOrder);

            var stop = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = OrderDirections.Sell,
                Type = OrderTypes.Stop,
                TriggerPrice = signalClose - SlTicks * Tick,
                QuantityToFill = contracts,
                Comment = "TRAPPED_SL"
            };
            OpenOrder(stop);
            _stopOrder = stop;
        }

        private void FlattenAll()
        {
            var qty = Math.Abs(CurrentPosition);
            if (qty > 0)
            {
                OpenOrder(new Order
                {
                    Portfolio = Portfolio,
                    Security = Security,
                    Direction = OrderDirections.Sell,
                    Type = OrderTypes.Market,
                    QuantityToFill = qty,
                    Comment = "TRAPPED_EOD"
                });
            }
            if (_stopOrder != null && _stopOrder.State == OrderStates.Active)
                CancelOrder(_stopOrder);
            _stopOrder = null;
        }

        private void ManageTrailing(decimal currentPrice)
        {
            if (_stopOrder == null || _entryPrice == 0)
                return;

            var favorableTicks = (currentPrice - _entryPrice) / Tick;
            if (favorableTicks > _peakFavorableTicks)
                _peakFavorableTicks = favorableTicks;

            if (!_trailActive && _peakFavorableTicks >= TrailActivateTicks)
                _trailActive = true;
            if (!_trailActive)
                return;

            var newStopPrice = _entryPrice + (_peakFavorableTicks - TrailTicks) * Tick;
            if (newStopPrice <= _stopOrder.TriggerPrice)
                return;

            var modified = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = OrderDirections.Sell,
                Type = OrderTypes.Stop,
                TriggerPrice = newStopPrice,
                QuantityToFill = _activeContracts,
                Comment = "TRAPPED_trail"
            };
            ModifyOrder(_stopOrder, modified);
            _stopOrder = modified;
        }

        // ── Chart drawing: prev-day VA and today's OR as horizontal lines ──

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (ChartInfo == null) return;
            var container = ChartInfo.PriceChartContainer;
            if (container == null) return;
            var right = container.Region.Width;

            var vaFont = new RenderFont("Arial", 9);

            if (DrawPrevVa && _vaLow > 0 && _vaHigh > 0)
            {
                var vaPen = new RenderPen(Color.Goldenrod, 1);
                DrawPriceLine(context, container, right, vaPen, vaFont,
                    _vaHigh, $"VAH prev {_vaHigh}");
                DrawPriceLine(context, container, right, vaPen, vaFont,
                    _vaLow, $"VAL prev {_vaLow}");
            }

            if (DrawOr && _orLocked && _orLow != decimal.MaxValue)
            {
                var orPen = new RenderPen(Color.DeepSkyBlue, 1);
                DrawPriceLine(context, container, right, orPen, vaFont,
                    _orHigh, $"OR high {_orHigh}");
                DrawPriceLine(context, container, right, orPen, vaFont,
                    _orLow, $"OR low {_orLow}");
            }
        }

        private static void DrawPriceLine(RenderContext context, dynamic container,
            int right, RenderPen pen, RenderFont font, decimal price, string label)
        {
            int y = container.GetYByPrice(price, false);
            context.DrawLine(pen, 0, y, right, y);
            context.DrawString(label, font, pen.Color, 4, y - 14);
        }

        protected override void OnNewMyTrade(MyTrade myTrade)
        {
            if (!_inTrade) return;
            if (myTrade.OrderDirection == OrderDirections.Buy)
                _entryPrice = myTrade.Price;
        }

        private string BuildTradeMessage(DateTime ny, decimal exit, decimal ticks, decimal pnlUsd)
        {
            var vaTxt = _vaLow > 0 && _vaHigh > 0
                ? $"[{_vaLow} , {_vaHigh}]" : "sin datos";
            var vaIn = _vaLow > 0 && _entryPrice >= _vaLow && _entryPrice <= _vaHigh;
            var celda = vaIn && _adnToday ? "ADN+VA (5)" : vaIn ? "dentro-VA (3)" : "base (1)";
            return
                $"TRAPPED {_currentNyDate:yyyy-MM-dd} — TRADE CERRADO\n" +
                $"Entrada: {_entryNyTime:HH:mm:ss} NY @ {_entryPrice} (fade breakdown)\n" +
                $"OR: [{_orLow} , {_orHigh}] | VA previo: {vaTxt}\n" +
                $"Celda escalera: {celda} -> {_activeContracts} contrato(s)\n" +
                $"Salida: {ny:HH:mm:ss} @ {exit}\n" +
                $"Resultado: {ticks:+0.#;-0.#} ticks = {pnlUsd:+0.00;-0.00} USD\n" +
                $"Gestion: SL {SlTicks}t | trail act {TrailActivateTicks}t dist {TrailTicks}t | EOD {HardCloseNy}";
        }

        private void NotifyTelegram(string message)
        {
            if (!UseTelegram) return;
            try
            {
                Directory.CreateDirectory(TelegramDir);
                var creds = Path.Combine(TelegramDir, "telegram_credentials.txt");
                var parentCreds = Path.Combine(TelegramParentDir, "telegram_credentials.txt");
                if (!File.Exists(creds) && File.Exists(parentCreds))
                    File.Copy(parentCreds, creds);
                TelegramTradeNotifier.QueueTerminalResult(TelegramDir, _currentNyDate, message);
            }
            catch
            {
                // Telegram nunca debe romper la estrategia.
            }
        }

        private void LogReplayTrade(DateTime ny, decimal entry, decimal exit,
            decimal ticks, decimal pnlUsd, string motivo)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(ReplayLogFile)!);
                if (!File.Exists(ReplayLogFile))
                    File.AppendAllText(ReplayLogFile,
                        "fecha,hora_ny,contratos,entry,exit,ticks,pnl_usd,motivo,or_low,or_high\n");
                File.AppendAllText(ReplayLogFile, string.Format(CultureInfo.InvariantCulture,
                    "{0:yyyy-MM-dd},{1:HH:mm:ss},{2},{3},{4},{5:0.##},{6:0.00},{7},{8},{9}\n",
                    _currentNyDate, ny, _activeContracts, entry, exit, ticks, pnlUsd,
                    motivo, _orLow, _orHigh));
            }
            catch { }
        }
    }
}
