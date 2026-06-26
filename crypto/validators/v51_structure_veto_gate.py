"""v51_structure_veto_gate -- exercise the structure-veto decision gate (engine_cli.py).

Proves that _veto_side + _classify_sameday_5m behave correctly on:
  - deterministic zigzag fixtures (offline)
  - live coinbase 5m bars converted to the spy-bar dict format (live)

The 5/04 invariant: range/unknown -> NO veto, so the +$730 range-reversal put
trade is never blocked by this gate (OP-16 non-negotiable).

Offline:
  T1  uptrend  + P/bear side  -> vetoed   (wrong-way short)
  T2  uptrend  + C/bull side  -> NOT vetoed
  T3  downtrend + C/bull side -> vetoed   (wrong-way long)
  T4  downtrend + P/bear side -> NOT vetoed
  T5  range    + P/bear side  -> NOT vetoed  (5/04 invariant)
  T6  unknown  + P/bear side  -> NOT vetoed  (fail-open)
  T7  unknown  + C/bull side  -> NOT vetoed  (fail-open)
  T8  _classify_sameday_5m: < 5 bars -> 'unknown'
  T9  _classify_sameday_5m: clear uptrend fixture -> 'uptrend'
  T10 _classify_sameday_5m: clear downtrend fixture -> 'downtrend'
  T11 _classify_sameday_5m: error / malformed bar -> 'unknown' (fail-open)
  T12 _veto_side: None side -> False (no veto for non-P/C)

Live: fetch live coinbase 5m bars, convert to spy dict format, run
_classify_sameday_5m, verify trend label is sane and veto logic is
consistent (never crashes, produces valid VETOED/ALLOWED verdict for
both sides against the live trend).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtest"))

from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from backtest.lib.engine.engine_cli import _classify_sameday_5m, _veto_side

_BASE = datetime(2026, 6, 26, 13, 30, 0, tzinfo=timezone.utc)

_VALID_TRENDS = {"uptrend", "downtrend", "range", "unknown"}


def _spy_bar(i: int, price: float) -> dict:
    """Build a spy-bar dict (the format _classify_sameday_5m expects)."""
    return {
        "open": price,
        "high": price + 0.5,
        "low": price - 0.5,
        "close": price,
        "volume": 1000.0,
        "timestamp_iso": (_BASE + timedelta(seconds=300 * i)).isoformat(),
    }


def _uptrend_bars(n: int = 15) -> list[dict]:
    """Clear ascending zigzag that produces HH/HL swings."""
    prices = [100, 103, 107, 104, 101, 105, 110, 107, 103, 108, 113, 110, 106, 111, 115]
    return [_spy_bar(i, prices[i % len(prices)] + i * 0.5) for i in range(n)]


def _downtrend_bars(n: int = 15) -> list[dict]:
    """Clear descending zigzag that produces LH/LL swings."""
    prices = list(reversed([100, 103, 107, 104, 101, 105, 110, 107, 103, 108, 113, 110, 106, 111, 115]))
    return [_spy_bar(i, prices[i % len(prices)] - i * 0.5) for i in range(n)]


def run_offline() -> dict:
    results: list[tuple[str, bool, str]] = []

    # T1: uptrend + P -> vetoed (wrong-way short)
    ok = _veto_side("P", "uptrend") is True
    results.append(("T1_uptrend_P_vetoed", ok, "_veto_side('P','uptrend')"))

    # T2: uptrend + C -> NOT vetoed
    ok = _veto_side("C", "uptrend") is False
    results.append(("T2_uptrend_C_allowed", ok, "_veto_side('C','uptrend')"))

    # T3: downtrend + C -> vetoed (wrong-way long)
    ok = _veto_side("C", "downtrend") is True
    results.append(("T3_downtrend_C_vetoed", ok, "_veto_side('C','downtrend')"))

    # T4: downtrend + P -> NOT vetoed
    ok = _veto_side("P", "downtrend") is False
    results.append(("T4_downtrend_P_allowed", ok, "_veto_side('P','downtrend')"))

    # T5: range + P -> NOT vetoed (5/04 invariant)
    ok = _veto_side("P", "range") is False
    results.append(("T5_range_P_allowed_5_04_invariant", ok, "_veto_side('P','range')"))

    # T6: unknown + P -> NOT vetoed (fail-open)
    ok = _veto_side("P", "unknown") is False
    results.append(("T6_unknown_P_failopen", ok, "_veto_side('P','unknown')"))

    # T7: unknown + C -> NOT vetoed (fail-open)
    ok = _veto_side("C", "unknown") is False
    results.append(("T7_unknown_C_failopen", ok, "_veto_side('C','unknown')"))

    # T8: < 5 bars -> 'unknown' (no veto, fail-open on thin data)
    short = [_spy_bar(i, 540.0 + i) for i in range(3)]
    t = _classify_sameday_5m(short)
    results.append(("T8_short_bars_unknown", t == "unknown", f"trend={t}"))

    # T9: clear uptrend fixture -> 'uptrend'
    t = _classify_sameday_5m(_uptrend_bars())
    results.append(("T9_classify_uptrend", t == "uptrend", f"trend={t}"))

    # T10: clear downtrend fixture -> 'downtrend'
    t = _classify_sameday_5m(_downtrend_bars())
    results.append(("T10_classify_downtrend", t == "downtrend", f"trend={t}"))

    # T11: malformed bar (missing fields) -> 'unknown' (fail-open, no crash)
    bad_bars = [{"timestamp_iso": "not-a-date", "open": "x", "close": "y"} for _ in range(10)]
    try:
        t = _classify_sameday_5m(bad_bars)
        ok = t == "unknown"
        note = f"trend={t} (no crash)"
    except Exception as e:
        ok, note = False, f"crash: {e}"
    results.append(("T11_malformed_failopen", ok, note))

    # T12: None side -> False (no veto for non-P/C inputs)
    ok = _veto_side(None, "uptrend") is False
    results.append(("T12_none_side_no_veto", ok, "_veto_side(None,'uptrend')"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """Fetch live coinbase 5m bars, run the veto gate, assert sanity."""
    try:
        from crypto.lib.bar import Bar

        raw = fetch_bars("coinbase", "BTC-USD", 300, 60)
        bars = list(closed_bars_only(raw, now_utc()))
        if not bars:
            return {"mode": "live", "pass": False, "note": "no closed bars from coinbase"}

        # Convert crypto.lib.Bar objects to spy-bar dict format (same shape heartbeat_core sends)
        spy_dicts = [
            {
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "timestamp_iso": b.open_time.isoformat(),
            }
            for b in bars
        ]

        trend = _classify_sameday_5m(spy_dicts)

        # Sanity: trend must be one of the valid labels
        trend_ok = trend in _VALID_TRENDS

        # Veto consistency: for each side, _veto_side must not crash
        veto_P = _veto_side("P", trend)
        veto_C = _veto_side("C", trend)

        # Domain invariants (held for ALL trends including live):
        #   - range/unknown: NEITHER side vetoed
        #   - uptrend: P vetoed, C allowed
        #   - downtrend: C vetoed, P allowed
        #   - never BOTH vetoed simultaneously (would block all trades)
        both_vetoed = veto_P and veto_C
        invariants_ok = trend_ok and not both_vetoed

        return {
            "mode": "live",
            "closed_bars": len(bars),
            "trend": trend,
            "veto_P": veto_P,
            "veto_C": veto_C,
            "both_vetoed": both_vetoed,
            "pass": invariants_ok,
        }
    except Exception as e:
        return {"mode": "live", "pass": False, "note": str(e)[:200]}


if __name__ == "__main__":
    import json
    print("=== OFFLINE ===")
    off = run_offline()
    for t in off["tests"]:
        print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:35s} {t['note']}")
    print(f"  {off['passed']}/{off['total']} pass  all_pass={off['all_pass']}")
    print("\n=== LIVE ===")
    live = run_live()
    print(json.dumps(live, indent=2, default=str))
