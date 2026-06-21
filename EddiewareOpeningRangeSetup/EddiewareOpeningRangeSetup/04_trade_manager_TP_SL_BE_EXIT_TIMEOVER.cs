namespace ATAS.Indicators
{
    internal static class TradeManagerTpSlBeExit
    {
        private const decimal NoImbalanceStopTicks = 60m;
        internal const decimal MinimumExecutableBracketTicks = 20m;

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
            public decimal NormalSpeedMaxTradeTicks { get; set; } = 120m;
            public decimal ValueAcceptanceMinTradeTicks { get; set; } = 30m;
            public decimal? ImbalanceStopPrice { get; set; }
            public decimal? NormalSpeedImbalanceStopPrice { get; set; }
            public decimal? ValueAcceptanceStopPrice { get; set; }
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
            public int Contracts { get; set; } = 2;
            public bool IsValid { get; set; } = true;
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
            public bool HitTp { get; set; }
            public bool HitSl { get; set; }
            public bool HitTpAndSlSameUpdate { get; set; }
        }

        public static TradePlan CreateInitialPlan(TradePlanRequest request)
        {
            var isAPlusSpeed = request.SpeedLabel == "A+ speed";
            var isNormalSpeed = request.SpeedLabel == "normal speed";
            var entry = request.Entry;

            if (isAPlusSpeed)
            {
                const decimal aPlusBracketTicks = 60m;
                var aPlusSl = request.Side == "BUY"
                    ? entry - aPlusBracketTicks * request.TickSize
                    : entry + aPlusBracketTicks * request.TickSize;
                var aPlusTp = request.Side == "BUY"
                    ? entry + aPlusBracketTicks * request.TickSize
                    : entry - aPlusBracketTicks * request.TickSize;

                return new TradePlan
                {
                    EntryProfile = GetTradeClassification(request.SpeedLabel),
                    Entry = entry,
                    Sl = aPlusSl,
                    Tp = aPlusTp,
                    SlTicks = aPlusBracketTicks,
                    TpTicks = aPlusBracketTicks,
                    UsesImbalanceStop = false,
                    IsAPlusSpeed = true,
                    IsNormalSpeed = false,
                    Contracts = 2,
                    IsValid = true
                };
            }

            var tradeTicks = isAPlusSpeed
                ? request.HardMaxTradeTicks
                : isNormalSpeed
                    ? request.MinTradeTicks
                    : request.Side == "BUY"
                    ? ClampTicks(RoundToTicks(entry - request.OrLow, request.TickSize), request.MinTradeTicks, request.MaxTradeTicks)
                    : ClampTicks(RoundToTicks(request.OrHigh - entry, request.TickSize), request.MinTradeTicks, request.MaxTradeTicks);

            var slTicks = request.MinTradeTicks;
            var sl = request.Side == "BUY"
                ? entry - slTicks * request.TickSize
                : entry + slTicks * request.TickSize;
            var tp = request.Side == "BUY"
                ? entry + tradeTicks * request.TickSize
                : entry - tradeTicks * request.TickSize;
            var entryProfile = GetTradeClassification(request.SpeedLabel);
            var usesImbalanceStop = false;
            var usesNormalSpeedImbalanceStop = false;

            if (request.ValueAcceptanceStopPrice.HasValue &&
                IsStopBehindEntry(request.Side, entry, request.ValueAcceptanceStopPrice.Value))
            {
                sl = request.ValueAcceptanceStopPrice.Value;
                slTicks = RoundToTicks(System.Math.Abs(entry - sl), request.TickSize);

                if (slTicks < request.ValueAcceptanceMinTradeTicks)
                {
                    slTicks = request.ValueAcceptanceMinTradeTicks;
                    sl = request.Side == "BUY"
                        ? entry - slTicks * request.TickSize
                        : entry + slTicks * request.TickSize;
                }

                if (slTicks > request.NormalSpeedMaxTradeTicks)
                {
                    return new TradePlan
                    {
                        EntryProfile = entryProfile,
                        Entry = entry,
                        Sl = sl,
                        Tp = 0,
                        SlTicks = slTicks,
                        TpTicks = 0,
                        UsesImbalanceStop = true,
                        IsAPlusSpeed = isAPlusSpeed,
                        IsNormalSpeed = isNormalSpeed,
                        Contracts = 0,
                        IsValid = false
                    };
                }

                tp = request.Side == "BUY"
                    ? entry + slTicks * request.TickSize
                    : entry - slTicks * request.TickSize;
                tradeTicks = slTicks;
                usesImbalanceStop = true;
                usesNormalSpeedImbalanceStop = true;
            }

            if (isNormalSpeed &&
                !usesNormalSpeedImbalanceStop &&
                request.NormalSpeedImbalanceStopPrice.HasValue &&
                IsStopBehindEntry(request.Side, entry, request.NormalSpeedImbalanceStopPrice.Value))
            {
                sl = request.NormalSpeedImbalanceStopPrice.Value;
                slTicks = RoundToTicks(System.Math.Abs(entry - sl), request.TickSize);

                if (slTicks > request.NormalSpeedMaxTradeTicks)
                {
                    return new TradePlan
                    {
                        EntryProfile = entryProfile,
                        Entry = entry,
                        Sl = sl,
                        Tp = 0,
                        SlTicks = slTicks,
                        TpTicks = 0,
                        UsesImbalanceStop = true,
                        IsAPlusSpeed = isAPlusSpeed,
                        IsNormalSpeed = isNormalSpeed,
                        Contracts = 0,
                        IsValid = false
                    };
                }

                tp = request.Side == "BUY"
                    ? entry + slTicks * request.TickSize
                    : entry - slTicks * request.TickSize;
                tradeTicks = slTicks;
                usesImbalanceStop = true;
                usesNormalSpeedImbalanceStop = true;
            }

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

            if (!usesImbalanceStop)
            {
                sl = request.Side == "BUY"
                    ? entry - NoImbalanceStopTicks * request.TickSize
                    : entry + NoImbalanceStopTicks * request.TickSize;
            }

            if (!usesNormalSpeedImbalanceStop)
            {
                tp = ClampExitDistance(
                    entry,
                    tp,
                    request.Side == "BUY" ? 1 : -1,
                    request.TickSize,
                    request.MinTradeTicks,
                    request.MaxTradeTicks,
                    request.EnforceMinExitDistance);
            }

            var plan = new TradePlan
            {
                EntryProfile = entryProfile,
                Entry = entry,
                Sl = sl,
                Tp = tp,
                SlTicks = RoundToTicks(System.Math.Abs(entry - sl), request.TickSize),
                TpTicks = RoundToTicks(System.Math.Abs(entry - tp), request.TickSize),
                UsesImbalanceStop = usesImbalanceStop,
                IsAPlusSpeed = isAPlusSpeed,
                IsNormalSpeed = isNormalSpeed,
                Contracts = isNormalSpeed && slTicks > request.MinTradeTicks ? 1 : 2,
                IsValid = true
            };

            EnforceMinimumOneToOneBracket(
                plan,
                request.Side,
                request.TickSize);

            return plan;
        }

        public static void EnforceMinimumOneToOneBracket(
            TradePlan plan,
            string side,
            decimal tickSize,
            decimal minimumTicks = MinimumExecutableBracketTicks)
        {
            if (plan == null || !plan.IsValid || tickSize <= 0 || minimumTicks <= 0)
                return;

            var currentSlTicks = RoundToTicks(
                System.Math.Abs(plan.Entry - plan.Sl),
                tickSize);
            var currentTpTicks = RoundToTicks(
                System.Math.Abs(plan.Entry - plan.Tp),
                tickSize);

            if (currentSlTicks >= minimumTicks && currentTpTicks >= minimumTicks)
            {
                plan.SlTicks = currentSlTicks;
                plan.TpTicks = currentTpTicks;
                return;
            }

            plan.SlTicks = minimumTicks;
            plan.TpTicks = minimumTicks;
            plan.Sl = side == "BUY"
                ? plan.Entry - minimumTicks * tickSize
                : plan.Entry + minimumTicks * tickSize;
            plan.Tp = side == "BUY"
                ? plan.Entry + minimumTicks * tickSize
                : plan.Entry - minimumTicks * tickSize;
        }

        public static TradeExitDecision EvaluateExit(TradeExitRequest request)
        {
            var mfeTicks = CalculateMfeTicks(
                request.Side,
                request.Entry,
                request.BestFavorablePrice,
                request.TickSize);
            decimal halfMfeExit = 0;

            var touchState = DetectExitTouches(
                request.Side,
                request.CandleHigh,
                request.CandleLow,
                request.Tp,
                request.Sl);
            var hitTp = touchState.HitTp;
            var hitSl = touchState.HitSl;

            if (!hitTp && !hitSl)
            {
                return new TradeExitDecision
                {
                    MfeTicks = mfeTicks,
                    HalfMfeExitPrice = halfMfeExit,
                    HitTp = false,
                    HitSl = false,
                    HitTpAndSlSameUpdate = false
                };
            }

            // OHLC/high-low data cannot establish which level traded first
            // when both are touched in the same update. Keep the historical
            // TP-first behavior for compatibility and export the ambiguity
            // so it can be visually validated in Replay.
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
                HalfMfeExitPrice = halfMfeExit,
                HitTp = hitTp,
                HitSl = hitSl,
                HitTpAndSlSameUpdate = hitTp && hitSl
            };
        }

        public sealed class ExitTouchState
        {
            public bool HitTp { get; set; }
            public bool HitSl { get; set; }
            public bool HitBoth => HitTp && HitSl;
        }

        public static ExitTouchState DetectExitTouches(
            string side,
            decimal high,
            decimal low,
            decimal tp,
            decimal sl)
        {
            return new ExitTouchState
            {
                HitTp = tp != 0 && IsTpHit(side, high, low, tp),
                HitSl = sl != 0 && IsSlHit(side, high, low, sl)
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
            decimal? stopPrice = null;

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];

                if (side == "BUY" && i > 0)
                {
                    var lowerLevel = levels[i - 1];

                    if (IsBuyStopImbalance(level, lowerLevel, imbalanceRatio))
                    {
                        if (!imbalancePrice.HasValue || level.Price < imbalancePrice.Value)
                        {
                            imbalancePrice = level.Price;
                            stopPrice = lowerLevel.Price;
                        }
                    }
                }

                if (side == "SELL" && i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    if (IsSellStopImbalance(level, upperLevel, imbalanceRatio))
                    {
                        if (!imbalancePrice.HasValue || level.Price > imbalancePrice.Value)
                        {
                            imbalancePrice = level.Price;
                            stopPrice = upperLevel.Price;
                        }
                    }
                }
            }

            if (!imbalancePrice.HasValue || !stopPrice.HasValue)
                return null;

            return new ImbalanceStop
            {
                ImbalancePrice = imbalancePrice.Value,
                StopPrice = stopPrice.Value
            };
        }

        private static bool IsBuyImbalance(
            FootprintLevel level,
            FootprintLevel lowerLevel,
            decimal imbalanceRatio,
            decimal imbalanceCompareMinVolume)
        {
            return level.Ask >= imbalanceCompareMinVolume &&
                level.Ask >= lowerLevel.Bid * imbalanceRatio;
        }

        private static bool IsBuyStopImbalance(
            FootprintLevel level,
            FootprintLevel lowerLevel,
            decimal imbalanceRatio)
        {
            return lowerLevel.Bid > 0 &&
                level.Ask >= lowerLevel.Bid * imbalanceRatio;
        }

        private static bool IsSellImbalance(
            FootprintLevel level,
            FootprintLevel upperLevel,
            decimal imbalanceRatio,
            decimal imbalanceCompareMinVolume)
        {
            return level.Bid >= imbalanceCompareMinVolume &&
                level.Bid >= upperLevel.Ask * imbalanceRatio;
        }

        private static bool IsSellStopImbalance(
            FootprintLevel level,
            FootprintLevel upperLevel,
            decimal imbalanceRatio)
        {
            return upperLevel.Ask > 0 &&
                level.Bid >= upperLevel.Ask * imbalanceRatio;
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

        private static bool IsStopBehindEntry(string side, decimal entry, decimal stop)
        {
            return side == "BUY"
                ? stop < entry
                : stop > entry;
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
