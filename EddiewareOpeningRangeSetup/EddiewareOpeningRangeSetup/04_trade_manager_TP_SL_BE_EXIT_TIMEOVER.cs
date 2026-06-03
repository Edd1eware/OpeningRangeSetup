namespace ATAS.Indicators
{
    internal static class TradeManagerTpSlBeExit
    {
        private const decimal DefaultImbalanceRatio = 3m;
        private const decimal DefaultImbalanceVolumeFilter = 70m;

        public sealed class ImbalanceDebugInfo
        {
            public int MaxBuyStreak { get; set; }
            public int MaxSellStreak { get; set; }
        }

        public sealed class FootprintLevel
        {
            public decimal Price { get; set; }
            public decimal Bid { get; set; }
            public decimal Ask { get; set; }
        }

        public sealed class ImbalanceStop
        {
            public decimal ImbalancePrice { get; set; }
            public decimal StopPrice { get; set; }
        }

        public sealed class PanicMetrics
        {
            public decimal MfeTicks { get; set; }
            public decimal PullbackTicks { get; set; }
            public decimal AdverseMoveTicks { get; set; }
            public decimal AdverseSpeed { get; set; }
            public decimal AdversePrice { get; set; }
            public decimal PanicTriggerPrice { get; set; }
        }

        public static bool IsTimeOver(System.DateTime currentTime, bool hasOpenTrade, System.TimeSpan timeOverTime)
        {
            return currentTime.TimeOfDay >= timeOverTime && !hasOpenTrade;
        }

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
                : isNormalSpeed
                    ? request.MinTradeTicks
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
            var entryProfile = GetTradeClassification(request.SpeedLabel);
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
                    entryProfile = GetTradeClassification(request.SpeedLabel);
                    usesImbalanceStop = true;
                }
                else if (imbalanceRiskTicks <= request.HardMaxTradeTicks)
                {
                    sl = request.ImbalanceStopPrice.Value;
                    tp = request.Side == "BUY"
                        ? entry + request.HardMaxTradeTicks * request.TickSize
                        : entry - request.HardMaxTradeTicks * request.TickSize;
                    entryProfile = GetTradeClassification(request.SpeedLabel);
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
            decimal halfMfeExit = 0;

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

        public static ImbalanceDebugInfo CalculateImbalanceDebugInfo(
            dynamic candle,
            decimal imbalanceRatio,
            decimal imbalanceCompareMinVolume)
        {
            var info = new ImbalanceDebugInfo();
            var levels = GetSortedPriceLevels(candle);

            if (levels.Count < 2)
                return info;

            var buyStreak = 0;
            var sellStreak = 0;

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];
                var buyImbalance = false;
                var sellImbalance = false;

                if (i > 0)
                {
                    var lowerLevel = levels[i - 1];
                    buyImbalance = IsBuyImbalance(level, lowerLevel, imbalanceRatio, imbalanceCompareMinVolume);
                }

                if (i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];
                    sellImbalance = IsSellImbalance(level, upperLevel, imbalanceRatio, imbalanceCompareMinVolume);
                }

                if (buyImbalance)
                {
                    buyStreak++;
                    if (buyStreak > info.MaxBuyStreak)
                        info.MaxBuyStreak = buyStreak;
                }
                else
                {
                    buyStreak = 0;
                }

                if (sellImbalance)
                {
                    sellStreak++;
                    if (sellStreak > info.MaxSellStreak)
                        info.MaxSellStreak = sellStreak;
                }
                else
                {
                    sellStreak = 0;
                }
            }

            return info;
        }

        public static string ResolveAPlusStructureSide(ImbalanceState state, string setupSide)
        {
            if (string.IsNullOrWhiteSpace(setupSide))
                return "";

            setupSide = setupSide.Trim().ToUpperInvariant();

            if (setupSide == "BUY" && state.HasBuy3_ImbalanceGroup)
                return "BUY";

            if (setupSide == "SELL" && state.HasSell3_ImbalanceGroup)
                return "SELL";

            return "";
        }

        public static ImbalanceStop? TryGetImbalanceStop(
            dynamic candle,
            string side,
            decimal tickSize,
            decimal imbalanceRatio,
            decimal imbalanceCompareMinVolume)
        {
            var levels = GetSortedPriceLevels(candle);

            if (levels.Count < 2)
                return null;

            decimal? imbalancePrice = null;

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];

                if (side == "BUY" && i > 0)
                {
                    var lowerLevel = levels[i - 1];

                    if (IsBuyImbalance(level, lowerLevel, imbalanceRatio, imbalanceCompareMinVolume))
                    {
                        if (!imbalancePrice.HasValue || level.Price > imbalancePrice.Value)
                            imbalancePrice = level.Price;
                    }
                }

                if (side == "SELL" && i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    if (IsSellImbalance(level, upperLevel, imbalanceRatio, imbalanceCompareMinVolume))
                    {
                        if (!imbalancePrice.HasValue || level.Price < imbalancePrice.Value)
                            imbalancePrice = level.Price;
                    }
                }
            }

            if (!imbalancePrice.HasValue)
                return null;

            return new ImbalanceStop
            {
                ImbalancePrice = imbalancePrice.Value,
                StopPrice = side == "BUY"
                    ? imbalancePrice.Value - tickSize
                    : imbalancePrice.Value + tickSize
            };
        }

        private static bool IsBuyImbalance(
            FootprintLevel level,
            FootprintLevel lowerLevel,
            decimal imbalanceRatio,
            decimal imbalanceCompareMinVolume)
        {
            var ratio = NormalizeImbalanceRatio(imbalanceRatio);
            var volumeFilter = NormalizeImbalanceVolumeFilter(imbalanceCompareMinVolume);

            return level.Ask >= volumeFilter &&
                PassesDiagonalRatio(level.Ask, lowerLevel.Bid, ratio);
        }

        private static bool IsSellImbalance(
            FootprintLevel level,
            FootprintLevel upperLevel,
            decimal imbalanceRatio,
            decimal imbalanceCompareMinVolume)
        {
            var ratio = NormalizeImbalanceRatio(imbalanceRatio);
            var volumeFilter = NormalizeImbalanceVolumeFilter(imbalanceCompareMinVolume);

            return level.Bid >= volumeFilter &&
                PassesDiagonalRatio(level.Bid, upperLevel.Ask, ratio);
        }

        private static bool PassesDiagonalRatio(decimal dominantVolume, decimal diagonalVolume, decimal ratio)
        {
            if (dominantVolume <= 0)
                return false;

            if (diagonalVolume <= 0)
                return true;

            return dominantVolume >= diagonalVolume * ratio;
        }

        private static decimal NormalizeImbalanceRatio(decimal imbalanceRatio)
        {
            return imbalanceRatio <= 0 ? DefaultImbalanceRatio : imbalanceRatio;
        }

        private static decimal NormalizeImbalanceVolumeFilter(decimal imbalanceCompareMinVolume)
        {
            return imbalanceCompareMinVolume <= 0
                ? DefaultImbalanceVolumeFilter
                : imbalanceCompareMinVolume;
        }

        public static System.Collections.Generic.List<FootprintLevel> GetSortedPriceLevels(dynamic candle)
        {
            var result = new System.Collections.Generic.List<FootprintLevel>();

            try
            {
                foreach (var level in candle.GetAllPriceLevels())
                {
                    result.Add(new FootprintLevel
                    {
                        Price = System.Convert.ToDecimal(level.Price),
                        Bid = System.Convert.ToDecimal(level.Bid),
                        Ask = System.Convert.ToDecimal(level.Ask)
                    });
                }
            }
            catch
            {
                return result;
            }

            result.Sort((left, right) => left.Price.CompareTo(right.Price));

            return result;
        }

        public static decimal UpdateBestFavorablePrice(
            string side,
            decimal currentBestFavorablePrice,
            decimal candleHigh,
            decimal candleLow)
        {
            if (side == "BUY")
                return candleHigh > currentBestFavorablePrice ? candleHigh : currentBestFavorablePrice;

            if (currentBestFavorablePrice == 0 || candleLow < currentBestFavorablePrice)
                return candleLow;

            return currentBestFavorablePrice;
        }

        public static double NormalizeElapsedSeconds(
            double elapsedSeconds,
            string timingSource,
            decimal replaySpeedMultiplier)
        {
            if (elapsedSeconds <= 0 || elapsedSeconds > 300)
                return 1;

            if (timingSource == "UtcNow" || elapsedSeconds < 1)
                return elapsedSeconds * (double)NormalizeReplaySpeedMultiplier(replaySpeedMultiplier);

            return elapsedSeconds;
        }

        public static double NormalizeAdverseElapsedSeconds(
            double adverseElapsedSeconds,
            double fallbackElapsedSeconds,
            string timingSource,
            decimal replaySpeedMultiplier)
        {
            if (adverseElapsedSeconds <= 0 || adverseElapsedSeconds > 300)
                return fallbackElapsedSeconds;

            if (timingSource == "UtcNow" || adverseElapsedSeconds < 1)
                return adverseElapsedSeconds * (double)NormalizeReplaySpeedMultiplier(replaySpeedMultiplier);

            return adverseElapsedSeconds;
        }

        public static decimal NormalizeReplaySpeedMultiplier(decimal replaySpeedMultiplier)
        {
            return replaySpeedMultiplier <= 0 ? 1 : replaySpeedMultiplier;
        }

        public static PanicMetrics CalculatePanicMetrics(
            string side,
            decimal entry,
            decimal bestFavorablePrice,
            decimal lastManagePrice,
            decimal candleHigh,
            decimal candleLow,
            decimal elapsedSeconds,
            decimal adverseElapsedSeconds,
            decimal panicPullbackTicks,
            decimal tickSize)
        {
            var adversePrice = side == "BUY" ? candleLow : candleHigh;
            var mfeTicks = side == "BUY"
                ? RoundToTicks(bestFavorablePrice - entry, tickSize)
                : RoundToTicks(entry - bestFavorablePrice, tickSize);
            var pullbackTicks = side == "BUY"
                ? RoundToTicks(bestFavorablePrice - adversePrice, tickSize)
                : RoundToTicks(adversePrice - bestFavorablePrice, tickSize);
            var adverseMoveTicks = side == "BUY"
                ? RoundToTicks(System.Math.Max(0, lastManagePrice - adversePrice), tickSize)
                : RoundToTicks(System.Math.Max(0, adversePrice - lastManagePrice), tickSize);
            var adverseSpeed = System.Math.Max(
                adverseMoveTicks / elapsedSeconds,
                pullbackTicks / adverseElapsedSeconds);

            return new PanicMetrics
            {
                MfeTicks = mfeTicks,
                PullbackTicks = pullbackTicks,
                AdverseMoveTicks = adverseMoveTicks,
                AdverseSpeed = adverseSpeed,
                AdversePrice = adversePrice,
                PanicTriggerPrice = side == "BUY"
                    ? bestFavorablePrice - panicPullbackTicks * tickSize
                    : bestFavorablePrice + panicPullbackTicks * tickSize
            };
        }

        public static void GetPostEntryHitRange(
            bool isEntryBar,
            decimal candleHigh,
            decimal candleLow,
            decimal candleClose,
            decimal entryBarHighAtEntry,
            decimal entryBarLowAtEntry,
            out decimal hitHigh,
            out decimal hitLow)
        {
            if (!isEntryBar)
            {
                hitHigh = candleHigh;
                hitLow = candleLow;
                return;
            }

            hitHigh = candleClose;
            hitLow = candleClose;

            if (candleHigh > entryBarHighAtEntry)
                hitHigh = candleHigh;

            if (candleLow < entryBarLowAtEntry)
                hitLow = candleLow;
        }

        public static bool HasVwapFailed(string side, decimal close, decimal vwap)
        {
            return side == "BUY"
                ? close < vwap
                : close > vwap;
        }

        public static decimal GetSessionVwap(int bar, System.DateTime date, System.Func<int, dynamic> getCandle)
        {
            decimal cumPv = 0;
            decimal cumVol = 0;

            for (var i = bar; i >= 0; i--)
            {
                var candle = getCandle(i);

                if (candle.Time.Date != date)
                    break;

                var volume = candle.Volume;

                if (volume <= 0)
                    continue;

                var typical = (candle.High + candle.Low + candle.Close) / 3m;

                cumPv += typical * volume;
                cumVol += volume;
            }

            return cumVol <= 0 ? 0 : cumPv / cumVol;
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
            return GetTradeClassification(speedLabel);
        }

        public static string GetTradeClassification(string speedLabel)
        {
            if (speedLabel == "normal speed")
                return "SCALP_NORMAL";

            if (speedLabel == "A+ speed")
                return "POTENTIAL_RUNNER";

            return "UNCLASSIFIED";
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

        public static decimal RoundToTicks(decimal points, decimal tickSize)
        {
            return System.Math.Round(points / tickSize, 2);
        }
    }
}
