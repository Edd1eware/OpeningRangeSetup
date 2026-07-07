using System;
using System.Collections.Generic;

namespace ATAS.Indicators
{
    // Cross-indicator bridge (same idiom as SharedTradeSignalSnapshot): the
    // Volume_Profile_Eddieware indicator PUBLISHES the frozen levels per session date,
    // and ATASScoreTradeResultExporter READS them when it writes a trade row. Both run in
    // the same ATAS process, so the static store is shared. No file I/O here.
    internal static class VolumeProfileStore
    {
        private static readonly object Sync = new object();
        private static readonly Dictionary<DateTime, VolumeProfileLevels> Map = new();

        public static void Publish(DateTime sessionDate, VolumeProfileLevels levels)
        {
            var key = sessionDate.Date;
            lock (Sync)
            {
                Prune(key);
                Map[key] = levels;
            }
        }

        public static bool TryGet(DateTime sessionDate, out VolumeProfileLevels levels)
        {
            lock (Sync)
            {
                return Map.TryGetValue(sessionDate.Date, out levels);
            }
        }

        // Keep only the active session to avoid unbounded growth / stale reads.
        private static void Prune(DateTime activeDate)
        {
            if (Map.Count == 0)
                return;

            var stale = new List<DateTime>();
            foreach (var k in Map.Keys)
                if (k != activeDate)
                    stale.Add(k);

            foreach (var k in stale)
                Map.Remove(k);
        }
    }

    internal struct VolumeProfileLevels
    {
        public bool HasDirection;
        public decimal DirPoc;
        public decimal DirVah;
        public decimal DirVal;
        public decimal DirHigh;
        public decimal DirLow;
        public decimal DirRangeTicks;
        public string Direction;   // HIGH / LOW / INSIDE / ""

        public bool HasLvn;
        public decimal LvnPoc;
        public decimal[] LvnLevels; // orange line prices; may be empty
    }
}
