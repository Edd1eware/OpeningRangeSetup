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

        /// <summary>
        /// Calcula estadisticas del CVD de la sesion usando UNICAMENTE barras
        /// con indice menor o igual a <paramref name="bar"/> (sin lookahead).
        /// El CVD se reconstruye barra a barra desde el inicio de la sesion.
        /// </summary>
        public static CumulativeDeltaSessionStats DetectSessionStats(
            int bar,
            Func<int, dynamic> getCandle,
            DateTime sessionDate,
            Func<dynamic, DateTime> getSessionTime,
            int slopeBars)
        {
            var stats = new CumulativeDeltaSessionStats();

            if (getCandle == null || getSessionTime == null || bar < 0)
                return stats;

            // 1) Encontrar la primera barra de la sesion caminando hacia atras.
            var firstSessionBar = bar;

            for (var i = bar; i >= 0; i--)
            {
                dynamic sessionCandle;
                DateTime candleSessionTime;

                try
                {
                    sessionCandle = getCandle(i);
                    candleSessionTime = getSessionTime(sessionCandle);
                }
                catch
                {
                    break;
                }

                if (candleSessionTime.Date != sessionDate.Date)
                    break;

                firstSessionBar = i;
            }

            // 2) Reconstruir el CVD hacia adelante SOLO hasta la barra actual.
            decimal cumulative = 0;
            decimal sessionMax = decimal.MinValue;
            decimal sessionMin = decimal.MaxValue;
            var barOfMax = firstSessionBar;
            var barOfMin = firstSessionBar;
            decimal cvdSlopeBarsAgo = 0;
            var slopeReferenceBar = bar - Math.Max(1, slopeBars);
            var hasAnyBar = false;

            for (var i = firstSessionBar; i <= bar; i++)
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

                cumulative += TryGetDecimal(sessionCandle, "Delta");
                hasAnyBar = true;

                if (cumulative > sessionMax)
                {
                    sessionMax = cumulative;
                    barOfMax = i;
                }

                if (cumulative < sessionMin)
                {
                    sessionMin = cumulative;
                    barOfMin = i;
                }

                if (i == slopeReferenceBar)
                    cvdSlopeBarsAgo = cumulative;
            }

            if (!hasAnyBar)
                return stats;

            stats.HasData = true;
            stats.CvdAtBar = cumulative;
            stats.SessionMax = sessionMax;
            stats.SessionMin = sessionMin;
            stats.BarsSinceMax = bar - barOfMax;
            stats.BarsSinceMin = bar - barOfMin;
            stats.CvdSlope = slopeReferenceBar >= firstSessionBar
                ? cumulative - cvdSlopeBarsAgo
                : cumulative;

            return stats;
        }

        /// <summary>
        /// Pullback del CVD AL MOMENTO DE LA ENTRADA, normalizado por el rango
        /// del CVD de la sesion. 0 = el CVD esta en su extremo a favor del lado;
        /// 1 = el CVD esta en el extremo opuesto. Solo usa datos pre-entrada.
        /// </summary>
        public static decimal CalculateAtEntryPullbackPercent(
            string side,
            decimal cvdAtEntry,
            decimal sessionMax,
            decimal sessionMin)
        {
            side = string.IsNullOrWhiteSpace(side) ? "" : side.Trim().ToUpperInvariant();
            var expansion = sessionMax - sessionMin;

            if (expansion <= 0)
                return 0;

            decimal pullback;

            if (side == "BUY")
                pullback = sessionMax - cvdAtEntry;
            else if (side == "SELL")
                pullback = cvdAtEntry - sessionMin;
            else
                return 0;

            var ratio = pullback / expansion;

            if (ratio < 0)
                return 0;

            return ratio > 1 ? 1 : ratio;
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

        public static string ClassifyPullback(decimal pullbackPercent)
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

    internal sealed class CumulativeDeltaSessionStats
    {
        public bool HasData { get; set; }
        public decimal CvdAtBar { get; set; }
        public decimal SessionMax { get; set; }
        public decimal SessionMin { get; set; }
        public decimal CvdSlope { get; set; }
        public int BarsSinceMax { get; set; }
        public int BarsSinceMin { get; set; }
    }
}
