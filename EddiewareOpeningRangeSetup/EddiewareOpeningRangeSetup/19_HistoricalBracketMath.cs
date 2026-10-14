using System;
using System.Collections.Generic;

namespace ATAS.Indicators
{
    /// <summary>
    /// Reconstructs a structural bracket from closed-candle price levels.
    /// This is arithmetic only: the result is not an original historical order
    /// and does not create, change, or submit any trading order.
    /// </summary>
    public static class HistoricalBracketMath
    {
        public sealed class Row
        {
            public decimal Low { get; }
            public decimal High { get; }
            public decimal Volume { get; }
            public decimal Reference { get; }
            // A zero reference is an allowed infinite ratio, never divided by zero.
            public double Ratio { get; }

            internal Row(decimal low, decimal high, decimal volume, decimal reference)
            {
                Low = low;
                High = high;
                Volume = volume;
                Reference = reference;
                Ratio = reference == 0m ? double.PositiveInfinity : (double)(volume / reference);
            }
        }

        public sealed class Result
        {
            public IReadOnlyList<Row> Levels { get; }
            public decimal Stop { get; }
            public decimal Target { get; }
            public decimal RiskTicks { get; }
            public string Reason { get; }
            public bool Success => Reason == "ok";

            internal Result(IReadOnlyList<Row> levels, decimal stop, decimal target,
                decimal riskTicks, string reason)
            {
                Levels = levels;
                Stop = stop;
                Target = target;
                RiskTicks = riskTicks;
                Reason = reason;
            }
        }

        private struct Cell
        {
            public decimal Bid;
            public decimal Ask;
        }

        /// <summary>Upper label of a fixed group of five native ticks.</summary>
        public static decimal UpperLabel(decimal price, decimal tick = 0.25m)
        {
            if (tick <= 0m)
                throw new ArgumentOutOfRangeException(nameof(tick), "Tick must be positive.");
            decimal step = 5m * tick;
            return decimal.Ceiling(price / step) * step;
        }

        private static Result Failure(string reason)
        {
            return new Result(Array.AsReadOnly(new Row[0]), 0m, 0m, 0m, reason);
        }

        /// <summary>
        /// Group raw levels by CEIL-5; compare Ask upper against Bid lower for
        /// buys, or Bid lower against Ask upper for sells. Missing interior
        /// levels are zero; no pair is fabricated beyond the grouped high/low.
        /// Levels are returned in ascending price order. Ratio is strictly >3,
        /// dominant volume is at least 70, and separated imbalances are allowed.
        /// The stop is five native ticks beyond the farthest aligned row edge;
        /// target is 1:1 from the supplied entry, without modeled fill slippage.
        /// </summary>
        public static Result Calculate(
            IEnumerable<(decimal Price, decimal Bid, decimal Ask)> levels,
            decimal rawHigh,
            decimal rawLow,
            decimal entry,
            int direction,
            decimal tick = 0.25m)
        {
            if (tick <= 0m)
                return Failure("invalid_tick");
            if (direction != 1 && direction != -1)
                return Failure("invalid_direction");
            if (rawLow <= 0m || rawHigh < rawLow)
                return Failure("invalid_candle_range");
            if (entry <= 0m)
                return Failure("invalid_entry");
            if (levels == null)
                return Failure("missing_levels");

            decimal step = 5m * tick;
            decimal high = UpperLabel(rawHigh, tick);
            decimal low = UpperLabel(rawLow, tick);
            var cells = new Dictionary<decimal, Cell>();
            foreach (var level in levels)
            {
                if (level.Price <= 0m || level.Bid < 0m || level.Ask < 0m)
                    return Failure("invalid_level");
                decimal label = UpperLabel(level.Price, tick);
                cells.TryGetValue(label, out Cell cell);
                cell.Bid += level.Bid;
                cell.Ask += level.Ask;
                cells[label] = cell;
            }

            var aligned = new List<Row>();
            for (decimal upper = high; upper > low; upper -= step)
            {
                decimal lower = upper - step;
                cells.TryGetValue(upper, out Cell upperCell);
                cells.TryGetValue(lower, out Cell lowerCell);
                decimal dominant = direction == 1 ? upperCell.Ask : lowerCell.Bid;
                decimal reference = direction == 1 ? lowerCell.Bid : upperCell.Ask;
                if (dominant < 70m || dominant <= 3m * reference)
                    continue;
                decimal label = direction == 1 ? upper : lower;
                aligned.Add(new Row(label - 4m * tick, label, dominant, reference));
            }
            if (aligned.Count == 0)
                return Failure("no_aligned_imbalance");

            aligned.Sort((a, b) => a.Low.CompareTo(b.Low));
            decimal stop = direction == 1
                ? aligned[0].Low - 5m * tick
                : aligned[aligned.Count - 1].High + 5m * tick;
            decimal distance = direction * (entry - stop);
            if (distance <= 0m)
                return Failure("invalid_stop_side");
            return new Result(aligned.AsReadOnly(), stop, entry + direction * distance,
                distance / tick, "ok");
        }
    }
}
