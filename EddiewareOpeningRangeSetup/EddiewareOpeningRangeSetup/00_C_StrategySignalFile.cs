using System;
using System.Globalization;
using System.IO;

namespace ATAS.Indicators
{
    // Canal en disco entre el Exporter y la ChartStrategy. Necesario porque ATAS
    // carga el DLL dos veces (Indicators/ y Strategies/) generando dos instancias
    // estaticas separadas. Un archivo supera ese limite.
    internal static class StrategySignalFile
    {
        private const string SignalFileName = "pending_strategy_signal.txt";

        private static readonly string SignalFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";

        public sealed class SignalData
        {
            public DateTime SessionDate { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public decimal SlPrice { get; set; }
            public decimal TpPrice { get; set; }
            public bool IsAPlusSpeed { get; set; }
            public int Bar { get; set; }
        }

        private static string FilePath =>
            Path.Combine(SignalFolder, SignalFileName);

        // Escribe la senal. Llamado por el Exporter al detectar A+ Speed.
        public static void Write(SignalData data)
        {
            if (data == null) return;
            try
            {
                Directory.CreateDirectory(SignalFolder);
                var line = string.Join(",",
                    data.SessionDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    data.Side,
                    data.EntryPrice.ToString(CultureInfo.InvariantCulture),
                    data.SlPrice.ToString(CultureInfo.InvariantCulture),
                    data.TpPrice.ToString(CultureInfo.InvariantCulture),
                    data.IsAPlusSpeed ? "1" : "0",
                    data.Bar.ToString(CultureInfo.InvariantCulture),
                    "PENDING");
                File.WriteAllText(FilePath, line);
            }
            catch { }
        }

        // Lee la senal si es de la fecha esperada y no fue consumida.
        public static SignalData? Read(DateTime sessionDate)
        {
            try
            {
                if (!File.Exists(FilePath))
                    return null;
                var line = File.ReadAllText(FilePath).Trim();
                var parts = line.Split(',');
                if (parts.Length < 7) return null;
                var legacyFormat = parts.Length == 7;
                var statusIndex = legacyFormat ? 6 : 7;
                if (parts[statusIndex] != "PENDING") return null;
                if (!DateTime.TryParseExact(parts[0], "yyyy-MM-dd",
                    CultureInfo.InvariantCulture, DateTimeStyles.None, out var date))
                    return null;
                if (date.Date != sessionDate.Date) return null;

                return new SignalData
                {
                    SessionDate = date,
                    Side = parts[1],
                    EntryPrice = decimal.Parse(parts[2], CultureInfo.InvariantCulture),
                    SlPrice = decimal.Parse(parts[3], CultureInfo.InvariantCulture),
                    TpPrice = legacyFormat ? 0 : decimal.Parse(parts[4], CultureInfo.InvariantCulture),
                    IsAPlusSpeed = parts[legacyFormat ? 4 : 5] == "1",
                    Bar = int.Parse(parts[legacyFormat ? 5 : 6], CultureInfo.InvariantCulture)
                };
            }
            catch { return null; }
        }

        // Marca como consumida. Llamado por la Strategy al entrar al trade.
        public static void MarkConsumed(DateTime sessionDate)
        {
            try
            {
                if (!File.Exists(FilePath)) return;
                var line = File.ReadAllText(FilePath).Trim();
                var parts = line.Split(',');
                if (parts.Length < 7) return;
                if (!DateTime.TryParseExact(parts[0], "yyyy-MM-dd",
                    CultureInfo.InvariantCulture, DateTimeStyles.None, out var date))
                    return;
                if (date.Date != sessionDate.Date) return;
                parts[parts.Length == 7 ? 6 : 7] = "CONSUMED";
                File.WriteAllText(FilePath, string.Join(",", parts));
            }
            catch { }
        }
    }
}
