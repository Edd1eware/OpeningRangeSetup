using System;
using System.Collections.Generic;

namespace ATAS.Indicators
{
    internal static class ImbalanceDetector
    {
        public static ImbalanceState DetectForScore(dynamic currentCandle, dynamic previousCandle, ImbalanceDetectorRequest request)
        {
            var current = Detect(currentCandle, request);
            var previous = previousCandle == null ? new ImbalanceState() : Detect(previousCandle, request);
            var state = new ImbalanceState
            {
                HasBuy3_ImbalanceGroup = current.HasBuy3_ImbalanceGroup,
                HasSell3_ImbalanceGroup = current.HasSell3_ImbalanceGroup,
                Buy3_ImbalanceGroupPrice = current.Buy3_ImbalanceGroupPrice,
                Sell3_ImbalanceGroupPrice = current.Sell3_ImbalanceGroupPrice
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

            state.Score = CalculateScore(state, request.Side);
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

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];
                var buyImbalance = false;
                var sellImbalance = false;

                if (i > 0)
                {
                    var lowerLevel = levels[i - 1];

                    // BUY diagonal: Ask actual vs Bid inferior.
                    buyImbalance =
                        lowerLevel.Bid >= request.CompareMinVolume &&
                        level.Ask >= lowerLevel.Bid * request.Ratio;
                }

                if (i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    // SELL diagonal: Bid actual vs Ask superior. Example: 58 x 17 => 58 >= 17 * ratio.
                    sellImbalance =
                        upperLevel.Ask >= request.CompareMinVolume &&
                        level.Bid >= upperLevel.Ask * request.Ratio;
                }

                if (buyImbalance)
                {
                    state.HasBuy_ImbalanceUnTouched = true;
                    state.Buy_ImbalanceUnTouchedPrice = level.Price;
                    buyStreak++;

                    if (buyStreak >= 3)
                    {
                        state.HasBuy3_ImbalanceGroup = true;
                        state.Buy3_ImbalanceGroupPrice = level.Price;
                    }
                }
                else
                {
                    buyStreak = 0;
                }

                if (sellImbalance)
                {
                    state.HasSell_ImbalanceUnTouched = true;
                    state.Sell_ImbalanceUnTouchedPrice = level.Price;
                    sellStreak++;

                    if (sellStreak >= 3)
                    {
                        state.HasSell3_ImbalanceGroup = true;
                        state.Sell3_ImbalanceGroupPrice = level.Price;
                    }
                }
                else
                {
                    sellStreak = 0;
                }
            }

            state.Score = CalculateScore(state, request.Side);
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

        private static int CalculateScore(ImbalanceState state, string side)
        {
            var score = 0;

            if (side == "BUY")
            {
                if (state.HasBuy_ImbalanceUnTouched)
                    score += 1;

                if (state.HasBuy3_ImbalanceGroup)
                    score += 2;
            }
            else if (side == "SELL")
            {
                if (state.HasSell_ImbalanceUnTouched)
                    score += 1;

                if (state.HasSell3_ImbalanceGroup)
                    score += 2;
            }

            return score;
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
        public decimal CompareMinVolume { get; set; } = 5m;
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
        public int Score { get; set; }
    }
}
