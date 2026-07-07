using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using ATAS.Indicators.Drawing;
using OFT.Rendering.Context;

namespace ATAS.Indicators
{
    /// <summary>
    /// Independent opening-range candidate engine and exact virtual-trade logger.
    /// It sends no orders.  Every candidate is built from closed information and is
    /// resolved tick-by-tick, including a marked-to-market timeout exit.
    /// </summary>
    [DisplayName("Opening Range Research Codex")]
    public sealed class OpeningRangeResearch_codex : Indicator
    {
        private const decimal FallbackTick = 0.25m;
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
        private readonly List<Candidate_codex> _candidates = new();
        private readonly List<BarSnapshot_codex> _bars = new();
        private readonly HashSet<string> _candidateKeys = new(StringComparer.Ordinal);

        private DateTime _sessionDate = DateTime.MinValue;
        private int _lastClosedBar = -1;
        private decimal _orHigh;
        private decimal _orLow;
        private bool _orReady;
        private bool _seenOutsideUp;
        private bool _seenOutsideDown;
        private decimal _cumulativeDelta;
        private decimal _cumTypicalVolume;
        private decimal _cumVolume;
        private decimal _lastPrice;
        private DateTime _lastMarketTimeNy = DateTime.MinValue;
        private int _strategySignals;
        private int _lastStrategyBar = int.MinValue;
        private bool _sessionComplete;

        [Display(Name = "Candidate start NY", Order = 1)]
        public TimeSpan CandidateStartNy { get; set; } = new(9, 31, 0);

        [Display(Name = "Candidate end NY", Order = 2)]
        public TimeSpan CandidateEndNy { get; set; } = new(9, 40, 0);

        [Display(Name = "Virtual exit NY", Order = 3)]
        public TimeSpan VirtualExitNy { get; set; } = new(9, 45, 0);

        [Display(Name = "TP ticks", Order = 4)]
        public decimal TargetTicks { get; set; } = 40m;

        [Display(Name = "SL ticks", Order = 5)]
        public decimal StopTicks { get; set; } = 40m;

        [Display(Name = "Round-trip slippage ticks", Order = 6)]
        public decimal SlippageTicks { get; set; } = 2m;

        [Display(Name = "Min OR ticks", Order = 7)]
        public decimal MinOrTicks { get; set; } = 30m;

        [Display(Name = "Max OR ticks", Order = 8)]
        public decimal MaxOrTicks { get; set; } = 220m;

        [Display(Name = "Near-boundary ticks", Order = 9)]
        public decimal NearBoundaryTicks { get; set; } = 12m;

        [Display(Name = "Failed-break excursion ticks", Order = 10)]
        public decimal FailedBreakTicks { get; set; } = 8m;

        [Display(Name = "Strategy score threshold", Order = 11)]
        public int StrategyScoreThreshold { get; set; } = 6;

        [Display(Name = "Max accepted signals/day", Order = 12)]
        public int MaxStrategySignalsPerDay { get; set; } = 2;

        [Display(Name = "Accepted signal cooldown bars", Order = 13)]
        public int AcceptedCooldownBars { get; set; } = 2;

        [Display(Name = "Output folder", Order = 14)]
        public string OutputFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddieWare_OpeningRangeSetup_version_codex\research_data_codex";

        public OpeningRangeResearch_codex()
        {
            Name = "Opening Range Research Codex";
            EnableCustomDrawing = false;
        }

        protected override void OnRecalculate()
        {
            base.OnRecalculate();
            ResetAll_codex();
        }

        protected override void OnNewTrade(MarketDataArg trade)
        {
            base.OnNewTrade(trade);
            var ny = ToNy_codex(trade.Time);
            ProcessMarketPrice_codex(trade.Price, ny);
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            dynamic current = GetCandle(bar);
            var currentNy = ToNy_codex((DateTime)current.Time);
            ProcessMarketPrice_codex(value, currentNy);

            var closed = bar - 1;
            if (closed <= _lastClosedBar)
                return;

            for (var b = _lastClosedBar + 1; b <= closed; b++)
                ProcessClosedBar_codex(b);
            _lastClosedBar = closed;
            PersistStatus_codex(currentNy);
        }

        private void ProcessClosedBar_codex(int bar)
        {
            dynamic candle = GetCandle(bar);
            var ny = ToNy_codex((DateTime)candle.Time);
            if (ny.Date != _sessionDate)
            {
                var previousPrice = _bars.Count > 0 ? _bars[^1].Close : _lastPrice;
                var previousTime = _bars.Count > 0 ? _bars[^1].TimeNy : _lastMarketTimeNy;
                FinalizeOpenCandidates_codex(previousPrice, previousTime, "SESSION_END");
                ResetSession_codex(ny.Date);
            }

            var snapshot = new BarSnapshot_codex
            {
                Bar = bar,
                TimeNy = ny,
                Open = Convert.ToDecimal(candle.Open),
                High = Convert.ToDecimal(candle.High),
                Low = Convert.ToDecimal(candle.Low),
                Close = Convert.ToDecimal(candle.Close),
                Volume = Convert.ToDecimal(candle.Volume),
                Delta = Convert.ToDecimal(candle.Delta)
            };

            var tod = ny.TimeOfDay;
            if (tod < new TimeSpan(9, 30, 0) || tod >= new TimeSpan(16, 0, 0))
                return;

            _bars.Add(snapshot);
            _cumulativeDelta += snapshot.Delta;
            _cumTypicalVolume += ((snapshot.High + snapshot.Low + snapshot.Close) / 3m) * snapshot.Volume;
            _cumVolume += snapshot.Volume;

            if (tod == new TimeSpan(9, 30, 0))
            {
                _orHigh = snapshot.High;
                _orLow = snapshot.Low;
                _orReady = true;
                return;
            }

            if (!_orReady)
                return;

            var tick = Tick_codex();
            if (snapshot.High >= _orHigh + FailedBreakTicks * tick)
                _seenOutsideUp = true;
            if (snapshot.Low <= _orLow - FailedBreakTicks * tick)
                _seenOutsideDown = true;

            if (tod >= VirtualExitNy)
            {
                FinalizeOpenCandidates_codex(snapshot.Close, ny, "TIMEOUT");
                _sessionComplete = true;
                return;
            }

            if (tod < CandidateStartNy || tod >= CandidateEndNy)
                return;

            GenerateCandidates_codex(snapshot);
        }

        private void GenerateCandidates_codex(BarSnapshot_codex bar)
        {
            var tick = Tick_codex();
            var orTicks = (_orHigh - _orLow) / tick;
            if (orTicks < MinOrTicks || orTicks > MaxOrTicks)
                return;

            if (bar.Close > _orHigh)
            {
                TryCreateCandidate_codex(bar, "CONTINUATION", "BUY");
                TryCreateCandidate_codex(bar, "EXTENSION_FADE", "SELL");
            }
            else if (bar.Close < _orLow)
            {
                TryCreateCandidate_codex(bar, "CONTINUATION", "SELL");
                TryCreateCandidate_codex(bar, "EXTENSION_FADE", "BUY");
            }

            if (bar.Close <= _orHigh && bar.Close >= _orHigh - NearBoundaryTicks * tick)
                TryCreateCandidate_codex(bar, "PRESSURE", "BUY");
            if (bar.Close >= _orLow && bar.Close <= _orLow + NearBoundaryTicks * tick)
                TryCreateCandidate_codex(bar, "PRESSURE", "SELL");

            if (_seenOutsideUp && bar.Close <= _orHigh && bar.Delta < 0)
                TryCreateCandidate_codex(bar, "FAILED_BREAK", "SELL");
            if (_seenOutsideDown && bar.Close >= _orLow && bar.Delta > 0)
                TryCreateCandidate_codex(bar, "FAILED_BREAK", "BUY");
        }

        private void TryCreateCandidate_codex(BarSnapshot_codex bar, string setup, string side)
        {
            var key = $"{_sessionDate:yyyyMMdd}:{bar.Bar}:{setup}:{side}";
            if (!_candidateKeys.Add(key))
                return;

            var previous = _bars.Count >= 2 ? _bars[^2] : null;
            var momentum3 = MomentumTicks_codex(3);
            var vwap = _cumVolume > 0 ? _cumTypicalVolume / _cumVolume : bar.Close;
            var tick = Tick_codex();
            var direction = side == "BUY" ? 1m : -1m;
            var body = Math.Abs(bar.Close - bar.Open) / tick;
            var range = Math.Max(tick, bar.High - bar.Low) / tick;
            var bodyEfficiency = body / range;
            var previousVolume = previous?.Volume ?? bar.Volume;
            var previousDelta = previous?.Delta ?? 0m;
            var volumeRatio = previousVolume > 0 ? bar.Volume / previousVolume : 1m;
            var deltaRatio = bar.Volume > 0 ? Math.Abs(bar.Delta) / bar.Volume : 0m;
            var alignedDelta = direction * bar.Delta > 0;
            var alignedMomentum = direction * momentum3 > 0;
            var alignedVwap = direction * (bar.Close - vwap) >= 0;
            var orTicks = (_orHigh - _orLow) / tick;
            var extension = side == "BUY"
                ? (bar.Close - _orHigh) / tick
                : (_orLow - bar.Close) / tick;
            var outsideDistance = bar.Close > _orHigh
                ? (bar.Close - _orHigh) / tick
                : bar.Close < _orLow
                    ? (_orLow - bar.Close) / tick
                    : 0m;
            if (setup == "EXTENSION_FADE")
                extension = outsideDistance;
            var rejectionWick = side == "SELL"
                ? (bar.High - Math.Max(bar.Open, bar.Close)) / tick
                : (Math.Min(bar.Open, bar.Close) - bar.Low) / tick;

            var score = 0;
            if (alignedDelta && Math.Abs(bar.Delta) >= 25m) score += 2;
            if (deltaRatio >= 0.08m) score += 1;
            if (volumeRatio >= 0.75m) score += 1;
            if (bodyEfficiency >= 0.45m) score += 1;
            if (alignedMomentum && Math.Abs(momentum3) >= 4m) score += 1;
            if (alignedVwap) score += 1;
            if (orTicks >= 40m && orTicks <= 180m) score += 1;
            if (bar.TimeNy.TimeOfDay <= new TimeSpan(9, 35, 0)) score += 1;
            if (setup == "FAILED_BREAK" && alignedDelta) score += 1;
            if (setup == "EXTENSION_FADE")
            {
                if (outsideDistance >= 8m && outsideDistance <= 100m) score += 2;
                if (rejectionWick >= 4m) score += 2;
                if (bar.TimeNy.TimeOfDay >= new TimeSpan(9, 32, 0)) score += 1;
                if (deltaRatio >= 0.18m) score += 1;
            }

            var setupCanTrade = setup == "FAILED_BREAK" || setup == "EXTENSION_FADE";
            var accepted = setupCanTrade
                && score >= StrategyScoreThreshold
                && _strategySignals < MaxStrategySignalsPerDay
                && bar.Bar - _lastStrategyBar >= AcceptedCooldownBars
                && !_candidates.Any(candidate => candidate.WouldTrade && !candidate.IsResolved);
            if (accepted)
            {
                _strategySignals++;
                _lastStrategyBar = bar.Bar;
            }

            var candidate = new Candidate_codex
            {
                CandidateId = key,
                SessionDate = _sessionDate,
                EntryTimeNy = bar.TimeNy,
                EntryBar = bar.Bar,
                Setup = setup,
                Side = side,
                Entry = bar.Close,
                OrHigh = _orHigh,
                OrLow = _orLow,
                OrTicks = orTicks,
                ExtensionTicks = extension,
                BodyTicks = body,
                RangeTicks = range,
                BodyEfficiency = bodyEfficiency,
                Volume = bar.Volume,
                PreviousVolume = previousVolume,
                VolumeRatio = volumeRatio,
                Delta = bar.Delta,
                PreviousDelta = previousDelta,
                DeltaRatio = deltaRatio,
                DeltaChange = bar.Delta - previousDelta,
                CumulativeDelta = _cumulativeDelta,
                Momentum3Ticks = momentum3,
                DistanceVwapTicks = (bar.Close - vwap) / tick,
                Score = score,
                WouldTrade = accepted,
                TargetTicks = TargetTicks,
                StopTicks = StopTicks
            };
            _candidates.Add(candidate);
            PersistSession_codex();
        }

        private void ProcessMarketPrice_codex(decimal price, DateTime marketTimeNy)
        {
            if (price <= 0)
                return;
            _lastPrice = price;
            _lastMarketTimeNy = marketTimeNy;
            if (_sessionDate == DateTime.MinValue || marketTimeNy.Date != _sessionDate)
                return;

            var tick = Tick_codex();
            var changed = false;
            foreach (var candidate in _candidates)
            {
                if (candidate.IsResolved || marketTimeNy <= candidate.EntryTimeNy)
                    continue;
                var direction = candidate.Side == "BUY" ? 1m : -1m;
                var signedTicks = direction * (price - candidate.Entry) / tick;
                candidate.MfeTicks = Math.Max(candidate.MfeTicks, signedTicks);
                candidate.MaeTicks = Math.Max(candidate.MaeTicks, -signedTicks);
                if (signedTicks >= candidate.TargetTicks)
                {
                    ResolveCandidate_codex(candidate, "WIN", marketTimeNy, price,
                        candidate.TargetTicks - SlippageTicks);
                    changed = true;
                }
                else if (signedTicks <= -candidate.StopTicks)
                {
                    ResolveCandidate_codex(candidate, "LOSS", marketTimeNy, price,
                        -candidate.StopTicks - SlippageTicks);
                    changed = true;
                }
            }
            if (changed)
                PersistSession_codex();
        }

        private void FinalizeOpenCandidates_codex(decimal price, DateTime timeNy, string reason)
        {
            if (_sessionDate == DateTime.MinValue || price <= 0)
                return;
            var tick = Tick_codex();
            var changed = false;
            foreach (var candidate in _candidates)
            {
                if (candidate.IsResolved)
                    continue;
                var direction = candidate.Side == "BUY" ? 1m : -1m;
                var markedTicks = direction * (price - candidate.Entry) / tick - SlippageTicks;
                ResolveCandidate_codex(candidate, reason, timeNy, price, markedTicks);
                changed = true;
            }
            if (changed)
                PersistSession_codex();
        }

        private static void ResolveCandidate_codex(
            Candidate_codex candidate,
            string outcome,
            DateTime exitTimeNy,
            decimal exitPrice,
            decimal pnlTicks)
        {
            candidate.Outcome = outcome;
            candidate.ExitTimeNy = exitTimeNy;
            candidate.ExitPrice = exitPrice;
            candidate.PnlTicks = pnlTicks;
        }

        private decimal MomentumTicks_codex(int bars)
        {
            if (_bars.Count < 2)
                return 0m;
            var last = _bars[^1].Close;
            var startIndex = Math.Max(0, _bars.Count - 1 - bars);
            return (last - _bars[startIndex].Close) / Tick_codex();
        }

        private void PersistSession_codex()
        {
            if (_sessionDate == DateTime.MinValue)
                return;
            try
            {
                Directory.CreateDirectory(OutputFolder);
                var path = Path.Combine(OutputFolder,
                    $"opening_range_candidates_{_sessionDate:yyyy-MM-dd}_codex.csv");
                var sb = new StringBuilder();
                sb.AppendLine(Candidate_codex.Header);
                foreach (var candidate in _candidates)
                    sb.AppendLine(candidate.ToCsv_codex());
                File.WriteAllText(path, sb.ToString());
            }
            catch
            {
                // Research logging must never interrupt the chart.
            }
        }

        private void PersistStatus_codex(DateTime marketTimeNy)
        {
            if (_sessionDate == DateTime.MinValue)
                return;
            try
            {
                Directory.CreateDirectory(OutputFolder);
                var path = Path.Combine(OutputFolder,
                    $"codex_status_{_sessionDate:yyyy-MM-dd}.txt");
                File.WriteAllText(path,
                    $"last_market_ny={marketTimeNy:HH:mm:ss}\n" +
                    $"or_ready={(_orReady ? 1 : 0)}\n" +
                    $"candidates={_candidates.Count}\n" +
                    $"accepted={_candidates.Count(candidate => candidate.WouldTrade)}\n" +
                    $"resolved={_candidates.Count(candidate => candidate.IsResolved)}\n" +
                    $"complete={(_sessionComplete ? 1 : 0)}\n");
            }
            catch
            {
                // Status is diagnostic only.
            }
        }

        private void ResetAll_codex()
        {
            _lastClosedBar = -1;
            _sessionDate = DateTime.MinValue;
            _lastPrice = 0m;
            _lastMarketTimeNy = DateTime.MinValue;
            _candidates.Clear();
            _bars.Clear();
            _candidateKeys.Clear();
            _sessionComplete = false;
        }

        private void ResetSession_codex(DateTime date)
        {
            _sessionDate = date.Date;
            _orReady = false;
            _orHigh = 0m;
            _orLow = 0m;
            _seenOutsideUp = false;
            _seenOutsideDown = false;
            _cumulativeDelta = 0m;
            _cumTypicalVolume = 0m;
            _cumVolume = 0m;
            _strategySignals = 0;
            _lastStrategyBar = int.MinValue;
            _sessionComplete = false;
            _bars.Clear();
            _candidates.Clear();
            _candidateKeys.Clear();
        }

        private decimal Tick_codex() => InstrumentInfo?.TickSize > 0m
            ? InstrumentInfo.TickSize
            : FallbackTick;

        private DateTime ToNy_codex(DateTime time)
        {
            var utc = time.Kind == DateTimeKind.Utc
                ? time
                : DateTime.SpecifyKind(time, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }
    }

    internal sealed class BarSnapshot_codex
    {
        public int Bar { get; init; }
        public DateTime TimeNy { get; init; }
        public decimal Open { get; init; }
        public decimal High { get; init; }
        public decimal Low { get; init; }
        public decimal Close { get; init; }
        public decimal Volume { get; init; }
        public decimal Delta { get; init; }
    }

    internal sealed class Candidate_codex
    {
        public const string Header =
            "candidate_id,fecha,entry_time_ny,entry_bar,setup,side,entry,or_high,or_low," +
            "or_ticks,extension_ticks,body_ticks,range_ticks,body_efficiency,volume," +
            "previous_volume,volume_ratio,delta,previous_delta,delta_ratio,delta_change," +
            "cumulative_delta,momentum3_ticks,distance_vwap_ticks,score,would_trade," +
            "tp_ticks,sl_ticks,outcome,exit_time_ny,exit_price,pnl_ticks,mfe_ticks,mae_ticks";

        public string CandidateId { get; init; } = "";
        public DateTime SessionDate { get; init; }
        public DateTime EntryTimeNy { get; init; }
        public int EntryBar { get; init; }
        public string Setup { get; init; } = "";
        public string Side { get; init; } = "";
        public decimal Entry { get; init; }
        public decimal OrHigh { get; init; }
        public decimal OrLow { get; init; }
        public decimal OrTicks { get; init; }
        public decimal ExtensionTicks { get; init; }
        public decimal BodyTicks { get; init; }
        public decimal RangeTicks { get; init; }
        public decimal BodyEfficiency { get; init; }
        public decimal Volume { get; init; }
        public decimal PreviousVolume { get; init; }
        public decimal VolumeRatio { get; init; }
        public decimal Delta { get; init; }
        public decimal PreviousDelta { get; init; }
        public decimal DeltaRatio { get; init; }
        public decimal DeltaChange { get; init; }
        public decimal CumulativeDelta { get; init; }
        public decimal Momentum3Ticks { get; init; }
        public decimal DistanceVwapTicks { get; init; }
        public int Score { get; init; }
        public bool WouldTrade { get; init; }
        public decimal TargetTicks { get; init; }
        public decimal StopTicks { get; init; }
        public string Outcome { get; set; } = "OPEN";
        public DateTime ExitTimeNy { get; set; } = DateTime.MinValue;
        public decimal ExitPrice { get; set; }
        public decimal PnlTicks { get; set; }
        public decimal MfeTicks { get; set; }
        public decimal MaeTicks { get; set; }
        public bool IsResolved => Outcome != "OPEN";

        public string ToCsv_codex()
        {
            var c = CultureInfo.InvariantCulture;
            return string.Join(",", new[]
            {
                CandidateId,
                SessionDate.ToString("yyyy-MM-dd", c),
                EntryTimeNy.ToString("HH:mm:ss.fff", c),
                EntryBar.ToString(c),
                Setup,
                Side,
                F_codex(Entry), F_codex(OrHigh), F_codex(OrLow), F_codex(OrTicks),
                F_codex(ExtensionTicks), F_codex(BodyTicks), F_codex(RangeTicks),
                F_codex(BodyEfficiency), F_codex(Volume), F_codex(PreviousVolume),
                F_codex(VolumeRatio), F_codex(Delta), F_codex(PreviousDelta),
                F_codex(DeltaRatio), F_codex(DeltaChange), F_codex(CumulativeDelta),
                F_codex(Momentum3Ticks), F_codex(DistanceVwapTicks), Score.ToString(c),
                WouldTrade ? "1" : "0", F_codex(TargetTicks), F_codex(StopTicks),
                Outcome,
                ExitTimeNy == DateTime.MinValue ? "" : ExitTimeNy.ToString("HH:mm:ss.fff", c),
                ExitTimeNy == DateTime.MinValue ? "" : F_codex(ExitPrice),
                IsResolved ? F_codex(PnlTicks) : "",
                F_codex(MfeTicks), F_codex(MaeTicks)
            });
        }

        private static string F_codex(decimal value) =>
            value.ToString("0.####", CultureInfo.InvariantCulture);
    }
}
