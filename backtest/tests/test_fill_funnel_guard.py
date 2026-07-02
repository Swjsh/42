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
