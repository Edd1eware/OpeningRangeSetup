namespace ATAS.Indicators
{
    internal static class TradeManagerTpSlBeExit
    {
        public sealed class TradePlanRequest
        {
            public string Side { get; set; } = "";
            public string SpeedLabel { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal OrLow { get; set; }
            public decimal OrHigh { get; set; }
            public decimal TickSize { get; set; }
            public decimal MinTradeTicks { get; set; }
            public decimal MaxTradeTicks { get; set; }
            public decimal HardMaxTradeTicks { get; set; }
            public decimal APlusStopTicks { get; set; }
            public decimal? ImbalanceStopPrice { get; set; }
            public bool CapSellStopAtOrHigh { get; set; }
            public bool EnforceMinExitDistance { get; set; }
        }

        public sealed class TradePlan
        {
            public string EntryProfile { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal Sl { get; set; }
            public decimal Tp { get; set; }
            public decimal SlTicks { get; set; }
            public decimal TpTicks { get; set; }
            public bool UsesImbalanceStop { get; set; }
            public bool IsAPlusSpeed { get; set; }
            public bool IsNormalSpeed { get; set; }
        }

        public sealed class TradeExitRequest
        {
            public string Side { get; set; } = "";
            public string SpeedLabel { get; set; } = "";
            public decimal Entry { get; set; }
            public decimal Sl { get; set; }
            public decimal Tp { get; set; }
            public decimal SlTicks { get; set; }
            public decimal TpTicks { get; set; }
            public decimal BestFavorablePrice { get; set; }
            public decimal CandleHigh { get; set; }
            public decimal CandleLow { get; set; }
            public decimal CurrentPrice { get; set; }
            public decimal HalfMfeExitMinMfeTicks { get; set; }
            public decimal FastExitMinMfeTicks { get; set; }
            public decimal FastExitPullbackTicks { get; set; }
            public decimal FastExitAdverseSpeedTicksPerSecond { get; set; }
            public decimal AdverseSpeedTicksPerSecond { get; set; }
            public decimal TickSize { get; set; }
        }

        public sealed class TradeExitDecision
        {
            public bool IsClosed { get; set; }
            public string Result { get; set; } = "OPEN";
            public decimal ExitPrice { get; set; }
            public decimal ResultTicks { get; set; }
            public decimal MfeTicks { get; set; }
            public decimal HalfMfeExitPrice { get; set; }
            public bool IsHalfMfeExit { get; set; }
            public bool IsFastExit { get; set; }
        }

        public static TradePlan CreateInitialPlan(TradePlanRequest request)
        {
            var isAPlusSpeed = request.SpeedLabel == "A+ speed";
            var isNormalSpeed = request.SpeedLabel == "normal speed";
            var entry = request.Entry;
            var tradeTicks = isAPlusSpeed
                ? request.HardMaxTradeTicks
                : request.Side == "BUY"
                    ? ClampTicks(RoundToTicks(entry - request.OrLow, request.TickSize), request.MinTradeTicks, request.MaxTradeTicks)
                    : ClampTicks(RoundToTicks(request.OrHigh - entry, request.TickSize), request.MinTradeTicks, request.MaxTradeTicks);

            var slTicks = isAPlusSpeed ? request.APlusStopTicks : request.MinTradeTicks;
            var sl = request.Side == "BUY"
                ? entry - slTicks * request.TickSize
                : entry + slTicks * request.TickSize;
            var tp = request.Side == "BUY"
                ? entry + tradeTicks * request.TickSize
                : entry - tradeTicks * request.TickSize;
            var entryProfile = isNormalSpeed ? $"{request.Side}1" : request.Side;
            var usesImbalanceStop = false;

            if (!isAPlusSpeed && !isNormalSpeed && request.ImbalanceStopPrice.HasValue)
            {
                var imbalanceRiskTicks = RoundToTicks(System.Math.Abs(entry - request.ImbalanceStopPrice.Value), request.TickSize);

                if (imbalanceRiskTicks <= 60)
                {
                    sl = request.ImbalanceStopPrice.Value;
                    tp = request.Side == "BUY"
                        ? entry + 60m * request.TickSize
                        : entry - 60m * request.TickSize;
                    entryProfile = $"{request.Side} 2";
                    usesImbalanceStop = true;
                }
                else if (imbalanceRiskTicks <= request.HardMaxTradeTicks)
                {
                    sl = request.ImbalanceStopPrice.Value;
                    tp = request.Side == "BUY"
                        ? entry + request.HardMaxTradeTicks * request.TickSize
                        : entry - request.HardMaxTradeTicks * request.TickSize;
                    entryProfile = $"{request.Side} 1";
                    usesImbalanceStop = true;
                }
            }

            if (!usesImbalanceStop && request.CapSellStopAtOrHigh && request.Side == "SELL" && sl > request.OrHigh)
                sl = request.OrHigh;

            if (!usesImbalanceStop)
                sl = ClampExitDistance(
                    entry,
                    sl,
                    request.Side == "BUY" ? -1 : 1,
                    request.TickSize,
                    request.MinTradeTicks,
                    request.MaxTradeTicks,
                    request.EnforceMinExitDistance);

            tp = ClampExitDistance(
                entry,
                tp,
                request.Side == "BUY" ? 1 : -1,
                request.TickSize,
                request.MinTradeTicks,
                request.MaxTradeTicks,
                request.EnforceMinExitDistance);

            return new TradePlan
            {
                EntryProfile = entryProfile,
                Entry = entry,
                Sl = sl,
                Tp = tp,
                SlTicks = RoundToTicks(System.Math.Abs(entry - sl), request.TickSize),
                TpTicks = RoundToTicks(System.Math.Abs(entry - tp), request.TickSize),
                UsesImbalanceStop = usesImbalanceStop,
                IsAPlusSpeed = isAPlusSpeed,
                IsNormalSpeed = isNormalSpeed
            };
        }

        public static TradeExitDecision EvaluateExit(TradeExitRequest request)
        {
            var mfeTicks = CalculateMfeTicks(
                request.Side,
                request.Entry,
                request.BestFavorablePrice,
                request.TickSize);
            var pullbackTicks = CalculatePullbackTicks(
                request.Side,
                request.BestFavorablePrice,
                request.CandleHigh,
                request.CandleLow,
                request.TickSize);

            if (request.SpeedLabel != "A+ speed" &&
                mfeTicks >= request.FastExitMinMfeTicks &&
                pullbackTicks >= request.FastExitPullbackTicks &&
                (request.AdverseSpeedTicksPerSecond >= request.FastExitAdverseSpeedTicksPerSecond ||
                 IsSlHit(request.Side, request.CandleHigh, request.CandleLow, request.Sl)))
            {
                var fastExitPrice = request.Side == "BUY"
                    ? request.BestFavorablePrice - request.FastExitPullbackTicks * request.TickSize
                    : request.BestFavorablePrice + request.FastExitPullbackTicks * request.TickSize;
                var resultTicks = TradeResultTicks(
                    "EXIT",
                    request.Entry,
                    request.TpTicks,
                    request.SlTicks,
                    fastExitPrice,
                    request.TickSize);

                if (resultTicks > 0)
                {
                    return new TradeExitDecision
                    {
                        IsClosed = false,
                        MfeTicks = mfeTicks,
                        HalfMfeExitPrice = fastExitPrice,
                        IsFastExit = true
                    };
                }
            }

            if (TryCalculateHalfMfeExit(
                    request.Side,
                    request.SpeedLabel,
                    request.Entry,
                    request.BestFavorablePrice,
                    request.HalfMfeExitMinMfeTicks,
                    request.TickSize,
                    out var halfMfeExit,
                    out mfeTicks))
            {
                var adversePrice = request.CurrentPrice;

                if (IsHalfMfeExitTouched(request.Side, adversePrice, halfMfeExit))
                {
                    return new TradeExitDecision
                    {
                        IsClosed = true,
                        Result = "EXIT",
                        ExitPrice = halfMfeExit,
                        ResultTicks = TradeResultTicks(
                            "EXIT",
                            request.Entry,
                            request.TpTicks,
                            request.SlTicks,
                            halfMfeExit,
                            request.TickSize),
                        MfeTicks = mfeTicks,
                        HalfMfeExitPrice = halfMfeExit,
                        IsHalfMfeExit = true
                    };
                }
            }

            var hitTp = IsTpHit(request.Side, request.CandleHigh, request.CandleLow, request.Tp);
            var hitSl = IsSlHit(request.Side, request.CandleHigh, request.CandleLow, request.Sl);

            if (!hitTp && !hitSl)
            {
                return new TradeExitDecision
                {
                    MfeTicks = mfeTicks,
                    HalfMfeExitPrice = halfMfeExit
                };
            }

            var result = hitTp ? "TP" : "SL";
            var exitPrice = hitTp ? request.Tp : request.Sl;

            return new TradeExitDecision
            {
                IsClosed = true,
                Result = result,
                ExitPrice = exitPrice,
                ResultTicks = TradeResultTicks(
                    result,
                    request.Entry,
                    request.TpTicks,
                    request.SlTicks,
                    exitPrice,
                    request.TickSize),
                MfeTicks = mfeTicks,
                HalfMfeExitPrice = halfMfeExit
            };
        }

        public static decimal CalculateHalfMfeExit(string side, decimal entry, decimal bestFavorablePrice)
        {
            return side == "BUY"
                ? entry + (bestFavorablePrice - entry) / 2m
                : entry - (entry - bestFavorablePrice) / 2m;
        }

        public static bool TryCalculateHalfMfeExit(
            string side,
            string speedLabel,
            decimal entry,
            decimal bestFavorablePrice,
            decimal minMfeTicks,
            decimal tickSize,
            out decimal halfMfeExit,
            out decimal mfeTicks)
        {
            halfMfeExit = 0;
            mfeTicks = 0;

            if (speedLabel == "A+ speed")
                return false;

            mfeTicks = side == "BUY"
                ? RoundToTicks(bestFavorablePrice - entry, tickSize)
                : RoundToTicks(entry - bestFavorablePrice, tickSize);

            if (mfeTicks < minMfeTicks)
                return false;

            halfMfeExit = CalculateHalfMfeExit(side, entry, bestFavorablePrice);
            return true;
        }

        public static decimal CalculateMfeTicks(string side, decimal entry, decimal bestFavorablePrice, decimal tickSize)
        {
            return side == "BUY"
                ? RoundToTicks(bestFavorablePrice - entry, tickSize)
                : RoundToTicks(entry - bestFavorablePrice, tickSize);
        }

        public static decimal CalculatePullbackTicks(
            string side,
            decimal bestFavorablePrice,
            decimal candleHigh,
            decimal candleLow,
            decimal tickSize)
        {
            var pullbackPoints = side == "BUY"
                ? bestFavorablePrice - candleLow
                : candleHigh - bestFavorablePrice;

            return System.Math.Max(0, RoundToTicks(pullbackPoints, tickSize));
        }

        public static bool IsHalfMfeExitTouched(string side, decimal adversePrice, decimal halfMfeExit)
        {
            return side == "BUY"
                ? adversePrice <= halfMfeExit
                : adversePrice >= halfMfeExit;
        }

        public static bool IsTpHit(string side, decimal high, decimal low, decimal tp)
        {
            return side == "BUY"
                ? high >= tp
                : low <= tp;
        }

        public static bool IsSlHit(string side, decimal high, decimal low, decimal sl)
        {
            return side == "BUY"
                ? low <= sl
                : high >= sl;
        }

        public static bool IsExitHit(string side, decimal high, decimal low, decimal exit)
        {
            return side == "BUY"
                ? low <= exit
                : high >= exit;
        }

        public static decimal TradeResultTicks(string result, decimal entry, decimal tpTicks, decimal slTicks, decimal exitPrice, decimal tickSize)
        {
            if (result == "TP")
                return tpTicks;

            if (result == "SL")
                return -slTicks;

            if (result == "EXIT" && exitPrice != 0)
                return RoundToTicks(System.Math.Abs(exitPrice - entry), tickSize);

            if (result == "BE")
                return 0;

            return 0;
        }

        public static string GetEntryProfile(string side, string speedLabel)
        {
            return speedLabel == "normal speed" ? $"{side}1" : side;
        }

        private static decimal ClampTicks(decimal ticks, decimal minTradeTicks, decimal maxTradeTicks)
        {
            if (ticks < minTradeTicks)
                return minTradeTicks;

            if (ticks > maxTradeTicks)
                return maxTradeTicks;

            return ticks;
        }

        private static decimal ClampExitDistance(
            decimal entry,
            decimal exit,
            int direction,
            decimal tickSize,
            decimal minTradeTicks,
            decimal maxTradeTicks,
            bool enforceMinDistance)
        {
            var currentDistance = System.Math.Abs(exit - entry);
            var minDistance = minTradeTicks * tickSize;
            var maxDistance = maxTradeTicks * tickSize;

            if ((!enforceMinDistance || currentDistance >= minDistance) && currentDistance <= maxDistance)
                return exit;

            if (enforceMinDistance && currentDistance < minDistance)
                return entry + direction * minDistance;

            return entry + direction * maxDistance;
        }

        private static decimal RoundToTicks(decimal points, decimal tickSize)
        {
            return System.Math.Round(points / tickSize, 2);
        }
    }
}
