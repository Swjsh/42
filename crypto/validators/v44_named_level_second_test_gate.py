"""v44_named_level_second_test_gate — NAMED_LEVEL_SECOND_TEST watcher correctness gate.

Background:
  2026-06-18: named_level_second_test_watcher.py ships as WATCH_ONLY.
  Detects a HIGHER-LOW (support) / LOWER-HIGH (resistance) SECOND test of a named
  ★★+ level within the session — a two-touch structural confirmation DISTINCT from
  the single-bar NAMED_LEVEL_WICK_BOUNCE (NLWB).

  Motivating case (2026-06-18 long/support):
    PML 743.35 named support — 09:45 test#1 low 743.86 bounced +$1.34, 11:45 test#2
    low 744.36 (+$0.50 higher low) closed green, 11:50 ran to 746.40 (+$2.04).

  THIS validator also guards the 2026-06-18 LEVEL-SCHEMA FIX: the watcher's level
  loader (via backtest.lib.watchers.level_source.load_named_levels) must derive
  ★-strength from the schema-v3 `tier` field when the planned `strength.stars`
  object is ABSENT (it is, in the live key-levels.json). Before the fix the loader
  read `strength.stars` directly → always 0 → empty level list → the watcher fired
  on NOTHING live. T5 below loads a fixture key-levels.json carrying only `tier`
  fields and asserts the structural levels load (and the round-number/psychological
  level is excluded).

Offline tests (6 total):
  T1  Higher-low SECOND test of named support, green bar  → WatcherSignal(long)
  T2  LOWER low (broke support, not a higher low)         → None
  T3  Single touch (no qualifying first-test bounce)      → None
  T4  Lower-high SECOND test of named resistance, red bar → WatcherSignal(short)
  T5  tier→stars level loading: fixture key-levels.json with tier-only fields loads
      structural support (Carry type=support) + resistance (Active/Carry) levels,
      AND excludes the psychological round-number level (capped at ★).
  T6  Empty level cache (no ★★+ levels) → None (gate-bypass guard)

Live audit (informational, non-blocking):
  Scan watcher-observations.jsonl for named_level_second_test_watcher rows; report
  confidence distribution + any structure_margin_dollars < MIN_HIGHER_LOW_DOLLARS
  (would indicate a higher-low/lower-high gate bypass). pass=True always.

Exit code:
  0 — all offline tests PASS
  1 — any offline test FAIL
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backtest.lib.filters import BarContext
from backtest.lib.watchers import level_source
from backtest.lib.watchers import named_level_second_test_watcher as _nlst
from backtest.lib.watchers.named_level_second_test_watcher import (
    detect_named_level_second_test_setup,
    ENTRY_TIME_START,
    ENTRY_TIME_END,
    MIN_HIGHER_LOW_DOLLARS,
    _MIN_STARS,
)


_DAY = "2026-06-18"
_PML = 743.35       # the motivating-case named support
_RES = 750.62       # a named resistance for the short-side test


# ---------------------------------------------------------------------------
# BarContext + level-injection helpers
# ---------------------------------------------------------------------------

def _ts(h: int, m: int) -> dt.datetime:
    return dt.datetime(2026, 6, 18, h, m)


def _make_ctx(rows: list[dict], *, vix: float = 17.0, vol_baseline: float = 1000.0) -> BarContext:
    df = pd.DataFrame(rows)
    cur = df.iloc[-1]
    return BarContext(
        bar_idx=len(df) - 1,
        timestamp_et=cur["timestamp_et"],
        bar=cur,
        prior_bars=df,            # full history INCLUDING current at [-1]
        ribbon_now=None,
        ribbon_history=[],
        vix_now=vix,
        vix_prior=vix,
        vol_baseline_20=vol_baseline,
        range_baseline_20=0.5,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
    )


def _reset_and_force(supports: list[float], resistances: list[float]) -> None:
    """Reset cooldown + inject a deterministic level set (bypasses file I/O)."""
    _nlst._last_signal_time = None
    _nlst._cached_support = sorted(set(supports))
    _nlst._cached_resistance = sorted(set(resistances))
    _nlst._cached_levels_date = _DAY


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rows_higher_low_long() -> list[dict]:
    """Higher-low second test of PML support → should fire long."""
    rows = [
        dict(timestamp_et=_ts(9, 35), open=746.0, high=746.3, low=745.7, close=746.1, volume=900),
        dict(timestamp_et=_ts(9, 40), open=746.1, high=746.4, low=745.5, close=745.6, volume=950),
        # test#1 @09:45 — low 743.86 within $0.75 of 743.35, bounce +$1.34
        dict(timestamp_et=_ts(9, 45), open=745.0, high=745.2, low=743.86, close=744.2, volume=1500),
        dict(timestamp_et=_ts(9, 50), open=744.2, high=745.20, low=744.0, close=745.0, volume=1300),
    ]
    for hh, mm in [(10, 0), (10, 30), (11, 0), (11, 30), (11, 40)]:
        rows.append(dict(timestamp_et=_ts(hh, mm), open=745.5, high=746.0, low=744.9, close=745.4, volume=800))
    # test#2 @11:45 — low 744.36 = +$0.50 higher low, green, vol 1.2x
    rows.append(dict(timestamp_et=_ts(11, 45), open=744.6, high=745.0, low=744.36, close=744.95, volume=1200))
    return rows


def _rows_lower_low() -> list[dict]:
    """Same history as the long fixture but current bar prints a LOWER low → no fire."""
    rows = _rows_higher_low_long()[:-1]
    rows.append(dict(timestamp_et=_ts(11, 45), open=744.0, high=744.3, low=743.50, close=744.1, volume=1200))
    return rows


def _rows_single_touch() -> list[dict]:
    """Current bar is the FIRST touch of the level — no prior bounce → no fire."""
    rows = []
    for k in range(0, 8):
        rows.append(dict(timestamp_et=_ts(11, 0 + k), open=746.0, high=746.3, low=745.6, close=746.0, volume=900))
    rows.append(dict(timestamp_et=_ts(11, 45), open=744.0, high=744.8, low=743.9, close=744.7, volume=1200))
    return rows


def _rows_lower_high_short() -> list[dict]:
    """Lower-high second test of named resistance → should fire short."""
    rows = [
        dict(timestamp_et=_ts(9, 35), open=748.0, high=748.5, low=747.8, close=748.2, volume=900),
        # test#1 @09:40 — high 750.50 within zone of 750.62, rejects -$1.0
        dict(timestamp_et=_ts(9, 40), open=749.5, high=750.50, low=749.4, close=749.6, volume=1500),
        dict(timestamp_et=_ts(9, 45), open=749.6, high=749.8, low=749.50, close=749.55, volume=1300),
    ]
    for mm in (0, 10, 20, 30):
        rows.append(dict(timestamp_et=_ts(10, mm), open=749.0, high=749.5, low=748.8, close=749.2, volume=800))
    # test#2 @10:40 — high 750.12 = $0.38 lower high, red, vol confirmed
    rows.append(dict(timestamp_et=_ts(10, 40), open=749.9, high=750.12, low=749.3, close=749.4, volume=1200))
    return rows


_FIXTURE_KEY_LEVELS = {
    "schema_version": 3,
    "for_session": _DAY,
    "levels": [
        # tier-only levels (NO strength.stars) — exactly the live-file schema shape.
        {"price": 743.35, "type": "support", "role": "broken_to_support", "tier": "Carry"},
        {"price": 750.62, "type": "resistance", "role": "support_broken_to_resistance", "tier": "Active"},
        {"price": 748.00, "type": "resistance", "role": None, "tier": "Carry"},
        # psychological round number — MUST be excluded (capped at ★, < min_stars=2).
        {"price": 750.00, "type": "psychological", "role": None, "tier": "Reference",
         "is_round_number": True},
    ],
}


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, note: str) -> None:
        results.append({"name": name, "pass": bool(ok), "note": note})

    # T1 — higher-low second test of support → long
    _reset_and_force([_PML], [747.0, 748.0])
    sig = detect_named_level_second_test_setup(_make_ctx(_rows_higher_low_long()))
    ok1 = (
        sig is not None and sig.direction == "long"
        and sig.setup_name == "NAMED_LEVEL_SECOND_TEST"
        and sig.watcher_name == "named_level_second_test_watcher"
        and abs(sig.metadata.get("named_level", 0) - _PML) < 0.01
    )
    record("T1_higher_low_fires_long", ok1,
           f"dir={sig.direction if sig else None} level={sig.metadata.get('named_level') if sig else None} "
           f"conf={sig.confidence if sig else None}")

    # T2 — lower low → no fire
    _reset_and_force([_PML], [747.0, 748.0])
    sig = detect_named_level_second_test_setup(_make_ctx(_rows_lower_low()))
    record("T2_lower_low_no_fire", sig is None,
           "None (PASS)" if sig is None else f"FIRED dir={sig.direction} (wrong)")

    # T3 — single touch (no first-test bounce) → no fire
    _reset_and_force([_PML], [747.0, 748.0])
    sig = detect_named_level_second_test_setup(_make_ctx(_rows_single_touch()))
    record("T3_single_touch_no_fire", sig is None,
           "None (PASS)" if sig is None else f"FIRED dir={sig.direction} (wrong)")

    # T4 — lower-high second test of resistance → short
    _reset_and_force([743.35], [_RES])
    sig = detect_named_level_second_test_setup(_make_ctx(_rows_lower_high_short()))
    ok4 = (
        sig is not None and sig.direction == "short"
        and abs(sig.metadata.get("named_level", 0) - _RES) < 0.01
    )
    record("T4_lower_high_fires_short", ok4,
           f"dir={sig.direction if sig else None} level={sig.metadata.get('named_level') if sig else None} "
           f"conf={sig.confidence if sig else None}")

    # T5 — tier→stars level loading from a fixture key-levels.json (the schema-fix guard)
    ok5, note5 = _check_tier_stars_loading()
    record("T5_tier_to_stars_loading", ok5, note5)

    # T6 — empty cache (no ★★+ levels) → no fire (gate-bypass guard)
    _reset_and_force([], [])
    sig = detect_named_level_second_test_setup(_make_ctx(_rows_higher_low_long()))
    record("T6_empty_cache_no_fire", sig is None,
           "None (PASS)" if sig is None else f"FIRED dir={sig.direction} (wrong)")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['name']:32s} {r['note']}")

    return {
        "mode": "offline",
        "evidence_basis": (
            "2026-06-18 PML 743.35 double test (09:45 → 11:45 +$0.50 higher low → 11:50 746.40). "
            "T5 guards the 2026-06-18 level-schema fix: tier→stars derivation when strength.stars "
            "is absent; psychological/round-number levels capped at ★."
        ),
        "constants_verified": {
            "ENTRY_TIME_START": str(ENTRY_TIME_START),
            "ENTRY_TIME_END": str(ENTRY_TIME_END),
            "MIN_HIGHER_LOW_DOLLARS": MIN_HIGHER_LOW_DOLLARS,
            "MIN_STARS": _MIN_STARS,
        },
        "tests": results,
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
    }


def _check_tier_stars_loading() -> tuple[bool, str]:
    """Write a fixture key-levels.json (tier-only, no strength.stars) and assert the
    shared loader derives stars from tier — structural levels load, round number excluded.
    """
    original_path = level_source._KEY_LEVELS_PATH
    tmpdir = tempfile.mkdtemp(prefix="v44_keylevels_")
    fixture = Path(tmpdir) / "key-levels.json"
    fixture.write_text(json.dumps(_FIXTURE_KEY_LEVELS), encoding="utf-8")
    try:
        level_source._KEY_LEVELS_PATH = fixture
        level_source.reset_cache()
        supports = level_source.load_named_levels(
            _DAY, roles=frozenset({"support", "broken_to_support"}),
            types=frozenset({"support"}), min_stars=2,
        )
        resistances = level_source.load_named_levels(
            _DAY, roles=frozenset({"resistance", "support_broken_to_resistance"}),
            types=frozenset({"resistance"}), min_stars=2,
        )
        sup_ok = supports == [743.35]
        res_ok = resistances == [748.0, 750.62]
        round_excluded = 750.00 not in supports and 750.00 not in resistances
        ok = sup_ok and res_ok and round_excluded
        note = (
            f"supports={supports} (want [743.35]) resistances={resistances} "
            f"(want [748.0, 750.62]) round_750_excluded={round_excluded}"
        )
        return ok, note
    finally:
        level_source._KEY_LEVELS_PATH = original_path
        level_source.reset_cache()
        # Restore the watcher's injected state so later tests are unaffected.
        _nlst._cached_levels_date = None


# ---------------------------------------------------------------------------
# Live audit
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        print("  [SKIP] watcher-observations.jsonl not found")
        return {"mode": "live", "all_pass": True, "total_obs": 0}

    obs: list[dict] = []
    margin_bypasses: list[dict] = []
    with obs_path.open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("watcher_name") != "named_level_second_test_watcher":
                continue
            obs.append(o)
            margin = (o.get("metadata") or {}).get("structure_margin_dollars")
            if margin is not None and margin < MIN_HIGHER_LOW_DOLLARS:
                margin_bypasses.append({
                    "date": o.get("date", o.get("bar_timestamp_et", "?")),
                    "structure_margin_dollars": margin,
                })

    from collections import Counter
    conf = Counter(o.get("confidence", "unknown") for o in obs)
    pnl = [o.get("would_be_pnl_dollars") for o in obs if o.get("would_be_pnl_dollars") is not None]
    wins = sum(1 for p in pnl if p > 0)
    wr = wins / len(pnl) * 100 if pnl else 0.0

    print(f"  [AUDIT] named_level_second_test_watcher obs: N={len(obs)}")
    print(f"          conf: high={conf.get('high',0)} medium={conf.get('medium',0)} low={conf.get('low',0)}")
    print(f"          structure-margin gate bypasses (< {MIN_HIGHER_LOW_DOLLARS}): {len(margin_bypasses)}")
    if pnl:
        print(f"          graded: N={len(pnl)} WR={wr:.1f}% avg=${sum(pnl)/len(pnl):.2f}")
    else:
        print("          graded: 0 (watcher recently shipped — live accumulation in progress)")
    print(f"          promotion status: WATCH_ONLY (live gate: {len(obs)}/3 J confirmations)")

    return {
        "mode": "live",
        "all_pass": True,
        "total_obs": len(obs),
        "conf_high": conf.get("high", 0),
        "conf_medium": conf.get("medium", 0),
        "conf_low": conf.get("low", 0),
        "margin_gate_bypasses": len(margin_bypasses),
        "graded_n": len(pnl),
        "wr_pct": round(wr, 1),
        "promotion_status": "WATCH_ONLY — needs 3+ J live confirmations",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live", "both"], default="offline")
    args = parser.parse_args(argv)

    print(f"\n[v44] NAMED_LEVEL_SECOND_TEST watcher gate — mode={args.mode}")
    print(f"      TIME_WINDOW = {ENTRY_TIME_START}–{ENTRY_TIME_END} ET  "
          f"MIN_HIGHER_LOW = ${MIN_HIGHER_LOW_DOLLARS:.2f}  MIN_STARS = {_MIN_STARS}")

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
