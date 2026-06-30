using System;
using System.IO;
using System.Text.Json;

namespace ATAS.Indicators
{
    // Lee el snapshot canonico de senal generado por el sync ladder en
    //   replay_sync_signals\score_trade_signal_snapshot_<yyyy-MM-dd>_NY.json
    //
    // Este archivo PRE-EXISTE a la corrida de la estrategia (lo escribe el
    // exporter durante el sync X1/X10) y contiene la senal CAUSAL del breakout:
    // bar, hora (UTC), precio de entrada, lado y flags A+. Es inmune al race del
    // canal live: en Replay el exporter solo escribe pending_strategy_signal.txt
    // al CIERRE de sesion (~09:50), demasiado tarde para que la estrategia entre
    // en el breakout (~09:32) -> causaba NO_SIGNAL. Con el snapshot canonico la
    // estrategia tiene la senal desde el inicio y entra al alcanzar la hora real.
    internal static class CanonicalSignalReader
    {
        private static readonly string Folder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\replay_sync_signals";

        public sealed class CanonicalSignal
        {
            public DateTime SessionDate { get; set; }
            public DateTime SignalTimeUtc { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public decimal SlPrice { get; set; }
            public decimal OrLow { get; set; }
            public decimal OrHigh { get; set; }
            public decimal OrRangeTicks { get; set; }
            public bool IsAPlusSpeed { get; set; }
            public int Bar { get; set; }
        }

        public static CanonicalSignal? Read(DateTime sessionDate)
        {
            try
            {
                var path = Path.Combine(
                    Folder,
                    $"score_trade_signal_snapshot_{sessionDate:yyyy-MM-dd}_NY.json");
                if (!File.Exists(path))
                    return null;

                using var doc = JsonDocument.Parse(File.ReadAllText(path));
                var root = doc.RootElement;

                if (!root.TryGetProperty("Signal", out var sig))
                    return null;
                if (!(sig.TryGetProperty("IsReady", out var ready) && ready.GetBoolean()))
                    return null;

                var sessDate = root.TryGetProperty("SessionDate", out var sd)
                    ? sd.GetDateTime()
                    : sessionDate;
                if (sessDate.Date != sessionDate.Date)
                    return null;

                var side = "";
                if (sig.TryGetProperty("ExecutionSide", out var es))
                    side = es.GetString() ?? "";
                if (string.IsNullOrEmpty(side) && sig.TryGetProperty("Side", out var sv))
                    side = sv.GetString() ?? "";
                if (string.IsNullOrEmpty(side))
                    return null;

                var signalUtc = root.TryGetProperty("SignalTime", out var st)
                    ? DateTime.SpecifyKind(st.GetDateTime(), DateTimeKind.Utc)
                    : DateTime.MinValue;

                decimal Dec(JsonElement parent, string name) =>
                    parent.TryGetProperty(name, out var v) && v.TryGetDecimal(out var d) ? d : 0m;

                var orLow  = Dec(sig, "OrLow");
                var orHigh = Dec(sig, "OrHigh");

                return new CanonicalSignal
                {
                    SessionDate   = sessDate.Date,
                    SignalTimeUtc = signalUtc,
                    Side          = side,
                    EntryPrice    = Dec(sig, "EntryPrice"),
                    // SL no esta en el snapshot; la estrategia lo deriva de SlTicks.
                    // Se deja un valor informativo desde el borde del OR contrario.
                    SlPrice       = side == "BUY" ? orLow : orHigh,
                    OrLow         = orLow,
                    OrHigh        = orHigh,
                    OrRangeTicks  = Dec(sig, "OrRangeTicks"),
                    IsAPlusSpeed  = sig.TryGetProperty("HasAPlusSpeedThreshold", out var ap) && ap.GetBoolean(),
                    Bar           = root.TryGetProperty("Bar", out var b) && b.TryGetInt32(out var bi) ? bi : -1
                };
            }
            catch
            {
                return null;
            }
        }
    }
}
