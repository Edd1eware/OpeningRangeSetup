namespace ATAS.Indicators
{
    internal static class AbsorptionDetector
    {
        public static void ApplyAPlusStructure(ImbalanceState state, string side)
        {
            state.HasAPlusStructure = false;
            state.APlusStructureSide = "";
            state.APlusStructurePrice = null;

            side = string.IsNullOrWhiteSpace(side) ? "" : side.Trim().ToUpperInvariant();

            if (side == "BUY" && state.HasBuy3_ImbalanceGroup)
            {
                state.HasAPlusStructure = true;
                state.APlusStructureSide = "BUY";
                state.APlusStructurePrice = state.Buy3_ImbalanceGroupPrice;
                return;
            }

            if (side == "SELL" && state.HasSell3_ImbalanceGroup)
            {
                state.HasAPlusStructure = true;
                state.APlusStructureSide = "SELL";
                state.APlusStructurePrice = state.Sell3_ImbalanceGroupPrice;
            }
        }

        public static int CalculateImbalanceScore(ImbalanceState state, string side)
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

        public static void ApplySignalSource(ScoreTradeSignal state)
        {
            if (state.IsValueAcceptance)
                return;

            var hasAPlusSpeed = state.SpeedLabel == "A+ speed" &&
                state.VolumeIncreasing &&
                state.VolumeOk &&
                state.DeltaWithSide;

            state.HasAPlusSpeed = hasAPlusSpeed && state.PriceAcceptedAfterSpeed;

            if (state.HasAPlusStructure)
            {
                state.HasAPlusAbsorption = !state.PriceAcceptedAfterImbalance;
                state.SignalSource = state.PriceAcceptedAfterImbalance ? "A+ STRUCTURE" : "A+ ABSORTION";
                return;
            }

            if (hasAPlusSpeed && !state.PriceAcceptedAfterSpeed)
            {
                state.HasAPlusAbsorption = true;
                state.APlusStructureSide = state.Side;
                state.SignalSource = "A+ ABSORTION";
                return;
            }

            if (state.HasAPlusSpeed)
            {
                state.SignalSource = "A+ SPEED";
                return;
            }

            state.SignalSource = "BREAKOUT";
        }
    }
}
