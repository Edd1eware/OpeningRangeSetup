using System;
using System.Collections.Generic;

namespace ATAS.Indicators.Atrapados
{
    // Group 9 — Footprint del bar del break (perfil por nivel).
    public static class FootprintFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var b = c.Bar;
            var lv = new List<Lvl>(b.Levels);
            lv.Sort((x, y) => x.Price.CompareTo(y.Price));
            var tick = c.Tick;

            double buy = 0, sell = 0, vol = 0, pocVol = -1, poc = double.NaN;
            foreach (var l in lv)
            {
                buy += l.Buy; sell += l.Sell;
                var lvVol = l.Buy + l.Sell;
                vol += lvVol;
                if (lvVol > pocVol) { pocVol = lvVol; poc = l.Price; }
            }
            if (vol <= 0) { buy = b.BuyVolume; sell = b.SellVolume; vol = b.Volume; }

            var mid = (b.High + b.Low) / 2.0;
            var pocShift = double.IsNaN(poc) ? double.NaN : (poc - mid) / tick;
            var range = (b.High - b.Low) / tick;
            var body = Math.Abs(b.Close - b.Open) / tick;
            var upperWick = (b.High - Math.Max(b.Open, b.Close)) / tick;
            var lowerWick = (Math.Min(b.Open, b.Close) - b.Low) / tick;

            row.Add("footprint_delta", buy - sell);
            row.Add("footprint_volume", vol);
            row.Add("footprint_buy_volume", buy);
            row.Add("footprint_sell_volume", sell);
            row.Add("footprint_poc", double.IsNaN(poc) ? double.NaN : poc);
            row.Add("footprint_poc_shift", pocShift);
            row.Add("footprint_rotation", vol > 0 ? (buy - sell) / vol : double.NaN);
            row.Add("footprint_body", body);
            row.Add("footprint_wick", upperWick + lowerWick);
            row.Add("footprint_efficiency", vol > 0 ? range / (vol / 1000.0 + 1e-9) : double.NaN);
        }
    }
}
