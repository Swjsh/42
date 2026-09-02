"""test_whole_engine_null_2026_09_01.py -- guards for setup/scripts/whole_engine_null.py
(TASK B1-whole-engine-null-runner). Synthetic fixtures only -- no network, no real trades
file dependency for the unit-level checks (a separate integration-style test at the bottom
touches the real trades-enriched.jsonl / SPY 5m file ONLY to check population membership,
never to assert a P&L number, which would break every time new trades land).

RED-PROOF (quoted in the build report): test_pass_criterion_beta_kill_nail was run once with
evaluate_pass_criterion's check2 condition inverted (`<` instead of `>`) to confirm the test
actually exercises the mechanism rather than passing vacuously, then reverted.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import whole_engine_null as wen  # noqa: E402


# ------------------------------------------------------------------------------------------ #
# entry_grid / spot_at -- the resampler's look-ahead + window discipline
# ------------------------------------------------------------------------------------------ #
def test_entry_grid_respects_window_bounds():
    grid = wen.entry_grid("2026-08-11")
    assert grid[0] == "09:35"
    assert grid[-1] == "15:00"
    # every point is on the 5-minute cadence the resampler actually draws from
    assert all(int(t.split(":")[1]) % 5 == 0 for t in grid)
    # RED-PROOF: an entry point outside the pre-registered window must NOT be present
    assert "09:30" not in grid and "15:05" not in grid and "15:40" not in grid


def _fake_spy5():
    rows = []
    for h, m, o in [(9, 30, 700.0), (9, 35, 701.0), (9, 40, 702.5), (15, 55, 705.0)]:
        rows.append({"timestamp_et": pd.Timestamp(f"2026-08-11 {h:02d}:{m:02d}:00"),
                    "open": o, "high": o + 0.1, "low": o - 0.1, "close": o + 0.05,
                    "date": "2026-08-11", "time": f"{h:02d}:{m:02d}"})
    return pd.DataFrame(rows)


def test_spot_at_exact_bar():
    df = _fake_spy5()
    assert wen.spot_at(df, "2026-08-11", "09:35") == 701.0


def test_spot_at_missing_bar_falls_back_before_not_after():
    df = _fake_spy5()
    # 09:37 has no bar -- must use the LAST bar AT OR BEFORE it (09:35), never a later one
    # (using a later bar would be a look-ahead leak: the resampler must never see the future).
    got = wen.spot_at(df, "2026-08-11", "09:37")
    assert got == 701.0, "spot_at must resolve to the prior CLOSED bar, not peek forward"


def test_atm_strike_rounds_to_nearest_dollar():
    assert wen.atm_strike(700.4) == 700
    assert wen.atm_strike(700.6) == 701


def test_occ_symbol_shape():
    assert wen.occ_symbol("2026-08-11", "C", 771) == "SPY260811C00771000"
    assert wen.occ_symbol("2026-08-11", "P", 771) == "SPY260811P00771000"


# ------------------------------------------------------------------------------------------ #
# N_c opposite-direction: flips SIDE only -- strike, date, qty must be byte-identical
# ------------------------------------------------------------------------------------------ #
def test_null_c_flips_side_only(monkeypatch):
    calls = []

    def fake_get_1m_bars(contract, date, budget):
        calls.append((contract, date))
        base = pd.Timestamp(f"{date} 09:40:00")
        return pd.DataFrame([
            {"timestamp_et": base, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
            {"timestamp_et": base + pd.Timedelta(minutes=1), "open": 1.0, "high": 1.0,
             "low": 1.0, "close": 1.0},
        ])

    def fake_walk_one(**kwargs):
        return {"dollar_pnl": 12.34, "qty": kwargs["qty"], "exit_avg_px": 1.0,
                "exit_reason": "eod", "hold_minutes": 5, "n_legs": 1}

    monkeypatch.setattr(wen, "get_1m_bars", fake_get_1m_bars)
    monkeypatch.setattr(wen, "walk_one", fake_walk_one)

    row = {"date": "2026-08-11", "right": "C", "strike": 771.0, "qty": 3,
           "symbol": "SPY260811C00771000", "entry_ts_et": "2026-08-11T09:40:00",
           "trigger_level": None, "ctx_extras": {}}
    out = wen.run_null_c([row], _fake_spy5(), wen.FetchBudget(0.0))

    assert out["n_trades"] == 1
    t = out["trades"][0]
    assert t["orig_side"] == "C"
    assert t["flip_side"] == "P", "opposite-direction null must flip C<->P, nothing else"
    assert t["flip_symbol"] == "SPY260811P00771000", "strike/date must stay byte-identical"
    assert t["orig_symbol"] == "SPY260811C00771000"


def test_proxy_trigger_level_direction():
    # put (bear rejection): level is ABOVE spot -> strike + above_dist
    put_row = {"trigger_level": None, "strike": 771.0, "right": "P",
              "ctx_extras": {"nearest_level_above_dist": 0.6, "nearest_level_below_dist": 2.0}}
    assert wen._proxy_trigger_level(put_row) == pytest.approx(771.6)
    # call (bull reclaim): level is BELOW spot -> strike - below_dist
    call_row = {"trigger_level": None, "strike": 771.0, "right": "C",
               "ctx_extras": {"nearest_level_above_dist": 2.0, "nearest_level_below_dist": 0.4}}
    assert wen._proxy_trigger_level(call_row) == pytest.approx(770.6)
    # real recorded value always wins over the reconstruction
    real_row = {"trigger_level": 750.0, "strike": 771.0, "right": "C", "ctx_extras": {}}
    assert wen._proxy_trigger_level(real_row) == 750.0


# ------------------------------------------------------------------------------------------ #
# pass-criterion evaluator -- hand-built distributions, mechanical grading
# ------------------------------------------------------------------------------------------ #
def _base_kwargs(**overrides):
    kw = dict(
        engine_total=1000.0, engine_total_cost=900.0,
        na_totals=[-100.0, -50.0, 0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0],
        na_totals_cost=[-120.0] * 10,
        nb_call_total=200.0,
        engine_p3_total=50.0,
        na_p3_totals=[-50.0, -25.0, 0.0, 25.0, 50.0],
        nc_total=-10.0,
        p2_n_days=25,
    )
    kw.update(overrides)
    return kw


def test_pass_criterion_all_green_passes():
    out = wen.evaluate_pass_criterion(**_base_kwargs(engine_total=5000.0))
    assert out["verdict"] == "PASS"
    assert out["all_checks_pass"] is True
    assert not any(v for k, v in out["kill_nails"].items() if k != "UNPOWERED" and k != "BETA")


def test_pass_criterion_null_dominated_fail():
    # engine sits INSIDE N_a's central 90% (p5=-95, p95=345 for this fixture) -> FAIL,
    # named nail NULL_DOMINATED.
    out = wen.evaluate_pass_criterion(**_base_kwargs(engine_total=100.0))
    assert out["verdict"] == "FAIL"
    assert "NULL_DOMINATED" in out["named_fails"]
    assert out["kill_nails"]["NULL_DOMINATED"] is True


def test_pass_criterion_beta_kill_nail():
    # engine below N_b call outright -> BETA nail fires (long calls in a rising tape did it)
    out = wen.evaluate_pass_criterion(**_base_kwargs(engine_total=150.0, nb_call_total=500.0))
    assert out["kill_nails"]["BETA"] is True
    assert out["verdict"] == "FAIL"


def test_pass_criterion_regime_bound_kill_nail():
    out = wen.evaluate_pass_criterion(**_base_kwargs(engine_total=5000.0, nc_total=75.0))
    assert out["kill_nails"]["REGIME_BOUND"] is True
    assert out["verdict"] == "FAIL"
    assert "REGIME_BOUND" in out["named_fails"]


def test_pass_criterion_down_day_blind_kill_nail():
    out = wen.evaluate_pass_criterion(**_base_kwargs(
        engine_total=5000.0, engine_p3_total=-100.0, na_p3_totals=[-10.0, 0.0, 10.0, 20.0, 30.0]))
    assert out["kill_nails"]["DOWN_DAY_BLIND"] is True
    assert out["verdict"] == "FAIL"


def test_pass_criterion_unpowered_flag_independent_of_verdict():
    # UNPOWERED (P2 < 20 days) must be reported but must NOT by itself flip an otherwise
    # clean P1 PASS to FAIL -- P2 is scored/adjudicated separately per the prereg.
    out = wen.evaluate_pass_criterion(**_base_kwargs(engine_total=5000.0, p2_n_days=3))
    assert out["kill_nails"]["UNPOWERED"] is True
    assert out["verdict"] == "PASS"


# ------------------------------------------------------------------------------------------ #
# V9 validate-the-validator GATE -- prereg addendum_2026_09_01_validator_fidelity.
# A PASS/FAIL computed by a walker that cannot reproduce the engine's own realized fill signs
# on >= SIGN_AGREEMENT_MIN of P1 entries is a statement about the harness, not the engine, so
# the reported verdict is WITHHELD. finalize_verdict() is the single point of truth and run()
# must route through it (checked below against the real latest.json artifact, not source text).
# ------------------------------------------------------------------------------------------ #
def test_finalize_verdict_withholds_when_harness_unreliable():
    assert wen.finalize_verdict("PASS", False) == wen.WITHHELD_VERDICT
    assert wen.finalize_verdict("FAIL", False) == wen.WITHHELD_VERDICT


def test_finalize_verdict_reports_mechanical_when_harness_reliable():
    assert wen.finalize_verdict("PASS", True) == "PASS"
    assert wen.finalize_verdict("FAIL", True) == "FAIL"


def test_finalize_verdict_fails_closed_on_garbage():
    assert wen.finalize_verdict("MAYBE", True) == wen.WITHHELD_VERDICT
    assert wen.finalize_verdict("PASS", None) == wen.WITHHELD_VERDICT


def test_prereg_addendum_names_the_validator_precondition():
    """The gate is written into the prereg itself (dated addendum), so it cannot be argued
    away as an unregistered knob again."""
    import json as _json
    prereg = _json.loads(wen.PREREG.read_text(encoding="utf-8"))
    add = prereg.get("addendum_2026_09_01_validator_fidelity")
    assert add, "prereg lost its validator-fidelity addendum"
    assert "0.85" in add["what"] and "WITHHELD" in add["what"]
    assert wen.SIGN_AGREEMENT_MIN == pytest.approx(0.85)


def test_latest_artifact_verdict_is_consistent_with_its_own_v9():
    """Behavioural check on the REAL output of run(): whatever latest.json holds, its
    overall_verdict must equal finalize_verdict(mechanical_verdict, harness_reliable).
    Skips only if the study has never been run on this box."""
    import json as _json
    latest = wen.OUT_DIR / "latest.json"
    if not latest.exists():
        pytest.skip("whole-engine-null has not been run on this box")
    doc = _json.loads(latest.read_text(encoding="utf-8"))
    if "mechanical_verdict" not in doc:
        pytest.fail("latest.json predates finalize_verdict(); re-run whole_engine_null.py")
    assert doc["overall_verdict"] == wen.finalize_verdict(doc["mechanical_verdict"], doc["harness_reliable"])
    if doc["v9_harness_validation"]["sign_agreement_rate"] < wen.SIGN_AGREEMENT_MIN:
        assert doc["overall_verdict"] == wen.WITHHELD_VERDICT


# ------------------------------------------------------------------------------------------ #
# cost model reuse -- must be A1's exact function, not a re-derived one
# ------------------------------------------------------------------------------------------ #
def test_cost_adjust_uses_a1_fee_model_and_2c_slip():
    trade = {"dollar_pnl": 100.0, "qty": 3, "exit_avg_px": 1.5}
    adjusted = wen.cost_adjust(trade)
    expected_fee = wen.glg.fee_ex_cat(3, 1.5)
    expected = 100.0 - expected_fee - (wen.COST_SLIP_CENTS / 100.0) * 3
    assert adjusted == pytest.approx(expected)
    assert adjusted < trade["dollar_pnl"], "cost adjustment must never IMPROVE realized P&L"


# ------------------------------------------------------------------------------------------ #
# real-data smoke test -- population membership only, no P&L assertion (would break on
# every new trade). Skips cleanly if trades-enriched.jsonl is absent (fresh checkout).
# ------------------------------------------------------------------------------------------ #
def test_p1_population_membership_real_data():
    if not wen.TRADES_ENRICHED.exists():
        pytest.skip("trades-enriched.jsonl not present in this checkout")
    rows = wen.load_engine_rows()
    pops = wen.build_populations(rows)
    p1 = pops["P1_post_ladder"]
    assert all(r["date"] >= wen.P1_START for r in p1)
    assert all(r["arm"] in wen.ACTIVE_ARMS for r in p1)
    assert all(r["attribution"] == "engine" for r in p1)
