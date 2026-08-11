using System;
using System.Collections.Generic;

namespace ATAS.Indicators
{
    internal static class ImbalanceDetector
    {
        private const int MinAPlusImbalanceGroup = 3;

        public static ImbalanceState DetectForScore(dynamic currentCandle, dynamic previousCandle, ImbalanceDetectorRequest request)
        {
            var current = Detect(currentCandle, request);
            var previous = previousCandle == null ? new ImbalanceState() : Detect(previousCandle, request);
            var state = new ImbalanceState
            {
                HasBuy3_ImbalanceGroup = current.HasBuy3_ImbalanceGroup,
                HasSell3_ImbalanceGroup = current.HasSell3_ImbalanceGroup,
                Buy3_ImbalanceGroupPrice = current.Buy3_ImbalanceGroupPrice,
                Sell3_ImbalanceGroupPrice = current.Sell3_ImbalanceGroupPrice,
                BuyImbalanceCount = current.BuyImbalanceCount,
                SellImbalanceCount = current.SellImbalanceCount,
                MaxBuyImbalanceGroup = current.MaxBuyImbalanceGroup,
                MaxSellImbalanceGroup = current.MaxSellImbalanceGroup,
                MaxBuyImbalanceGroupPrice = current.MaxBuyImbalanceGroupPrice,
                MaxSellImbalanceGroupPrice = current.MaxSellImbalanceGroupPrice,
                BuyImbalancePrices = new List<decimal>(current.BuyImbalancePrices),
                SellImbalancePrices = new List<decimal>(current.SellImbalancePrices)
            };

            if (previous.HasBuy_ImbalanceUnTouched &&
                previous.Buy_ImbalanceUnTouchedPrice.HasValue &&
                !IsTouched(currentCandle, previous.Buy_ImbalanceUnTouchedPrice.Value))
            {
                state.HasBuy_ImbalanceUnTouched = true;
                state.Buy_ImbalanceUnTouchedPrice = previous.Buy_ImbalanceUnTouchedPrice;
            }

            if (previous.HasSell_ImbalanceUnTouched &&
                previous.Sell_ImbalanceUnTouchedPrice.HasValue &&
                !IsTouched(currentCandle, previous.Sell_ImbalanceUnTouchedPrice.Value))
            {
                state.HasSell_ImbalanceUnTouched = true;
                state.Sell_ImbalanceUnTouchedPrice = previous.Sell_ImbalanceUnTouchedPrice;
            }

            AbsorptionDetector.ApplyAPlusStructure(state, request.Side);
            state.Score = AbsorptionDetector.CalculateImbalanceScore(state, request.Side);
            return state;
        }

        public static ImbalanceState Detect(dynamic candle, ImbalanceDetectorRequest request)
        {
            var levels = GetSortedPriceLevels(candle);
            var state = new ImbalanceState();

            if (levels.Count < 2)
                return state;

            var buyStreak = 0;
            var sellStreak = 0;
            var inferredTickSize = InferTickSize(levels);
            decimal? lastBuyImbalancePrice = null;
            decimal? lastSellImbalancePrice = null;

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];
                var buyImbalance = false;
                var sellImbalance = false;

                if (i > 0)
                {
                    var lowerLevel = levels[i - 1];

                    // BUY diagonal: Ask actual vs Bid inferior.
                    buyImbalance = IsBuyImbalance(level, lowerLevel, request);
                }

                if (i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    // SELL diagonal: Bid actual vs Ask superior. Example: 58 x 17 => 58 >= 17 * ratio.
                    sellImbalance = IsSellImbalance(level, upperLevel, request);
                }

                if (buyImbalance)
                {
                    state.BuyImbalanceCount++;
                    state.BuyImbalancePrices.Add(level.Price);
                    state.HasBuy_ImbalanceUnTouched = true;
                    state.Buy_ImbalanceUnTouchedPrice = level.Price;
                    buyStreak = IsNextAdjacentImbalance(lastBuyImbalancePrice, level.Price, inferredTickSize)
                        ? buyStreak + 1
                        : 1;
                    lastBuyImbalancePrice = level.Price;
                    if (buyStreak > state.MaxBuyImbalanceGroup)
                    {
                        state.MaxBuyImbalanceGroup = buyStreak;
                        state.MaxBuyImbalanceGroupPrice = level.Price;
                    }

                    if (buyStreak >= MinAPlusImbalanceGroup)
                    {
                        state.HasBuy3_ImbalanceGroup = true;
                        state.Buy3_ImbalanceGroupPrice = level.Price;
                    }
                }
                else
                {
                    buyStreak = 0;
                    lastBuyImbalancePrice = null;
                }

                if (sellImbalance)
                {
                    state.SellImbalanceCount++;
                    state.SellImbalancePrices.Add(level.Price);
                    state.HasSell_ImbalanceUnTouched = true;
                    state.Sell_ImbalanceUnTouchedPrice = level.Price;
                    sellStreak = IsNextAdjacentImbalance(lastSellImbalancePrice, level.Price, inferredTickSize)
                        ? sellStreak + 1
                        : 1;
                    lastSellImbalancePrice = level.Price;
                    if (sellStreak > state.MaxSellImbalanceGroup)
                    {
                        state.MaxSellImbalanceGroup = sellStreak;
                        state.MaxSellImbalanceGroupPrice = level.Price;
                    }

                    if (sellStreak >= MinAPlusImbalanceGroup)
                    {
                        state.HasSell3_ImbalanceGroup = true;
                        state.Sell3_ImbalanceGroupPrice = level.Price;
                    }
                }
                else
                {
                    sellStreak = 0;
                    lastSellImbalancePrice = null;
                }
            }

            AbsorptionDetector.ApplyAPlusStructure(state, request.Side);
            state.Score = AbsorptionDetector.CalculateImbalanceScore(state, request.Side);
            return state;
        }

        private static bool IsTouched(dynamic candle, decimal price)
        {
            try
            {
                return candle.Low <= price && candle.High >= price;
            }
            catch
            {
                return true;
            }
        }

        private static bool IsBuyImbalance(FootprintLevel level, FootprintLevel lowerLevel, ImbalanceDetectorRequest request)
        {
            return level.Ask >= request.CompareMinVolume &&
                level.Ask >= lowerLevel.Bid * request.Ratio;
        }

        private static bool IsSellImbalance(FootprintLevel level, FootprintLevel upperLevel, ImbalanceDetectorRequest request)
        {
            return level.Bid >= request.CompareMinVolume &&
                level.Bid >= upperLevel.Ask * request.Ratio;
        }

        private static bool IsNextAdjacentImbalance(decimal? previousPrice, decimal currentPrice, decimal tickSize)
        {
            if (!previousPrice.HasValue)
                return false;

            if (tickSize <= 0)
                return true;

            var distance = Math.Abs(currentPrice - previousPrice.Value);
            return distance > 0 && distance <= tickSize * 1.5m;
        }

        private static decimal InferTickSize(List<FootprintLevel> levels)
        {
            decimal tickSize = 0;

            for (var i = 1; i < levels.Count; i++)
            {
                var distance = Math.Abs(levels[i].Price - levels[i - 1].Price);

                if (distance <= 0)
                    continue;

                if (tickSize == 0 || distance < tickSize)
                    tickSize = distance;
            }

            return tickSize;
        }

        private static List<FootprintLevel> GetSortedPriceLevels(dynamic candle)
        {
            var result = new List<FootprintLevel>();

            try
            {
                foreach (var level in candle.GetAllPriceLevels())
                {
                    result.Add(new FootprintLevel
                    {
                        Price = Convert.ToDecimal(level.Price),
                        Bid = Convert.ToDecimal(level.Bid),
                        Ask = Convert.ToDecimal(level.Ask)
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

        private sealed class FootprintLevel
        {
            public decimal Price { get; set; }
            public decimal Bid { get; set; }
            public decimal Ask { get; set; }
        }
    }

    internal sealed class ImbalanceDetectorRequest
    {
        public string Side { get; set; } = "";
        public decimal Ratio { get; set; } = 3m;
        public decimal CompareMinVolume { get; set; } = 70m;
    }

    internal sealed class ImbalanceState
    {
        public bool HasBuy_ImbalanceUnTouched { get; set; }
        public bool HasSell_ImbalanceUnTouched { get; set; }
        public bool HasBuy3_ImbalanceGroup { get; set; }
        public bool HasSell3_ImbalanceGroup { get; set; }
        public decimal? Buy_ImbalanceUnTouchedPrice { get; set; }
        public decimal? Sell_ImbalanceUnTouchedPrice { get; set; }
        public decimal? Buy3_ImbalanceGroupPrice { get; set; }
        public decimal? Sell3_ImbalanceGroupPrice { get; set; }
        public bool HasAPlusStructure { get; set; }
        public string APlusStructureSide { get; set; } = "";
        public decimal? APlusStructurePrice { get; set; }
        public int MaxBuyImbalanceGroup { get; set; }
        public int MaxSellImbalanceGroup { get; set; }
        public decimal? MaxBuyImbalanceGroupPrice { get; set; }
        public decimal? MaxSellImbalanceGroupPrice { get; set; }
        public int BuyImbalanceCount { get; set; }
        public int SellImbalanceCount { get; set; }
        public List<decimal> BuyImbalancePrices { get; set; } = new List<decimal>();
        public List<decimal> SellImbalancePrices { get; set; } = new List<decimal>();
        public int Score { get; set; }
    }
}
