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
    // ORB-GREEN v1 (frozen 28/07/2026) - long-only opening range breakout of NQ
    // gated by a single causal bit: the 09:30:00 one-second bar must close above
    // its own open. Chart MUST be 1-second bars.
    //
    // Measured on 496 breakouts, 2022-04 to 2026-07, DST aware:
    //     unfiltered   WR 52.82%   below the 53.33% breakeven of a 60/60 bracket
    //     filtered     WR 58.44%   PF 1.41   EV +6.12 ticks   4.76 trades/month
    //     dev 2022-24 57.40% -> holdout 2025-26 60.81%
    //
    // NOT a validated edge. The green-bar component failed two independent
    // falsifications earlier the same day: it does not work on the short side, and
    // it adds nothing on a five minute opening range. It was also the best of 56
    // searched combinations, and 2022 is negative. This strategy exists to collect
    // prospective observations in replay, never to authorise capital.
    //
    // Rules, frozen. Nothing here may be tuned:
    //     gate   the 09:30:00 NY bar closes strictly above its open
    //     OR     09:30:00-09:30:59 NY, locked when a bar at/after 09:31 arrives
    //     entry  first CLOSED 1s bar whose close is above the OR high
    //     skip   if a bar closes below the OR low first, the day is skipped
    //     bracket TP 60 ticks, SL 60 ticks, symmetric, no trailing, no breakeven
    //     hard close 15:59 NY
    [DisplayName("EW ORB Green First Second v1")]
    public class OpeningRangeGreenFirstSecond : ChartStrategy
    {
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private DateTime _currentNyDate = DateTime.MinValue;
        private bool _enteredToday;
        private bool _skipToday;
        private bool _gateEvaluated;
        private bool _gatePassed;
        private decimal _orHigh = decimal.MinValue;
        private decimal _orLow = decimal.MaxValue;
        private bool _orLocked;
        private int _lastSeenBar = -1;

        private Order? _stopOrder;
        private Order? _targetOrder;
        private bool _inTrade;
        private decimal _entryPrice;
        private DateTime _entryNyTime;

        private const string LogDir =
            @"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\orb_rr1_battery_v1\output";
        private const string LogFile = "orb_green_replay_log.csv";

        [Display(Name = "Contracts", GroupName = "Sizing", Order = 10)]
        public int Contracts { get; set; } = 1;

        [Display(Name = "TP ticks", GroupName = "Bracket", Order = 20)]
        public int TpTicks { get; set; } = 60;

        [Display(Name = "SL ticks", GroupName = "Bracket", Order = 21)]
        public int SlTicks { get; set; } = 60;

        [Display(Name = "Require green first second", GroupName = "Filter", Order = 30)]
        public bool RequireGreenFirstSecond { get; set; } = true;

        [Display(Name = "Last entry NY", GroupName = "Session", Order = 40)]
        public string LastEntryNy { get; set; } = "15:50:00";

        [Display(Name = "Hard close NY", GroupName = "Session", Order = 41)]
        public string HardCloseNy { get; set; } = "15:59:00";

        [Display(Name = "Auto start", GroupName = "Session", Order = 42)]
        public bool AutoStart { get; set; } = true;

        [Display(Name = "Write replay log", GroupName = "Session", Order = 43)]
        public bool WriteLog { get; set; } = true;

        private decimal Tick => InstrumentInfo?.TickSize ?? 0.25m;

        private DateTime ToNy(DateTime time)
        {
            var utc = time.Kind == DateTimeKind.Utc
                ? time
                : DateTime.SpecifyKind(time, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        private static TimeSpan ParseNy(string text, TimeSpan fallback)
        {
            return TimeSpan.TryParse(text, CultureInfo.InvariantCulture, out var parsed)
                ? parsed
                : fallback;
        }

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
                _gateEvaluated = false;
                _gatePassed = false;
                _orHigh = decimal.MinValue;
                _orLow = decimal.MaxValue;
                _orLocked = false;
                _inTrade = false;
                _stopOrder = null;
                _targetOrder = null;
            }

            var tod = ny.TimeOfDay;
            var orStart = new TimeSpan(9, 30, 0);
            var orEnd = new TimeSpan(9, 31, 0);
            var firstSecondEnd = new TimeSpan(9, 30, 1);
            var hardClose = ParseNy(HardCloseNy, new TimeSpan(15, 59, 0));
            var lastEntry = ParseNy(LastEntryNy, new TimeSpan(15, 50, 0));

            // The gate: the very first second of the session. Evaluated once, from
            // the bar whose NY time is 09:30:00 exactly.
            if (!_gateEvaluated && tod >= orStart && tod < firstSecondEnd)
            {
                _gatePassed = (decimal)candle.Close > (decimal)candle.Open;
                _gateEvaluated = true;
            }

            // Opening range accumulates during 09:30:00-09:30:59 and locks after.
            if (tod >= orStart && tod < orEnd)
            {
                if ((decimal)candle.High > _orHigh)
                    _orHigh = (decimal)candle.High;
                if ((decimal)candle.Low < _orLow)
                    _orLow = (decimal)candle.Low;
            }
            else if (tod >= orEnd && !_orLocked &&
                     _orHigh > decimal.MinValue && _orLow < decimal.MaxValue)
            {
                _orLocked = true;
                if (RequireGreenFirstSecond && !_gatePassed)
                    _skipToday = true;
            }

            if (tod >= hardClose)
            {
                if (_inTrade || CurrentPosition != 0)
                    FlattenAll();
                return;
            }

            if (_enteredToday || _skipToday || !_orLocked)
                return;
            if (tod > lastEntry)
                return;

            // Judge only CLOSED bars: when a new bar index appears, judge bar-1.
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

            // The first closed bar outside the range decides the day.
            if (prevClose < _orLow)
            {
                _skipToday = true;
                return;
            }
            if (prevClose > _orHigh)
                EnterLong(prevClose, ny);
        }

        private void EnterLong(decimal signalClose, DateTime ny)
        {
            _enteredToday = true;
            _inTrade = true;
            _entryPrice = signalClose;
            _entryNyTime = ny;

            OpenOrder(new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = OrderDirections.Buy,
                Type = OrderTypes.Market,
                QuantityToFill = Contracts,
                Comment = "ORBGREEN_entry"
            });

            var stop = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = OrderDirections.Sell,
                Type = OrderTypes.Stop,
                TriggerPrice = signalClose - SlTicks * Tick,
                QuantityToFill = Contracts,
                Comment = "ORBGREEN_SL"
            };
            OpenOrder(stop);
            _stopOrder = stop;

            var target = new Order
            {
                Portfolio = Portfolio,
                Security = Security,
                Direction = OrderDirections.Sell,
                Type = OrderTypes.Limit,
                Price = signalClose + TpTicks * Tick,
                QuantityToFill = Contracts,
                Comment = "ORBGREEN_TP"
            };
            OpenOrder(target);
            _targetOrder = target;

            AppendLog($"{_currentNyDate:yyyy-MM-dd},{ny:HH:mm:ss},ENTRY,{signalClose}," +
                      $"{_orHigh},{_orLow},{_gatePassed}");
        }

        private void FlattenAll()
        {
            var quantity = Math.Abs(CurrentPosition);
            if (quantity > 0)
            {
                OpenOrder(new Order
                {
                    Portfolio = Portfolio,
                    Security = Security,
                    Direction = CurrentPosition > 0
                        ? OrderDirections.Sell
                        : OrderDirections.Buy,
                    Type = OrderTypes.Market,
                    QuantityToFill = quantity,
                    Comment = "ORBGREEN_EOD"
                });
            }
            if (_stopOrder != null && _stopOrder.State == OrderStates.Active)
                CancelOrder(_stopOrder);
            if (_targetOrder != null && _targetOrder.State == OrderStates.Active)
                CancelOrder(_targetOrder);
            _stopOrder = null;
            _targetOrder = null;
            _inTrade = false;
        }

        private void AppendLog(string line)
        {
            if (!WriteLog)
                return;
            try
            {
                Directory.CreateDirectory(LogDir);
                var path = Path.Combine(LogDir, LogFile);
                if (!File.Exists(path))
                {
                    File.AppendAllText(
                        path,
                        "date,time_ny,event,price,or_high,or_low,gate_green\n");
                }
                File.AppendAllText(path, line + "\n");
            }
            catch
            {
                // logging must never break the strategy
            }
        }

        protected override void OnNewMyTrade(MyTrade myTrade)
        {
            if (myTrade == null)
                return;
            AppendLog($"{_currentNyDate:yyyy-MM-dd}," +
                      $"{ToNy(myTrade.Time):HH:mm:ss},FILL,{myTrade.Price},,,{_gatePassed}");
        }
    }
}
