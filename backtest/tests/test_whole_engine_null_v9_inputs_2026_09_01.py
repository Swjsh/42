"""test_whole_engine_null_v9_inputs_2026_09_01.py -- guards for the two V9 input-fidelity
fixes in setup/scripts/whole_engine_null.py (2026-09-01 build):

BUG 1: walk_one hardcoded structure_stop_enabled=True for every row, even though 7/121 P1
rows really ran stop_mode="premium" live. Fix: thread the row's REAL recorded stop_mode
through walk_one -> structure_stop_enabled=(stop_mode=="structure"), with None (missing/null
real stop_mode) preserving today's exact default (True). SCOPED TO V9 ONLY -- run_null_a and
run_null_c (the synthetic null legs) have no real per-row stop_mode to thread and must keep
byte-identical behaviour (structure_stop_enabled=True), which this file also pins.

BUG 2: walk_one hardcoded ribbon_tick_df=None, making ribbon_flip exits (15/121 P1 rows)
structurally unreproducible. Fix (path A -- feasible, built): reconstruct a real per-tick
ribbon series from automation/state/core-decisions.jsonl (which has full coverage for every
P1 trading day on both "safe" and "bold" accounts, verified this build) via a look-ahead-safe
backward-as-of merge onto each contract's own 1-minute option-bar timestamps
(build_ribbon_tick_df), threaded ONLY into V9's walk_one calls via the new `ribbon_account`
kwarg (default None preserves today's ribbon_tick_df=None for N_a/N_c).

All tests here monkeypatch wen.get_1m_bars / wen.walk_exit_manager / wen._ribbon_series_for
-- no network I/O, no dependency on the live trades-enriched.jsonl or core-decisions.jsonl
files (whose real contents change day to day).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import whole_engine_null as wen  # noqa: E402


def _fake_opt_df(date: str, n: int = 3, start: str = "09:40:00") -> pd.DataFrame:
    base = pd.Timestamp(f"{date} {start}")
    return pd.DataFrame([
        {"timestamp_et": base + pd.Timedelta(minutes=i), "open": 1.0, "high": 1.05,
         "low": 0.95, "close": 1.0}
        for i in range(n)
    ])


def _fake_spy5(date: str) -> pd.DataFrame:
    rows = []
    for h, m in [(9, 30), (9, 35), (9, 40), (15, 55)]:
        rows.append({"timestamp_et": pd.Timestamp(f"{date} {h:02d}:{m:02d}:00"),
                    "open": 700.0, "high": 700.1, "low": 699.9, "close": 700.0,
                    "date": date, "time": f"{h:02d}:{m:02d}"})
    return pd.DataFrame(rows)


def _fake_walk_result(**overrides):
    base = dict(resolved=True, exit_reason="time_stop", dollar_pnl=10.0, hold_minutes=5,
               legs=[object()])
    base.update(overrides)
    return SimpleNamespace(**base)


# ------------------------------------------------------------------------------------------ #
# BUG 1 -- structure_stop_enabled must reflect the row's REAL stop_mode
# ------------------------------------------------------------------------------------------ #
def test_walk_one_premium_stop_mode_disables_structure_stop(monkeypatch):
    date = "2026-08-11"
    captured = {}

    def fake_get_1m_bars(contract, d, budget):
        return _fake_opt_df(d)

    def fake_walk_exit_manager(**kwargs):
        captured.update(kwargs)
        return _fake_walk_result()

    monkeypatch.setattr(wen, "get_1m_bars", fake_get_1m_bars)
    monkeypatch.setattr(wen, "walk_exit_manager", fake_walk_exit_manager)

    out = wen.walk_one(symbol="SPY260811C00771000", side="C", date=date,
                       entry_time_et=pd.Timestamp(f"{date} 09:39:00").to_pydatetime(),
                       entry_premium=1.0, qty=3, trigger_level=771.0,
                       spy5=_fake_spy5(date), budget=wen.FetchBudget(0.0),
                       stop_mode="premium")

    assert out is not None
    assert captured["structure_stop_enabled"] is False, (
        "a row whose REAL stop_mode is 'premium' must be walked with structure_stop_enabled=False")


def test_walk_one_structure_stop_mode_enables_structure_stop(monkeypatch):
    date = "2026-08-11"
    captured = {}

    def fake_get_1m_bars(contract, d, budget):
        return _fake_opt_df(d)

    def fake_walk_exit_manager(**kwargs):
        captured.update(kwargs)
        return _fake_walk_result()

    monkeypatch.setattr(wen, "get_1m_bars", fake_get_1m_bars)
    monkeypatch.setattr(wen, "walk_exit_manager", fake_walk_exit_manager)

    out = wen.walk_one(symbol="SPY260811C00771000", side="C", date=date,
                       entry_time_et=pd.Timestamp(f"{date} 09:39:00").to_pydatetime(),
                       entry_premium=1.0, qty=3, trigger_level=771.0,
                       spy5=_fake_spy5(date), budget=wen.FetchBudget(0.0),
                       stop_mode="structure")

    assert out is not None
    assert captured["structure_stop_enabled"] is True, (
        "a row whose REAL stop_mode is 'structure' must be walked with structure_stop_enabled=True")


def test_walk_one_null_stop_mode_preserves_legacy_default_true(monkeypatch):
    """A V9 row whose recorded stop_mode is itself null must keep TODAY'S exact behaviour
    (structure_stop_enabled=True) -- the task's explicit 'leave null rows alone' instruction."""
    date = "2026-08-11"
    captured = {}

    def fake_get_1m_bars(contract, d, budget):
        return _fake_opt_df(d)

    def fake_walk_exit_manager(**kwargs):
        captured.update(kwargs)
        return _fake_walk_result()

    monkeypatch.setattr(wen, "get_1m_bars", fake_get_1m_bars)
    monkeypatch.setattr(wen, "walk_exit_manager", fake_walk_exit_manager)

    out = wen.walk_one(symbol="SPY260811C00771000", side="C", date=date,
                       entry_time_et=pd.Timestamp(f"{date} 09:39:00").to_pydatetime(),
                       entry_premium=1.0, qty=3, trigger_level=771.0,
                       spy5=_fake_spy5(date), budget=wen.FetchBudget(0.0),
                       stop_mode=None)

    assert out is not None
    assert captured["structure_stop_enabled"] is True


def test_walk_one_omitted_stop_mode_kwarg_is_backward_compatible(monkeypatch):
    """A caller (N_a / N_c) that does not pass stop_mode at all -- not even None explicitly --
    must see byte-identical behaviour to before this fix: structure_stop_enabled=True."""
    date = "2026-08-11"
    captured = {}

    def fake_get_1m_bars(contract, d, budget):
        return _fake_opt_df(d)

    def fake_walk_exit_manager(**kwargs):
        captured.update(kwargs)
        return _fake_walk_result()

    monkeypatch.setattr(wen, "get_1m_bars", fake_get_1m_bars)
    monkeypatch.setattr(wen, "walk_exit_manager", fake_walk_exit_manager)

    out = wen.walk_one(symbol="SPY260811C00771000", side="C", date=date,
                       entry_time_et=pd.Timestamp(f"{date} 09:39:00").to_pydatetime(),
                       entry_premium=1.0, qty=3, trigger_level=771.0,
                       spy5=_fake_spy5(date), budget=wen.FetchBudget(0.0))

    assert out is not None
    assert captured["structure_stop_enabled"] is True
    assert captured["ribbon_tick_df"] is None


# ------------------------------------------------------------------------------------------ #
# NULL LEGS MUST STAY BYTE-IDENTICAL -- run_null_a / run_null_c never thread the new kwargs
# ------------------------------------------------------------------------------------------ #
def test_null_legs_source_never_passes_new_kwargs():
    """Source-level pin (cheaper + more durable than mocking the whole random-resample loop):
    neither run_null_a's nor run_null_c's call to walk_one may reference stop_mode= or
    ribbon_account=, which is what keeps them on walk_one's byte-identical legacy defaults."""
    src = Path(wen.__file__).read_text(encoding="utf-8")

    def _body(fn_name: str, next_fn_name: str) -> str:
        start = src.index(f"def {fn_name}(")
        end = src.index(f"def {next_fn_name}(")
        return src[start:end]

    null_a_body = _body("run_null_a", "percentile")
    null_c_body = _body("run_null_c", "evaluate_pass_criterion")
    for body, name in ((null_a_body, "run_null_a"), (null_c_body, "run_null_c")):
        assert "stop_mode=" not in body, f"{name} must not thread a real stop_mode"
        assert "ribbon_account=" not in body, f"{name} must not thread ribbon reconstruction"


def test_null_c_walk_one_call_still_defaults_structure_true(monkeypatch):
    """Functional pin (not just source grep): run_null_c's actual walk_one call, when routed
    through the REAL walk_one (not a mocked walk_one), still resolves structure_stop_enabled
    to True -- proving the wiring, not just the absence of the new keyword in the source."""
    date = "2026-08-11"
    captured_calls = []

    def fake_get_1m_bars(contract, d, budget):
        return _fake_opt_df(d)

    def fake_walk_exit_manager(**kwargs):
        captured_calls.append(kwargs)
        return _fake_walk_result()

    monkeypatch.setattr(wen, "get_1m_bars", fake_get_1m_bars)
    monkeypatch.setattr(wen, "walk_exit_manager", fake_walk_exit_manager)

    row = {"date": date, "right": "C", "strike": 771.0, "qty": 3,
           "symbol": "SPY260811C00771000", "entry_ts_et": f"{date}T09:39:00",
           "trigger_level": None, "ctx_extras": {}}
    wen.run_null_c([row], _fake_spy5(date), wen.FetchBudget(0.0))

    assert len(captured_calls) == 1
    assert captured_calls[0]["structure_stop_enabled"] is True
    assert captured_calls[0]["ribbon_tick_df"] is None


# ------------------------------------------------------------------------------------------ #
# BUG 2 -- ribbon reconstruction: cadence, look-ahead safety, MIXED pass-through, honest None
# ------------------------------------------------------------------------------------------ #
def test_core_account_for_arm_mapping():
    assert wen._core_account_for_arm("bold-2") == "bold"
    assert wen._core_account_for_arm("safe-2") == "safe"
    assert wen._core_account_for_arm("safe-3") == "safe"
    assert wen._core_account_for_arm("risky-1") == "safe"
    assert wen._core_account_for_arm("some_future_arm") == "safe"


def test_build_ribbon_tick_df_matches_opt_df_row_count(monkeypatch):
    date = "2026-08-11"
    opt_df = _fake_opt_df(date, n=5, start="09:40:00")

    ribbon_series = pd.DataFrame({
        "timestamp_et": pd.to_datetime([f"{date} 09:38:00", f"{date} 09:42:00"]),
        "stack": ["BULL", "BEAR"],
    })
    monkeypatch.setattr(wen, "_ribbon_series_for", lambda d, a: ribbon_series)

    out = wen.build_ribbon_tick_df(opt_df, date, "safe")
    assert out is not None
    assert len(out) == len(opt_df)
    assert list(out.columns) == ["stack"]


def test_build_ribbon_tick_df_returns_none_when_no_series(monkeypatch):
    date = "2026-08-11"
    opt_df = _fake_opt_df(date)
    monkeypatch.setattr(wen, "_ribbon_series_for", lambda d, a: None)
    assert wen.build_ribbon_tick_df(opt_df, date, "safe") is None


def test_build_ribbon_tick_df_is_look_ahead_safe(monkeypatch):
    """The core assertion: a bar must take the LATEST tick AT OR BEFORE its own timestamp,
    never a later one. Fixture is built so that using the LATER tick would produce a
    DIFFERENT (wrong) answer -- proving the later tick is not used, not just that some value
    is returned."""
    date = "2026-08-11"
    # opt_df bar sits at 09:41:00 -- strictly between the two ribbon ticks.
    opt_df = pd.DataFrame([
        {"timestamp_et": pd.Timestamp(f"{date} 09:41:00"), "open": 1.0, "high": 1.0,
         "low": 1.0, "close": 1.0},
    ])
    ribbon_series = pd.DataFrame({
        "timestamp_et": pd.to_datetime([f"{date} 09:39:00", f"{date} 09:45:00"]),
        "stack": ["BULL", "BEAR"],  # BEAR is LATER than the bar -- must NOT be selected
    })
    monkeypatch.setattr(wen, "_ribbon_series_for", lambda d, a: ribbon_series)

    out = wen.build_ribbon_tick_df(opt_df, date, "safe")
    assert out is not None
    assert out.iloc[0]["stack"] == "BULL", (
        "a bar at 09:41 must see the 09:39 tick (BULL), never the 09:45 tick (BEAR) -- "
        "a look-ahead leak would silently pull BEAR")


def test_build_ribbon_tick_df_bar_before_first_tick_is_inert_not_lookahead(monkeypatch):
    """A bar strictly before the day's first logged tick has nothing faithful to backward-fill
    from -- it must come back NaN/None (inert: not in ('BULL','BEAR')), never the first
    AVAILABLE tick (which would be a look-ahead leak from the bar's own future)."""
    date = "2026-08-11"
    opt_df = pd.DataFrame([
        {"timestamp_et": pd.Timestamp(f"{date} 09:30:00"), "open": 1.0, "high": 1.0,
         "low": 1.0, "close": 1.0},
    ])
    ribbon_series = pd.DataFrame({
        "timestamp_et": pd.to_datetime([f"{date} 09:35:00"]),
        "stack": ["BULL"],
    })
    monkeypatch.setattr(wen, "_ribbon_series_for", lambda d, a: ribbon_series)

    out = wen.build_ribbon_tick_df(opt_df, date, "safe")
    assert out is not None
    assert pd.isna(out.iloc[0]["stack"])


def test_build_ribbon_tick_df_mixed_passes_through_unmapped(monkeypatch):
    date = "2026-08-11"
    opt_df = pd.DataFrame([
        {"timestamp_et": pd.Timestamp(f"{date} 09:41:00"), "open": 1.0, "high": 1.0,
         "low": 1.0, "close": 1.0},
    ])
    ribbon_series = pd.DataFrame({
        "timestamp_et": pd.to_datetime([f"{date} 09:39:00"]),
        "stack": ["MIXED"],
    })
    monkeypatch.setattr(wen, "_ribbon_series_for", lambda d, a: ribbon_series)

    out = wen.build_ribbon_tick_df(opt_df, date, "safe")
    assert out.iloc[0]["stack"] == "MIXED", "MIXED must pass through untranslated, not become None"


def test_walk_one_ribbon_account_threads_reconstructed_series(monkeypatch):
    date = "2026-08-11"
    sentinel = pd.DataFrame({"stack": ["BULL", "BULL", "BEAR"]})
    captured = {}

    monkeypatch.setattr(wen, "get_1m_bars", lambda contract, d, budget: _fake_opt_df(d, n=3))
    monkeypatch.setattr(wen, "build_ribbon_tick_df", lambda opt_df, d, acct: sentinel)

    def fake_walk_exit_manager(**kwargs):
        captured.update(kwargs)
        return _fake_walk_result()

    monkeypatch.setattr(wen, "walk_exit_manager", fake_walk_exit_manager)

    out = wen.walk_one(symbol="SPY260811C00771000", side="C", date=date,
                       entry_time_et=pd.Timestamp(f"{date} 09:39:00").to_pydatetime(),
                       entry_premium=1.0, qty=3, trigger_level=771.0,
                       spy5=_fake_spy5(date), budget=wen.FetchBudget(0.0),
                       ribbon_account="safe")

    assert out is not None
    assert captured["ribbon_tick_df"] is sentinel


# ------------------------------------------------------------------------------------------ #
# run_v9 OUTPUT -- per-exit_reason breakdown, n_scratch_rows, disclosed limitations
# ------------------------------------------------------------------------------------------ #
def test_run_v9_output_has_exit_reason_breakdown_and_scratch_count(monkeypatch):
    monkeypatch.setattr(wen, "_ribbon_series_for", lambda d, a: None)  # force "no series" path

    def fake_walk_one(**kwargs):
        return {"dollar_pnl": kwargs["entry_premium"] * 0, "qty": kwargs["qty"],
               "exit_avg_px": 1.0, "exit_reason": "eod", "hold_minutes": 1, "n_legs": 1}

    call_i = {"n": 0}
    canned = [
        {"pnl": 50.0, "walked": 40.0},   # structure_stop, agree
        {"pnl": -30.0, "walked": 25.0},  # premium_stop, disagree
        {"pnl": 0.0, "walked": 10.0},    # scratch row (real_pnl == 0)
        {"pnl": -15.0, "walked": -5.0},  # ribbon_flip, agree
    ]

    def fake_walk_one2(**kwargs):
        i = call_i["n"]
        call_i["n"] += 1
        return {"dollar_pnl": canned[i]["walked"], "qty": kwargs["qty"], "exit_avg_px": 1.0,
               "exit_reason": "whatever", "hold_minutes": 1, "n_legs": 1}

    monkeypatch.setattr(wen, "walk_one", fake_walk_one2)

    rows = [
        {"symbol": "A", "date": "2026-08-11", "arm": "safe-2", "right": "C", "qty": 1,
         "entry_px": 1.0, "entry_ts_et": "2026-08-11T09:40:00", "pnl_dollars": canned[0]["pnl"],
         "exit_reason": "structure_stop", "stop_mode": "structure", "ctx_extras": {}},
        {"symbol": "B", "date": "2026-08-11", "arm": "bold-2", "right": "P", "qty": 1,
         "entry_px": 1.0, "entry_ts_et": "2026-08-11T09:41:00", "pnl_dollars": canned[1]["pnl"],
         "exit_reason": "premium_stop", "stop_mode": "premium", "ctx_extras": {}},
        {"symbol": "C", "date": "2026-08-11", "arm": "risky-1", "right": "C", "qty": 1,
         "entry_px": 1.0, "entry_ts_et": "2026-08-11T09:42:00", "pnl_dollars": canned[2]["pnl"],
         "exit_reason": "time_stop", "stop_mode": None, "ctx_extras": {}},
        {"symbol": "D", "date": "2026-08-11", "arm": "risky-1", "right": "P", "qty": 1,
         "entry_px": 1.0, "entry_ts_et": "2026-08-11T09:43:00", "pnl_dollars": canned[3]["pnl"],
         "exit_reason": "ribbon_flip", "stop_mode": "structure", "ctx_extras": {}},
    ]

    out = wen.run_v9(rows, _fake_spy5("2026-08-11"), wen.FetchBudget(0.0))

    assert out["n_compared"] == 4
    assert out["n_scratch_rows"] == 1
    assert set(out["agreement_by_exit_reason"].keys()) == {
        "structure_stop", "premium_stop", "time_stop", "ribbon_flip"}
    assert out["agreement_by_exit_reason"]["structure_stop"]["n"] == 1
    assert out["agreement_by_exit_reason"]["structure_stop"]["n_agree"] == 1
    assert out["agreement_by_exit_reason"]["premium_stop"]["n_agree"] == 0
    assert out["agreement_by_exit_reason"]["ribbon_flip"]["n_agree"] == 1
    # ribbon coverage was forced to "no series" above -> disclosed, not silently dropped
    assert out["ribbon_reconstruction"]["n_rows_without_ribbon_series"] == 4
    assert any("core-decisions.jsonl" in lim for lim in out["known_limitations"])
    assert any("ribbon_flip" in lim for lim in out["known_limitations"])
    # stop_mode fidelity disclosed
    assert out["stop_mode_fidelity"]["n_real_stop_mode"] == 3
    assert out["stop_mode_fidelity"]["n_defaulted_structure_true"] == 1


def test_run_v9_threads_stop_mode_and_ribbon_account_per_row(monkeypatch):
    seen = []

    def fake_walk_one(**kwargs):
        seen.append({"stop_mode": kwargs.get("stop_mode"),
                    "ribbon_account": kwargs.get("ribbon_account")})
        return {"dollar_pnl": 1.0, "qty": kwargs["qty"], "exit_avg_px": 1.0,
               "exit_reason": "x", "hold_minutes": 1, "n_legs": 1}

    monkeypatch.setattr(wen, "walk_one", fake_walk_one)
    monkeypatch.setattr(wen, "_ribbon_series_for", lambda d, a: None)

    rows = [
        {"symbol": "A", "date": "2026-08-11", "arm": "safe-2", "right": "C", "qty": 1,
         "entry_px": 1.0, "entry_ts_et": "2026-08-11T09:40:00", "pnl_dollars": 5.0,
         "exit_reason": "structure_stop", "stop_mode": "structure", "ctx_extras": {}},
        {"symbol": "B", "date": "2026-08-11", "arm": "bold-2", "right": "P", "qty": 1,
         "entry_px": 1.0, "entry_ts_et": "2026-08-11T09:41:00", "pnl_dollars": -5.0,
         "exit_reason": "premium_stop", "stop_mode": "premium", "ctx_extras": {}},
    ]
    wen.run_v9(rows, _fake_spy5("2026-08-11"), wen.FetchBudget(0.0))

    assert seen[0] == {"stop_mode": "structure", "ribbon_account": "safe"}
    assert seen[1] == {"stop_mode": "premium", "ribbon_account": "bold"}


def test_sign_agreement_min_unchanged():
    assert wen.SIGN_AGREEMENT_MIN == 0.85


# --------------------------------------------------------------------------------------- #
# MAGNITUDE FIDELITY (added 2026-09-02). Sign agreement was the ONLY fidelity bar any
# exit-walk study used, and the PDT-blocked-counterfactual run proved that insufficient:
# 95.35% sign agreement while replaying its anchor set to -$2,201.60 against an actual
# -$538.00. These pin that magnitude is now DISCLOSED -- and, just as importantly, that it
# is NOT silently turned into a pass/fail bar fitted to values we have already seen.
# --------------------------------------------------------------------------------------- #
def _cmp(real, walked):
    return [{"real_pnl": r, "walked_pnl": w} for r, w in zip(real, walked)]


def test_magnitude_fidelity_reports_aggregate_and_per_side_ratios():
    # winners under-reproduced, losers exact -- the shape actually observed on P1.
    out = wen._magnitude_fidelity(_cmp([100.0, 200.0, -50.0], [88.0, 176.0, -50.0]))
    assert out["n"] == 3
    assert out["actual_total_dollars"] == 250.0
    assert out["replay_total_dollars"] == 214.0
    assert out["winners"]["ratio"] == round(264.0 / 300.0, 4)
    assert out["losers"]["ratio"] == 1.0, "losers replayed exactly must read 1.0"
    assert out["aggregate_ratio"] == round(214.0 / 250.0, 4)


def test_magnitude_fidelity_criterion_is_pre_registered_not_fitted_here():
    """SUPERSEDES test_magnitude_fidelity_is_disclosure_not_a_gate (2026-09-03,
    WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY). That test pinned "no bar exists yet" -- true
    at the time, and exactly the gap this fold closes: a magnitude criterion NOW exists
    (backtest/lib/walker_magnitude_fidelity.py), pre-registered from V9's OWN prior run
    (analysis/whole-engine-null/2026-09-02.json) and the PDT anchor's numbers -- NOT fitted
    to whatever population this specific call happens to score. The still-load-bearing
    invariant from the old test survives unchanged: magnitude never feeds
    `harness_reliable` (see test_sign_agreement_remains_the_only_reliability_gate below) --
    it is a SECOND, independent read, reported alongside the sign gate, never instead of it."""
    out = wen._magnitude_fidelity(_cmp([10.0, -10.0], [5.0, -20.0]))
    assert "criterion" in out
    assert out["criterion"]["verdict"] in ("PASS", "FAIL", "INSUFFICIENT")
    assert "backtest/lib/walker_magnitude_fidelity.py" in out["criterion"]["note"]
    assert not any(k in ("pass", "harness_reliable") for k in out), (
        "magnitude must not introduce a key that could be mistaken for the sign-based gate")


def test_magnitude_fidelity_never_divides_by_a_zero_denominator():
    out = wen._magnitude_fidelity(_cmp([50.0, -50.0], [10.0, -10.0]))
    assert out["aggregate_ratio"] is None, "net actual is 0 -- must report None, not divide"
    assert out["winners"]["ratio"] is not None and out["losers"]["ratio"] is not None


def test_magnitude_fidelity_handles_empty_input():
    assert wen._magnitude_fidelity([]) == {"n": 0}


def test_sign_agreement_remains_the_only_reliability_gate():
    """Guard the separation: harness_reliable must key off sign agreement alone."""
    src = (REPO / "setup" / "scripts" / "whole_engine_null.py").read_text(encoding="utf-8")
    assert '"harness_reliable": rate >= SIGN_AGREEMENT_MIN' in src, (
        "harness_reliable must depend on the sign-agreement rate only")
    assert "magnitude" not in src.split('"harness_reliable"')[1].split("\n")[0]
