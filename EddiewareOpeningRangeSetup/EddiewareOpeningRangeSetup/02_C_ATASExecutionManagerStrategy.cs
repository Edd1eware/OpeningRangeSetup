using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
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
        private bool _autoStarted;

        // Logging realista por fills reales (OnNewMyTrade + ClosedPnL).
        private bool _tradeOpen;
        private decimal _entryFillPrice;
        private string _entryFillSide = "";
        private DateTime _entryFillTimeNy;
        private decimal _lastClosedPnl;

        private const string TraderLogDir =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\strategy_tester_results";

        [Display(Name = "Auto-start (demo/live, NO replay)", Order = 5)]
        public bool AutoStart { get; set; } = false;

        [Display(Name = "Contratos", Order = 10)]
        public int Contracts { get; set; } = 5;

        [Display(Name = "SL ticks", Order = 20)]
        public decimal SlTicks { get; set; } = 50;

        [Display(Name = "Trailing activa (+ticks)", Order = 30)]
        public decimal TrailActivateTicks { get; set; } = 20;

        [Display(Name = "Trailing distancia (ticks)", Order = 40)]
        public decimal TrailTicks { get; set; } = 10;

        [Display(Name = "Solo A+ Speed", Order = 50)]
        public bool OnlyAPlusSpeed { get; set; } = true;

        [Display(Name = "Entrada desde (HH:mm NY)", Order = 60)]
        public string EntryFromNy { get; set; } = "09:30";

        [Display(Name = "Entrada hasta (HH:mm NY)", Order = 61)]
        public string EntryToNy { get; set; } = "09:40";

        [Display(Name = "Cierre forzado (HH:mm NY)", Order = 62)]
        public string HardCloseNy { get; set; } = "09:50";

        private decimal Tick => InstrumentInfo?.TickSize ?? 0.25m;

        private static TimeSpan ParseNy(string value, TimeSpan fallback)
        {
            return TimeSpan.TryParse(value, out var ts) ? ts : fallback;
        }

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            // Auto-arranque (solo demo/live; en replay se deja en Started manual).
            if (AutoStart && !_autoStarted &&
                State != StrategyStates.Started && State != StrategyStates.Error)
            {
                _autoStarted = true;
                Start();
            }

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
            }

            var tod = ny.TimeOfDay;
            var entryFrom = ParseNy(EntryFromNy, new TimeSpan(9, 30, 0));
            var entryTo = ParseNy(EntryToNy, new TimeSpan(9, 40, 0));
            var hardClose = ParseNy(HardCloseNy, new TimeSpan(9, 50, 0));

            // En posicion -> gestionar trailing. Cierre forzado al pasar el horario
            // limite (margen para trades lentos), aunque no haya tocado SL/trailing.
            if (CurrentPosition != 0 && _openSide != "")
            {
                if (tod >= hardClose)
                {
                    Flatten();
                    return;
                }
                ManageTrailing((decimal)candle.Close);
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
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                return;                       // ventana cerrada; no entrar tarde
            }

            var pending = ExecutionSignalBus.Peek(_currentNyDate);
            if (pending == null)
                return;
            if (OnlyAPlusSpeed && !pending.IsAPlusSpeed)
            {
                ExecutionSignalBus.MarkConsumed(_currentNyDate);
                return;
            }

            EnterTrade(pending);
            ExecutionSignalBus.MarkConsumed(_currentNyDate);
        }

        private void EnterTrade(ExecutionSignalBus.PendingEntry e)
        {
            var isBuy = e.Side == "BUY";
            var entryDir = isBuy ? OrderDirections.Buy : OrderDirections.Sell;
            var exitDir = isBuy ? OrderDirections.Sell : OrderDirections.Buy;

            var entry = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = entryDir,
                Type = OrderTypes.Market,
                QuantityToFill = Contracts,
                Comment = "EW_claude_entry"
            };
            OpenOrder(entry);

            _entryPrice = e.EntryPrice;
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
                QuantityToFill = Contracts,
                Comment = "EW_claude_SL"
            };
            OpenOrder(stop);

            _stopOrder = stop;
            _openSide = e.Side;
            _enteredToday = true;
            _trailActive = false;
            _peakFavorableTicks = 0;
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
                QuantityToFill = Contracts,
                Comment = "EW_claude_trail"
            };
            ModifyOrder(_stopOrder, modified);
            _stopOrder = modified;
        }

        // Captura los FILLS REALES (precio con slippage, comision). El PnL en $ se
        // toma de ClosedPnL (ATAS lo calcula con el valor real del NQ: $5/tick).
        protected override void OnNewMyTrade(MyTrade myTrade)
        {
            var comment = myTrade?.Order?.Comment ?? "";

            if (!_tradeOpen && comment.Contains("entry"))
            {
                _tradeOpen = true;
                _entryFillPrice = myTrade.Price;
                _entryFillSide = myTrade.OrderDirection == OrderDirections.Buy ? "BUY" : "SELL";
                _entryFillTimeNy = ToNy(myTrade.Time);
                return;
            }

            // El fill que deja la posicion en 0 = salida -> registrar el trade.
            if (_tradeOpen && CurrentPosition == 0)
            {
                var pnlUsd = ClosedPnL - _lastClosedPnl;   // PnL REALIZADO real ($)
                _lastClosedPnl = ClosedPnL;
                LogTrade(_entryFillTimeNy, _entryFillSide, _entryFillPrice, myTrade.Price, pnlUsd, comment);
                _tradeOpen = false;
            }
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
                        "fecha,side,contratos,entry_fill,exit_fill,ticks,pnl_usd,exit_motivo\n");
                }
                var tickMove = side == "BUY"
                    ? (exitFill - entryFill) / Tick
                    : (entryFill - exitFill) / Tick;
                var motivo = exitComment.Contains("hardclose") ? "HARD_CLOSE"
                    : exitComment.Contains("trail") ? "TRAIL"
                    : exitComment.Contains("SL") ? "SL" : "EXIT";
                File.AppendAllText(path, string.Format(CultureInfo.InvariantCulture,
                    "{0:yyyy-MM-dd},{1},{2},{3},{4},{5:0.##},{6:0.00},{7}\n",
                    ny.Date, side, Contracts, entryFill, exitFill, tickMove, pnlUsd, motivo));
            }
            catch
            {
                // logging best-effort; no romper la estrategia.
            }
        }
    }
}
