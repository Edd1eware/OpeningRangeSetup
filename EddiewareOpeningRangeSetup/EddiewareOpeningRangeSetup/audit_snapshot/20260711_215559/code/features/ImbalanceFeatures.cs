using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Group 8 — Imbalances (diagonal footprint). Buy imbalance: Ask[p] >= ratio*Bid[p-1];
    // Sell imbalance: Bid[p] >= ratio*Ask[p+1]. Needs footprint levels on the bar.
    public static class ImbalanceFeatures
    {
        private const double Ratio = 3.0;
        private const double MinVol = 70.0;

        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var lv = new List<Lvl>(c.Bar.Levels);
            lv.Sort((a, b) => a.Price.CompareTo(b.Price));   // ascending by price

            int buyCount = 0, sellCount = 0;
            double largest = 0, sumImb = 0, imbVolume = 0;
            double minPrice = double.NaN, maxPrice = double.NaN;
            var tick = c.Tick;

            for (var i = 0; i < lv.Count; i++)
            {
                var ask = lv[i].Buy;    // executed at ask (aggressive buy)
                var bidBelow = i > 0 ? lv[i - 1].Sell : 0;   // sell at price below
                var bid = lv[i].Sell;   // executed at bid (aggressive sell)
                var askAbove = i < lv.Count - 1 ? lv[i + 1].Buy : 0;

                if (ask >= MinVol && ask >= Ratio * Math.Max(bidBelow, 1))
                {
                    buyCount++;
                    var mag = ask / Math.Max(bidBelow, 1);
                    if (mag > largest) largest = mag;
                    sumImb += mag; imbVolume += ask;
                    Track(lv[i].Price, ref minPrice, ref maxPrice);
                }
                if (bid >= MinVol && bid >= Ratio * Math.Max(askAbove, 1))
                {
                    sellCount++;
                    var mag = bid / Math.Max(askAbove, 1);
                    if (mag > largest) largest = mag;
                    sumImb += mag; imbVolume += bid;
                    Track(lv[i].Price, ref minPrice, ref maxPrice);
                }
            }

            var total = buyCount + sellCount;
            var span = double.IsNaN(minPrice) ? 0 : (maxPrice - minPrice) / tick;

            row.Add("imbalance_count", total);
            row.Add("imbalance_buy_count", buyCount);
            row.Add("imbalance_sell_count", sellCount);
            row.Add("imbalance_largest", largest);
            row.Add("imbalance_avg", total > 0 ? sumImb / total : 0);
            row.Add("imbalance_density", span > 0 ? total / span : (total > 0 ? total : 0));
            row.Add("imbalance_cluster_size", total);
            row.Add("imbalance_cluster_volume", imbVolume);
            row.Add("imbalance_price_span", span);
            row.Add("imbalance_three_flag", (buyCount >= 3 || sellCount >= 3) ? 1 : 0);
        }

        private static void Track(double price, ref double min, ref double max)
        {
            if (double.IsNaN(min) || price < min) min = price;
            if (double.IsNaN(max) || price > max) max = price;
        }
    }
}
