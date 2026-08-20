"""Tests for multi/lib/signal.py -- the per-symbol signal builder (analogue of
automation/state/fleet/build_shared_signal.py) that scores a symbol's own bars through
multi/lib/filters.py and assembles a shared-signal-shaped dict.

Covers: the $12 ACTIVE_BAND -> percent-of-price conversion (select_active_levels), fail-loud
behavior on missing/short/malformed bar data, the params.json read-only contract, the
no-order-placement hard rule, and one end-to-end build_signal() integration pass.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi.lib import filters as mf  # noqa: E402
from multi.lib import signal as ms  # noqa: E402

SIGNAL_PATH = REPO_ROOT / "multi" / "lib" / "signal.py"
PARAMS_PATH = REPO_ROOT / "automation" / "state" / "multi" / "params.json"


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL GUARDS
# ─────────────────────────────────────────────────────────────────────────────

def test_signal_file_exists():
    assert SIGNAL_PATH.is_file()


def test_no_import_of_the_source_spy_lane_engine():
    """Same guard as test_multi_filters.py's, applied to signal.py: the only in-repo import
    may be the sibling fork multi.lib.filters.
    RED-PROOF: add `from automation.state.fleet import build_shared_signal` anywhere in
    signal.py and this test fails."""
    tree = ast.parse(SIGNAL_PATH.read_text(encoding="utf-8"))
    banned_fragments = ("backtest", "fleet")
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(f in mod for f in banned_fragments):
                offenders.append(("from", mod, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if any(f in alias.name for f in banned_fragments):
                    offenders.append(("import", alias.name, node.lineno))
    assert not offenders, f"multi/lib/signal.py imports the source engine: {offenders}"


def test_no_order_placement_surface():
    """HARD RULE: 'No order placement of any kind. This is scoring only.' Structural guard:
    no order-placement-shaped identifier anywhere in signal.py's source.
    RED-PROOF: add a call to `place_option_order(...)` (or similar) anywhere in signal.py
    and this test fails."""
    src = SIGNAL_PATH.read_text(encoding="utf-8").lower()
    banned_substrings = (
        "place_option_order", "place_order", "place_stock_order", "place_crypto_order",
        "submit_order", "mcp__alpaca", "cancel_order", "close_position",
    )
    offenders = [b for b in banned_substrings if b in src]
    assert not offenders, f"order-placement surface found in signal.py: {offenders}"


def test_never_writes_params_json():
    """HARD RULE: automation/state/multi/params.json 'ALREADY EXIST -- read them, do not
    modify them.' Structural guard: no write-mode file open on PARAMS_PATH anywhere in
    signal.py (the only params.json touch point is _load_multi_params's read_text call).
    RED-PROOF: add `PARAMS_PATH.write_text(...)` anywhere in signal.py and this test fails."""
    src = SIGNAL_PATH.read_text(encoding="utf-8")
    assert "PARAMS_PATH.write_text" not in src
    assert "PARAMS_PATH.open(" not in src or '"w"' not in src


def test_params_json_untouched_by_a_real_build_signal_call():
    """End-to-end proof, not just a source scan: call build_signal() against the real
    params.json and assert its on-disk bytes are byte-identical before and after."""
    before = PARAMS_PATH.read_bytes()
    bars, level = _make_bear_signal_bars(55.0)
    ms.build_signal("TEST_PARAMS_RO", bars, candidate_levels=[level], write=False)
    after = PARAMS_PATH.read_bytes()
    assert before == after


# ─────────────────────────────────────────────────────────────────────────────
# ACTIVE_BAND — was ACTIVE_BAND=$12 (setup/scripts/refresh_levels_intraday.py). Converted to
# percent-of-price. This is the "vary-and-assert" proof for that specific conversion.
# ─────────────────────────────────────────────────────────────────────────────

def test_active_band_matches_the_original_12_dollars_at_the_700_reference():
    """Pins the conversion's anchor point: at the task's own $700 SPY reference price, the
    new percent-of-price band must reproduce the original $12 window exactly."""
    band_dollars = ms.ACTIVE_BAND_PCT_OF_PRICE * 700.0
    assert band_dollars == pytest.approx(12.0, rel=1e-9)


def test_select_active_levels_scales_with_price_not_a_flat_dollar_window():
    """The core proof: a level $10 away from spot is INSIDE the old flat $12 window at ANY
    price, but a $10 move on a $40 stock is 25% -- nowhere near 'still in play' the way a
    $10 move on a $700 name (1.4%) is. The percent-of-price conversion must therefore
    ACCEPT the $10-away level near a $700 spot and REJECT the identical $10-away level near
    a $40 spot.
    RED-PROOF: hardcode select_active_levels to use a flat `12.0` dollar band instead of
    `active_band_pct * spot` and both cases include the level (test fails on the second
    assertion)."""
    included_near_high_price = ms.select_active_levels([710.0], spot=700.0)  # 10 <= 12.0 band
    excluded_near_low_price = ms.select_active_levels([50.0], spot=40.0)     # 10 > 0.686 band
    assert included_near_high_price == [710.0]
    assert excluded_near_low_price == []


def test_select_active_levels_band_pct_is_a_load_bearing_parameter():
    """Direct vary-and-assert on the active_band_pct argument itself."""
    wide = ms.select_active_levels([710.0], spot=700.0, active_band_pct=0.02)   # band=14 -> in
    narrow = ms.select_active_levels([710.0], spot=700.0, active_band_pct=0.001)  # band=0.7 -> out
    assert wide == [710.0]
    assert narrow == []


def test_select_active_levels_empty_inputs_never_raise():
    assert ms.select_active_levels(None, 100.0) == []
    assert ms.select_active_levels([], 100.0) == []
    assert ms.select_active_levels([100.0], 0.0) == []


# ─────────────────────────────────────────────────────────────────────────────
# build_bar_context — FAIL LOUD on missing/short/malformed bars.
# ─────────────────────────────────────────────────────────────────────────────

def _flat_bars(n: int, price: float = 100.0, with_index: bool = True) -> pd.DataFrame:
    rows = [{"open": price, "high": price + 0.05, "low": price - 0.05, "close": price,
             "volume": 1_000_000.0} for _ in range(n)]
    df = pd.DataFrame(rows)
    if with_index:
        df.index = pd.date_range("2026-08-19 09:35:00", periods=n, freq="5min")
    return df


def test_build_bar_context_raises_on_none_bars():
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", None)


def test_build_bar_context_raises_on_empty_bars():
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", pd.DataFrame())


def test_build_bar_context_raises_on_missing_columns():
    df = pd.DataFrame({"open": [1.0] * 60, "close": [1.0] * 60})
    df.index = pd.date_range("2026-08-19 09:35:00", periods=60, freq="5min")
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", df)


def test_build_bar_context_raises_on_non_datetime_index():
    df = _flat_bars(60, with_index=False)  # default RangeIndex
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", df)


def test_build_bar_context_raises_on_nan_close():
    df = _flat_bars(60)
    df.loc[df.index[10], "close"] = float("nan")
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", df)


def test_build_bar_context_raises_below_min_bars_required():
    """Boundary vary-and-assert: MIN_BARS_REQUIRED - 1 raises, MIN_BARS_REQUIRED itself does
    not (paired with the real ribbon/ATR warmup check in the end-to-end test below)."""
    df = _flat_bars(ms.MIN_BARS_REQUIRED - 1)
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", df)


def test_build_bar_context_raises_on_bar_idx_out_of_range():
    df = _flat_bars(60)
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", df, bar_idx=999)


def test_build_bar_context_raises_on_flat_degenerate_atr():
    """A perfectly flat bar series produces ATR(14)==0 -- a data problem, not 'no tolerance';
    build_bar_context must refuse rather than silently divide every ATR-relative threshold
    down to zero."""
    df = _flat_bars(60, price=100.0)
    # make every bar IDENTICAL (zero true range) so ATR genuinely collapses to 0
    for col in ("open", "high", "low", "close"):
        df[col] = 100.0
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", df)


# ─────────────────────────────────────────────────────────────────────────────
# htf_15m_stack — optional, None-safe.
# ─────────────────────────────────────────────────────────────────────────────

def test_htf_15m_stack_none_when_not_supplied():
    df = _flat_bars(60)
    ctx = ms.build_bar_context("AAPL", df)
    assert ctx.htf_15m_stack is None


def test_htf_15m_stack_raises_on_non_datetime_htf_index():
    df = _flat_bars(60)
    htf = _flat_bars(60, with_index=False)
    with pytest.raises(ms.SignalBuildError):
        ms.build_bar_context("AAPL", df, htf_15m_bars=htf)


# ─────────────────────────────────────────────────────────────────────────────
# END-TO-END — one real build_signal() pass.
# ─────────────────────────────────────────────────────────────────────────────

def _make_bear_signal_bars(base_price: float, n_warmup: int = 49):
    """MIN_BARS_REQUIRED (50) bars: a bear-drift warmup + one level-rejection trigger bar,
    on a proper DatetimeIndex so build_signal's full pipeline (ribbon/ATR/levels/action) runs
    for real."""
    rows = []
    mult = 1.05
    step = 0.0012
    for _ in range(n_warmup):
        o, c = mult, mult - step
        h, l = max(o, c) + 0.00015, min(o, c) - 0.00015
        rows.append({"open": o * base_price, "high": h * base_price, "low": l * base_price,
                     "close": c * base_price, "volume": 1_000_000.0})
        mult = c
    prior_close_mult = mult
    level_mult = prior_close_mult + 0.006
    o = prior_close_mult
    close_mult = prior_close_mult - 0.0030
    high_mult = level_mult + 0.0020
    low_mult = min(o, close_mult) - 0.0006
    rows.append({"open": o * base_price, "high": high_mult * base_price,
                 "low": low_mult * base_price, "close": close_mult * base_price,
                 "volume": 2_000_000.0})
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-08-19 09:35:00", periods=len(df), freq="5min")
    return df, level_mult * base_price


def test_build_signal_end_to_end_bear_action():
    bars, level = _make_bear_signal_bars(55.0)
    sig = ms.build_signal("XYZ", bars, candidate_levels=[level], write=False)
    assert sig["symbol"] == "XYZ"
    assert sig["action"] == "ENTER_BEAR"
    assert sig["bear"]["passed"] is True
    assert sig["bull"]["passed"] is False
    assert "level_rejection" in sig["bear"]["triggers_fired"]
    assert sig["ribbon_stack"] == "BEAR"
    assert sig["spot"] == pytest.approx(float(bars.iloc[-1]["close"]))


def test_build_signal_no_candidate_levels_holds_but_does_not_raise():
    bars, _level = _make_bear_signal_bars(55.0)
    sig = ms.build_signal("XYZ", bars, candidate_levels=None, write=False)
    assert sig["bear"]["passed"] is False  # no level in range -> no level-tied trigger -> blocked
    assert sig["action"] == "HOLD"


def test_build_signal_write_roundtrips_atomically(tmp_path):
    bars, level = _make_bear_signal_bars(55.0)
    out_path = tmp_path / "XYZ.json"
    sig = ms.build_signal("XYZ", bars, candidate_levels=[level], write=True, out_path=out_path)
    assert out_path.is_file()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk == sig
    assert list(out_path.parent.glob(".*.tmp")) == []  # tmp file was cleaned up (renamed)


def test_build_signal_write_true_without_out_path_raises():
    bars, level = _make_bear_signal_bars(55.0)
    with pytest.raises(ms.SignalBuildError):
        ms.build_signal("XYZ", bars, candidate_levels=[level], write=True)


def test_default_signal_path_does_not_collide_with_sibling_owned_files():
    p = ms.default_signal_path("AAPL")
    assert p.parent.name == "signals"
    assert p.parent.parent == REPO_ROOT / "automation" / "state" / "multi"
    sibling_owned = {"scanner-*.json", "decisions.jsonl", "positions.json",
                      "exit-state.json", "circuit-breaker.json", "secrets.json"}
    assert p.name not in sibling_owned


def test_param_override_reads_signal_block_when_present():
    """Vary-and-assert for the params.json override path itself (not exercised by the real
    params.json, which defines no `signal` block today -- see module docstring)."""
    default_val = ms._param_override({"signal": {}}, "min_triggers", 1.0)
    overridden_val = ms._param_override({"signal": {"min_triggers": 3}}, "min_triggers", 1.0)
    assert default_val == 1.0
    assert overridden_val == 3.0
