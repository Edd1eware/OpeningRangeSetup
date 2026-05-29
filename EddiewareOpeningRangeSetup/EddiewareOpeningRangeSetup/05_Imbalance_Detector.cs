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
                Sell3_ImbalanceGroupPrice = current.Sell3_ImbalanceGroupPrice,
                HasBuy3_Separated = current.HasBuy3_Separated,
                HasSell3_Separated = current.HasSell3_Separated,
                BuyImbalanceCount = current.BuyImbalanceCount,
                SellImbalanceCount = current.SellImbalanceCount
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
                    state.BuyImbalanceCount++;
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
                    state.SellImbalanceCount++;
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

            // 3+ imbalances sueltos en toda la vela (independiente de si estan pegados).
            state.HasBuy3_Separated = state.BuyImbalanceCount >= 3;
            state.HasSell3_Separated = state.SellImbalanceCount >= 3;

            state.Score = CalculateScore(state, request.Side);
            return state;
        }

        // Devuelve TODOS los niveles con imbalance de la vela (para pintarlos en el grafico).
        public static List<ImbalanceLevel> DetectLevels(dynamic candle, ImbalanceDetectorRequest request)
        {
            var result = new List<ImbalanceLevel>();
            var levels = GetSortedPriceLevels(candle);

            for (var i = 0; i < levels.Count; i++)
            {
                var level = levels[i];

                if (i > 0)
                {
                    var lowerLevel = levels[i - 1];

                    // BUY diagonal: Ask actual vs Bid inferior.
                    if (lowerLevel.Bid >= request.CompareMinVolume &&
                        level.Ask >= lowerLevel.Bid * request.Ratio)
                    {
                        result.Add(new ImbalanceLevel { Price = level.Price, IsBuy = true });
                    }
                }

                if (i < levels.Count - 1)
                {
                    var upperLevel = levels[i + 1];

                    // SELL diagonal: Bid actual vs Ask superior.
                    if (upperLevel.Ask >= request.CompareMinVolume &&
                        level.Bid >= upperLevel.Ask * request.Ratio)
                    {
                        result.Add(new ImbalanceLevel { Price = level.Price, IsBuy = false });
                    }
                }
            }

            return result;
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
                // 3+ pegados => 2 pts; si no, 3+ separados => 1 pt (escala, no se suman).
                if (state.HasBuy3_ImbalanceGroup)
                    score += 2;
                else if (state.HasBuy3_Separated)
                    score += 1;
            }
            else if (side == "SELL")
            {
                if (state.HasSell3_ImbalanceGroup)
                    score += 2;
                else if (state.HasSell3_Separated)
                    score += 1;
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

    internal sealed class ImbalanceLevel
    {
        public decimal Price { get; set; }
        public bool IsBuy { get; set; }
    }

    internal sealed class ImbalanceDetectorRequest
    {
        public string Side { get; set; } = "";
        public decimal Ratio { get; set; } = 3m;

        // Gate de volumen sobre el lado MENOR de la diagonal (configurable).
        // Evita imbalances falsos por division con volumenes minimos. Subelo si quieres mas exigencia.
        public decimal CompareMinVolume { get; set; } = 5m;
    }

    internal sealed class ImbalanceState
    {
        public bool HasBuy_ImbalanceUnTouched { get; set; }
        public bool HasSell_ImbalanceUnTouched { get; set; }

        // 3+ imbalances SEPARADOS (conteo total en la vela, no importa si estan pegados) => 1 punto.
        public bool HasBuy3_Separated { get; set; }
        public bool HasSell3_Separated { get; set; }

        // 3+ imbalances PEGADOS (racha en niveles contiguos) => 2 puntos.
        public bool HasBuy3_ImbalanceGroup { get; set; }
        public bool HasSell3_ImbalanceGroup { get; set; }

        // Conteo total de imbalances diagonales detectados en la vela.
        public int BuyImbalanceCount { get; set; }
        public int SellImbalanceCount { get; set; }
        public decimal? Buy_ImbalanceUnTouchedPrice { get; set; }
        public decimal? Sell_ImbalanceUnTouchedPrice { get; set; }
        public decimal? Buy3_ImbalanceGroupPrice { get; set; }
        public decimal? Sell3_ImbalanceGroupPrice { get; set; }
        public int Score { get; set; }
    }
}
