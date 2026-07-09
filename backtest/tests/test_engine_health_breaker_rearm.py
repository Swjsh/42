"""Guard for the breaker re-arm freshness check wired into the engine-health beacon
(2026-07-09 root-cause fix).

Incident: both circuit-breaker.json files were still stamped 2026-07-08 (last_reset /
session_id) while the engine traded 2026-07-09, because the premarket LLM run -- the
historical only writer of a fresh starting_equity_today/equity_start_of_day -- failed both
attempts with "API Error: Unable to connect to API (ConnectionRefused)" (its
claude-code-router dependency at 127.0.0.1:3456 had died overnight with no auto-restart).
check_killswitch only ever asked ".tripped?" so it read GREEN throughout ("armed, not
tripped" says nothing about whether the SoD anchor is fresh). check_breaker_rearm closes
that observability gap; daily_loss_guard.rearm() closes the write-side gap independently
(LLM/CCR-independent, direct Alpaca REST) -- this test file guards the READ side only.

Pins the load-bearing SAFETY invariant: the check is NON-CRITICAL (mirrors level_feed /
gex_archive / dispatch_health) -- a stale re-arm degrades the verdict to YELLOW but can
NEVER trade-halt nor RED the critical engine verdict, while a genuine RTH staleness still
returns RED *status* so the transition-only alerter pings J once. Bite-tested non-vacuous
(the date-equality check actually discriminates) and fail-open on every malformed-input
path.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

# --- import setup/scripts/engine_health.py by path (not a package) ---
_REPO = Path(__file__).resolve().parents[2]
_EH_PATH = _REPO / "setup" / "scripts" / "engine_health.py"
_spec = importlib.util.spec_from_file_location("engine_health_breakerrearm_under_test", _EH_PATH)
engine_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine_health)

# 2026-07-09 is a Thursday. RTH past the open warmup; and a market-closed time.
_ET_RTH = datetime(2026, 7, 9, 13, 0, 0)       # 13:00 ET -- the actual incident discovery time
_ET_CLOSED = datetime(2026, 7, 9, 3, 48, 0)    # pre-open, market closed
_TODAY = "2026-07-09"
_YESTERDAY = "2026-07-08"


def _write_breaker(tmp_path: Path, name: str, payload) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# The safety invariant: a fresh/closed breaker is GREEN critical=False, but a
# STALE re-arm degrades NON-CRITICAL (RED status, critical=False) -- never halts.
# --------------------------------------------------------------------------- #

def test_today_dated_safe_breaker_is_green(tmp_path):
    p = _write_breaker(tmp_path, "cb.json", {"last_reset": f"{_TODAY}T08:31:00-04:00", "tripped": False})
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", p, "last_reset", True, _ET_RTH)
    assert chk["name"] == "breaker_rearm_safe"
    assert chk["status"] == "GREEN"
    assert chk["critical"] is False


def test_today_dated_bold_breaker_is_green(tmp_path):
    p = _write_breaker(tmp_path, "cb.json", {"session_id": _TODAY, "tripped": False})
    chk = engine_health.check_breaker_rearm("breaker_rearm_bold", p, "session_id", True, _ET_RTH)
    assert chk["status"] == "GREEN"


def test_stale_safe_breaker_during_rth_is_red_but_noncritical(tmp_path):
    """The load-bearing case: this is EXACTLY the 2026-07-09 incident fixture --
    last_reset dated 2026-07-08 while the engine trades 2026-07-09 -- must surface RED
    *status* (alertable) but critical=False (a stale re-arm never trade-halts)."""
    p = _write_breaker(tmp_path, "cb.json", {
        "last_reset": "2026-07-08T08:31:00-04:00", "tripped": False,
        "starting_equity_today": 1512.83, "current_equity": 1512.83,
    })
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", p, "last_reset", True, _ET_RTH)
    assert chk["status"] == "RED"
    assert chk["critical"] is False, "a stale re-arm must NEVER be a critical trade-halt"
    assert "STALE RE-ARM" in chk["detail"]
    assert _YESTERDAY in chk["detail"] and _TODAY in chk["detail"]


def test_stale_bold_breaker_during_rth_is_red_but_noncritical(tmp_path):
    """Cross-schema check: bold uses session_id (bare date), not last_reset."""
    p = _write_breaker(tmp_path, "cb.json", {"session_id": "2026-07-08", "tripped": False})
    chk = engine_health.check_breaker_rearm("breaker_rearm_bold", p, "session_id", True, _ET_RTH)
    assert chk["status"] == "RED"
    assert chk["critical"] is False


def test_red_breaker_rearm_does_not_red_the_critical_verdict():
    """A non-critical breaker_rearm RED in fuse() must degrade to YELLOW, not RED -- else a
    stale re-arm would falsely alarm as a live-engine death / gate conductor backpressure."""
    critical_greens = [
        engine_health._chk("heartbeat_safe", "GREEN", "ok", critical=True),
        engine_health._chk("heartbeat_bold", "GREEN", "ok", critical=True),
        engine_health._chk("killswitch_safe", "GREEN", "armed, not tripped", critical=True),
    ]
    red_rearm = engine_health._chk("breaker_rearm_safe", "RED", "STALE RE-ARM", critical=False)
    verdict, reds = engine_health.fuse(critical_greens + [red_rearm])
    assert verdict == "YELLOW", "non-critical breaker_rearm RED must degrade to YELLOW, not RED"
    assert any("breaker_rearm_safe" in r for r in reds)


def test_red_breaker_rearm_is_alertable():
    checks = [
        engine_health._chk("heartbeat_safe", "GREEN", "ok", critical=True),
        engine_health._chk("breaker_rearm_safe", "RED", "stale", critical=False),
    ]
    red_checks = sorted(c["name"] for c in checks if c["status"] == "RED")
    assert "breaker_rearm_safe" in red_checks


def test_build_report_includes_both_breaker_rearm_checks():
    report = engine_health.build_report()
    names = [c["name"] for c in report["checks"]]
    assert "breaker_rearm_safe" in names
    assert "breaker_rearm_bold" in names
    for cname in ("breaker_rearm_safe", "breaker_rearm_bold"):
        chk = next(c for c in report["checks"] if c["name"] == cname)
        # NON-CRITICAL always -- never gates the top-level verdict to RED by itself.
        if chk["status"] == "RED":
            assert chk["critical"] is False


# --------------------------------------------------------------------------- #
# Quiet window: market-closed never cries wolf even on a genuinely stale date.
# --------------------------------------------------------------------------- #

def test_market_closed_stale_is_green(tmp_path):
    p = _write_breaker(tmp_path, "cb.json", {"last_reset": "2026-07-01T08:31:00-04:00"})
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", p, "last_reset", False, _ET_CLOSED)
    assert chk["status"] == "GREEN"
    assert "market closed" in chk["detail"]


# --------------------------------------------------------------------------- #
# Fail-open: missing / garbled / non-dict / missing-date-field -> benign YELLOW or a
# defensible RED-but-noncritical, never a crash.
# --------------------------------------------------------------------------- #

def test_missing_file_is_benign_yellow(tmp_path):
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", tmp_path / "nope.json",
                                             "last_reset", True, _ET_RTH)
    assert chk["status"] == "YELLOW"
    assert chk["critical"] is False


def test_garbled_json_is_benign_yellow(tmp_path):
    p = tmp_path / "cb.json"
    p.write_text("{not valid json", encoding="utf-8")
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", p, "last_reset", True, _ET_RTH)
    assert chk["status"] == "YELLOW"
    assert chk["critical"] is False


def test_non_dict_payload_is_benign_yellow(tmp_path):
    p = tmp_path / "cb.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", p, "last_reset", True, _ET_RTH)
    assert chk["status"] == "YELLOW"
    assert chk["critical"] is False


def test_missing_date_field_is_red_not_a_crash(tmp_path):
    """No date_field at all (never armed) is worth surfacing (RED) but must still never
    crash the beacon nor go critical."""
    p = _write_breaker(tmp_path, "cb.json", {"tripped": False})
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", p, "last_reset", True, _ET_RTH)
    assert chk["status"] == "RED"
    assert chk["critical"] is False
    assert "NOT RE-ARMED" in chk["detail"]


# --------------------------------------------------------------------------- #
# BITE: prove the date-equality comparison is non-vacuous (a real mismatch is what
# produces RED, not some unconditional branch).
# --------------------------------------------------------------------------- #

def test_bite_today_dated_flips_stale_case_to_green(tmp_path):
    """Same fixture shape as the stale-RED case, except last_reset IS today -- proves the
    comparison (not some other branch) is what produces the RED/GREEN split."""
    p = _write_breaker(tmp_path, "cb.json", {"last_reset": f"{_TODAY}T08:31:00-04:00"})
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", p, "last_reset", True, _ET_RTH)
    assert chk["status"] == "GREEN"

    p2 = _write_breaker(tmp_path, "cb2.json", {"last_reset": f"{_YESTERDAY}T08:31:00-04:00"})
    chk2 = engine_health.check_breaker_rearm("breaker_rearm_safe", p2, "last_reset", True, _ET_RTH)
    assert chk2["status"] == "RED"


def test_bite_exception_path_is_fail_open_not_a_crash(tmp_path, monkeypatch):
    """Force _read_json to raise inside the try/except -- the check must still return a
    benign dict, never propagate, proving the fail-open wrapper actually catches something."""
    def boom(_path):
        raise RuntimeError("simulated read explosion")
    monkeypatch.setattr(engine_health, "_read_json", boom)
    chk = engine_health.check_breaker_rearm("breaker_rearm_safe", tmp_path / "cb.json",
                                             "last_reset", True, _ET_RTH)
    assert chk["status"] == "YELLOW"
    assert chk["critical"] is False
    assert "breaker-rearm check failed" in chk["detail"]
