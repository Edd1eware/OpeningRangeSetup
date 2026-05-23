namespace ATAS.Indicators
{
    internal static class TradeManagerTpSlBeExit
    {
        public static decimal CalculateHalfMfeExit(string side, decimal entry, decimal bestFavorablePrice)
        {
            return side == "BUY"
                ? entry + (bestFavorablePrice - entry) / 2m
                : entry - (entry - bestFavorablePrice) / 2m;
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
    }
}
