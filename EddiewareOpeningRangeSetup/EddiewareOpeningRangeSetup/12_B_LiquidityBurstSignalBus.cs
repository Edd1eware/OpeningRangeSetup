using System;

namespace ATAS.Indicators
{
    internal static class LiquidityBurstSignalBus
    {
        private static readonly object Sync = new object();
        private static LiquidityBurstSignalSnapshot? _latest;

        public static void Publish(LiquidityBurstSignalSnapshot snapshot)
        {
            if (snapshot == null)
                return;

            lock (Sync)
                _latest = snapshot;
        }

        public static LiquidityBurstSignalSnapshot? GetLatest(
            DateTime sessionDate,
            DateTime currentTime,
            int maxAgeSeconds)
        {
            lock (Sync)
            {
                if (_latest == null)
                    return null;

                if (_latest.SessionDate.Date != sessionDate.Date)
                    return null;

                // Strict causal guard: the completed one-second feature cannot be
                // consumed by another indicator callback whose market timestamp
                // still precedes the detector callback that published it.
                var publishAge = ResolvePublishAgeSeconds(_latest, currentTime);
                if (publishAge < 0)
                    return null;

                var age = ResolveAgeSeconds(_latest, currentTime);
                if (age < 0 || age > Math.Max(1, maxAgeSeconds))
                    return null;

                return _latest;
            }
        }

        public static void Reset()
        {
            lock (Sync)
                _latest = null;
        }

        private static double ResolveAgeSeconds(LiquidityBurstSignalSnapshot snapshot, DateTime currentTime)
        {
            var currentAsUtc = currentTime.Kind == DateTimeKind.Utc
                ? currentTime
                : DateTime.SpecifyKind(currentTime, DateTimeKind.Utc);
            var utcAge = (currentAsUtc - snapshot.TimestampUtc).TotalSeconds;
            var nyAge = (currentTime - snapshot.TimestampNy).TotalSeconds;

            return currentTime.Kind == DateTimeKind.Utc ? utcAge : nyAge;
        }

        private static double ResolvePublishAgeSeconds(
            LiquidityBurstSignalSnapshot snapshot,
            DateTime currentTime)
        {
            var currentAsUtc = currentTime.Kind == DateTimeKind.Utc
                ? currentTime
                : DateTime.SpecifyKind(currentTime, DateTimeKind.Utc);
            var utcAge = (currentAsUtc - snapshot.DetectorPublishTimestampUtc).TotalSeconds;
            var publishDelay = snapshot.DetectorPublishTimestampUtc - snapshot.TimestampUtc;
            var publishNy = snapshot.TimestampNy.Add(publishDelay);
            var nyAge = (currentTime - publishNy).TotalSeconds;

            return currentTime.Kind == DateTimeKind.Utc ? utcAge : nyAge;
        }
    }

    internal sealed class LiquidityBurstSignalSnapshot
    {
        public LiquidityBurstSignalSnapshot(
            string burstId,
            DateTime sessionDate,
            DateTime timestampUtc,
            DateTime detectorPublishTimestampUtc,
            DateTime timestampNy,
            string side,
            decimal price,
            decimal delta1s,
            decimal deltaChange1s,
            decimal deltaChangeZScore,
            decimal deltaPercentile,
            decimal velocity1s,
            decimal acceleration1s,
            decimal tradesPerSecond,
            decimal contractsPerSecond,
            string episodeId,
            int burstIndexInEpisode,
            decimal? secondsSincePriorBurst)
        {
            BurstId = burstId;
            SessionDate = sessionDate.Date;
            TimestampUtc = timestampUtc;
            DetectorPublishTimestampUtc = detectorPublishTimestampUtc;
            TimestampNy = timestampNy;
            Side = side;
            Price = price;
            Delta1s = delta1s;
            DeltaChange1s = deltaChange1s;
            DeltaChangeZScore = deltaChangeZScore;
            DeltaPercentile = deltaPercentile;
            Velocity1s = velocity1s;
            Acceleration1s = acceleration1s;
            TradesPerSecond = tradesPerSecond;
            ContractsPerSecond = contractsPerSecond;
            EpisodeId = episodeId;
            BurstIndexInEpisode = burstIndexInEpisode;
            SecondsSincePriorBurst = secondsSincePriorBurst;
        }

        public string BurstId { get; }
        public DateTime SessionDate { get; }
        public DateTime TimestampUtc { get; }
        public DateTime DetectorPublishTimestampUtc { get; }
        public DateTime TimestampNy { get; }
        public string Side { get; }
        public decimal Price { get; }
        public decimal Delta1s { get; }
        public decimal DeltaChange1s { get; }
        public decimal DeltaChangeZScore { get; }
        public decimal DeltaPercentile { get; }
        public decimal Velocity1s { get; }
        public decimal Acceleration1s { get; }
        public decimal TradesPerSecond { get; }
        public decimal ContractsPerSecond { get; }
        public string EpisodeId { get; }
        public int BurstIndexInEpisode { get; }
        public decimal? SecondsSincePriorBurst { get; }
    }
}
