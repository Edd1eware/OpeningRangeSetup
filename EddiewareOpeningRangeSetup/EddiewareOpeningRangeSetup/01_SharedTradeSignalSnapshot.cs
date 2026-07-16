using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace ATAS.Indicators
{
    internal static class SharedTradeSignalSnapshot
    {
        private static readonly object Sync = new object();
        private static readonly Dictionary<SessionKey, Snapshot> Snapshots = new Dictionary<SessionKey, Snapshot>();
        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            WriteIndented = true
        };

        public static Snapshot? CaptureOrGet(
            DateTime sessionDate,
            decimal orLow,
            decimal orHigh,
            int bar,
            DateTime signalTime,
            ScoreTradeSignal signal)
        {
            return CaptureOrGet(
                sessionDate,
                orLow,
                orHigh,
                bar,
                signalTime,
                signal,
                "",
                "");
        }

        public static Snapshot? CaptureOrGet(
            DateTime sessionDate,
            decimal orLow,
            decimal orHigh,
            int bar,
            DateTime signalTime,
            ScoreTradeSignal signal,
            string canonicalFilePath,
            string exporterVersion)
        {
            var key = new SessionKey(sessionDate.Date, orLow, orHigh);

            lock (Sync)
            {
                RemoveOldSessions(sessionDate.Date);

                var persisted = TryReadPersistedSnapshot(
                    canonicalFilePath,
                    exporterVersion,
                    sessionDate.Date,
                    orLow,
                    orHigh);
                if (persisted != null)
                {
                    Snapshots[key] = persisted;
                    return signalTime >= persisted.SignalTime
                        ? persisted
                        : null;
                }

                if (Snapshots.TryGetValue(key, out var existing))
                {
                    if (signalTime < existing.SignalTime)
                    {
                        // Callers sin canonicalFilePath (Visual, otros indicadores)
                        // usan candle.Time como signalTime en recalculo historico, que
                        // puede ser anterior al tick real de la senal. No borrar —
                        // el snapshot sigue siendo valido para dibujar.
                        // Solo el Exporter (con canonicalFilePath) puede eliminar si el
                        // Replay reinicio realmente (tiempo retrocedio entre sesiones).
                        if (string.IsNullOrEmpty(canonicalFilePath))
                            return existing;

                        Snapshots.Remove(key);
                    }
                    else
                    {
                        TryWritePersistedSnapshot(
                            canonicalFilePath,
                            exporterVersion,
                            sessionDate.Date,
                            orLow,
                            orHigh,
                            existing);
                        return existing;
                    }
                }

                if (signal == null || !signal.IsReady)
                    return null;

                var snapshot = new Snapshot(bar, signalTime, CloneSignal(signal));
                Snapshots[key] = snapshot;
                TryWritePersistedSnapshot(
                    canonicalFilePath,
                    exporterVersion,
                    sessionDate.Date,
                    orLow,
                    orHigh,
                    snapshot);
                return snapshot;
            }
        }

        private static Snapshot? TryReadPersistedSnapshot(
            string canonicalFilePath,
            string exporterVersion,
            DateTime sessionDate,
            decimal orLow,
            decimal orHigh)
        {
            if (string.IsNullOrWhiteSpace(canonicalFilePath) ||
                !File.Exists(canonicalFilePath))
            {
                return null;
            }

            try
            {
                var persisted = JsonSerializer.Deserialize<PersistedSnapshot>(
                    File.ReadAllText(canonicalFilePath),
                    JsonOptions);
                if (persisted == null || persisted.Signal == null)
                    return null;

                if (!string.Equals(persisted.ExporterVersion, exporterVersion, StringComparison.Ordinal) ||
                    persisted.SessionDate.Date != sessionDate.Date ||
                    persisted.OrLow != orLow ||
                    persisted.OrHigh != orHigh ||
                    !persisted.Signal.IsReady)
                {
                    return null;
                }

                return new Snapshot(
                    persisted.Bar,
                    persisted.SignalTime,
                    CloneSignal(persisted.Signal));
            }
            catch
            {
                return null;
            }
        }

        private static void TryWritePersistedSnapshot(
            string canonicalFilePath,
            string exporterVersion,
            DateTime sessionDate,
            decimal orLow,
            decimal orHigh,
            Snapshot snapshot)
        {
            if (string.IsNullOrWhiteSpace(canonicalFilePath))
                return;

            try
            {
                var directory = Path.GetDirectoryName(canonicalFilePath);
                if (!string.IsNullOrWhiteSpace(directory) && !Directory.Exists(directory))
                    Directory.CreateDirectory(directory);

                var persisted = new PersistedSnapshot
                {
                    ExporterVersion = exporterVersion,
                    SessionDate = sessionDate.Date,
                    OrLow = orLow,
                    OrHigh = orHigh,
                    Bar = snapshot.Bar,
                    SignalTime = snapshot.SignalTime,
                    Signal = CloneSignal(snapshot.Signal)
                };

                File.WriteAllText(
                    canonicalFilePath,
                    JsonSerializer.Serialize(persisted, JsonOptions));
            }
            catch
            {
                // Best-effort sync helper. In-memory snapshot still works.
            }
        }

        private static void RemoveOldSessions(DateTime activeDate)
        {
            var staleKeys = new List<SessionKey>();

            foreach (var key in Snapshots.Keys)
            {
                if (key.SessionDate != activeDate)
                    staleKeys.Add(key);
            }

            foreach (var key in staleKeys)
                Snapshots.Remove(key);
        }

        private static ScoreTradeSignal CloneSignal(ScoreTradeSignal source)
        {
            return new ScoreTradeSignal
            {
                IsBreakout = source.IsBreakout,
                IsAPlusStructureSignal = source.IsAPlusStructureSignal,
                IsReady = source.IsReady,
                Side = source.Side,
                ExecutionSide = source.ExecutionSide,
                EntryPrice = source.EntryPrice,
                EntryBarHighAtEntry = source.EntryBarHighAtEntry,
                EntryBarLowAtEntry = source.EntryBarLowAtEntry,
                OrLow = source.OrLow,
                OrHigh = source.OrHigh,
                OrRangeTicks = source.OrRangeTicks,
                Vwap = source.Vwap,
                BodyBreakoutTicks = source.BodyBreakoutTicks,
                BreakoutSpeed = source.BreakoutSpeed,
                SpeedElapsedSeconds = source.SpeedElapsedSeconds,
                SpeedUsedReplayFallback = source.SpeedUsedReplayFallback,
                SpeedTimingSource = source.SpeedTimingSource,
                SpeedLabel = source.SpeedLabel,
                RawSpeedLabel = source.RawSpeedLabel,
                Volume = source.Volume,
                Delta = source.Delta,
                CumulativeDelta = source.CumulativeDelta,
                CumulativeDeltaSource = source.CumulativeDeltaSource,
                PreviousVolume = source.PreviousVolume,
                PreviousDelta = source.PreviousDelta,
                VolumeIncreasing = source.VolumeIncreasing,
                DeltaChange = source.DeltaChange,
                DeltaWithSide = source.DeltaWithSide,
                PriceAcceptedAfterImbalance = source.PriceAcceptedAfterImbalance,
                PriceRejectedAfterImbalance = source.PriceRejectedAfterImbalance,
                PriceAcceptedAfterSpeed = source.PriceAcceptedAfterSpeed,
                RangeOk = source.RangeOk,
                BodyOk = source.BodyOk,
                VolumeOk = source.VolumeOk,
                DeltaOk = source.DeltaOk,
                TimeOk = source.TimeOk,
                VwapOk = source.VwapOk,
                SpeedValid = source.SpeedValid,
                HasBuy_ImbalanceUnTouched = source.HasBuy_ImbalanceUnTouched,
                HasSell_ImbalanceUnTouched = source.HasSell_ImbalanceUnTouched,
                HasBuy3_ImbalanceGroup = source.HasBuy3_ImbalanceGroup,
                HasSell3_ImbalanceGroup = source.HasSell3_ImbalanceGroup,
                HasSide3_ImbalanceGroup = source.HasSide3_ImbalanceGroup,
                HasSide3_Imbalances = source.HasSide3_Imbalances,
                HasAny3_ImbalanceGroup = source.HasAny3_ImbalanceGroup,
                BuyImbalanceCount = source.BuyImbalanceCount,
                SellImbalanceCount = source.SellImbalanceCount,
                BreakoutSideImbalanceStopPrice = source.BreakoutSideImbalanceStopPrice,
                ValueAcceptanceStopPrice = source.ValueAcceptanceStopPrice,
                IsValueAcceptance = source.IsValueAcceptance,
                HasAPlusStructure = source.HasAPlusStructure,
                HasAPlusAbsorption = source.HasAPlusAbsorption,
                HasAPlusSpeed = source.HasAPlusSpeed,
                HasAPlusSpeedThreshold = source.HasAPlusSpeedThreshold,
                IsFakeBreakout = source.IsFakeBreakout,
                IsJudasSwing = source.IsJudasSwing,
                HasLiquidityBurst = source.HasLiquidityBurst,
                APlusStructureSide = source.APlusStructureSide,
                APlusStructurePrice = source.APlusStructurePrice,
                LiquidityBurstId = source.LiquidityBurstId,
                LiquidityBurstSide = source.LiquidityBurstSide,
                LiquidityBurstDelta1s = source.LiquidityBurstDelta1s,
                LiquidityBurstDeltaChange1s = source.LiquidityBurstDeltaChange1s,
                LiquidityBurstDeltaChangeZScore = source.LiquidityBurstDeltaChangeZScore,
                LiquidityBurstDeltaPercentile = source.LiquidityBurstDeltaPercentile,
                LiquidityBurstVelocity1s = source.LiquidityBurstVelocity1s,
                LiquidityBurstAcceleration1s = source.LiquidityBurstAcceleration1s,
                LiquidityBurstTradesPerSecond = source.LiquidityBurstTradesPerSecond,
                LiquidityBurstContractsPerSecond = source.LiquidityBurstContractsPerSecond,
                SignalSource = source.SignalSource,
                SpeedIgnoredByStructure = source.SpeedIgnoredByStructure,
                ImbalanceScore = source.ImbalanceScore,
                Score = source.Score
            };
        }

        internal sealed class Snapshot
        {
            public Snapshot(int bar, DateTime signalTime, ScoreTradeSignal signal)
            {
                Bar = bar;
                SignalTime = signalTime;
                Signal = signal;
            }

            public int Bar { get; }
            public DateTime SignalTime { get; }
            public ScoreTradeSignal Signal { get; }
        }

        private sealed class PersistedSnapshot
        {
            public string ExporterVersion { get; set; } = "";
            public DateTime SessionDate { get; set; }
            public decimal OrLow { get; set; }
            public decimal OrHigh { get; set; }
            public int Bar { get; set; }
            public DateTime SignalTime { get; set; }
            public ScoreTradeSignal Signal { get; set; } = new ScoreTradeSignal();
        }

        private readonly struct SessionKey : IEquatable<SessionKey>
        {
            public SessionKey(DateTime sessionDate, decimal orLow, decimal orHigh)
            {
                SessionDate = sessionDate;
                OrLow = orLow;
                OrHigh = orHigh;
            }

            public DateTime SessionDate { get; }
            private decimal OrLow { get; }
            private decimal OrHigh { get; }

            public bool Equals(SessionKey other)
            {
                return SessionDate == other.SessionDate &&
                    OrLow == other.OrLow &&
                    OrHigh == other.OrHigh;
            }

            public override bool Equals(object? obj)
            {
                return obj is SessionKey other && Equals(other);
            }

            public override int GetHashCode()
            {
                return HashCode.Combine(SessionDate, OrLow, OrHigh);
            }
        }
    }
}
