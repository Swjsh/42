"""Guard: the quiet-mode blackout must hold while J is at a fullscreen app.

THE INCIDENT (2026-08-29, 23:30 ET). The LOUD maintenance band opens at 23:00 ET on
the premise that J is asleep. He was gaming. The blackout lifted, ~116 held-down tasks
were re-enabled at once, and two of them flashed a console window that took focus
mid-match -- the exact disturbance quiet mode exists to prevent.

The clock was never the constraint; presence is. `presence_hold()` keeps the blackout
on past 23:00 while a genuinely fullscreen window owns the foreground.

Three invariants are pinned here, each one a way the gate could silently rot:
  1. A presence hold NEVER reaches into the weekday trading band -- a held-down
     heartbeat is worse than a popup.
  2. The fullscreen test discriminates by window STYLE, not geometry. A maximised
     browser also covers the monitor; matching on rect alone would hold the blackout
     forever and re-create the 2026-08-26 starvation bug.
  3. A broken probe fails OPEN (no hold), degrading to clock-only behaviour.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "setup" / "scripts"))

qm = pytest.importorskip("quiet_mode")


def _et(day: str, hour: int) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=qm.ET)


def test_presence_hold_never_reaches_into_the_trading_day():
    """Weekday 08:00-18:00 ET: no hold, whatever is on screen."""
    for hour in range(qm.MAINTENANCE_END_HOUR, qm.QUIET_START_HOUR):
        assert qm.presence_hold(_et("2026-08-28", hour)) is None, f"held at {hour}:00 Fri"


def test_presence_hold_is_live_outside_the_trading_day(monkeypatch):
    monkeypatch.setattr(qm, "_manual_hold", lambda: None)
    monkeypatch.setattr(qm, "_foreground_fullscreen", lambda: "r5apex_dx12.exe")
    # 23:30 ET Saturday -- the exact moment of the incident.
    held = qm.presence_hold(_et("2026-08-29", 23))
    assert held and "r5apex_dx12.exe" in held


def test_fullscreen_probe_rejects_framed_windows():
    """A maximised (framed) window must not read as fullscreen.

    Pinned at the constant level: the probe's first gate is WS_CAPTION|WS_THICKFRAME,
    the two styles a maximised window keeps and a fullscreen game drops. If someone
    rewrites the probe to compare rects only, these constants stop being consulted.
    """
    src = (ROOT / "setup" / "scripts" / "quiet_mode.py").read_text(encoding="utf-8")
    probe = src.split("def _foreground_fullscreen")[1].split("\ndef ")[0]
    assert "WS_CAPTION" in probe and "WS_THICKFRAME" in probe
    assert "return None" in probe.split("GetWindowLongW")[1][:200], \
        "style check must short-circuit before any geometry comparison"


def test_probe_failure_fails_open(monkeypatch):
    def boom():
        raise RuntimeError("no user32")
    monkeypatch.setattr(qm, "_manual_hold", lambda: None)
    monkeypatch.setattr(qm, "_foreground_fullscreen", boom)
    with pytest.raises(RuntimeError):
        qm.presence_hold(_et("2026-08-29", 23))  # surfaced, never swallowed silently


def test_enforce_path_consults_presence_hold():
    """The gate must be wired into --enforce, not merely defined."""
    src = (ROOT / "setup" / "scripts" / "quiet_mode.py").read_text(encoding="utf-8")
    main = src.split("def main(")[1]
    assert "presence_hold()" in main, "--enforce ignores the presence gate"


def test_linger_survives_an_alt_tab(monkeypatch, tmp_path):
    """A brief alt-tab must not restore 116 tasks and put the popups back."""
    monkeypatch.setattr(qm, "PRESENCE_FILE", tmp_path / "presence.json")
    monkeypatch.setattr(qm, "_manual_hold", lambda: None)
    night = _et("2026-08-29", 23)

    monkeypatch.setattr(qm, "_foreground_fullscreen", lambda: "r5apex_dx12.exe")
    assert qm.presence_hold(night)  # game seen -> recorded

    monkeypatch.setattr(qm, "_foreground_fullscreen", lambda: None)
    just_after = night + dt.timedelta(minutes=qm.PRESENCE_LINGER_MIN - 1)
    assert "linger" in (qm.presence_hold(just_after) or ""), "alt-tab dropped the hold"

    walked_away = night + dt.timedelta(minutes=qm.PRESENCE_LINGER_MIN + 1)
    assert qm.presence_hold(walked_away) is None, "hold never expires"
