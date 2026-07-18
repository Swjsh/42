"""Guard for backtest/tools/replay_today_eval.py (GOAL-REPLAY-TODAY-GREEN ITERATION 2: the
faithful-signal rebuild). Load-bearing invariants:

  1. DETERMINISM: same recorded decision streams + same real OPRA cache -> byte-identical
     per-arm P&L across two independent runs. If this harness itself is non-deterministic, no
     future lever comparison built on top of it means anything.
  2. SIGNAL-LAYER FIX PIN: iteration 1's dominant failure was capturing only 1/4 named events
     because it re-detected levels from price history instead of reading the engine's own
     recorded signal stream. Iteration 2 must capture 5/5 in-scope named events (100%) and
     reproduce live's own recorded tier via classify_tier() on every extracted entry (12/12) --
     this is what actually got fixed this iteration, and it is worth a standing regression guard
     independent of whether the EXIT layer is faithful yet.
  3. FAITHFULNESS REGRESSION PIN: this run's actual per-arm replay P&L (and the resulting
     all_faithful=False verdict) is pinned. The exit layer's residual gap (5-min-bar data
     resolution vs live's ~1-minute ticks, see module docstring) is diagnosed, not fixed, this
     iteration -- if a future edit silently changes these numbers without a documented reason,
     this test fails loud (C7 "silent success is failure").
  4. HARNESS SCOPE DISCLOSURE: every NAMED_EVENTS row marked in_scope=False must carry a
     non-empty out_of_scope_reason.

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

# Pinned baseline (iteration 2, 2026-07-17 real tape + real OPRA fills + recorded decision
# streams). See analysis/recommendations/replay-today-baseline-2026-07-17.json for the full
# record.
PINNED_TOTAL_PNL = {
    "core_safe": -312.0,
    "core_bold": 65.25,
    "fleet_safe_3": -83.25,
    "fleet_risky_1": -138.75,
    "fleet_risky_3": -36.75,
}
PINNED_DETERMINISM_HASH = "4d57bc48d151e1e2"
PINNED_ALL_FAITHFUL = False
PINNED_N_FAITHFUL = 0
PINNED_N_CAPTURED = 5
PINNED_N_IN_SCOPE = 5
PINNED_N_DECISION_MATCHES = 12
PINNED_N_ENTRIES = 12


def _build_all_results():
    core_today = rte.rows_for_today(rte.load_jsonl(rte.CORE_DECISIONS_PATH))
    fleet_today = {arm: rte.rows_for_today(rte.load_jsonl(path))
                   for arm, path in rte.FLEET_DECISIONS_PATHS.items()}
    entries_by_arm = {"core_safe": [], "core_bold": []}
    for e in rte.extract_core_entries(core_today):
        entries_by_arm[e["arm"]].append(e)
    for arm in rte.FLEET_ARM_IDS:
        entries_by_arm[arm] = rte.extract_fleet_entries(arm, fleet_today[arm])

    import json
    core_safe_params = json.loads(rte.CORE_SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
    core_bold_params = json.loads(rte.CORE_BOLD_PARAMS_PATH.read_text(encoding="utf-8"))
    all_entries = [e for es in entries_by_arm.values() for e in es]
    rte.enrich_exit_shape(all_entries, core_safe_params, core_bold_params)
    mismatches = rte.decision_layer_check(all_entries)

    levels_active, levels_carry, _ = rte.load_levels()
    spy_rth, ribbon_df = rte.load_spy_ribbon()

    all_results = {}
    for arm, es in entries_by_arm.items():
        trades = []
        for e in es:
            fill, status = rte.simulate_entry(e, spy_rth, ribbon_df, levels_active, levels_carry)
            if fill is None:
                continue
            trades.append(rte.fill_to_dict(e, fill))
        trades.sort(key=lambda t: t["entry_time_et"])
        all_results[arm] = {
            "arm": arm, "trades": trades, "n_trades": len(trades),
            "total_pnl": round(sum(t["dollar_pnl"] for t in trades), 2),
        }
    return all_results, all_entries, mismatches


@pytest.fixture(scope="module")
def built():
    return _build_all_results()


@pytest.fixture(scope="module")
def all_results(built):
    return built[0]


# ---------------------------------------------------------------------------------------------
# 1) DETERMINISM
# ---------------------------------------------------------------------------------------------
def test_determinism_two_independent_runs_match():
    run_a, _, _ = _build_all_results()
    run_b, _, _ = _build_all_results()
    assert rte.determinism_hash(run_a) == rte.determinism_hash(run_b)
    for arm in run_a:
        assert run_a[arm]["total_pnl"] == run_b[arm]["total_pnl"], arm
        assert run_a[arm]["n_trades"] == run_b[arm]["n_trades"], arm


def test_determinism_hash_pinned(all_results):
    assert rte.determinism_hash(all_results) == PINNED_DETERMINISM_HASH, (
        "determinism_hash drifted from the pinned iteration-2 baseline -- either the harness "
        "changed or an upstream input (core-decisions.jsonl, fleet decisions.jsonl, params.json, "
        "key-levels.json, today's OPRA cache) did. Investigate before trusting any lever "
        "comparison built on this harness."
    )


# ---------------------------------------------------------------------------------------------
# 2) SIGNAL-LAYER FIX PIN -- the actual iteration-2 win, independent of exit-layer faithfulness.
# ---------------------------------------------------------------------------------------------
def test_capture_is_100_percent_on_in_scope_events(all_results):
    events = rte.capture_report({arm: res["trades"] for arm, res in all_results.items()})
    n_in_scope = sum(1 for e in events if e["in_scope"])
    n_captured = sum(1 for e in events if e["in_scope"] and e["captured"])
    assert n_in_scope == PINNED_N_IN_SCOPE
    assert n_captured == PINNED_N_CAPTURED, (
        f"capture regressed to {n_captured}/{n_in_scope} -- iteration 1 scored 1/4 because it "
        f"re-detected levels from price history instead of reading the engine's own recorded "
        f"signal stream. Iteration 2 must stay at 100% capture (this is the actual fix -- "
        f"entries are read verbatim, not re-detected)."
    )


def test_decision_layer_tier_reproduction(built):
    _, all_entries, mismatches = built
    assert len(all_entries) == PINNED_N_ENTRIES
    assert len(all_entries) - len(mismatches) == PINNED_N_DECISION_MATCHES, (
        "classify_tier() re-applied to recorded/reconstructed triggers no longer reproduces "
        "live's own recorded tier on every entry -- the decision-layer re-run this task called "
        "for has drifted from a clean match. Inspect the mismatches list."
    )


# ---------------------------------------------------------------------------------------------
# 3) FAITHFULNESS REGRESSION PIN
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arm_key,expected_pnl", list(PINNED_TOTAL_PNL.items()))
def test_pinned_total_pnl_per_arm(all_results, arm_key, expected_pnl):
    assert all_results[arm_key]["total_pnl"] == pytest.approx(expected_pnl, abs=0.01)


def test_faithfulness_verdict_pinned(all_results):
    trades_today = rte.load_trades_csv_today()
    _, live_engine_only, _ = rte.compute_live_truth(trades_today)
    faithfulness = {k: rte.faithfulness_for(k, v["total_pnl"], live_engine_only.get(k, 0.0))
                     for k, v in all_results.items()}
    n_faithful = sum(1 for f in faithfulness.values() if f["faithful"])
    all_faithful = all(f["faithful"] for f in faithfulness.values())
    assert n_faithful == PINNED_N_FAITHFUL
    assert all_faithful == PINNED_ALL_FAITHFUL, (
        "Harness faithfulness verdict flipped since iteration 2. If this now reads "
        "all_faithful=True, DO NOT treat that as ready-to-tune without re-running the "
        "fable-too-good hunt -- a sudden green after a documented, quantified 5-minute-bar "
        "data-resolution gap (see module docstring EXIT LAYER section) is exactly the artifact "
        "this repo's doctrine says to distrust first. It would mean either the OPRA cache "
        "gained finer resolution (verify) or the harness stopped exercising the real exit path."
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


def test_j_called_trade_correctly_excluded_from_engine_only_truth():
    trades_today = rte.load_trades_csv_today()
    raw, engine_only, manual_excluded = rte.compute_live_truth(trades_today)
    # The 12:04 J-called 746C is the one known manual trade today (journal j_override='Y') --
    # engine_only must be strictly less than raw for core_safe by exactly that excluded amount.
    assert manual_excluded.get("core_safe", 0.0) == pytest.approx(89.0, abs=0.01)
    assert raw["core_safe"] - engine_only["core_safe"] == pytest.approx(89.0, abs=0.01)
