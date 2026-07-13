using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using ATAS.DataFeedsCore;   // MarketByOrder, MarketByOrderUpdateTypes, MarketDataType

namespace ATAS.Indicators
{
    // ATRAPADOS — Book Recorder (research). Dumps the RAW microstructure streams that
    // Track B needs (contexto_OR_catboost/TRACK_B_MBO_pendiente.md) so pulling /
    // stacking / refill / iceberg / OFI can be reconstructed OFFLINE in Python.
    //
    // Writes up to three per-date CSVs into OutputFolder, gated by the same
    // target_trade_result_date.txt as the exporter/scanner (one date at a time):
    //   mbo_{date}_NY.csv  : per-order add/change/delete   (needs MBO in the feed)
    //   mbp_{date}_NY.csv  : per-level resting-size updates (DOM moving = always on)
    //   tape_{date}_NY.csv : executed trades                (to split exec vs cancel)
    // Plus bookrec_status_{date}.txt with row counts so you can SEE whether MBO fired.
    //
    // Touches NOTHING of the exporter or the X1/X10 replay-sync logic. It only
    // subscribes to data streams the platform already produces during replay.
    [DisplayName("ATRAPADOS Book Recorder")]
    public class BookRecorder : Indicator
    {
        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        // ── Parameters ──────────────────────────────────────────────────
        [Display(Name = "Carpeta de salida", Order = 1)]
        public string OutputFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings";

        [Display(Name = "Gate por target-date (harness)", Order = 2,
            Description = "Solo graba la fecha en target_trade_result_date.txt (mismo gate que el exporter).")]
        public bool GateByTargetDate { get; set; } = true;

        [Display(Name = "Grabar MBO (por-orden)", Order = 3)]
        public bool RecordMbo { get; set; } = true;

        [Display(Name = "Grabar MBP (profundidad)", Order = 4)]
        public bool RecordMbp { get; set; } = true;

        [Display(Name = "Grabar Tape (trades)", Order = 5)]
        public bool RecordTape { get; set; } = true;

        [Display(Name = "Ventana inicio NY (HH:mm)", Order = 6)]
        public string StartNy { get; set; } = "09:25";

        [Display(Name = "Ventana fin NY (HH:mm)", Order = 7)]
        public string EndNy { get; set; } = "15:35";

        private readonly string _targetDateFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\target_trade_result_date.txt";

        // ── Runtime state ───────────────────────────────────────────────
        private bool _subscribed;
        private DateTime? _target;              // gated target date (NY), cached
        private TimeSpan _winStart, _winEnd;

        private StreamWriter? _mbo, _mbp, _tape;
        private DateTime _openDate = DateTime.MinValue;
        private long _mboRows, _mbpRows, _tapeRows;
        private int _flushCtr;

        public BookRecorder()
        {
            Name = "ATRAPADOS Book Recorder";
            EnableCustomDrawing = false;
        }

        protected override void OnRecalculate()
        {
            base.OnRecalculate();
            CloseWriters();
            _openDate = DateTime.MinValue;
            _mboRows = _mbpRows = _tapeRows = 0;
            _flushCtr = 0;
            _winStart = ParseNy(StartNy, new TimeSpan(9, 25, 0));
            _winEnd = ParseNy(EndNy, new TimeSpan(15, 35, 0));
            _target = GateByTargetDate ? ReadTargetDate() : null;

            if (!_subscribed && RecordMbo)
            {
                try { SubscribeMarketByOrderData(); } catch { }
                _subscribed = true;   // fire-once; feed may or may not carry MBO
            }
        }

        // Indicator requires OnCalculate; the recorder is event-driven, so this is a no-op.
        protected override void OnCalculate(int bar, decimal value) { }

        // ── Per-order stream (true MBO): New / Change / Delete / Snapshot ──
        protected override void OnMarketByOrdersChanged(IEnumerable<MarketByOrder> values)
        {
            base.OnMarketByOrdersChanged(values);
            if (!RecordMbo || values == null) return;
            foreach (var o in values)
            {
                var ny = ToNy(o.Time);
                if (!InWindow(ny)) continue;
                var w = Writer(ref _mbo, "mbo", ny.Date,
                    "time_ny,type,side,price,volume,order_id,priority");
                if (w == null) continue;
                w.Write(ny.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture));
                w.Write(',');  w.Write(o.Type);
                w.Write(',');  w.Write(o.Side);
                w.Write(',');  w.Write(Num(o.Price));
                w.Write(',');  w.Write(Num(o.Volume));
                w.Write(',');  w.Write(o.ExchangeOrderId);
                w.Write(',');  w.Write(o.Priority);
                w.Write('\n');
                _mboRows++;
                MaybeFlush();
            }
        }

        // ── Per-level resting-size stream (MBP / DOM updates) ──
        protected override void MarketDepthChanged(MarketDataArg depth)
        {
            base.MarketDepthChanged(depth);
            if (!RecordMbp || depth == null) return;
            var ny = ToNy(depth.Time);
            if (!InWindow(ny)) return;
            var w = Writer(ref _mbp, "mbp", ny.Date, "time_ny,side,price,volume");
            if (w == null) return;
            w.Write(ny.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture));
            w.Write(',');  w.Write(depth.DataType);              // Bid | Ask
            w.Write(',');  w.Write(Num(depth.Price));
            w.Write(',');  w.Write(Num(depth.Volume));           // new resting size
            w.Write('\n');
            _mbpRows++;
            MaybeFlush();
        }

        // ── Tape (executions) to separate consumed vs cancelled liquidity ──
        protected override void OnNewTrade(MarketDataArg trade)
        {
            base.OnNewTrade(trade);
            if (!RecordTape || trade == null) return;
            var ny = ToNy(trade.Time);
            if (!InWindow(ny)) return;
            var w = Writer(ref _tape, "tape", ny.Date, "time_ny,price,volume,direction");
            if (w == null) return;
            w.Write(ny.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture));
            w.Write(',');  w.Write(Num(trade.Price));
            w.Write(',');  w.Write(Num(trade.Volume));
            w.Write(',');  w.Write(trade.Direction);             // Buy | Sell | Between
            w.Write('\n');
            _tapeRows++;
            MaybeFlush();
        }

        // ── Writer management (one open file set per date; gated) ──────────
        private StreamWriter? Writer(ref StreamWriter? slot, string kind, DateTime nyDate, string header)
        {
            if (GateByTargetDate && _target.HasValue && nyDate.Date != _target.Value.Date)
                return null;

            if (nyDate.Date != _openDate)
            {
                FinalizeStatus();     // dump counts of the date we are leaving
                CloseWriters();
                _openDate = nyDate.Date;
                _mboRows = _mbpRows = _tapeRows = 0;
            }
            if (slot == null)
            {
                try
                {
                    if (!Directory.Exists(OutputFolder))
                        Directory.CreateDirectory(OutputFolder);
                    var path = Path.Combine(OutputFolder,
                        $"{kind}_{nyDate:yyyy-MM-dd}_NY.csv");
                    slot = new StreamWriter(path, false) { AutoFlush = false };
                    slot.Write(header);
                    slot.Write('\n');
                }
                catch { slot = null; }
            }
            return slot;
        }

        private void MaybeFlush()
        {
            if (++_flushCtr < 8000) return;
            _flushCtr = 0;
            try { _mbo?.Flush(); _mbp?.Flush(); _tape?.Flush(); } catch { }
        }

        private void FinalizeStatus()
        {
            if (_openDate == DateTime.MinValue) return;
            try
            {
                var path = Path.Combine(OutputFolder,
                    $"bookrec_status_{_openDate:yyyy-MM-dd}.txt");
                File.WriteAllText(path,
                    $"mbo_rows={_mboRows}\nmbp_rows={_mbpRows}\ntape_rows={_tapeRows}\n" +
                    $"mbo_present={( _mboRows > 0 ? 1 : 0)}\n");
            }
            catch { }
        }

        private void CloseWriters()
        {
            FinalizeStatus();
            try { _mbo?.Flush(); _mbo?.Dispose(); } catch { }
            try { _mbp?.Flush(); _mbp?.Dispose(); } catch { }
            try { _tape?.Flush(); _tape?.Dispose(); } catch { }
            _mbo = _mbp = _tape = null;
        }

        // ── Helpers ────────────────────────────────────────────────────
        private bool InWindow(DateTime ny)
        {
            var tod = ny.TimeOfDay;
            return tod >= _winStart && tod < _winEnd;
        }

        private DateTime ToNy(DateTime t)
        {
            var utc = t.Kind == DateTimeKind.Utc ? t : DateTime.SpecifyKind(t, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, _nyZone);
        }

        private DateTime? ReadTargetDate()
        {
            try
            {
                if (!File.Exists(_targetDateFile)) return null;
                var txt = File.ReadAllText(_targetDateFile).Trim();
                return DateTime.TryParseExact(txt, "yyyy-MM-dd",
                    CultureInfo.InvariantCulture, DateTimeStyles.None, out var d)
                    ? d.Date : (DateTime?)null;
            }
            catch { return null; }
        }

        private static string Num(decimal v) =>
            v.ToString("0.#####", CultureInfo.InvariantCulture);

        private static TimeSpan ParseNy(string value, TimeSpan fallback)
            => TimeSpan.TryParse(value, out var ts) ? ts : fallback;
    }
}
