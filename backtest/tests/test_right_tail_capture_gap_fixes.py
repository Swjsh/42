"""RED-proof for GOAL-FLEET-CAPTURE-GAP-2026-09-05 F3 defect fixes to
setup/scripts/right_tail_capture.py.

Two bugs fixed in the same fire:
1. `_refusal_reason` discarded every gate rejection (min_triggers/confluence) because
   those rows carry risk_code=None -- the OLD filter `risk_code not in (None, "ALLOW")`
   excluded them. Confirmed against real safe-3/risky-1 decisions.jsonl rows, e.g.
   {"risk_code": None, "reason": "gate: 1 triggers < 2"}.
2. `_fleet_decisions_for_arm_day` returned [] unconditionally for safe-2/bold-2 (core,
   mcp_heartbeat-executed arms with no fleet decisions.jsonl file), so every missed wave
   for those two arms fell through to "no matching fleet decision row found" even when
   core-decisions.jsonl had a real HOLD/SKIP_* row at that tick.

Both tests fail against the pre-fix code (risk_code=None gate row -> None; core-account
arm -> [] regardless of core-decisions.jsonl content) and pass against the fix.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import right_tail_capture as rtc  # noqa: E402


def test_gate_reason_with_null_risk_code_is_recovered_not_dropped():
    decisions = [
        {
            "ts_et": "2026-08-04T12:27:03.000000",
            "action": "HOLD",
            "risk_code": None,
            "reason": "gate: 1 triggers < 2",
        }
    ]
    after = dt.datetime(2026, 8, 4, 12, 26, 3)
    result = rtc._refusal_reason(decisions, after)
    assert result is not None, "gate: rejection with risk_code=None must not be discarded"
    assert result == "GATE: gate: 1 triggers < 2"


def test_a_plus_gate_reason_recovered():
    decisions = [
        {
            "ts_et": "2026-08-04T12:27:03.000000",
            "action": "HOLD",
            "risk_code": None,
            "reason": "A+ gate: confidence missing, need >= 0.65",
        }
    ]
    after = dt.datetime(2026, 8, 4, 12, 26, 3)
    result = rtc._refusal_reason(decisions, after)
    assert result is not None
    assert result.startswith("GATE: A+ gate:")


def test_generic_no_setup_hold_still_returns_none():
    """A genuine 'nothing fired' HOLD (not a gate rejection) must still be filtered out --
    the fix must not become a catch-all that erases the 'no attributable evidence' case."""
    decisions = [
        {
            "ts_et": "2026-08-04T12:27:03.000000",
            "action": "HOLD",
            "risk_code": None,
            "reason": "no qualifying setup (no strategy fired)",
        }
    ]
    after = dt.datetime(2026, 8, 4, 12, 26, 3)
    result = rtc._refusal_reason(decisions, after)
    assert result is None


def test_core_account_arms_read_core_decisions_not_empty_fleet_dir(tmp_path, monkeypatch):
    core_path = tmp_path / "core-decisions.jsonl"
    rows = [
        {"ts_et": "2026-08-04T12:27:03", "account": "bold", "action": "SKIP_STRUCTURE_VETO",
         "verdict": "HOLD", "reason": "structure-veto: C entry blocked",
         "bull_blockers": ["structure"], "bear_blockers": []},
        {"ts_et": "2026-08-04T12:27:03", "account": "safe", "action": "HOLD", "verdict": "HOLD",
         "reason": "no setup passed scoring", "bull_blockers": [], "bear_blockers": []},
    ]
    core_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(rtc, "CORE_DECISIONS_PATH", core_path)

    bold_rows = rtc._fleet_decisions_for_arm_day("bold-2", "2026-08-04")
    assert len(bold_rows) == 1
    assert bold_rows[0]["risk_code"] == "SKIP_STRUCTURE_VETO"

    safe_rows = rtc._fleet_decisions_for_arm_day("safe-2", "2026-08-04")
    assert len(safe_rows) == 1
    assert safe_rows[0]["risk_code"] is None  # genuine no-signal HOLD, not a gate


def test_core_reshape_uses_action_not_verdict_pdt_deny_real_row(tmp_path, monkeypatch):
    """RED-proof for the v1->v2 reshape fix: a verdict=ENTER_BULL row whose real
    execution outcome was a PDT denial must surface as RISK_DENY_PDT, not as a
    filtered-out ALLOW. Fixture is the real 2026-08-04T12:26:55 bold-account row
    (fields trimmed) that motivated this fix."""
    core_path = tmp_path / "core-decisions.jsonl"
    row = {
        "ts_et": "2026-08-04T12:26:55", "account": "bold",
        "verdict": "ENTER_BULL", "action": "RISK_DENY_PDT",
        "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
        "bull_blockers": [], "bear_blockers": [5, 7, 8, 9, 10],
        "exec": {"status": "RISK_DENY_PDT", "reason": "bold: 3 day-trades in 5d ... PDT rule blocks a 4th day-trade"},
    }
    core_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(rtc, "CORE_DECISIONS_PATH", core_path)

    bold_rows = rtc._fleet_decisions_for_arm_day("bold-2", "2026-08-04")
    assert len(bold_rows) == 1
    assert bold_rows[0]["risk_code"] == "RISK_DENY_PDT", (
        "using verdict instead of action would mislabel this ALLOW and hide the PDT deny"
    )


def test_fleet_rest_arms_unaffected_still_read_own_decisions_file():
    assert "safe-3" not in rtc.CORE_ACCOUNT_FOR_ARM
    assert "risky-1" not in rtc.CORE_ACCOUNT_FOR_ARM
