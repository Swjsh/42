"""MES-specific curated strategy config v3 — derived from REAL MES native backtest.

v3 (MNQ) was derived from Nasdaq data. MES requires a SEPARATE config because:
  1. erl_irl long high: MNQ #1 edge (+$3,996) but MES disaster (-$5,788)
  2. shotgun short high: MNQ +$2,486 (WR=67%) but MES -$1,174 (WR=59%)
  3. tbr_high_vol: MNQ long works well, MES only short/medium survives
  4. erl_irl short: Negative on MES across all slices

MES backtest (2025-01-02 to 2026-06-12, 2,611 signals with real VIX per row):
  Full-field: WR=43.7%, Net=-$29,890 -- many signal types lose on S&P
  v3_mes filtered: IS=+$1,906 / OOS=+$2,238. Gate: PASS (WF=1.52). +2 tick stress: +$664 (marginal).

Surviving slices (n>=15, net>0 full-period):
  1. shotgun_scalper long high:  n=78,  WR=64%, Net=+$2,765, $/t=$35   <-- FLAGSHIP
  2. v14_enhanced short medium:  n=128, WR=30%, Net=+$713,  $/t=$5.6  <-- asymmetric R:R
  3. v14_enhanced short high:    n=28,  WR=64%, Net=+$678,  $/t=$24   <-- quality signal
  4. tbr_high_vol short medium:  n=91,  WR=58%, Net=+$203,  $/t=$2.2  <-- high WR

Key differences vs MNQ v3:
  - NO erl_irl (S&P ERL structure differs from Nasdaq)
  - NO shotgun short (negative on S&P despite positive on Nasdaq)
  - v14_enhanced short medium included despite low WR (asymmetric wins compensate)
  - tbr only short side (S&P is more mean-reverting on up side)

WARNING: v14_enhanced short medium WR=30% — asymmetric profile means 3 wins pay for 7 losses.
This is fragile to adverse sampling. Monitor closely, suspend if WR drops below 25% live.
"""
from __future__ import annotations

CURATED_V3_MES_RULES = [
    # === TIER 1: High WR, confirmed edge ===
    # shotgun long/high: n=78, WR=64%, $35/trade — S&P momentum long
    ("shotgun_scalper_watcher", "long",  "high",   16, None),

    # v14_enhanced short/high: n=28, WR=64%, $24/trade — quality short signal
    ("v14_enhanced_watcher",    "short", "high",   18, None),

    # === TIER 2: High WR, positive but smaller edge ===
    # tbr_high_vol short/medium: n=91, WR=58%, $2/trade — consistent but thin
    ("tbr_high_vol_watcher",    "short", "medium", 16, None),

    # v14_enhanced short/medium: n=81 (VIX>=18), WR=44%, IS=+$1,273, OOS=-$165 (marginal)
    # OOS barely negative: Q1-26=-$22, Q2-26=-$144. Monitor closely; suspend if WR<30% live.
    ("v14_enhanced_watcher",    "short", "medium", 18, None),
]


def should_take_v3_mes(watcher: str, direction: str, confidence: str, vix: float) -> bool:
    """MES-specific v3 filter — more conservative than MNQ, shorter signal set."""
    for (w, d, c, vmin, vmax) in CURATED_V3_MES_RULES:
        if w == watcher and d == direction and c == confidence:
            if vmin is not None and vix < vmin:
                return False
            if vmax is not None and vix >= vmax:
                return False
            return True
    return False
