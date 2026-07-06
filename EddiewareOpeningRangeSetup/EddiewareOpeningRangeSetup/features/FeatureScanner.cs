using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using ATAS.Indicators.Atrapados;

namespace ATAS.Indicators
{
    // Feature Scanner (research). Runs on 1-min bars as a SIBLING
    // indicator alongside the frozen exporter. Detects the first Opening-Range
    // breakout per session, looks forward (look-ahead intencional) to label whether
    // the move reached >=60t, snapshots all buildable feature groups, and writes a
    // per-date sidecar CSV joinable to score_trade_result_{fecha}.csv by `fecha`.
    //
    // Touches NOTHING of the exporter or the X1/X10 replay-sync logic. Connection is:
    // same chart/replay + same target_trade_result_date.txt gate + `fecha` join key.
    [DisplayName("Feature Scanner")]
    public class FeatureScanner : Indicator
    {
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private readonly TimeSpan _rthStart = new(9, 30, 0);
        private readonly TimeSpan _rthEnd = new(16, 0, 0);
        private readonly TimeSpan _ibEnd = new(10, 30, 0);

        private SessionContext _ctx = new();
        private readonly List<BarData> _sessionBars = new();
        private DateTime _curDate = DateTime.MinValue;
        private int _lastProcessed = -1;
        private bool _eventDone;
        private PendingEvent? _pending;
        private bool _headerWritten;

        // ── Parameters ──────────────────────────────────────────────────
        [Display(Name = "OR minutos", Order = 1)]
        public int OrMinutes { get; set; } = 5;

        [Display(Name = "Move objetivo (ticks)", Order = 2)]
        public decimal MoveTargetTicks { get; set; } = 60m;

        [Display(Name = "Whale: imbalance min (delta/vol)", Order = 3)]
        public decimal ImbalanceThresh { get; set; } = 0.30m;

        [Display(Name = "Whale: |zscore| delta min", Order = 4)]
        public decimal ZThresh { get; set; } = 1.0m;

        [Display(Name = "Ultimo break (HH:mm NY)", Order = 5)]
        public string LastBreakoutNy { get; set; } = "15:00";

        [Display(Name = "Carpeta de salida", Order = 6)]
        public string OutputFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";

        [Display(Name = "Gate por target-date (harness)", Order = 7,
            Description = "Escribe solo la fecha de target_trade_result_date.txt (mismo gate que el exporter). Off = acumula todas las fechas en un archivo.")]
        public bool GateByTargetDate { get; set; } = true;

        private readonly string _targetDateFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\target_trade_result_date.txt";

        private double Tick => (double)(InstrumentInfo?.TickSize ?? 0.25m);

        public FeatureScanner()
        {
            Name = "Feature Scanner";
            EnableCustomDrawing = false;
        }

        protected override void OnRecalculate()
        {
            base.OnRecalculate();
            _ctx = new SessionContext();
            _sessionBars.Clear();
            _curDate = DateTime.MinValue;
            _lastProcessed = -1;
            _eventDone = false;
            _pending = null;
            _headerWritten = false;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1) return;
            var closed = bar - 1;
            if (closed <= _lastProcessed) return;
            for (var b = _lastProcessed + 1; b <= closed; b++)
                ProcessBar(b);
            _lastProcessed = closed;
        }

        private void ProcessBar(int b)
        {
            dynamic candle = GetCandle(b);
            DateTime utc = candle.Time;
            var ny = ToNy(utc);
            var date = ny.Date;

            if (date != _curDate)
            {
                FinalizePending();
                _ctx.FinalizePrevSession(_sessionBars, Tick);
                _sessionBars.Clear();
                _ctx.ResetForNewSession(date, Tick);
                _curDate = date;
                _eventDone = false;
                _pending = null;
            }

            var tod = ny.TimeOfDay;
            if (tod < _rthStart || tod >= _rthEnd)
            {
                if (tod >= _rthEnd) FinalizePending();
                return;
            }

            var bd = BuildBar(b, candle, ny);
            _sessionBars.Add(bd);

            var orEnd = _rthStart + TimeSpan.FromMinutes(OrMinutes);
            var inOr = tod < orEnd;
            if (inOr) _ctx.UpdateOpeningRange(bd);
            _ctx.UpdateWithBar(bd, tod < _ibEnd);
            if (!inOr && !_ctx.OrLocked && _ctx.OrBars > 0) _ctx.OrLocked = true;

            // forward-track an active event (bars after the breakout bar)
            if (_pending != null && b > _pending.EventBar)
                UpdateTrackers(bd);

            // detect first breakout after OR locks
            if (_ctx.OrLocked && !_eventDone && tod <= ParseNy(LastBreakoutNy, new TimeSpan(15, 0, 0)))
            {
                string? dir = null;
                if (bd.Close > _ctx.OrHigh) dir = "up";
                else if (bd.Close < _ctx.OrLow) dir = "down";
                if (dir != null)
                {
                    StartEvent(dir, bd, b);
                    _eventDone = true;
                }
            }
        }

        private void StartEvent(string dir, BarData bd, int b)
        {
            var row = BuildFeatureRow(dir);
            _pending = new PendingEvent
            {
                Dir = dir,
                Entry = bd.Close,
                EventBar = b,
                Row = row,
                Whale = WhaleAtEvent(dir, bd)
            };
        }

        private FeatureRow BuildFeatureRow(string dir)
        {
            var ctx = new FeatureCtx
            {
                Session = _sessionBars,
                I = _sessionBars.Count - 1,
                Ctx = _ctx,
                Tick = Tick,
                BreakDir = dir
            };
            var row = new FeatureRow();
            row.AddText("fecha", _curDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
            row.AddText("break_dir", dir);
            row.Add("entry_price", ctx.Bar.Close);
            row.Add("or_high", _ctx.OrHigh);
            row.Add("or_low", _ctx.OrLow);
            row.Add("break_bar_sec", ctx.Bar.SecondsFromOpen);

            TimeFeatures.Collect(row, ctx);
            OpeningRangeFeatures.Collect(row, ctx);
            PriceFeatures.Collect(row, ctx);
            DistanceFeatures.Collect(row, ctx);
            SpeedFeatures.Collect(row, ctx);
            VolumeFeatures.Collect(row, ctx);
            DeltaFeatures.Collect(row, ctx);
            ImbalanceFeatures.Collect(row, ctx);
            FootprintFeatures.Collect(row, ctx);
            AbsorptionFeatures.Collect(row, ctx);
            AccumulationFeatures.Collect(row, ctx);
            VolatilityFeatures.Collect(row, ctx);
            VwapFeatures.Collect(row, ctx);
            MarketProfileFeatures.Collect(row, ctx);
            DerivedFeatures.Collect(row, ctx);
            MicrostructureFeatures.Collect(row, ctx);   // Track A — executed microstructure

            _ctx.VelocitySeries.EmitStats(row, "velocity");
            _ctx.VelocitySeries.EmitLags(row, "velocity");
            _ctx.VolumeSeries.EmitStats(row, "volcore");
            _ctx.VolumeSeries.EmitLags(row, "volcore");
            _ctx.DeltaSeries.EmitStats(row, "deltacore");
            _ctx.DeltaSeries.EmitLags(row, "deltacore");
            return row;
        }

        private bool WhaleAtEvent(string dir, BarData b)
        {
            var dirSign = dir == "up" ? 1 : -1;
            if (Math.Sign(b.Delta) != dirSign) return false;
            if (b.Volume <= 0) return false;
            var imb = Math.Abs(b.Delta) / b.Volume;
            var z = _ctx.DeltaSeries.ZScore(30);
            var zOk = double.IsNaN(z) || Math.Abs(z) >= (double)ZThresh;
            return imb >= (double)ImbalanceThresh && zOk;
        }

        private void UpdateTrackers(BarData b)
        {
            var e = _pending!;
            double fav, adv;
            if (e.Dir == "up")
            {
                fav = (b.High - e.Entry) / Tick;
                adv = (e.Entry - b.Low) / Tick;
            }
            else
            {
                fav = (e.Entry - b.Low) / Tick;
                adv = (b.High - e.Entry) / Tick;
            }
            if (fav > e.Mfe) e.Mfe = fav;
            if (adv > e.Mae) e.Mae = adv;
            e.Bars++;
            if (!e.Reached60 && e.Mfe >= (double)MoveTargetTicks)
            {
                e.Reached60 = true;
                e.BarsTo60 = e.Bars;
                e.First60BeforeAdverse = e.Mae < 20;
            }
        }

        private void FinalizePending()
        {
            if (_pending == null) return;
            var e = _pending;
            var row = e.Row;
            var label60 = e.Mfe >= (double)MoveTargetTicks;
            var whale = label60 && e.Whale;

            row.Add("mfe_ticks", e.Mfe);
            row.Add("mae_ticks", e.Mae);
            row.Add("bars_to_60", e.Reached60 ? e.BarsTo60 : double.NaN);
            row.Add("first_60_before_20adv", e.First60BeforeAdverse ? 1 : 0);
            row.Add("label_move60", label60 ? 1 : 0);
            row.Add("label_whale", whale ? 1 : 0);
            row.Add("whale_orderflow", e.Whale ? 1 : 0);

            WriteRow(_curDate, row);
            _pending = null;
        }

        private void WriteRow(DateTime nyDate, FeatureRow row)
        {
            try
            {
                if (!Directory.Exists(OutputFolder))
                    Directory.CreateDirectory(OutputFolder);

                if (GateByTargetDate)
                {
                    var target = ReadTargetDate();
                    if (target != null && target.Value.Date != nyDate.Date)
                        return;
                    var path = Path.Combine(OutputFolder,
                        $"features_scan_{nyDate:yyyy-MM-dd}_NY.csv");
                    File.WriteAllText(path,
                        row.Header() + Environment.NewLine + row.Line() + Environment.NewLine);
                }
                else
                {
                    var path = Path.Combine(OutputFolder, "features_scan_all.csv");
                    if (!_headerWritten && !File.Exists(path))
                    {
                        File.WriteAllText(path, row.Header() + Environment.NewLine);
                        _headerWritten = true;
                    }
                    File.AppendAllText(path, row.Line() + Environment.NewLine);
                }
            }
            catch
            {
                // research sidecar must never interrupt anything on the chart.
            }
        }

        private DateTime? ReadTargetDate()
        {
            try
            {
                if (!File.Exists(_targetDateFile)) return null;
                var txt = File.ReadAllText(_targetDateFile).Trim();
                return DateTime.TryParseExact(txt, "yyyy-MM-dd",
                    CultureInfo.InvariantCulture, DateTimeStyles.None, out var d)
                    ? d.Date
                    : (DateTime?)null;
            }
            catch { return null; }
        }

        private BarData BuildBar(int b, dynamic candle, DateTime ny)
        {
            var bd = new BarData
            {
                Bar = b,
                TimeNy = ny,
                Open = Convert.ToDouble(candle.Open),
                High = Convert.ToDouble(candle.High),
                Low = Convert.ToDouble(candle.Low),
                Close = Convert.ToDouble(candle.Close),
                Volume = Convert.ToDouble(candle.Volume),
                Delta = Convert.ToDouble(candle.Delta),
                SecondsFromOpen =
                    (ny - new DateTime(ny.Year, ny.Month, ny.Day, 9, 30, 0)).TotalSeconds
            };

            var levels = new List<Lvl>();
            double buy = 0, sell = 0;
            try
            {
                foreach (var l in candle.GetAllPriceLevels())
                {
                    var lv = new Lvl
                    {
                        Price = Convert.ToDouble(l.Price),
                        Buy = Convert.ToDouble(l.Ask),
                        Sell = Convert.ToDouble(l.Bid)
                    };
                    levels.Add(lv);
                    buy += lv.Buy;
                    sell += lv.Sell;
                }
            }
            catch { }

            if (levels.Count == 0)
            {
                buy = (bd.Volume + bd.Delta) / 2.0;
                sell = (bd.Volume - bd.Delta) / 2.0;
            }
            bd.Levels = levels;
            bd.BuyVolume = buy;
            bd.SellVolume = sell;
            return bd;
        }

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        private static TimeSpan ParseNy(string value, TimeSpan fallback)
            => TimeSpan.TryParse(value, out var ts) ? ts : fallback;

        private sealed class PendingEvent
        {
            public string Dir = "";
            public double Entry;
            public int EventBar;
            public FeatureRow Row = null!;
            public bool Whale;
            public double Mfe;
            public double Mae;
            public int Bars;
            public bool Reached60;
            public int BarsTo60;
            public bool First60BeforeAdverse;
        }
    }
}
