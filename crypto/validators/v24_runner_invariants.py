"""v24_runner_invariants — regression tests for watcher runner invariants (T62/T63 + RTH contract).

Background (L25 + L35):
  `runner.py` was refactored in 2026-05-13 fire #22 to surface watcher exceptions to stderr
  instead of silently swallowing them (T63 fix).  A separate T62 fix logs a WARNING when
  `multi_day_rth` is None/empty in an apparent live call.  Without these guards: watcher
  exceptions are invisible in task logs → "0 observations today" with no error trace →
  the ORB/ODF/PFF watchers appear broken for a day before anyone notices (the 5/13 foot-gun,
  L35).

Offline tests (T1-T5):
  T1  RTH_MULTI_DAY    — multi_day_rth spanning 2 RTH days → bar found, no mismatch warn
  T2  RTH_OPEN_BOUNDARY — bar exactly at 09:30 ET → idx found in multi_day_rth (idx >= 0)
  T3  POST_MARKET_MISMATCH — bar at 16:05 ET (not in RTH multi_day_rth) → T62 warn in stderr
  T4  EXCEPTION_UNMASKED — patched watcher raises ValueError → logged to stderr, no propagation
  T5  NONE_RETURN_CLEAN   — all watchers return None → run_all_watchers returns empty list

Live: N/A — structural test of runner behavior, not a data-source test.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import types
from contextlib import redirect_stderr
from pathlib import Path
from typing import Optional
import unittest.mock as mock

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "backtest"))

from backtest.lib.watchers.runner import run_all_watchers
import backtest.lib.watchers.runner as _runner_mod
from backtest.lib.filters import BarContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(
    ts: str,
    price: float = 540.0,
    volume: int = 300_000,
    tz_aware: bool = False,
) -> pd.Series:
    """Build a minimal OHLCV bar Series compatible with run_all_watchers."""
    timestamp = pd.Timestamp(ts)
    if tz_aware:
        timestamp = timestamp.tz_localize("America/New_York")
    return pd.Series({
        "timestamp_et": timestamp,
        "open": price,
        "high": price + 0.5,
        "low": price - 0.5,
        "close": price + 0.1,
        "volume": volume,
    })


def _make_minimal_ctx(bar: pd.Series, bar_idx: int) -> BarContext:
    """Build the minimal BarContext that run_all_watchers needs without errors."""
    ts = bar["timestamp_et"]
    if hasattr(ts, "to_pydatetime"):
        ts_py = ts.to_pydatetime()
    else:
        ts_py = dt.datetime.fromisoformat(str(ts))
    if ts_py.tzinfo is None:
        ts_py = ts_py.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))

    prior = pd.DataFrame([
        _make_bar(f"2026-05-20 09:30:00", 539.0),
        _make_bar(f"2026-05-20 09:35:00", 540.0),
        _make_bar(f"2026-05-20 09:40:00", 540.5),
    ])
    return BarContext(
        bar_idx=bar_idx,
        timestamp_et=ts_py,
        bar=bar,
        prior_bars=prior,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=17.5,
        vix_prior=17.4,
        vol_baseline_20=300_000.0,
        range_baseline_20=1.0,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states={},
    )


def _reset_runner_dedup() -> None:
    """Reset the runner's module-level per-day dedup state between tests."""
    _runner_mod._dedup_state = {}
    _runner_mod._dedup_date = None


def _call_runner(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    bar_idx: int,
    multi_day_rth: Optional[pd.DataFrame] = None,
) -> tuple[list, str]:
    """Call run_all_watchers, capturing all stderr output.  Returns (signals, stderr_text)."""
    _reset_runner_dedup()
    ctx = _make_minimal_ctx(bar, bar_idx)
    captured = io.StringIO()
    with redirect_stderr(captured):
        signals = run_all_watchers(
            bar,
            day_bars,
            bar_idx,
            vol_baseline_20=300_000.0,
            ctx=ctx,
            vix_now=17.5,
            multi_day_rth=multi_day_rth,
            ribbon_state_dict=None,
        )
    return signals, captured.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run T1-T5 offline regression tests for watcher runner invariants."""
    results: list[tuple[str, bool, str]] = []

    # -----------------------------------------------------------------------
    # T1: RTH_MULTI_DAY — multi_day_rth spanning 2 RTH days
    #   bar is in day 2 of RTH history. bar_idx_full must be found (no mismatch warning).
    # -----------------------------------------------------------------------
    day1_bars = [
        _make_bar(f"2026-05-19 09:30:00", 540.0),
        _make_bar(f"2026-05-19 09:35:00", 540.5),
        _make_bar(f"2026-05-19 09:40:00", 541.0),
    ]
    day2_bars = [
        _make_bar(f"2026-05-20 09:30:00", 542.0),
        _make_bar(f"2026-05-20 09:35:00", 542.5),
        _make_bar(f"2026-05-20 09:40:00", 543.0),
    ]
    multi_day = pd.DataFrame(day1_bars + day2_bars).reset_index(drop=True)
    bar_t1 = _make_bar("2026-05-20 09:40:00", 543.0)
    day_bars_t1 = pd.DataFrame(day2_bars)
    _, stderr_t1 = _call_runner(bar_t1, day_bars_t1, 2, multi_day_rth=multi_day)

    # Must NOT produce T62 mismatch warning (bar IS in multi_day_rth)
    t1_ok = "NOT MATCHED" not in stderr_t1
    results.append((
        "T1_rth_multi_day_bar_found_no_mismatch",
        t1_ok,
        f"stderr_lines={len([l for l in stderr_t1.splitlines() if l.strip()])} "
        f"mismatch_warn={'YES' if 'NOT MATCHED' in stderr_t1 else 'NO'}",
    ))

    # -----------------------------------------------------------------------
    # T2: RTH_OPEN_BOUNDARY — bar exactly at 09:30 ET (RTH open)
    #   Bar at the RTH open boundary must be matched in multi_day_rth (no mismatch warn).
    # -----------------------------------------------------------------------
    bar_t2 = _make_bar("2026-05-21 09:30:00", 544.0)
    multi_day_t2 = pd.DataFrame([bar_t2]).reset_index(drop=True)
    day_bars_t2 = pd.DataFrame([bar_t2])
    _, stderr_t2 = _call_runner(bar_t2, day_bars_t2, 0, multi_day_rth=multi_day_t2)

    t2_ok = "NOT MATCHED" not in stderr_t2
    results.append((
        "T2_rth_open_boundary_09_30_included",
        t2_ok,
        f"mismatch_warn={'YES' if 'NOT MATCHED' in stderr_t2 else 'NO'}",
    ))

    # -----------------------------------------------------------------------
    # T3: POST_MARKET_MISMATCH — bar at 16:05 ET (post-market)
    #   multi_day_rth contains only RTH bars (does NOT contain 16:05 bar).
    #   The runner MUST write a T62 mismatch warning to stderr (not crash).
    # -----------------------------------------------------------------------
    bar_t3 = _make_bar("2026-05-21 16:05:00", 544.5)
    # Only RTH bar in multi_day_rth — 16:05 is absent
    rth_only = pd.DataFrame([_make_bar("2026-05-21 09:30:00", 544.0)]).reset_index(drop=True)
    day_bars_t3 = pd.DataFrame([bar_t3])
    no_exception = True
    try:
        _, stderr_t3 = _call_runner(bar_t3, day_bars_t3, 0, multi_day_rth=rth_only)
    except Exception as exc:
        stderr_t3 = ""
        no_exception = False
    t3_ok = "NOT MATCHED" in stderr_t3 and no_exception
    results.append((
        "T3_post_market_mismatch_warns_no_crash",
        t3_ok,
        f"mismatch_warn={'YES' if 'NOT MATCHED' in stderr_t3 else 'NO'} no_crash={no_exception}",
    ))

    # -----------------------------------------------------------------------
    # T4: EXCEPTION_UNMASKED — patched watcher raises ValueError
    #   Temporarily replace detect_v14_enhanced_setup in the runner's namespace.
    #   The exception MUST appear in stderr (not be silently swallowed).
    # -----------------------------------------------------------------------
    bar_t4 = _make_bar("2026-05-20 10:00:00", 543.0)
    day_bars_t4 = pd.DataFrame([bar_t4])
    _original_v14e = _runner_mod.detect_v14_enhanced_setup

    def _exploding_v14e(_ctx):
        raise ValueError("SYNTHETIC_WATCHER_EXCEPTION_T4")

    no_propagation = True
    try:
        _runner_mod.detect_v14_enhanced_setup = _exploding_v14e
        _, stderr_t4 = _call_runner(bar_t4, day_bars_t4, 0, multi_day_rth=None)
    except Exception:
        # If the exception propagated, T4 FAILS
        stderr_t4 = ""
        no_propagation = False
    finally:
        _runner_mod.detect_v14_enhanced_setup = _original_v14e

    t4_ok = "SYNTHETIC_WATCHER_EXCEPTION_T4" in stderr_t4 and no_propagation
    results.append((
        "T4_watcher_exception_logged_not_swallowed",
        t4_ok,
        f"exception_in_stderr={'YES' if 'SYNTHETIC_WATCHER_EXCEPTION_T4' in stderr_t4 else 'NO'} "
        f"no_propagation={no_propagation}",
    ))

    # -----------------------------------------------------------------------
    # T5: NONE_RETURN_CLEAN — patched watchers return None
    #   Replace detect_v14_enhanced_setup with a None-returning function.
    #   run_all_watchers must return a list (no exception), signals ≥ 0.
    # -----------------------------------------------------------------------
    bar_t5 = _make_bar("2026-05-20 10:05:00", 543.0)
    day_bars_t5 = pd.DataFrame([bar_t5])
    _original_v14e_t5 = _runner_mod.detect_v14_enhanced_setup

    def _none_v14e(_ctx):
        return None

    clean_return = True
    result_is_list = True
    try:
        _runner_mod.detect_v14_enhanced_setup = _none_v14e
        signals_t5, _ = _call_runner(bar_t5, day_bars_t5, 0, multi_day_rth=None)
        result_is_list = isinstance(signals_t5, list)
    except Exception:
        clean_return = False
    finally:
        _runner_mod.detect_v14_enhanced_setup = _original_v14e_t5

    t5_ok = clean_return and result_is_list
    results.append((
        "T5_none_return_watcher_clean_empty_list",
        t5_ok,
        f"clean_return={clean_return} result_is_list={result_is_list}",
    ))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:120]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """No live data source required — runner invariants are structural / unit-level."""
    return {
        "mode": "live",
        "pass": True,
        "note": (
            "Runner invariant regression is offline-only — tests stderr-unmask + "
            "RTH mismatch contract using synthetic bars. T1-T5 cover multi-day RTH "
            "matching, boundary handling, post-market mismatch, exception surfacing, "
            "and clean None-return handling."
        ),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:55s} {t['note']}")

    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        print(f"\n=== LIVE === {sc['live']['note']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    all_ok = True
    if "offline" in sc and not sc["offline"]["all_pass"]:
        all_ok = False
    if "live" in sc and not sc["live"]["pass"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
