using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
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

        private decimal Tick => InstrumentInfo?.TickSize ?? 0.25m;

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

            // En posicion -> gestionar trailing.
            if (CurrentPosition != 0 && _openSide != "")
            {
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
    }
}
