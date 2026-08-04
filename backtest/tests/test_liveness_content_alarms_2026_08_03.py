"""Guards for the 2026-08-03 CONTENT-ALARM extensions to the two liveness watchers.

THE GAP (PIPELINE-CHAIN-MAP-2026-08-03.md): both watchers were CONTENT-BLIND -- a day of
772 armed SKIP_NO_DATA ticks, a fleet arm riding a stale signal all day, or the 2026-08-03
afternoon's 33-35 SKIP_MIN_PREMIUM_FLOOR wall per bold-tier arm all read RAN/ALL_TICKED and
alarmed nothing. These tests pin the additive closure:

  * dominance of a silent-failure shape produces named `content_alarms` + a reason fold +
    an alarm_line -- RED-proof: revert either module's content pass and these fail;
  * status / exit-code semantics are UNTOUCHED (fail-open) -- a degraded day still reads
    RAN / ALL_TICKED;
  * vary-and-assert: a healthy day produces ZERO alarms (the alarms cannot cry wolf).

$0, offline, synthetic ledgers in tmp_path. Run:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_liveness_content_alarms_2026_08_03.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import engine_liveness_check as elc  # noqa: E402
import fleet_liveness_check as flc  # noqa: E402

DAY = "2026-08-03"  # a Monday


# ---------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------
def _core_ledger(tmp_path: Path, rows: list) -> Path:
    p = tmp_path / "core-decisions.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _core_row(**over) -> dict:
    base = {"ts_et": f"{DAY}T10:00:00", "account": "safe", "armed": True,
            "verdict": "HOLD", "vix": 15.9, "blind": False}
    base.update(over)
    return base


def _fleet_ledger(tmp_path: Path, arm_id: str, rows: list) -> None:
    d = tmp_path / arm_id
    d.mkdir(exist_ok=True)
    with open(d / "decisions.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _fleet_row(**over) -> dict:
    base = {"ts_et": f"{DAY}T10:00:00.000000-04:00", "arm_id": "risky-1",
            "signal_status": "ok", "action": "HOLD", "risk_code": None, "reason": "x"}
    base.update(over)
    return base


def _accounts(tmp_path: Path, arm_ids=("safe-3", "risky-1", "risky-3")) -> Path:
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"arms": [
        {"id": a, "status": "active", "execution": "fleet_rest"} for a in arm_ids]}),
        encoding="utf-8")
    return p


# ---------------------------------------------------------------------------------------
# engine_liveness_check: core-ledger content alarms
# ---------------------------------------------------------------------------------------
def test_core_healthy_day_has_zero_content_alarms(tmp_path):
    """Vary-and-assert baseline: 100 clean armed ticks -> RAN, no alarms, no reason fold."""
    p = _core_ledger(tmp_path, [_core_row() for _ in range(100)])
    res = elc.check_day(DAY, path=p)
    assert res["status"] == elc.STATUS_RAN
    assert res["content_alarms"] == []
    assert "CONTENT ALARMS" not in res["reason"]
    assert elc.alarm_line(res) is None


def test_core_no_data_dominance_alarms_but_status_stays_ran(tmp_path):
    """The 2026-07-24-class hole's OTHER half: the process ticked, the feed was dead."""
    rows = ([_core_row(verdict="SKIP_NO_DATA") for _ in range(40)]
            + [_core_row() for _ in range(60)])
    res = elc.check_day(DAY, path=_core_ledger(tmp_path, rows))
    assert res["status"] == elc.STATUS_RAN, "fail-open: content alarms never fake an outage"
    assert any("FEED_DEAD_INSIDE_RUNNING_ENGINE" in a for a in res["content_alarms"])
    assert "CONTENT ALARMS" in res["reason"], "must ride reason so every consumer surfaces it"
    line = elc.alarm_line(res)
    assert line is not None and "degraded" in line


def test_core_blind_dominance_alarms(tmp_path):
    rows = ([_core_row(blind=True) for _ in range(50)] + [_core_row() for _ in range(50)])
    res = elc.check_day(DAY, path=_core_ledger(tmp_path, rows))
    assert any("BLIND" in a for a in res["content_alarms"])


def test_core_vix_zero_dominance_alarms(tmp_path):
    """vix=0.0 (the _fetch_vix fallback) silently disables the bear VIX floor AND opens the
    bull cap -- wrong-behavior, not just no-trade. Dominance must alarm."""
    rows = ([_core_row(vix=0.0) for _ in range(40)] + [_core_row() for _ in range(60)])
    res = elc.check_day(DAY, path=_core_ledger(tmp_path, rows))
    assert any("VIX_FEED_DEAD" in a for a in res["content_alarms"])


def test_core_infra_failures_alarm_at_absolute_threshold(tmp_path):
    rows = ([_core_row(verdict="ENTER_BEAR", exec={"status": "EQUITY_FETCH_FAIL"})
             for _ in range(3)] + [_core_row() for _ in range(97)])
    res = elc.check_day(DAY, path=_core_ledger(tmp_path, rows))
    assert any("BROKER_INFRA_FAILURES" in a for a in res["content_alarms"])


def test_core_below_thresholds_stays_quiet(tmp_path):
    """One-off bad ticks are routine, not walls: 10% no-data + 2 infra fails -> silent."""
    rows = ([_core_row(verdict="SKIP_NO_DATA") for _ in range(10)]
            + [_core_row(verdict="ENTER_BULL", exec={"status": "NO_PREMIUM"}) for _ in range(2)]
            + [_core_row() for _ in range(88)])
    res = elc.check_day(DAY, path=_core_ledger(tmp_path, rows))
    assert res["content_alarms"] == []
    assert elc.alarm_line(res) is None


def test_core_unarmed_diagnostic_rows_never_count(tmp_path):
    """Armed-only discipline (2026-08-01) extends to the content pass: 200 unarmed
    SKIP_NO_DATA diagnostic rows must not alarm a healthy armed day."""
    rows = ([_core_row(armed=False, verdict="SKIP_NO_DATA") for _ in range(200)]
            + [_core_row() for _ in range(100)])
    res = elc.check_day(DAY, path=_core_ledger(tmp_path, rows))
    assert res["ticks"] == 100
    assert res["content_alarms"] == []


def test_core_did_not_run_shape_unchanged(tmp_path):
    """The pre-existing outage contract is byte-compatible: DID_NOT_RUN, exit-map intact."""
    res = elc.check_day(DAY, path=_core_ledger(tmp_path, []))
    assert res["status"] == elc.STATUS_DID_NOT_RUN
    assert elc._EXIT[res["status"]] == 3


# ---------------------------------------------------------------------------------------
# fleet_liveness_check: per-arm content alarms
# ---------------------------------------------------------------------------------------
def test_fleet_healthy_day_has_zero_content_alarms(tmp_path):
    acc = _accounts(tmp_path)
    for a in ("safe-3", "risky-1", "risky-3"):
        _fleet_ledger(tmp_path, a, [_fleet_row(arm_id=a) for _ in range(50)])
    res = flc.check_day(DAY, accounts_path=acc, fleet_dir=tmp_path)
    assert res["status"] == flc.STATUS_ALL_TICKED
    assert res["content_alarms"] == []
    assert flc.alarm_line(res) is None


def test_fleet_floor_wall_alarms_the_2026_08_03_shape(tmp_path):
    """THE exhibit: 35 SKIP_MIN_PREMIUM_FLOOR rows on one arm (today's real risky-1 count)
    must alarm as FLOOR_WALL while status stays ALL_TICKED. This count is the standing
    baseline the ATM-TIER-EXTENSION prereg watches."""
    acc = _accounts(tmp_path)
    _fleet_ledger(tmp_path, "safe-3", [_fleet_row(arm_id="safe-3") for _ in range(50)])
    _fleet_ledger(tmp_path, "risky-3", [_fleet_row(arm_id="risky-3") for _ in range(50)])
    _fleet_ledger(tmp_path, "risky-1",
                  [_fleet_row(arm_id="risky-1", risk_code="SKIP_MIN_PREMIUM_FLOOR",
                              reason="premium 0.11 < min_entry_premium floor 0.3")
                   for _ in range(35)]
                  + [_fleet_row(arm_id="risky-1") for _ in range(300)])
    res = flc.check_day(DAY, accounts_path=acc, fleet_dir=tmp_path)
    assert res["status"] == flc.STATUS_ALL_TICKED, "fail-open: a floor wall is not an outage"
    assert any("risky-1: FLOOR_WALL 35" in a for a in res["content_alarms"])
    assert "CONTENT ALARMS" in res["reason"]
    line = flc.alarm_line(res)
    assert line is not None and "FLOOR_WALL" in line
    assert res["arm_content"]["risky-1"]["floor_blocks"] == 35


def test_fleet_stale_signal_wall_alarms(tmp_path):
    """A fleet blind to its own brain (stale/missing shared-signal most of the day)."""
    acc = _accounts(tmp_path, arm_ids=("risky-1",))
    _fleet_ledger(tmp_path, "risky-1",
                  [_fleet_row(signal_status="signal_stale_900s") for _ in range(40)]
                  + [_fleet_row() for _ in range(60)])
    res = flc.check_day(DAY, accounts_path=acc, fleet_dir=tmp_path)
    assert any("SIGNAL_STALE_WALL" in a for a in res["content_alarms"])


def test_fleet_error_rows_alarm(tmp_path):
    acc = _accounts(tmp_path, arm_ids=("safe-3",))
    _fleet_ledger(tmp_path, "safe-3",
                  [_fleet_row(arm_id="safe-3", action="ERROR",
                              reason="no creds in secrets.json") for _ in range(3)]
                  + [_fleet_row(arm_id="safe-3") for _ in range(50)])
    res = flc.check_day(DAY, accounts_path=acc, fleet_dir=tmp_path)
    assert any("ARM_ERRORS" in a for a in res["content_alarms"])


def test_fleet_rescue_denied_is_counted_but_never_alarms(tmp_path):
    """Post-L246-fix visibility: denied floor-rescues are tallied (glanceable) but are a
    working-as-designed refusal, never an alarm."""
    acc = _accounts(tmp_path, arm_ids=("risky-1",))
    _fleet_ledger(tmp_path, "risky-1",
                  [_fleet_row(risk_code="SKIP_MIN_PREMIUM_FLOOR",
                              reason="premium 0.11 < floor 0.3; FULL_SEND floor_rescue "
                                     "denied: NOT_FLAT") for _ in range(2)]
                  + [_fleet_row() for _ in range(60)])
    res = flc.check_day(DAY, accounts_path=acc, fleet_dir=tmp_path)
    assert res["arm_content"]["risky-1"]["rescue_denied"] == 2
    assert not any("rescue" in a.lower() for a in res["content_alarms"])


def test_fleet_below_thresholds_stays_quiet(tmp_path):
    acc = _accounts(tmp_path, arm_ids=("risky-3",))
    _fleet_ledger(tmp_path, "risky-3",
                  [_fleet_row(arm_id="risky-3", risk_code="SKIP_MIN_PREMIUM_FLOOR")
                   for _ in range(9)]  # 9 < FLOOR_BLOCK_ALARM_MIN
                  + [_fleet_row(arm_id="risky-3", signal_status="signal_stale_500s")
                     for _ in range(5)]  # 5/64 < 30%
                  + [_fleet_row(arm_id="risky-3") for _ in range(50)])
    res = flc.check_day(DAY, accounts_path=acc, fleet_dir=tmp_path)
    assert res["content_alarms"] == []


def test_fleet_silent_arm_semantics_unchanged(tmp_path):
    """The pre-existing SOME_SILENT contract is intact -- and content alarms from the arms
    that DID tick still ride the payload."""
    acc = _accounts(tmp_path, arm_ids=("safe-3", "risky-1"))
    _fleet_ledger(tmp_path, "safe-3", [])  # ticked never
    _fleet_ledger(tmp_path, "risky-1",
                  [_fleet_row(risk_code="SKIP_MIN_PREMIUM_FLOOR") for _ in range(12)])
    res = flc.check_day(DAY, accounts_path=acc, fleet_dir=tmp_path)
    assert res["status"] == flc.STATUS_SOME_SILENT
    assert res["silent_arms"] == ["safe-3"]
    assert any("FLOOR_WALL" in a for a in res["content_alarms"])
