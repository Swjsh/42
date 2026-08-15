"""Guard for backtest/tools/replay_today_eval.py (GOAL-REPLAY-TODAY-GREEN, iterations 2 + 3).
Load-bearing invariants:

  1. DETERMINISM: same recorded decision streams + same real OPRA cache -> byte-identical
     per-arm P&L across two independent runs. If this harness itself is non-deterministic, no
     future lever comparison built on top of it means anything. Pinned for BOTH the 5-min-only
     path (iteration 2, `simulate_entry`) and the 1-min-primary path (iteration 3,
     `simulate_entry_best`) -- the 5-min path stays as the documented fallback, so it must stay
     provably unchanged.
  2. SIGNAL-LAYER FIX PIN: iteration 1's dominant failure was capturing only 1/4 named events
     because it re-detected levels from price history instead of reading the engine's own
     recorded signal stream. Iteration 2 must capture 5/5 in-scope named events (100%) and
     reproduce live's own recorded tier via classify_tier() on every extracted entry (12/12) --
     this is what actually got fixed, unaffected by iteration 3's exit-layer work, and is worth
     a standing regression guard independent of whether the EXIT layer is faithful yet.
  3. FAITHFULNESS REGRESSION PINS (both iterations): iteration 2's 5-min-path per-arm replay
     P&L stays pinned (all_faithful=False, 0/5). Iteration 3's 1-min-path per-arm replay P&L is
     ALSO pinned (all_faithful=False, 2/5 -- both trivial $0/$0 arms, not a mechanism win) --
     see module docstring for the honest diagnosis: 1-min resolution fixed the entry-fill-price
     mechanism but revealed a MORE severe version of the exit-mechanism gap (the
     v15_profit_lock_mode='fixed' zero-offset breakeven floor triggers on ordinary 1-min 0DTE
     noise). If a future edit silently changes these numbers without a documented reason, this
     test fails loud (C7 "silent success is failure").
  4. HARNESS SCOPE DISCLOSURE: every NAMED_EVENTS row marked in_scope=False must carry a
     non-empty out_of_scope_reason.
  5. ITERATION 3 1-MIN-SPECIFIC PINS: exit-layer resolution counts (12 entries all use the real
     1-min path, zero 5-min fallbacks -- proves the 1-min OPRA/SPY fetch actually covers every
     traded contract) and the entry-fill-price fidelity improvement (all 12 entries' |delta| <=
     $0.10, down from up to $0.23 at 5-min).

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_replay_today_eval.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import replay_today_eval as rte  # noqa: E402

# Pinned baseline (iteration 2, 2026-07-17 real tape + real OPRA fills + recorded decision
# streams). See analysis/recommendations/replay-today-baseline-2026-07-17.json.
#
# RE-PINNED 2026-08-15 -- AND THE DRIFT IS THE FINDING, NOT THE CHORE.
#
# This harness reads LIVE params.json / strategies.py / key-levels.json, so its numbers move
# whenever exit config ships. Four J-directed exit changes landed after the pin (pre-TP1
# ratchet 1a9b1409, ladder af6cf286, trail arm +40->+75 658ecc79, ribbon buffer 20a9e792) and
# the pin was never moved with them, so it sat RED and detected nothing.
#
# WHAT MOVED, and why it matters more than the pin does:
#     arm              pinned      now      delta
#     core_safe        -312.00   -336.00   -24.00
#     core_bold          65.25     61.25    -4.00
#     fleet_safe_3      -83.25    -95.25   -12.00
#     fleet_risky_1    -138.75   -158.75   -20.00
#     fleet_risky_3     -36.75    -56.75   -20.00
#                                  TOTAL   -80.00
# EVERY ARM IS WORSE. Not one improved. The 1-min path shows the same one-directional shape.
# Sibling evidence the same night: exit_manager_replay's bold 13:51:21 went 177.4 -> 114.0
# (live made 191) via `premium_stop @ 0.61`.
#
# So across TWO replay days and SIX arm-instances the current exit config replays uniformly
# worse than the pre-ratchet baseline, with zero counter-examples. That is not proof of a
# regression -- these could be days the insurance was not needed, which is exactly what the
# ratchet is FOR -- but a one-directional result with no offsetting day anywhere in the
# available evidence is the shape that deserves a measurement, not a shrug. Pre-registered as
# PRE-TP1-RATCHET-COST-2026-08-15; escalated to J in STATUS.md.
#
# MAINTENANCE RULE: re-derive these in the SAME commit as any exit-config ship and state what
# moved. A pin quietly dragged to today's numbers is how a real exit regression slips through.
PINNED_TOTAL_PNL = {
    "core_safe": -336.0,      # was -312.00
    "core_bold": 61.25,       # was   65.25
    "fleet_safe_3": -95.25,   # was  -83.25
    "fleet_risky_1": -158.75, # was -138.75
    "fleet_risky_3": -56.75,  # was  -36.75
}
PINNED_DETERMINISM_HASH = "53a86e4ffee65adf"   # was 4d57bc48d151e1e2
PINNED_ALL_FAITHFUL = False
PINNED_N_FAITHFUL = 0
PINNED_N_CAPTURED = 5
PINNED_N_IN_SCOPE = 5
PINNED_N_DECISION_MATCHES = 12
PINNED_N_ENTRIES = 12

# ITERATION 3 (1-min exit-layer path via simulate_entry_best) -- see module docstring.
# RE-PINNED 2026-08-15, same cause and the SAME one-directional shape as the 5-min path above:
#   core_safe 0.0 -> -30.0 | core_bold 99.0 -> 83.75 | fleet_safe_3 0.0 -> -12.0
#   fleet_risky_1 0.0 -> -20.0 | fleet_risky_3 4.0 -> -16.0
# Five arms, five degradations, no improvements. Two independent exit paths agreeing on the
# direction is why this was escalated rather than absorbed.
PINNED_TOTAL_PNL_1MIN = {
    "core_safe": -30.0,       # was  0.0
    "core_bold": 83.75,       # was 99.0
    "fleet_safe_3": -12.0,    # was  0.0
    "fleet_risky_1": -20.0,   # was  0.0
    "fleet_risky_3": -16.0,   # was  4.0
}
PINNED_DETERMINISM_HASH_1MIN = "72aa9774157d44b1"   # was b1199323f7e5c827
PINNED_ALL_FAITHFUL_1MIN = False
PINNED_N_FAITHFUL_1MIN = 2
PINNED_RESOLUTION_COUNTS_1MIN = {"1min": 12, "5min_fallback": 0, "none": 0}


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


def _build_all_results_1min():
    """ITERATION 3: mirrors _build_all_results() above but routes through
    simulate_entry_best() (1-min primary, 5-min fallback) -- same recorded entries/decision
    layer, only the EXIT layer's data resolution differs."""
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

    levels_active, levels_carry, _ = rte.load_levels()
    spy_rth, ribbon_df = rte.load_spy_ribbon()
    spy_1m_rth = rte.load_spy_1min_rth()
    ribbon_1m = rte.build_ribbon_1min(spy_1m_rth, spy_rth, ribbon_df) if spy_1m_rth is not None else None
    opt_1min_cache = {}
    if rte.HIRES_DIR.exists():
        suffix = f"_1m_{rte.DATE_STR}.csv"
        for p in rte.HIRES_DIR.glob(f"SPY{rte.TRADE_DATE.strftime('%y%m%d')}*{suffix}"):
            sym = p.name[: -len(suffix)]
            df = rte.load_opt_1min(sym)
            if df is not None:
                opt_1min_cache[sym] = df

    all_results = {}
    resolution_counts = {"1min": 0, "5min_fallback": 0, "none": 0}
    for arm, es in entries_by_arm.items():
        trades = []
        for e in es:
            fill, status, resolution = rte.simulate_entry_best(
                e, spy_rth, ribbon_df, spy_1m_rth, ribbon_1m, levels_active, levels_carry, opt_1min_cache)
            resolution_counts[resolution] += 1
            if fill is None:
                continue
            trades.append(rte.fill_to_dict(e, fill, resolution))
        trades.sort(key=lambda t: t["entry_time_et"])
        all_results[arm] = {
            "arm": arm, "trades": trades, "n_trades": len(trades),
            "total_pnl": round(sum(t["dollar_pnl"] for t in trades), 2),
        }
    return all_results, resolution_counts


@pytest.fixture(scope="module")
def built():
    return _build_all_results()


@pytest.fixture(scope="module")
def all_results(built):
    return built[0]


@pytest.fixture(scope="module")
def built_1min():
    return _build_all_results_1min()


@pytest.fixture(scope="module")
def all_results_1min(built_1min):
    return built_1min[0]


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


# ---------------------------------------------------------------------------------------------
# 5) ITERATION 3 -- 1-MIN EXIT-LAYER PATH (simulate_entry_best). See module docstring for the
# full, honest diagnosis: entry-fill mechanism FIXED, exit-mechanism gap NOT fixed (revealed a
# more severe artifact instead). These pins exist so a future edit that silently changes this
# run's actual numbers fails loud (C7), not so the numbers "should" look any particular way.
# ---------------------------------------------------------------------------------------------
def test_1min_determinism_two_independent_runs_match():
    run_a, _ = _build_all_results_1min()
    run_b, _ = _build_all_results_1min()
    assert rte.determinism_hash(run_a) == rte.determinism_hash(run_b)
    for arm in run_a:
        assert run_a[arm]["total_pnl"] == run_b[arm]["total_pnl"], arm


def test_1min_determinism_hash_pinned(all_results_1min):
    assert rte.determinism_hash(all_results_1min) == PINNED_DETERMINISM_HASH_1MIN, (
        "1-min-path determinism_hash drifted from the pinned iteration-3 baseline -- either "
        "the harness changed or an upstream input (recorded decision streams, params.json, "
        "key-levels.json, today's 1-min OPRA/SPY cache in backtest/data/highres/) did."
    )


def test_1min_resolution_counts_pinned(built_1min):
    _, resolution_counts = built_1min
    assert resolution_counts == PINNED_RESOLUTION_COUNTS_1MIN, (
        "Exit-layer resolution mix drifted -- expected all 12 recorded entries to resolve via "
        "the real 1-min OPRA/SPY cache with zero 5-min fallbacks. A change here means either a "
        "1-min cache file went missing (backtest/data/highres/) or a new entry appeared that "
        "isn't covered by fetch_today_1min.py's fixed 7-contract fetch list."
    )


@pytest.mark.parametrize("arm_key,expected_pnl", list(PINNED_TOTAL_PNL_1MIN.items()))
def test_1min_pinned_total_pnl_per_arm(all_results_1min, arm_key, expected_pnl):
    assert all_results_1min[arm_key]["total_pnl"] == pytest.approx(expected_pnl, abs=0.01)


def test_1min_faithfulness_verdict_pinned(all_results_1min):
    trades_today = rte.load_trades_csv_today()
    _, live_engine_only, _ = rte.compute_live_truth(trades_today)
    faithfulness = {k: rte.faithfulness_for(k, v["total_pnl"], live_engine_only.get(k, 0.0))
                     for k, v in all_results_1min.items()}
    n_faithful = sum(1 for f in faithfulness.values() if f["faithful"])
    all_faithful = all(f["faithful"] for f in faithfulness.values())
    assert n_faithful == PINNED_N_FAITHFUL_1MIN
    assert all_faithful == PINNED_ALL_FAITHFUL_1MIN, (
        "1-min-path faithfulness verdict flipped. If this now reads all_faithful=True, DO NOT "
        "treat that as ready-to-tune without re-running the fable-too-good hunt -- the module "
        "docstring documents WHY 1-min resolution zeroed out core_safe's real winners via the "
        "v15_profit_lock_mode='fixed' breakeven-floor artifact; a sudden green here would mean "
        "either that mechanism stopped firing (verify against params.json) or this test stopped "
        "exercising the real exit path."
    )


def test_1min_entry_fill_price_fidelity_improved(all_results_1min):
    """The one mechanism iteration 3 actually fixed: entry-fill-price deltas vs live's real fill
    must be small (<= $0.10) on every entry that has a live_entry_px to compare against -- was
    up to $0.23 (30%) at 5-min resolution (core_safe's 13:01 entry)."""
    n_checked = 0
    for res in all_results_1min.values():
        for t in res["trades"]:
            delta = t.get("entry_px_delta")
            if delta is None:
                continue
            n_checked += 1
            assert abs(delta) <= 0.10, (
                f"{res['arm']} {t['signal_ts_et']}: entry_px_delta={delta} exceeds the $0.10 "
                f"fidelity bar the 1-min entry-fill fix is supposed to hold."
            )
    assert n_checked == PINNED_N_ENTRIES, (
        f"expected all {PINNED_N_ENTRIES} recorded entries to carry a live_entry_px comparison; "
        f"only {n_checked} did."
    )


def test_1min_opra_cache_is_gapless_for_todays_contracts():
    """Verified precondition for treating the 1-min index-lockstep walk as exact rather than an
    approximation on top of an approximation (see module docstring ITERATION 3 section)."""
    spy_1m = rte.load_spy_1min_rth()
    assert spy_1m is not None, "1-min SPY cache missing -- run backtest/tools/fetch_today_1min.py"
    assert len(spy_1m) == 390, f"expected 390 RTH 1-min SPY bars, got {len(spy_1m)}"
    suffix = f"_1m_{rte.DATE_STR}.csv"
    contracts = list(rte.HIRES_DIR.glob(f"SPY{rte.TRADE_DATE.strftime('%y%m%d')}*{suffix}"))
    assert len(contracts) >= 6, "expected at least the 6 traded put/call contracts cached"
    for p in contracts:
        sym = p.name[: -len(suffix)]
        df = rte.load_opt_1min(sym)
        rth = df[(df["timestamp_et"].dt.time >= dt.time(9, 30)) & (df["timestamp_et"].dt.time < dt.time(16, 0))]
        assert len(rth) == 390, f"{sym}: expected 390 gapless RTH 1-min bars, got {len(rth)}"
