namespace ATAS.Indicators
{
    internal static class CumulativeDeltaDetector
    {
        public static CumulativeDeltaState Detect(decimal currentCumulativeDelta, decimal previousCumulativeDelta)
        {
            var change = currentCumulativeDelta - previousCumulativeDelta;

            return new CumulativeDeltaState
            {
                CurrentCumulativeDelta = currentCumulativeDelta,
                PreviousCumulativeDelta = previousCumulativeDelta,
                DeltaChange = change,
                IsRising = change > 0,
                IsFalling = change < 0
            };
        }
    }

    internal sealed class CumulativeDeltaState
    {
        public decimal CurrentCumulativeDelta { get; set; }
        public decimal PreviousCumulativeDelta { get; set; }
        public decimal DeltaChange { get; set; }
        public bool IsRising { get; set; }
        public bool IsFalling { get; set; }
    }
}
