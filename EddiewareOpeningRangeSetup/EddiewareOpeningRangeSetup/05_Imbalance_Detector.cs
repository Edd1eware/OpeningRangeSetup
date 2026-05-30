using System;
using System.Collections.Generic;

namespace ATAS.Indicators
{
    internal static class ImbalanceDetector
    {
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

                    buyImbalance =
                        lowerLevel.Bid >= request.CompareMinVolume &&
                        level.Ask >= lowerLevel.Bid * request.Ratio;
                }

                if (i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    sellImbalance =
                        upperLevel.Ask >= request.CompareMinVolume &&
                        level.Bid >= upperLevel.Ask * request.Ratio;
                }

                if (buyImbalance)
                {
                    state.HasBuy_ImbalanceUnTouched = true;
                    buyStreak++;

                    if (buyStreak >= 3)
                        state.HasBuy3_ImbalanceGroup = true;
                }
                else
                {
                    buyStreak = 0;
                }

                if (sellImbalance)
                {
                    state.HasSell_ImbalanceUnTouched = true;
                    sellStreak++;

                    if (sellStreak >= 3)
                        state.HasSell3_ImbalanceGroup = true;
                }
                else
                {
                    sellStreak = 0;
                }
            }

            state.Score = CalculateScore(state, request.Side);
            return state;
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
        public int Score { get; set; }
    }
}
