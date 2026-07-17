"""Guard for backtest/tools/replay_today_eval.py (GOAL-REPLAY-TODAY-GREEN iteration 1 eval
harness). Load-bearing invariants:

  1. DETERMINISM: same tape + same config -> byte-identical per-arm P&L across two independent
     runs. The whole point of an eval harness is that a later iteration's lever change is the
     ONLY thing that can move the score -- if the harness itself is non-deterministic, no lever
     comparison built on top of it means anything.
  2. FAITHFULNESS REGRESSION PIN: this run's actual per-arm replay P&L (and the resulting
     all_faithful=False verdict) is pinned. If a future edit to the harness or its upstream
     inputs (params.json, aggressive/params.json, today's OPRA cache) silently changes these
     numbers, this test fails loud instead of the drift going unnoticed -- exactly the C7
     "silent success is failure" anti-pattern this repo's doctrine warns about.
  3. STRIKE-OFFSET SIGN CONVENTION: crypto/lib/strike_selection.py's tables use
     positive=ITM/negative=OTM; lib.orchestrator.run_backtest's strike_offset kwarg uses the
     OPPOSITE convention (positive=OTM/negative=ITM, per bold_strike_axis_ab.py's own
     STRIKE_CELLS = [("OTM-3", 3), ..., ("ITM-2", -2)]). replay_today_eval.strike_offset_for()
     must apply exactly one sign flip -- this was gotten wrong once during this file's own
     construction (a throwaway diagnostic script, not the shipped tool) and is worth a
     standing regression guard.
  4. HARNESS SCOPE DISCLOSURE: every NAMED_EVENTS row marked in_scope=False must carry a
     non-empty out_of_scope_reason -- an eval harness that silently drops a named capture
     target instead of disclosing why is worse than no capture report at all.

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_replay_today_eval.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import replay_today_eval as rte  # noqa: E402
from crypto.lib.strike_selection import V15_SAFE_TIERS, V15_BOLD_TIERS  # noqa: E402

# Pinned baseline (iteration 1, 2026-07-17 real tape + real OPRA fills). See
# analysis/recommendations/replay-today-baseline-2026-07-17.json for the full record.
PINNED_TOTAL_PNL = {
    "core_safe": 55.12,
    "core_bold": -250.0,
    "fleet_safe_3": 0.0,
    "fleet_risky_1": 0.0,
    "fleet_risky_3": 32.75,
}
PINNED_DETERMINISM_HASH = "5e4c7d50e577e0ca"
PINNED_ALL_FAITHFUL = False
PINNED_N_FAITHFUL = 2  # fleet_safe_3 + fleet_risky_1 (both trivially 0==0)


@pytest.fixture(scope="module")
def spy_vix():
    return rte.load_data()


@pytest.fixture(scope="module")
def all_results(spy_vix):
    spy, vix = spy_vix
    core_safe = rte.run_core_safe(spy, vix)
    core_bold = rte.run_core_bold(spy, vix)
    fleet = {k: rte.run_fleet_arm(spy, vix, k) for k in rte.FLEET_ARMS}
    return {"core_safe": core_safe, "core_bold": core_bold, **fleet}


# ---------------------------------------------------------------------------------------------
# 1) DETERMINISM
# ---------------------------------------------------------------------------------------------
def test_determinism_two_independent_runs_match(spy_vix):
    spy, vix = spy_vix
    run_a = {
        "core_safe": rte.run_core_safe(spy, vix),
        "core_bold": rte.run_core_bold(spy, vix),
        **{k: rte.run_fleet_arm(spy, vix, k) for k in rte.FLEET_ARMS},
    }
    run_b = {
        "core_safe": rte.run_core_safe(spy, vix),
        "core_bold": rte.run_core_bold(spy, vix),
        **{k: rte.run_fleet_arm(spy, vix, k) for k in rte.FLEET_ARMS},
    }
    assert rte.determinism_hash(run_a) == rte.determinism_hash(run_b)
    for arm in run_a:
        assert run_a[arm]["total_pnl"] == run_b[arm]["total_pnl"], arm
        assert run_a[arm]["n_trades"] == run_b[arm]["n_trades"], arm


def test_determinism_hash_pinned(all_results):
    assert rte.determinism_hash(all_results) == PINNED_DETERMINISM_HASH, (
        "determinism_hash drifted from the pinned iteration-1 baseline -- either the harness "
        "changed or an upstream input (params.json / aggressive/params.json / today's OPRA "
        "cache) did. Investigate before trusting any lever comparison built on this harness."
    )


# ---------------------------------------------------------------------------------------------
# 2) FAITHFULNESS REGRESSION PIN
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arm_key,expected_pnl", list(PINNED_TOTAL_PNL.items()))
def test_pinned_total_pnl_per_arm(all_results, arm_key, expected_pnl):
    assert all_results[arm_key]["total_pnl"] == pytest.approx(expected_pnl, abs=0.01)


def test_faithfulness_verdict_pinned(all_results):
    faithfulness = {k: rte.faithfulness_for(k, v["total_pnl"]) for k, v in all_results.items()}
    n_faithful = sum(1 for f in faithfulness.values() if f["faithful"])
    all_faithful = all(f["faithful"] for f in faithfulness.values())
    assert n_faithful == PINNED_N_FAITHFUL
    assert all_faithful == PINNED_ALL_FAITHFUL, (
        "Harness faithfulness verdict flipped since iteration 1. If this now reads "
        "all_faithful=True, DO NOT treat that as ready-to-tune without re-running the "
        "fable-too-good hunt -- a sudden green after a documented dominant divergence "
        "(level-set source mismatch, see module docstring) is exactly the artifact this "
        "repo's doctrine says to distrust first."
    )


# ---------------------------------------------------------------------------------------------
# 3) STRIKE-OFFSET SIGN CONVENTION
# ---------------------------------------------------------------------------------------------
def test_strike_offset_sign_convention_safe_atm():
    # V15_SAFE_TIERS <$2K tier: strike_offset=0 (ATM) -- sign-flip-invariant case, doesn't
    # discriminate the bug on its own, but must still be exactly 0.
    so = rte.strike_offset_for(1485.31, V15_SAFE_TIERS)
    assert so == 0


def test_strike_offset_sign_convention_bold_otm3():
    # V15_BOLD_TIERS <$2K tier: crypto-lib strike_offset=-3 (their OWN convention: negative=OTM).
    # orchestrator/simulator convention is OPPOSITE (positive=OTM, per bold_strike_axis_ab.py's
    # STRIKE_CELLS = [("OTM-3", 3), ...]) -- strike_offset_for() must return +3, NOT -3.
    so = rte.strike_offset_for(1963.04, V15_BOLD_TIERS)
    assert so == 3, (
        f"strike_offset_for(<$2K, V15_BOLD_TIERS) returned {so}, expected +3 (OTM-3 in "
        f"orchestrator/simulator sign convention). Passing -3 here would silently simulate "
        f"ITM-3 instead of OTM-3 -- the exact sign bug caught in a throwaway diagnostic while "
        f"building this harness (never shipped, but worth a standing regression guard)."
    )


def test_strike_offset_direction_matches_sanity_invariant(all_results):
    # Sanity invariant (strike_selection.py docstring): for a PUT, OTM iff strike < spot.
    # core_bold trades OTM-3 puts -- every fill's strike must be BELOW that bar's entry_spot-
    # implied round-close, i.e. strictly less than round(SPY close) that day (~743).
    bold_trades = all_results["core_bold"]["trades"]
    assert bold_trades, "expected >=1 core_bold trade in the pinned baseline"
    for t in bold_trades:
        if t["side"] == "P":
            assert t["strike"] < 745, (
                f"OTM-3 put strike {t['strike']} is not below the day's ~743-745 spot range -- "
                f"sign convention regression (would indicate an ITM strike was simulated)."
            )


# ---------------------------------------------------------------------------------------------
# 4) HARNESS SCOPE DISCLOSURE
# ---------------------------------------------------------------------------------------------
def test_out_of_scope_events_carry_a_reason():
    for ev in rte.NAMED_EVENTS:
        if not ev["in_scope"]:
            reason = ev.get("out_of_scope_reason", "")
            assert reason and len(reason) > 20, (
                f"NAMED_EVENTS entry {ev['id']!r} is marked in_scope=False but has no "
                f"substantive out_of_scope_reason -- silent scope-narrowing is not allowed."
            )


def test_named_events_cover_both_core_arms():
    arms_covered = {ev["arm"] for ev in rte.NAMED_EVENTS}
    assert "core_safe" in arms_covered
    assert "core_bold" in arms_covered


def test_capture_report_matches_named_events_count(all_results):
    events = rte.capture_report(all_results)
    assert len(events) == len(rte.NAMED_EVENTS)
    for ev in events:
        if not ev["in_scope"]:
            assert ev["captured"] is None
