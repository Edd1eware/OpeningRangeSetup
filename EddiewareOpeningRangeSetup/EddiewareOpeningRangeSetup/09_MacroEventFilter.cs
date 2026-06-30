using System;
using System.Collections.Generic;

namespace ATAS.Indicators
{
    internal static class MacroEventFilter
    {
        // FOMC announcement days (second day of each meeting) — federalreserve.gov
        // Update each December for the following year.
        private static readonly HashSet<DateTime> FomcDates = new()
        {
            // 2025
            new DateTime(2025, 1, 29), new DateTime(2025, 3, 19), new DateTime(2025, 5,  7),
            new DateTime(2025, 6, 18), new DateTime(2025, 7, 30), new DateTime(2025, 9, 17),
            new DateTime(2025,10, 29), new DateTime(2025,12, 10),
            // 2026
            new DateTime(2026, 1, 28), new DateTime(2026, 3, 18), new DateTime(2026, 4, 29),
            new DateTime(2026, 6, 17), new DateTime(2026, 7, 29), new DateTime(2026, 9, 16),
            new DateTime(2026,10, 28), new DateTime(2026,12,  9),
            // 2027 — update in Dec 2026
            new DateTime(2027, 1, 27), new DateTime(2027, 3, 17), new DateTime(2027, 5,  5),
            new DateTime(2027, 6, 16), new DateTime(2027, 7, 28), new DateTime(2027, 9, 15),
            new DateTime(2027,10, 27), new DateTime(2027,12,  8),
        };

        // CPI release days — bls.gov schedule (08:30 ET)
        // Update each December for the following year.
        private static readonly HashSet<DateTime> CpiDates = new()
        {
            // 2025
            new DateTime(2025, 1,15), new DateTime(2025, 2,12), new DateTime(2025, 3,12),
            new DateTime(2025, 4,10), new DateTime(2025, 5,13), new DateTime(2025, 6,11),
            new DateTime(2025, 7,15), new DateTime(2025, 8,12), new DateTime(2025, 9,11),
            new DateTime(2025,10,14), new DateTime(2025,11,12), new DateTime(2025,12,10),
            // 2026
            new DateTime(2026, 1,14), new DateTime(2026, 2,11), new DateTime(2026, 3,11),
            new DateTime(2026, 4, 9), new DateTime(2026, 5,13), new DateTime(2026, 6,10),
            new DateTime(2026, 7,14), new DateTime(2026, 8,12), new DateTime(2026, 9,10),
            new DateTime(2026,10,14), new DateTime(2026,11,11), new DateTime(2026,12, 9),
            // 2027 — update in Dec 2026
            new DateTime(2027, 1,13), new DateTime(2027, 2,10), new DateTime(2027, 3,10),
            new DateTime(2027, 4, 9), new DateTime(2027, 5,12), new DateTime(2027, 6, 9),
            new DateTime(2027, 7,14), new DateTime(2027, 8,11), new DateTime(2027, 9, 9),
            new DateTime(2027,10,13), new DateTime(2027,11,10), new DateTime(2027,12, 8),
        };

        /// <summary>
        /// Returns true if <paramref name="date"/> is a high-impact macro event day:
        /// FOMC, CPI, NFP (first Friday of month), or Jackson Hole week (last Mon-Fri of August).
        /// </summary>
        public static bool IsBlockedDate(DateTime date)
        {
            var d = date.Date;
            return FomcDates.Contains(d)
                || CpiDates.Contains(d)
                || IsNfpDay(d)
                || IsJacksonHoleWeek(d);
        }

        /// <summary>Returns the reason string for logging, or empty if not blocked.</summary>
        public static string BlockedReason(DateTime date)
        {
            var d = date.Date;
            if (FomcDates.Contains(d))          return "FOMC";
            if (CpiDates.Contains(d))           return "CPI";
            if (IsNfpDay(d))                    return "NFP";
            if (IsJacksonHoleWeek(d))           return "JACKSON HOLE";
            return "";
        }

        // NFP = first Friday of each calendar month.
        private static bool IsNfpDay(DateTime date)
        {
            if (date.DayOfWeek != DayOfWeek.Friday)
                return false;

            // Is it the first Friday? day <= 7
            return date.Day <= 7;
        }

        // Jackson Hole = last full Mon-Fri week of August.
        // Heuristic: block Mon-Fri of the week containing the last Thursday of August.
        private static bool IsJacksonHoleWeek(DateTime date)
        {
            if (date.Month != 8)
                return false;

            var lastThursday = LastWeekdayOfMonth(date.Year, 8, DayOfWeek.Thursday);
            var weekStart    = lastThursday.AddDays(-(int)lastThursday.DayOfWeek + 1); // Monday
            var weekEnd      = weekStart.AddDays(4);                                   // Friday

            return date >= weekStart && date <= weekEnd;
        }

        private static DateTime LastWeekdayOfMonth(int year, int month, DayOfWeek weekday)
        {
            var lastDay = new DateTime(year, month, DateTime.DaysInMonth(year, month));
            var diff = ((int)lastDay.DayOfWeek - (int)weekday + 7) % 7;
            return lastDay.AddDays(-diff);
        }
    }
}
