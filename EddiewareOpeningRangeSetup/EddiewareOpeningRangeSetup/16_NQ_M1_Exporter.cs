using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;

namespace ATAS.Indicators
{
    // Dumps closed M1 candles to CSV so the NQ side of the ATAS/MT5 lead-lag study can
    // be analysed offline. Read-only: it never places orders and never mutates chart
    // state. Attach once to an NQ M1 chart with the full DST 2025-2026 range loaded.
    //
    // Only bars strictly older than the forming bar are written, so the file is causal
    // by construction. Each bar index is written exactly once per session.
    [DisplayName("NQ M1 Exporter")]
    public class NqM1Exporter : Indicator
    {
        private const string Version = "nq-m1-exporter-2026-08-12-v1";

        private readonly List<string> _pending = new();

        private int _lastWrittenBar = -1;
        private string _path = string.Empty;
        private bool _headerChecked;
        private int _rowsWritten;

        public NqM1Exporter()
            : base(true)
        {
            DenyToChangePanel = true;
            DataSeries[0].IsHidden = true;
            EnableCustomDrawing = false;
        }

        [Display(Name = "Carpeta de salida", Order = 10, GroupName = "Exportación")]
        public string OutputFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\atas_mt5_sync";

        [Display(Name = "Nombre de archivo", Order = 20, GroupName = "Exportación")]
        public string FileName { get; set; } = "nq_m1_export.csv";

        [Display(Name = "Volcar cada N barras", Order = 30, GroupName = "Exportación")]
        public int FlushEveryBars { get; set; } = 500;

        protected override void OnRecalculate()
        {
            // A recalculation replays the whole series; start the file from scratch so
            // the export can never contain two different runs interleaved.
            _pending.Clear();
            _lastWrittenBar = -1;
            _headerChecked = false;
            _rowsWritten = 0;
            _path = string.Empty;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            // The last bar is still forming; never export it.
            if (bar >= CurrentBar - 1)
                return;

            if (bar <= _lastWrittenBar)
                return;

            _lastWrittenBar = bar;

            var candle = GetCandle(bar);
            if (candle == null)
                return;

            _pending.Add(string.Join(";",
                candle.Time.ToString("O", CultureInfo.InvariantCulture),
                candle.Time.Kind.ToString(),
                candle.LastTime.ToString("O", CultureInfo.InvariantCulture),
                candle.Open.ToString(CultureInfo.InvariantCulture),
                candle.High.ToString(CultureInfo.InvariantCulture),
                candle.Low.ToString(CultureInfo.InvariantCulture),
                candle.Close.ToString(CultureInfo.InvariantCulture),
                candle.Volume.ToString(CultureInfo.InvariantCulture),
                candle.Ticks.ToString(CultureInfo.InvariantCulture)));

            if (_pending.Count >= Math.Max(1, FlushEveryBars))
                Flush();
        }

        protected override void OnFinishRecalculate()
        {
            Flush();
        }

        private void Flush()
        {
            if (_pending.Count == 0)
                return;

            try
            {
                Directory.CreateDirectory(OutputFolder);

                if (string.IsNullOrEmpty(_path))
                {
                    var name = string.IsNullOrWhiteSpace(FileName) ? "nq_m1_export.csv" : FileName;
                    _path = Path.Combine(OutputFolder, name);
                }

                if (!_headerChecked)
                {
                    // Truncate on the first flush of a run so a stale schema from an
                    // earlier build can never be appended to silently.
                    using (var header = new StreamWriter(_path, append: false))
                    {
                        header.WriteLine($"# {Version} instrument={InstrumentInfo?.Instrument} " +
                                         $"tf=M1 generated_utc={DateTime.UtcNow:O}");
                        header.WriteLine("time_raw;time_kind;last_time_raw;open;high;low;close;volume;ticks");
                    }

                    _headerChecked = true;
                }

                using var writer = new StreamWriter(_path, append: true);
                foreach (var row in _pending)
                    writer.WriteLine(row);

                _rowsWritten += _pending.Count;
                _pending.Clear();

                WriteStatus($"ok rows={_rowsWritten} path={_path}");
            }
            catch (Exception ex)
            {
                WriteStatus($"error {ex.GetType().Name}: {ex.Message}");
            }
        }

        // The project has no logger; a side file keeps the run auditable without adding
        // a dependency, and lets the offline analysis verify the export completed.
        private void WriteStatus(string message)
        {
            try
            {
                var statusPath = Path.Combine(OutputFolder, "nq_m1_export_status.txt");
                File.WriteAllText(statusPath,
                    $"{Version}{Environment.NewLine}" +
                    $"utc={DateTime.UtcNow:O}{Environment.NewLine}" +
                    $"instrument={InstrumentInfo?.Instrument}{Environment.NewLine}" +
                    $"{message}{Environment.NewLine}");
            }
            catch
            {
                // Status reporting must never break the export itself.
            }
        }
    }
}
