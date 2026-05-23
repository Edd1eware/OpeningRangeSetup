using System;

namespace ATAS.Indicators
{
    internal static class SpeedClasification
    {
        public static decimal CalculateBreakoutSpeed(dynamic candle, decimal bodyBreakoutTicks, DateTime speedBarStartedAtUtc)
        {
            if (bodyBreakoutTicks <= 0)
                return 0;

            var currentTime = TryGetCandleUpdateTime(candle);
            var startTime = candle.Time;
            var elapsedSeconds = (currentTime - startTime).TotalSeconds;

            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
                elapsedSeconds = (DateTime.UtcNow - speedBarStartedAtUtc).TotalSeconds;

            if (elapsedSeconds <= 0)
                elapsedSeconds = 1;

            return bodyBreakoutTicks / (decimal)elapsedSeconds;
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
            try { return candle.LastTime; } catch { }
            try { return candle.LastTradeTime; } catch { }
            try { return candle.TimeLast; } catch { }
            try { return candle.CloseTime; } catch { }
            try { return candle.LastUpdateTime; } catch { }

            return DateTime.UtcNow;
        }
    }
}
