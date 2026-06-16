using System;

namespace ATAS.Indicators
{
    internal static class SpeedClasification
    {
        public sealed class SpeedState
        {
            public decimal TicksPerSecond { get; set; }
            public decimal ElapsedSeconds { get; set; }
            public bool UsedReplayFallback { get; set; }
            public string TimingSource { get; set; } = "";
        }

        public static decimal CalculateBreakoutSpeed(dynamic candle, decimal bodyBreakoutTicks, DateTime speedBarStartedAtUtc, decimal replaySpeedMultiplier = 1)
        {
            return CalculateBreakoutSpeedState(candle, bodyBreakoutTicks, speedBarStartedAtUtc, replaySpeedMultiplier).TicksPerSecond;
        }

        public static SpeedState CalculateBreakoutSpeedState(dynamic candle, decimal bodyBreakoutTicks, DateTime speedBarStartedAtUtc, decimal replaySpeedMultiplier = 1)
        {
            if (bodyBreakoutTicks <= 0)
                return new SpeedState();

            string timingSource;
            var currentTime = TryGetCandleUpdateTime(candle, out timingSource);
            var startTime = candle.Time;
            var elapsedSeconds = (currentTime - startTime).TotalSeconds;
            var usedReplayFallback = false;

            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
            {
                elapsedSeconds = (DateTime.UtcNow - speedBarStartedAtUtc).TotalSeconds;
                usedReplayFallback = true;
                timingSource = "replay-fallback";
            }

            if (elapsedSeconds <= 0)
                elapsedSeconds = 1;

            elapsedSeconds *= (double)NormalizeReplaySpeedMultiplier(replaySpeedMultiplier);

            return new SpeedState
            {
                TicksPerSecond = bodyBreakoutTicks / (decimal)elapsedSeconds,
                ElapsedSeconds = (decimal)elapsedSeconds,
                UsedReplayFallback = usedReplayFallback,
                TimingSource = timingSource
            };
        }

        private static decimal NormalizeReplaySpeedMultiplier(decimal replaySpeedMultiplier)
        {
            return replaySpeedMultiplier <= 0 ? 1 : replaySpeedMultiplier;
        }

        public static string GetSpeedLabel(
            decimal speedTicksPerSecond,
            decimal minNormalSpeedTicksPerSecond,
            decimal aPlusSpeedTicksPerSecond)
        {
            if (speedTicksPerSecond <= minNormalSpeedTicksPerSecond)
                return "invalid speed";

            if (speedTicksPerSecond <= aPlusSpeedTicksPerSecond)
                return "normal speed";

            return "A+ speed";
        }

        public static DateTime TryGetCandleUpdateTime(dynamic candle)
        {
            string timingSource;
            return TryGetCandleUpdateTime(candle, out timingSource);
        }

        public static DateTime TryGetCandleUpdateTime(dynamic candle, out string timingSource)
        {
            try { timingSource = "LastTime"; return candle.LastTime; } catch { }
            try { timingSource = "LastTradeTime"; return candle.LastTradeTime; } catch { }
            try { timingSource = "TimeLast"; return candle.TimeLast; } catch { }
            try { timingSource = "CloseTime"; return candle.CloseTime; } catch { }
            try { timingSource = "LastUpdateTime"; return candle.LastUpdateTime; } catch { }

            timingSource = "UtcNow";
            return DateTime.UtcNow;
        }
    }
}
