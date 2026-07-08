"""level_memory_producer.py — write multi-day MEMORY levels to a SHADOW key (V1, 2026-07-08).

The live engine had NO multi-day level memory (verified 2026-07-08: key-levels.json = today's
intraday + curated levels only). J reads multi-day structure naturally ("bounced off 739.50 like
last Thursday"; "rejected the bottom of those 746 candles"). This runs the existing memory engine
(backtest/lib/watchers/level_memory.py) over recent SPY 5m history and writes the memory-weighted
levels (touches + role-flips + candle-bottom CLUSTERS) to automation/state/key-levels-memory.json
— a SHADOW feed the engine / dashboard / self-check can SEE and G5's emit_reject_alert can ping on
— WITHOUT changing what the live engine trades. Roles are STRUCTURAL (level_memory's own
support/resistance from pivot type), deduped by price -> no contradictory-role bug.

The entry-wire (merging these into the live key-levels.json that filter-10 trades off) is A/B-gated
and NEEDS-REVIEW — this producer is the safe, visible half. Read-only market data; no orders.

Run: python setup/scripts/level_memory_producer.py   (schedulable every N min).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
from lib.watchers import level_memory as LM  # noqa: E402

SHADOW = REPO / "automation" / "state" / "key-levels-memory.json"
MIN_MEMORY = 20.0       # only well-tested levels (raised from 3: 3 gave 43 levels = S/R everywhere)
STRONG_MEMORY = 60.0    # >= this => tier "Active" (else "Reference")
LOOKBACK_DAYS = 10      # multi-day memory horizon
DEDUP_EPS = 0.60        # collapse levels within $0.60 into ONE zone (J reads zones, not pivots)
TOP_N = 12              # cap the map at the strongest N zones (readable; not a wall of levels)


def _load_spy() -> "pd.DataFrame | None":
    """Recent SPY 5m OHLCV as timestamp_et/open/high/low/close/volume. yfinance (off the hot
    path); None on failure so the producer fails open (writes nothing rather than garbage)."""
    try:
        import yfinance as yf
        d = yf.download("SPY", period="1mo", interval="5m", progress=False)
    except Exception:
        return None
    if d is None or not len(d):
        return None
    d = d.reset_index()
    tcol = d.columns[0]

    def col(name):
        v = d[name]
        return v.values.ravel() if hasattr(v, "values") else v

    try:
        return pd.DataFrame({
            "timestamp_et": pd.to_datetime(d[tcol]),
            "open": col("Open"), "high": col("High"), "low": col("Low"),
            "close": col("Close"), "volume": col("Volume"),
        })
    except Exception:
        return None


def select_levels(raw) -> list[dict]:
    """PURE: filter (>= MIN_MEMORY) + dedup-into-zones (DEDUP_EPS, strongest wins) + cap (TOP_N)
    + map to the key-levels schema. Broker/network-free -> unit-testable on synthetic Levels.
    Each output carries ONE structural role per price (level_memory's own support/resistance),
    so no contradictory-role bug can arise (one polarity per price, deduped)."""
    keep = [lv for lv in raw if lv.memory_score >= MIN_MEMORY]
    keep.sort(key=lambda lv: -lv.memory_score)     # strongest first, so the zone winner is strongest
    out: list[dict] = []
    for lv in keep:
        if any(abs(lv.price - o["price"]) <= DEDUP_EPS for o in out):
            continue  # a stronger already-kept level owns this price zone
        out.append({
            "price": round(float(lv.price), 2),
            "type": lv.role, "role": lv.role,
            "label": f"MEMORY_{lv.role[:3].upper()}_{lv.memory_score:.0f}",
            "memory_score": round(float(lv.memory_score), 2),
            "touches": int(lv.touches), "role_flips": int(lv.role_flips),
            "tier": "Active" if lv.memory_score >= STRONG_MEMORY else "Reference",
            "source": "level_memory",
        })
    out = out[:TOP_N]                              # cap (readable map, not a wall of levels)
    out.sort(key=lambda o: -o["price"])            # price-ordered for display/consumers
    return out


def build_levels(df: pd.DataFrame) -> list[dict]:
    """Memory levels at the latest bar (causal), selected/deduped/capped via select_levels()."""
    lm = LM.LevelMemory(df)
    return select_levels(lm.levels_at(len(lm.df) - 1, lookback_days=LOOKBACK_DAYS))


def main() -> int:
    df = _load_spy()
    if df is None or len(df) < 50:
        print("[level_memory_producer] SPY load failed -> wrote nothing (fail-open)")
        return 0
    levels = build_levels(df)
    spot = round(float(df["close"].iloc[-1]), 2)
    payload = {"generated_at_et": str(pd.Timestamp.now(tz="America/New_York").replace(microsecond=0)),
               "spot": spot, "lookback_days": LOOKBACK_DAYS, "min_memory": MIN_MEMORY,
               "count": len(levels), "levels": levels,
               "note": "SHADOW multi-day memory levels (V1). NOT yet fed to entries (A/B/NEEDS-REVIEW)."}
    SHADOW.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[level_memory_producer] spot {spot} -> {len(levels)} memory levels (>= {MIN_MEMORY}):")
    for lv in levels:
        print(f"   {lv['price']:8.2f}  {lv['role']:10s}  mem {lv['memory_score']:5.1f}  "
              f"touches {lv['touches']}  flips {lv['role_flips']}  [{lv['tier']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
