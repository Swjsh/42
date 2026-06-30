"""Guard for the intraday-level-feed freshness check wired into the engine-health beacon
(2026-06-29 conductor).

The level feed (refresh_levels_intraday.py / Gamma_LevelRefresh, ~every 5 min during RTH)
is the ONLY shippable win of the 06-29 missed-setups mission -- it rewrites key-levels.json
.as_of so the engine isn't blind to intraday structure (the frozen-levels root cause). The
fix is purely PRODUCER-side: `_read_levels()` rejects NO stale timestamp, so if the refresh
task silently dies the engine reads FROZEN levels again, undetected (C7 silent-rot).
`check_level_feed` surfaces it.

Pins the load-bearing SAFETY invariant: the check is NON-CRITICAL, so a stale level feed
degrades the verdict to YELLOW but can NEVER trade-halt nor RED the critical engine verdict
-- while a genuine RTH stall still returns RED *status* so the transition-only alerter pings
J once. Bite-tested non-vacuous (the staleness threshold actually discriminates).
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

# --- import setup/scripts/engine_health.py by path (not a package) ---
_REPO = Path(__file__).resolve().parents[2]
_EH_PATH = _REPO / "setup" / "scripts" / "engine_health.py"
_spec = importlib.util.spec_from_file_location("engine_health_levelfeed_under_test", _EH_PATH)
engine_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine_health)

# 2026-06-29 is a Monday. RTH past the open warmup; and a market-closed time.
_ET_RTH = datetime(2026, 6, 29, 11, 0, 0)      # 11:00 ET, minutes_since_open=90 > warmup
_ET_WARMUP = datetime(2026, 6, 29, 9, 35, 0)   # 09:35 ET, minutes_since_open=5 < warmup
_ET_CLOSED = datetime(2026, 6, 29, 3, 48, 0)   # pre-open, market closed


def _point_state(monkeypatch, tmp_path: Path, as_of):
    """Repoint engine_health.STATE at a tmp dir holding a key-levels.json with `as_of`."""
    monkeypatch.setattr(engine_health, "STATE", tmp_path)
    if as_of is not None:
        (tmp_path / "key-levels.json").write_text(
            json.dumps({"as_of": as_of, "levels": []}), encoding="utf-8")


def _as_of(et: datetime) -> str:
    """The exact format refresh_levels_intraday writes (naive ET + literal -04:00)."""
    return et.strftime("%Y-%m-%dT%H:%M:%S-04:00")


# --------------------------------------------------------------------------- #
# The safety invariant: a GREEN/closed feed is critical-True liveness, but a
# STALE feed degrades NON-CRITICAL (RED status, critical=False) -- never halts.
# --------------------------------------------------------------------------- #

def test_fresh_feed_during_rth_is_green(monkeypatch, tmp_path):
    _point_state(monkeypatch, tmp_path, _as_of(datetime(2026, 6, 29, 10, 55, 0)))  # 5m old
    chk = engine_health.check_level_feed(True, _ET_RTH)
    assert chk["name"] == "level_feed"
    assert chk["status"] == "GREEN"


def test_stale_feed_during_rth_is_red_but_noncritical(monkeypatch, tmp_path):
    """The load-bearing case: feed 40m stale during RTH -> RED *status* (alertable) but
    critical=False (a frozen level feed degrades level-awareness, never trade-halts)."""
    _point_state(monkeypatch, tmp_path, _as_of(datetime(2026, 6, 29, 10, 20, 0)))  # 40m old
    chk = engine_health.check_level_feed(True, _ET_RTH)
    assert chk["status"] == "RED"
    assert chk["critical"] is False, "a stale level feed must NEVER be a critical trade-halt"
    assert "FROZEN" in chk["detail"]


def test_red_level_feed_does_not_red_the_critical_verdict():
    """A non-critical level_feed RED in fuse() must degrade to YELLOW, not RED -- else it
    would gate conductor backpressure + falsely alarm as a live-engine death."""
    critical_greens = [
        engine_health._chk("heartbeat_safe", "GREEN", "ok", critical=True),
        engine_health._chk("heartbeat_bold", "GREEN", "ok", critical=True),
    ]
    red_feed = engine_health._chk("level_feed", "RED", "LEVEL FEED STALE", critical=False)
    verdict, reds = engine_health.fuse(critical_greens + [red_feed])
    assert verdict == "YELLOW", "non-critical level_feed RED must degrade to YELLOW, not RED"
    assert any("level_feed" in r for r in reds)


def test_red_level_feed_is_alertable():
    checks = [
        engine_health._chk("heartbeat_safe", "GREEN", "ok", critical=True),
        engine_health._chk("level_feed", "RED", "stale", critical=False),
    ]
    red_checks = sorted(c["name"] for c in checks if c["status"] == "RED")
    assert "level_feed" in red_checks


def test_build_report_includes_level_feed():
    report = engine_health.build_report()
    names = [c["name"] for c in report["checks"]]
    assert "level_feed" in names
    feed = next(c for c in report["checks"] if c["name"] == "level_feed")
    # NON-CRITICAL whenever it is RED (it is critical-True only on a GREEN liveness read).
    if feed["status"] == "RED":
        assert feed["critical"] is False


# --------------------------------------------------------------------------- #
# Quiet windows: market-closed + open-warmup never cry wolf.
# --------------------------------------------------------------------------- #

def test_market_closed_stale_is_green(monkeypatch, tmp_path):
    """Refresh only runs during RTH -- a stale as_of overnight is EXPECTED, not a fault."""
    _point_state(monkeypatch, tmp_path, _as_of(datetime(2026, 6, 26, 15, 50, 0)))  # last Fri
    chk = engine_health.check_level_feed(False, _ET_CLOSED)
    assert chk["status"] == "GREEN"
    assert "market closed" in chk["detail"]


def test_open_warmup_stale_is_green(monkeypatch, tmp_path):
    """In the first minutes after the open the first refresh is still pending -- no cry-wolf."""
    _point_state(monkeypatch, tmp_path, _as_of(datetime(2026, 6, 29, 8, 40, 0)))  # premarket draw
    chk = engine_health.check_level_feed(True, _ET_WARMUP)
    assert chk["status"] == "GREEN"


# --------------------------------------------------------------------------- #
# Fail-open: missing / garbled / unparseable -> benign YELLOW, never a crash.
# --------------------------------------------------------------------------- #

def test_missing_file_is_benign_yellow(monkeypatch, tmp_path):
    _point_state(monkeypatch, tmp_path, None)  # no key-levels.json written
    chk = engine_health.check_level_feed(True, _ET_RTH)
    assert chk["status"] == "YELLOW"
    assert chk["critical"] is False  # benign -> no ping


def test_no_as_of_is_benign_yellow(monkeypatch, tmp_path):
    monkeypatch.setattr(engine_health, "STATE", tmp_path)
    (tmp_path / "key-levels.json").write_text(json.dumps({"levels": []}), encoding="utf-8")
    chk = engine_health.check_level_feed(True, _ET_RTH)
    assert chk["status"] == "YELLOW"


def test_unparseable_as_of_is_benign_yellow(monkeypatch, tmp_path):
    _point_state(monkeypatch, tmp_path, "not-a-timestamp-at-all")
    chk = engine_health.check_level_feed(True, _ET_RTH)
    assert chk["status"] == "YELLOW"


# --------------------------------------------------------------------------- #
# BITE: prove the staleness threshold is non-vacuous.
# --------------------------------------------------------------------------- #

def test_bite_neutering_threshold_flips_stale_to_green(monkeypatch, tmp_path):
    """If LEVEL_FEED_STALE_MIN were huge, the 40m-stale RTH case would read GREEN -- proving
    the threshold (not some other branch) is what produces the RED."""
    _point_state(monkeypatch, tmp_path, _as_of(datetime(2026, 6, 29, 10, 20, 0)))  # 40m old
    assert engine_health.check_level_feed(True, _ET_RTH)["status"] == "RED"
    monkeypatch.setattr(engine_health, "LEVEL_FEED_STALE_MIN", 10_000)
    assert engine_health.check_level_feed(True, _ET_RTH)["status"] == "GREEN"
