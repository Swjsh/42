"""Guards for rolling_loss_circuit_study.py -- the WEEKLY-CIRCUIT-BREAKER-CORE calibration.

WHAT THIS MODULE DECIDED, AND WHY THE GUARDS MATTER MORE THAN USUAL. The study returned a
NULL: across an 8-cell window x threshold grid on real fills, every cell COST the book money
(-$53 to -$1,718) and six of eight made the worst drawdown DEEPER, not shallower. A circuit
breaker that worsens the drawdown it exists to limit is not a safety device.

That is a result nobody wants, which is exactly the kind that quietly rots. If a later edit
breaks the counterfactual in a flattering direction, the null silently becomes a green light
for a risk control that the evidence never supported. So the arithmetic is pinned here.

THE ONE MECHANISM TO UNDERSTAND: blocked days must contribute 0 to the counterfactual AND
enter the trailing window as 0 -- never their real P&L. A circuit that consults the P&L of a
day it prevented is reading a number that would not exist. It also happens to be the source
of the null: safe-3 lost -1048/-156/-102, tripped a 3-day/-$1000 circuit, and the very next
day was +457. The circuit blocks the rebound.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "setup" / "scripts" / "rolling_loss_circuit_study.py"


@pytest.fixture(scope="module")
def rl():
    spec = importlib.util.spec_from_file_location("rolling_loss_circuit_study_g", MOD)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["rolling_loss_circuit_study_g"] = m
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------------------
# max_drawdown is a PATH statistic
# ---------------------------------------------------------------------------------------

def test_max_drawdown_basic(rl):
    assert rl.max_drawdown([100.0, -30.0, -20.0, 40.0]) == -50.0


def test_max_drawdown_is_never_positive(rl):
    assert rl.max_drawdown([10.0, 20.0, 30.0]) == 0.0
    assert rl.max_drawdown([]) == 0.0


def test_max_drawdown_depends_on_ORDER(rl):
    """If a refactor ever computes this from a total or a sorted series it stops being a
    drawdown. Same days, different order, different answer -- that IS the definition."""
    losses_after_the_peak = rl.max_drawdown([100.0, -50.0, -50.0])   # peak 100 -> trough 0
    losses_split_by_a_win = rl.max_drawdown([-50.0, 100.0, -50.0])   # never 100 below a peak
    assert losses_after_the_peak == -100.0
    assert losses_split_by_a_win == -50.0
    assert losses_after_the_peak < losses_split_by_a_win, (
        "the same three days in a different order gave the same answer -- this is computing "
        "a total or a sorted statistic, not a drawdown"
    )


# ---------------------------------------------------------------------------------------
# The counterfactual's no-peeking contract
# ---------------------------------------------------------------------------------------

def _days(*pnls):
    return [(f"2026-08-{i + 1:02d}", float(p)) for i, p in enumerate(pnls)]


def test_window_is_not_judged_before_it_is_full(rl):
    """A 2-day-old arm has not had the chance to breach a 3-day limit. Judging a short
    history as a breach would block every arm on its opening days."""
    # Day 2's trailing history is a SINGLE day of -1200, which already exceeds the -1000
    # limit in magnitude. Only the len(recent) >= window test stops it counting. A fixture
    # where the short history does not breach proves nothing (caught in RED-proof).
    out = rl.counterfactual(_days(-1200.0, -1200.0), window=3, threshold=1000.0)
    assert out["days_blocked"] == 0, (
        "a 2-day-old arm was blocked on a 3-day rule -- an incomplete window is being "
        "judged as a breach"
    )
    assert out["counterfactual_pnl"] == -2400.0


def test_a_blocked_day_contributes_zero_not_its_real_pnl(rl):
    days = _days(-500.0, -300.0, -300.0, +999.0)
    out = rl.counterfactual(days, window=3, threshold=1000.0)
    assert out["days_blocked"] == 1, "the -1100 trailing sum should have tripped the circuit"
    assert out["counterfactual_pnl"] == -1100.0, (
        "the blocked day's +999 leaked into the counterfactual -- the circuit is being "
        "credited with P&L from a day it prevented"
    )
    assert out["delta"] == -999.0


def test_a_blocked_day_enters_the_trailing_window_as_zero(rl):
    """The self-release property. Zeros age into the window and lift the trailing sum back
    over the threshold with no separate reset rule -- but only if the blocked day is
    recorded as 0. Recording its REAL (large, positive) P&L would release the circuit
    early using a number that never happened.
    """
    # The blocked day's REAL P&L is a large LOSS. That is what discriminates: carrying it
    # into the window keeps the circuit tripped for days afterwards on the strength of a
    # loss that never happened, because the entry was blocked. Zero releases it correctly.
    # (A fixture where the blocked day is a large WIN cannot tell the two apart -- both
    # release. Found in RED-proof, where a `trailing.append(pnl)` mutant escaped.)
    days = _days(-500.0, -300.0, -300.0, -5000.0, +100.0, +100.0)
    out = rl.counterfactual(days, window=3, threshold=1000.0)
    assert out["blocked_dates"] == ["2026-08-04"], (
        f"expected exactly one blocked day; got {out['blocked_dates']} -- if days 5-6 are "
        "also blocked, the prevented day's -5000 was carried into the trailing window"
    )
    assert out["counterfactual_pnl"] == -1100.0 + 100.0 + 100.0


def test_a_sustained_drawdown_blocks_consecutive_days_as_ONE_trip(rl):
    """trips counts EPISODES, days_blocked counts days. Conflating them would report a
    single bad stretch as many independent confirmations."""
    out = rl.counterfactual(_days(-600.0, -600.0, -600.0, -50.0, -50.0, -50.0),
                            window=3, threshold=1000.0)
    assert out["trips"] == 1
    assert out["days_blocked"] >= 2


def test_threshold_must_be_a_positive_magnitude(rl):
    """Passing -1000 (the sign it is compared against) would make the test `sum <= +1000`
    and block essentially every day. Fail loudly rather than invert the rule."""
    with pytest.raises(ValueError):
        rl.counterfactual(_days(-100.0), window=1, threshold=-1000.0)
    with pytest.raises(ValueError):
        rl.counterfactual(_days(-100.0), window=1, threshold=0.0)


def test_window_must_be_positive(rl):
    with pytest.raises(ValueError):
        rl.rolling_sums([1.0, 2.0], 0)


def test_a_never_tripping_circuit_is_an_exact_no_op(rl):
    days = _days(10.0, -5.0, 20.0, -3.0)
    out = rl.counterfactual(days, window=3, threshold=99999.0)
    assert out["delta"] == 0.0 and out["trips"] == 0
    assert out["max_dd_counterfactual"] == out["max_dd_actual"]


# ---------------------------------------------------------------------------------------
# Data hygiene: a missing P&L is not a flat day
# ---------------------------------------------------------------------------------------

def test_rows_with_non_numeric_pnl_are_skipped_not_zeroed(rl, tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [
        {"arm": "safe-2", "date": "2026-08-01", "pnl_dollars": -100.0},
        {"arm": "safe-2", "date": "2026-08-02", "pnl_dollars": None},
        {"arm": "safe-2", "date": "2026-08-03", "pnl_dollars": "oops"},
        {"arm": "safe-2", "date": "2026-08-04", "pnl_dollars": 50.0},
    ]), encoding="utf-8")
    out = rl.load_arm_days(p, arms=("safe-2",))
    assert out["_skipped_rows"] == 2
    assert [d for d, _ in out["safe-2"]] == ["2026-08-01", "2026-08-04"], (
        "a row with no readable P&L became a flat day -- that is fabricated data in a "
        "risk-control calibration"
    )


def test_booleans_are_not_accepted_as_pnl(rl, tmp_path):
    """`isinstance(True, int)` is True in Python. A bool in a money field is corruption."""
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"arm": "safe-2", "date": "2026-08-01", "pnl_dollars": True}),
                 encoding="utf-8")
    out = rl.load_arm_days(p, arms=("safe-2",))
    assert out["safe-2"] == [] and out["_skipped_rows"] == 1


def test_multiple_fills_on_one_day_are_summed(rl, tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [
        {"arm": "safe-2", "date": "2026-08-01", "pnl_dollars": -100.0},
        {"arm": "safe-2", "date": "2026-08-01", "pnl_dollars": 40.0},
    ]), encoding="utf-8")
    out = rl.load_arm_days(p, arms=("safe-2",))
    assert out["safe-2"] == [("2026-08-01", -60.0)]


# ---------------------------------------------------------------------------------------
# Semantics: measurement only, never an order path
# ---------------------------------------------------------------------------------------

def test_the_module_contains_no_order_or_broker_call(rl):
    """Block-new-entries-only, and in fact this module does not even evaluate live -- it is
    a study. AST, not grep: the docstring names the semantics in prose."""
    tree = ast.parse(MOD.read_text(encoding="utf-8"))
    banned = {"place_option_order", "close_position", "close_all_positions",
              "close_all_spy_options", "submit_order", "cancel_order"}
    hits = [n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in banned]
    assert not hits, f"a study module gained an order path: {hits}"


# ---------------------------------------------------------------------------------------
# THE NULL. Pinned so a flattering regression cannot quietly become a green light.
# ---------------------------------------------------------------------------------------

def test_the_recorded_null_still_holds_on_the_real_ledger(rl):
    """2026-09-02: every cell of the 8-cell grid cost the book money, and 6 of 8 made the
    worst per-arm drawdown DEEPER. If this ever flips, it is either new data (fine -- update
    the pre-registration) or a broken counterfactual (not fine). Either way it must be
    LOOKED AT, not absorbed silently."""
    if not (REPO / "analysis" / "trades-enriched.jsonl").exists():
        pytest.skip("ledger absent")
    rep = rl.run()
    cells = rep["grid"]
    assert len(cells) == 8
    losing = [c for c in cells if c["book_delta"] < 0]
    assert len(losing) == len(cells), (
        "a window/threshold cell now IMPROVES book P&L. The 2026-09-02 calibration found "
        "none did. Re-read the counterfactual before treating this as good news -- the "
        "likeliest cause is a blocked day's P&L leaking back in."
    )
    worsened = [c for c in cells if c["book_dd_improvement"] < 0]
    assert len(worsened) >= 5, (
        f"only {len(worsened)}/8 cells now deepen drawdown; the calibration recorded 6. "
        "The null that killed this proposal has moved -- re-derive it before acting."
    )


def test_the_two_surviving_candidates_are_still_the_ones_pre_registered(rl):
    """W=5/T=800 and W=5/T=1000 were the only cells that shallowed drawdown, and they are
    the two frozen for forward evaluation. They survive on n=4 and n=2 trips -- pinned here
    so their identity cannot drift out from under the pre-registration."""
    if not (REPO / "analysis" / "trades-enriched.jsonl").exists():
        pytest.skip("ledger absent")
    rep = rl.run()
    helped = {(c["window"], c["threshold"]) for c in rep["grid"]
              if c["book_dd_improvement"] > 0}
    assert helped == {(5, 800.0), (5, 1000.0)}, (
        f"the drawdown-helping cells changed to {sorted(helped)}; the pre-registration "
        "analysis/recommendations/rolling-loss-circuit-core-2026-09-02.json froze "
        "(5, 800) and (5, 1000) and must be re-issued, not silently reinterpreted"
    )
