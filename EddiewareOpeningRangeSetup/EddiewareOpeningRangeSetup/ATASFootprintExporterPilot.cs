using System;
using System.Globalization;
using System.IO;
using System.Linq;
using ATAS.Indicators;

namespace ATAS.Indicators
{
    public class ATASFootprintExporterPilot : Indicator
    {
        private readonly string _exportFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator";

        private readonly DateTime _targetDate =
            new DateTime(2026, 5, 8);

        // En UTC porque ATAS está entregando 13:30 = 09:30 NY
        private readonly TimeSpan _targetCandleTimeUtc =
            new TimeSpan(13, 30, 0);

        private bool _exported930 = false;

        public ATASFootprintExporterPilot()
        {
            Name = "ATAS Export Closed 930 Footprint";
            EnableCustomDrawing = false;
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            if (_exported930)
                return;

            if (bar < 2)
                return;

            var current = GetCandle(bar);
            var previous = GetCandle(bar - 1);

            // Esperar a que ya estemos en una vela posterior a 9:30 UTC.
            // Así la vela 9:30 ya cerró.
            if (previous.Time.Date != _targetDate.Date)
                return;

            if (previous.Time.TimeOfDay != _targetCandleTimeUtc)
                return;

            if (current.Time.TimeOfDay <= _targetCandleTimeUtc)
                return;

            ExportClosedCandle(bar - 1);

            _exported930 = true;
        }

        private void ExportClosedCandle(int candleBar)
        {
            if (!Directory.Exists(_exportFolder))
                Directory.CreateDirectory(_exportFolder);

            var c = GetCandle(candleBar);

            string filePath = Path.Combine(
                _exportFolder,
                "closed_footprint_atas_2026-05-08_0930NY.csv"
            );

            using (var writer = new StreamWriter(filePath, false))
            {
                writer.WriteLine("date,time_utc,bar_index,price,bid,ask,volume,candle_open,candle_high,candle_low,candle_close,candle_delta,candle_volume");

                var levels = c.GetAllPriceLevels();

                foreach (var level in levels.OrderByDescending(x => x.Price))
                {
                    writer.WriteLine(string.Join(",",
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