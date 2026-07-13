using System;

namespace ATAS.Indicators
{
    internal static class CumulativeDeltaDetector
    {
        public static CumulativeDeltaState Detect(
            int bar,
            dynamic candle,
            Func<int, dynamic> getCandle,
            DateTime sessionDate,
            Func<dynamic, DateTime> getSessionTime)
        {
            decimal directValue;

            if (TryGetKnownCumulativeDelta(candle, out directValue))
            {
                return new CumulativeDeltaState
                {
                    Value = directValue,
                    Source = "CandleProperty"
                };
            }

            decimal cumulativeDelta = 0;

            for (var i = bar; i >= 0; i--)
            {
                dynamic sessionCandle;

                try
                {
                    sessionCandle = getCandle(i);
                }
                catch
                {
                    break;
                }

                DateTime candleSessionTime;

                try
                {
                    candleSessionTime = getSessionTime(sessionCandle);
                }
                catch
                {
                    break;
                }

                if (candleSessionTime.Date != sessionDate.Date)
                    break;

                cumulativeDelta += TryGetDecimal(sessionCandle, "Delta");
            }

            return new CumulativeDeltaState
            {
                Value = cumulativeDelta,
                Source = "SessionDeltaSum"
            };
        }

        public static CumulativeDeltaPullbackState CalculatePullback(
            string side,
            decimal entryCvd,
            decimal currentCvd,
            decimal previousPeakCvd)
        {
            side = string.IsNullOrWhiteSpace(side) ? "" : side.Trim().ToUpperInvariant();

            var peakCvd = previousPeakCvd;

            if (side == "BUY")
            {
                if (currentCvd > peakCvd)
                    peakCvd = currentCvd;
            }
            else if (side == "SELL")
            {
                if (currentCvd < peakCvd)
                    peakCvd = currentCvd;
            }

            var pullback = CalculatePullbackPercent(side, entryCvd, currentCvd, peakCvd);

            return new CumulativeDeltaPullbackState
            {
                EntryCvd = entryCvd,
                PeakCvd = peakCvd,
                CurrentCvd = currentCvd,
                PullbackPercent = pullback,
                PullbackLabel = ClassifyPullback(pullback)
            };
        }

        private static decimal CalculatePullbackPercent(string side, decimal entryCvd, decimal currentCvd, decimal peakCvd)
        {
            decimal expansion;
            decimal pullback;

            if (side == "SELL")
            {
                expansion = entryCvd - peakCvd;
                pullback = currentCvd - peakCvd;
            }
            else
            {
                expansion = peakCvd - entryCvd;
                pullback = peakCvd - currentCvd;
            }

            if (expansion <= 0)
                return 0;

            var ratio = pullback / expansion;

            if (ratio < 0)
                return 0;

            return ratio;
        }

        private static string ClassifyPullback(decimal pullbackPercent)
        {
            if (pullbackPercent < 0.25m)
                return "Excelente";

            if (pullbackPercent < 0.50m)
                return "Normal";

            if (pullbackPercent < 0.75m)
                return "Advertencia";

            return "Riesgo de reversion";
        }

        private static bool TryGetKnownCumulativeDelta(dynamic candle, out decimal value)
        {
            var propertyNames = new[]
            {
                "CumulativeDelta",
                "Cumulative_Delta",
                "CumDelta",
                "CummulativeDelta",
                "Cummulative_Delta"
            };

            foreach (var propertyName in propertyNames)
            {
                bool found;
                value = TryGetDecimal(candle, propertyName, out found);

                if (found)
                    return true;
            }

            value = 0;
            return false;
        }

        private static decimal TryGetDecimal(dynamic source, string propertyName)
        {
            bool found;
            return TryGetDecimal(source, propertyName, out found);
        }

        private static decimal TryGetDecimal(dynamic source, string propertyName, out bool found)
        {
            found = false;

            if (source == null)
                return 0;

            try
            {
                var property = source.GetType().GetProperty(propertyName);

                if (property == null)
                    return 0;

                var rawValue = property.GetValue(source);

                if (rawValue == null)
                    return 0;

                found = true;
                return Convert.ToDecimal(rawValue);
            }
            catch
            {
                found = false;
                return 0;
            }
        }
    }

    internal sealed class CumulativeDeltaState
    {
        public decimal Value { get; set; }
        public string Source { get; set; } = "";
    }

    internal sealed class CumulativeDeltaPullbackState
    {
        public decimal EntryCvd { get; set; }
        public decimal PeakCvd { get; set; }
        public decimal CurrentCvd { get; set; }
        public decimal PullbackPercent { get; set; }
        public string PullbackLabel { get; set; } = "";
    }
}
