using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using ATAS.Indicators;

namespace ATAS.Indicators
{
    public class ATASFootprintSessionExporter : Indicator
    {
        private readonly string _exportFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator";

        private readonly string _targetDateFile =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\target_date.txt";

        // Horario NY directo
        private readonly TimeSpan _startTimeNy = new TimeSpan(9, 30, 0);
        private readonly TimeSpan _endTimeNy = new TimeSpan(10, 30, 0);

        private readonly HashSet<string> _exportedBars = new HashSet<string>();

        private readonly TimeZoneInfo _nyZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        public ATASFootprintSessionExporter()
        {
            Name = "ATAS Footprint Session Exporter Target Date NY 0930 1030";
            EnableCustomDrawing = false;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (bar < 1)
                return;

            int closedBar = bar - 1;

            var c = GetCandle(closedBar);

            DateTime nyTime = ConvertToNewYorkTime(c.Time);

            var targetDate = ReadTargetDate();

            if (targetDate == null)
                return;

            if (nyTime.Date != targetDate.Value.Date)
                return;

            var t = nyTime.TimeOfDay;

            if (t < _startTimeNy || t > _endTimeNy)
                return;

            string key = nyTime.ToString("yyyy-MM-dd") + "_" + closedBar;

            if (_exportedBars.Contains(key))
                return;

            ExportClosedCandle(closedBar, nyTime);

            _exportedBars.Add(key);
        }

        private DateTime ConvertToNewYorkTime(DateTime candleTime)
        {
            DateTime utcTime;

            if (candleTime.Kind == DateTimeKind.Utc)
                utcTime = candleTime;
            else
                utcTime = DateTime.SpecifyKind(candleTime, DateTimeKind.Utc);

            return TimeZoneInfo.ConvertTimeFromUtc(utcTime, _nyZone);
        }

        private DateTime? ReadTargetDate()
        {
            if (!File.Exists(_targetDateFile))
                return null;

            string txt = File.ReadAllText(_targetDateFile).Trim();

            if (DateTime.TryParseExact(
                txt,
                "yyyy-MM-dd",
                CultureInfo.InvariantCulture,
                DateTimeStyles.None,
                out DateTime parsed))
            {
                return parsed.Date;
            }

            return null;
        }

        private void ExportClosedCandle(int candleBar, DateTime nyTime)
        {
            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var c = GetCandle(candleBar);

            string dateStr = nyTime.ToString("yyyy-MM-dd");

            string filePath = Path.Combine(
                _exportFolder,
                $"footprint_atas_{dateStr}_0930_1030_NY.csv"
            );

            bool fileExists = File.Exists(filePath);

            using (var writer = new StreamWriter(filePath, true))
            {
                if (!fileExists)
                {
                    writer.WriteLine(
                        "date_ny,time_ny,date_utc,time_utc,bar_index,price,bid,ask,level_volume," +
                        "candle_open,candle_high,candle_low,candle_close,candle_delta,candle_volume"
                    );
                }

                var levels = c.GetAllPriceLevels();

                foreach (var level in levels.OrderByDescending(x => x.Price))
                {
                    writer.WriteLine(string.Join(",",
                        nyTime.ToString("yyyy-MM-dd"),
                        nyTime.ToString("HH:mm:ss"),
                        c.Time.ToString("yyyy-MM-dd"),
                        c.Time.ToString("HH:mm:ss"),
                        candleBar.ToString(CultureInfo.InvariantCulture),
                        level.Price.ToString(CultureInfo.InvariantCulture),
                        level.Bid.ToString(CultureInfo.InvariantCulture),
                        level.Ask.ToString(CultureInfo.InvariantCulture),
                        level.Volume.ToString(CultureInfo.InvariantCulture),
                        c.Open.ToString(CultureInfo.InvariantCulture),
                        c.High.ToString(CultureInfo.InvariantCulture),
                        c.Low.ToString(CultureInfo.InvariantCulture),
                        c.Close.ToString(CultureInfo.InvariantCulture),
                        c.Delta.ToString(CultureInfo.InvariantCulture),
                        c.Volume.ToString(CultureInfo.InvariantCulture)
                    ));
                }
            }
        }
    }
}