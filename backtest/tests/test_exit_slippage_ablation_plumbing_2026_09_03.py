"""GUARD for WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION (2026-09-03) -- the exit_slippage
override plumbing added to `setup/scripts/pdt_blocked_counterfactual.py` and
`setup/scripts/whole_engine_null.py`.

WHAT WAS ADDED (research plumbing only -- no walker default changed, see each module's own
docstring notes at the touched call sites):
  * `pdt_blocked_counterfactual._price_via_walker` / `.price_intent` / `.harness_validation`
    grew an additive `exit_slippage: Optional[float] = None` kwarg that forwards to
    `_walk_via_exit_manager` only when `walker == "exit_manager"` and the value is not None.
  * `pdt_blocked_counterfactual._resolve_exit_slippage_arg` parses the new `--exit-slippage`
    CLI flag: None passthrough, a float, or the literal "live" (which must fail loudly --
    analysis/pain-ledger/latency.json carries no dollar-denominated exit-slippage field as of
    2026-09-03, entry-fills-only pipeline TIMING in seconds, wrong arms too).
  * `whole_engine_null.walk_one` grew an additive `exit_slippage: float =
    DEFAULT_EXIT_SLIPPAGE` kwarg (imported from exit_manager_walk.py -- the SAME constant that
    module's own kwarg already defaulted to), forwarded to `walk_exit_manager`.

THE INVARIANT THIS FILE EXISTS TO HOLD: adding the override must not, by itself, move a single
historical number for any existing caller (harness_validation()/main() with no --exit-slippage;
every whole_engine_null.py call site, which never passed exit_slippage before). Pure/synthetic
tests only -- no network, no OPRA bar cache, no ledger I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest/lib", "setup/scripts", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pytest  # noqa: E402

import pdt_blocked_counterfactual as pbc  # noqa: E402
import whole_engine_null as wen  # noqa: E402
from exit_manager_walk import DEFAULT_EXIT_SLIPPAGE  # noqa: E402


# --------------------------------------------------------------- pdt_blocked_counterfactual


def test_price_via_walker_default_omits_exit_slippage_kwarg(monkeypatch):
    """exit_slippage=None (the default) must NOT pass an exit_slippage kwarg to
    _walk_via_exit_manager at all -- so that adapter's own 0.01 default is what actually runs,
    byte-identical to every call site that predates this override."""
    captured = {}

    def _fake(fill, shape, bars, *, trigger_level=0.0, spy_map=None, exit_slippage=0.01):
        captured["exit_slippage"] = exit_slippage
        return {"pnl": 0.0, "legs": [], "n_legs": 0, "mfe_pct": None, "walked_stage": None}

    monkeypatch.setattr(pbc, "_walk_via_exit_manager", _fake)
    pbc._price_via_walker("exit_manager", {}, {}, None, trigger_level=0.0, spy_map={})
    assert captured["exit_slippage"] == 0.01, (
        "omitting --exit-slippage must reproduce _walk_via_exit_manager's own untouched "
        "default (0.01), not silently pass a different value")


def test_price_via_walker_forwards_explicit_override(monkeypatch):
    captured = {}

    def _fake(fill, shape, bars, *, trigger_level=0.0, spy_map=None, exit_slippage=0.01):
        captured["exit_slippage"] = exit_slippage
        return {"pnl": 0.0, "legs": [], "n_legs": 0, "mfe_pct": None, "walked_stage": None}

    monkeypatch.setattr(pbc, "_walk_via_exit_manager", _fake)
    pbc._price_via_walker("exit_manager", {}, {}, None, trigger_level=0.0, spy_map={},
                          exit_slippage=0.0)
    assert captured["exit_slippage"] == 0.0


def test_price_via_walker_ignores_override_for_multileg(monkeypatch):
    """The multileg walker has no market-stages-only asymmetry to ablate on -- its own
    slippage=0.01 kwarg (applied to every leg) must be untouched by --exit-slippage."""
    captured = {}

    def _fake_walk(fill, shape, bars, *, trigger_level, fill_mode, spy_closes, slippage):
        captured["slippage"] = slippage
        return {"pnl": 0.0, "legs": [], "n_legs": 0, "mfe_pct": None}

    monkeypatch.setattr(pbc, "walk", _fake_walk)
    pbc._price_via_walker("multileg", {"date": "2026-07-08"}, {}, None, trigger_level=0.0,
                          spy_map={}, exit_slippage=0.0)
    assert captured["slippage"] == 0.01, "multileg's own slippage constant must not move"


def test_resolve_exit_slippage_arg_none_passthrough():
    assert pbc._resolve_exit_slippage_arg(None) is None


def test_resolve_exit_slippage_arg_parses_float():
    assert pbc._resolve_exit_slippage_arg("0") == 0.0
    assert pbc._resolve_exit_slippage_arg("0.05") == pytest.approx(0.05)


def test_resolve_exit_slippage_arg_live_fails_loudly_when_field_absent():
    """analysis/pain-ledger/latency.json (as of 2026-09-03) is a pipeline-TIMING instrument
    with no dollar exit-slippage field -- 'live' must raise, never silently fall back to 0 or
    to the default."""
    with pytest.raises(SystemExit):
        pbc._resolve_exit_slippage_arg("live")


# --------------------------------------------------------------- whole_engine_null


def test_walk_one_default_exit_slippage_equals_module_constant():
    """The additive kwarg's default must equal exit_manager_walk.DEFAULT_EXIT_SLIPPAGE (0.02)
    -- the exact value walk_exit_manager already used before this kwarg existed on walk_one,
    so a call site that never passes exit_slippage sees no behavior change."""
    import inspect
    sig = inspect.signature(wen.walk_one)
    assert sig.parameters["exit_slippage"].default == DEFAULT_EXIT_SLIPPAGE == 0.02


def test_walk_one_forwards_exit_slippage_to_walk_exit_manager(monkeypatch):
    captured = {}

    class _FakeResult:
        resolved = True
        exit_reason = "time_stop"
        dollar_pnl = 0.0
        hold_minutes = 0
        legs = []

    def _fake_walk_exit_manager(**kwargs):
        captured.update(kwargs)
        return _FakeResult()

    monkeypatch.setattr(wen, "walk_exit_manager", _fake_walk_exit_manager)
    monkeypatch.setattr(wen, "get_1m_bars", lambda *a, **k: __import__("pandas").DataFrame(
        {"timestamp_et": [__import__("pandas").Timestamp("2026-07-08 10:00")],
         "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}))
    monkeypatch.setattr(wen, "day_frame", lambda spy5, date: __import__("pandas").DataFrame(
        {"timestamp_et": [__import__("pandas").Timestamp("2026-07-08 10:00")], "close": [500.0]}))

    import datetime as dt
    wen.walk_one(symbol="SPY260708C00500000", side="C", date="2026-07-08",
                entry_time_et=dt.datetime(2026, 7, 8, 9, 40), entry_premium=1.0, qty=1,
                trigger_level=None, spy5=None, budget=wen.FetchBudget(0.0),
                exit_slippage=0.07)
    assert captured["exit_slippage"] == 0.07


def test_walk_one_omits_override_uses_default(monkeypatch):
    captured = {}

    class _FakeResult:
        resolved = True
        exit_reason = "time_stop"
        dollar_pnl = 0.0
        hold_minutes = 0
        legs = []

    def _fake_walk_exit_manager(**kwargs):
        captured.update(kwargs)
        return _FakeResult()

    monkeypatch.setattr(wen, "walk_exit_manager", _fake_walk_exit_manager)
    monkeypatch.setattr(wen, "get_1m_bars", lambda *a, **k: __import__("pandas").DataFrame(
        {"timestamp_et": [__import__("pandas").Timestamp("2026-07-08 10:00")],
         "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}))
    monkeypatch.setattr(wen, "day_frame", lambda spy5, date: __import__("pandas").DataFrame(
        {"timestamp_et": [__import__("pandas").Timestamp("2026-07-08 10:00")], "close": [500.0]}))

    import datetime as dt
    wen.walk_one(symbol="SPY260708C00500000", side="C", date="2026-07-08",
                entry_time_et=dt.datetime(2026, 7, 8, 9, 40), entry_premium=1.0, qty=1,
                trigger_level=None, spy5=None, budget=wen.FetchBudget(0.0))
    assert captured["exit_slippage"] == DEFAULT_EXIT_SLIPPAGE
