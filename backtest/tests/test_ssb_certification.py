"""Companion guards for backtest/tools/ssb_certification_study.py (SS-B production-code
certification, 2026-07-09). Load-bearing invariants:

  1. NON-VACUOUS PIN (the task's explicit requirement): replay_production_path, on a hand-
     computed synthetic fixture, must fire the structure stop at the EXACT expected bar/price/
     P&L -- and a DELIBERATELY-WRONG stop value (a sabotaged catastrophe_stop_pct) on the SAME
     fixture must produce a DIFFERENT, also hand-verified, result. This proves the pin actually
     discriminates: if the harness regressed to use the wrong stop, the correct-case assertion
     would RED, not silently pass. (test_hand_computed_correct / test_deliberately_wrong_stop_diverges)
  2. Structure-stop-enabled flag-off must fall back to premium mode end-to-end through THIS
     module's own harness (mirrors automation/state/fleet/test_structure_stop_wiring.py's own
     flag-off guard, one layer up).
  3. last_closed_5m_close_asof must implement the SAME "closed-bar" semantics
     structure_stop_study.structure_stop_signal_time uses (next-bar-open knowability, C6) --
     cross-checked against a shared synthetic SPY history.
  4. The OP-16 edge_capture formula (winner_total - loser_exposure, loser exposure floored at 0)
     must match a hand-computed value, and a "forgot the floor" mutation must diverge from it --
     the same non-vacuous-pin pattern applied to the Task 2 formula.
  5. Structural self-consistency of the persisted analysis/recommendations/
     ssb-certification-2026-07-09.json: verdict fields follow from their own counts, and the
     OP-16 edge_capture figures re-derive from the per-trade rows exactly.

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_ssb_certification.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import ssb_certification_study as cert   # noqa: E402
import structure_stop_study as sss       # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / "ssb-certification-2026-07-09.json"

# The SS-B strategy shape, straight from the live strategies.py (never hand-copied here).
SHAPE = dict(cert.ribbon_ride_exit_shape())
assert SHAPE["stop_mode"] == "structure" and SHAPE["catastrophe_stop_pct"] == -0.50, (
    "this test module assumes RIBBON_RIDE.exit is still the SS-B structure cell -- if that "
    "changed, the fixtures below need re-deriving, not silent adaptation")


def _spy_lifetime(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def _flat_bars_then_breach() -> tuple[pd.DataFrame, list]:
    """Shared fixture: PUT side, entry=1.00, trigger_level=500.0.

    SPY 5m bars: flat below trigger through 09:30, closes ABOVE the trigger (501) on the
    09:35-09:40 bar -> per structure_stop_study's own next-bar-open convention, the breach is
    knowable starting at option-bar-open 09:40.

    Option 1m bars: flat at 1.00 through 09:38 (no TP1, no catastrophe -- TP1 needs
    best>=2.00, the -50% cap needs worst<=0.50). 09:39: a dip to low=0.90 (breaches an -8%
    stop of 0.92 but NOT the real -50% cap of 0.50 -- this bar is what makes test #2
    discriminating). 09:40: open=0.95 (this is where the REAL harness must fire structure_stop,
    since last_closed_5m_close first reflects the breach exactly at option-bar-open 09:40)."""
    spy_rows = [
        {"timestamp_et": dt.datetime(2026, 7, 9, 9, 30), "close": 498.0},
        {"timestamp_et": dt.datetime(2026, 7, 9, 9, 35), "close": 501.0},   # breach bar
    ]
    bars = [
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 30), 1.00, 1.05, 0.98, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 31), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 32), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 33), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 34), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 35), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 36), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 37), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 38), 1.00, 1.00, 1.00, 1.00),
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 39), 0.95, 0.96, 0.90, 0.91),  # dip, no fire (correct shape)
        sss.NormBar(dt.datetime(2026, 7, 9, 9, 40), 0.95, 0.97, 0.93, 0.94),  # structure fires HERE
    ]
    return _spy_lifetime(spy_rows), bars


# ---------------------------------------------------------------------------------------------
# 1) NON-VACUOUS PIN: correct stop vs deliberately-wrong stop
# ---------------------------------------------------------------------------------------------
def test_hand_computed_correct_structure_stop_fires_at_expected_bar_and_price():
    """THE PIN. entry=1.00, qty=6, catastrophe_stop_pct=-0.50 (the real SS-B value) ->
    runner_stop=0.50. The 09:39 dip (low=0.90) stays above 0.50 -> no catastrophe fire. At
    09:40, last_closed_5m_close=501.0 > trigger_level=500.0 (PUT side) -> structure_stop fires,
    filling at the bar's OPEN (0.95), per the C6 next-bar-open convention. Hand-computed pnl =
    (0.95 - 1.00) * 6 * 100 = -30.00."""
    spy_lifetime, bars = _flat_bars_then_breach()
    r = cert.replay_production_path(1.00, "P", 6, bars, spy_lifetime, SHAPE, 500.0, True,
                                    dt.time(15, 40))
    assert r["pnl"] == -30.00, r
    assert r["structure_fired"] is True
    assert len(r["exits"]) == 1
    assert r["exits"][0]["stage"] == "structure_stop"
    assert r["exits"][0]["fill_price"] == 0.95
    assert r["exits"][0]["dt"] == dt.datetime(2026, 7, 9, 9, 40).isoformat()


def test_deliberately_wrong_stop_diverges_from_the_pinned_result():
    """NON-VACUOUSNESS PROOF: the SAME fixture, but with catastrophe_stop_pct sabotaged to
    -0.08 (a deliberately-wrong stop -- simulating a regression that used the flag-OFF
    emergency-fallback value of -0.20's cousin instead of the real -0.50 cap). runner_stop
    becomes 0.92; the 09:39 dip (low=0.90) now breaches it BEFORE the structure stop's 09:40
    trigger time, firing premium_stop at fill=entry*(1-0.08)=0.92, pnl=(0.92-1.00)*6*100=-48.00.
    This is DIFFERENT from the pinned -30.00/structure_stop above (different stage, different
    bar, different price) -- proof that if the correct-case test above were the ONLY guard and
    someone regressed the stop value, THIS divergence is exactly the kind of bug that pin would
    catch, because the two cases produce measurably, mechanically different outcomes."""
    spy_lifetime, bars = _flat_bars_then_breach()
    sabotaged_shape = dict(SHAPE)
    sabotaged_shape["catastrophe_stop_pct"] = -0.08     # WRONG value (real production is -0.50)
    r = cert.replay_production_path(1.00, "P", 6, bars, spy_lifetime, sabotaged_shape, 500.0,
                                    True, dt.time(15, 40))
    assert r["pnl"] == -48.00, r
    assert r["structure_fired"] is False, "the wrong (tighter) stop must pre-empt the structure exit"
    assert r["exits"][0]["stage"] == "premium_stop"
    assert r["exits"][0]["fill_price"] == 0.92
    assert r["exits"][0]["dt"] == dt.datetime(2026, 7, 9, 9, 39).isoformat()
    # explicit cross-check against test #1's pinned numbers -- the two must disagree
    correct = cert.replay_production_path(1.00, "P", 6, bars, spy_lifetime, SHAPE, 500.0, True,
                                          dt.time(15, 40))
    assert r["pnl"] != correct["pnl"]
    assert r["exits"][0]["stage"] != correct["exits"][0]["stage"]


# ---------------------------------------------------------------------------------------------
# 2) FLAG-OFF FALLBACK (mirrors test_structure_stop_wiring.py, one layer up)
# ---------------------------------------------------------------------------------------------
def test_structure_stop_enabled_false_falls_back_to_premium_mode_and_never_fires_structure():
    """structure_stop_enabled=False at from_entry -> stop_mode='premium' even with a
    structure-declaring shape + a real trigger_level -- the flag is the ONLY switch (matches
    exit_manager.ExitState.from_entry's own resolution rule, exercised end-to-end here)."""
    spy_lifetime, bars = _flat_bars_then_breach()
    r = cert.replay_production_path(1.00, "P", 6, bars, spy_lifetime, SHAPE, 500.0, False,
                                    dt.time(15, 40))
    assert r["structure_fired"] is False
    assert r["final_stop_mode"] == "premium"
    # with the flag off, RIBBON_RIDE's OWN premium_stop_pct (-0.20) governs, not the -0.50 cap
    stop_stage_exits = [e for e in r["exits"] if e["stage"] == "premium_stop"]
    if stop_stage_exits:
        assert stop_stage_exits[0]["fill_price"] == round(1.00 * (1 - 0.20), 4)


# ---------------------------------------------------------------------------------------------
# 3) last_closed_5m_close_asof matches structure_stop_signal_time's own closed-bar semantics
# ---------------------------------------------------------------------------------------------
def test_last_closed_5m_close_asof_agrees_with_structure_stop_signal_time_on_timing():
    """Both mechanisms must agree on WHEN a breach becomes knowable: structure_stop_study's
    ss_time (next bar's open) and this module's last_closed_5m_close_asof (first tick where the
    breaching bar is 'closed') must point at the SAME option-bar timestamp for the shared
    fixture -- the one structural property both implementations are supposed to share (see
    module docstring's discussion of where they can still diverge: catastrophe-vs-structure
    PRIORITY on the same bar, not the breach TIMING itself)."""
    spy_lifetime, bars = _flat_bars_then_breach()
    ss_time = sss.structure_stop_signal_time(spy_lifetime, "P", 500.0, 0.0)
    assert ss_time == dt.datetime(2026, 7, 9, 9, 40)

    # first option bar whose last_closed_5m_close_asof reflects the breach:
    first_reflecting = None
    for bar in bars:
        lc5 = cert.last_closed_5m_close_asof(spy_lifetime, bar.dt)
        if lc5 is not None and lc5 > 500.0:
            first_reflecting = bar.dt
            break
    assert first_reflecting == ss_time


def test_last_closed_5m_close_asof_none_before_any_bar_has_closed():
    spy_lifetime, bars = _flat_bars_then_breach()
    # the very first option bar (09:30) is BEFORE any 5m SPY bar (09:30 open) can have closed
    assert cert.last_closed_5m_close_asof(spy_lifetime, dt.datetime(2026, 7, 9, 9, 30)) is None


# ---------------------------------------------------------------------------------------------
# 4) OP-16 edge_capture formula -- hand-computed + non-vacuous "forgot the floor" mutation
# ---------------------------------------------------------------------------------------------
def _edge_capture(rows: list[dict]) -> float:
    winner_total = sum(r["pnl"] for r in rows if r["role"] == "winner")
    loser_exposure = sum(max(0.0, -r["pnl"]) for r in rows if r["role"] == "loser")
    return round(winner_total - loser_exposure, 2)


def _edge_capture_unfloored_bug(rows: list[dict]) -> float:
    """A deliberately-wrong formula (forgets max(0, ...) on the loser side) -- for the
    non-vacuousness proof below."""
    winner_total = sum(r["pnl"] for r in rows if r["role"] == "winner")
    loser_exposure = sum(-r["pnl"] for r in rows if r["role"] == "loser")   # BUG: no floor
    return round(winner_total - loser_exposure, 2)


def test_edge_capture_formula_hand_computed():
    rows = [
        {"role": "winner", "pnl": 300.0}, {"role": "winner", "pnl": 400.0},
        {"role": "loser", "pnl": -100.0}, {"role": "loser", "pnl": 50.0},   # a loser day with pnl>=0
    ]
    # winner_total=700, loser_exposure=max(0,100)+max(0,-50)=100+0=100 -> edge=600
    assert _edge_capture(rows) == 600.0


def test_edge_capture_formula_unfloored_mutation_diverges_when_a_loser_day_is_profitable():
    """Non-vacuousness proof: the bug only shows up when a 'loser' day is AVOIDED (engine pnl
    >= 0) -- exactly J_ANCHOR_TRADES' realistic shape where a candidate shape sometimes ducks a
    loser entirely. On the SAME rows as above, the unfloored formula double-counts the +50
    avoided-loser day as a PENALTY instead of a floor-to-zero no-op, producing a DIFFERENT
    (wrong) edge_capture -- proving the max(0, ...) floor is load-bearing, not decorative."""
    rows = [
        {"role": "winner", "pnl": 300.0}, {"role": "winner", "pnl": 400.0},
        {"role": "loser", "pnl": -100.0}, {"role": "loser", "pnl": 50.0},
    ]
    correct = _edge_capture(rows)
    buggy = _edge_capture_unfloored_bug(rows)
    assert buggy != correct
    # winner_total=700, unfloored loser_exposure = 100 + (-50) = 50 -> buggy edge = 650 (vs correct 600)
    assert buggy == 650.0


def test_j_anchor_trades_are_the_verbatim_op16_source_of_truth():
    """Cross-checks cert.J_ANCHOR_TRADES against CLAUDE.md OP-16's literal dollar figures --
    a transcription-drift guard (the module-level assert already enforces the winner-sum
    identity at import time; this test also pins the individual per-trade figures)."""
    by_date_side = {(t["date"], t["side"], t["strike"]): t["j_pnl"] for t in cert.J_ANCHOR_TRADES}
    assert by_date_side[("2026-04-29", "P", 710)] == 342.0
    assert by_date_side[("2026-05-01", "P", 721)] == 470.0
    assert by_date_side[("2026-05-04", "P", 721)] == 730.0
    assert by_date_side[("2026-05-05", "P", 722)] == -260.0
    assert by_date_side[("2026-05-06", "P", 730)] == -300.0
    assert by_date_side[("2026-05-07", "C", 734)] == -45.0
    assert by_date_side[("2026-05-07", "C", 737)] == -120.0
    assert len(cert.J_ANCHOR_TRADES) == 7


def test_occ_symbol_format():
    assert cert.occ_symbol(dt.date(2026, 4, 29), 710, "P") == "SPY260429P00710000"
    assert cert.occ_symbol(dt.date(2026, 5, 7), 737, "C") == "SPY260507C00737000"


# ---------------------------------------------------------------------------------------------
# 5) STRUCTURAL SELF-CONSISTENCY OF THE REAL PERSISTED OUTPUT
# ---------------------------------------------------------------------------------------------
def test_output_json_exists_and_has_expected_shape_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/ssb_certification_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert out["commit_certified"] == cert.SHIP_COMMIT
    assert "parity" in out and "j_anchor" in out
    assert out["parity"]["verdict"] in ("MATCH", "BENIGN-DIVERGENCE", "REAL-DIVERGENCE")
    assert out["j_anchor"]["verdict"] in ("PASS", "FAIL")
    assert out["parity"]["n_positions"] == 10


def test_output_parity_verdict_follows_from_its_own_counts_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/ssb_certification_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    p = out["parity"]
    assert p["n_match"] + p["n_benign_divergence"] + p["n_real_divergence"] == p["n_positions"]
    expect = "REAL-DIVERGENCE" if p["n_real_divergence"] else (
        "BENIGN-DIVERGENCE" if p["n_benign_divergence"] else "MATCH")
    assert p["verdict"] == expect
    for row in p["positions"]:
        expected_diff = round(row["production_path"]["pnl"] - row["study_ss_b"]["pnl"], 2)
        assert row["diff_dollars"] == expected_diff, row


def test_output_control_self_check_passed_real_run():
    """The harness's own non-structure branches (catastrophe/TP1/trail/time-stop) must
    reproduce the study's PUBLISHED CONTROL total exactly -- if this ever fails, the parity
    numbers above are not trustworthy (the harness itself would be suspect, not just the
    structure-stop wiring under test)."""
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/ssb_certification_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert out["parity"]["control_self_check"]["matches"] is True, out["parity"]["control_self_check"]


def test_output_j_anchor_edge_capture_matches_hand_formula_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/ssb_certification_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    ja = out["j_anchor"]
    rows = [{"role": r["role"], "pnl": r["ss_b_pnl"]} for r in ja["trades"]]
    assert _edge_capture(rows) == ja["edge_capture_ss_b"]
    rows_ctl = [{"role": r["role"], "pnl": r["control_pnl"]} for r in ja["trades"]]
    assert _edge_capture(rows_ctl) == ja["edge_capture_control"]
    # verdict must follow from floor + no-winner-flip, exactly as the module computes it
    winners_flipped = [r["date"] for r in ja["trades"] if r["role"] == "winner" and r["ss_b_pnl"] < 0]
    expect_pass = ja["edge_capture_ss_b"] >= ja["op16_floor"] and not winners_flipped
    assert ja["verdict"] == ("PASS" if expect_pass else "FAIL")
    assert ja["winners_flipped_negative_dates"] == winners_flipped


def test_output_j_anchor_has_all_seven_trades_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/ssb_certification_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    trades = out["j_anchor"]["trades"]
    assert len(trades) == 7
    assert sum(1 for t in trades if t["role"] == "winner") == 3
    assert sum(1 for t in trades if t["role"] == "loser") == 4
    assert {t["date"] for t in trades} == {
        "2026-04-29", "2026-05-01", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"}
