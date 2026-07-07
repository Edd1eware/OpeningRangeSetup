using System;
using System.Globalization;

namespace ATAS.Indicators
{
    // Graduated kill-switch position sizer (validated design 2026-07-07).
    //
    // Rationale (kill_switch_sim.py, robustness by 2000-perm shuffle on the real
    // 2025-2026 EW ORB sequence): the OLD "full size until the DD cliff" governor
    // burns ~26% of orderings, because a losing grind blows through the cushion
    // before the last-second cut helps. De-sizing EARLIER and GRADUALLY (half at
    // 0.35*cushion, min at 0.60*cushion) plus a losing-streak override drops the
    // shuffle burn probability to ~1.9% at base=4 (Pro $4,500 cushion) while
    // keeping +$19,780 P50 -- vs fixed-3c (26% burn) or fixed-6c (99%).
    //
    // Tiers (integer contracts): full=base, half=max(1,round(base/2)), min=1.
    // Never fully pauses (min tier keeps 1c) so the account stays in the game and
    // can re-arm; a hard 0 would deadlock (paused days generate no green days).
    //
    // Decision each step (before the NEXT entry, fed the realized account balance
    // = net PnL since account start, in account currency):
    //   dd = peak - balance
    //   ddTier    = 0 if dd < f1*cushion, 1 if dd < f2*cushion, else 2
    //   streakTier= 0, or 1 if streak>=sHalf, or 2 if streak>=sPause
    //   target    = max(ddTier, streakTier)            (deeper index = smaller)
    //   cut instantly when target deeper; step UP one tier only after `rearmGreen`
    //   green days OR `probeDays` stuck (anti-whipsaw / anti-deadlock).
    //
    // Recommended (LucidPro 150k, $4,500 MLL): base=3 to start (0% shuffle burn),
    // step base to 4 after forward-validation (1.9% burn, +17% PnL). Configurable.
    //
    // Stateful: one instance per account/run. Feed OnTradeClosed(pnlUsd) after each
    // closed trade; read CurrentSize before each entry. Persist/restore via the
    // Serialize()/Deserialize() strings so it survives ATAS restarts.
    public sealed class KillSwitchSizer
    {
        private readonly int _base;
        private readonly int _half;
        private readonly decimal _cushion;
        private readonly decimal _f1;
        private readonly decimal _f2;
        private readonly int _sHalf;
        private readonly int _sPause;
        private readonly int _rearmGreen;
        private readonly int _probeDays;

        // 0 = full, 1 = half, 2 = min
        private int _tier;
        private int _streak;   // consecutive losing trades
        private int _green;    // consecutive winning trades (for re-arm)
        private int _stuck;    // steps stuck at current low tier (time probe)
        private decimal _balance;
        private decimal _peak;

        public KillSwitchSizer(int baseSize = 3, decimal cushion = 4500m,
            decimal f1 = 0.35m, decimal f2 = 0.60m,
            int sHalf = 3, int sPause = 4, int rearmGreen = 2, int probeDays = 8)
        {
            if (baseSize < 1) throw new ArgumentOutOfRangeException(nameof(baseSize));
            if (cushion <= 0) throw new ArgumentOutOfRangeException(nameof(cushion));
            if (f1 <= 0 || f2 <= f1 || f2 >= 1)
                throw new ArgumentOutOfRangeException(nameof(f2), "require 0 < f1 < f2 < 1");

            _base = baseSize;
            _half = Math.Max(1, (int)Math.Round(baseSize / 2.0, MidpointRounding.AwayFromZero));
            _cushion = cushion;
            _f1 = f1;
            _f2 = f2;
            _sHalf = sHalf;
            _sPause = sPause;
            _rearmGreen = rearmGreen;
            _probeDays = probeDays;
        }

        /// <summary>Contracts to trade for the NEXT entry, per the current tier.</summary>
        public int CurrentSize => _tier == 0 ? _base : (_tier == 1 ? _half : 1);

        public int Tier => _tier;
        public decimal PeakBalance => _peak;
        public decimal CurrentDrawdown => _peak - _balance;
        public int LosingStreak => _streak;

        /// <summary>
        /// Update after a closed trade with its realized PnL (account currency, signed).
        /// Recomputes the tier for the next entry. Returns the new CurrentSize.
        /// </summary>
        public int OnTradeClosed(decimal pnlUsd)
        {
            _balance += pnlUsd;
            if (_balance > _peak) _peak = _balance;

            var dd = _peak - _balance;
            int ddTier = dd < _f1 * _cushion ? 0 : (dd < _f2 * _cushion ? 1 : 2);
            int streakTier = _streak >= _sPause ? 2 : (_streak >= _sHalf ? 1 : 0);
            int target = Math.Max(ddTier, streakTier);

            if (target > _tier)
            {
                _tier = target; _green = 0; _stuck = 0;      // cut instantly
            }
            else if (target < _tier && (_green >= _rearmGreen || _stuck >= _probeDays))
            {
                _tier -= 1; _green = 0; _stuck = 0;          // step up one level
            }
            else
            {
                _stuck += 1;
            }

            // streak / green bookkeeping from the trade just closed
            if (pnlUsd < 0m) { _streak += 1; _green = 0; }
            else if (pnlUsd > 0m) { _streak = 0; _green += 1; }

            return CurrentSize;
        }

        public string StateReason() =>
            $"KILL tier={_tier} size={CurrentSize} (DD ${_peak - _balance:0} peak ${_peak:0} " +
            $"streak {_streak})";

        public void Reset()
        {
            _tier = 0; _streak = 0; _green = 0; _stuck = 0;
            _balance = 0m; _peak = 0m;
        }

        // ── Persistence (survives ATAS restart / session change) ───────────
        public string Serialize() => string.Join("|", new[]
        {
            _tier.ToString(CultureInfo.InvariantCulture),
            _streak.ToString(CultureInfo.InvariantCulture),
            _green.ToString(CultureInfo.InvariantCulture),
            _stuck.ToString(CultureInfo.InvariantCulture),
            _balance.ToString(CultureInfo.InvariantCulture),
            _peak.ToString(CultureInfo.InvariantCulture)
        });

        public void Deserialize(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return;
            var p = s.Split('|');
            if (p.Length < 6) return;
            try
            {
                _tier = int.Parse(p[0], CultureInfo.InvariantCulture);
                _streak = int.Parse(p[1], CultureInfo.InvariantCulture);
                _green = int.Parse(p[2], CultureInfo.InvariantCulture);
                _stuck = int.Parse(p[3], CultureInfo.InvariantCulture);
                _balance = decimal.Parse(p[4], CultureInfo.InvariantCulture);
                _peak = decimal.Parse(p[5], CultureInfo.InvariantCulture);
            }
            catch { /* corrupt state -> keep defaults */ }
        }
    }
}
