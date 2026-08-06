"""Graduated guards for the fill-funnel truth instrument (built 2026-07-01).

THE DISEASE THESE RED ON: 2026-07-01 ground truth was 766 core decision rows,
10 ENTER_BEAR (all PLACE_FAIL, 0 broker-accepted) + 4 fleet ENTER_BULL that
FILLED and were exit-managed -- yet the EOD journal claimed "ENTER signals: 0"
and loop-state.json said ticks_today=0. The funnel (setup/scripts/fill_funnel.py)
re-derives ticks -> signals -> ENTER -> attempted -> accepted -> filled -> exited
from the ledgers; self_check flags PLACEMENT BROKEN as BROKEN.

Fixtures under fixtures/ are TODAY'S REAL ROWS (core: all 22 non-HOLD + 20
sampled HOLDs; fleet: risky-1 full round trip, safe-1 incl. the 15:52 PLACE_FAIL
bear). If funnel math regresses, these tests fail against the real tape.
"""
import datetime as dt
import importlib.util
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIX = os.path.join(HERE, "fixtures")
CORE_FIXTURE = os.path.join(FIX, "funnel-core-2026-07-01.jsonl")
FLEET_FIXTURE = os.path.join(FIX, "funnel-fleet-2026-07-01")


def _load(name):
    path = os.path.join(ROOT, "setup", "scripts", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ff = _load("fill_funnel")
sc = _load("self_check")
lsr = _load("loop_state_refresh")

from pathlib import Path

DAY = "2026-07-01"
EOD = dt.datetime(2026, 7, 1, 18, 0)   # Wednesday 18:00 ET (post-market)
MIDDAY = dt.datetime(2026, 7, 1, 12, 0)


def _empty_fleet(tmp_path):
    d = tmp_path / "fleet-empty"
    d.mkdir(exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# BUILD 1 guard: today's REAL rows -> ENTER=10, accepted=0. FRAME-CORRECTED
# 2026-07-02: every 2026-07-01 rejection carries bracket_err/oto_err (the retired
# bracket->oto->simple ladder). The shipped _place_simple_entry code emits only
# simple_err/_error (guarded build-side: test_money_path_2026_07_01 AST + behavioral),
# so this day is PROVABLY pre-fix history -> DEGRADED "PLACEMENT PRE-FIX ARTIFACT",
# NOT a live RED. Leaving it RED left self_check perpetually-BROKEN on stale data,
# masking a genuine future placement fault (L189/L197).
# ---------------------------------------------------------------------------

def test_real_day_core_is_pre_fix_artifact_degraded(tmp_path):
    f = ff.compute_funnel(DAY, core_path=Path(CORE_FIXTURE),
                          fleet_dir=_empty_fleet(tmp_path), now=EOD)
    t = f["totals"]
    assert t["enter"] == 10, f"expected 10 ENTER from today's real rows, got {t['enter']}"
    assert t["attempted"] == 10
    assert t["accepted"] == 0, "0 broker-accepted was today's ground truth"
    # every failed attempt used the retired ladder -> pre-fix artifact, not live RED
    for name in ("core:safe", "core:bold"):
        a = f["accounts"][name]
        assert a["retired_ladder_fails"] == a["attempted"] > 0, \
            f"{name}: all 2026-07-01 fails carry bracket_err/oto_err (retired ladder)"
    assert f["verdict"] != "RED", "a provably pre-fix day must NOT be a live RED"
    joined = " | ".join(f["flags"])
    assert "PLACEMENT PRE-FIX ARTIFACT[core:safe]" in joined
    assert "PLACEMENT PRE-FIX ARTIFACT[core:bold]" in joined
    assert "PLACEMENT BROKEN" not in joined, "retired-ladder rejections are not a live fault"
    # PLACE_FAIL reasons must still be surfaced verbatim from the broker response
    assert "expires soon" in joined or any(
        "expires soon" in r for a in f["accounts"].values() for r in a["place_fail_reasons"])


# ---------------------------------------------------------------------------
# THE NON-VACUOUS BITE: a GENUINE placement fault (simple order rejected, NO
# bracket/oto attempt) must STILL fire PLACEMENT BROKEN -> RED. This proves the
# pre-fix carve-out narrows only the retired-ladder signature, not real faults.
# ---------------------------------------------------------------------------

def _simple_only_reject_rows(day="2026-07-02"):
    """An ENTER whose simple-first order was rejected (e.g. buying power / bad limit).
    No bracket_err/oto_err -> current code produced it -> a live fault."""
    return [{
        "ts_et": f"{day}T10:15:02", "account": "safe", "verdict": "ENTER_BEAR",
        "triggers": ["trendline_rejection"], "reason": "test",
        "exec": {"status": "PLACE_FAIL", "symbol": "SPY_TEST_P00740000", "qty": 3,
                 "broker": {"_error": "HTTP Error 403", "simple_err": {
                     "_status": 403, "_body": {"message": "insufficient buying power"}}}},
    }]


def test_genuine_simple_only_rejection_is_placement_broken_red(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _simple_only_reject_rows())
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 12, 0))
    a = f["accounts"]["core:safe"]
    assert a["attempted"] == 1 and a["accepted"] == 0
    assert a["retired_ladder_fails"] == 0, "no bracket/oto attempt -> not a retired-ladder day"
    assert f["verdict"] == "RED"
    joined = " | ".join(f["flags"])
    assert "PLACEMENT BROKEN[core:safe]" in joined
    assert "insufficient buying power" in joined


def test_real_day_enter_after_ceiling_flagged(tmp_path):
    f = ff.compute_funnel(DAY, core_path=Path(CORE_FIXTURE),
                          fleet_dir=_empty_fleet(tmp_path), now=EOD)
    joined = " | ".join(f["flags"])
    assert "ENTER AFTER CEILING" in joined, "core ENTERs fired 15:51-15:55, past the 15:00 ceiling"


def test_real_day_fleet_fills_and_exits_counted(tmp_path):
    core = tmp_path / "core-empty.jsonl"
    core.write_text("", encoding="utf-8")
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=Path(FLEET_FIXTURE), now=EOD)
    r1 = f["accounts"]["fleet:risky-1"]
    assert (r1["enter"], r1["accepted"], r1["filled"], r1["exited"]) == (1, 1, 1, 1), \
        "risky-1's real 11:22 ENTER_BULL was accepted, filled, and exit-managed (SELL_ALL placed)"
    s1 = f["accounts"]["fleet:safe-1"]
    assert s1["enter"] == 2 and s1["accepted"] == 1, \
        "safe-1: 11:22 bull accepted + 15:52 bear PLACE_FAIL"
    joined = " | ".join(f["flags"])
    assert "PLACEMENT BROKEN[fleet:safe-1]" not in joined, \
        "an arm with >=1 accepted order is NOT placement-broken"
    assert f["verdict"] != "RED"
    assert "FILL WITHOUT EXIT" not in joined, "the round trip was exit-managed"


# ---------------------------------------------------------------------------
# synthetic healthy day -> GREEN
# ---------------------------------------------------------------------------

def _healthy_rows(day="2026-07-02"):
    enter = {
        "ts_et": f"{day}T10:15:02", "account": "safe", "verdict": "ENTER_BEAR",
        "triggers": ["trendline_rejection"], "reason": "test",
        "exec": {"status": "PLACED", "symbol": "SPY_TEST_P00740000", "qty": 3,
                 "broker": {"id": "abc-123", "filled_qty": "3", "symbol": "SPY_TEST_P00740000"}},
    }
    fill_seen = {"ts_et": f"{day}T10:20:02", "account": "safe", "verdict": "HOLD",
                 "exit_pass": [{"symbol": "SPY_TEST_P00740000", "open_qty": 3, "actions": []}]}
    exited = {"ts_et": f"{day}T10:40:02", "account": "safe", "verdict": "HOLD",
              "exit_pass": [{"symbol": "SPY_TEST_P00740000", "open_qty": 3,
                             "actions": [{"kind": "SELL_ALL", "qty": 3, "placed": True,
                                          "broker": {"id": "def-456"}}]}]}
    holds = [{"ts_et": f"{day}T10:{m:02d}:02", "account": "safe", "verdict": "HOLD"}
             for m in range(45, 55)]
    return [enter, fill_seen, exited] + holds


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_synthetic_healthy_day_green(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _healthy_rows())
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    a = f["accounts"]["core:safe"]
    assert (a["enter"], a["attempted"], a["accepted"], a["filled"], a["exited"]) == (1, 1, 1, 1, 1)
    assert f["flags"] == []
    assert f["verdict"] == "GREEN"


def test_fill_without_exit_degraded_only_at_eod(tmp_path):
    rows = _healthy_rows()
    rows[2]["exit_pass"][0]["actions"] = []  # never exited
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, rows)
    # midday: open fill is normal -> no flag
    f_mid = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                              now=dt.datetime(2026, 7, 2, 12, 0))
    assert "FILL WITHOUT EXIT" not in " | ".join(f_mid["flags"])
    # post-EOD: a fill with no exit record = DEGRADED
    f_eod = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                              now=dt.datetime(2026, 7, 2, 16, 30))
    assert "FILL WITHOUT EXIT" in " | ".join(f_eod["flags"])
    assert f_eod["verdict"] == "DEGRADED"


def test_idle_day_is_not_a_fault(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, [{"ts_et": "2026-07-02T10:00:02", "account": "safe", "verdict": "HOLD"}])
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    assert f["verdict"] == "IDLE" and f["flags"] == []


# ---------------------------------------------------------------------------
# self_check wiring: PLACEMENT BROKEN must classify as BROKEN
# ---------------------------------------------------------------------------

def test_self_check_pre_fix_artifact_not_broken(tmp_path):
    # FRAME-CORRECTED 2026-07-02: today's real rows are a provable pre-fix
    # retired-ladder day -> self_check must surface them (DEGRADED) but NOT flag
    # BROKEN (which would keep self_check perpetually-RED on immutable stale data).
    problems = sc.check_fill_funnel(EOD, core_path=Path(CORE_FIXTURE),
                                    fleet_dir=_empty_fleet(tmp_path))
    assert problems, "today's real rows must still surface fill-funnel problems"
    joined = " | ".join(problems)
    assert "PRE-FIX ARTIFACT" in joined, "retired-ladder day must be surfaced as a pre-fix artifact"
    assert "PLACEMENT BROKEN" not in joined
    assert not any(sc._problem_is_broken(p) for p in problems), \
        "a provably pre-fix day must NOT map to the BROKEN verdict"


def test_self_check_genuine_placement_fault_is_broken(tmp_path):
    # THE BITE: a real simple-first rejection (no bracket/oto) must map to BROKEN.
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _simple_only_reject_rows(day=DAY))
    problems = sc.check_fill_funnel(EOD, core_path=core, fleet_dir=_empty_fleet(tmp_path))
    joined = " | ".join(problems)
    assert "PLACEMENT BROKEN" in joined
    assert any(sc._problem_is_broken(p) for p in problems), \
        "a genuine simple-first placement fault must map to the BROKEN verdict"


def test_self_check_healthy_day_silent(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _healthy_rows())
    problems = sc.check_fill_funnel(dt.datetime(2026, 7, 2, 18, 0), core_path=core,
                                    fleet_dir=_empty_fleet(tmp_path))
    assert problems == []


def test_self_check_skips_weekend_and_premarket(tmp_path):
    sat = dt.datetime(2026, 7, 4, 12, 0)   # Saturday
    assert sc.check_fill_funnel(sat, core_path=Path(CORE_FIXTURE),
                                fleet_dir=_empty_fleet(tmp_path)) == []
    early = dt.datetime(2026, 7, 1, 9, 0)  # before 09:40 gate
    assert sc.check_fill_funnel(early, core_path=Path(CORE_FIXTURE),
                                fleet_dir=_empty_fleet(tmp_path)) == []


# ---------------------------------------------------------------------------
# BUILD 3 guard: loop-state ticks_today derived from the ledger
# ---------------------------------------------------------------------------

def test_loop_state_refresh_derives_ticks_from_ledger(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "loop-state.json").write_text(json.dumps(
        {"schema_version": 3, "ticks_today": 0, "current_mode": "BASE"}), encoding="utf-8")
    core = state / "core-decisions.jsonl"
    core.write_text(Path(CORE_FIXTURE).read_text(encoding="utf-8"), encoding="utf-8")
    s = lsr.refresh(EOD, state_dir=state)
    assert s["changed"] is True
    ls = json.loads((state / "loop-state.json").read_text(encoding="utf-8"))
    assert ls["ticks_today"] > 0, "766-real-rows-vs-ticks_today=0 was the 2026-07-01 lie"
    assert ls["ticks_today"] == s["ticks_today"]
    assert ls["ticks_today_source"] == "core-decisions.jsonl"
    assert ls["current_mode"] == "BASE", "refresher must not clobber other fields"
    # idempotent second run: no rewrite
    s2 = lsr.refresh(EOD, state_dir=state)
    assert s2["changed"] is False


def test_loop_state_refresh_fails_open(tmp_path):
    state = tmp_path / "state"
    state.mkdir()  # no loop-state.json at all
    s = lsr.refresh(EOD, state_dir=state)
    assert s["changed"] is False and "missing" in s["note"]


# ---------------------------------------------------------------------------
# BUILD 2 guard: the EOD quant renderer carries the CSV P&L (the -$215 truth)
# ---------------------------------------------------------------------------

def test_render_markdown_carries_csv_pnl(tmp_path):
    repo = tmp_path / "repo"
    (repo / "journal").mkdir(parents=True)
    # headerless row, trades-aggressive.csv style (dollar_pnl at index 13)
    (repo / "journal" / "trades-aggressive.csv").write_text(
        "2026-07-01,09:45:21,09:51:35,RECONCILE_FILL,SPY260701P00742000,0,742,P,5,"
        "1.22,0.79,610,395,-215,N/A\n", encoding="utf-8")
    f = ff.compute_funnel(DAY, core_path=Path(CORE_FIXTURE),
                          fleet_dir=_empty_fleet(tmp_path), now=EOD)
    md = ff.render_markdown(f, repo=repo)
    assert "-215" in md and "RECONCILE_FILL" in md
    assert "PLACE_FAIL reasons" in md and "expires soon" in md
    assert "| **TOTAL** |" in md


# ---------------------------------------------------------------------------
# BUILD 3 guard (2026-07-08): RISK_DENY_* is RULE ENFORCEMENT, not a placement
# fault. The disease: 13 real ENTER rows (PDT jail day) all exec.status=
# RISK_DENY_PDT read as attempted>0 & accepted==0 -> "PLACEMENT BROKEN" spam
# to Discord while Rule 7 was working exactly as designed. RISK_DENY_* now has
# its own funnel stage `rule_blocked` + an informational RULE-BLOCKED flag.
# ---------------------------------------------------------------------------

def test_risk_deny_is_rule_block_not_broken(tmp_path):
    core = tmp_path / "core-decisions.jsonl"
    rows = []
    for i in range(3):
        rows.append(json.dumps({
            "ts_et": f"2026-07-08T13:3{i}:02", "account": "safe", "armed": True,
            "verdict": "ENTER_BULL", "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
            "triggers": ["level_reclaim"], "reason": "scored",
            "exec": {"status": "RISK_DENY_PDT",
                     "reason": "safe: 7 day-trades in 5d at equity $1,513 < $25,000",
                     "symbol": "SPY260708C00749000", "qty": 5, "premium": 0.15},
        }))
    core.write_text("\n".join(rows) + "\n", encoding="utf-8")
    f = ff.compute_funnel("2026-07-08", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 8, 18, 0))
    a = f["accounts"]["core:safe"]
    assert a["enter"] == 3
    assert a["rule_blocked"] == 3, "RISK_DENY rows must land in the rule_blocked stage"
    assert a["attempted"] == 0, "a risk-gate refusal is NOT a placement attempt"
    assert f["verdict"] != "RED", "rule enforcement must never read as PLACEMENT BROKEN"
    assert not any("PLACEMENT BROKEN" in fl for fl in f["flags"])
    assert any("RULE-BLOCKED[core:safe]" in fl for fl in f["flags"]), "must stay VISIBLE (OP-33)"


# ---------------------------------------------------------------------------
# BUILD 4 guard (2026-07-16, SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN.md §5 row 5):
# a FLEET ENTER row whose placement died at the entry-ceiling/floor gate
# (fleet_live.py's _place_live returns mode="LIVE", reason="SKIP_LATE_ENTRY"/
# "SKIP_EARLY_ENTRY" BEFORE any broker call) must NOT count as `attempted` --
# and must therefore never trip PLACEMENT BROKEN. Mirrors the core NOT_FLAT fix.
# ---------------------------------------------------------------------------

def _fleet_skip_late_entry_row(day="2026-07-16", arm="safe-1"):
    return [{
        "ts_et": f"{day}T15:52:01", "arm_id": arm, "action": "ENTER_BEAR",
        "side": "P", "setup_name": "BEARISH_REJECTION", "strike": 744, "qty": 3,
        "reason": "trendline_rejection",
        "placement": {"mode": "LIVE", "placed": False, "reason": "SKIP_LATE_ENTRY",
                      "entry_ceiling_et": "15:00"},
    }]


def test_fleet_skip_late_entry_not_attempted_not_broken(tmp_path):
    fleet_dir = tmp_path / "fleet"
    arm_dir = fleet_dir / "safe-1"
    arm_dir.mkdir(parents=True)
    _write_jsonl(arm_dir / "decisions.jsonl", _fleet_skip_late_entry_row())
    core = tmp_path / "core-empty.jsonl"
    core.write_text("", encoding="utf-8")
    f = ff.compute_funnel("2026-07-16", core_path=core, fleet_dir=fleet_dir,
                          now=dt.datetime(2026, 7, 16, 18, 0))
    a = f["accounts"]["fleet:safe-1"]
    assert a["enter"] == 1, "the ENTER_BEAR row must still be counted as an ENTER"
    assert a["attempted"] == 0, "SKIP_LATE_ENTRY bailed before the broker -- NOT an attempt"
    assert a["accepted"] == 0
    joined = " | ".join(f["flags"])
    assert "PLACEMENT BROKEN" not in joined, \
        "a correctly time-gated SKIP_LATE_ENTRY must never read as PLACEMENT BROKEN"
    assert f["verdict"] != "RED"


def test_fleet_skip_early_entry_not_attempted_not_broken(tmp_path):
    fleet_dir = tmp_path / "fleet"
    arm_dir = fleet_dir / "risky-1"
    arm_dir.mkdir(parents=True)
    row = _fleet_skip_late_entry_row(arm="risky-1")
    row[0]["placement"] = {"mode": "LIVE", "placed": False, "reason": "SKIP_EARLY_ENTRY",
                            "entry_floor_et": "09:35"}
    _write_jsonl(arm_dir / "decisions.jsonl", row)
    core = tmp_path / "core-empty.jsonl"
    core.write_text("", encoding="utf-8")
    f = ff.compute_funnel("2026-07-16", core_path=core, fleet_dir=fleet_dir,
                          now=dt.datetime(2026, 7, 16, 18, 0))
    a = f["accounts"]["fleet:risky-1"]
    assert a["enter"] == 1 and a["attempted"] == 0 and a["accepted"] == 0
    assert not any("PLACEMENT BROKEN" in fl for fl in f["flags"])
    assert f["verdict"] != "RED"


def test_fleet_genuine_place_fail_still_broken(tmp_path):
    """THE NON-VACUOUS BITE: a fleet ENTER that DID reach the broker and got
    rejected must still trip PLACEMENT BROKEN -- the skip-reason carve-out must
    not swallow real placement faults."""
    fleet_dir = tmp_path / "fleet"
    arm_dir = fleet_dir / "safe-1"
    arm_dir.mkdir(parents=True)
    rows = [{
        "ts_et": "2026-07-16T10:15:01", "arm_id": "safe-1", "action": "ENTER_BEAR",
        "side": "P", "setup_name": "BEARISH_REJECTION", "strike": 744, "qty": 3,
        "reason": "trendline_rejection",
        "placement": {"mode": "LIVE", "placed": False, "reason": "order rejected",
                      "symbol": "SPY260716P00744000",
                      "broker": {"_error": "insufficient buying power"}},
    }]
    _write_jsonl(arm_dir / "decisions.jsonl", rows)
    core = tmp_path / "core-empty.jsonl"
    core.write_text("", encoding="utf-8")
    f = ff.compute_funnel("2026-07-16", core_path=core, fleet_dir=fleet_dir,
                          now=dt.datetime(2026, 7, 16, 18, 0))
    a = f["accounts"]["fleet:safe-1"]
    assert a["attempted"] == 1 and a["accepted"] == 0
    assert any("PLACEMENT BROKEN[fleet:safe-1]" in fl for fl in f["flags"])
    assert f["verdict"] == "RED"


# ---------------------------------------------------------------------------
# BUILD 5 guard (2026-07-20): a `verdict`=ENTER row that was ALREADY correctly
# gated by heartbeat_core.py's own entry-time ceiling (action="SKIP_LATE_ENTRY",
# no exec dict, zero broker attempt -- confirmed via 2026-07-20 real ground
# truth: 6 core rows 15:41-15:45 ET, all attempted==0) must NOT be flagged as
# "ENTER AFTER CEILING" -- that flag means the GATE FAILED, not that it fired.
# Producer/consumer mismatch: this funnel keyed off the pre-gate `verdict`
# field while the ceiling's own verdict lives in the post-gate `action` field.
# ---------------------------------------------------------------------------

def _core_skip_late_entry_row(day="2026-07-20", hhmm="15:41:02"):
    return [{
        "ts_et": f"{day}T{hhmm}", "account": "safe", "verdict": "ENTER_BEAR",
        "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "triggers": ["trendline_rejection"],
        "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates",
        "action": "SKIP_LATE_ENTRY", "entry_ceiling_et": "15:00",
        # no "exec" key at all -- the ceiling branch never reaches _execute
    }]


def test_enter_after_ceiling_excludes_gated_skip_late_entry(tmp_path):
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, _core_skip_late_entry_row())
    f = ff.compute_funnel("2026-07-20", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 20, 18, 0))
    a = f["accounts"]["core:safe"]
    assert a["enter"] == 1, "still counted as an ENTER verdict"
    assert a["attempted"] == 0, "SKIP_LATE_ENTRY never reaches _execute -- no exec dict"
    assert a["enters_after_ceiling"] == [], \
        "a row the ceiling gate already caught (action=SKIP_LATE_ENTRY) is NOT a bypass"
    joined = " | ".join(f["flags"])
    assert "ENTER AFTER CEILING" not in joined
    assert f["verdict"] != "RED"


def test_enter_after_ceiling_fleet_excludes_gated_skip_late_entry(tmp_path):
    fleet_dir = tmp_path / "fleet"
    arm_dir = fleet_dir / "safe-1"
    arm_dir.mkdir(parents=True)
    _write_jsonl(arm_dir / "decisions.jsonl", _fleet_skip_late_entry_row())
    core = tmp_path / "core-empty.jsonl"
    core.write_text("", encoding="utf-8")
    f = ff.compute_funnel("2026-07-16", core_path=core, fleet_dir=fleet_dir,
                          now=dt.datetime(2026, 7, 16, 18, 0))
    a = f["accounts"]["fleet:safe-1"]
    assert a["enters_after_ceiling"] == [], \
        "fleet SKIP_LATE_ENTRY (placement.reason) is also gate-caught, not a bypass"
    joined = " | ".join(f["flags"])
    assert "ENTER AFTER CEILING" not in joined


def test_real_day_enter_after_ceiling_still_flagged_when_genuinely_bypassed(tmp_path):
    """THE NON-VACUOUS BITE: the 2026-07-01 fixture (pre-dates the ceiling gate --
    action="PLACE_FAIL", a REAL broker attempt after 15:00) must still trip the
    flag. Duplicates test_real_day_enter_after_ceiling_flagged as an explicit
    regression pin for this fix."""
    f = ff.compute_funnel(DAY, core_path=Path(CORE_FIXTURE),
                          fleet_dir=_empty_fleet(tmp_path), now=EOD)
    joined = " | ".join(f["flags"])
    assert "ENTER AFTER CEILING" in joined, \
        "a genuine post-ceiling broker attempt (action=PLACE_FAIL, not SKIP_LATE_ENTRY) must still flag"


def test_unknown_exec_status_still_fails_open_to_red(tmp_path):
    """The fail-open invariant survives the rule-block split: a NEW unrecognized
    status still counts as attempted and (with 0 accepted) still trips RED."""
    core = tmp_path / "core-decisions.jsonl"
    core.write_text(json.dumps({
        "ts_et": "2026-07-08T10:00:02", "account": "safe", "armed": True,
        "verdict": "ENTER_BEAR", "side": "P", "setup": "BEARISH_REJECTION",
        "triggers": ["trendline_rejection"], "reason": "scored",
        "exec": {"status": "SOME_NEW_FAULT", "symbol": "SPY260708P00745000", "qty": 3},
    }) + "\n", encoding="utf-8")
    f = ff.compute_funnel("2026-07-08", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 8, 18, 0))
    a = f["accounts"]["core:safe"]
    assert a["attempted"] == 1 and a["rule_blocked"] == 0
    assert f["verdict"] == "RED"


# ---------------------------------------------------------------------------
# BUILD 6 guard (2026-07-22): secondary-setup (extra_exec) attribution + the
# IDLE-misclassification fix it exposed. Ground truth: 2026-07-22 core:safe
# read enter=0/attempted=0/accepted=0 in the PRIMARY ENTER pipeline while
# extra_exec fired 4 PLACED across vwap_continuation + bollinger_squeeze (the
# secondary-setup placement path fill_funnel never counted) and 2 real
# broker-truth fills+exits landed via exit_pass with zero primary ENTER rows.
# The old verdict line keyed on `enter` ALONE -> read IDLE -> propagated into
# gamma-narrative.json's facts_digest + LLM narrative text as "the system
# stayed idle" on a day the engine actually placed and filled orders. C7
# (silent success is failure): this did not crash, it just told J the wrong
# thing about whether the engine traded.
# ---------------------------------------------------------------------------

def _extra_exec_only_rows(day="2026-07-02"):
    return [
        {"ts_et": f"{day}T10:00:02", "account": "safe", "verdict": "HOLD",
         "extra_exec": [{"setup": "vwap_continuation", "action": "PLACED"}]},
        {"ts_et": f"{day}T10:05:02", "account": "safe", "verdict": "HOLD",
         "extra_exec": [{"setup": "bollinger_squeeze", "action": "SKIP_LATE_ENTRY"}]},
        {"ts_et": f"{day}T10:10:02", "account": "safe", "verdict": "HOLD",
         "extra_exec": [{"setup": "vwap_continuation", "action": "PLACED"}]},
    ]


def test_extra_exec_attribution_counts_by_setup_and_action(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _extra_exec_only_rows())
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    a = f["accounts"]["core:safe"]
    assert a["extra_setup_placed"] == {
        "vwap_continuation": {"PLACED": 2},
        "bollinger_squeeze": {"SKIP_LATE_ENTRY": 1},
    }
    assert a["extra_placed_total"] == 2, "only PLACED actions count toward the total"
    assert f["totals"]["extra_placed_total"] == 2
    assert "vwap_continuation=2PLACED" in ff.render_text(f)
    md = ff.render_markdown(f, repo=tmp_path)
    assert "Secondary-setup placements (extra_exec, 2 PLACED)" in md
    assert "vwap_continuation: 2x PLACED" in md


def test_extra_exec_placed_flips_idle_to_green(tmp_path):
    """THE BITE: 0 primary ENTERs but a secondary-setup PLACED order fired ->
    the day is NOT idle. This is the exact 2026-07-22 disease reproduced."""
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _extra_exec_only_rows())
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    assert f["totals"]["enter"] == 0, "no primary-pipeline ENTER fired -- this is the trap"
    assert f["flags"] == []
    assert f["verdict"] == "GREEN", (
        "a day with a real secondary-setup PLACED order must not read IDLE -- "
        "IDLE silently told J 'the system stayed idle' while it placed orders")


def test_fill_via_exit_pass_alone_flips_idle_to_green(tmp_path):
    """The OTHER root cause: a real broker-truth fill+exit with 0 primary
    ENTER rows at all (2026-07-22 ground truth: core:safe filled=2/exited=2,
    enter=0) must also not read IDLE."""
    rows = [{"ts_et": "2026-07-02T10:00:02", "account": "safe", "verdict": "HOLD",
             "exit_pass": [{"symbol": "SPY_TEST_P00740000", "open_qty": 3,
                            "actions": [{"kind": "SELL_ALL", "qty": 3, "placed": True}]}]}]
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, rows)
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    a = f["accounts"]["core:safe"]
    assert a["enter"] == 0 and a["filled"] == 1 and a["exited"] == 1
    assert f["verdict"] == "GREEN", "a real broker-truth fill+exit with 0 ENTERs is not idle"


def test_genuinely_empty_day_still_reads_idle(tmp_path):
    """Non-vacuous bite the other direction: NO fill, NO extra_exec PLACED,
    NO enter -> still IDLE (duplicates test_idle_day_is_not_a_fault's intent
    with an explicit extra_setup_placed/extra_placed_total assertion)."""
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, [{"ts_et": "2026-07-02T10:00:02", "account": "safe", "verdict": "HOLD"}])
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    a = f["accounts"]["core:safe"]
    assert a["extra_setup_placed"] == {} and a["extra_placed_total"] == 0
    assert f["verdict"] == "IDLE"


# ---------------------------------------------------------------------------
# FILL-PROVENANCE + SYNTHETIC-ROW QUARANTINE guards (2026-08-06).
# THE SCAR: on 2026-08-06 core:safe filled TWO symbols -- a bear put off a
# primary ENTER_BEAR, and a bollinger_squeeze LONG off the secondary extra_exec
# path. The funnel rendered "2 filled / 2 exited from 5 ENTER verdicts", which
# read as though both were primary-pipeline entries. An EOD review then spent
# the day chasing a BULLISH_RECLAIM / filter-5 story for a trade the primary
# pipeline never made (its verdict that minute was HOLD; filter 5 never cleared
# all session). Same day, two armed=false/core_tick_id=null diagnostic rows sat
# in the LIVE ledger and inflated bollinger_squeeze to "2 PLACED" when exactly
# one order reached the broker.
# ---------------------------------------------------------------------------

def _mixed_pipeline_rows(day="2026-07-02"):
    """One PRIMARY ENTER fill (a put) + one SECONDARY extra_exec fill (a call)."""
    return [
        # primary pipeline: ENTER_BEAR -> placed + filled
        {"ts_et": f"{day}T10:31:03", "account": "safe", "armed": True,
         "core_tick_id": f"{day}T10:31:02", "verdict": "ENTER_BEAR",
         "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
         "exec": {"status": "PLACED", "symbol": "SPY260702P00770000", "qty": 3,
                  "broker": {"id": "ord-primary", "filled_qty": "3"}}},
        # secondary pipeline: verdict HOLD, order placed off extra_exec
        {"ts_et": f"{day}T14:21:03", "account": "safe", "armed": True,
         "core_tick_id": f"{day}T14:21:02", "verdict": "HOLD",
         "extra_exec": [{"setup": "bollinger_squeeze", "action": "PLACED",
                         "exec": {"status": "PLACED", "symbol": "SPY260702C00769000",
                                  "qty": 3, "broker": {"id": "ord-secondary"}}}]},
        # broker-truth: both symbols held then exited
        {"ts_et": f"{day}T14:22:03", "account": "safe", "armed": True,
         "core_tick_id": f"{day}T14:22:02", "verdict": "HOLD",
         "exit_pass": [{"symbol": "SPY260702P00770000", "open_qty": 3,
                        "actions": [{"kind": "SELL_ALL", "placed": True}]},
                       {"symbol": "SPY260702C00769000", "open_qty": 3,
                        "actions": [{"kind": "SELL_ALL", "placed": True}]}]},
    ]


def test_secondary_fill_is_not_credited_to_the_primary_pipeline(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _mixed_pipeline_rows())
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    a = f["accounts"]["core:safe"]
    assert a["filled"] == 2, "two distinct symbols reached the broker"
    assert a["filled_primary"] == 1, "exactly ONE fill came from the ENTER pipeline"
    assert a["filled_extra"] == 1, "the bollinger_squeeze long is a SECONDARY fill"
    assert a["filled_unattributed"] == 0
    assert a["extra_fill_setups"] == {"bollinger_squeeze": 1}
    head = a["why"]["headline"]
    assert "1 from 1 primary ENTER verdicts" in head, head
    assert "SECONDARY extra_exec" in head and "bollinger_squeeze x1" in head, head
    assert "NOT a primary ENTER" in head, (
        "the headline MUST say the secondary fill is not a primary entry -- "
        "this exact ambiguity produced the 2026-08-06 filter-5 misattribution")


def test_synthetic_unarmed_rows_are_quarantined_not_counted(tmp_path):
    rows = _mixed_pipeline_rows()
    # a diagnostic/gym write into the LIVE ledger: armed=false AND no core_tick_id
    rows.append({"ts_et": "2026-07-02T04:16:32", "account": "safe", "armed": False,
                 "core_tick_id": None, "verdict": "HOLD", "spy": 751.0,
                 "extra_exec": [{"setup": "bollinger_squeeze", "action": "PLACED",
                                 "exec": None}]})
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, rows)
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    a = f["accounts"]["core:safe"]
    assert f["synthetic_core_rows_excluded"] == 1
    assert a["ticks"] == 3, "the synthetic row must not inflate the tick count"
    assert a["extra_placed_total"] == 1, (
        "only the ONE real broker order counts -- the phantom armed=false PLACED "
        "with a null exec must not double the secondary-setup tally")
    assert "quarantined 1 synthetic core row" in ff.render_text(f)


def test_armed_row_with_tick_id_is_never_quarantined(tmp_path):
    """Non-vacuous the other way: a REAL tick is never dropped by the filter."""
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _mixed_pipeline_rows())
    f = ff.compute_funnel("2026-07-02", core_path=core, fleet_dir=_empty_fleet(tmp_path),
                          now=dt.datetime(2026, 7, 2, 18, 0))
    assert f["synthetic_core_rows_excluded"] == 0
    assert f["accounts"]["core:safe"]["ticks"] == 3
