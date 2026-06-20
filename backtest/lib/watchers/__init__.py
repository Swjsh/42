"""Strategy watchers — watch-only setup detectors.

Each watcher implements detect_setup(bar, context) -> Optional[WatcherSignal].
Watchers run alongside the live engine but DO NOT place trades. They log
detected setups + would-be P&L to a single observation file:
  automation/state/watcher-observations.jsonl

After N validated triggers (per CLAUDE.md OP 16: 3+ live wins), a watcher
gets promoted from WATCH-ONLY to LIVE TRADING via explicit J ratification.

Watchers shipped (production):
  - orb_watcher.py      : ORB GOAT 30-min opening range break (long + short)
  - bullish_watcher.py  : BULLISH_RECLAIM_RIDE_THE_RIBBON (mirror of bear)

RETIRED / deleted (2026-06-18, watcher-fleet de-sprawl):
  - sniper_watcher.py   : SNIPER_LEVEL_BREAK — retired 2026-05-14 (J directive: kill
      redundancy, v14_enhanced covers the level-break + ribbon-flip family with better
      real-fills). The standalone lib/sniper_detector.py stays in tree (offline diag).
  - pinfade_watcher.py  : PIN-FADE — deleted 2026-06-18 (16-month verdict 1/53 = 1.9% WR,
      -$7,900). Flag-disabled since 2026-05-10; needs a ground-up rebuild before any return.

Watchers added 2026-05-13 (WATCH-ONLY, draft):
  - vwap_watcher.py                : VWAP_REJECTION_PRIME (spec defaults)
  - opening_drive_fade_watcher.py  : OPENING_DRIVE_FADE HOD/LOD fade
  - v14_enhanced_watcher.py        : v14 + 09:45 entry + profit-lock variant

Watchers added 2026-05-19 (WATCH-ONLY, OP-21 historical gate PASS):
  - bearish_reversal_at_level_watcher.py : BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON
      J's 5/01-style countertrend puts on extended bull days at ★★★ resistance.
      Historical gate: 3/3 PASS (2025-04-23, 2026-03-23×2, 2026-03-31). N=4 total.
      Live gate: 0/3. DO NOT promote to heartbeat until 3+ live J confirmations.
  - level_break_first_strike_watcher.py  : LEVEL_BREAK_FIRST_STRIKE (LBFS)
      Bearish first-strike on MIXED-ribbon days; level breaks >=20c with vol >=1.5x.
      VIX<20: 43.3% WR (n=30), NO EDGE. VIX>=20: 100% WR (n=4), ratifiable.
      OP-21 gate: VIX>=20 variant N>=15 across >=2 distinct regimes before promotion.

Watchers added 2026-05-20 evening (WATCH-ONLY, live-accumulation only):
  - close_ceiling_fade_watcher.py : CLOSE_CEILING_DISTRIBUTION_FADE
      L59 pattern (J identified live 2026-05-20): N>=3 bars testing ★★+ ceiling without
      closing above → fake breakout bar → buy puts. Historical backtest impossible (no
      key-levels archive). Live watcher accumulates observations vs today's named levels.
      Promotion: N>=20 live obs + WR>=50% + real-fills + 3 live J wins.
      Entry: 09:45-14:30 ET. premium_stop=-0.99 (chart-stop only per L51/L55).
  - floor_hold_bounce_watcher.py  : FLOOR_HOLD_DISTRIBUTION_BOUNCE
      Bullish analog of L59: N>=3 bars testing ★★+ support without closing below →
      fake breakdown bar → buy calls. Historical backtest impossible (no key-levels archive).
      Support roles: {"support","carry"} with stars>=2. Wyckoff "spring" pattern.
      Promotion: N>=20 live obs + WR>=50% + real-fills + 3 live J wins.
      Entry: 09:45-14:30 ET. premium_stop=-0.99 (chart-stop only per L51/L55).

Watchers added 2026-05-20 (WATCH-ONLY, OP-21 historical gate PASS):
  - named_level_wick_bounce_watcher.py          : NAMED_LEVEL_WICK_BOUNCE (NLWB) WATCH_FRAGILE
      Real-fills 2026-05-20 (full 16-month, PDL, ribbon=MIXED/BULL): WR=47.8% N=23, P&L=-$1,294. FAIL ❌
      Walk-forward STABLE -7.9pp (PDL relaxed). OP-21 real-fills gate FAILED.
      VIX-regime rescue 2026-05-20: NO_RESCUE. No VIX-gated variant passes WR>=50% AND PnL>0.
      Root: R:R mismatch — break-even WR=70% required (TP1=+30%, chart-stop=PDL-$0.80).
      NO promotion path under current exit knobs. Redesign exits to fix (TP1>=100% or tighter stop).
  - double_bottom_morning_low_vol_watcher.py    : DOUBLE_BOTTOM_MORNING_LOW_VOL
      Walk-forward DEGRADED -15.2pp (MORNING filter overfits early 2025). WATCH_FRAGILE.
  - momentum_acceleration_highvol_watcher.py    : MOMENTUM_ACCELERATION_HIGHVOL
      Walk-forward IMPROVED +6.6pp. 16-month Rank #1 (N=47, WR=59.6%). WATCH_FRAGILE.
      Real-fills DEGRADED -16.7pp (WR=42.9%); VIX[20-25) drag. VIX>=25 subset: WR=54.5%
      but N=11 (insufficient). Direction split at VIX>=25: long WR=75% N=4 (+$887),
      short WR=42.9% N=7 (-$435) — BULL ribbon calls drive all positive P&L at high vol.
      Live gate: 0/3. DO NOT promote until real-fills gate re-passed at VIX>=25 N>=15.
  - double_bottom_base_quiet_watcher.py         : DOUBLE_BOTTOM_BASE_QUIET
      Walk-forward STABLE +1.2pp. 16-month cross-validated (N=168, WR=59.5%). WATCH_STABLE.
      conf=LOW gate (conf < 0.60): keeps clean base patterns, rejects pathological 0.60-0.70
      band (OOS WR=46.8%). No MORNING filter -- fires 09:35-15:55 ET. Most robust watcher.
      Real-fills 2026-05-20: WR=63.9% N=122, PnL=+$1,755 (+$14/trade). FAVORABLE +4.4pp.
      OP-21 gates: historical ✓, walk-forward ✓, real-fills ✓. Live gate: 0/3 ❌.
      DO NOT promote until 3 live J confirmations (double-bottom in quiet market, any time).
  - hs_near_named_level_watcher.py              : HEAD_AND_SHOULDERS_NEAR_NAMED_LEVEL
      16-month (2026-05-20): near_named N=88 WR=50.0% (coin flip) — was a FALSE POSITIVE.
      WATCH_FRAGILE: OP-21 historical gate FAILED. Stays in runner for observation only.
      Live gate: 0/3. Superseded by hs_watcher.py (no proximity filter, better evidence).
  - hs_watcher.py                               : HEAD_AND_SHOULDERS_BEAR (WATCH_STABLE)
      Walk-forward STABLE +4.0pp (train 54.5% N=132 / test 58.5% N=53). No proximity filter.
      VIX>=25: WR=60.2% (N=93) strongest. VIX 15-20: 43.3% drag. Overall N=185 WR=55.7%.
      Real-fills 2026-05-20 (09:40-12:00 ET): WR=73.7% N=19, PnL=+$346. Afternoon (12:00-13:30)
      is theta drag (WR=55.6%, PnL=-$1,042) — entry window restricted to 09:40-12:00.
      OP-21 gates: historical ✓, walk-forward ✓, real-fills ✓. Live gate: 0/3 ❌.
      Bearish signal (direction="short"). DO NOT promote until 3 live J confirmations.

Watcher added 2026-05-21 morning (WATCH-FRAGILE, Stage-1 scan only):
  - rsi_divergence_watcher.py             : RSI_DIVERGENCE_BULL (leaderboard #11)
      Classic 5m RSI(14) bullish divergence: price LL + RSI HL → momentum exhaustion.
      Stage-1 scan: N=42 WR=81.0%, 41 distinct dates. VIX_MOD WR=85.2% N=27.
      OOS walk-forward PASS (IS=83.9% OOS=72.7% ratio=0.867). BEAR divergence excluded (WR=47.6%).
      OP-16 edge_capture ZERO standalone — no J anchor day coverage. COMPLEMENTARY SIGNAL:
      primary value as bear-exit enhancer or bull-trigger confirmation (not standalone entry).
      Promotion: N>=15 live obs, WR>=70%, >=8 distinct dates, OOS + real-fills check.
      No warmup needed (stateless per-call: computes RSI from prior_bars each bar).

Watcher added 2026-05-24 (WATCH-ONLY, 0/3 live J confirmations):
  - bearish_rejection_morning_watcher.py   : BEARISH_REJECTION_MORNING
      J's highest-value anchor entries: 4/29 +$342 (10:25 ET) and 5/04 +$730 (10:27 ET).
      Setup: 09:35-10:55 ET, ribbon=BEAR (just flipped), named level rejection >=15c, vol >=1.5×.
      DISTINCT from BEARISH_REVERSAL_AT_LEVEL (11:00+, ribbon=BULL countertrend).
      This is TREND-FOLLOWING from the ribbon flip, not a countertrend fade.
      Anchor coverage: 4/29 "711.4 rejection + ribbon flip" at 10:25, 5/04 "premarket level +
      trendline + ribbon flip" at 10:27. Both bars_after_trigger=0 (at_close trigger).
      The existing BEARISH_REVERSAL watcher's 11:00 time gate structurally misses these entries.
      Gym: v40_bearish_rejection_morning_gate (78/78 PASS 2026-05-24).
      Promotion: N>=3 live J confirmations + real-fills WR>=50% + Rule 9 ratification.

Per OP 21 (Watch-First Promotion Path) — every new strategy starts here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WatcherSignal:
    """Output of a watcher's detect_setup() call."""
    watcher_name: str
    setup_name: str
    direction: str  # "long" | "short" | "neutral"
    entry_price: float
    stop_price: float
    tp1_price: float
    runner_price: Optional[float]
    confidence: str  # "low" | "medium" | "high"
    reason: str
    triggers_fired: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# Re-export each watcher's detect_*_setup entry point. Importers can either
# import these directly from `lib.watchers` or from the individual modules.
# Imports are deferred-style at the bottom to avoid circular issues.
from .vwap_watcher import detect_vwap_setup  # noqa: E402
from .opening_drive_fade_watcher import detect_opening_drive_fade_setup  # noqa: E402
from .v14_enhanced_watcher import detect_v14_enhanced_setup  # noqa: E402
from .premarket_fail_fade_watcher import detect_premarket_fail_fade_setup  # noqa: E402
from .bearish_reversal_at_level_watcher import detect_bearish_reversal_at_level  # noqa: E402
from .level_break_first_strike_watcher import detect_lbfs_setup  # noqa: E402
from .named_level_wick_bounce_watcher import detect_nlwb_setup  # noqa: E402
from .double_bottom_morning_low_vol_watcher import detect_db_morning_low_vol_setup  # noqa: E402
from .momentum_acceleration_highvol_watcher import detect_momentum_accel_highvol_setup  # noqa: E402
from .double_bottom_base_quiet_watcher import detect_db_base_quiet_setup  # noqa: E402
from .hs_watcher import detect_hs_setup  # noqa: E402
from .close_ceiling_fade_watcher import detect_close_ceiling_fade_setup  # noqa: E402
from .floor_hold_bounce_watcher import detect_floor_hold_bounce_setup  # noqa: E402
from .rsi_divergence_watcher import detect_rsi_divergence_bull  # noqa: E402
from .orb15_watcher import detect_orb15_break  # noqa: E402
from .erl_irl_watcher import detect_erl_irl_setup  # noqa: E402
from .named_level_second_test_watcher import detect_named_level_second_test_setup  # noqa: E402
from .stairstep_continuation_watcher import detect_stairstep_continuation_setup  # noqa: E402
from .vwap_trend_pullback_watcher import detect_vwap_trend_pullback_setup  # noqa: E402
from .vwap_continuation_watcher import detect_vwap_continuation_setup  # noqa: E402

__all__ = [
    "WatcherSignal",
    "detect_vwap_setup",
    "detect_opening_drive_fade_setup",
    "detect_v14_enhanced_setup",
    "detect_premarket_fail_fade_setup",
    "detect_bearish_reversal_at_level",
    "detect_lbfs_setup",
    "detect_nlwb_setup",
    "detect_db_morning_low_vol_setup",
    "detect_momentum_accel_highvol_setup",
    "detect_db_base_quiet_setup",
    "detect_hs_setup",
    "detect_close_ceiling_fade_setup",
    "detect_floor_hold_bounce_setup",
    "detect_rsi_divergence_bull",
    "detect_orb15_break",
    "detect_erl_irl_setup",
    "detect_named_level_second_test_setup",
    "detect_stairstep_continuation_setup",
    "detect_vwap_trend_pullback_setup",
    "detect_vwap_continuation_setup",
]
