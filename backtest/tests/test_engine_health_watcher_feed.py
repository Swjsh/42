"""Guard for the watcher_feed critical re-arm (WATCHER-FEED-REARM-CONFIRM, 2026-06-24).

The 2026-06-22 cry-wolf downgrade set the RTH producer-dark branch of
`check_watcher_feed` to critical=False as a DELIBERATE TEMPORARY measure while the
watcher_live.py producer rebuild was in flight. After the rebuild shipped + was
confirmed (ET-gate 3e8ed79, load-fallback 57cef40, integration 2eceac1, plus full
09:30-15:55 ET coverage on 2026-06-24) the branch was re-armed to critical=True.

This pins the re-arm so a future edit cannot silently re-downgrade the producer-dark
canary -- AND pins the non-blocking semantics of the supporting cases (missing file =
YELLOW/non-critical fail-safe; quiet-when-closed = GREEN) so the canary stays both
loud-on-real-dark and quiet-overnight.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

# --- import setup/scripts/engine_health.py by path (not a package) ---
_REPO = Path(__file__).resolve().parents[2]
_EH_PATH = _REPO / "setup" / "scripts" / "engine_health.py"
_spec = importlib.util.spec_from_file_location("engine_health_under_test", _EH_PATH)
engine_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine_health)


def _write_obs(state_dir: Path, bar_date_et: str) -> None:
    """Write a minimal watcher-observations.jsonl whose newest row carries
    bar_timestamp_et on the given date."""
    line = (
        '{"observed_at": "x", "bar_timestamp_et": "%sT15:45:00", '
        '"watcher_name": "t", "setup_name": "T"}\n' % bar_date_et
    )
    (state_dir / "watcher-observations.jsonl").write_text(line, encoding="utf-8")


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_health, "STATE", tmp_path)
    return tmp_path


# === THE re-arm guard: producer-dark during RTH must be critical=True ===
def test_producer_dark_during_rth_is_critical_true(state_dir):
    """RE-ARMED 2026-06-24: a dark producer during RTH gates the overall verdict RED.
    A regression back to critical=False is the cry-wolf-era downgrade returning."""
    _write_obs(state_dir, "2026-06-23")  # yesterday's bar = producer dark today
    et = datetime(2026, 6, 24, 11, 0, 0)
    chk = engine_health.check_watcher_feed(market_open=True, et=et)
    assert chk["status"] == "RED"
    assert chk["critical"] is True, "producer-dark RTH must be critical (re-arm regressed)"
    assert "PRODUCER DARK" in chk["detail"]


def test_producing_today_during_rth_is_green_and_critical(state_dir):
    _write_obs(state_dir, "2026-06-24")
    et = datetime(2026, 6, 24, 11, 0, 0)
    chk = engine_health.check_watcher_feed(market_open=True, et=et)
    assert chk["status"] == "GREEN"
    assert chk["critical"] is True


def test_quiet_when_market_closed_is_green(state_dir):
    """Overnight quiet must read GREEN (no crying wolf when the market is closed)."""
    _write_obs(state_dir, "2026-06-23")
    et = datetime(2026, 6, 24, 19, 0, 0)
    chk = engine_health.check_watcher_feed(market_open=False, et=et)
    assert chk["status"] == "GREEN"
    assert chk["critical"] is True


def test_missing_file_is_yellow_non_critical_failsafe(state_dir):
    """A missing state file is a fail-safe YELLOW, never a crash or critical RED."""
    et = datetime(2026, 6, 24, 11, 0, 0)
    chk = engine_health.check_watcher_feed(market_open=True, et=et)
    assert chk["status"] == "YELLOW"
    assert chk["critical"] is False
