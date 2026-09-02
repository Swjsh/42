"""Companion guards for T-W8 HEADROOM + RETEST (backtest/tools/tw8_headroom_retest.py +
tw8_level_context.py). Three load-bearing invariants, per the task's pre-registration
discipline:

  1. The pre-registration file (analysis/recommendations/headroom-retest-preregistration.json)
     is frozen and its hash-checked fields match what the runner actually used at run time
     (hash check) -- a drift here means the study silently ran against a DIFFERENT candidate
     grid than the one that was pre-registered.
  2. C6 (look-ahead): a synthetic future level must NOT leak into the frozen level set or the
     headroom computed from it -- the same "plant a future value, assert invisible earlier"
     pattern backtest/tests/test_level_memory.py already uses for a different module.
  3. The null-comparison (H's random-skip baseline) is NON-VACUOUS: it is unit-tested in
     isolation AND verified to have actually run inside the real study output (not just a
     function that exists but was never exercised on 0<n_kept<n_total data).

Also covers R's misses-priced-in invariant (a real, checked cost -- not silently excluded)
and structural completeness of the verdict grid against the frozen candidate axes.

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_tw8_headroom_retest.py -q
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import tw8_level_context as lc          # noqa: E402
import tw8_headroom_retest as tw8       # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "headroom-retest-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "headroom-retest-tw8.json"


# ---------------------------------------------------------------------------------------------
# 1) PRE-REGISTRATION FROZEN FIELDS + HASH CHECK
# ---------------------------------------------------------------------------------------------
def test_preregistration_file_exists_and_is_frozen_v1():
    assert PREREG.exists(), f"pre-registration missing: {PREREG}"
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert preg["version"] == 1
    # A prereg's STATUS is a state machine that correct operation ADVANCES; its CONTENT is
    # what must never move. This line used to pin the status to FROZEN_PENDING_RUN, so the
    # guard went RED the moment the study was legitimately run and its verdict recorded --
    # exactly what a pre-registration exists to allow. Four of these fired together on
    # 2026-09-02 for that reason, having been run the night before.
    #
    # This is NOT a weakened assertion. It pins the legal state machine AND requires a
    # RUN_COMPLETE claim to be backed by an actual run record on the file, which the old
    # equality check never did. Immutability of the design itself is guarded -- properly --
    # by the sibling tests in this file that pin the sha256 population hashes and the
    # runner's frozen constants; those are the anti-repick teeth, not this line.
    status = str(preg["status"])
    assert status.startswith("FROZEN_") or status.startswith("RUN_COMPLETE"), (
        f"illegal prereg status {status!r} -- a prereg may sit FROZEN_* or advance to "
        f"RUN_COMPLETE, and nothing else (a draft/unfrozen status here means the "
        f"no-repick clause is not in force)"
    )
    if status.startswith("RUN_COMPLETE"):
        assert any(k.startswith("closed_") for k in preg), (
            f"status is {status!r} but the file carries no closed_* run record -- a "
            f"completed verdict must be evidenced on the prereg, not just asserted"
        )
    assert preg["hypothesis_provenance"]["excluded_from_all_windows"] is True


def test_preregistration_candidate_grid_matches_runner_constants():
    """Frozen thresholds/patience/null-trial-count/seed/small-n-gate in the pre-registration
    must match EXACTLY what the runner uses -- catches silent grid drift (a re-pick after
    seeing results would show up here as a mismatch)."""
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert preg["candidates"]["H"]["thresholds_usd"] == tw8.H_THRESHOLDS
    assert preg["candidates"]["R"]["patience_bars"] == tw8.R_PATIENCE
    assert preg["null_baseline"]["trials"] == tw8.NULL_TRIALS
    assert preg["null_baseline"]["seed"] == tw8.NULL_SEED
    assert preg["pass_bar"]["small_n_threshold"] == tw8.SMALL_N_THRESHOLD
    assert preg["exit_shapes"]["CONTROL"]["shape"] == tw8.CONTROL_SHAPE
    assert preg["exit_shapes"]["exit-A"]["shape"] == tw8.EXIT_A_SHAPE


def test_preregistration_hashes_match_runner_expected_constants():
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert preg["signal_set_integrity"]["exploratory"]["sha256_16"] == tw8.EXPECTED_EXPLORATORY_SHA16
    assert preg["signal_set_integrity"]["fresh"]["sha256_16"] == tw8.EXPECTED_FRESH_SHA16


def test_preflight_verifies_the_real_signal_sets_on_disk():
    """Runs the REAL preflight() -- reads the actual signal-set files, hashes them fresh -- and
    asserts they validate clean against the frozen pre-registration. Proves the runner performs
    a genuine check at run time, not a hardcoded pass."""
    pf = tw8.preflight()
    assert pf["exploratory_hash_ok"] is True, pf
    assert pf["fresh_hash_ok"] is True, pf
    assert pf["preregistration_version_ok"] is True, pf


def test_preflight_abort_condition_is_fail_closed():
    """main() aborts (return 1) if ANY hash/version check fails -- verify the boolean gate
    itself would trip on a corrupted preflight result (does not require corrupting real files)."""
    pf = tw8.preflight()
    assert pf["exploratory_hash_ok"] and pf["fresh_hash_ok"] and pf["preregistration_version_ok"]
    for bad_key in ("exploratory_hash_ok", "fresh_hash_ok", "preregistration_version_ok"):
        tampered = dict(pf)
        tampered[bad_key] = False
        would_abort = not (tampered["exploratory_hash_ok"] and tampered["fresh_hash_ok"]
                            and tampered["preregistration_version_ok"])
        assert would_abort is True, f"flipping {bad_key} to False must trip the abort gate"


def test_today_2026_07_09_excluded_from_both_signal_sets():
    """The hypothesis-generating day must not appear in either window (pre-registration's own
    disclosure)."""
    exp_data = tw8.sc.load_or_build_signals()
    exp_signals = exp_data["signals"] if isinstance(exp_data, dict) else exp_data
    fresh_data = tw8.t5.build_fresh_slice()
    for s in exp_signals + fresh_data["signals"]:
        assert dt.date.fromisoformat(s["date"]) != tw8.TODAY_EXCLUDED, (
            f"2026-07-09 leaked into a signal set: {s}")


# ---------------------------------------------------------------------------------------------
# 2) C6 LOOK-AHEAD GUARD -- synthetic future-level leak tests
# ---------------------------------------------------------------------------------------------
def _synthetic_spy(rows: list[dict]) -> pd.DataFrame:
    spy_full = pd.DataFrame(rows)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    spy_full["time"] = spy_full["timestamp_et"].dt.time
    return spy_full


def test_c6_frozen_level_set_does_not_see_a_future_spike():
    """A price spike planted AFTER the freeze bar (first bar >= 09:35 ET) must NOT appear in
    the frozen level set -- proves frozen_level_set_for_date only ever reads bars <= the freeze
    bar (the same invariant lib/orchestrator.py relies on, reproduced on synthetic data so this
    test has zero dependency on real market files)."""
    date = dt.date(2099, 3, 2)
    rows = [
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 30)), "open": 100.0, "high": 100.05,
         "low": 99.95, "close": 100.0, "volume": 1000},
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 35)), "open": 100.0, "high": 100.05,
         "low": 99.95, "close": 100.0, "volume": 1000},
        # LOOK-AHEAD bar: an obviously-detectable spike well after the freeze bar.
        {"timestamp_et": dt.datetime.combine(date, dt.time(14, 0)), "open": 100.0, "high": 9999.0,
         "low": 99.5, "close": 101.0, "volume": 5000},
    ]
    spy_full = _synthetic_spy(rows)
    level_set = lc.frozen_level_set_for_date(spy_full, date, {})
    assert level_set is not None
    assert 9999.0 not in level_set.active, (
        f"future spike leaked into the frozen level set (C6 violation): {level_set.active}")
    assert all(lv < 1000 for lv in level_set.active), (
        f"an implausibly large (look-ahead-tainted) level leaked: {level_set.active}")


def test_c6_headroom_ignores_a_future_opposing_level():
    """End-to-end via enrich_signal: a synthetic BULL signal must compute headroom from ONLY
    pre-signal structure. A future spike that would obviously become 'the next resistance
    above' must never appear as next_opposing_level."""
    date = dt.date(2099, 3, 3)
    rows = []
    t = dt.datetime.combine(date, dt.time(9, 30))
    price = 100.0
    for _ in range(3):
        rows.append({"timestamp_et": t, "open": price, "high": price + 0.10, "low": price - 0.10,
                     "close": price, "volume": 1000})
        t += dt.timedelta(minutes=5)
        price += 0.05
    trigger_time = t
    entry_spot = price
    rows.append({"timestamp_et": trigger_time, "open": price - 0.05, "high": price + 0.02,
                 "low": price - 0.15, "close": entry_spot, "volume": 1200})
    # future spike -- must not be visible to the frozen level set or headroom calc.
    spike_time = dt.datetime.combine(date, dt.time(14, 0))
    rows.append({"timestamp_et": spike_time, "open": 100.0, "high": 9999.0, "low": 99.5,
                 "close": 101.0, "volume": 5000})
    spy_full = _synthetic_spy(rows)

    sig = {"date": str(date), "entry_ts": (trigger_time + dt.timedelta(minutes=5)).isoformat(),
           "side": "C", "entry_spot": entry_spot, "direction": "bull",
           "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON"}
    enriched = lc.enrich_signal(sig, spy_full, {})
    assert enriched["next_opposing_level"] != 9999.0
    if enriched["next_opposing_level"] is not None:
        assert enriched["next_opposing_level"] < 200
    assert enriched["headroom_dollars"] is None or enriched["headroom_dollars"] < 200


# ---------------------------------------------------------------------------------------------
# 3) NULL-COMPARISON NON-VACUOUS
# ---------------------------------------------------------------------------------------------
def test_null_distribution_unit_edge_cases():
    assert tw8.null_distribution([1.0, 2.0, 3.0], k=0, n_trials=10, seed=1) is None
    assert tw8.null_distribution([1.0, 2.0, 3.0], k=5, n_trials=10, seed=1) is None   # k > n


def test_null_distribution_is_genuinely_sampled_not_a_stub():
    pool = [float(i) for i in range(-50, 51)]      # -50..50, real spread, mean 0
    d1 = tw8.null_distribution(pool, k=10, n_trials=500, seed=1)
    d2 = tw8.null_distribution(pool, k=10, n_trials=500, seed=2)
    assert d1 is not None and d2 is not None
    assert d1["n_trials"] == 500 and d1["k"] == 10
    assert d1["stdev"] > 0, "zero variance across 500 trials means sampling isn't actually happening"
    assert d1["mean_of_means"] != d2["mean_of_means"] or d1["min"] != d2["min"], (
        "two different seeds produced an identical distribution -- looks like a stub, not real sampling")


def test_output_file_null_comparison_actually_ran():
    """Reads the ALREADY-GENERATED headroom-retest-tw8.json (run tw8_headroom_retest.py first)
    and asserts the null comparison is a real, non-trivial computation in the actual study
    output -- not merely unit-testable in isolation."""
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/tw8_headroom_retest.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    found_real_null = False
    for window_name in ("exploratory", "fresh"):
        h = out["windows"][window_name]["candidate_H"]
        for threshold, exits in h.items():
            for exit_name, cell in exits.items():
                if 0 < cell["n_kept"] < cell["n_total"]:
                    null = cell["null_random_skip"]
                    assert null is not None, (
                        f"{window_name}/{threshold}/{exit_name}: null missing despite 0<n_kept<n_total")
                    assert null["n_trials"] == tw8.NULL_TRIALS
                    assert isinstance(null["mean_of_means"], (int, float))
                    found_real_null = True
    assert found_real_null, "no H cell exercised the null path in the real output -- non-vacuous check failed"


# ---------------------------------------------------------------------------------------------
# R: misses priced in (not excluded) + verdict-grid completeness
# ---------------------------------------------------------------------------------------------
def test_output_file_r_misses_are_priced_in_not_excluded():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/tw8_headroom_retest.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    found_real_miss = False
    for window_name in ("exploratory", "fresh"):
        r = out["windows"][window_name]["candidate_R"]
        for patience, exits in r.items():
            for exit_name, cell in exits.items():
                assert cell["n_eligible"] == cell["n_filled"] + cell["n_missed"]
                if cell["n_missed"] > 0:
                    found_real_miss = True
                    if cell["n_filled"] > 0:
                        assert cell["expectancy_incl_misses"] != cell["expectancy_filled_only"], (
                            f"{window_name}/{patience}/{exit_name}: incl-misses == filled-only "
                            "despite n_missed>0 -- misses look excluded, not priced at $0")
    assert found_real_miss, "no R cell produced a real miss in the real output -- misses-priced-in check is vacuous"


def test_output_verdict_grid_matches_frozen_candidate_grid():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/tw8_headroom_retest.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    v = out["verdicts"]
    assert set(v["H"].keys()) == {str(t) for t in tw8.H_THRESHOLDS}
    for exits in v["H"].values():
        assert set(exits.keys()) == set(tw8.EXIT_SHAPES.keys())
        for cell in exits.values():
            assert cell["overall"] in ("PASS", "FAIL", "INCONCLUSIVE_SMALL_N")
    assert set(v["R"].keys()) == {str(p) for p in tw8.R_PATIENCE}
    for exits in v["R"].values():
        assert set(exits.keys()) == set(tw8.EXIT_SHAPES.keys())
        for cell in exits.values():
            assert cell["overall"] in ("PASS", "FAIL", "INCONCLUSIVE_SMALL_N")


# ---------------------------------------------------------------------------------------------
# 4) REAL-DATA MINI INTEGRATION (fresh window only -- cheap: ~18 signals, local cache, $0)
# ---------------------------------------------------------------------------------------------
def test_fresh_window_pipeline_runs_end_to_end_on_real_data():
    fresh_data = tw8.t5.build_fresh_slice()
    result = tw8.run_window("fresh_pytest_check", fresh_data["signals"],
                             tw8.FRESH_START_WARMUP, tw8.FRESH_END)
    assert result["n_prepared"] == fresh_data["n"]
    assert result["control_all"]["n"] == result["n_prepared"]
    for threshold in tw8.H_THRESHOLDS:
        for exit_name in tw8.EXIT_SHAPES:
            cell = result["candidate_H"][str(threshold)][exit_name]
            assert cell["n_kept"] + cell["n_skipped"] == result["n_prepared"]
    for patience in tw8.R_PATIENCE:
        for exit_name in tw8.EXIT_SHAPES:
            cell = result["candidate_R"][str(patience)][exit_name]
            assert cell["n_eligible"] == result["n_eligible_for_r"]
            assert cell["n_eligible"] == cell["n_filled"] + cell["n_missed"]
