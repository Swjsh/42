"""Curated futures strategy config — the 'change it up' iteration result (2026-06-14).

Derived from the 16-month MES Stage-1 scan: include only the strategy slices that are
individually profitable (n>=20) with their regime gates. This is the futures analog of the
options params.json. IN-SAMPLE selection — must clear OOS walk-forward before any live use.

Each rule: (watcher, direction, confidence, vix_min, vix_max). vix_min/None = no floor;
vix_max/None = no ceiling. A signal is taken iff it matches a rule AND passes the rule's VIX gate.
"""
from __future__ import annotations

CURATED_V2B_RULES = [
    # winners that want elevated vol (VIX>=16): momentum + ORB
    ("shotgun_scalper_watcher",          "long",  "medium", 16,  None),
    ("shotgun_scalper_watcher",          "long",  "high",   16,  None),
    ("tbr_high_vol_watcher",             "long",  "medium", 16,  None),
    ("tbr_high_vol_watcher",             "long",  "high",   16,  None),
    ("orb_watcher",                      "long",  "medium", 16,  None),
    # J's morning rejection (his real edge) — robust across regimes
    ("bearish_rejection_morning_watcher","short", "medium", None, None),
    ("bearish_rejection_morning_watcher","short", "low",    22,  None),
    # ERL->IRL ONLY survives as short/high in the VIX 16-22 band (inverted high-vol response)
    ("erl_irl_watcher",                  "short", "high",   16,  22),
    # tbr shorts only in stress
    ("tbr_high_vol_watcher",             "short", "medium", 22,  None),
]


def should_take(watcher: str, direction: str, confidence: str, vix: float) -> bool:
    for (w, d, c, vmin, vmax) in CURATED_V2B_RULES:
        if w == watcher and d == direction and c == confidence:
            if vmin is not None and vix < vmin:
                return False
            if vmax is not None and vix >= vmax:
                return False
            return True
    return False
