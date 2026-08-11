using System;

namespace ATAS.Indicators.Atrapados
{
    // Group 1 — Tiempo. All computable from the bar timestamp (NY).
    // is_nfp / is_opex use calendar heuristics (first / third Friday). is_fomc needs
    // an external calendar file; left 0 here (populated later via a dates table).
    public static class TimeFeatures
    {
        public static void Collect(FeatureRow row, FeatureCtx c)
        {
            var t = c.Bar.TimeNy;
            var open = new DateTime(t.Year, t.Month, t.Day, 9, 30, 0);
            var sessionStart = open;

            row.Add("time_session_seconds", (t - sessionStart).TotalSeconds);
            row.Add("time_seconds_from_open", (t - open).TotalSeconds);
            row.Add("time_seconds_to_1000",
                (new DateTime(t.Year, t.Month, t.Day, 10, 0, 0) - t).TotalSeconds);
            row.Add("time_seconds_to_1030",
                (new DateTime(t.Year, t.Month, t.Day, 10, 30, 0) - t).TotalSeconds);
            row.Add("time_minute_of_day", t.Hour * 60 + t.Minute);
            row.Add("time_second_of_minute", t.Second);
            row.Add("time_weekday", (int)t.DayOfWeek);
            row.Add("time_month", t.Month);
            row.Add("time_quarter", (t.Month - 1) / 3 + 1);
            row.Add("time_is_fomc", 0);                 // TODO: external calendar
            row.Add("time_is_nfp", IsNthFriday(t, 1));  // first Friday ~ NFP
            row.Add("time_is_opex", IsNthFriday(t, 3));  // third Friday ~ OpEx
        }

        private static bool IsNthFriday(DateTime t, int n)
        {
            if (t.DayOfWeek != DayOfWeek.Friday) return false;
            var count = 0;
            for (var d = 1; d <= t.Day; d++)
                if (new DateTime(t.Year, t.Month, d).DayOfWeek == DayOfWeek.Friday) count++;
            return count == n;
        }
    }
}
