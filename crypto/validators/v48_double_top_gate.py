"""v48_double_top_gate — validate the DOUBLE_TOP watcher (bearish mirror of double_bottom).

The double_top_detector PRIMITIVE is already covered by v22_chart_patterns; this gate
locks the WATCHER WRAPPER's contract (backtest/lib/watchers/double_top_watcher.py):
it fires direction="short" when an intraday M completes (close below the trough), it
respects the RTH window + cooldown, and — the load-bearing design choice — it applies
NO edge-derived gates (no conf ceiling / VIX / proximity), because no validated combo
search exists for the double top on our data and the watcher's job is to gather an
UNBIASED SPY 5m sample. Confidence is REPORTED, never used to suppress.

Caveat encoded in the watcher + asserted here as metadata: TA-PATTERN-REFERENCE.md §B —
the intraday double top "IS a usable short trigger but is really an A.4 CHoCH/level-
rejection in disguise; do not attach Bulkowski's 25% figure to it." Re-measure the
failure rate on our SPY 5m sample before ANY live trigger (OP-21, 0/3 live wins).

Offline tests:
  T1  clean M (twin highs + trough + close below trough) in RTH  -> fires short
  T2  monotonic uptrend (no twin peaks)                          -> None
  T3  twin peaks but final close ABOVE the trough (no break)     -> None (isolates break gate)
  T4  clean M OUTSIDE RTH (08:xx)                                -> None (time gate)
  T5  cooldown: second identical call is suppressed; re-fires after the cooldown elapses
  T6  metadata contract (no_edge_gates marker, bulkowski caveat, op21 gate, neckline)

Live: audit watcher-observations.jsonl for double_top rows (informational, network-free).

Exit code: 0 if all offline tests PASS, 1 otherwise.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backtest.lib.filters import BarContext
from backtest.lib.watchers import double_top_watcher as _dt
from backtest.lib.watchers.double_top_watcher import (
    detect_double_top_setup,
    _RTH_START,
    _RTH_END,
    _COOLDOWN_MINUTES,
    _WINDOW_BARS,
)


def _ts(i: int, *, hour: int = 9, minute: int = 35) -> dt.datetime:
    return dt.datetime(2026, 5, 4, hour, minute) + dt.timedelta(minutes=5 * i)


def _make_ctx(rows: list[dict], vix: float = 17.0) -> BarContext:
    df = pd.DataFrame(rows)
    cur = df.iloc[-1]
    return BarContext(
        bar_idx=len(df) - 1,
        timestamp_et=cur["timestamp_et"],
        bar=cur,
        prior_bars=df,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=vix,
        vix_prior=vix,
        vol_baseline_20=1000.0,
        range_baseline_20=0.5,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
    )


def _reset() -> None:
    _dt._last_signal_time = None


# ── Fixtures ──────────────────────────────────────────────────────────────────
# A clean SPY-priced M: HIGH1≈740.0, trough(neckline)=737.0, HIGH2≈739.9, then a
# breakdown bar closing 736.7 (< neckline). 10 bars (>= the 10-bar floor).

def _rows_double_top(*, hour: int = 9, minute: int = 35, final_close: float = 736.7) -> list[dict]:
    raw = [
        (735.0, 735.5, 734.5, 735.1),   # filler
        (735.1, 735.6, 734.8, 735.3),   # filler
        (735.3, 738.0, 735.1, 737.8),
        (737.8, 740.0, 737.5, 739.5),   # HIGH1 (local high 740.0)
        (739.5, 738.5, 737.2, 737.5),
        (737.5, 738.0, 737.0, 737.6),   # trough low 737.0 = neckline
        (737.6, 738.8, 737.4, 738.6),
        (738.6, 739.9, 738.3, 739.6),   # HIGH2 (local high 739.9, ~equal to HIGH1)
        (739.6, 739.0, 737.5, 737.8),
        (737.8, 737.5, 736.5, final_close),   # final bar (breakdown when close < 737.0)
    ]
    rows = []
    for i, (o, h, l, c) in enumerate(raw):
        rows.append(dict(timestamp_et=_ts(i, hour=hour, minute=minute),
                         open=o, high=h, low=l, close=c, volume=1000 + i * 50))
    return rows


def _rows_no_pattern() -> list[dict]:
    """Monotonic uptrend — no twin peaks, detector returns None."""
    rows = []
    for i in range(11):
        p = 735.0 + i * 0.5
        rows.append(dict(timestamp_et=_ts(i), open=p, high=p + 0.4, low=p - 0.1, close=p + 0.3, volume=1000))
    return rows


def _rows_twin_no_break() -> list[dict]:
    """Twin peaks present but the final bar closes ABOVE the trough — no neckline break.
    Final bar high stays below HIGH2 so HIGH2 remains a local high; only the break gate fails."""
    rows = _rows_double_top()
    rows[-1] = dict(timestamp_et=_ts(9), open=737.8, high=738.2, low=737.3, close=738.0, volume=1450)
    return rows


# ── Offline ───────────────────────────────────────────────────────────────────

def run_offline() -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, note: str) -> None:
        results.append({"name": name, "pass": bool(ok), "note": note})

    # T1 — clean M in RTH fires short
    _reset()
    sig = detect_double_top_setup(_make_ctx(_rows_double_top()))
    ok = (sig is not None and sig.direction == "short" and sig.setup_name == "DOUBLE_TOP"
          and sig.stop_price > sig.entry_price and abs(sig.metadata.get("neckline", 0) - 737.0) < 0.01)
    record("T1_clean_M_fires_short", ok,
           f"dir={sig.direction} conf={sig.confidence} stop={sig.stop_price:.2f} neck={sig.metadata.get('neckline')}"
           if sig else "None (expected a short)")

    # T2 — monotonic uptrend, no pattern
    _reset()
    sig = detect_double_top_setup(_make_ctx(_rows_no_pattern()))
    record("T2_no_pattern_none", sig is None, "None (PASS)" if sig is None else f"FIRED {sig.direction}")

    # T3 — twin peaks but no neckline break (close above trough)
    _reset()
    sig = detect_double_top_setup(_make_ctx(_rows_twin_no_break()))
    record("T3_twin_no_break_none", sig is None, "None (PASS)" if sig is None else f"FIRED {sig.direction}")

    # T4 — clean M outside RTH (08:35 start -> last bar 09:20 < 09:35)
    _reset()
    sig = detect_double_top_setup(_make_ctx(_rows_double_top(hour=8, minute=35)))
    record("T4_outside_rth_none", sig is None, "None (PASS)" if sig is None else f"FIRED at {sig.reason[:20]}")

    # T5 — cooldown: identical second call suppressed; re-fires once the cooldown elapses
    _reset()
    sig_a = detect_double_top_setup(_make_ctx(_rows_double_top()))
    sig_b = detect_double_top_setup(_make_ctx(_rows_double_top()))           # elapsed 0 < cooldown
    _dt._last_signal_time = _ts(9) - dt.timedelta(minutes=_COOLDOWN_MINUTES + 1)  # push past cooldown
    sig_c = detect_double_top_setup(_make_ctx(_rows_double_top()))
    ok = sig_a is not None and sig_b is None and sig_c is not None
    record("T5_cooldown_suppress_then_refire", ok,
           f"a={'fire' if sig_a else 'none'} b={'fire' if sig_b else 'none'} c={'fire' if sig_c else 'none'} "
           f"(cooldown={_COOLDOWN_MINUTES}m)")

    # T6 — metadata contract (the honesty markers + neckline)
    _reset()
    sig = detect_double_top_setup(_make_ctx(_rows_double_top()))
    md = sig.metadata if sig else {}
    ok = (sig is not None and "no_edge_gates" in md and "bulkowski_caveat" in md
          and "op21_live_gate" in md and "neckline" in md and "confidence_score" in md)
    record("T6_metadata_contract", ok,
           f"keys={sorted(k for k in md if k in {'no_edge_gates','bulkowski_caveat','op21_live_gate','neckline','confidence_score'})}"
           if sig else "None")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['name']:38s} {r['note']}")

    return {
        "mode": "offline",
        "constants_verified": {
            "RTH_START": str(_RTH_START),
            "RTH_END": str(_RTH_END),
            "COOLDOWN_MINUTES": _COOLDOWN_MINUTES,
            "WINDOW_BARS": _WINDOW_BARS,
        },
        "design_note": (
            "WATCH_ONLY mirror of double_bottom. NO edge-derived gates by design — gathers an "
            "unbiased SPY 5m double-top sample. Bulkowski 25% is daily/weekly; re-measure on SPY "
            "5m before any live trigger. OP-21 live gate 0/3."
        ),
        "tests": results,
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
    }


# ── Live audit (informational, network-free) ──────────────────────────────────

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        print("  [SKIP] watcher-observations.jsonl not found")
        return {"mode": "live", "all_pass": True, "total_obs": 0}

    n_obs = 0
    shorts = 0
    with obs_path.open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("watcher_name") != "double_top":
                continue
            n_obs += 1
            if o.get("direction") == "short":
                shorts += 1

    print(f"  [AUDIT] double_top observations: N={n_obs} (all should be direction=short: {shorts})")
    return {"mode": "live", "all_pass": True, "total_obs": n_obs, "short_obs": shorts}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    args = parser.parse_args(argv)

    print("\n[v48] DOUBLE_TOP watcher gate — bearish mirror of double_bottom (WATCH_ONLY, OP-21 0/3)")
    rc = 0
    if args.mode in ("offline", "both"):
        result = run_offline()
        status = "PASS" if result["all_pass"] else "FAIL"
        print(f"\n  [{status}] offline: {result['passed']}/{result['total']} tests passed")
        if not result["all_pass"]:
            rc = 1
    if args.mode in ("live", "both"):
        run_live()
    return rc


if __name__ == "__main__":
    sys.exit(main())
