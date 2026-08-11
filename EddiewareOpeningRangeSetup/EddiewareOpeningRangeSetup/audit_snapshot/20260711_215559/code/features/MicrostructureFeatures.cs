using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Track A — Executed-microstructure features. Built from FOOTPRINT bars ONLY:
    // aggressive buy = volume executed at the ask, aggressive sell = executed at the
    // bid. No order book / MBO here — pulling, stacking, refill, depth, OFI and the
    // rest of the resting-liquidity dynamics stay in the pending Track B spec
    // (contexto_OR_catboost/TRACK_B_MBO_pendiente.md) until full-day MBO exists.
    //
    // Windows are bar-based (1-min bars) to match the rest of the pipeline. Every new
    // column carries the `mx_` prefix so it never collides with existing groups
    // (absorption_*, footprint_*, d_*, delta_*, volume_*).
    public static class MicrostructureFeatures
    {
        private static readonly int[] Windows = { 1, 3, 5, 10 };

        // A footprint level is "large" when its executed volume is this multiple of
        // the mean level volume on the break bar (whale-by-execution proxy).
        private const double LargeLevelMult = 2.5;

        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var tick = c.Tick;
            var dir = c.IsUp ? 1.0 : -1.0;

            foreach (var n in Windows)
            {
                var w = c.Window(n);
                if (w.Count == 0) continue;

                double aggBuy = 0, aggSell = 0, vol = 0;
                double hi = double.MinValue, lo = double.MaxValue;
                foreach (var b in w)
                {
                    aggBuy += b.BuyVolume;
                    aggSell += b.SellVolume;
                    vol += b.Volume;
                    if (b.High > hi) hi = b.High;
                    if (b.Low < lo) lo = b.Low;
                }

                var totalAgg = aggBuy + aggSell;
                var netAgg = aggBuy - aggSell;
                var rangeTicks = tick > 0 ? (hi - lo) / tick : double.NaN;
                var netMoveTicks = tick > 0
                    ? (w[w.Count - 1].Close - w[0].Open) / tick : double.NaN;
                var absMove = Math.Abs(netMoveTicks);

                // --- Consumption / aggression (executed) ---
                row.Add($"mx_agg_buy_{n}b", aggBuy);
                row.Add($"mx_agg_sell_{n}b", aggSell);
                row.Add($"mx_net_agg_{n}b", netAgg);
                row.Add($"mx_aggressor_ratio_{n}b",
                    totalAgg > 0 ? aggBuy / totalAgg : double.NaN);

                // --- Movement efficiency ---
                // contracts_per_tick: high = lots of volume for little travel (absorptive);
                // ticks_per_100c: inverse, high = efficient / thin travel.
                row.Add($"mx_contracts_per_tick_{n}b",
                    rangeTicks > 0 ? totalAgg / rangeTicks : double.NaN);
                row.Add($"mx_ticks_per_100c_{n}b",
                    totalAgg > 0 ? rangeTicks / (totalAgg / 100.0) : double.NaN);

                // --- Market impact ---
                row.Add($"mx_price_impact_ticks_{n}b",
                    totalAgg > 0 ? absMove / totalAgg : double.NaN);
                row.Add($"mx_price_impact_1000_{n}b",
                    totalAgg > 0 ? absMove / (totalAgg / 1000.0) : double.NaN);
                // Directional: positive when the move went the break's way per contract.
                row.Add($"mx_dir_impact_{n}b",
                    totalAgg > 0 ? (dir * netMoveTicks) / totalAgg : double.NaN);

                // --- Toxicity / illiquidity ---
                // VPIN (bar-window proxy of the volume-bucket original).
                row.Add($"mx_vpin_{n}b",
                    totalAgg > 0 ? Math.Abs(netAgg) / totalAgg : double.NaN);
                // Kyle lambda: price sensitivity per unit of signed order flow.
                row.Add($"mx_kyle_lambda_{n}b",
                    Math.Abs(netAgg) > 0 ? absMove / Math.Abs(netAgg) : double.NaN);
                // Amihud illiquidity: |return in ticks| per contract of raw volume.
                row.Add($"mx_amihud_{n}b",
                    vol > 0 ? absMove / vol : double.NaN);

                // --- Absorption (signed/raw volume that failed to move price) ---
                row.Add($"mx_vol_without_move_{n}b",
                    rangeTicks > 0 ? vol / rangeTicks : vol);
                row.Add($"mx_delta_without_move_{n}b",
                    rangeTicks > 0 ? Math.Abs(netAgg) / rangeTicks : Math.Abs(netAgg));
            }

            // Consecutive absorptive bars ending at the break: above-average volume
            // spent inside a below-average range (stall before the move).
            row.Add("mx_consecutive_absorption", ConsecutiveAbsorption(c));

            // Whale-by-execution: outsized footprint levels on the break bar.
            WhaleByExecution(row, c);
        }

        private static double ConsecutiveAbsorption(FeatureCtx c)
        {
            var meanVol = c.Ctx.VolumeSeries.Mean(30);
            var meanRange = c.Ctx.RangeSeries.Mean(30);
            if (double.IsNaN(meanVol) || double.IsNaN(meanRange)) return double.NaN;

            var tick = c.Tick;
            var count = 0;
            for (var k = c.I; k >= 0; k--)
            {
                var b = c.Session[k];
                var rangeTicks = tick > 0 ? (b.High - b.Low) / tick : double.NaN;
                if (b.Volume > meanVol && rangeTicks < meanRange) count++;
                else break;
            }
            return count;
        }

        private static void WhaleByExecution(FeatureRow row, FeatureCtx c)
        {
            var lv = c.Bar.Levels;
            if (lv.Count == 0)
            {
                row.Add("mx_whale_large_count", double.NaN);
                row.Add("mx_whale_large_vol", double.NaN);
                row.Add("mx_whale_concentration", double.NaN);
                row.Add("mx_whale_impact", double.NaN);
                return;
            }

            double total = 0, max = 0;
            var vols = new List<double>(lv.Count);
            foreach (var l in lv)
            {
                var v = l.Buy + l.Sell;
                vols.Add(v);
                total += v;
                if (v > max) max = v;
            }
            var mean = total / vols.Count;

            double largeCount = 0, largeVol = 0;
            foreach (var v in vols)
                if (v >= LargeLevelMult * mean) { largeCount++; largeVol += v; }

            var rangeTicks = c.Tick > 0 ? (c.Bar.High - c.Bar.Low) / c.Tick : double.NaN;

            row.Add("mx_whale_large_count", largeCount);
            row.Add("mx_whale_large_vol", largeVol);
            // Concentration: share of bar volume in the single heaviest level.
            row.Add("mx_whale_concentration", total > 0 ? max / total : double.NaN);
            // Impact: ticks travelled per contract sitting in the heaviest level.
            row.Add("mx_whale_impact", max > 0 ? rangeTicks / max : double.NaN);
        }
    }
}
