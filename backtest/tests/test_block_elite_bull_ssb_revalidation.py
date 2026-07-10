"""Guards for the block_elite_bull SS-B revalidation (RELAUNCH of the 2026-07-09 PC-reboot-killed
study). Pins THREE things per the mission's TESTS requirement:

  1. prereg hash pin -- the frozen pre-registration cannot be silently edited after freezing
     without this test REDing.
  2. old-exit parity check actually BITES -- a non-vacuous test that the tolerance function
     rejects a genuinely-diverged number, not just accepts everything.
  3. dedupe rule -- the event-grouping logic (gap threshold + representative-row selection)
     is pinned against synthetic fixtures so a future edit can't silently change what counts
     as "one signal" without a test noticing.

Fast + deterministic: no network calls, no full backtest re-run (those are exercised by running
the module's main() directly, not by this guard suite).
"""
import json
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backtest"))
sys.path.insert(0, os.path.join(REPO, "backtest", "tools"))
sys.path.insert(0, os.path.join(REPO, "automation", "state", "fleet"))

import block_elite_bull_ssb_revalidation as m  # noqa: E402

PREREG = os.path.join(REPO, "analysis", "recommendations",
                      "block-elite-bull-ssb-preregistration.json")
RESULT = os.path.join(REPO, "analysis", "recommendations",
                      "block-elite-bull-ssb-revalidation.json")


# ---- 1. prereg hash pin ------------------------------------------------------

def test_prereg_file_exists_and_is_frozen():
    assert os.path.exists(PREREG)
    preg = json.load(open(PREREG, encoding="utf-8"))
    assert preg["status"] == "FROZEN_PENDING_RUN"
    assert preg["version"] == 1


def test_prereg_hash_matches_hardcoded_expectation():
    """The hash baked into the runner must match what's actually on disk right now. If someone
    edits the preregistration (cohort def, dedupe rule, pass bar...) after freezing, THIS test
    REDs -- it does not silently re-hash and move on."""
    pf = m.preflight()
    assert pf["prereg_hash_ok"] is True
    assert pf["prereg_sha256_16_recomputed"] == m.EXPECTED_PREREG_SHA16
    assert pf["prereg_sha256_16_stored"] == m.EXPECTED_PREREG_SHA16


def test_prereg_hash_bites_on_mutation(tmp_path):
    """Non-vacuous: prove the hash check actually detects a change, not just that it happens
    to match today. Mutate a copy's pass-bar n-floor and confirm the recomputed hash diverges
    from the frozen expectation."""
    preg = json.load(open(PREREG, encoding="utf-8"))
    mutated = dict(preg)
    mutated["pass_bar"] = dict(mutated["pass_bar"])
    mutated["pass_bar"]["conditions"] = list(mutated["pass_bar"]["conditions"]) + ["5. EXTRA"]
    mutated_no_hash = {k: v for k, v in mutated.items() if k != "content_sha256_16"}
    mutated_hash = m._content_hash(mutated_no_hash)
    assert mutated_hash != m.EXPECTED_PREREG_SHA16, \
        "hash check is vacuous -- a mutated preregistration must NOT hash-match the frozen spec"


# ---- 2. old-exit parity check bites ------------------------------------------

def test_parity_accepts_within_tolerance():
    assert m.parity_within_tolerance(-241.26, expected=-241.26) is True
    assert m.parity_within_tolerance(-240.30, expected=-241.26) is True  # $0.96 off, under $1.00


def test_parity_rejects_beyond_tolerance():
    """Non-vacuous: a genuinely diverged re-run (params drift, engine change) must FAIL the
    parity check, not be waved through."""
    assert m.parity_within_tolerance(-241.26 + 1.50, expected=-241.26) is False
    assert m.parity_within_tolerance(0.0, expected=-241.26) is False
    assert m.parity_within_tolerance(-241.26 * -1, expected=-241.26) is False  # sign flip


# ---- 3. dedupe rule -----------------------------------------------------------

def _row(ts, **kw):
    base = {"ts_et": ts, "account": "safe", "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM",
            "spy": 750.0, "triggers": ["level_reclaim", "confluence"], "trigger_level_exact": None}
    base.update(kw)
    return base


def test_dedupe_merges_within_gap():
    rows = [_row("2026-07-01T09:41:00"), _row("2026-07-01T09:42:00"), _row("2026-07-01T09:45:00")]
    events = m.dedupe_into_events(rows, gap_minutes=5)
    assert len(events) == 1
    assert events[0]["n_ticks"] == 3
    assert events[0]["first_ts"] == "2026-07-01T09:41:00"


def test_dedupe_splits_beyond_gap():
    rows = [_row("2026-07-01T09:41:00"), _row("2026-07-01T09:47:00")]  # 6 min gap > 5
    events = m.dedupe_into_events(rows, gap_minutes=5)
    assert len(events) == 2


def test_dedupe_boundary_is_inclusive():
    """Exactly gap_minutes apart must still merge (<=, not <)."""
    rows = [_row("2026-07-01T09:41:00"), _row("2026-07-01T09:46:00")]  # exactly 5 min
    events = m.dedupe_into_events(rows, gap_minutes=5)
    assert len(events) == 1


def test_dedupe_empty_and_single():
    assert m.dedupe_into_events([]) == []
    single = m.dedupe_into_events([_row("2026-07-01T09:41:00")])
    assert len(single) == 1 and single[0]["n_ticks"] == 1


def test_dedupe_unsorted_input_still_orders_correctly():
    rows = [_row("2026-07-01T10:00:00"), _row("2026-07-01T09:41:00"), _row("2026-07-01T09:42:00")]
    events = m.dedupe_into_events(rows, gap_minutes=5)
    assert len(events) == 2
    assert events[0]["first_ts"] == "2026-07-01T09:41:00"
    assert events[1]["first_ts"] == "2026-07-01T10:00:00"


# ---- stale-echo cross-account corroboration ----------------------------------

def test_stale_echo_detected_via_cross_account():
    entry = _row("2026-07-10T09:31:04", account="bold")
    other = [{"ts_et": "2026-07-10T09:31:03", "account": "safe", "action": "SKIP_STALE_TRIGGER"}]
    stale, reason = m.is_possible_stale_echo(entry, other)
    assert stale is True
    assert "SKIP_STALE_TRIGGER" in reason


def test_stale_echo_not_flagged_without_corroboration():
    entry = _row("2026-07-10T09:31:04", account="bold")
    other = [{"ts_et": "2026-07-10T09:31:03", "account": "safe", "action": "HOLD"}]
    stale, _ = m.is_possible_stale_echo(entry, other)
    assert stale is False


def test_stale_echo_outside_90s_window_not_flagged():
    entry = _row("2026-07-10T09:31:04")
    other = [{"ts_et": "2026-07-10T09:35:00", "account": "safe", "action": "SKIP_STALE_TRIGGER"}]
    stale, _ = m.is_possible_stale_echo(entry, other)
    assert stale is False


# ---- strike / drop-top1 pure helpers ------------------------------------------

def test_strike_for_call_matches_simulator_real_convention():
    # simulator_real.py:376: strike = atm + strike_offset (offset=-2 -> ITM by $2 for calls)
    assert m.strike_for_call(751.19, strike_offset=-2) == 749
    assert m.strike_for_call(751.55, strike_offset=-2) == 750  # round(751.55)=752 -> 750


def test_drop_top1_removes_single_largest_winner():
    remainder, positive = m.drop_top1([100.0, -30.0, -20.0, 5.0])
    assert remainder == pytest.approx(-45.0)
    assert positive is False


def test_drop_top1_no_winners_keeps_total():
    remainder, positive = m.drop_top1([-10.0, -20.0])
    assert remainder == pytest.approx(-30.0)
    assert positive is False


def test_drop_top1_empty():
    assert m.drop_top1([]) == (0.0, False)


def test_is_super_tier():
    assert m._is_super_tier({"triggers": ["level_reclaim", "ribbon_flip", "confluence"]}) is True
    assert m._is_super_tier({"triggers": ["a", "b", "c"]}) is True  # 3+ triggers
    assert m._is_super_tier({"triggers": ["level_reclaim", "confluence"]}) is False  # ELITE, not SUPER


# ---- golden finding (once committed) ------------------------------------------

@pytest.mark.skipif(not os.path.exists(RESULT), reason="revalidation result not yet committed")
def test_committed_revalidation_verdict():
    r = json.load(open(RESULT, encoding="utf-8"))
    pb = r["pass_bar"]
    # non-vacuous: verdict must be the AND of all 4 conditions, not an independent field that
    # could drift from them.
    expected_all_pass = (pb["condition_1_ssb_total_positive"] and pb["condition_2_ssb_drop_top1_positive"]
                         and pb["condition_3_old_exit_parity"] and pb["condition_4_n_events_floor_12"])
    assert pb["all_pass"] == expected_all_pass
    assert pb["verdict"] == ("UNBLOCK_PROPOSE" if expected_all_pass else "KEEP")
    # n_events_floor is only meaningful if the mining actually ran (n>0)
    assert r["elite_cohort"]["n_events_total"] > 0
