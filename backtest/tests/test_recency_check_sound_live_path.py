"""Guards for backtest/autoresearch/recency_check.py -- POSTFIX-RECENCY-CHECK-UNSOUND-REPLAY
fix (2026-08-08 night, follow-up from POSTFIX-GATE-COSTING-UNSOUND-REPLAY / commit 97a2e2ac).

Pin, in order:
  1. LEGACY SIGNATURE PIN: `simulate_set` (the function 60+ one-off research scripts import
     directly for internal comparability) keeps its EXACT pre-fix signature -- a change here
     would silently break every one of those callers.
  2. STRUCTURAL PROOF: `simulate_trade_real` is referenced ONLY inside `simulate_set`'s own
     function body -- `simulate_set_sound` / `_replay_signal_sound` / `main` never mention it.
     A future edit that quietly re-wires the live path back onto the old engine would show up
     here as a diff, not a silent regression.
  3. THE SOUNDNESS PROOF: `simulate_set_sound` routes every signal through
     `lib.exit_manager_walk.walk_exit_manager` (the REAL production exit_manager core) and
     NEVER touches `simulate_trade_real` -- proven by monkeypatching the name bound inside
     recency_check's own namespace (the one `simulate_set` calls) to raise if invoked while
     `simulate_set_sound` runs.
  4. SCHEMA: `simulate_set_sound`'s coverage dict carries replay_engine="walk_exit_manager" /
     replay_soundness="sound", matching the schema gate_expiry_check.py's evaluate_gate_pnl and
     postfix_gate_costing.py's mine() both emit.
  5. LIVE-PATH-ONLY WIRING: `main()`'s source calls `simulate_set_sound`, never a bare
     `simulate_set(` -- the legacy function stays reachable ONLY for external importers, never
     from this file's own live flow.
  6. VERDICT-CLASSIFICATION UNCHANGED: `verdict_for` / `book_verdict` (untouched by this fix)
     still classify CONFIRM/YELLOW/RED/NO_FILLS exactly as before -- only their INPUTS (now
     sound-replay P&L) changed, never the classification logic itself.
"""
from __future__ import annotations

import datetime as dt
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from autoresearch import recency_check as rc
import lib.simulator_real as simulator_real_module


# ─────────────────────────────────────────────────────────────────── (1) legacy signature pin
def test_legacy_simulate_set_signature_unchanged():
    """60+ one-off research scripts import `simulate_set` and depend on its EXACT call
    contract for internal comparability -- pin it so a future edit can't silently break them."""
    sig = inspect.signature(rc.simulate_set)
    params = list(sig.parameters.values())
    names = [p.name for p in params]
    assert names == ["signals", "spy", "ribbon", "vix", "strike_offset", "setup", "qty"]
    kw_only = {p.name for p in params if p.kind == inspect.Parameter.KEYWORD_ONLY}
    assert kw_only == {"strike_offset", "setup", "qty"}, "strike_offset/setup/qty must stay keyword-only"
    # still calls the legacy engine -- this function is INTENTIONALLY unchanged, not merely
    # present with the right shape.
    src = inspect.getsource(rc.simulate_set)
    assert "simulate_trade_real(" in src


# ─────────────────────────────────────────────────────────────────── (2) structural proof
def test_simulate_trade_real_only_referenced_inside_legacy_simulate_set():
    """`simulate_trade_real` must be reachable from exactly ONE place in this module's live
    code: inside `simulate_set`'s own body. The sound live path (`simulate_set_sound`,
    `_replay_signal_sound`, `main`) must never mention it -- a future accidental fallback onto
    the unsound engine would show up here as a diff, not a silent regression."""
    src = Path(rc.__file__).read_text(encoding="utf-8")
    call_sites = [m.start() for m in re.finditer(r"\bsimulate_trade_real\s*\(", src)]
    # exactly one call site in the whole file: the one inside simulate_set.
    assert len(call_sites) == 1, (
        f"expected exactly 1 simulate_trade_real( call site (inside legacy simulate_set), "
        f"found {len(call_sites)}")
    legacy_src = inspect.getsource(rc.simulate_set)
    assert "simulate_trade_real(" in legacy_src

    for fn in (rc.simulate_set_sound, rc._replay_signal_sound, rc.main):
        fn_src = inspect.getsource(fn)
        assert re.search(r"\bsimulate_trade_real\s*\(", fn_src) is None, (
            f"{fn.__name__} must never CALL simulate_trade_real (POSTFIX-RECENCY-CHECK-"
            f"UNSOUND-REPLAY) -- the sound live path uses walk_exit_manager exclusively "
            f"(a bare prose MENTION of the retired name in a comment is fine)")


# ─────────────────────────────────────────────────────────────────── (5) live-path-only wiring
def test_main_calls_simulate_set_sound_never_bare_simulate_set():
    """The live path (main(), the function Gamma_LicenseMonitor re-invokes nightly) must call
    ONLY simulate_set_sound -- never the legacy simulate_set -- so recency-confirmation.json is
    always computed by the sound engine."""
    src = inspect.getsource(rc.main)
    assert "simulate_set_sound(" in src
    assert re.search(r"[^_]\bsimulate_set\s*\(", src) is None, (
        "main() must not call the legacy simulate_set( ) directly")


# ─────────────────────────────────────────────────────────────────── fixtures for (3)/(4)
class _FakeSoundReplayModule:
    """Stands in for the lazily-imported backtest/tools/gate_revalidation_ab.py -- same shape
    test_gate_expiry_check.py / test_postfix_gate_costing.py's fixtures use."""

    def __init__(self):
        self.ribbon_tick_calls = 0

    def account_config(self):
        return {
            "safe": {"qty": 3, "structure_stop_enabled": False, "time_stop_et": dt.time(15, 40)},
            "bold": {"qty": 5, "structure_stop_enabled": False, "time_stop_et": dt.time(15, 40)},
        }

    def build_ribbon_lookup(self, spy):
        return "FAKE_RIBBON_LOOKUP"

    def ribbon_ride_shape(self):
        # matches test_graduated_guards.py's own walk_exit_manager frame-fix fixture shape --
        # 99% targets so the walk naturally runs to data-exhausted force-close, deterministic.
        return {"premium_stop_pct": -0.99, "tp1_premium_pct": 99.0, "tp1_qty_fraction": 0.667,
                "profit_lock_mode": "fixed", "runner_target_pct": 99.0}

    def ribbon_tick_df_for(self, opt_df, ribbon_lookup):
        self.ribbon_tick_calls += 1
        assert ribbon_lookup == "FAKE_RIBBON_LOOKUP"
        return pd.DataFrame({"stack": [None] * len(opt_df)})


def _tiny_spy() -> pd.DataFrame:
    ts = pd.Timestamp("2026-07-01 10:00:00")
    return pd.DataFrame({
        "timestamp_et": [ts], "date": [ts.date()],
        "open": [450.0], "high": [450.2], "low": [449.8], "close": [450.1],
    })


def _tiny_opt_df() -> pd.DataFrame:
    ts0 = pd.Timestamp("2026-07-01 10:05:00")
    times = [ts0 + pd.Timedelta(minutes=5 * i) for i in range(6)]
    n = len(times)
    return pd.DataFrame({
        "timestamp_et": times,
        "open": [1.00, 1.02, 0.98, 1.01, 0.99, 1.00],
        "high": [1.05, 1.06, 1.03, 1.05, 1.03, 1.04],
        "low": [0.95, 0.97, 0.93, 0.96, 0.94, 0.95],
        "close": [1.02, 0.98, 1.01, 0.99, 1.00, 1.00],
        "volume": [100] * n, "vwap": [1.00] * n, "trade_count": [10] * n,
    })


@pytest.fixture(autouse=True)
def _clear_sound_module_cache():
    rc._SOUND_REPLAY_MODULE = None
    yield
    rc._SOUND_REPLAY_MODULE = None


# ─────────────────────────────────────────────────────────────────── (3)+(4) core soundness proof
def test_simulate_set_sound_never_calls_simulate_trade_real_and_stamps_provenance(monkeypatch):
    fake_grab = _FakeSoundReplayModule()
    monkeypatch.setattr(rc, "_sound_replay_module", lambda: fake_grab)
    monkeypatch.setattr(rc, "_nearest_cached_strike", lambda d, target, side, max_steps: 450)
    monkeypatch.setattr(rc, "option_symbol", lambda d, strike, side: f"FAKE_{d}_{strike}_{side}")
    monkeypatch.setattr(rc, "load_contract_bars", lambda symbol, frame=None: _tiny_opt_df())

    def _boom(*a, **k):
        raise AssertionError("simulate_set_sound must NEVER call simulate_trade_real "
                              "(POSTFIX-RECENCY-CHECK-UNSOUND-REPLAY)")
    monkeypatch.setattr(rc, "simulate_trade_real", _boom)
    monkeypatch.setattr(simulator_real_module, "simulate_trade_real", _boom)

    spy = _tiny_spy()
    spy_by_date = {spy.iloc[0]["date"]: spy}
    sg = rc.Signal(bar_idx=0, side="C", stop_level=449.0, note="test")

    rows, cov = rc.simulate_set_sound([sg], spy, spy_by_date, "FAKE_RIBBON_LOOKUP",
                                       strike_offset=0, qty=3, account="safe")

    assert fake_grab.ribbon_tick_calls == 1, "the sound replay must have actually run"
    assert cov["signals"] == 1
    assert cov["filled"] == 1
    assert cov["replay_engine"] == "walk_exit_manager"
    assert cov["replay_soundness"] == "sound"
    assert len(rows) == 1
    row = rows[0]
    assert row["side"] == "C"
    assert row["strike"] == 450
    assert isinstance(row["pnl"], float)
    assert row["exit"]  # non-empty exit reason string from the real walk_exit_manager


def test_simulate_set_sound_reports_no_contract_without_crashing(monkeypatch):
    """A signal whose strike has no cached contract must degrade to a counted status, not a
    crash -- same fail-open contract the legacy simulate_set honors via cache_miss."""
    fake_grab = _FakeSoundReplayModule()
    monkeypatch.setattr(rc, "_sound_replay_module", lambda: fake_grab)
    monkeypatch.setattr(rc, "_nearest_cached_strike", lambda d, target, side, max_steps: None)

    def _boom(*a, **k):
        raise AssertionError("must never reach simulate_trade_real")
    monkeypatch.setattr(rc, "simulate_trade_real", _boom)

    spy = _tiny_spy()
    spy_by_date = {spy.iloc[0]["date"]: spy}
    sg = rc.Signal(bar_idx=0, side="P", stop_level=451.0, note="test")

    rows, cov = rc.simulate_set_sound([sg], spy, spy_by_date, "FAKE_RIBBON_LOOKUP",
                                       strike_offset=-2, qty=5, account="bold")
    assert rows == []
    assert cov["filled"] == 0
    assert cov["status_counts"].get("no_contract") == 1
    assert cov["replay_engine"] == "walk_exit_manager"


# ─────────────────────────────────────────────────────────────────── (6) verdict classification
def test_verdict_for_classification_unchanged():
    """Pins verdict_for's CONFIRM/YELLOW/RED/NO_FILLS boundaries -- only the P&L feeding this
    function changed with the soundness fix, never the classification rule itself."""
    floor = 10
    v, _ = rc.verdict_for({"n": 12, "exp_per_trade": 5.0}, {"exp_per_trade": 1.0}, floor)
    assert v == "CONFIRM"
    v, _ = rc.verdict_for({"n": 3, "exp_per_trade": 5.0}, {"exp_per_trade": 1.0}, floor)
    assert v == "YELLOW"
    v, _ = rc.verdict_for({"n": 12, "exp_per_trade": -5.0}, {"exp_per_trade": 1.0}, floor)
    assert v == "RED"
    v, _ = rc.verdict_for({"n": 0}, {"exp_per_trade": 1.0}, floor)
    assert v == "NO_FILLS"
    v, _ = rc.verdict_for({"n": 3, "exp_per_trade": -5.0}, {"exp_per_trade": 1.0}, floor)
    assert v == "YELLOW"  # small-n wobble against a positive full-OOS base


def test_book_verdict_classification_unchanged():
    floor = 10
    v, _ = rc.book_verdict({"n_trades": 12, "total_dollar": 120.0},
                            {"n_trades": 20, "total_dollar": 20.0}, floor)
    assert v == "CONFIRM"
    v, _ = rc.book_verdict({"n_trades": 12, "total_dollar": -120.0},
                            {"n_trades": 20, "total_dollar": 20.0}, floor)
    assert v == "RED"
