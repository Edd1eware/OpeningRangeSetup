using System;

namespace ATAS.Indicators
{
    internal static class SpeedClasification
    {
        private const double FallbackBarSeconds = 6d;

        public sealed class SpeedState
        {
            public decimal TicksPerSecond { get; set; }
            public decimal ElapsedSeconds { get; set; }
            public bool UsedReplayFallback { get; set; }
            public string TimingSource { get; set; } = "";
        }

        public static decimal CalculateBreakoutSpeed(
            dynamic candle,
            decimal bodyBreakoutTicks,
            DateTime speedBarStartedAtUtc,
            decimal replaySpeedMultiplier = 1,
            DateTime? marketUpdateTime = null)
        {
            return CalculateBreakoutSpeedState(
                candle,
                bodyBreakoutTicks,
                speedBarStartedAtUtc,
                replaySpeedMultiplier,
                marketUpdateTime).TicksPerSecond;
        }

        public static SpeedState CalculateBreakoutSpeedState(
            dynamic candle,
            decimal bodyBreakoutTicks,
            DateTime speedBarStartedAtUtc,
            decimal replaySpeedMultiplier = 1,
            DateTime? marketUpdateTime = null)
        {
            if (bodyBreakoutTicks <= 0)
                return new SpeedState();

            var timingSource = "";
            var currentTime = marketUpdateTime.HasValue &&
                marketUpdateTime.Value != DateTime.MinValue
                    ? marketUpdateTime.Value
                    : TryGetCandleUpdateTime(candle, out timingSource);
            var usedReplayFallback = false;
            double elapsedSeconds;

            if (marketUpdateTime.HasValue &&
                marketUpdateTime.Value != DateTime.MinValue)
            {
                timingSource = "MarketTradeTime";
                elapsedSeconds = (currentTime - candle.Time).TotalSeconds;
            }
            else if (timingSource == "UtcNow")
            {
                usedReplayFallback = true;
                timingSource = "UtcNow-ReplayAdjusted";
                elapsedSeconds = speedBarStartedAtUtc == DateTime.MinValue
                    ? 0
                    : (DateTime.UtcNow - speedBarStartedAtUtc).TotalSeconds *
                      (double)NormalizeReplaySpeedMultiplier(replaySpeedMultiplier);
            }
            else
            {
                // LastTime/LastTradeTime/etc. already contain historical market
                // time during Replay. Multiplying them by X10 would count the
                // replay acceleration twice and understate ticks per second.
                elapsedSeconds = (currentTime - candle.Time).TotalSeconds;
            }

            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
            {
                usedReplayFallback = true;
                timingSource = "bar-close-fallback";
                elapsedSeconds = FallbackBarSeconds;
            }

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
            if (speedTicksPerSecond < minNormalSpeedTicksPerSecond)
                return "invalid speed";

            if (speedTicksPerSecond < aPlusSpeedTicksPerSecond)
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
