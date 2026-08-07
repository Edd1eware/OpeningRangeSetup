using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Text;
using ATAS.Indicators;

namespace ATAS.Indicators
{
    /// <summary>
    /// Dumps raw footprint data (per-bar OHLC plus per-price Bid/Ask) to CSV so the
    /// NetFlow -> orderflow pilot can compute imbalances numerically in Python instead
    /// of reading them from screenshots.
    ///
    /// Read-only: it never places orders and never mutates chart visuals.
    ///
    /// Intended usage:
    ///   Pass 1 - attach to an NQ m1 chart covering the pilot dates -> imbalance zones.
    ///   Pass 2 - attach to a finer chart (1 second) -> intrabar SL/TP ordering.
    /// One CSV pair is written per session date so a single chart load can cover many days.
    /// </summary>
    [DisplayName("NetFlow Footprint Exporter")]
    public class NetFlowFootprintExporter : Indicator
    {
        private const string ExporterVersion = "netflow-footprint-exporter-2026-08-04-v2";

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private readonly HashSet<string> _writtenHeaders = new HashSet<string>();

        // Keyed by bar timestamp, not by bar index: reloading chart history shifts every
        // index, so an index-keyed set would silently skip the newly loaded bars.
        private readonly HashSet<string> _exportedBarKeys = new HashSet<string>();

        private int _lastProcessedBar = -1;

        public NetFlowFootprintExporter()
            : base(true)
        {
            DenyToChangePanel = true;
            DataSeries[0].IsHidden = true;
        }

        [Display(Name = "Export folder", GroupName = "Output", Order = 10)]
        public string ExportFolder { get; set; } =
            @"C:\Users\k_99_\Documents\Indicador ATAS\netflow-orderflow-research-db\data\raw\atas_footprint";

        [Display(Name = "Session tag", GroupName = "Output", Order = 20)]
        public string SessionTag { get; set; } = "m1";

        [Display(Name = "Window start NY (HH:mm)", GroupName = "Filter", Order = 30)]
        public string WindowStartNy { get; set; } = "09:25";

        [Display(Name = "Window end NY (HH:mm)", GroupName = "Filter", Order = 40)]
        public string WindowEndNy { get; set; } = "10:45";

        [Display(Name = "Export levels", GroupName = "Filter", Order = 50)]
        public bool ExportLevels { get; set; } = true;

        protected override void OnCalculate(int bar, decimal value)
        {
            WriteDiagnosticOnce(bar);

            // Only export bars that are already closed, so partial footprint is never written.
            var closedBar = bar - 1;

            if (closedBar < 0 || closedBar == _lastProcessedBar)
                return;

            _lastProcessedBar = closedBar;
            TryExportBar(closedBar);
        }

        /// <summary>
        /// Heartbeat written on the first calculation so an empty export folder can be told
        /// apart from an indicator that never ran at all.
        /// </summary>
        private void WriteDiagnosticOnce(int bar)
        {
            // Written on every fresh calculation pass, so reloading chart history leaves
            // a new line instead of staying silent behind a one-shot flag.
            if (bar != 0)
                return;

            var instrument = "unknown";
            var timeFrame = "unknown";
            var firstBarNy = "unknown";
            var lastBarNy = "unknown";
            var totalBars = -1;

            try
            {
                instrument = InstrumentInfo?.Instrument ?? "null";
            }
            catch
            {
                instrument = "throw";
            }

            try
            {
                timeFrame = ChartInfo?.TimeFrame ?? "null";
            }
            catch
            {
                timeFrame = "throw";
            }

            try
            {
                totalBars = CurrentBar;
                firstBarNy = ConvertToNewYorkTime(GetCandle(0).Time)
                    .ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);
                lastBarNy = ConvertToNewYorkTime(GetCandle(Math.Max(0, CurrentBar - 1)).Time)
                    .ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);
            }
            catch
            {
                // Leave the placeholders.
            }

            var line = string.Join(
                ",",
                ExporterVersion,
                DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture),
                Sanitize(instrument),
                Sanitize(timeFrame),
                Sanitize(SessionTag),
                totalBars.ToString(CultureInfo.InvariantCulture),
                bar.ToString(CultureInfo.InvariantCulture),
                firstBarNy,
                lastBarNy,
                Sanitize(WindowStartNy),
                Sanitize(WindowEndNy));

            const string header =
                "exporter_version,local_time,instrument,timeframe,session_tag," +
                "current_bar,calc_bar,first_bar_ny,last_bar_ny,window_start_ny,window_end_ny";

            AppendLine(Path.Combine(ExportFolder, "_diagnostic.csv"), header, line);
        }

        private void TryExportBar(int bar)
        {
            IndicatorCandle candle;

            try
            {
                candle = GetCandle(bar);
            }
            catch
            {
                return;
            }

            if (candle == null)
                return;

            var ny = ConvertToNewYorkTime(candle.Time);

            if (!IsInsideWindow(ny))
                return;

            var barKey = ny.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);

            if (!_exportedBarKeys.Add(barKey))
                return;

            var dateKey = ny.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

            WriteBarRow(dateKey, bar, ny, candle);

            if (ExportLevels)
                WriteLevelRows(dateKey, ny, candle);
        }

        private bool IsInsideWindow(DateTime ny)
        {
            if (!TryParseHourMinute(WindowStartNy, out var start))
                start = new TimeSpan(9, 25, 0);

            if (!TryParseHourMinute(WindowEndNy, out var end))
                end = new TimeSpan(10, 45, 0);

            var time = ny.TimeOfDay;
            return time >= start && time < end;
        }

        private static bool TryParseHourMinute(string text, out TimeSpan result)
        {
            return TimeSpan.TryParseExact(
                text,
                @"hh\:mm",
                CultureInfo.InvariantCulture,
                out result);
        }

        private void WriteBarRow(string dateKey, int bar, DateTime ny, IndicatorCandle candle)
        {
            var path = BuildPath(dateKey, "bars");

            const string header =
                "exporter_version,session_date_ny,bar_time_ny,bar_index,timeframe_tag," +
                "open,high,low,close,volume,delta,max_delta,min_delta,ticks";

            var row = string.Join(
                ",",
                ExporterVersion,
                dateKey,
                ny.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture),
                bar.ToString(CultureInfo.InvariantCulture),
                Sanitize(SessionTag),
                Format(candle.Open),
                Format(candle.High),
                Format(candle.Low),
                Format(candle.Close),
                Format(candle.Volume),
                Format(candle.Delta),
                Format(candle.MaxDelta),
                Format(candle.MinDelta),
                Format(candle.Ticks));

            AppendLine(path, header, row);
        }

        private void WriteLevelRows(string dateKey, DateTime ny, IndicatorCandle candle)
        {
            var path = BuildPath(dateKey, "levels");

            const string header =
                "exporter_version,session_date_ny,bar_time_ny,timeframe_tag,price,bid,ask,volume";

            var builder = new StringBuilder();
            var barTime = ny.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);

            try
            {
                foreach (var level in candle.GetAllPriceLevels())
                {
                    builder.Append(ExporterVersion).Append(',')
                        .Append(dateKey).Append(',')
                        .Append(barTime).Append(',')
                        .Append(Sanitize(SessionTag)).Append(',')
                        .Append(Format(level.Price)).Append(',')
                        .Append(Format(level.Bid)).Append(',')
                        .Append(Format(level.Ask)).Append(',')
                        .Append(Format(level.Volume))
                        .Append('\n');
                }
            }
            catch
            {
                return;
            }

            if (builder.Length == 0)
                return;

            AppendLine(path, header, builder.ToString().TrimEnd('\n'));
        }

        private string BuildPath(string dateKey, string kind)
        {
            var fileName = string.Format(
                CultureInfo.InvariantCulture,
                "netflow_fp_{0}_{1}_{2}.csv",
                kind,
                dateKey,
                Sanitize(SessionTag));

            return Path.Combine(ExportFolder, fileName);
        }

        private void AppendLine(string path, string header, string payload)
        {
            try
            {
                var folder = Path.GetDirectoryName(path);

                if (!string.IsNullOrEmpty(folder) && !Directory.Exists(folder))
                    Directory.CreateDirectory(folder);

                if (_writtenHeaders.Add(path) && !File.Exists(path))
                    File.AppendAllText(path, header + "\n", Encoding.UTF8);

                File.AppendAllText(path, payload + "\n", Encoding.UTF8);
            }
            catch
            {
                // Never let an IO failure break the chart calculation.
            }
        }

        private static string Sanitize(string text)
        {
            if (string.IsNullOrWhiteSpace(text))
                return "unset";

            return text.Replace(',', '_').Replace('\n', '_').Replace('\r', '_').Trim();
        }

        private static string Format(decimal value)
        {
            return value.ToString(CultureInfo.InvariantCulture);
        }

        private DateTime ConvertToNewYorkTime(DateTime candleTime)
        {
            var utcTime = candleTime.Kind == DateTimeKind.Utc
                ? candleTime
                : DateTime.SpecifyKind(candleTime, DateTimeKind.Utc);

            return TimeZoneInfo.ConvertTimeFromUtc(utcTime, _nyZone);
        }
    }
}
