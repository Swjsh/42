"""confluence_producer.py -- stack the shadow structural sources into scored CONFLUENCE ZONES.

J reads structure by CONFLUENCE, not exact levels: his 745.39 line is where a memory level
(744.40), a live trendline (744.35), yesterday's wick-low shelf (745.21), and the Thu->Mon
gap-top all CONVERGE -- a ~$1.4-wide zone. The engine had these as SEPARATE shadow files
(key-levels-memory.json / trendlines-live.json / prior-rth-close.json) + the raw wick-lows, but
nothing COMBINED them. This aggregates the 4 sources into price ZONES where >= MIN_SOURCES
DISTINCT sources agree within +/-BAND, scored by distinct-source-count + weight, deduped +
capped to a handful (the 43-noise-levels failure is tamed by require-2-distinct-sources + TOP_N).
Writes automation/state/confluence-zones.json -- the engine/dashboard can rank by conviction.

SHADOW-only, $0. The entry-use (trade off confluence) is A/B-gated NEEDS-REVIEW, like the other
vision wires. Designed via the confluence-layer-design workflow (validated vs J's 745 read).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
MEMORY_F = STATE / "key-levels-memory.json"
TREND_F = STATE / "trendlines-live.json"
GAP_F = STATE / "prior-rth-close.json"
OUT_F = STATE / "confluence-zones.json"

BAND = 0.85          # +/- window ($): sources within this of an anchor "align" (J's zone ~$1.4 wide)
MIN_SOURCES = 2      # >= this many DISTINCT sources to graduate to a confluence zone (kills noise)
TOP_N = 8            # cap the map to a handful of REAL zones

# per-source base weight (memory adds its own score on top)
_W = {"memory": 1.0, "trendline": 30.0, "wick_low": 25.0, "gap_magnet": 40.0}


def build_zones(points: list, band: float = BAND, min_sources: int = MIN_SOURCES,
                top_n: int = TOP_N) -> list:
    """PURE: for each anchor point, gather points within +/-band; a ZONE requires >= min_sources
    DISTINCT sources. Dedup overlapping zones (keep the higher score). Cap top_n. Testable."""
    zones = []
    for anchor in points:
        near = [p for p in points if abs(p["price"] - anchor["price"]) <= band]
        srcs = {p["source"] for p in near}
        if len(srcs) < min_sources:
            continue
        prices = [p["price"] for p in near]
        score = round(len(srcs) * 100 + sum(p["weight"] for p in near), 1)
        zones.append({
            "center": round(sum(prices) / len(prices), 2),
            "low": round(min(prices), 2), "high": round(max(prices), 2),
            "n_sources": len(srcs), "sources": sorted(srcs), "score": score,
            "members": [f"{p['source']}@{p['price']}" for p in sorted(near, key=lambda x: x["price"])],
        })
    zones.sort(key=lambda z: -z["score"])
    kept: list = []
    for z in zones:
        if any(abs(z["center"] - k["center"]) <= band for k in kept):
            continue  # a stronger overlapping zone already owns this price
        kept.append(z)
    return kept[:top_n]


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError):
        return None


def _wick_lows() -> list:
    """Prior trading day's RTH low + today's session low (the 'defended wick' anchors J reads).
    yfinance, off the hot path; [] on failure."""
    try:
        import yfinance as yf
        d = yf.download("SPY", period="7d", interval="5m", progress=False)
        if not len(d):
            return []
        d = d.reset_index()
        tcol = d.columns[0]
        et = pd.to_datetime(d[tcol])
        et = et.dt.tz_convert("America/New_York") if et.dt.tz is not None else et
        low = d["Low"]
        low = low.values.ravel() if hasattr(low, "values") else low
        dates = et.dt.date
        hm = et.dt.strftime("%H:%M")
        rth = (hm >= "09:30") & (hm <= "16:00")
        out = []
        for day in sorted(set(dates))[-2:]:  # prior day + today
            m = (dates == day) & rth
            if m.any():
                out.append(round(float(pd.Series(low)[m.values].min()), 2))
        return out
    except Exception:
        return []


def harvest() -> list:
    """Flatten the 4 shadow/derived sources into tagged points {price, source, weight, meta}."""
    pts = []
    mem = _read(MEMORY_F)
    for lv in (mem or {}).get("levels", []):
        pts.append({"price": float(lv["price"]), "source": "memory",
                    "weight": _W["memory"] + float(lv.get("memory_score", 0)), "meta": lv.get("label", "")})
    tr = _read(TREND_F)
    for t in (tr or {}).get("trendlines", []):
        pts.append({"price": float(t["current_value"]), "source": "trendline",
                    "weight": _W["trendline"] + float(t.get("respect_count", 0)), "meta": t.get("status", "")})
    gap = _read(GAP_F)
    if gap and gap.get("prior_rth_close") is not None:
        pts.append({"price": float(gap["prior_rth_close"]), "source": "gap_magnet",
                    "weight": _W["gap_magnet"], "meta": f"gap {gap.get('gap_pts')}"})
    for w in _wick_lows():
        pts.append({"price": w, "source": "wick_low", "weight": _W["wick_low"], "meta": "rth_low"})
    return pts


def main() -> int:
    points = harvest()
    zones = build_zones(points)
    OUT_F.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "band": BAND, "min_sources": MIN_SOURCES, "input_points": len(points),
        "count": len(zones), "zones": zones,
        "note": "CONFLUENCE zones = where >= 2 distinct structural sources (memory/trendline/wick_low/"
                "gap) converge. SHADOW-only (entry-use A/B-gated NEEDS-REVIEW). Higher score = more "
                "sources stacked = higher conviction (how J reads 745.39)."}, indent=2), encoding="utf-8")
    print(f"[confluence_producer] {len(points)} points -> {len(zones)} confluence zones:")
    for z in zones:
        print(f"   {z['center']:8.2f}  [{z['low']}-{z['high']}]  {z['n_sources']} sources "
              f"{z['sources']}  score {z['score']}  <- {' + '.join(z['members'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
