"""Guards for backtest/tools/participation_cascade.py -- the joint gate-cascade
funnel (C15) built 2026-07-10 after J's "6 arms and nothing took a trade from
over 700 signals... why didn't you see this yesterday?" on a $0 day / $7 trend.

Fixtures under fixtures/participation-cascade-2026-07-0{9,10}/ are FULL,
UNMODIFIED real ledger rows for those two sessions (core-decisions.jsonl +
all 4 fleet arms' decisions.jsonl + the real RTH 5m SPY bars) -- mirrors
test_fill_funnel_guard.py's "TODAY'S REAL ROWS" fixture philosophy. The dedup
rule depends on real chronological adjacency, so these are NOT down-sampled:
dropping a "boring" HOLD row between two distinct bursts would silently merge
them into one event and corrupt the exact counts this suite pins.

  2026-07-09 = the "engine participated" shape: 10 real fleet orders.
  2026-07-10 = the PARTICIPATION_HOLE shape: 31 passed-scoring events, 0
               orders, on a real 0.973%-range trend day.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_participation_cascade.py -q
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIX = Path(HERE) / "fixtures"


def _load(name: str, relpath: str):
    path = os.path.join(ROOT, *relpath.split("/"), f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = _load("participation_cascade", "backtest/tools")


# ---------------------------------------------------------------------------
# CORE row classification -- one case per real skip/verdict string catalogued
# from automation/state/core-decisions.jsonl
# ---------------------------------------------------------------------------

class TestClassifyCoreRow:
    def test_no_data_engine_error(self):
        r = {"verdict": "ERROR", "error": "can't subtract offset-naive and offset-aware datetimes"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "NO_DATA"
        assert c["category"] == pc.CAT_NONE

    def test_no_data_bad_input(self):
        r = {"verdict": "SKIP_BAD_INPUT", "reason": None}
        c = pc.classify_core_row(r)
        assert c["stage"] == "NO_DATA"

    def test_no_signal_is_the_modal_hold(self):
        r = {"verdict": "HOLD", "reason": "no setup passed scoring (neither bear nor bull)"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "NO_SIGNAL"
        assert c["category"] == pc.CAT_NONE
        assert c["side"] is None and c["setup"] is None

    def test_structure_veto(self):
        r = {"verdict": "SKIP_STRUCTURE_VETO", "side": "C", "setup": None,
             "reason": "structure-veto: C entry blocked -- price structure is 'downtrend' (wrong-way entry)"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "STRUCTURE_VETO"
        assert c["category"] == pc.CAT_VETO

    def test_gate_block_elite_bull_is_a_tier_cohort_gate(self):
        r = {"verdict": "SKIP_ELITE_BULL_LEVEL_RECLAIM", "side": "C", "setup": None,
             "reason": "blocked by entry gate block_elite_bull"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "GATE_BLOCK"
        assert c["category"] == pc.CAT_GATE
        assert c["blocker"] == "block_elite_bull"
        assert c["blocker"] in pc.TIER_COHORT_GATES

    def test_window_block_named_hour_range(self):
        r = {"verdict": "SKIP_BULL_1100_1200", "side": "C", "setup": None,
             "reason": "blocked by entry gate block_bull_1100_1200"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "WINDOW_BLOCK"
        assert c["category"] == pc.CAT_WINDOW
        assert c["blocker"] == "block_bull_1100_1200"

    def test_window_block_afternoon_gate(self):
        r = {"verdict": "SKIP_CONF_LVL_REC_AFTERNOON", "side": "C", "setup": None,
             "reason": "blocked by entry gate block_conf_lvl_rec_afternoon"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "WINDOW_BLOCK"
        assert c["blocker"] == "block_conf_lvl_rec_afternoon"

    def test_non_window_named_gate_stays_plain_gate(self):
        r = {"verdict": "SKIP_DOJI_ENTRY_BAR", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
             "reason": "blocked by entry gate entry_bar_body_pct_min"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "GATE_BLOCK"
        assert c["category"] == pc.CAT_GATE
        assert c["blocker"] == "entry_bar_body_pct_min"
        assert c["blocker"] not in pc.TIER_COHORT_GATES

    def test_enter_then_skip_late_entry_is_a_window_block_with_tier(self):
        r = {"verdict": "ENTER_BULL", "action": "SKIP_LATE_ENTRY", "side": "C",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "WINDOW_BLOCK"
        assert c["tier"] == "SUPER"

    def test_enter_then_skip_stale_trigger(self):
        r = {"verdict": "ENTER_BULL", "action": "SKIP_STALE_TRIGGER", "side": "C",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)",
             "trigger_bar_et": "2026-07-09T15:55:00-04:00"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "STALE_TRIGGER"
        assert c["category"] == pc.CAT_EXEC

    def test_enter_then_skip_min_premium_floor_is_risk_gate_not_execution(self):
        r = {"verdict": "ENTER_BULL", "action": "SKIP_MIN_PREMIUM_FLOOR", "side": "C",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)",
             "exec": {"status": "SKIP_MIN_PREMIUM_FLOOR", "symbol": "SPY260710C00756000",
                      "premium": 0.11, "min_entry_premium": 0.3}}
        c = pc.classify_core_row(r)
        assert c["stage"] == "RISK_GATE_DENY"
        assert c["category"] == pc.CAT_RISK
        assert c["blocker"] == "min_premium_floor"

    def test_enter_then_risk_deny_pdt(self):
        r = {"verdict": "ENTER_BEAR", "action": "RISK_DENY_PDT", "side": "P",
             "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
             "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "RISK_GATE_DENY"
        assert c["blocker"] == "risk_deny_pdt"

    def test_enter_then_not_flat_is_risk_gate(self):
        r = {"verdict": "ENTER_BULL", "action": "NOT_FLAT", "side": "C",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "reason": "..."}
        c = pc.classify_core_row(r)
        assert c["stage"] == "RISK_GATE_DENY"
        assert c["blocker"] == "not_flat_rule4"

    def test_enter_then_place_fail(self):
        r = {"verdict": "ENTER_BEAR", "action": "PLACE_FAIL", "side": "P",
             "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
             "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)",
             "exec": {"status": "PLACE_FAIL", "symbol": "SPY_TEST_P",
                      "broker": {"_error": "HTTP Error 403"}}}
        c = pc.classify_core_row(r)
        assert c["stage"] == "PLACE_FAIL"
        assert c["category"] == pc.CAT_EXEC

    def test_enter_then_placed(self):
        r = {"verdict": "ENTER_BEAR", "action": "ENTER_BEAR", "side": "P",
             "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
             "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)",
             "exec": {"status": "PLACED", "symbol": "SPY_TEST", "broker": {"id": "abc123", "filled_qty": "0"}}}
        c = pc.classify_core_row(r)
        assert c["stage"] == "PLACED"
        assert c["category"] == pc.CAT_SUCCESS

    def test_unrecognized_action_fails_open_not_silent(self):
        """OP-33: a brand-new/unrecognized downstream code must still be
        COUNTED and VISIBLE (OTHER_BLOCK), never silently dropped."""
        r = {"verdict": "ENTER_BULL", "action": "SKIP_SOME_BRAND_NEW_GATE_2027", "side": "C",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)"}
        c = pc.classify_core_row(r)
        assert c["stage"] == "OTHER_BLOCK"
        assert "skip_some_brand_new_gate_2027" in c["blocker"]


# ---------------------------------------------------------------------------
# FLEET row classification -- one case per real skip/reason/risk_code string
# catalogued from automation/state/fleet/<arm>/decisions.jsonl
# ---------------------------------------------------------------------------

class TestClassifyFleetRow:
    def test_no_signal(self):
        r = {"action": "HOLD", "side": None, "setup_name": None, "risk_code": None,
             "reason": "no qualifying setup (no strategy fired)"}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "NO_SIGNAL"

    def test_no_data_stale_signal_feed(self):
        r = {"action": "HOLD", "signal_status": "signal_stale_1452s", "reason": "no live signal"}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "NO_DATA"

    def test_risk_gate_min_premium_floor(self):
        r = {"action": "HOLD", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "quality": "ELITE", "risk_code": "SKIP_MIN_PREMIUM_FLOOR",
             "reason": "premium 0.29 < min_entry_premium floor 0.3"}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "RISK_GATE_DENY"
        assert c["blocker"] == "min_premium_floor"
        assert c["tier"] == "ELITE"

    def test_risk_gate_not_flat_rule4(self):
        r = {"action": "HOLD", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "quality": "ELITE", "risk_code": "NOT_FLAT",
             "reason": ("risk_gate denied: PA3DHPT7KIQE: position already open (status='open') "
                       "-- flatten before a new entry (Rule 4: no adding without a new trigger)")}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "RISK_GATE_DENY"
        assert c["blocker"] == "not_flat_rule4"

    def test_risk_gate_unreadable_input_is_no_data(self):
        r = {"action": "HOLD", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "quality": "BASE", "risk_code": "UNREADABLE_INPUT", "reason": "unreadable input"}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "NO_DATA"

    def test_gate_block_arm_selectivity(self):
        r = {"action": "HOLD", "side": "P", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
             "quality": None, "risk_code": None, "reason": "A+ gate: requires confluence/sequence (not EXCELLENT)"}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "GATE_BLOCK"
        assert c["blocker"] == "arm_selectivity_gate"

    def test_gate_block_direction_lock(self):
        r = {"action": "HOLD", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "quality": None, "risk_code": None, "reason": "direction_lock=PUT_ONLY skips a CALL signal"}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "GATE_BLOCK"
        assert c["blocker"] == "direction_lock"

    def test_window_block_early_entry_uses_placement_reason_directly(self):
        r = {"action": "ENTER_BULL", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "quality": "ELITE", "risk_code": "ALLOW", "reason": "ribbon_ride C (ELITE)",
             "placement": {"mode": "LIVE", "placed": False, "reason": "SKIP_EARLY_ENTRY",
                          "entry_floor_et": "09:35"}}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "WINDOW_BLOCK"
        assert c["blocker"] == "entry_floor_09:35"

    def test_placed(self):
        r = {"action": "ENTER_BULL", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "quality": "ELITE", "risk_code": "ALLOW", "reason": "ribbon_ride C (ELITE)",
             "placement": {"mode": "LIVE", "placed": True, "symbol": "SPY260709C00751000",
                          "broker": {"id": "xyz", "filled_qty": "0"}}}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "PLACED"

    def test_place_fail_uses_placement_reason_not_a_synthesized_fallback(self):
        """The exact gap fill_funnel.py has (verified 2026-07-10 real tape): a
        fleet PLACE_FAIL row has no `broker` sub-dict to read a rejection text
        from, so a naive fallback mislabels it "no broker response recorded"
        even when placement.reason names the real cause (e.g. SKIP_EARLY_ENTRY
        was misread that way upstream). This module must read placement.reason
        directly instead of synthesizing a generic broker-layer excuse."""
        r = {"action": "ENTER_BULL", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "quality": "ELITE", "risk_code": "ALLOW", "reason": "ribbon_ride C (ELITE)",
             "placement": {"mode": "LIVE", "placed": False, "reason": "some_new_broker_code"}}
        c = pc.classify_fleet_row(r)
        assert c["stage"] == "PLACE_FAIL"
        assert c["detail"] == "some_new_broker_code"


# ---------------------------------------------------------------------------
# dedup rule
# ---------------------------------------------------------------------------

def _enter_row(ts: str, action: str = "SKIP_MIN_PREMIUM_FLOOR") -> dict:
    return {"ts_et": ts, "verdict": "ENTER_BULL", "action": action, "side": "C",
            "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
            "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)",
            "exec": {"status": action}}


def _hold_row(ts: str) -> dict:
    return {"ts_et": ts, "verdict": "HOLD", "reason": "no setup passed scoring (neither bear nor bull)"}


class TestDedup:
    def test_collapses_consecutive_identical_ticks_into_one_event(self):
        rows = [_enter_row(f"2026-07-10T09:3{i}:00", "SKIP_STALE_TRIGGER") for i in range(1, 6)]
        events = pc.build_events(rows, "safe-2", "core")
        assert len(events) == 1
        assert events[0]["n_ticks"] == 5
        assert events[0]["ts_start"] == "2026-07-10T09:31:00"
        assert events[0]["ts_end"] == "2026-07-10T09:35:00"
        assert events[0]["stage"] == "STALE_TRIGGER"

    def test_hold_between_two_identical_bursts_yields_two_events(self):
        """Real shape from core-decisions.jsonl 2026-07-10 (account=bold):
        3 ENTER_BULL/SKIP_MIN_PREMIUM_FLOOR ticks (11:21-11:23), several HOLD
        ticks, then 3 more (11:31-11:33) -- two distinct re-tests of the same
        level, not one continuous signal. See module docstring dedup rule."""
        rows = ([_enter_row(f"2026-07-10T11:2{i}:00") for i in (1, 2, 3)]
                + [_hold_row(f"2026-07-10T11:2{i}:00") for i in (4, 5, 6, 7, 8, 9)]
                + [_enter_row(f"2026-07-10T11:3{i}:00") for i in (1, 2, 3)])
        events = pc.build_events(rows, "bold-2", "core")
        blocking = [e for e in events if e["stage"] == "RISK_GATE_DENY"]
        assert len(blocking) == 2, f"expected two distinct re-tests, got {len(blocking)}: {blocking}"
        assert blocking[0]["n_ticks"] == 3
        assert blocking[1]["n_ticks"] == 3
        no_signal = [e for e in events if e["stage"] == "NO_SIGNAL"]
        assert len(no_signal) == 1 and no_signal[0]["n_ticks"] == 6

    def test_placed_promoted_to_filled_by_same_day_exit_pass_evidence(self):
        rows = [
            {"ts_et": "2026-07-09T09:43:02", "verdict": "ENTER_BULL", "action": "ENTER_BULL", "side": "C",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
             "exec": {"status": "PLACED", "symbol": "SPY_TEST_C1", "broker": {"id": "o1", "filled_qty": "0"}}},
            {"ts_et": "2026-07-09T09:44:02", "verdict": "HOLD",
             "reason": "no setup passed scoring (neither bear nor bull)",
             "exit_pass": [{"symbol": "SPY_TEST_C1", "open_qty": 3}]},
        ]
        events = pc.build_events(rows, "safe-2", "core")
        placed_or_filled = [e for e in events if e["stage"] in ("PLACED", "FILLED")]
        assert len(placed_or_filled) == 1
        assert placed_or_filled[0]["stage"] == "FILLED"

    def test_placed_without_fill_evidence_stays_placed(self):
        rows = [
            {"ts_et": "2026-07-09T09:43:02", "verdict": "ENTER_BULL", "action": "ENTER_BULL", "side": "C",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
             "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
             "exec": {"status": "PLACED", "symbol": "SPY_TEST_C2", "broker": {"id": "o2", "filled_qty": "0"}}},
        ]
        events = pc.build_events(rows, "safe-2", "core")
        assert events[0]["stage"] == "PLACED"


# ---------------------------------------------------------------------------
# evaluate_day -- the PARTICIPATION_HOLE predicate, in isolation
# ---------------------------------------------------------------------------

class TestEvaluateDay:
    def test_idle_when_nothing_passed_scoring(self):
        verdict, _ = pc.evaluate_day(0, 0, 1.5)
        assert verdict == "IDLE"

    def test_ok_when_any_order_placed(self):
        verdict, _ = pc.evaluate_day(10, 1, 1.5)
        assert verdict == "OK"

    def test_low_participation_below_event_floor(self):
        verdict, _ = pc.evaluate_day(pc._MIN_PASSED_SCORING_FOR_HOLE - 1, 0, 1.5)
        assert verdict == "LOW_PARTICIPATION"

    def test_range_unknown_suppresses_the_headline_alert_but_stays_visible(self):
        verdict, flags = pc.evaluate_day(5, 0, None)
        assert verdict == "LOW_PARTICIPATION_RANGE_UNKNOWN"
        assert flags  # never silent (OP-33)

    def test_below_range_threshold_is_not_a_hole(self):
        verdict, _ = pc.evaluate_day(5, 0, pc._SPY_RANGE_PCT_THRESHOLD - 0.1)
        assert verdict == "LOW_PARTICIPATION"

    def test_hole_fires_at_the_exact_threshold(self):
        verdict, _ = pc.evaluate_day(pc._MIN_PASSED_SCORING_FOR_HOLE, 0, pc._SPY_RANGE_PCT_THRESHOLD)
        assert verdict == "PARTICIPATION_HOLE"


# ---------------------------------------------------------------------------
# end-to-end on the real 2026-07-09 / 2026-07-10 tape
# ---------------------------------------------------------------------------

class TestParticipationHoleOnRealTape:
    def _compute(self, day: str) -> dict:
        d = FIX / f"participation-cascade-{day}"
        return pc.compute_cascade_day(day, core_glob_dir=d, fleet_dir=d / "fleet", data_dir=d)

    def test_2026_07_10_fires_participation_hole(self):
        f = self._compute("2026-07-10")
        assert f["verdict"] == "PARTICIPATION_HOLE"
        assert f["n_orders"] == 0
        assert f["n_passed_scoring_events"] >= pc._MIN_PASSED_SCORING_FOR_HOLE
        assert f["spy_range_pct"] is not None
        assert f["spy_range_pct"] >= pc._SPY_RANGE_PCT_THRESHOLD

    def test_2026_07_09_does_not_fire_participation_hole(self):
        f = self._compute("2026-07-09")
        assert f["verdict"] != "PARTICIPATION_HOLE"
        assert f["n_orders"] == 10, f"07-09 real fleet participation was 10 orders, got {f['n_orders']}"
        assert f["joint_participation_pct"] and f["joint_participation_pct"] > 0

    def test_2026_07_10_leaderboard_is_pinned_to_the_real_tape(self):
        """If the funnel math regresses, this fails against the real tape
        (mirrors test_fill_funnel_guard.py's pinning philosophy)."""
        f = self._compute("2026-07-10")
        assert f["n_passed_scoring_events"] == 31
        assert f["n_orders"] == 0
        blockers = {b["blocker"]: b["n_arm_events"] for b in f["top_blockers"]}
        assert blockers["min_premium_floor"] == 18
        assert blockers["block_elite_bull"] == 4
        assert blockers["entry_floor_09:35"] == 4
        assert blockers["block_bull_1100_1200"] == 2

    def test_2026_07_10_honesty_check_real_leader_vs_j_hypothesis(self):
        """J's stated expectation (WHY section) named block_elite_bull + tier +
        ribbon_flip-cohort + window gates as the leaders. Reality (see
        block_bull_ribbon_flip absent from both params.json GATE_KEYS pass-
        throughs -- the cohort gate is not even wired active): the true #1
        killer is the risk gate's min-premium floor, block_elite_bull is #2,
        and no ribbon_flip-cohort block fires at all. This test pins that
        honest finding so a future edit can't quietly revert to confirming
        the hypothesis instead of the data (OP-33 / no-oversell)."""
        f = self._compute("2026-07-10")
        top = f["top_blockers"][0]
        assert top["blocker"] == "min_premium_floor"
        assert top["category"] == "risk_gate"
        names = {b["blocker"] for b in f["top_blockers"]}
        assert "block_bull_ribbon_flip" not in names, (
            "ribbon_flip-cohort gate fired -- either params.json wired it active "
            "(re-verify TIER_COHORT_GATES/leaderboard) or this is a genuine surprise, not a regression assumption")


# ---------------------------------------------------------------------------
# artifact writers (tmp_path only -- never touches the real state file)
# ---------------------------------------------------------------------------

class TestArtifactWriters:
    def test_write_state_file_round_trips(self, tmp_path):
        import json as _json
        d = FIX / "participation-cascade-2026-07-10"
        f = pc.compute_cascade_day("2026-07-10", core_glob_dir=d, fleet_dir=d / "fleet", data_dir=d)
        p = pc.write_state_file([f], state_dir=tmp_path)
        assert p is not None and p.exists()
        payload = _json.loads(p.read_text(encoding="utf-8"))
        assert payload["date"] == "2026-07-10"
        assert payload["verdict"] == "PARTICIPATION_HOLE"
        assert "events" not in payload, "full per-tick events must be dropped from the compact state file"
        assert len(payload["sessions"]) == 1

    def test_write_report_produces_nonempty_markdown(self, tmp_path):
        d9 = FIX / "participation-cascade-2026-07-09"
        d10 = FIX / "participation-cascade-2026-07-10"
        f9 = pc.compute_cascade_day("2026-07-09", core_glob_dir=d9, fleet_dir=d9 / "fleet", data_dir=d9)
        f10 = pc.compute_cascade_day("2026-07-10", core_glob_dir=d10, fleet_dir=d10 / "fleet", data_dir=d10)
        out = tmp_path / "report.md"
        p = pc.write_report([f9, f10], report_path=out, spotlight=("2026-07-10",))
        assert p == out and p.exists()
        text = p.read_text(encoding="utf-8")
        assert "PARTICIPATION_HOLE" in text
        assert "min_premium_floor" in text
