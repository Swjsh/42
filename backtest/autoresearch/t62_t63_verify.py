"""T62 + T63 verification — confirm runner.py now writes to stderr on:
  (a) silent-skip when multi_day_rth is None during apparent live call
  (b) per-watcher exception (mocked)
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    ROOT = Path(__file__).resolve().parent.parent.parent
except NameError:
    ROOT = Path.cwd().parent if Path.cwd().name == "backtest" else Path.cwd()
sys.path.insert(0, str(ROOT / "backtest"))

import datetime as dt
import io
import pandas as pd
from contextlib import redirect_stderr

from lib.watchers.runner import run_all_watchers
from lib.filters import BarContext


def make_bar(price=740.0, vol=300000, ts=None):
    if ts is None:
        # current ET clock-ish (so the T62 live-call heuristic fires)
        ts = pd.Timestamp(dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).replace(microsecond=0, tzinfo=None))
    return pd.Series({
        "timestamp_et": ts,
        "open": price,
        "high": price + 0.5,
        "low": price - 0.5,
        "close": price + 0.1,
        "volume": vol,
    })


def make_minimal_ctx(bar, bar_idx):
    """Build a minimal BarContext for runner. Required fields: bar_idx, timestamp_et, bar, vol_baseline_20, range_baseline_20, vix_now, ribbon_now, levels_active, multi_day_levels, prior_bars."""
    return BarContext(
        bar_idx=bar_idx,
        timestamp_et=bar["timestamp_et"].to_pydatetime() if hasattr(bar["timestamp_et"], "to_pydatetime") else bar["timestamp_et"],
        bar=bar,
        prior_bars=pd.DataFrame([make_bar(p) for p in [740.0, 740.5, 740.2, 740.1, 740.0]]),
        ribbon_now=None,
        ribbon_history=[],
        vix_now=17.5,
        vix_prior=17.4,
        vol_baseline_20=300000.0,
        range_baseline_20=1.0,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states={},
    )


def test_T62_no_multi_day_rth():
    """When multi_day_rth is None in a live call, runner should write a WARNING to stderr."""
    bar = make_bar()
    today_bars = pd.DataFrame([bar])
    bar_idx = 0
    ctx = make_minimal_ctx(bar, bar_idx)

    captured = io.StringIO()
    with redirect_stderr(captured):
        # NB: pass multi_day_rth=None explicitly
        signals = run_all_watchers(
            bar, today_bars, bar_idx,
            vol_baseline_20=300000.0,
            ctx=ctx,
            vix_now=17.5,
            multi_day_rth=None,
            ribbon_state_dict=None,
        )

    output = captured.getvalue()
    print("--- T62 TEST: no multi_day_rth ---")
    print(f"signals_returned: {len(signals)}")
    print(f"stderr_captured:\n{output if output else '(empty)'}")
    print(f"T62 invariant detected: {'WARNING T62' in output}")
    print()


def test_T63_normal_call_with_multi_day_rth():
    """Sanity: when multi_day_rth IS provided, no T62 warning should fire."""
    bar = make_bar()
    today_bars = pd.DataFrame([bar])
    bar_idx = 0
    ctx = make_minimal_ctx(bar, bar_idx)

    # Build a tiny multi_day_rth with the same timestamp so bar_idx_full >= 0
    mdr = pd.DataFrame([bar])

    captured = io.StringIO()
    with redirect_stderr(captured):
        signals = run_all_watchers(
            bar, today_bars, bar_idx,
            vol_baseline_20=300000.0,
            ctx=ctx,
            vix_now=17.5,
            multi_day_rth=mdr,
            ribbon_state_dict=None,
        )

    output = captured.getvalue()
    print("--- T63 TEST: normal call with multi_day_rth + minimal-ctx (some watchers may throw) ---")
    print(f"signals_returned: {len(signals)}")
    print(f"stderr_lines: {len([l for l in output.splitlines() if l.strip()])}")
    if output:
        print("stderr first 600 chars:")
        print(output[:600])
    else:
        print("stderr empty (no watcher exceptions)")
    print()
    print(f"T63 check — exceptions visible: {any(w in output for w in ['exception:', 'watcher exception'])}")


if __name__ == "__main__":
    test_T62_no_multi_day_rth()
    test_T63_normal_call_with_multi_day_rth()
