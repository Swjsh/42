"""v45_stairstep_continuation_gate — STAIRSTEP_CONTINUATION watcher correctness gate.

Background:
  2026-06-18: stairstep_continuation_watcher.py ships as WATCH_ONLY.
  Detects a continuation setup at a BROKEN named level where successive retests from
  the broken side form a STRICT monotonic stairstep — progressively LOWER highs
  (descending → short / puts) or progressively HIGHER lows (ascending → long / calls).

  Motivating case (the missed 2026-05-07 735.40 sequence): 735.40 broke down, three
  retests printed strictly lower highs 736.12 → 735.61 → 735.41 (LH-LH-LH); SPY then
  continued -$5.65 to 729.75. The engine bought calls at 12:30 (counter-trend trap) —
  J's eye saw the stairstep the engine missed.

  Like the other named-level watchers, the loader derives ★-strength from the
  schema-v3 `tier` field (via backtest.lib.watchers.level_source) since the live
  key-levels.json has no `strength.stars`. Offline tests inject the level cache
  directly (deterministic — no key-levels.json dependency).

Offline tests (5 total):
  T1  Strict monotonic LH-LH-LH descending at a broken-to-resistance level, red
      confirming bar → WatcherSignal(short)
  T2  Non-monotonic retests (middle high is higher) → None
  T3  Green confirming bar on the descending setup (no continuation) → None
  T4  Strict monotonic higher-lows ascending at a broken-to-support level, green
      confirming bar → WatcherSignal(long)
  T5  Empty level cache (no ★★+ levels) → None (gate-bypass guard)

Live audit (informational, non-blocking):
  Scan watcher-observations.jsonl for stairstep_continuation_watcher rows; report
  confidence distribution + any retest_count < MIN_RETESTS (would indicate the
  monotonic-stairstep gate was bypassed). pass=True always.

Exit code:
  0 — all offline tests PASS
  1 — any offline test FAIL
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
from backtest.lib.watchers import stairstep_continuation_watcher as _ss
from backtest.lib.watchers.stairstep_continuation_watcher import (
    detect_stairstep_continuation_setup,
    ENTRY_TIME_START,
    ENTRY_TIME_END,
    MIN_RETESTS,
    _MIN_STARS,
)


_DAY = "2026-05-07"
_RES_LEVEL = 735.40       # the 5/07 broken-to-resistance level
_SUP_LEVEL = 740.00       # an ascending broken-to-support level


def _ts(h: int, m: int) -> dt.datetime:
    return dt.datetime(2026, 5, 7, h, m)


def _make_ctx(rows: list[dict], *, vix: float = 18.0) -> BarContext:
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


def _reset_and_force(all_levels: list[float], broken_res: list[float], broken_sup: list[float]) -> None:
    """Reset cooldown + inject a deterministic level set (bypasses file I/O)."""
    _ss._last_signal_time = None
    _ss._cached_all = sorted(set(all_levels))
    _ss._cached_broken_res = sorted(set(broken_res))
    _ss._cached_broken_sup = sorted(set(broken_sup))
    _ss._cached_levels_date = _DAY


# ---------------------------------------------------------------------------
# Fixtures (reuse the watcher's proven self-test geometry)
# ---------------------------------------------------------------------------

def _rows_descending_short() -> list[dict]:
    """Break down + LH-LH-LH 736.12 → 735.61 → 735.41 + red confirming bar → short."""
    return [
        dict(timestamp_et=_ts(11, 35), open=735.5, high=735.6, low=734.7, close=734.90, volume=1500),
        dict(timestamp_et=_ts(11, 40), open=734.9, high=736.12, low=734.8, close=735.10, volume=1200),
        dict(timestamp_et=_ts(11, 45), open=735.0, high=735.2, low=734.5, close=734.7, volume=900),
        dict(timestamp_et=_ts(11, 50), open=734.7, high=735.61, low=734.6, close=735.00, volume=1100),
        dict(timestamp_et=_ts(11, 55), open=735.0, high=735.1, low=734.3, close=734.5, volume=850),
        dict(timestamp_et=_ts(12, 0), open=734.5, high=735.41, low=734.4, close=734.80, volume=1000),
        dict(timestamp_et=_ts(12, 5), open=734.8, high=734.9, low=734.0, close=734.20, volume=1300),
    ]


def _rows_non_monotonic() -> list[dict]:
    """Highs 735.61 → 736.12 → 735.41 (middle higher) → strict run < MIN_RETESTS → None."""
    return [
        dict(timestamp_et=_ts(11, 35), open=735.5, high=735.6, low=734.7, close=734.90, volume=1500),
        dict(timestamp_et=_ts(11, 40), open=734.9, high=735.61, low=734.8, close=735.10, volume=1200),
        dict(timestamp_et=_ts(11, 45), open=735.0, high=735.2, low=734.5, close=734.7, volume=900),
        dict(timestamp_et=_ts(11, 50), open=734.7, high=736.12, low=734.6, close=735.00, volume=1100),
        dict(timestamp_et=_ts(11, 55), open=735.0, high=735.1, low=734.3, close=734.5, volume=850),
        dict(timestamp_et=_ts(12, 0), open=734.5, high=735.41, low=734.4, close=734.80, volume=1000),
        dict(timestamp_et=_ts(12, 5), open=734.8, high=734.9, low=734.0, close=734.20, volume=1300),
    ]


def _rows_green_confirm() -> list[dict]:
    """Descending stairstep but confirming bar closes GREEN → no continuation → None."""
    rows = _rows_descending_short()[:-1]
    rows.append(dict(timestamp_et=_ts(12, 5), open=734.2, high=735.0, low=734.1, close=734.90, volume=1300))
    return rows


def _rows_ascending_long() -> list[dict]:
    """Break up + higher-lows 739.40 → 739.70 → 739.95 + green confirming bar → long."""
    return [
        dict(timestamp_et=_ts(10, 0), open=739.8, high=740.6, low=739.7, close=740.30, volume=1500),
        dict(timestamp_et=_ts(10, 5), open=740.3, high=740.5, low=739.40, close=740.10, volume=1200),
        dict(timestamp_et=_ts(10, 10), open=740.1, high=740.7, low=740.0, close=740.5, volume=900),
        dict(timestamp_et=_ts(10, 15), open=740.5, high=740.8, low=739.70, close=740.20, volume=1100),
        dict(timestamp_et=_ts(10, 20), open=740.2, high=740.9, low=740.1, close=740.6, volume=850),
        dict(timestamp_et=_ts(10, 25), open=740.6, high=741.0, low=739.95, close=740.40, volume=1000),
        dict(timestamp_et=_ts(10, 30), open=740.4, high=741.3, low=740.35, close=741.20, volume=1300),
    ]


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, note: str) -> None:
        results.append({"name": name, "pass": bool(ok), "note": note})

    # T1 — strict descending LH-LH-LH → short
    _reset_and_force([_RES_LEVEL, 729.75, 732.0], [_RES_LEVEL], [])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_descending_short()))
    ok1 = (
        sig is not None and sig.direction == "short"
        and sig.setup_name == "STAIRSTEP_CONTINUATION"
        and sig.watcher_name == "stairstep_continuation_watcher"
        and sig.metadata.get("retest_count", 0) >= MIN_RETESTS
    )
    record("T1_descending_fires_short", ok1,
           f"dir={sig.direction if sig else None} "
           f"seq={sig.metadata.get('retest_sequence') if sig else None} "
           f"conf={sig.confidence if sig else None}")

    # T2 — non-monotonic → no fire
    _reset_and_force([_RES_LEVEL, 729.75, 732.0], [_RES_LEVEL], [])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_non_monotonic()))
    record("T2_non_monotonic_no_fire", sig is None,
           "None (PASS)" if sig is None else f"FIRED dir={sig.direction} (wrong)")

    # T3 — green confirming bar → no fire
    _reset_and_force([_RES_LEVEL, 729.75, 732.0], [_RES_LEVEL], [])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_green_confirm()))
    record("T3_green_confirm_no_fire", sig is None,
           "None (PASS)" if sig is None else f"FIRED dir={sig.direction} (wrong)")

    # T4 — strict ascending higher-lows → long
    _reset_and_force([_SUP_LEVEL, 743.0, 745.0], [], [_SUP_LEVEL])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_ascending_long()))
    ok4 = (
        sig is not None and sig.direction == "long"
        and sig.metadata.get("retest_count", 0) >= MIN_RETESTS
    )
    record("T4_ascending_fires_long", ok4,
           f"dir={sig.direction if sig else None} "
           f"seq={sig.metadata.get('retest_sequence') if sig else None} "
           f"conf={sig.confidence if sig else None}")

    # T5 — empty cache (no ★★+ levels) → no fire (gate-bypass guard)
    _reset_and_force([], [], [])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_descending_short()))
    record("T5_empty_cache_no_fire", sig is None,
           "None (PASS)" if sig is None else f"FIRED dir={sig.direction} (wrong)")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['name']:32s} {r['note']}")

    return {
        "mode": "offline",
        "evidence_basis": (
            "2026-05-07 735.40 LH-LH-LH (736.12 → 735.61 → 735.41) → 729.75 (-$5.65). "
            "MIN_RETESTS=3 strict-monotonic retests required; confirming bar must close "
            "the right color on the broken side."
        ),
        "constants_verified": {
            "ENTRY_TIME_START": str(ENTRY_TIME_START),
            "ENTRY_TIME_END": str(ENTRY_TIME_END),
            "MIN_RETESTS": MIN_RETESTS,
            "MIN_STARS": _MIN_STARS,
        },
        "tests": results,
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
    }


# ---------------------------------------------------------------------------
# Live audit
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        print("  [SKIP] watcher-observations.jsonl not found")
        return {"mode": "live", "all_pass": True, "total_obs": 0}

    obs: list[dict] = []
    retest_bypasses: list[dict] = []
    with obs_path.open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("watcher_name") != "stairstep_continuation_watcher":
                continue
            obs.append(o)
            n_retests = (o.get("metadata") or {}).get("retest_count")
            if n_retests is not None and n_retests < MIN_RETESTS:
                retest_bypasses.append({
                    "date": o.get("date", o.get("bar_timestamp_et", "?")),
                    "retest_count": n_retests,
                })

    from collections import Counter
    conf = Counter(o.get("confidence", "unknown") for o in obs)
    pnl = [o.get("would_be_pnl_dollars") for o in obs if o.get("would_be_pnl_dollars") is not None]
    wins = sum(1 for p in pnl if p > 0)
    wr = wins / len(pnl) * 100 if pnl else 0.0

    print(f"  [AUDIT] stairstep_continuation_watcher obs: N={len(obs)}")
    print(f"          conf: high={conf.get('high',0)} medium={conf.get('medium',0)} low={conf.get('low',0)}")
    print(f"          retest-count gate bypasses (< {MIN_RETESTS}): {len(retest_bypasses)}")
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
        "retest_gate_bypasses": len(retest_bypasses),
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

    print(f"\n[v45] STAIRSTEP_CONTINUATION watcher gate — mode={args.mode}")
    print(f"      TIME_WINDOW = {ENTRY_TIME_START}–{ENTRY_TIME_END} ET  "
          f"MIN_RETESTS = {MIN_RETESTS}  MIN_STARS = {_MIN_STARS}")

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
