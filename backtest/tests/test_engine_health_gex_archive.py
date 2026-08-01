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
    -- never RED on a clean checkout where Gamma_CboeOiBank has been firing. Was RED
    (2 unexplained interior gaps 2026-07-24/07-30) until journal/gex-archive/known-gaps.json
    was filed 2026-08-01 -- this pins the live fix, not just a synthetic case."""
    chk = engine_health.check_gex_archive(_ET)
    assert chk["status"] in ("GREEN", "YELLOW")
    assert chk["critical"] is False


# --------------------------------------------------------------------------- #
# expect_today time-gating (2026-08-01, G-ARCHIVE-GAP-LOUD): a same-day miss must
# surface THAT EVENING, not sit silent until a later interior-gap scan happens to run.
# --------------------------------------------------------------------------- #

def test_expect_today_false_before_capture_window(monkeypatch):
    """Before 16:00 ET, today is not yet owed -- expect_today must stay False so a
    not-yet-captured today is never falsely flagged."""
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return {"status": "GREEN", "reason": "x", "days_accrued": 1, "latest_session": "2026-08-01"}

    import backtest.tools.gex_archive_health as gah
    monkeypatch.setattr(gah, "assess_archive_continuity", _spy)
    et_before = datetime(2026, 8, 3, 15, 59, 0)  # Monday, before the 15:55(ET)->16:00 gate
    engine_health.check_gex_archive(et_before)
    assert captured["expect_today"] is False


def test_expect_today_true_after_capture_window_on_a_weekday(monkeypatch):
    """From 16:00 ET on a weekday, today's capture IS owed -- expect_today must flip True
    so a same-day miss shows up in engine-health.json that evening (the fix for the
    2026-07-24 / 2026-07-30 gaps sitting undiscovered for days)."""
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return {"status": "GREEN", "reason": "x", "days_accrued": 1, "latest_session": "2026-08-01"}

    import backtest.tools.gex_archive_health as gah
    monkeypatch.setattr(gah, "assess_archive_continuity", _spy)
    et_after = datetime(2026, 8, 3, 16, 0, 0)  # Monday, right at the gate
    engine_health.check_gex_archive(et_after)
    assert captured["expect_today"] is True


def test_expect_today_false_on_weekend_even_after_16_00(monkeypatch):
    """The time gate alone must not flag a weekend as owed -- weekday check comes first."""
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return {"status": "GREEN", "reason": "x", "days_accrued": 1, "latest_session": "2026-07-31"}

    import backtest.tools.gex_archive_health as gah
    monkeypatch.setattr(gah, "assess_archive_continuity", _spy)
    et_weekend = datetime(2026, 8, 1, 20, 0, 0)  # Saturday evening
    engine_health.check_gex_archive(et_weekend)
    assert captured["expect_today"] is False


def test_bite_a_same_day_miss_now_surfaces_same_evening(monkeypatch):
    """RED-PROOF / non-vacuous: with the old hardcoded expect_today=False, a fetch that
    silently never ran today would read GREEN (today just isn't 'owed' yet, forever). With
    the time-gated fix, past 16:00 ET a real assess_archive_continuity call (not mocked)
    correctly reads the miss the SAME evening once expect_today flips True -- proven here by
    asserting the two gate states actually produce DIFFERENT expect_today values reaching
    the real (unmocked) continuity function, i.e. the fix is not a no-op."""
    import backtest.tools.gex_archive_health as gah
    seen = []
    real = gah.assess_archive_continuity

    def _wrap(**kw):
        seen.append(kw.get("expect_today"))
        return real(**kw)

    monkeypatch.setattr(gah, "assess_archive_continuity", _wrap)
    engine_health.check_gex_archive(datetime(2026, 8, 3, 15, 0, 0))  # pre-window
    engine_health.check_gex_archive(datetime(2026, 8, 3, 16, 30, 0))  # post-window
    assert seen == [False, True], "the same-day gate must actually change behavior, not be dead code"
