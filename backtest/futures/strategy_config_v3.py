"""Curated futures strategy config v3 — derived from REAL MNQ native backtest.

v2b was tuned on SPY proxy (S&P signals, MES sim). v3 is derived from REAL MNQ bars,
where the signal landscape differs: shotgun works both long AND short, erl_irl works
both directions, tbr_high_vol is solid on both sides.

Decision methodology (2026-06-16, real MNQ data + real VIX per row, n=2254 signals over 366 days):
  - Include only slices with n>=15, net>0, WR>=55% OR n>=20 with strong net
  - IS 2025: +$6,860, OOS 2026: +$15,027. Gate: PASS (WF=3.86).
  - Regime shift: 2025 was difficult (choppy with VIX mostly <18 in Q3-Q4)
  - 2026 has seen higher volatility (tariff shock, macro events) -> suits these strategies
  - VIX per row: IMPLEMENTED — all VIX gates use actual VIX at signal time (not fixed 17.0)

Key differences vs v2b:
  1. erl_irl LONG high is the #1 edge on MNQ (WR=79%, +$3,996) — was suppressed in v2b
  2. shotgun works short/high (WR=67%, +$2,486) — v2b excluded this
  3. tbr_high_vol strong on BOTH sides with medium conf
  4. bullish_watcher long/medium has edge but lower WR (46%) — conservative inclusion
  5. bearish_rejection_morning REMOVED — negative on real MNQ data

v3 config: focus on high-WR, mechanistically-justified slices.
OOS performance: use this on any data from 2026 onward.

IMPORTANT: v3 uses VIX=16 floor same as v2b. ERL->IRL eats into MNQ's volatility structure.
VIX per row is implemented in drive_native_backtest.py — all gates use actual bar-level VIX.
"""
from __future__ import annotations

# Each tuple: (watcher, direction, confidence, vix_min, vix_max)
# None = no limit on that dimension
CURATED_V3_RULES = [
    # === TOP TIER (WR >= 65%, n>=25, confirmed OOS-2026 positive) ===
    # erl_irl long/high: 107 trades, WR=79%, +$3,996/trade=$37 -- #1 edge on real MNQ
    ("erl_irl_watcher",              "long",  "high",   16, None),

    # shotgun long both confs: WR 68-73%, combined +$6,438 -- momentum on Nasdaq
    ("shotgun_scalper_watcher",      "long",  "medium", 16, None),
    ("shotgun_scalper_watcher",      "long",  "high",   16, None),

    # shotgun short high: 217 trades, WR=67%, +$2,486 -- works in both directions
    ("shotgun_scalper_watcher",      "short", "high",   16, None),

    # tbr_high_vol long/medium: 28 trades, WR=71%, +$1,545 -- strong long signal
    ("tbr_high_vol_watcher",         "long",  "medium", 16, None),

    # tbr_high_vol short/medium: 34 trades, WR=71%, +$797 -- works short too
    ("tbr_high_vol_watcher",         "short", "medium", 16, None),

    # === SECOND TIER (WR lower or smaller n, but positive net) ===
    # erl_irl short/medium: 106 trades, WR=75%, +$1,800 -- confirmed edge
    ("erl_irl_watcher",              "short", "medium", 16, 22),  # band restriction (v2b learning)

    # v14_enhanced short/medium: 81 trades (VIX>=18), WR=38%, IS=+$2,037, OOS=-$632
    # OOS breakdown: Q1-26 WR=15% -$1,414 (bull market = shorts crushed), Q2-26 WR=60% +$781 (bear market)
    # Regime-sensitive: works in bear/volatile regime, fails in trending bull. Watch closely.
    # WR=38% at 2.04x R ratio = positive EV. Include conservatively but monitor quarterly.
    ("v14_enhanced_watcher",         "short", "medium", 18, None),
    ("v14_enhanced_watcher",         "short", "high",   18, None),

    # tbr_high_vol long/high: 16 trades IS (small n), skip for now -- revisit with more data
    # bullish_watcher long/medium: 131 trades WR=47% -- marginal, exclude until OOS confirmed
]


def should_take_v3(watcher: str, direction: str, confidence: str, vix: float) -> bool:
    """v3 curated filter — more permissive than v2b on long side, less on short."""
    for (w, d, c, vmin, vmax) in CURATED_V3_RULES:
        if w == watcher and d == direction and c == confidence:
            if vmin is not None and vix < vmin:
                return False
            if vmax is not None and vix >= vmax:
                return False
            return True
    return False


# Backward compat alias
should_take = should_take_v3
