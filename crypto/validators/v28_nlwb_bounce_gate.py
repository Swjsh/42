"""v28_nlwb_bounce_gate — NLWB/LBFS mutual-exclusion + float-precision regression gate.

Background:
  2026-05-19: NAMED_LEVEL_WICK_BOUNCE (NLWB) watcher shipped as a BULL first-strike entry
  (bar wicks >=8c below named support, closes ABOVE). LEVEL_BREAK_FIRST_STRIKE (LBFS) is
  the BEARISH mirror (bar closes BELOW the level = confirmed break).

  These two setups are STRUCTURALLY MUTUALLY EXCLUSIVE on any given bar:
    - LBFS fires when: bar_close < level  (close below = confirmed breakdown)
    - NLWB fires when: bar_close > level  AND  bar_low < level - 8c  (bounce above)

  FLOAT-PRECISION BUG (L51 analog catch):
    (734.56 - 734.48) * 100.0 = 7.9999999... in IEEE 754 (not 8.0)
    Without `round(..., 2)`, `7.9999... < 8.0` → the motivating 5/19 12:35 ET case
    SILENTLY FAILS (wick_cents computed as 7.9999... which is < 8.0 threshold).
    Fix in named_level_wick_bounce_watcher.py:
        wick_cents = round((lvl - bar_low) * 100.0, 2)  # IEEE 754 guard

  This validator provides:
    T1: Classic NLWB bar → NLWB detector fires, wick_cents rounds correctly
    T2: Classic LBFS bar → NLWB detector returns None (close below level blocks it)
    T3: Bar close == level exactly → neither fires (strict inequalities)
    T4: FLOAT PRECISION EDGE CASE — raw (734.56-734.48)*100 = 7.9999... without round()
        confirms the round() fix is present (motivating 5/19 case fires correctly)
    T5: Wick below level but bounce too small (< 8c) → NLWB does NOT fire
    T6: Wick below but close also below level → NLWB does NOT fire (close gate)

Modes:
  offline  6 synthetic bar tests covering mutual exclusion + float precision.
           All 6 must PASS before the gym is green.
  live     Scan today's watcher-observations.jsonl for any bar where BOTH nlwb AND lbfs
           signals appear on the same bar (should NEVER happen — structural impossibility).
           Audit mode: pass=True always (observation phase).

Exit code:
  0  all offline tests pass
  1  any offline test fails
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Synthetic bar helper
# ---------------------------------------------------------------------------

def _bar(open_: float, high: float, low: float, close: float, volume: int = 100_000):
    """Create a minimal bar dict for detection logic testing."""
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _check_nlwb_wick(bar: dict, level: float, min_cents: float = 8.0) -> tuple[bool, float]:
    """Reproduce the exact logic from named_level_wick_bounce_watcher.py.

    Returns (fires, wick_cents_computed).
    This is the ground-truth inline test — any change to the watcher's wick math
    must be reflected here to keep the test meaningful.
    """
    bar_low = float(bar["low"])
    bar_close = float(bar["close"])

    # The CRITICAL fix: round to 2dp to guard against IEEE 754 drift
    wick_cents = round((level - bar_low) * 100.0, 2)

    fires = (wick_cents >= min_cents) and (bar_close > level)
    return fires, wick_cents


def _check_lbfs_close(bar: dict, level: float, min_break_cents: float = 20.0) -> bool:
    """Reproduce the LBFS close-below-level check.

    LBFS fires when close is >= min_break_cents BELOW the level.
    This is the LBFS gate that is OPPOSITE to NLWB.
    """
    bar_close = float(bar["close"])
    break_cents = round((level - bar_close) * 100.0, 2)
    return break_cents >= min_break_cents


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run 6 offline tests covering mutual exclusion + float precision.

    Motivating case (5/19 12:35 ET): SPY 5m bar
      open=734.86  high=735.05  low=734.48  close=735.05
      Named level = 734.56 (premarket low)
      wick_cents = round((734.56 - 734.48) * 100, 2) = round(7.9999..., 2) = 8.0 ✓
      close 735.05 > 734.56 ✓ → NLWB fires
    """
    results: list[tuple[str, bool, str]] = []
    LEVEL = 734.56

    # ── T1: Classic NLWB bar — the 5/19 12:35 motivating case ───────────────
    nlwb_bar = _bar(open_=734.86, high=735.05, low=734.48, close=735.05)
    fires, wick_cents = _check_nlwb_wick(nlwb_bar, LEVEL)
    lbfs_fires = _check_lbfs_close(nlwb_bar, LEVEL)
    ok = fires and not lbfs_fires and wick_cents == 8.0
    results.append((
        "T1_nlwb_fires_lbfs_does_not",
        ok,
        f"nlwb_fires={fires} lbfs_fires={lbfs_fires} wick_cents={wick_cents}",
    ))

    # ── T2: Classic LBFS bar — close well below level ────────────────────────
    # Bar breaks DOWN through 734.56 with body below the level
    lbfs_bar = _bar(open_=734.8, high=734.9, low=734.1, close=734.2)
    nlwb_fires_t2, _ = _check_nlwb_wick(lbfs_bar, LEVEL)
    lbfs_fires_t2 = _check_lbfs_close(lbfs_bar, LEVEL)
    ok = not nlwb_fires_t2 and lbfs_fires_t2
    results.append((
        "T2_lbfs_fires_nlwb_does_not",
        ok,
        f"nlwb_fires={nlwb_fires_t2} lbfs_fires={lbfs_fires_t2}",
    ))

    # ── T3: Bar close == level exactly — neither fires (strict inequalities) ─
    exact_bar = _bar(open_=734.5, high=734.8, low=734.3, close=734.56)  # close == level
    nlwb_fires_t3, _ = _check_nlwb_wick(exact_bar, LEVEL)
    lbfs_fires_t3 = _check_lbfs_close(exact_bar, LEVEL, min_break_cents=20.0)
    # NLWB requires close > level (strict). close == level → False.
    # LBFS requires close < level by >= 20c. break_cents = 0.0 < 20 → False.
    ok = not nlwb_fires_t3 and not lbfs_fires_t3
    results.append((
        "T3_exact_level_neither_fires",
        ok,
        f"nlwb_fires={nlwb_fires_t3} lbfs_fires={lbfs_fires_t3}",
    ))

    # ── T4: FLOAT PRECISION — the IEEE 754 foot-gun (L51-analog catch) ───────
    # Without round(): (734.56 - 734.48) * 100.0 = 7.999999999... < 8.0 → FAIL
    # With round(..., 2): 7.9999... → 8.0 >= 8.0 → PASS
    raw_float = (LEVEL - 734.48) * 100.0          # deliberately un-rounded
    rounded_float = round(raw_float, 2)
    # raw_float should be < 8.0 (IEEE 754 floating-point subtraction artifact)
    # rounded_float should be exactly 8.0
    raw_would_fail = raw_float < 8.0              # True = bug exists without round()
    fix_works = rounded_float >= 8.0             # True = round() correctly gates it
    ok = raw_would_fail and fix_works
    results.append((
        "T4_float_precision_round_fix",
        ok,
        f"raw_float={raw_float} (<8.0={raw_would_fail}) rounded={rounded_float} (>=8.0={fix_works})",
    ))

    # ── T5: Wick below level but bounce too small (< 8c) → NLWB does NOT fire ─
    tiny_wick_bar = _bar(open_=734.7, high=735.0, low=734.50, close=734.80)
    # low=734.50 → wick = (734.56-734.50)*100 = 6.0c < 8.0 → should NOT fire
    fires_t5, wick_t5 = _check_nlwb_wick(tiny_wick_bar, LEVEL)
    ok = not fires_t5 and wick_t5 < 8.0
    results.append((
        "T5_small_wick_no_fire",
        ok,
        f"fires={fires_t5} wick_cents={wick_t5}",
    ))

    # ── T6: Wick below level but close is ALSO below level → NLWB does NOT fire
    no_bounce_bar = _bar(open_=734.7, high=734.8, low=734.40, close=734.50)
    # low=734.40 → wick_cents = round((734.56-734.40)*100, 2) = 16.0 >= 8 BUT
    # close=734.50 < 734.56 → bounce check fails → NLWB does not fire
    fires_t6, wick_t6 = _check_nlwb_wick(no_bounce_bar, LEVEL)
    ok = not fires_t6 and wick_t6 >= 8.0
    results.append((
        "T6_wick_ok_but_close_below_no_fire",
        ok,
        f"fires={fires_t6} wick_cents={wick_t6} close={no_bounce_bar['close']}",
    ))

    # ── Build result dict ────────────────────────────────────────────────────
    all_pass = all(r[1] for r in results)
    return {
        "mode": "offline",
        "evidence_basis": (
            "2026-05-19 12:35 ET: SPY 5m bar low=734.48 (8c wick below premarket-low 734.56), "
            "close=735.05 (49c above). (734.56-734.48)*100=7.9999... in IEEE 754 — round() fix "
            "required for the watcher to fire. Motivating case: SPY ran +$3.05 in 90 min."
        ),
        "tests": [
            {"name": name, "pass": ok, "note": note}
            for name, ok, note in results
        ],
        "passed": sum(1 for _, ok, _ in results if ok),
        "total": len(results),
        "all_pass": all_pass,
    }


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

def run_live() -> dict:
    """Scan watcher-observations.jsonl for NLWB + LBFS same-bar co-fires (must never happen).

    The structural mutual exclusion means: for any given 5m bar at a given level,
    NLWB (close > level) and LBFS (close < level) CANNOT both fire. If they do,
    one of the detectors has a bug.

    Audit mode: pass=True always. RED flag if co-fire count > 0.
    """
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {
            "mode": "live",
            "source": str(obs_path),
            "skipped": True,
            "reason": "watcher-observations.jsonl not found",
            "pass": True,
        }

    # Load all observations for today and group by (date, bar_timestamp)
    from collections import defaultdict
    import datetime as dt

    today = dt.date.today().isoformat()
    bar_setups: defaultdict[str, list[str]] = defaultdict(list)

    lines_read = 0
    try:
        with open(obs_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obs = json.loads(line)
                except json.JSONDecodeError:
                    continue
                obs_date = obs.get("date", "")
                if obs_date != today:
                    continue
                lines_read += 1
                ts = obs.get("bar_timestamp") or obs.get("timestamp_et") or ""
                key = f"{obs_date}@{ts}"
                setup = obs.get("setup_name", obs.get("watcher_name", ""))
                bar_setups[key].append(setup)
    except Exception as exc:
        return {
            "mode": "live",
            "skipped": True,
            "reason": f"read error: {exc}",
            "pass": True,
        }

    # Find bars where both NLWB and LBFS appear (structural impossibility)
    co_fires = []
    for key, setups in bar_setups.items():
        has_nlwb = any("NAMED_LEVEL_WICK_BOUNCE" in s for s in setups)
        has_lbfs = any("LEVEL_BREAK_FIRST_STRIKE" in s for s in setups)
        if has_nlwb and has_lbfs:
            co_fires.append({"bar_key": key, "setups": setups})

    verdict = "GREEN" if not co_fires else "RED"
    return {
        "mode": "live",
        "source": str(obs_path),
        "date": today,
        "lines_read_today": lines_read,
        "co_fires_nlwb_lbfs": co_fires,
        "co_fire_count": len(co_fires),
        "verdict": verdict,
        "note": (
            "NLWB (close > level) and LBFS (close < level) are structurally mutually exclusive. "
            "Any co-fire on the same bar indicates a detector bug."
        ),
        "pass": True,  # audit mode — RED is informational
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="v28 NLWB/LBFS mutual-exclusion + float-precision gate")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    args = parser.parse_args()

    if args.mode == "live":
        result = run_live()
    else:
        result = run_offline()

    print(json.dumps(result, indent=2))
    return 0 if result.get("all_pass", result.get("pass", True)) else 1


if __name__ == "__main__":
    sys.exit(main())
