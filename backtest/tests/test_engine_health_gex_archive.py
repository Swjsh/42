"""Guard for the GEX-archive continuity check wired into the engine-health beacon
(2026-06-29 conductor).

The months-long GEX OI accrual (Gamma_CboeOiBank -> journal/gex-archive/) is the
'class'-rung data engine. `assess_archive_continuity` + its synthetic-fixture guard
already existed, but NOTHING ran the checker against the LIVE archive on a schedule --
so a silent accrual death (un-scheduled / reaped / format change) would surface months
late. `check_gex_archive` wires it into the every-minute health beacon.

This pins the load-bearing SAFETY invariant: the check is NON-CRITICAL, so a stalled
RESEARCH accrual can degrade the verdict to YELLOW but can NEVER trade-halt nor RED the
critical engine verdict -- while a genuine multi-day stall still returns RED *status* so
the transition-only alerter pings J once (the silent death surfaced). Bite-tested
non-vacuous: neutering the non-critical flag would flip the critical-verdict test RED.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

# --- import setup/scripts/engine_health.py by path (not a package) ---
_REPO = Path(__file__).resolve().parents[2]
_EH_PATH = _REPO / "setup" / "scripts" / "engine_health.py"
_spec = importlib.util.spec_from_file_location("engine_health_gex_under_test", _EH_PATH)
engine_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine_health)

_ET = datetime(2026, 6, 29, 3, 48, 0)  # naive ET, market closed


def _patch_assess(monkeypatch, result):
    """Patch the assess_archive_continuity that check_gex_archive imports lazily."""
    import backtest.tools.gex_archive_health as gah
    monkeypatch.setattr(gah, "assess_archive_continuity", lambda **kw: result)


# --------------------------------------------------------------------------- #
# The safety invariant: NON-CRITICAL, always.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", ["GREEN", "YELLOW", "RED"])
def test_gex_check_is_never_critical(monkeypatch, status):
    _patch_assess(monkeypatch, {"status": status, "reason": "x",
                                "days_accrued": 6, "latest_session": "2026-06-26"})
    chk = engine_health.check_gex_archive(_ET)
    assert chk["name"] == "gex_archive"
    assert chk["critical"] is False, "GEX accrual is research-data -- must NEVER be critical"
    assert chk["status"] == status


def test_red_gex_does_not_red_the_critical_verdict():
    """The load-bearing invariant: a stalled GEX accrual degrades to YELLOW, never RED.
    A non-critical RED in fuse() must not flip the overall verdict to RED (which would
    gate conductor backpressure + falsely alarm as a live-engine death)."""
    critical_greens = [
        engine_health._chk("heartbeat_safe", "GREEN", "ok", critical=True),
        engine_health._chk("heartbeat_bold", "GREEN", "ok", critical=True),
    ]
    red_gex = engine_health._chk("gex_archive", "RED", "accrual stalled", critical=False)
    verdict, reds = engine_health.fuse(critical_greens + [red_gex])
    assert verdict == "YELLOW", "non-critical GEX RED must degrade to YELLOW, not RED"
    assert any("gex_archive" in r for r in reds)


def test_red_gex_is_alertable():
    """A genuine stall must appear in red_checks so the transition-only alerter pings J."""
    checks = [
        engine_health._chk("heartbeat_safe", "GREEN", "ok", critical=True),
        engine_health._chk("gex_archive", "RED", "accrual stalled", critical=False),
    ]
    red_checks = sorted(c["name"] for c in checks if c["status"] == "RED")
    assert "gex_archive" in red_checks


def test_build_report_includes_gex_archive():
    report = engine_health.build_report()
    names = [c["name"] for c in report["checks"]]
    assert "gex_archive" in names
    gex = next(c for c in report["checks"] if c["name"] == "gex_archive")
    assert gex["critical"] is False


# --------------------------------------------------------------------------- #
# Fail-open: a broken checker is a benign YELLOW, never a crash, never a ping.
# --------------------------------------------------------------------------- #

def test_assess_exception_is_benign_yellow(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("archive read exploded")
    import backtest.tools.gex_archive_health as gah
    monkeypatch.setattr(gah, "assess_archive_continuity", _boom)
    chk = engine_health.check_gex_archive(_ET)
    assert chk["status"] == "YELLOW"
    assert chk["critical"] is False  # benign -> not in red_checks -> no ping


def test_unknown_status_coerced_to_yellow(monkeypatch):
    _patch_assess(monkeypatch, {"status": "PURPLE", "reason": "?",
                                "days_accrued": 0, "latest_session": None})
    chk = engine_health.check_gex_archive(_ET)
    assert chk["status"] == "YELLOW"


def test_live_archive_reads_green_or_yellow():
    """Against the real archive this fire, accrual is healthy (or at most benignly stale)
    -- never RED on a clean checkout where Gamma_CboeOiBank has been firing."""
    chk = engine_health.check_gex_archive(_ET)
    assert chk["status"] in ("GREEN", "YELLOW")
    assert chk["critical"] is False
