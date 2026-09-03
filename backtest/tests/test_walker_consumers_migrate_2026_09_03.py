"""GUARD for WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK (2026-09-03,
automation/overnight/queue.md:2561) -- the `--walker {multileg,exit_manager}` switch added to
`setup/scripts/pdt_blocked_counterfactual.py`.

WALKER-MARKET-STAGE-FILL-ROOT-FIX's negative result (queue.md:2550) closed the door on further
patching `multileg_exit_walk`: it cannot reach the magnitude criterion without a 1-min-native
rewrite. `exit_manager_walk.walk_exit_manager` already passes it on the V9 anchor (ratio
0.645). This file pins:

  1. `multileg` (the default, EVERY pre-existing call site) is a BYTE-IDENTICAL dispatch to
     the exact `multileg_exit_walk.walk()` call this script always made -- a snapshot test on
     a synthetic fixture (no OPRA cache / ledger I/O needed).
  2. `exit_manager` dispatches to the new `_walk_via_exit_manager` adapter instead, which
     honours `trigger_level`/`structure_stop_enabled` with the EXACT SAME convention multileg
     already uses (`structure_stop_enabled=bool(trigger_level)`, trigger_level passed
     unconverted -- 0.0 stays 0.0, never coerced to None).
  3. `harness_validation(walker=...)` forwards the walker choice into pricing and captures
     `recorded_stage`/`walked_stage` per row so `stage_decomposition` (already shipped in
     `walker_magnitude_fidelity.py`) can localize a magnitude defect.
  4. `exit_manager_magnitude_gate(hv)` -- the pure PASS/FAIL/INSUFFICIENT gate the queue item
     requires BEFORE any G1-G4 number from the exit_manager walker may be trusted.

Pure-function / monkeypatched-dispatch tests only -- no network, no OPRA bar cache, no ledger
I/O for tests 1-9. RED-PROOF (exercised manually, quoted in the session report): (a) inverting
the `walker == "exit_manager"` dispatch check in `_price_via_walker` flips
`test_default_walker_dispatch_is_byte_identical_to_direct_walk_call` AND
`test_exit_manager_walker_dispatches_to_adapter_not_walk` to fail; (b) changing
`structure_stop_enabled=bool(trigger_level)` to a hardcoded `False` in `_walk_via_exit_manager`
flips `test_walk_via_exit_manager_structure_stop_enabled_true_when_trigger_level_present`;
(c) loosening `exit_manager_magnitude_gate` to `return True` unconditionally flips
`test_exit_manager_magnitude_gate_false_on_fail_and_insufficient`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "setup" / "scripts"
_LIB = _ROOT / "backtest" / "lib"
_TOOLS = _ROOT / "backtest" / "tools"
_FLEET = _ROOT / "automation" / "state" / "fleet"
for _p in (_SCRIPTS, _LIB, _TOOLS, _FLEET, _ROOT / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import pdt_blocked_counterfactual as pbc  # noqa: E402


# ============================================================================================ #
# fixtures
# ============================================================================================ #
def _synthetic_bars() -> pd.DataFrame:
    """A TP1-then-EOD path: entry 1.00, bar 3 crosses tp1_premium_pct (ribbon_ride's post-
    STOP-B shape is +100% -> 2.00), remainder marks out at the last close."""
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime(
            ["2026-08-01 09:35:00", "2026-08-01 09:40:00", "2026-08-01 09:45:00"]),
        "open": [1.00, 1.05, 2.10], "high": [1.00, 1.05, 2.10],
        "low": [1.00, 1.05, 2.10], "close": [1.00, 1.05, 2.10],
    })


def _synthetic_fill() -> dict:
    return {"entry_premium": 1.00, "qty": 10, "symbol": "SPY260801C00600000",
           "date": "2026-08-01", "entry_time": "09:35:00", "strategy": "RIBBON"}


# ============================================================================================ #
# 1. default walker ("multileg") is a byte-identical dispatch
# ============================================================================================ #
def test_default_walker_dispatch_is_byte_identical_to_direct_walk_call():
    bars, fill = _synthetic_bars(), _synthetic_fill()
    shape = pbc.canonical_shape("2026-08-01")
    via_dispatch = pbc._price_via_walker("multileg", fill, shape, bars,
                                         trigger_level=0.0, spy_map={})
    direct = pbc.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme",
                      spy_closes=None, slippage=0.01)
    assert via_dispatch == direct


def test_price_intent_default_walker_calls_walk_not_the_exit_manager_adapter(monkeypatch):
    called = {"walk": False, "adapter": False}

    def _spy_walk(*a, **kw):
        called["walk"] = True
        return {"pnl": 0.0, "legs": [], "n_legs": 0, "mfe_pct": 0.0}

    def _spy_adapter(*a, **kw):
        called["adapter"] = True
        return {"pnl": 0.0, "legs": [], "n_legs": 0, "mfe_pct": None}

    monkeypatch.setattr(pbc, "walk", _spy_walk)
    monkeypatch.setattr(pbc, "_walk_via_exit_manager", _spy_adapter)
    intent = {"date": "2026-08-01", "entry_premium": 1.0, "qty": 10,
             "symbol": "SPY260801C00600000", "entry_time": "09:35:00", "setup": "RIBBON",
             "trigger_level": None}
    pbc.price_intent(intent, _synthetic_bars(), {})
    assert called["walk"] is True
    assert called["adapter"] is False


# ============================================================================================ #
# 2. exit_manager walker dispatches to the new adapter, not multileg's walk()
# ============================================================================================ #
def test_exit_manager_walker_dispatches_to_adapter_not_walk(monkeypatch):
    called = {"walk": False, "adapter": False}

    def _spy_walk(*a, **kw):
        called["walk"] = True
        return {"pnl": 0.0, "legs": [], "n_legs": 0, "mfe_pct": 0.0}

    def _spy_adapter(fill, shape, bars, *, trigger_level=0.0, spy_map=None):
        called["adapter"] = True
        return {"pnl": 0.0, "legs": [], "n_legs": 0, "mfe_pct": None}

    monkeypatch.setattr(pbc, "walk", _spy_walk)
    monkeypatch.setattr(pbc, "_walk_via_exit_manager", _spy_adapter)
    bars, fill = _synthetic_bars(), _synthetic_fill()
    shape = pbc.canonical_shape("2026-08-01")
    pbc._price_via_walker("exit_manager", fill, shape, bars, trigger_level=650.0, spy_map={})
    assert called["adapter"] is True
    assert called["walk"] is False


def test_exit_manager_adapter_returns_pnl_legs_n_legs_mfe_contract():
    """The adapter's return dict must satisfy the SAME contract callers already rely on
    (walk()'s {"pnl","legs","n_legs","mfe_pct"}), so no caller needs to branch on walker."""
    bars, fill = _synthetic_bars(), _synthetic_fill()
    shape = pbc.canonical_shape("2026-08-01")
    res = pbc._walk_via_exit_manager(fill, shape, bars, trigger_level=0.0, spy_map={})
    assert set(("pnl", "legs", "n_legs", "mfe_pct")) <= set(res.keys())
    assert isinstance(res["pnl"], float)
    assert isinstance(res["legs"], list)
    assert res["n_legs"] == len(res["legs"])
    for leg in res["legs"]:
        assert set(("t", "stage", "qty", "px", "pnl")) <= set(leg.keys())


# ============================================================================================ #
# 2b. WALKER-PDT-ANCHOR-FIDELITY-INPUTS (2026-09-03) step 1: walked_stage is the FULL
# compound leg sequence, not just the last leg.
# ============================================================================================ #
def test_walk_via_exit_manager_walked_stage_is_full_compound_sequence(monkeypatch):
    """A two-leg result (tp1 partial, then trail on the runner) must report
    walked_stage == 'tp1+trail', matching trades-enriched.jsonl's own compound exit_reason
    convention -- NOT just the last leg ('trail'), which is the exact labeling artifact
    WALKER-STAGE-DISAGREE-RESIDUAL-2026-09-03.md Finding 0 diagnosed."""
    class _Leg:
        def __init__(self, stage, ts, qty, px, pnl):
            self.stage, self.ts_et, self.qty, self.fill_price, self.leg_pnl = (
                stage, ts, qty, px, pnl)

    def _spy_walk_exit_manager(**kw):
        class _R:
            resolved = True
            exit_reason = "trail"
            dollar_pnl = 273.4
            legs = [_Leg("tp1", pd.Timestamp("2026-08-01 10:00"), 2, 2.00, 200.0),
                   _Leg("trail", pd.Timestamp("2026-08-01 11:00"), 1, 1.734, 73.4)]
        return _R()

    monkeypatch.setattr(pbc, "walk_exit_manager", _spy_walk_exit_manager)
    res = pbc._walk_via_exit_manager(_synthetic_fill(), pbc.canonical_shape("2026-08-01"),
                                     _synthetic_bars(), trigger_level=0.0, spy_map={})
    assert res["walked_stage"] == "tp1+trail"


# ============================================================================================ #
# 2c. WALKER-PDT-ANCHOR-FIDELITY-INPUTS (2026-09-03) step 2: ribbon_tick_df wiring
# ============================================================================================ #
def test_walk_via_exit_manager_builds_ribbon_tick_df_when_account_given(monkeypatch):
    """A fill carrying an 'account' key must get a REAL (non-None) ribbon_tick_df, built via
    whole_engine_null.build_ribbon_tick_df -- NOT the permanently-None value this adapter used
    before this fold."""
    captured = {}
    sentinel = pd.DataFrame({"stack": ["BULL", "BEAR", "BULL"]})

    def _spy_walk_exit_manager(**kw):
        captured.update(kw)
        class _R:
            resolved, exit_reason, dollar_pnl, legs = True, "tp1", 100.0, []
        return _R()

    monkeypatch.setattr(pbc, "walk_exit_manager", _spy_walk_exit_manager)
    monkeypatch.setattr(pbc.wen, "build_ribbon_tick_df", lambda opt_df, date, account: sentinel)
    fill = dict(_synthetic_fill())
    fill["account"] = "safe"
    pbc._walk_via_exit_manager(fill, pbc.canonical_shape("2026-08-01"), _synthetic_bars(),
                               trigger_level=0.0, spy_map={})
    assert captured["ribbon_tick_df"] is sentinel


def test_walk_via_exit_manager_ribbon_tick_df_none_without_account(monkeypatch):
    """Backward-compatible default: a fill with no 'account' key (every caller predating this
    fold) must keep ribbon_tick_df=None -- not a silent behavior change for those callers."""
    captured = {}

    def _spy_walk_exit_manager(**kw):
        captured.update(kw)
        class _R:
            resolved, exit_reason, dollar_pnl, legs = True, "tp1", 100.0, []
        return _R()

    monkeypatch.setattr(pbc, "walk_exit_manager", _spy_walk_exit_manager)
    fill = dict(_synthetic_fill())  # no "account" key
    pbc._walk_via_exit_manager(fill, pbc.canonical_shape("2026-08-01"), _synthetic_bars(),
                               trigger_level=0.0, spy_map={})
    assert captured["ribbon_tick_df"] is None


# ============================================================================================ #
# 3. structure_stop_enabled / trigger_level convention matches multileg's own
# ============================================================================================ #
def test_walk_via_exit_manager_structure_stop_enabled_true_when_trigger_level_present(monkeypatch):
    captured = {}

    def _spy_walk_exit_manager(**kw):
        captured.update(kw)
        class _R:
            resolved, exit_reason, dollar_pnl, legs = True, "tp1", 100.0, []
        return _R()

    monkeypatch.setattr(pbc, "walk_exit_manager", _spy_walk_exit_manager)
    pbc._walk_via_exit_manager(_synthetic_fill(), pbc.canonical_shape("2026-08-01"),
                               _synthetic_bars(), trigger_level=650.0, spy_map={})
    assert captured["structure_stop_enabled"] is True
    assert captured["trigger_level"] == 650.0  # unconverted, not coerced


def test_walk_via_exit_manager_structure_stop_enabled_false_on_zero_trigger_level(monkeypatch):
    captured = {}

    def _spy_walk_exit_manager(**kw):
        captured.update(kw)
        class _R:
            resolved, exit_reason, dollar_pnl, legs = True, "tp1", 100.0, []
        return _R()

    monkeypatch.setattr(pbc, "walk_exit_manager", _spy_walk_exit_manager)
    pbc._walk_via_exit_manager(_synthetic_fill(), pbc.canonical_shape("2026-08-01"),
                               _synthetic_bars(), trigger_level=0.0, spy_map={})
    assert captured["structure_stop_enabled"] is False
    assert captured["trigger_level"] == 0.0  # not None -- matches multileg's own convention


# ============================================================================================ #
# 4. no-bars-after-entry honest gap, matching walk()'s own error-dict contract
# ============================================================================================ #
def test_walk_via_exit_manager_no_bars_after_entry_returns_error_dict():
    fill = dict(_synthetic_fill())
    fill["entry_time"] = "16:00:00"  # after every bar in the fixture
    res = pbc._walk_via_exit_manager(fill, pbc.canonical_shape("2026-08-01"),
                                     _synthetic_bars(), trigger_level=0.0, spy_map={})
    assert "error" in res
    assert res["pnl"] == 0.0


# ============================================================================================ #
# 5. harness_validation threads `walker` into pricing (monkeypatched I/O boundary)
# ============================================================================================ #
def _fake_anchor_row() -> dict:
    return {"date": "2026-08-01", "arm": "safe-2", "symbol": "SPY260801C00600000",
           "stop_mode": "premium", "entry_px": 1.0, "qty": 10,
           "entry_ts_et": "2026-08-01T09:35:00", "pnl_dollars": 50.0,
           "trigger_level": None, "exit_reason": "tp1"}


def test_harness_validation_forwards_walker_choice_to_pricer(monkeypatch):
    seen_walkers = []

    def _spy_dispatch(walker, fill, shape, bars, *, trigger_level, spy_map, **_kw):
        seen_walkers.append(walker)
        return {"pnl": 60.0, "legs": [{"stage": "tp1"}], "n_legs": 1, "mfe_pct": None}

    monkeypatch.setattr(pbc, "load_anchor_sample", lambda: [_fake_anchor_row()])
    monkeypatch.setattr(pbc, "spy_by_day", lambda: {})
    monkeypatch.setattr(pbc, "load_contract_bars", lambda sym: _synthetic_bars())
    monkeypatch.setattr(pbc, "_price_via_walker", _spy_dispatch)

    pbc.harness_validation(walker="exit_manager")
    assert seen_walkers == ["exit_manager"]

    seen_walkers.clear()
    pbc.harness_validation()  # default
    assert seen_walkers == ["multileg"]


def test_harness_validation_rows_carry_recorded_and_walked_stage(monkeypatch):
    def _spy_dispatch(walker, fill, shape, bars, *, trigger_level, spy_map, **_kw):
        return {"pnl": 60.0, "legs": [{"t": "09:45", "stage": "structure_stop", "qty": 10,
                                       "px": 1.5, "pnl": 60.0}], "n_legs": 1, "mfe_pct": None}

    monkeypatch.setattr(pbc, "load_anchor_sample", lambda: [_fake_anchor_row()])
    monkeypatch.setattr(pbc, "spy_by_day", lambda: {})
    monkeypatch.setattr(pbc, "load_contract_bars", lambda sym: _synthetic_bars())
    monkeypatch.setattr(pbc, "_price_via_walker", _spy_dispatch)

    hv = pbc.harness_validation(walker="exit_manager")
    assert hv["n"] == 1
    row = hv["rows"][0]
    assert row["recorded_stage"] == "tp1"        # from the anchor row's own exit_reason
    assert row["walked_stage"] == "structure_stop"  # from the walker's last leg
    assert "stage_decomposition" in hv
    # recorded != walked -> this row lands in the disagree bucket
    assert hv["stage_decomposition"]["stage_disagree"]["n"] == 1
    assert hv["stage_decomposition"]["stage_agree"]["n"] == 0


# ============================================================================================ #
# 6. exit_manager_magnitude_gate -- pure PASS/FAIL/INSUFFICIENT gate
# ============================================================================================ #
def test_exit_manager_magnitude_gate_true_only_on_pass():
    assert pbc.exit_manager_magnitude_gate({"magnitude_fidelity_verdict": "PASS"}) is True


def test_exit_manager_magnitude_gate_false_on_fail_and_insufficient():
    assert pbc.exit_manager_magnitude_gate({"magnitude_fidelity_verdict": "FAIL"}) is False
    assert pbc.exit_manager_magnitude_gate({"magnitude_fidelity_verdict": "INSUFFICIENT"}) is False
    assert pbc.exit_manager_magnitude_gate({}) is False


# ============================================================================================ #
# 7. CLI parsing -- default is multileg, output paths never collide
# ============================================================================================ #
def test_cli_default_walker_is_multileg():
    args = pbc._parse_args([])
    assert args.walker == "multileg"


def test_cli_accepts_exit_manager_walker():
    args = pbc._parse_args(["--walker", "exit_manager"])
    assert args.walker == "exit_manager"


def test_cli_rejects_unknown_walker():
    with pytest.raises(SystemExit):
        pbc._parse_args(["--walker", "not-a-real-walker"])


def test_exit_manager_output_paths_never_equal_published_artifact():
    assert pbc.OUT_JSON_EXIT_MGR != pbc.OUT_JSON
    assert pbc.OUT_MD_EXIT_MGR != pbc.OUT_MD
    assert pbc.OUT_JSON_EXIT_MGR.name.endswith("-exit-manager-walk.json")


# ============================================================================================ #
# 8. WALKER-PDT-ANCHOR-FIDELITY-INPUTS (2026-09-03) step 3: --bars 1min dispatch
# ============================================================================================ #
def test_cli_default_bars_is_5min():
    assert pbc._parse_args([]).bars == "5min"


def test_cli_accepts_1min_bars():
    assert pbc._parse_args(["--bars", "1min"]).bars == "1min"


def test_load_anchor_bars_5min_default_calls_load_contract_bars(monkeypatch):
    calls = []
    monkeypatch.setattr(pbc, "load_contract_bars", lambda sym: calls.append(sym) or _synthetic_bars())
    cache = {}
    bars = pbc._load_anchor_bars("SPY260801C00600000", "2026-08-01", "5min", cache)
    assert calls == ["SPY260801C00600000"]
    assert bars is not None
    assert cache["SPY260801C00600000"] is bars  # cached by symbol alone, matches prior behavior


def test_load_anchor_bars_1min_calls_fetch_1min_cached_not_5min_cache(monkeypatch):
    calls = {"fetch_1min": [], "load_5min": 0}

    def _spy_fetch_1min(sym, date):
        calls["fetch_1min"].append((sym, date))
        return _synthetic_bars(), "rest_fetch"

    monkeypatch.setattr(pbc, "fetch_1min_cached", _spy_fetch_1min)
    monkeypatch.setattr(pbc, "load_contract_bars",
                        lambda sym: (_ for _ in ()).throw(AssertionError("must not call 5min cache")))
    cache = {}
    bars = pbc._load_anchor_bars("SPY260801C00600000", "2026-08-01", "1min", cache)
    assert calls["fetch_1min"] == [("SPY260801C00600000", "2026-08-01")]
    assert bars is not None
    assert cache[("SPY260801C00600000", "2026-08-01")] is bars  # keyed by (symbol,date)


def test_harness_validation_threads_bar_resolution_to_pricer(monkeypatch):
    """harness_validation(bar_resolution='1min') must route bar loading through
    _load_anchor_bars with '1min', not silently fall back to the 5min cache."""
    seen = []

    def _spy_load_anchor_bars(sym, date, bar_resolution, cache):
        seen.append((sym, date, bar_resolution))
        return _synthetic_bars()

    monkeypatch.setattr(pbc, "load_anchor_sample", lambda: [_fake_anchor_row()])
    monkeypatch.setattr(pbc, "spy_by_day", lambda: {})
    monkeypatch.setattr(pbc, "_load_anchor_bars", _spy_load_anchor_bars)
    monkeypatch.setattr(pbc, "_price_via_walker",
                        lambda walker, fill, shape, bars, *, trigger_level, spy_map, **_kw:
                        {"pnl": 50.0, "legs": [], "n_legs": 0, "mfe_pct": None})

    pbc.harness_validation(walker="exit_manager", bar_resolution="1min")
    assert seen == [("SPY260801C00600000", "2026-08-01", "1min")]


# ============================================================================================ #
# 9. Magnitude gate must still HALT before any cohort pricing/G1-G4 on a FAIL/INSUFFICIENT
# verdict -- re-affirms test group 6 at the point main() actually consumes the gate.
# ============================================================================================ #
def test_exit_manager_magnitude_gate_halts_on_fail_verdict_from_real_harness_shape():
    """A harness_validation-shaped dict with verdict FAIL must NOT pass the gate -- the exact
    input shape exit_manager_magnitude_gate is called with in main()."""
    hv = {"walker": "exit_manager", "n": 43, "magnitude_fidelity_verdict": "FAIL",
         "magnitude_fidelity": {"aggregate_ratio": 2.4212}}
    assert pbc.exit_manager_magnitude_gate(hv) is False
