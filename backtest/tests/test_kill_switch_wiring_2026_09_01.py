"""test_kill_switch_wiring_2026_09_01.py -- guards for the W2 kill-switch 3-way
filename mismatch fix (audit: entry gate reads (STATE/'kill-switch') bare-name with
ZERO writers; eod_flatten.py._escalate_inner wrote kill-switch-{arm}.json that NOTHING
read; the LLM aggressive flattener wrote automation/state/kill-switch.json that NOTHING
read; the only ENFORCED halt was circuit-breaker.json 'tripped', which daily_loss_guard.
rearm() unconditionally re-armed every premarket).

CONTRACTS PINNED:
  1. ESCALATE_TRIPS_CB   -- eod_flatten.py._escalate_inner trips the account's OWN
                            circuit-breaker.json (the file heartbeat_core.py's entry
                            gate actually reads) for the two CORE arms, in addition to
                            the kill-switch-{arm}.json file it already wrote.
  2. ESCALATE_SKIPS_FLEET -- a fleet arm (no circuit-breaker.json on the live gate
                            path) is skipped for the breaker write, never raises.
  3. ESCALATION_FLAGS_RED -- engine_health.check_escalation_flags goes RED on either a
                            kill-switch*.json file OR an escalation_unresolved=true
                            breaker, and GREEN otherwise.
  4. REARM_REFUSES        -- daily_loss_guard.rearm() refuses to clear tripped when
                            escalation_unresolved is true, but still refreshes equity.
  5. REARM_STILL_WORKS    -- the ordinary (no escalation) rearm path is unchanged.
  6. PROMPTS_NO_BARE_KS   -- neither eod-flatten prompt still tells the LLM to create
                            the bare automation/state/kill-switch file on an MCP outage.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "setup" / "scripts"
_FLEET = REPO / "automation" / "state" / "fleet"
for _p in (str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


ef = _load("kswiring_eod_flatten", _SCRIPTS / "eod_flatten.py")
eh = _load("kswiring_engine_health", _SCRIPTS / "engine_health.py")
dlg = _load("kswiring_daily_loss_guard", _SCRIPTS / "daily_loss_guard.py")


# ===========================================================================
# 1 + 2. eod_flatten.py._escalate_inner trips the correct circuit-breaker
# ===========================================================================

def _seed_breaker(path: Path, **overrides) -> dict:
    base = {
        "tripped": False,
        "tripped_reason": None,
        "tripped_at": None,
        "starting_equity_today": 5000.0,
        "current_equity": 4800.0,
        "_untouched_marker": "must-survive",
    }
    base.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return base


def test_escalate_trips_safe_core_circuit_breaker(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "_REPO", tmp_path)
    (tmp_path / "automation" / "state").mkdir(parents=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True)
    cb_path = tmp_path / "automation" / "state" / "circuit-breaker.json"
    _seed_breaker(cb_path)

    ef._escalate_inner("safe-2", 2, ["broker timeout"], tmp_path / "flat.log")

    data = json.loads(cb_path.read_text(encoding="utf-8"))
    assert data["tripped"] is True, "core arm escalation must trip the LIVE-GATE breaker"
    assert "EOD_FLATTEN_ESCALATION" in data["tripped_reason"]
    assert data["escalation_unresolved"] is True
    assert data["tripped_at"], "tripped_at must be stamped"
    # every pre-existing field survives (no clobbering).
    assert data["_untouched_marker"] == "must-survive"
    assert data["starting_equity_today"] == 5000.0
    # the kill-switch-{arm}.json file is STILL written (unread today, harmless).
    assert (tmp_path / "automation" / "state" / "kill-switch-safe-2.json").exists()


def test_escalate_trips_bold_core_circuit_breaker_on_its_own_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "_REPO", tmp_path)
    (tmp_path / "automation" / "state" / "aggressive").mkdir(parents=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True)
    cb_path = tmp_path / "automation" / "state" / "aggressive" / "circuit-breaker.json"
    _seed_breaker(cb_path, trip_reason=None, tripped_at_et=None,
                  equity_start_of_day=5000.0, equity_current=4500.0)

    ef._escalate_inner("bold-2", 1, ["x"], tmp_path / "flat.log")

    data = json.loads(cb_path.read_text(encoding="utf-8"))
    assert data["tripped"] is True
    # BOLD schema uses trip_reason / tripped_at_et, NOT tripped_reason / tripped_at
    # (the C9 symmetry trap -- see daily_loss_guard.py ACCOUNTS mapping).
    assert "EOD_FLATTEN_ESCALATION" in data["trip_reason"]
    assert data["tripped_at_et"]
    assert data["escalation_unresolved"] is True
    assert data["_untouched_marker"] == "must-survive"


def test_escalate_fleet_arm_never_writes_a_core_breaker(tmp_path, monkeypatch):
    """Fleet arms (safe-3/risky-1/risky-3) have no circuit-breaker.json on the live gate
    path -- fleet_executor.py's halt is FROZEN/out of scope. Must never raise, and must
    never invent a circuit-breaker.json that nothing else expects."""
    monkeypatch.setattr(ef, "_REPO", tmp_path)
    (tmp_path / "automation" / "state").mkdir(parents=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True)

    ef._escalate_inner("safe-3", 1, ["x"], tmp_path / "flat.log")  # must not raise

    assert not (tmp_path / "automation" / "state" / "circuit-breaker.json").exists()
    assert (tmp_path / "automation" / "state" / "kill-switch-safe-3.json").exists()


def test_escalate_still_never_raises_when_breaker_dir_unwritable(tmp_path, monkeypatch):
    """Fail-soft contract preserved: a circuit-breaker write failure must not abort the
    sweep (mirrors the existing kill-switch-file fail-soft guard)."""
    monkeypatch.setattr(ef, "_REPO", tmp_path / "does" / "not" / "exist")
    ef._escalate("bold-2", 3, ["x"], tmp_path / "nowhere" / "flat.log")  # must not raise


# ===========================================================================
# 3. engine_health.check_escalation_flags
# ===========================================================================

def test_escalation_flags_green_when_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(eh, "STATE", tmp_path)
    monkeypatch.setattr(eh, "AGG", tmp_path / "aggressive")
    (tmp_path / "aggressive").mkdir(parents=True)
    result = eh.check_escalation_flags("escalation_flags")
    assert result["status"] == "GREEN"
    assert result["critical"] is True


def test_escalation_flags_red_on_killswitch_file(tmp_path, monkeypatch):
    monkeypatch.setattr(eh, "STATE", tmp_path)
    monkeypatch.setattr(eh, "AGG", tmp_path / "aggressive")
    (tmp_path / "aggressive").mkdir(parents=True)
    (tmp_path / "kill-switch-safe-3.json").write_text("{}", encoding="utf-8")

    result = eh.check_escalation_flags("escalation_flags")
    assert result["status"] == "RED"
    assert result["critical"] is True
    assert "kill-switch-safe-3.json" in result["detail"]


def test_escalation_flags_red_on_unresolved_breaker(tmp_path, monkeypatch):
    monkeypatch.setattr(eh, "STATE", tmp_path)
    monkeypatch.setattr(eh, "AGG", tmp_path / "aggressive")
    (tmp_path / "aggressive").mkdir(parents=True)
    (tmp_path / "circuit-breaker.json").write_text(
        json.dumps({"tripped": True, "escalation_unresolved": True}), encoding="utf-8")

    result = eh.check_escalation_flags("escalation_flags")
    assert result["status"] == "RED"
    assert "safe_circuit_breaker.escalation_unresolved" in result["detail"]


def test_escalation_flags_registered_in_build_report():
    """The check must actually be wired into build_report's checks list, not just
    exist as a dangling function nobody calls."""
    source = (Path(eh.__file__)).read_text(encoding="utf-8")
    assert 'check_escalation_flags("escalation_flags")' in source


# ===========================================================================
# 4 + 5. daily_loss_guard.rearm()
# ===========================================================================

def _seed_safe_breaker(path: Path, *, date: str, tripped: bool, escalation_unresolved: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "tripped": tripped,
        "tripped_at": "2026-08-31T14:00:00-04:00" if tripped else None,
        "tripped_reason": "daily_loss_30.0%_>=_30%_limit (daily_loss_guard)" if tripped else None,
        "starting_equity_today": 5000.0,
        "current_equity": 3500.0,
        "daily_loss_limit_dollars": 1500.0,
        "daily_loss_limit_pct": 0.30,
        "max_drawdown_today_dollars": 1500.0,
        "max_drawdown_today_pct": 0.30,
        "day_trades_used_5d": 1,
        "last_reset": f"{date}T08:30:00-04:00",
        "escalation_unresolved": escalation_unresolved,
    }, indent=2), encoding="utf-8")


def test_rearm_refuses_to_clear_tripped_when_escalation_unresolved(tmp_path, monkeypatch):
    cb_path = tmp_path / "circuit-breaker.json"
    _seed_safe_breaker(cb_path, date="2026-08-31", tripped=True, escalation_unresolved=True)
    monkeypatch.setitem(dlg.ACCOUNTS["safe"], "breaker", cb_path)
    monkeypatch.setattr(dlg, "_fetch_equity", lambda account: 5100.0)
    monkeypatch.setattr(dlg, "LOG_DIR", tmp_path)

    result = dlg.rearm("safe", dry_run=False)

    assert result["action"] == "REARM_REFUSED_UNRESOLVED_ESCALATION"
    assert result["escalation_unresolved"] is True
    data = json.loads(cb_path.read_text(encoding="utf-8"))
    assert data["tripped"] is True, (
        "REARM_REFUSED must leave tripped=True -- this is the exact bug the W2 audit "
        "named ('daily_loss_guard.rearm() unconditionally re-arms each premarket')"
    )
    assert data["tripped_reason"], "tripped_reason must survive, not be nulled"
    # equity STILL refreshes so run()'s stale-SoD guard doesn't itself misfire.
    assert data["starting_equity_today"] == 5100.0
    assert data["current_equity"] == 5100.0


def test_rearm_dry_run_does_not_write_when_escalation_unresolved(tmp_path, monkeypatch):
    cb_path = tmp_path / "circuit-breaker.json"
    _seed_safe_breaker(cb_path, date="2026-08-31", tripped=True, escalation_unresolved=True)
    monkeypatch.setitem(dlg.ACCOUNTS["safe"], "breaker", cb_path)
    monkeypatch.setattr(dlg, "_fetch_equity", lambda account: 5100.0)

    result = dlg.rearm("safe", dry_run=True)

    assert result["action"] == "REARM_REFUSED_UNRESOLVED_ESCALATION"
    # file on disk must be untouched by a dry run.
    data = json.loads(cb_path.read_text(encoding="utf-8"))
    assert data["starting_equity_today"] == 5000.0


def test_rearm_still_clears_tripped_when_no_escalation(tmp_path, monkeypatch):
    """Regression pin: the ordinary rearm path (no escalation_unresolved) must still
    work exactly as before -- this fix must not weaken the happy path."""
    cb_path = tmp_path / "circuit-breaker.json"
    _seed_safe_breaker(cb_path, date="2026-08-31", tripped=True, escalation_unresolved=False)
    monkeypatch.setitem(dlg.ACCOUNTS["safe"], "breaker", cb_path)
    monkeypatch.setattr(dlg, "_fetch_equity", lambda account: 5200.0)
    monkeypatch.setattr(dlg, "LOG_DIR", tmp_path)

    result = dlg.rearm("safe", dry_run=False)

    assert result["action"] == "REARMED"
    data = json.loads(cb_path.read_text(encoding="utf-8"))
    assert data["tripped"] is False
    assert data["tripped_reason"] is None
    assert data["starting_equity_today"] == 5200.0


def test_rearm_no_op_when_already_armed_today_even_with_escalation(tmp_path, monkeypatch):
    """bdate == today short-circuits BEFORE any tripped mutation -- confirms the
    escalation guard doesn't change same-day idempotency."""
    import datetime as _dt
    from et_clock import ET_TZ  # noqa: E402
    today = _dt.datetime.now(_dt.timezone.utc).astimezone(ET_TZ).strftime("%Y-%m-%d")
    cb_path = tmp_path / "circuit-breaker.json"
    _seed_safe_breaker(cb_path, date=today, tripped=True, escalation_unresolved=True)
    monkeypatch.setitem(dlg.ACCOUNTS["safe"], "breaker", cb_path)

    result = dlg.rearm("safe", dry_run=False)
    assert result["action"] == "already_armed_today"
    data = json.loads(cb_path.read_text(encoding="utf-8"))
    assert data["tripped"] is True  # untouched, as before this fix


# ===========================================================================
# 6. prompt text no longer tells the LLM to create the bare kill-switch file
#    on an MCP outage (scoped to the two eod-flatten prompts this task edited --
#    NOT a blanket ban on "kill-switch" bare mentions elsewhere, e.g. heartbeat.md's
#    unrelated TV-blindness kill-switch, which is out of scope for W2).
# ===========================================================================

_BARE_KS_ON_UNREACHABLE = re.compile(
    r"unreachable.{0,30}create.{0,40}kill-switch(?!-)", re.IGNORECASE | re.DOTALL)

_EOD_FLATTEN_PROMPTS = (
    REPO / "automation" / "prompts" / "eod-flatten.md",
    REPO / "automation" / "prompts" / "aggressive" / "eod-flatten.md",
)


@pytest.mark.parametrize("path", _EOD_FLATTEN_PROMPTS, ids=lambda p: p.name)
def test_eod_flatten_prompt_no_longer_creates_bare_killswitch(path: Path):
    text = path.read_text(encoding="utf-8")
    assert not _BARE_KS_ON_UNREACHABLE.search(text), (
        f"{path} still tells the LLM to create the bare automation/state/kill-switch "
        "file on an MCP outage -- that file has ZERO readers on the live gate path. "
        "It must check today's eod-flatten-<date>.jsonl for a Core-verified-flat result "
        "first, and escalate via the per-account circuit-breaker.json otherwise."
    )


@pytest.mark.parametrize("path", _EOD_FLATTEN_PROMPTS, ids=lambda p: p.name)
def test_eod_flatten_prompt_now_checks_core_log_first(path: Path):
    text = path.read_text(encoding="utf-8")
    assert "CORE_VERIFIED_FLAT" in text
    assert "escalation_unresolved" in text
    assert "eod-flatten-{today}.jsonl" in text


def test_no_other_prompt_gained_a_new_bare_killswitch_on_unreachable():
    """Repo-wide sanity check: the ONLY places this exact 'unreachable -> create bare
    kill-switch' phrasing could have existed were the two eod-flatten prompts fixed
    above. This does not assert anything about unrelated bare-kill-switch usages
    (TV blindness, drift escalation in premarket.md/heartbeat.md) which are out of
    scope for W2 and intentionally untouched."""
    prompts_dir = REPO / "automation" / "prompts"
    hits = []
    for p in prompts_dir.rglob("*.md"):
        if p in _EOD_FLATTEN_PROMPTS:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if _BARE_KS_ON_UNREACHABLE.search(text):
            hits.append(str(p.relative_to(REPO)))
    assert not hits, f"unexpected 'unreachable -> create bare kill-switch' phrasing in: {hits}"
