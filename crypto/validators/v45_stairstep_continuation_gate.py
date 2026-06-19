"""v45_stairstep_continuation_gate — STAIRSTEP_CONTINUATION RETIREMENT gate.

>>> The STAIRSTEP_CONTINUATION watcher was RETIRED 2026-06-18 (structurally anti-J-edge). <<<
This gate now verifies the RETIREMENT holds: detect_stairstep_continuation_setup MUST return
None on every input — including the REAL, picture-perfect 2026-05-07 735.40 descending
staircase. There is NO fabricated-fixture green test; a fabricated test that "passes" on
fake data is exactly the failure mode this rewrite removes.

WHY RETIRED (full evidence in the watcher module docstring + the task report):
  1. Fabricated motivating case. The original docstring/fixture cited "736.12 → 735.61 →
     735.41" pressing 735.40 on 2026-05-07. Those bars do NOT exist in the real SPY 5m tape.
     The REAL descending highs (RTH) are 735.59 → 735.55 → 735.50 → 735.39 (11:30-11:45 ET).
  2. Local-maximum contradiction. The old _collect_descending_retests required each retest
     high to be a strict local maximum — which a clean descending staircase can never satisfy,
     so it filtered out the real stairstep and fired 0 times on the real anchor.
  3. Anti-J-edge (fatal). 2026-05-07 is a J LOSS day. Over the OP-16 anchor set (j_edge_tracker
     J_WINNERS/J_LOSERS, look-ahead-neutralized historical levels via validate_breakout_family):
         variant                          edge_capture   anti?   real-fills ATM/ITM2 exp (16mo)
         CURRENT  (local-max, shipped)      -$364.80      YES     n/a (didn't reach real-fills)
         CORRECTED(collect-all, no l-max)   -$509.57      YES     -$27.57 / -$42.54  (NEGATIVE)
     Both lose on ALL THREE of J's WIN days (4/29, 5/01, 5/04) and profit on his LOSS days.
     The corrected variant fires MORE and is MORE anti-edge. No variant clears the gate, so
     per playbook rule 5 ("setups that fail thresholds get retired, not loosened") it is retired.

Offline tests (4 total — all assert NON-firing):
  T1  REAL 2026-05-07 735.40 descending staircase (735.59→735.55→735.50→735.39) → None
  T2  REAL ascending broken-to-support shape → None
  T3  Strong descending fixture WITH the level cache injected (would have fired pre-retirement)
      → None  (proves the retirement, not just an empty-cache short-circuit)
  T4  Empty level cache → None (gate-bypass guard still holds)

Live audit (informational, non-blocking):
  Confirm no NEW stairstep_continuation_watcher observations are being emitted post-retirement.
  Any row dated after the retirement date is flagged (the detector should never fire). pass=True
  always — this is a heads-up, not a hard gate.

Exit code:
  0 — all offline retirement tests PASS (detector correctly returns None everywhere)
  1 — any offline test FAIL (detector fired = retirement broken)
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
_RES_LEVEL = 735.40       # the 5/07 broken-to-resistance level (REAL tape)
_SUP_LEVEL = 740.00       # an ascending broken-to-support level
_RETIRED_ON = dt.date(2026, 6, 18)


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
# Fixtures — REAL 2026-05-07 SPY 5m tape (no fabricated values)
# ---------------------------------------------------------------------------

def _rows_real_descending() -> list[dict]:
    """REAL RTH 11:25-11:55 ET: descending highs 735.59 → 735.55 → 735.50 → 735.39
    pressing the broken 735.40 level; SPY then continued to 729.75 (-$5.65).
    Pulled verbatim from backtest/data/spy_5m_2025-01-01_2026-06-16.csv.
    A picture-perfect descending staircase — the RETIRED detector must NOT fire.
    """
    return [
        dict(timestamp_et=_ts(11, 25), open=735.04, high=735.24, low=734.34, close=734.82, volume=12186),
        dict(timestamp_et=_ts(11, 30), open=734.87, high=735.59, low=734.87, close=735.55, volume=8113),
        dict(timestamp_et=_ts(11, 35), open=735.51, high=735.55, low=735.24, close=735.24, volume=6813),
        dict(timestamp_et=_ts(11, 40), open=735.24, high=735.50, low=735.07, close=735.32, volume=5439),
        dict(timestamp_et=_ts(11, 45), open=735.29, high=735.39, low=734.82, close=734.82, volume=4928),
        dict(timestamp_et=_ts(11, 50), open=734.83, high=734.96, low=734.55, close=734.88, volume=8612),
        dict(timestamp_et=_ts(11, 55), open=734.88, high=734.88, low=733.82, close=734.00, volume=10699),
    ]


def _rows_real_ascending() -> list[dict]:
    """Ascending broken-to-support shape (higher lows under a flipped level). The retired
    detector must NOT fire on the long side either."""
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
# Offline tests — all assert the retired detector returns None
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, note: str) -> None:
        results.append({"name": name, "pass": bool(ok), "note": note})

    # T1 — REAL descending staircase → None
    _reset_and_force([_RES_LEVEL, 729.75, 732.0], [_RES_LEVEL], [])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_real_descending()))
    record("T1_real_descending_does_not_fire", sig is None,
           "None (retired, PASS)" if sig is None else f"FIRED dir={sig.direction} (retirement broken!)")

    # T2 — REAL ascending shape → None
    _reset_and_force([_SUP_LEVEL, 743.0, 745.0], [], [_SUP_LEVEL])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_real_ascending()))
    record("T2_real_ascending_does_not_fire", sig is None,
           "None (retired, PASS)" if sig is None else f"FIRED dir={sig.direction} (retirement broken!)")

    # T3 — descending shape WITH level cache injected: pre-retirement this path could fire.
    # Asserting None here proves the RETIREMENT (the return-None stub), not an empty-cache exit.
    _reset_and_force([_RES_LEVEL, 729.75, 732.0], [_RES_LEVEL], [])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_real_descending()))
    record("T3_retirement_holds_with_levels_present", sig is None,
           "None (retired, PASS)" if sig is None else f"FIRED dir={sig.direction} (retirement broken!)")

    # T4 — empty cache → None (gate-bypass guard).
    _reset_and_force([], [], [])
    sig = detect_stairstep_continuation_setup(_make_ctx(_rows_real_descending()))
    record("T4_empty_cache_no_fire", sig is None,
           "None (PASS)" if sig is None else f"FIRED dir={sig.direction} (wrong)")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['name']:40s} {r['note']}")

    return {
        "mode": "offline",
        "retired_on": _RETIRED_ON.isoformat(),
        "retirement_reason": (
            "Structurally anti-J-edge. Over the OP-16 anchor set every variant has NEGATIVE "
            "edge_capture (shipped -$364.80 / corrected -$509.57) and is anti-correlated with "
            "J's edge (loses on WIN days 4/29-5/04, profits on LOSS days 5/05-5/07). Corrected "
            "real-fills exp ATM -$27.57 / ITM2 -$42.54 over 16mo. No variant clears; retired per "
            "playbook rule 5 (fail thresholds -> retire, not loosen)."
        ),
        "real_tape_note": (
            "Fixtures use the REAL 2026-05-07 SPY 5m tape (descending highs 735.59 -> 735.55 -> "
            "735.50 -> 735.39 at 11:30-11:45 ET pressing 735.40 -> 729.75). The fabricated "
            "736.12/735.61/735.41 values from the original gate are GONE."
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
# Live audit — confirm no NEW observations post-retirement (non-blocking)
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        print("  [SKIP] watcher-observations.jsonl not found")
        return {"mode": "live", "all_pass": True, "total_obs": 0}

    obs: list[dict] = []
    post_retirement: list[dict] = []
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
            raw_date = str(o.get("date") or o.get("bar_timestamp_et") or "")[:10]
            try:
                if raw_date and dt.date.fromisoformat(raw_date) > _RETIRED_ON:
                    post_retirement.append({"date": raw_date})
            except ValueError:
                pass

    print(f"  [AUDIT] stairstep_continuation_watcher obs: N={len(obs)} (all pre-retirement expected)")
    print(f"          post-retirement fires (should be 0): {len(post_retirement)}")
    if post_retirement:
        print(f"          WARNING: {len(post_retirement)} obs dated after {_RETIRED_ON} — "
              f"detector should be retired (returns None). Investigate.")
    print(f"          status: RETIRED {_RETIRED_ON} (anti-J-edge). Detector returns None.")

    return {
        "mode": "live",
        "all_pass": True,  # informational only
        "total_obs": len(obs),
        "post_retirement_fires": len(post_retirement),
        "status": f"RETIRED {_RETIRED_ON.isoformat()} — anti-J-edge",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live", "both"], default="offline")
    args = parser.parse_args(argv)

    print(f"\n[v45] STAIRSTEP_CONTINUATION RETIREMENT gate — mode={args.mode}")
    print(f"      RETIRED {_RETIRED_ON} (anti-J-edge). Detector must return None on all inputs.")

    rc = 0
    if args.mode in ("offline", "both"):
        result = run_offline()
        status = "PASS" if result["all_pass"] else "FAIL"
        print(f"\n  [{status}] offline: {result['passed']}/{result['total']} retirement tests passed")
        if not result["all_pass"]:
            rc = 1

    if args.mode in ("live", "both"):
        run_live()

    return rc


if __name__ == "__main__":
    sys.exit(main())
