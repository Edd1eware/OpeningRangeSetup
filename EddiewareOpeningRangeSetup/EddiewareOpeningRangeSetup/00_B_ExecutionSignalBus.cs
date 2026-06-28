using System;

namespace ATAS.Indicators
{
    // Canal en memoria entre el indicador (exporter, detecta la senal) y la
    // ChartStrategy (Execution Manager, coloca las ordenes). Aditivo: el exporter
    // PUBLICA cada entrada; la estrategia la CONSUME. No altera la operativa ni los
    // CSV sincronizados (es un side-channel).
    internal static class ExecutionSignalBus
    {
        private static readonly object Sync = new object();

        public sealed class PendingEntry
        {
            public DateTime SessionDate { get; set; }
            public DateTime SignalTimeNy { get; set; }
            public string Side { get; set; } = "";       // BUY / SELL
            public decimal EntryPrice { get; set; }
            public decimal SlPrice { get; set; }
            public bool IsAPlusSpeed { get; set; }
            public string SpeedLabel { get; set; } = "";
            public decimal OrRangeTicks { get; set; }
            public int Bar { get; set; }
            public bool Consumed { get; set; }
        }

        private static PendingEntry? _latest;

        // Llamado por el exporter cuando crea un trade (una vez por senal/sesion).
        public static void Publish(PendingEntry entry)
        {
            if (entry == null)
                return;
            lock (Sync)
            {
                // Solo una entrada por sesion; si ya hay una consumida o de la misma
                // fecha y bar, no la dupliques.
                if (_latest != null &&
                    _latest.SessionDate.Date == entry.SessionDate.Date &&
                    _latest.Bar == entry.Bar)
                {
                    return;
                }
                _latest = entry;
            }
        }

        // Devuelve la entrada pendiente de la fecha si existe y no fue consumida.
        public static PendingEntry? Peek(DateTime sessionDate)
        {
            lock (Sync)
            {
                if (_latest == null || _latest.Consumed)
                    return null;
                if (_latest.SessionDate.Date != sessionDate.Date)
                    return null;
                return _latest;
            }
        }

        public static void MarkConsumed(DateTime sessionDate)
        {
            lock (Sync)
            {
                if (_latest != null && _latest.SessionDate.Date == sessionDate.Date)
                    _latest.Consumed = true;
            }
        }

        public static void Reset()
        {
            lock (Sync)
            {
                _latest = null;
            }
        }
    }
}
