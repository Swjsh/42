"""Guard for the tickers-lane day-one autopsy (GOAL-TICKERS-LANE-2026-09-04, T7) bug.

ROOT CAUSE: `multi/lib/context.py::update_level_states` built `bounce_history` as a list of
BARE FLOATS (`hist.append(round(extreme, 4))`). Both consumers -- the fork
(`multi/lib/filters.py::detect_sequence_rejection`/`_reclaim`) AND production (FROZEN,
`backtest/lib/filters.py::detect_sequence_rejection`/`_reclaim`) subscript each entry
(`e["high_reached"]` / `e["low_reached"]`), i.e. they require a DICT -- matching
`backtest/lib/orchestrator.py::update_level_state`'s reference shape
`{"bar_idx": ..., "high_reached"|"low_reached": ...}`. A bare float raised
`TypeError: 'float' object is not subscriptable`.

MEASURED IMPACT (2026-09-04, first live trading day for tickers-1/2/3): 144 TICK_ERROR rows
(32 + 102 + 10) in `automation/state/tickers/<arm>/ledger.jsonl`. The exception escapes
`multi/core.py::tick`'s narrow `except (SignalBuildError, ValueError)` around the
`build_signal_fn` call uncaught, aborting the ENTIRE remaining `for sym in symbols` loop for
that tick -- every symbol after the one that hit a 3+-bounce broken level was silently never
scored, not just that one symbol.

This test RED-proofs the fix: reverting `update_level_states`'s bounce-append block to
`hist.append(round(extreme, 4))` must make `test_bounce_history_entries_are_dicts_not_floats`
fail, and `test_sequence_rejection_survives_three_bounces_no_crash` raise the exact TypeError
this bug produced in production.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi.lib import context as mctx      # noqa: E402
from multi.lib import filters as mf        # noqa: E402
from backtest.lib import filters as bf     # noqa: E402


def _bar(o, h, l, c, ts):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1_000_000.0}, ts


def _bars_df(rows_with_ts) -> pd.DataFrame:
    rows = [r for r, _ in rows_with_ts]
    idx = pd.DatetimeIndex([ts for _, ts in rows_with_ts], tz="America/New_York")
    return pd.DataFrame(rows, index=idx)


def _grow_bounce_history(tmp_path, level: float = 100.0) -> dict:
    """Simulate 5 successive ticks: price breaks below `level` (role -> broken_to_resistance),
    then pokes back up toward it three times (three bounce touches), each poke a distinct
    high so none get deduped. Returns the final {price: LevelStateRec} dict."""
    base_ts = pd.Timestamp("2026-09-04 09:30", tz="America/New_York")
    rows = []
    # warmup + the break below `level`
    for i, close in enumerate([102.0, 101.5, 101.0, 100.5, 99.0, 98.5]):
        rows.append(_bar(close, close + 0.2, close - 0.2, close,
                          base_ts + pd.Timedelta(minutes=5 * i)))
    state_dir = tmp_path / "levelstate"
    out = mctx.update_level_states("ZTEST", [level], _bars_df(rows), state_dir=state_dir)

    # Three distinct poke-up bounces, each a separate call (separate tick). Close stays well
    # below `level` (classic rejection wick) so role never flips; each high is >0.15 apart
    # from the last (the touch band at this price) so the de-dup path never collapses them.
    for j, poke_high in enumerate([99.9, 100.1, 100.3]):
        rows.append(_bar(98.6, poke_high, 98.4, 98.6,
                          base_ts + pd.Timedelta(minutes=5 * (6 + j))))
        out = mctx.update_level_states("ZTEST", [level], _bars_df(rows), state_dir=state_dir)
    return out


def test_bounce_history_entries_are_dicts_not_floats(tmp_path):
    out = _grow_bounce_history(tmp_path)
    rec = out[100.0]
    assert rec.role == "broken_to_resistance"
    assert len(rec.bounce_history) >= 3, rec.bounce_history
    for entry in rec.bounce_history:
        assert isinstance(entry, dict), (
            f"bounce_history entry {entry!r} is a bare {type(entry).__name__}, not a dict -- "
            "the 2026-09-04 regression (L-tickers-bounce-history-shape)"
        )
        assert "high_reached" in entry
        assert "bar_idx" in entry


def test_sequence_rejection_survives_three_bounces_no_crash(tmp_path):
    """The exact call shape that raised `TypeError: 'float' object is not subscriptable`
    144 times on 2026-09-04 -- both the fork's and production's (FROZEN) detector, on the
    SAME LevelStateRec (duck-typed: both only read .role/.bounce_history)."""
    out = _grow_bounce_history(tmp_path)
    rec = out[100.0]

    # Must not raise -- this is the RED-proof: reverting the context.py fix reproduces the
    # exact production TypeError here.
    fork_result = mf.detect_sequence_rejection(rec)
    prod_result = bf.detect_sequence_rejection(rec)
    assert isinstance(fork_result, bool)
    assert isinstance(prod_result, bool)


def test_reverting_the_fix_reproduces_the_exact_production_error(tmp_path):
    """Pins the failure mode itself: a LevelStateRec whose bounce_history is (as before the
    fix) a list of bare floats raises exactly `TypeError: 'float' object is not
    subscriptable` from both frozen detectors -- proving this test suite would have caught
    the 2026-09-04 bug had it existed beforehand."""
    from multi.lib.context import LevelStateRec

    broken = LevelStateRec(price=100.0, role="broken_to_resistance",
                            bounce_history=[99.6, 99.75, 99.9])  # pre-fix shape
    with pytest.raises(TypeError, match="not subscriptable"):
        mf.detect_sequence_rejection(broken)
    with pytest.raises(TypeError, match="not subscriptable"):
        bf.detect_sequence_rejection(broken)
