using System;
using System.Collections.Generic;

namespace ATAS.Indicators
{
    internal static class SharedTradeSignalSnapshot
    {
        private static readonly object Sync = new object();
        private static readonly Dictionary<SessionKey, Snapshot> Snapshots = new Dictionary<SessionKey, Snapshot>();

        public static Snapshot? CaptureOrGet(
            DateTime sessionDate,
            decimal orLow,
            decimal orHigh,
            int bar,
            DateTime signalTime,
            ScoreTradeSignal signal)
        {
            var key = new SessionKey(sessionDate.Date, orLow, orHigh);

            lock (Sync)
            {
                RemoveOldSessions(sessionDate.Date);

                if (Snapshots.TryGetValue(key, out var existing))
                    return existing;

                if (signal == null || !signal.IsReady)
                    return null;

                var snapshot = new Snapshot(bar, signalTime, CloneSignal(signal));
                Snapshots[key] = snapshot;
                return snapshot;
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
                IsFakeBreakout = source.IsFakeBreakout,
                IsJudasSwing = source.IsJudasSwing,
                APlusStructureSide = source.APlusStructureSide,
                APlusStructurePrice = source.APlusStructurePrice,
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
