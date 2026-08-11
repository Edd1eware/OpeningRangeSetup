using System;

namespace ATAS.Indicators
{
    // Drawdown-based position-size protection (frozen design 06/07/2026).
    //
    // Rationale (Codex analysis on the m1v_5<=90 ORB setup): a "K consecutive SL"
    // trigger does NOT reduce account drawdown, because the worst 2024 bleed was a
    // grind of many full-SL losses interleaved with small wins that keep resetting
    // the consecutive-loss counter. The drawdown-from-peak of equity DOES see that
    // grind. So we de-size on equity drawdown, not on a losing streak.
    //
    // Logic (identical to the backtest sim):
    //   peak = max(peak, balance)
    //   if (peak - balance) >= triggerDrawdown -> de-size to floor
    //   if balance >= peak                     -> restore to base (new equity high)
    //
    // Recommended for LucidPro 150k (MLL EOD $4,500), 40/20/40 trailing bracket:
    //   base = 3 mini, floor = 1 mini, trigger = $3,000.
    //   Historical result: maxDD $3,580 (buffer $920 vs $4,500) vs fixed-3 $4,155
    //   (buffer $345), keeping PnL +$16,590 (above fixed-2 +$15,840).
    //
    // Feed it end-of-day realized account balance (net PnL since account start, in
    // account currency). Stateful: create one instance per account/run.
    public sealed class DrawdownSizeGuard
    {
        private readonly int _baseSize;
        private readonly int _floorSize;
        private readonly decimal _triggerDrawdown;

        private decimal _peakBalance;
        private bool _protecting;

        /// <param name="baseSize">Normal size in contracts (e.g. 3 mini).</param>
        /// <param name="floorSize">Protected size in contracts (e.g. 1 mini).</param>
        /// <param name="triggerDrawdown">Equity drawdown from peak that switches to
        /// floor size, in account currency (e.g. 3000m).</param>
        public DrawdownSizeGuard(int baseSize = 3, int floorSize = 1, decimal triggerDrawdown = 3000m)
        {
            if (baseSize < 1) throw new ArgumentOutOfRangeException(nameof(baseSize));
            if (floorSize < 1) throw new ArgumentOutOfRangeException(nameof(floorSize));
            if (floorSize > baseSize) throw new ArgumentOutOfRangeException(nameof(floorSize),
                "floorSize must be <= baseSize");
            if (triggerDrawdown <= 0) throw new ArgumentOutOfRangeException(nameof(triggerDrawdown));

            _baseSize = baseSize;
            _floorSize = floorSize;
            _triggerDrawdown = triggerDrawdown;
        }

        /// <summary>Current size to trade, in contracts.</summary>
        public int CurrentSize => _protecting ? _floorSize : _baseSize;

        /// <summary>True while in protection mode (trading floor size).</summary>
        public bool IsProtecting => _protecting;

        /// <summary>Highest account balance seen so far.</summary>
        public decimal PeakBalance => _peakBalance;

        /// <summary>Current drawdown from peak (>= 0).</summary>
        public decimal CurrentDrawdown => _peakBalance - _lastBalance;

        private decimal _lastBalance;

        /// <summary>
        /// Update with the latest realized account balance (net PnL since start) and
        /// return the size to use for the NEXT entry. Call once per closed trade /
        /// end of day, before sizing the next order.
        /// </summary>
        public int Update(decimal balance)
        {
            _lastBalance = balance;
            if (balance > _peakBalance)
                _peakBalance = balance;

            var drawdown = _peakBalance - balance;
            if (drawdown >= _triggerDrawdown)
                _protecting = true;        // grind detected -> protect
            if (balance >= _peakBalance)
                _protecting = false;       // new equity high -> restore base

            return CurrentSize;
        }

        /// <summary>Reason string for logging.</summary>
        public string StateReason() =>
            _protecting
                ? $"PROTECT floor={_floorSize} (DD ${_peakBalance - _lastBalance:0} >= ${_triggerDrawdown:0})"
                : $"BASE size={_baseSize} (peak ${_peakBalance:0})";

        /// <summary>Reset all state (new account / new evaluation).</summary>
        public void Reset()
        {
            _peakBalance = 0m;
            _lastBalance = 0m;
            _protecting = false;
        }
    }
}
