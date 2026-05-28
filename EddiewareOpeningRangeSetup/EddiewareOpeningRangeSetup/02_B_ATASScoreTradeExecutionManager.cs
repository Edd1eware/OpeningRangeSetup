using System;
using System.ComponentModel;
using ATAS.Indicators;

namespace ATAS.Indicators
{
    [DisplayName("02_B_ATASScoreTradeExecutionManager")]
    public class ATASScoreTradeExecutionManager : Indicator
    {
        private const decimal SetupTickSize = 0.25m;
        private const decimal HardMaxTradeTicks = 120m;
        private const decimal APlusStopTicks = 100m;
        private readonly ScoreTradeSignalEngine _signalEngine = new ScoreTradeSignalEngine();

        private DateTime _currentDate = DateTime.MinValue;
        private decimal _orHigh;
        private decimal _orLow;
        private int _orBar = -1;
        private bool _orReady;
        private bool _tradePlanned;

        [DisplayName("Enable Execution")]
        public bool EnableExecution { get; set; } = false;

        [DisplayName("Opening Time UTC")]
        public TimeSpan OpeningTimeUtc { get; set; } = new TimeSpan(13, 30, 0);

        [DisplayName("Max Signal Time UTC")]
        public TimeSpan MaxSignalTimeUtc { get; set; } = new TimeSpan(14, 30, 0);

        [DisplayName("Min Score / Cutoff Score")]
        public int MinScore { get; set; } = 5;

        [DisplayName("Min OR Range Ticks")]
        public decimal MinOrRangeTicks { get; set; } = 40;

        [DisplayName("Max OR Range Ticks")]
        public decimal MaxOrRangeTicks { get; set; } = 350;

        [DisplayName("Min Body Breakout Ticks")]
        public decimal MinBodyBreakoutTicks { get; set; } = 10;

        [DisplayName("Min Volume")]
        public decimal MinVolume { get; set; } = 800;

        [DisplayName("Min Abs Delta")]
        public decimal MinAbsDelta { get; set; } = 25;

        [DisplayName("Min Normal Speed Ticks/Sec")]
        public decimal MinNormalSpeedTicksPerSecond { get; set; } = 2;

        [DisplayName("Min A+ Speed Ticks/Sec")]
        public decimal APlusSpeedTicksPerSecond { get; set; } = 5;

        [DisplayName("Replay Speed Multiplier")]
        public decimal ReplaySpeedMultiplier { get; set; } = 1;

        [DisplayName("Min SL/TP Ticks")]
        public decimal MinTradeTicks { get; set; } = 60;

        [DisplayName("Max SL/TP Ticks")]
        public decimal MaxTradeTicks { get; set; } = 120;

        public ATASScoreTradeExecutionManager()
        {
            Name = "02_B_ATASScoreTradeExecutionManager";
            EnableCustomDrawing = false;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            var candle = GetCandle(bar);

            if (candle.Time.Date != _currentDate)
                ResetDay(candle.Time.Date);

            _signalEngine.UpdateSpeedClock(bar);

            var closedBar = bar - 1;

            if (!_orReady && closedBar >= 0)
            {
                var closedCandle = GetCandle(closedBar);

                if (IsOpeningCandle(closedCandle))
                {
                    _orHigh = closedCandle.High;
                    _orLow = closedCandle.Low;
                    _orBar = closedBar;
                    _orReady = true;
                }
            }

            if (!_orReady || _tradePlanned || bar <= _orBar)
                return;

            var signal = _signalEngine.Calculate(bar, candle, new Func<int, dynamic>(GetCandle), new ScoreTradeSignalRequest
            {
                OrLow = _orLow,
                OrHigh = _orHigh,
                CurrentTime = candle.Time,
                SessionDate = candle.Time.Date,
                GetSessionTime = c => c.Time,
                SignalStartTime = OpeningTimeUtc,
                SignalEndTime = MaxSignalTimeUtc,
                NormalSpeedAllowedUntilTime = OpeningTimeUtc.Add(new TimeSpan(0, 3, 59)),
                TickSize = SetupTickSize,
                MinScore = MinScore,
                MinOrRangeTicks = MinOrRangeTicks,
                MaxOrRangeTicks = MaxOrRangeTicks,
                MinBodyBreakoutTicks = MinBodyBreakoutTicks,
                MinVolume = MinVolume,
                MinAbsDelta = MinAbsDelta,
                MinNormalSpeedTicksPerSecond = MinNormalSpeedTicksPerSecond,
                APlusSpeedTicksPerSecond = APlusSpeedTicksPerSecond,
                ReplaySpeedMultiplier = ReplaySpeedMultiplier
            });

            if (!signal.IsReady)
                return;

            var plan = TradeManagerTpSlBeExit.CreateInitialPlan(new TradeManagerTpSlBeExit.TradePlanRequest
            {
                Side = signal.Side,
                SpeedLabel = signal.SpeedLabel,
                Entry = signal.EntryPrice,
                OrLow = signal.OrLow,
                OrHigh = signal.OrHigh,
                TickSize = SetupTickSize,
                MinTradeTicks = MinTradeTicks,
                MaxTradeTicks = Math.Min(MaxTradeTicks, HardMaxTradeTicks),
                HardMaxTradeTicks = HardMaxTradeTicks,
                APlusStopTicks = APlusStopTicks,
                CapSellStopAtOrHigh = true,
                EnforceMinExitDistance = false
            });

            _tradePlanned = true;

            if (!EnableExecution)
                return;

            // Order submission will be added only after demo API wiring is confirmed.
            _ = plan;
        }

        private bool IsOpeningCandle(dynamic candle)
        {
            var time = candle.Time.TimeOfDay;
            return time.Hours == OpeningTimeUtc.Hours && time.Minutes == OpeningTimeUtc.Minutes;
        }

        private void ResetDay(DateTime date)
        {
            _currentDate = date;
            _orHigh = 0;
            _orLow = 0;
            _orBar = -1;
            _orReady = false;
            _tradePlanned = false;
            _signalEngine.ResetDay();
        }
    }
}
