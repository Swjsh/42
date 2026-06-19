"""Characterise the SPY price-action setup behind J's top Webull winners.

Step 3 of the Webull mining task. For each top winner we cached SPY 5m bars
(IEX feed) covering the RTH session of the trade date. SPX/SPY track ~10:1,
so SPY price action *is* the setup J traded even on his SPXW (cash SPX) trades.

This module loads the cached bars (analysis/webull-j-trades/winner_candles.json),
locates J's entry bar by wall-clock ET, and computes objective, look-ahead-free
features describing what price was doing AT THE ENTRY:

  - opening_range_pos: where entry sits in the 09:30-10:00 opening range
  - prior_trend_30m: net % move over the 6 bars before entry (momentum sign)
  - session_extreme_retrace: how far price had retraced from the session
        high/low established *before* entry (reversal vs continuation tell)
  - new_session_extreme: did the entry bar print a fresh session hi/lo
        (breakout) or not (pullback/reversal)?
  - vwap_side: entry close vs session VWAP-to-date (trend-with / counter)
  - archetype: a coarse label combining the above

All features use ONLY bars at or before the entry bar (no look-ahead).

The cache is written by build_cache() from the bars pulled via the Alpaca
MCP at authoring time. Re-running build_cache requires the raw bars (kept in
winner_candles.json once written). Pure stdlib + pandas. py_compile clean.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent.parent
OUT_DIR = REPO / "analysis" / "webull-j-trades"
CACHE = OUT_DIR / "winner_candles.json"

# ET offset for the cached dates: all fall in EDT (UTC-4). 13:30Z = 09:30 ET.
_EDT_OFFSET_H = 4


@dataclass(frozen=True)
class Bar:
    t_et: dt.datetime  # naive ET
    o: float
    h: float
    l: float
    c: float
    v: int


def _utc_to_et(ts_z: str) -> dt.datetime:
    """'2023-06-01T13:30:00Z' -> naive ET datetime (EDT, UTC-4)."""
    base = dt.datetime.strptime(ts_z, "%Y-%m-%dT%H:%M:%SZ")
    return base - dt.timedelta(hours=_EDT_OFFSET_H)


def _bars_from_raw(raw_bars: list[dict[str, Any]]) -> list[Bar]:
    out = []
    for b in raw_bars:
        out.append(Bar(
            t_et=_utc_to_et(b["t"]),
            o=float(b["o"]), h=float(b["h"]), l=float(b["l"]),
            c=float(b["c"]), v=int(b["v"]),
        ))
    out.sort(key=lambda x: x.t_et)
    return out


def load_cache() -> dict[str, Any]:
    if not CACHE.exists():
        raise FileNotFoundError(
            f"{CACHE} missing — run build_cache() with the raw Alpaca bars first"
        )
    return json.loads(CACHE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Feature extraction (look-ahead free)
# --------------------------------------------------------------------------- #
def _entry_index(bars: list[Bar], entry_hhmm: str) -> Optional[int]:
    """Index of the 5m bar containing the entry time (floor to 5m)."""
    h, m = (int(x) for x in entry_hhmm.split(":"))
    floored = m - (m % 5)
    target = bars[0].t_et.replace(hour=h, minute=floored, second=0)
    for i, b in enumerate(bars):
        if b.t_et == target:
            return i
    # fall back to nearest bar at/just before entry
    best = None
    for i, b in enumerate(bars):
        if b.t_et <= target:
            best = i
    return best


def extract_features(bars: list[Bar], entry_hhmm: str, bias: str) -> dict[str, Any]:
    idx = _entry_index(bars, entry_hhmm)
    if idx is None:
        return {"error": "entry bar not found"}
    entry = bars[idx]
    prior = bars[: idx + 1]  # bars up to AND INCLUDING entry bar

    # Opening range = first 6 bars (09:30-10:00).
    opening = bars[:6]
    or_hi = max(b.h for b in opening)
    or_lo = min(b.l for b in opening)
    or_rng = or_hi - or_lo
    or_pos = (entry.c - or_lo) / or_rng if or_rng > 0 else 0.5

    # Prior 30m trend = net move over 6 bars before entry.
    look = bars[max(0, idx - 6): idx + 1]
    trend_30m = (entry.c - look[0].o) / look[0].o * 100 if look else 0.0

    # Session extreme established BEFORE the entry bar.
    pre = bars[:idx] if idx > 0 else bars[:1]
    sess_hi = max(b.h for b in pre)
    sess_lo = min(b.l for b in pre)
    sess_rng = sess_hi - sess_lo

    # Did entry bar print a fresh session extreme?
    new_hi = entry.h >= sess_hi
    new_lo = entry.l <= sess_lo

    # Retrace from the relevant extreme (for the entry direction).
    if bias == "bull":
        # bullish: how far above the session low did we enter (reclaim depth)?
        retrace = (entry.c - sess_lo) / sess_rng if sess_rng > 0 else 0.0
        new_extreme = new_hi
    else:
        # bearish: how far below the session high did we enter (rejection depth)?
        retrace = (sess_hi - entry.c) / sess_rng if sess_rng > 0 else 0.0
        new_extreme = new_lo

    # VWAP-to-date.
    pv = sum(((b.h + b.l + b.c) / 3) * b.v for b in prior)
    vol = sum(b.v for b in prior)
    vwap = pv / vol if vol else entry.c
    vwap_side = "above" if entry.c >= vwap else "below"

    # Coarse archetype.
    archetype = _classify(bias, trend_30m, new_extreme, retrace, or_pos, entry.c, vwap)

    return {
        "entry_bar_et": entry.t_et.strftime("%H:%M"),
        "entry_close": round(entry.c, 2),
        "opening_range": [round(or_lo, 2), round(or_hi, 2)],
        "opening_range_pos": round(or_pos, 2),
        "prior_trend_30m_pct": round(trend_30m, 2),
        "session_hi_before": round(sess_hi, 2),
        "session_lo_before": round(sess_lo, 2),
        "new_session_extreme": bool(new_extreme),
        "extreme_retrace_frac": round(retrace, 2),
        "vwap_to_date": round(vwap, 2),
        "vwap_side": vwap_side,
        "archetype": archetype,
    }


def _classify(bias, trend_30m, new_extreme, retrace, or_pos, close, vwap) -> str:
    """Coarse setup archetype from the look-ahead-free features."""
    with_trend = (bias == "bull" and close >= vwap) or (bias == "bear" and close < vwap)
    if new_extreme and with_trend:
        return "momentum_breakout_continuation"
    if bias == "bull" and trend_30m > 0.15 and not new_extreme:
        return "bullish_pullback_resumption"
    if bias == "bear" and trend_30m < -0.15 and not new_extreme:
        return "bearish_pullback_resumption"
    # entered against the immediately-prior swing = reversal off an extreme
    if bias == "bull" and retrace < 0.4:
        return "bullish_reversal_off_low"
    if bias == "bear" and retrace < 0.4:
        return "bearish_reversal_off_high"
    if with_trend:
        return "trend_continuation_midrange"
    return "counter_trend_fade"


def analyze_all() -> list[dict[str, Any]]:
    cache = load_cache()
    results = []
    for w in cache["winners"]:
        bars = _bars_from_raw(w["bars"])
        feats = extract_features(bars, w["entry_hhmm"], w["bias"])
        results.append({
            "date": w["date"],
            "symbol": w["symbol"],
            "bias": w["bias"],
            "pnl": w["pnl"],
            "entry_hhmm": w["entry_hhmm"],
            "exit_hhmm": w["exit_hhmm"],
            **feats,
        })
    return results


def main() -> int:
    results = analyze_all()
    print("=" * 92)
    print("SETUP ARCHETYPES BEHIND J'S TOP WINNERS (SPY 5m, look-ahead-free)")
    print("=" * 92)
    for r in results:
        print(f"\n{r['date']}  {r['symbol']}  {r['bias'].upper()}  +${r['pnl']:.0f}  "
              f"entry {r['entry_hhmm']} -> exit {r['exit_hhmm']}")
        print(f"    archetype:        {r.get('archetype')}")
        print(f"    prior 30m trend:  {r.get('prior_trend_30m_pct')}%   "
              f"OR-pos: {r.get('opening_range_pos')}   "
              f"vwap: {r.get('vwap_side')}")
        print(f"    new sess extreme: {r.get('new_session_extreme')}   "
              f"extreme-retrace: {r.get('extreme_retrace_frac')}")
    # Archetype tally.
    from collections import Counter
    tally = Counter(r.get("archetype") for r in results)
    print("\n" + "=" * 40)
    print("ARCHETYPE TALLY:")
    for k, n in tally.most_common():
        print(f"    {k}: {n}")
    # write
    out = OUT_DIR / "winner_setups.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
