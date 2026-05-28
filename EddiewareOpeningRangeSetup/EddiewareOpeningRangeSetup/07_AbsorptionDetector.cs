using System;

namespace ATAS.Indicators
{
    internal static class AbsorptionDetector
    {
        public static AbsorptionState DetectTradeManagement(AbsorptionDetectorRequest request)
        {
            var adverseDelta = request.Side == "BUY"
                ? request.Delta < 0
                : request.Delta > 0;
            var strongDelta = Math.Abs(request.Delta) >= request.MinAbsDelta;
            var strongVolume = request.Volume >= request.MinVolume;
            var rejectionTicks = CalculateRejectionTicks(request);
            var progressTicks = CalculateProgressTicks(request);
            var isRejected = rejectionTicks >= request.MinRejectionTicks;
            var isStalled = progressTicks <= request.MaxProgressTicks;
            var isDetected = adverseDelta && strongDelta && strongVolume && isRejected && isStalled;

            return new AbsorptionState
            {
                Side = request.Side,
                Status = isDetected ? "ABSORPTION_EXIT_CONDITION" : "NO_ABSORPTION",
                Delta = request.Delta,
                Volume = request.Volume,
                RejectionTicks = rejectionTicks,
                ProgressTicks = progressTicks,
                IsAdverseDelta = adverseDelta,
                IsStrongDelta = strongDelta,
                IsStrongVolume = strongVolume,
                IsRejected = isRejected,
                IsStalled = isStalled,
                ShouldExit = isDetected
            };
        }

        private static decimal CalculateRejectionTicks(AbsorptionDetectorRequest request)
        {
            if (request.TickSize <= 0)
                return 0;

            var rejection = request.Side == "BUY"
                ? request.High - request.Close
                : request.Close - request.Low;

            return Math.Max(0, Math.Round(rejection / request.TickSize, 2));
        }

        private static decimal CalculateProgressTicks(AbsorptionDetectorRequest request)
        {
            if (request.TickSize <= 0)
                return 0;

            var progress = request.Side == "BUY"
                ? request.High - request.BestFavorablePrice
                : request.BestFavorablePrice - request.Low;

            return Math.Max(0, Math.Round(progress / request.TickSize, 2));
        }
    }

    internal sealed class AbsorptionDetectorRequest
    {
        public string Side { get; set; } = "";
        public decimal Open { get; set; }
        public decimal High { get; set; }
        public decimal Low { get; set; }
        public decimal Close { get; set; }
        public decimal Volume { get; set; }
        public decimal Delta { get; set; }
        public decimal BestFavorablePrice { get; set; }
        public decimal TickSize { get; set; }
        public decimal MinVolume { get; set; }
        public decimal MinAbsDelta { get; set; }
        public decimal MinRejectionTicks { get; set; } = 8m;
        public decimal MaxProgressTicks { get; set; } = 4m;
    }

    internal sealed class AbsorptionState
    {
        public string Side { get; set; } = "";
        public string Status { get; set; } = "NO_ABSORPTION";
        public decimal Delta { get; set; }
        public decimal Volume { get; set; }
        public decimal RejectionTicks { get; set; }
        public decimal ProgressTicks { get; set; }
        public bool IsAdverseDelta { get; set; }
        public bool IsStrongDelta { get; set; }
        public bool IsStrongVolume { get; set; }
        public bool IsRejected { get; set; }
        public bool IsStalled { get; set; }
        public bool ShouldExit { get; set; }
    }
}
