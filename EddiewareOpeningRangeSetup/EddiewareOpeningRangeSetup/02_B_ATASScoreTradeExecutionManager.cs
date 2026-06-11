using System;

namespace ATAS.Indicators
{
    internal static class ATASScoreTradeExecutionManager
    {
        public sealed class CvdPullbackUpdateRequest
        {
            public string Side { get; set; } = "";
            public decimal EntryCvd { get; set; }
            public decimal PreviousPeakCvd { get; set; }
            public int Bar { get; set; }
            public dynamic? Candle { get; set; }
            public Func<int, dynamic>? GetCandle { get; set; }
            public DateTime SessionDate { get; set; }
            public Func<dynamic, DateTime>? GetSessionTime { get; set; }
        }

        public sealed class CvdPullbackUpdate
        {
            public decimal CumulativeDelta { get; set; }
            public string CumulativeDeltaSource { get; set; } = "";
            public decimal CvdPeak { get; set; }
            public decimal CvdCurrent { get; set; }
            public decimal CvdPullbackPercent { get; set; }
            public string CvdPullbackLabel { get; set; } = "";
        }

        public sealed class CvdRiskBracketRequest
        {
            public string Side { get; set; } = "";
            public string SpeedLabel { get; set; } = "";
            public string Result { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal TpTicks { get; set; }
            public decimal TickSize { get; set; }
            public string CvdPullbackLabel { get; set; } = "";
            public bool CvdRiskBracketActive { get; set; }
            public bool AllowNormalSpeed { get; set; }
        }

        public sealed class CvdRiskBracketDecision
        {
            public bool ShouldApply { get; set; }
            public decimal Tp { get; set; }
            public decimal TpTicks { get; set; }
        }

        public sealed class CvdProfitLockRequest
        {
            public string Side { get; set; } = "";
            public string SpeedLabel { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal TpTicks { get; set; }
            public decimal TickSize { get; set; }
            public decimal MfeTicks { get; set; }
            public decimal CurrentBestMfeTicks { get; set; }
            public decimal CurrentLockTicks { get; set; }
            public decimal PullbackTicks { get; set; }
            public bool AllowNormalSpeed { get; set; }
        }

        public sealed class CvdProfitLockUpdate
        {
            public bool Armed { get; set; }
            public decimal BestMfeTicks { get; set; }
            public decimal LockTicks { get; set; }
            public decimal ExitPrice { get; set; }
        }

        public sealed class CvdRiskExitProgressRequest
        {
            public string Side { get; set; } = "";
            public string SpeedLabel { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal TpTicks { get; set; }
            public decimal TickSize { get; set; }
            public decimal CurrentPrice { get; set; }
            public bool ProfitLockArmed { get; set; }
            public decimal ProfitLockExitPrice { get; set; }
            public decimal ProfitLockTicks { get; set; }
            public decimal ProfitLockBestMfeTicks { get; set; }
            public string CvdPullbackLabel { get; set; } = "";
            public bool AllowNormalSpeed { get; set; }
        }

        public static CvdPullbackUpdate UpdateCvdPullback(CvdPullbackUpdateRequest request)
        {
            if (request.Candle == null || request.GetCandle == null || request.GetSessionTime == null)
            {
                return new CvdPullbackUpdate
                {
                    CumulativeDelta = request.EntryCvd,
                    CumulativeDeltaSource = "Unavailable",
                    CvdPeak = request.PreviousPeakCvd,
                    CvdCurrent = request.EntryCvd,
                    CvdPullbackPercent = 0,
                    CvdPullbackLabel = "Excelente"
                };
            }

            var currentCvd = CumulativeDeltaDetector.Detect(
                request.Bar,
                request.Candle,
                request.GetCandle,
                request.SessionDate,
                request.GetSessionTime);

            var pullback = CumulativeDeltaDetector.CalculatePullback(
                request.Side,
                request.EntryCvd,
                currentCvd.Value,
                request.PreviousPeakCvd);

            return new CvdPullbackUpdate
            {
                CumulativeDelta = currentCvd.Value,
                CumulativeDeltaSource = currentCvd.Source,
                CvdPeak = pullback.PeakCvd,
                CvdCurrent = pullback.CurrentCvd,
                CvdPullbackPercent = pullback.PullbackPercent,
                CvdPullbackLabel = pullback.PullbackLabel
            };
        }

        public static CvdRiskBracketDecision TryApplyCvdRiskBracket(CvdRiskBracketRequest request)
        {
            if (request.Result != "OPEN")
                return new CvdRiskBracketDecision();

            if (request.CvdRiskBracketActive)
                return new CvdRiskBracketDecision();

            if (request.SpeedLabel == "normal speed" && !request.AllowNormalSpeed)
                return new CvdRiskBracketDecision();

            if (request.TpTicks <= 0 || request.TickSize <= 0)
                return new CvdRiskBracketDecision();

            if (request.CvdPullbackLabel != "Riesgo de reversion")
                return new CvdRiskBracketDecision();

            var tp50Ticks = Math.Max(1, Math.Floor(request.TpTicks * 0.50m));
            var tp = request.Side == "BUY"
                ? request.Entry + tp50Ticks * request.TickSize
                : request.Entry - tp50Ticks * request.TickSize;

            return new CvdRiskBracketDecision
            {
                ShouldApply = true,
                Tp = tp,
                TpTicks = tp50Ticks
            };
        }

        public static CvdProfitLockUpdate UpdateCvdProfitLock(CvdProfitLockRequest request)
        {
            var bestMfeTicks = Math.Max(request.CurrentBestMfeTicks, request.MfeTicks);
            var update = new CvdProfitLockUpdate
            {
                Armed = false,
                BestMfeTicks = bestMfeTicks,
                LockTicks = request.CurrentLockTicks,
                ExitPrice = 0
            };

            if ((request.SpeedLabel == "normal speed" && !request.AllowNormalSpeed) || request.TpTicks <= 0 || request.TickSize <= 0)
                return update;

            var armTicks = request.TpTicks * 0.50m;
            if (bestMfeTicks < armTicks)
                return update;

            var trailingTicks = bestMfeTicks - request.PullbackTicks;
            var lockedTicks = Math.Min(request.TpTicks, Math.Max(armTicks, trailingTicks));
            var exitPrice = request.Side == "BUY"
                ? request.Entry + lockedTicks * request.TickSize
                : request.Entry - lockedTicks * request.TickSize;

            update.Armed = true;
            update.LockTicks = Math.Max(request.CurrentLockTicks, lockedTicks);
            update.ExitPrice = lockedTicks <= request.CurrentLockTicks ? 0 : exitPrice;
            return update;
        }

        public static bool HasCvdRiskExitProgress(CvdRiskExitProgressRequest request)
        {
            if (request.SpeedLabel == "normal speed" && !request.AllowNormalSpeed)
                return false;

            if (request.TpTicks <= 0 || request.TickSize <= 0)
                return false;

            if (!request.ProfitLockArmed || request.ProfitLockExitPrice == 0)
                return false;

            if (request.CvdPullbackLabel != "Riesgo de reversion")
                return false;

            if (request.ProfitLockBestMfeTicks <= request.ProfitLockTicks)
                return false;

            return CalculateCurrentFavorableTicks(
                request.Side,
                request.Entry,
                request.CurrentPrice,
                request.TickSize) <= request.ProfitLockTicks;
        }

        public static decimal CalculateCurrentFavorableTicks(
            string side,
            decimal entry,
            decimal currentPrice,
            decimal tickSize)
        {
            if (tickSize <= 0)
                return 0;

            if (side == "BUY")
                return Math.Max(0, Math.Round((currentPrice - entry) / tickSize, 0));

            if (side == "SELL")
                return Math.Max(0, Math.Round((entry - currentPrice) / tickSize, 0));

            return 0;
        }
    }
}
