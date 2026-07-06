using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Text;
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
        private int _barsSeen;
        private bool _wroteRow;
        private string _lastBarNy = "";
        private readonly List<SlideSnap> _slideSnaps = new();
        private readonly HashSet<int> _slidBars = new();
        // TEMP data-availability probe (pre-open / overnight bars + footprint levels).
        private int _preBars, _preLvl, _onBars, _onLvl, _pdBars, _pdLvl;

        // ── Parameters ──────────────────────────────────────────────────
        // 1 = alineado con el exporter (OR = candle de apertura 09:30, 1 min). Con 5
        // el OR no bloqueaba hasta 09:35 y los TP rapidos (09:31-09:33) se perdian.
        [Display(Name = "OR minutos", Order = 1)]
        public int OrMinutes { get; set; } = 1;

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

        [Display(Name = "Finalizar/escribir a (HH:mm NY)", Order = 8,
            Description = "El replay corta ~09:50, antes de RTH end (16:00). Sin esto la fila nunca se escribe. Debe caer dentro de la ventana del replay.")]
        public string FinalizeNy { get; set; } = "09:48";

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
            _barsSeen = 0;
            _wroteRow = false;
            _lastBarNy = "";
            _slideSnaps.Clear();
            _slidBars.Clear();
            _preBars = _preLvl = _onBars = _onLvl = _pdBars = _pdLvl = 0;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1) return;
            var closed = bar - 1;
            if (closed > _lastProcessed)
            {
                for (var b = _lastProcessed + 1; b <= closed; b++)
                    ProcessBar(b);
                _lastProcessed = closed;
            }
            // Detect the breakout on the CURRENT forming bar too, so instant-TP days
            // (breakout + TP within the first bar after OR, e.g. 09:31:08) get captured
            // before the replay stops and that bar never closes.
            LiveBreakoutCheck(bar);
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
                _barsSeen = 0;
                _wroteRow = false;
                _lastBarNy = "";
                _slideSnaps.Clear();
                _slidBars.Clear();
                // #1: drop any sidecar left by a PRIOR run for this date, so a no-trade
                // day cannot keep a stale traded row (and slide starts clean).
                CleanDateSidecars(date);
            }

            var tod = ny.TimeOfDay;

            // TEMP probe: does the featsweep replay actually load pre-open / overnight /
            // prev-RTH bars, and do they carry footprint price levels? Counts land in the
            // status file. Remove once the profile-architecture data source is confirmed.
            {
                int lvls = 0;
                try { foreach (var _l in candle.GetAllPriceLevels()) lvls++; } catch { }
                if (tod >= new TimeSpan(8, 30, 0) && tod < _rthStart) { _preBars++; if (lvls > 0) _preLvl++; }
                else if (tod >= new TimeSpan(18, 0, 0) || tod < new TimeSpan(8, 30, 0)) { _onBars++; if (lvls > 0) _onLvl++; }
                else if (tod >= _rthStart && tod < _rthEnd) { _pdBars++; if (lvls > 0) _pdLvl++; }
            }

            if (tod < _rthStart || tod >= _rthEnd)
            {
                if (tod >= _rthEnd) FinalizePending();
                return;
            }

            var bd = BuildBar(b, candle, ny);
            _sessionBars.Add(bd);
            _barsSeen++;
            _lastBarNy = ny.ToString("HH:mm:ss", CultureInfo.InvariantCulture);

            var orEnd = _rthStart + TimeSpan.FromMinutes(OrMinutes);
            var inOr = tod < orEnd;
            if (inOr) _ctx.UpdateOpeningRange(bd);
            _ctx.UpdateWithBar(bd, tod < _ibEnd);
            if (!inOr && !_ctx.OrLocked && _ctx.OrBars > 0) _ctx.OrLocked = true;

            // forward-track an active event (bars after the breakout bar)
            if (_pending != null && b > _pending.EventBar)
                UpdateTrackers(bd);

            // TRADED capture: align to the exporter's REAL entry (side + price) via the
            // in-memory ExecutionSignalBus, instead of the scanner's own first OR cross.
            // The naive cross could be the OPPOSITE side of the traded setup (e.g. 06-26:
            // scanner up @09:31 vs exporter SELL @09:33) -> X and y described different
            // events. Bus-driven guarantees the feature row matches the traded outcome.
            TryBusEntry(bd, b, _sessionBars, _sessionBars.Count - 1);

            // SLIDE capture: causal snapshot on every post-OR bar (ALL days, traded or
            // not), forward-tracked in both directions. This is the "state before the
            // move" dataset -> separate sidecar so it never mixes with the traded label.
            SlideStep(bd);

            // The replay stops as soon as the exporter writes a terminal result
            // (TP ~09:33, TIME_OVER ~09:40) — before 09:48 and long before RTH end.
            // So write the pending event row INCREMENTALLY every bar (gated overwrite):
            // whatever bar the replay stops on, the sidecar CSV already reflects it.
            if (_pending != null && GateByTargetDate)
                EmitPendingRow();

            // Fallback for full-day / non-gated use: one-shot finalize near window end.
            if (_pending != null && tod >= ParseNy(FinalizeNy, new TimeSpan(9, 48, 0)))
                FinalizePending();

            WriteStatus();
        }

        // Build the label suffix from the CURRENT forward-tracking state and write
        // the per-date sidecar (gated overwrite). Does NOT null _pending nor mutate
        // the base row, so it can run every bar; the last write before the replay
        // stops is the one that survives.
        private void EmitPendingRow()
        {
            var e = _pending;
            if (e == null) return;

            var label60 = e.Mfe >= (double)MoveTargetTicks;
            var whale = label60 && e.Whale;
            var barsTo60 = e.Reached60
                ? e.BarsTo60.ToString(CultureInfo.InvariantCulture)
                : "";

            var header = e.Row.Header() +
                ",mfe_ticks,mae_ticks,bars_to_60,first_60_before_20adv," +
                "label_move60,label_whale,whale_orderflow";
            var line = e.Row.Line() + "," +
                e.Mfe.ToString("0.###############", CultureInfo.InvariantCulture) + "," +
                e.Mae.ToString("0.###############", CultureInfo.InvariantCulture) + "," +
                barsTo60 + "," +
                (e.First60BeforeAdverse ? "1" : "0") + "," +
                (label60 ? "1" : "0") + "," +
                (whale ? "1" : "0") + "," +
                (e.Whale ? "1" : "0");

            WriteRawRow(_curDate, header, line);
        }

        // Gated per-date overwrite from raw header/line strings (used by EmitPendingRow).
        private void WriteRawRow(DateTime nyDate, string header, string line)
        {
            try
            {
                if (GateByTargetDate)
                {
                    var target = ReadTargetDate();
                    if (target != null && target.Value.Date != nyDate.Date)
                        return;
                }
                if (!Directory.Exists(OutputFolder))
                    Directory.CreateDirectory(OutputFolder);
                var path = Path.Combine(OutputFolder,
                    $"features_scan_{nyDate:yyyy-MM-dd}_NY.csv");
                File.WriteAllText(path,
                    header + Environment.NewLine + line + Environment.NewLine);
                _wroteRow = true;
            }
            catch
            {
                // research sidecar must never interrupt anything on the chart.
            }
        }

        // Heartbeat de diagnostico: prueba que el indicador ESTA cargado y corriendo
        // en el chart. Si este archivo no aparece tras el replay, el Feature Scanner
        // NO esta en el chart (o ATAS no recargo el DLL). Ungated a proposito.
        private void WriteStatus()
        {
            try
            {
                if (!Directory.Exists(OutputFolder))
                    Directory.CreateDirectory(OutputFolder);
                var path = Path.Combine(OutputFolder,
                    $"featscan_status_{_curDate:yyyy-MM-dd}.txt");
                File.WriteAllText(path,
                    $"bars_seen={_barsSeen}\n" +
                    $"last_bar_ny={_lastBarNy}\n" +
                    $"or_locked={(_ctx.OrLocked ? 1 : 0)}\n" +
                    $"or_high={_ctx.OrHigh}\n" +
                    $"or_low={_ctx.OrLow}\n" +
                    $"event_detected={(_eventDone ? 1 : 0)}\n" +
                    $"pending_active={(_pending != null ? 1 : 0)}\n" +
                    $"wrote_features_row={(_wroteRow ? 1 : 0)}\n" +
                    $"finalize_ny={FinalizeNy}\n" +
                    $"gate_by_target={(GateByTargetDate ? 1 : 0)}\n" +
                    $"probe_preopen_bars={_preBars} with_levels={_preLvl}\n" +
                    $"probe_overnight_bars={_onBars} with_levels={_onLvl}\n" +
                    $"probe_rth_bars={_pdBars} with_levels={_pdLvl}\n");
            }
            catch { }
        }

        // Detect the exporter's entry on the forming bar (intrabar). Needed for instant-TP
        // days where the entry bar never closes before the replay stops. Reads the same
        // ExecutionSignalBus, so an intrabar exporter entry is captured within a tick.
        private void LiveBreakoutCheck(int bar)
        {
            if (_eventDone) return;

            dynamic candle = GetCandle(bar);
            DateTime utc = candle.Time;
            var ny = ToNy(utc);
            if (ny.Date != _curDate) return;

            var tod = ny.TimeOfDay;
            if (tod < _rthStart || tod >= _rthEnd) return;

            var orEnd = _rthStart + TimeSpan.FromMinutes(OrMinutes);
            if (tod < orEnd) return;                    // still inside OR window
            if (!_ctx.OrLocked && _ctx.OrBars > 0)      // time-lock OR mid-bar
                _ctx.OrLocked = true;
            if (!_ctx.OrLocked) return;

            var bd = BuildBar(bar, candle, ny);
            // Feature context = closed session bars + this forming bar as the last one.
            var live = new List<BarData>(_sessionBars) { bd };
            TryBusEntry(bd, bar, live, live.Count - 1);
        }

        // Capture the TRADED row when (and only when) the exporter has published an entry
        // for this session on the ExecutionSignalBus. Side/EntryPrice come from the
        // exporter, so X (features) and y (its outcome) describe the SAME trade. Peek
        // only (never MarkConsumed) so the live Execution Manager still consumes it.
        private void TryBusEntry(BarData bd, int b, IReadOnlyList<BarData> session, int i)
        {
            if (_eventDone) return;
            var pe = ExecutionSignalBus.Peek(_curDate);
            if (pe == null) return;
            string? dir = pe.Side == "BUY" ? "up" : pe.Side == "SELL" ? "down" : null;
            if (dir == null) return;

            StartEvent(dir, bd, b, session, i, (double)pe.EntryPrice);
            _eventDone = true;
            if (GateByTargetDate) EmitPendingRow();

            // #2: instant-entry fallback. On instant-TP days the entry bar never closes
            // before the replay stops, so no closed slide snapshot exists. If the slide
            // set is still empty, capture ONE from the (forming) entry bar so those days
            // are not absent from the slide dataset. Guarded to _slideSnaps.Count==0 so
            // normal days (which already have closed snapshots) are untouched.
            if (_slideSnaps.Count == 0)
                AddSlideSnapshot(bd, session, i, b);

            WriteStatus();
        }

        // entryPrice = the REAL entry (exporter's for traded rows, bar Close for slide),
        // so forward MFE/MAE and entry_price are measured from the same anchor as y.
        private void StartEvent(string dir, BarData bd, int b, IReadOnlyList<BarData> session,
            int i, double entryPrice)
        {
            var row = BuildFeatureRow(dir, "traded", session, i, entryPrice);
            _pending = new PendingEvent
            {
                Dir = dir,
                Entry = entryPrice,
                EventBar = b,
                Row = row,
                Whale = WhaleAtEvent(dir, bd)
            };
        }

        private FeatureRow BuildFeatureRow(string dir, string captureType,
            IReadOnlyList<BarData> session, int i, double entryPrice)
        {
            var ctx = new FeatureCtx
            {
                Session = session,
                I = i,
                Ctx = _ctx,
                Tick = Tick,
                BreakDir = dir
            };
            var row = new FeatureRow();
            row.AddText("fecha", _curDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
            row.AddText("break_dir", dir);
            row.AddText("capture_type", captureType);
            row.Add("entry_price", entryPrice);
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
                    _wroteRow = true;
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
                    _wroteRow = true;
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

        // SLIDE dataset: at every post-OR bar snapshot causal features (X_t, using only
        // bars up to t), then let each subsequent bar extend the forward excursion of all
        // buffered snapshots (y_t = did price run >=40/60t up or down after t). One pass,
        // no look-ahead, all days. Rewritten incrementally so a replay stop is safe.
        private void SlideStep(BarData bd)
        {
            if (!InSlideWindow(bd.TimeNy.TimeOfDay) || !_ctx.OrLocked) return;
            ExtendSlide(bd);                                        // 1) forward-track existing
            AddSlideSnapshot(bd, _sessionBars, _sessionBars.Count - 1, bd.Bar);  // 2) new snapshot
        }

        private bool InSlideWindow(TimeSpan tod)
        {
            var orEnd = _rthStart + TimeSpan.FromMinutes(OrMinutes);
            return tod >= orEnd && tod < _rthEnd;
        }

        // Extend the forward excursion of every buffered snapshot with a LATER bar. Snaps
        // are only extended by bars strictly after their own (Bar < bd.Bar), so a snapshot
        // never counts its own bar as forward movement (safe even if it was added intrabar).
        private void ExtendSlide(BarData bd)
        {
            foreach (var s in _slideSnaps)
            {
                if (s.Bar >= bd.Bar) continue;
                var up = (bd.High - s.Anchor) / Tick;
                var dn = (s.Anchor - bd.Low) / Tick;
                if (up > s.MfeUp) s.MfeUp = up;
                if (dn > s.MfeDn) s.MfeDn = dn;
                s.Bars++;
                if (!s.Hit40Up && s.MfeUp >= 40) { s.Hit40Up = true; if (s.FirstHit40 == 0) s.FirstHit40 = 1; }
                if (!s.Hit40Dn && s.MfeDn >= 40) { s.Hit40Dn = true; if (s.FirstHit40 == 0) s.FirstHit40 = -1; }
                if (!s.Hit60Up && s.MfeUp >= 60) s.Hit60Up = true;
                if (!s.Hit60Dn && s.MfeDn >= 60) s.Hit60Dn = true;
            }
        }

        // Causal snapshot anchored at this bar's Close, deduped by bar index (a bar added
        // intrabar as an instant-entry fallback is not re-added when it later closes). dir
        // = OR side price sits on now (causal); forward labels are computed both ways.
        private void AddSlideSnapshot(BarData bd, IReadOnlyList<BarData> session, int i, int barIdx)
        {
            if (!_slidBars.Add(barIdx)) return;
            var mid = (_ctx.OrHigh + _ctx.OrLow) / 2.0;
            var dir = bd.Close >= _ctx.OrHigh ? "up"
                : bd.Close <= _ctx.OrLow ? "down"
                : (bd.Close >= mid ? "up" : "down");
            var row = BuildFeatureRow(dir, "slide", session, i, bd.Close);
            _slideSnaps.Add(new SlideSnap { Row = row, Anchor = bd.Close, Bar = barIdx });
            WriteSlideRows();
        }

        private void WriteSlideRows()
        {
            try
            {
                if (_slideSnaps.Count == 0) return;
                if (GateByTargetDate)
                {
                    var target = ReadTargetDate();
                    if (target != null && target.Value.Date != _curDate.Date) return;
                }
                if (!Directory.Exists(OutputFolder))
                    Directory.CreateDirectory(OutputFolder);

                var sb = new StringBuilder();
                sb.Append(_slideSnaps[0].Row.Header())
                  .Append(",fwd_mfe_up,fwd_mfe_dn,fwd_bars,hit40_up,hit40_dn,hit60_up,hit60_dn,first_hit40")
                  .Append('\n');
                foreach (var s in _slideSnaps)
                {
                    sb.Append(s.Row.Line()).Append(',')
                      .Append(Fmt(s.MfeUp)).Append(',')
                      .Append(Fmt(s.MfeDn)).Append(',')
                      .Append(s.Bars.ToString(CultureInfo.InvariantCulture)).Append(',')
                      .Append(s.Hit40Up ? '1' : '0').Append(',')
                      .Append(s.Hit40Dn ? '1' : '0').Append(',')
                      .Append(s.Hit60Up ? '1' : '0').Append(',')
                      .Append(s.Hit60Dn ? '1' : '0').Append(',')
                      .Append(s.FirstHit40.ToString(CultureInfo.InvariantCulture)).Append('\n');
                }
                var path = Path.Combine(OutputFolder,
                    $"features_slide_{_curDate:yyyy-MM-dd}_NY.csv");
                File.WriteAllText(path, sb.ToString());
            }
            catch
            {
                // research sidecar must never interrupt anything on the chart.
            }
        }

        // Delete this date's per-date sidecars before (re)processing it, so a no-trade day
        // cannot inherit a stale traded row from an earlier run. Only touches the gated
        // target date; the accumulate-all mode (non-gated) uses a single file and is skipped.
        private void CleanDateSidecars(DateTime nyDate)
        {
            try
            {
                if (!GateByTargetDate) return;
                var target = ReadTargetDate();
                if (target != null && target.Value.Date != nyDate.Date) return;
                foreach (var pre in new[] { "features_scan_", "features_slide_" })
                {
                    var p = Path.Combine(OutputFolder, $"{pre}{nyDate:yyyy-MM-dd}_NY.csv");
                    if (File.Exists(p)) File.Delete(p);
                }
            }
            catch
            {
                // research sidecar must never interrupt anything on the chart.
            }
        }

        private static string Fmt(double v) =>
            double.IsNaN(v) || double.IsInfinity(v)
                ? ""
                : v.ToString("0.###############", CultureInfo.InvariantCulture);

        private sealed class SlideSnap
        {
            public FeatureRow Row = null!;
            public int Bar;              // bar index this snapshot was taken on (dedup key)
            public double Anchor;        // Close at snapshot (forward-excursion origin)
            public double MfeUp;
            public double MfeDn;
            public int Bars;
            public bool Hit40Up;
            public bool Hit40Dn;
            public bool Hit60Up;
            public bool Hit60Dn;
            public int FirstHit40;       // 0 none, 1 up first, -1 down first
        }

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
