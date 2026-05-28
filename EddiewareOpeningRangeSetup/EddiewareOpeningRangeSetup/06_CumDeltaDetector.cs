using System;

namespace ATAS.Indicators
{
    internal static class CumDeltaDetector
    {
        public static CumDeltaState DetectTradeManagement(decimal cumulativeDeltaFromEntry, decimal bestManagementValue, string side, decimal minAbsDelta)
        {
            var state = Detect(cumulativeDeltaFromEntry, side, minAbsDelta);
            state.ManagementValue = side == "BUY"
                ? cumulativeDeltaFromEntry
                : -cumulativeDeltaFromEntry;
            state.BestManagementValue = Math.Max(bestManagementValue, state.ManagementValue);
            state.WeaknessPercent = CalculateWeaknessPercent(state.ManagementValue, state.BestManagementValue);
            state.Status = GetStatus(state.WeaknessPercent);
            state.IsSupportiveForTrade = state.ManagementValue > 0;
            state.IsAgainstTrade = state.ManagementValue < 0;
            state.ShouldExit = state.WeaknessPercent > 50m;
            return state;
        }

        public static CumDeltaState Detect(decimal delta, string side, decimal minAbsDelta)
        {
            var absDelta = Math.Abs(delta);

            return new CumDeltaState
            {
                Delta = delta,
                AbsDelta = absDelta,
                IsStrongEnough = absDelta >= minAbsDelta,
                IsBuyAligned = side == "BUY" && delta > 0,
                IsSellAligned = side == "SELL" && delta < 0
            };
        }

        public static CumDeltaState Detect(decimal currentCumulativeDelta, decimal previousCumulativeDelta, string side, decimal minAbsDelta)
        {
            return Detect(currentCumulativeDelta - previousCumulativeDelta, side, minAbsDelta);
        }

        private static decimal CalculateWeaknessPercent(decimal managementValue, decimal bestManagementValue)
        {
            if (bestManagementValue <= 0)
                return managementValue < 0 ? 100m : 0m;

            var weakness = (bestManagementValue - managementValue) / bestManagementValue * 100m;
            return Math.Max(0m, Math.Min(100m, Math.Round(weakness, 2)));
        }

        private static string GetStatus(decimal weaknessPercent)
        {
            if (weaknessPercent > 50m)
                return "EXIT_CONDITION";

            if (weaknessPercent >= 30m)
                return "WEAKENING";

            return "HEALTHY";
        }
    }

    internal sealed class CumDeltaState
    {
        public decimal Delta { get; set; }
        public decimal AbsDelta { get; set; }
        public decimal ManagementValue { get; set; }
        public decimal BestManagementValue { get; set; }
        public decimal WeaknessPercent { get; set; }
        public string Status { get; set; } = "HEALTHY";
        public bool IsStrongEnough { get; set; }
        public bool IsBuyAligned { get; set; }
        public bool IsSellAligned { get; set; }
        public bool IsSupportiveForTrade { get; set; }
        public bool IsAgainstTrade { get; set; }
        public bool ShouldExit { get; set; }
        public bool IsAlignedWithSide => IsBuyAligned || IsSellAligned;
    }
}
