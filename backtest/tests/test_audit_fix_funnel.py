"""Guard for the fill-funnel FALSE-RED fix (audit fix #4, 2026-07-07).

THE DISEASE THIS REDs ON: setup/scripts/fill_funnel.py counted a CORE ENTER row as
`attempted` whenever its exec dict was truthy -- and a pure-skip exec like
{"status": "NOT_FLAT"} (we already hold a position; the broker is NEVER called) is
truthy. So a flat-veto day read attempted>0 & accepted==0 -> a phantom "PLACEMENT
BROKEN" RED that propagated to gamma_glance + self_check (it flagged RED on
2026-07-07 though the broker was never touched -- the fleet arms filled fine).

THE FIX: `attempted` counts a CORE ENTER only when its exec status is a REAL
placement OUTCOME (PLACED / PLACE_FAIL / NO_PREMIUM / RISK_DENY_* / broker reject).
NOT_FLAT and every SKIP_* bail before the broker -> not an attempt.

NON-VACUOUS (both directions):
  * a day of NOT_FLAT core ENTERs  -> attempted==0 AND verdict is NOT RED / not
    PLACEMENT BROKEN. (This is the branch that FLIPS when the fix is reverted.)
  * a GENUINE simple-order reject (PLACE_FAIL w/ real broker error, no bracket/oto)
    -> STILL attempted==1 and STILL RED / PLACEMENT BROKEN. (Proves the fix narrows
    only the never-hit-the-broker skips, not real placement faults.)
"""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name):
    path = os.path.join(ROOT, "setup", "scripts", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ff = _load("fill_funnel")

DAY = "2026-07-07"
MIDDAY = dt.datetime(2026, 7, 7, 12, 0)   # Tuesday 12:00 ET (in-session)
EOD = dt.datetime(2026, 7, 7, 18, 0)      # post-market


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _empty_fleet(tmp_path):
    d = tmp_path / "fleet-empty"
    d.mkdir(exist_ok=True)
    return d


def _not_flat_enter_rows(n=6, day=DAY):
    """N core ENTER_BEAR ticks that each skipped at the flat-verify gate (we already
    hold a position). exec status = NOT_FLAT: the broker is NEVER called, so there
    is NO broker dict and NO order id -- exactly today's real 2026-07-07 rows."""
    rows = []
    for i in range(n):
        rows.append({
            "ts_et": f"{day}T10:{40 + i:02d}:03", "account": "safe",
            "verdict": "ENTER_BEAR", "side": "P",
            "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
            "triggers": ["trendline_rejection"],
            "reason": "passed scoring + all entry gates",
            "exec": {"status": "NOT_FLAT"}, "action": "NOT_FLAT",
        })
    return rows


def _skip_enter_rows(day=DAY):
    """Core ENTERs that bailed at pre-broker SKIP gates (late/stale/early). Same
    truthy-exec trap: they must NOT count as placement attempts."""
    return [
        {"ts_et": f"{day}T15:10:03", "account": "safe", "verdict": "ENTER_BEAR",
         "triggers": ["trendline_rejection"], "reason": "late",
         "exec": {"status": "SKIP_LATE_ENTRY", "entry_ceiling_et": "15:00"},
         "action": "SKIP_LATE_ENTRY"},
        {"ts_et": f"{day}T09:31:03", "account": "bold", "verdict": "ENTER_BULL",
         "triggers": ["reclaim"], "reason": "early",
         "exec": {"status": "SKIP_EARLY_ENTRY", "entry_floor_et": "09:35"},
         "action": "SKIP_EARLY_ENTRY"},
    ]


def _genuine_reject_rows(day=DAY):
    """A REAL placement fault: the simple-first order was sent and the broker
    rejected it (insufficient buying power). No bracket_err/oto_err -> current
    simple-first code produced it -> a live fault that MUST stay RED."""
    return [{
        "ts_et": f"{day}T10:15:03", "account": "safe", "verdict": "ENTER_BEAR",
        "triggers": ["trendline_rejection"], "reason": "real fault",
        "exec": {"status": "PLACE_FAIL", "symbol": "SPY_TEST_P00740000", "qty": 3,
                 "broker": {"_error": "HTTP Error 403", "simple_err": {
                     "_status": 403, "_body": {"message": "insufficient buying power"}}}},
        "action": "PLACE_FAIL",
    }]


# ---------------------------------------------------------------------------
# DIRECTION 1 -- the branch the fix FLIPS: NOT_FLAT skips are not attempts,
# so a pure flat-veto day is NOT a phantom PLACEMENT BROKEN RED.
# ---------------------------------------------------------------------------

def test_not_flat_day_is_not_a_false_placement_red(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _not_flat_enter_rows(n=6))
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path), now=MIDDAY)
    a = f["accounts"]["core:safe"]
    assert a["enter"] == 6, "the 6 NOT_FLAT rows are still ENTER signals"
    assert a["attempted"] == 0, \
        "NOT_FLAT never calls the broker -> it is NOT a placement attempt"
    assert a["accepted"] == 0
    assert f["verdict"] != "RED", "a flat-veto day must NOT be a live RED"
    joined = " | ".join(f["flags"])
    assert "PLACEMENT BROKEN" not in joined, \
        "no broker call happened -> no PLACEMENT BROKEN flag"


def test_pre_broker_skip_statuses_are_not_attempts(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _skip_enter_rows())
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path), now=EOD)
    tot = f["totals"]
    assert tot["enter"] == 2, "both SKIP rows are ENTER signals"
    assert tot["attempted"] == 0, "SKIP_LATE_ENTRY / SKIP_EARLY_ENTRY bail before the broker"
    joined = " | ".join(f["flags"])
    assert "PLACEMENT BROKEN" not in joined


# ---------------------------------------------------------------------------
# DIRECTION 2 -- the BITE: a GENUINE broker reject STILL goes RED. Proves the
# fix narrows only never-hit-the-broker skips, not real placement faults.
# ---------------------------------------------------------------------------

def test_genuine_simple_reject_still_red(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _genuine_reject_rows())
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path), now=MIDDAY)
    a = f["accounts"]["core:safe"]
    assert a["attempted"] == 1, "a broker-rejected PLACE_FAIL IS a real placement attempt"
    assert a["accepted"] == 0
    assert a["retired_ladder_fails"] == 0, "no bracket/oto -> current-code fault, not pre-fix"
    assert f["verdict"] == "RED", "a genuine simple-first rejection must STILL be a live RED"
    joined = " | ".join(f["flags"])
    assert "PLACEMENT BROKEN[core:safe]" in joined
    assert "insufficient buying power" in joined


def test_not_flat_skips_mixed_with_one_real_reject_still_red(tmp_path):
    """Mixed day: 6 NOT_FLAT skips + 1 genuine reject. attempted counts ONLY the
    real reject (not the skips), and the day STILL REDs on that one real fault."""
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, _not_flat_enter_rows(n=6) + _genuine_reject_rows())
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path), now=MIDDAY)
    a = f["accounts"]["core:safe"]
    assert a["enter"] == 7
    assert a["attempted"] == 1, "6 NOT_FLAT excluded; only the genuine reject is an attempt"
    assert f["verdict"] == "RED"
    assert "PLACEMENT BROKEN[core:safe]" in " | ".join(f["flags"])


# ---------------------------------------------------------------------------
# fail-open safety: an UNKNOWN core exec status is still counted as an attempt
# (a novel real fault must never be silently swallowed -- OP-33 visibility).
# ---------------------------------------------------------------------------

def test_unknown_status_fails_open_to_attempted(tmp_path):
    core = tmp_path / "core.jsonl"
    _write_jsonl(core, [{
        "ts_et": f"{DAY}T10:15:03", "account": "safe", "verdict": "ENTER_BEAR",
        "triggers": ["trendline_rejection"], "reason": "novel",
        "exec": {"status": "SOME_BRAND_NEW_FAULT", "broker": {}},
        "action": "SOME_BRAND_NEW_FAULT",
    }])
    f = ff.compute_funnel(DAY, core_path=core, fleet_dir=_empty_fleet(tmp_path), now=MIDDAY)
    a = f["accounts"]["core:safe"]
    assert a["attempted"] == 1, "an unrecognized status must fail OPEN (counted), never hide a fault"


# ---------------------------------------------------------------------------
# unit-level check on the classifier itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,expected", [
    ("NOT_FLAT", False), ("SKIP_LATE_ENTRY", False), ("SKIP_EARLY_ENTRY", False),
    ("SKIP_STALE_TRIGGER", False), ("NO_CREDS", False), ("EQUITY_FETCH_FAIL", False),
    ("WOULD_PLACE", False),
    ("PLACED", True), ("PLACE_FAIL", True), ("NO_PREMIUM", True),
    # 2026-07-08: RISK_DENY_* reclassified as rule_block (own funnel stage), NOT an
    # attempt -- a PDT-jail day spammed "PLACEMENT BROKEN" while Rule 7 worked.
    # See test_fill_funnel_guard.py::test_risk_deny_is_rule_block_not_broken.
    ("RISK_DENY_MAXLOSS", False), ("RISK_DENY_ANYTHING", False),
    ("SOME_UNKNOWN", True),  # fail open
])
def test_core_is_attempt_classifier(status, expected):
    assert ff._core_is_attempt(status) is expected
    if status.startswith("RISK_DENY"):
        assert ff._core_is_rule_block(status) is True
