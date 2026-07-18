"""Guard for conductor_wake_watch.py -- the WAKE-ON-EVENT watcher for Gamma_Conductor.

Locks the state-file contract (conductor-wake-watermark.json schema + idempotent
line-count advance) and the detection precision fix found live during the 2026-07-18
build session: a companion narrative post containing a siren emoji in its "content"
field is NOT a RED-grade infra alert and must NOT wake the conductor -- only the
"message" schema (self_check / mcp_audit / engine_health / preopen_readiness /
participation_daily / spend_summary, every genuine infra-health producer) counts.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "setup" / "scripts" / "conductor_wake_watch.py"
_spec = importlib.util.spec_from_file_location("conductor_wake_watch", _SCRIPT)
cww = importlib.util.module_from_spec(_spec)
sys.modules["conductor_wake_watch"] = cww
_spec.loader.exec_module(cww)  # type: ignore

import datetime as dt


# ---------------------------------------------------------------------------
# scan_outbox_for_red -- "message" schema only, "content" schema ignored
# ---------------------------------------------------------------------------

def _write_outbox(path: Path, lines: list[dict]):
    with path.open("w", encoding="utf-8") as f:
        for row in lines:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_message_schema_red_detected(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    _write_outbox(outbox, [
        {"ts": "2026-07-18T10:00:00", "source": "self_check", "message": "SELF-CHECK BROKEN: fill funnel RED"},
    ])
    monkeypatch.setattr(cww, "OUTBOX", outbox)
    found, total, evidence = cww.scan_outbox_for_red(0)
    assert found is True
    assert total == 1
    assert "BROKEN" in evidence


def test_content_schema_narrative_emoji_is_not_a_red_event(tmp_path, monkeypatch):
    """Live-verified false positive during the build session: a companion narrative post
    with a siren emoji in "content" (not "message") must NOT wake the conductor."""
    outbox = tmp_path / "discord-outbox.jsonl"
    _write_outbox(outbox, [
        {"content": "<@1> \U0001F6A8 Honest read on v15 stress test -- WR 4% on event days", "source": "companion", "queued_at": "2026-07-18T00:00:00"},
    ])
    monkeypatch.setattr(cww, "OUTBOX", outbox)
    found, total, evidence = cww.scan_outbox_for_red(0)
    assert found is False
    assert total == 1


def test_only_scans_lines_appended_since_watermark(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    _write_outbox(outbox, [
        {"source": "self_check", "message": "SELF-CHECK BROKEN: old RED, already seen"},
    ])
    monkeypatch.setattr(cww, "OUTBOX", outbox)
    # Watermark already saw this 1 line -> nothing new -> no event even though it's a RED line.
    found, total, _ = cww.scan_outbox_for_red(1)
    assert found is False
    assert total == 1


def test_missing_outbox_file_is_a_clean_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(cww, "OUTBOX", tmp_path / "does-not-exist.jsonl")
    found, total, evidence = cww.scan_outbox_for_red(0)
    assert (found, total, evidence) == (False, 0, "")


# ---------------------------------------------------------------------------
# scan_known_broken -- fresh-entry-since-watermark detection
# ---------------------------------------------------------------------------

def test_known_broken_new_entry_detected(tmp_path, monkeypatch):
    status = tmp_path / "STATUS.md"
    status.write_text(
        "## [2026-07-18] some fire\n\ncontent\n\n## Known broken\n"
        "[2026-07-18T12:00:00-04:00] MCP_AUDIT_RED: something broke\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cww, "STATUS_MD", status)
    found, marker = cww.scan_known_broken(None)
    assert found is True
    assert marker == "2026-07-18T12:00:00-04:00"


def test_known_broken_same_marker_is_not_a_new_event(tmp_path, monkeypatch):
    status = tmp_path / "STATUS.md"
    status.write_text(
        "## Known broken\n[2026-07-11T18:30:04] MCP_AUDIT_RED: TradingView unresponsive\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cww, "STATUS_MD", status)
    found, marker = cww.scan_known_broken("2026-07-11T18:30:04")
    assert found is False
    assert marker == "2026-07-11T18:30:04"


def test_no_known_broken_header_is_clean(tmp_path, monkeypatch):
    status = tmp_path / "STATUS.md"
    status.write_text("## some other section\nnothing broken here\n", encoding="utf-8")
    monkeypatch.setattr(cww, "STATUS_MD", status)
    found, marker = cww.scan_known_broken(None)
    assert found is False
    assert marker is None


# ---------------------------------------------------------------------------
# is_rth / target_task -- mode selection by ET time-of-day
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hour,minute,weekday_offset,expected", [
    (10, 0, 0, True),    # Monday 10:00 -> RTH
    (9, 29, 0, False),   # Monday 09:29 -> before open
    (15, 55, 0, False),  # Monday 15:55 -> at close boundary, exclusive
    (15, 54, 0, True),   # Monday 15:54 -> still RTH
    (12, 0, 5, False),   # Saturday 12:00 -> weekend, never RTH regardless of hour
    (12, 0, 6, False),   # Sunday 12:00 -> weekend
])
def test_is_rth_boundaries(hour, minute, weekday_offset, expected):
    # 2026-07-13 is a Monday; add weekday_offset days to land on the target weekday.
    base = dt.datetime(2026, 7, 13, hour, minute)
    d = base + dt.timedelta(days=weekday_offset)
    assert cww.is_rth(d) is expected


def test_target_task_rth_vs_afterhours():
    monday_rth = dt.datetime(2026, 7, 13, 11, 0)
    monday_evening = dt.datetime(2026, 7, 13, 20, 0)
    saturday = dt.datetime(2026, 7, 18, 14, 0)
    assert cww.target_task(monday_rth) == "Gamma_ConductorRTH"
    assert cww.target_task(monday_evening) == "Gamma_Conductor"
    assert cww.target_task(saturday) == "Gamma_Conductor"


# ---------------------------------------------------------------------------
# watermark round-trip (the state-file contract)
# ---------------------------------------------------------------------------

def test_watermark_round_trip(tmp_path, monkeypatch):
    wm_path = tmp_path / "conductor-wake-watermark.json"
    monkeypatch.setattr(cww, "WATERMARK", wm_path)
    wm = cww._load_watermark()
    assert wm == {"last_fired_at_utc": None, "outbox_lines_seen": 0, "known_broken_marker": None}
    wm["outbox_lines_seen"] = 42
    wm["last_fired_at_utc"] = "2026-07-18T10:00:00+00:00"
    cww._save_watermark(wm)
    reloaded = cww._load_watermark()
    assert reloaded["outbox_lines_seen"] == 42
    assert reloaded["last_fired_at_utc"] == "2026-07-18T10:00:00+00:00"


def test_watermark_corrupted_file_degrades_to_default(tmp_path, monkeypatch):
    wm_path = tmp_path / "conductor-wake-watermark.json"
    wm_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(cww, "WATERMARK", wm_path)
    wm = cww._load_watermark()
    assert wm["outbox_lines_seen"] == 0


# ---------------------------------------------------------------------------
# main() end-to-end -- debounce + dry-run + fail-open
# ---------------------------------------------------------------------------

def test_main_dry_run_detects_but_never_fires(tmp_path, monkeypatch, capsys):
    outbox = tmp_path / "discord-outbox.jsonl"
    status = tmp_path / "STATUS.md"
    wm_path = tmp_path / "wm.json"
    _write_outbox(outbox, [{"source": "self_check", "message": "SELF-CHECK BROKEN: x"}])
    status.write_text("no known broken section\n", encoding="utf-8")
    monkeypatch.setattr(cww, "OUTBOX", outbox)
    monkeypatch.setattr(cww, "STATUS_MD", status)
    monkeypatch.setattr(cww, "WATERMARK", wm_path)
    fired = {"called": False}
    monkeypatch.setattr(cww, "fire_task", lambda t: fired.__setitem__("called", True) or (True, "ok"))

    rc = cww.main(["--dry-run"])
    assert rc == 0
    assert fired["called"] is False
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "would fire" in out


def test_main_debounce_prevents_immediate_refire(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    status = tmp_path / "STATUS.md"
    wm_path = tmp_path / "wm.json"
    status.write_text("no known broken section\n", encoding="utf-8")
    monkeypatch.setattr(cww, "OUTBOX", outbox)
    monkeypatch.setattr(cww, "STATUS_MD", status)
    monkeypatch.setattr(cww, "WATERMARK", wm_path)
    calls = {"n": 0}
    monkeypatch.setattr(cww, "fire_task", lambda t: (calls.__setitem__("n", calls["n"] + 1), (True, "ok"))[1])

    _write_outbox(outbox, [{"source": "self_check", "message": "SELF-CHECK BROKEN: first"}])
    assert cww.main([]) == 0
    assert calls["n"] == 1  # first RED event fires immediately

    _write_outbox(outbox, [
        {"source": "self_check", "message": "SELF-CHECK BROKEN: first"},
        {"source": "self_check", "message": "SELF-CHECK BROKEN: second, moments later"},
    ])
    assert cww.main([]) == 0
    assert calls["n"] == 1  # debounced: <30min since the first fire, must NOT fire again


def test_main_force_bypasses_debounce(tmp_path, monkeypatch):
    outbox = tmp_path / "discord-outbox.jsonl"
    status = tmp_path / "STATUS.md"
    wm_path = tmp_path / "wm.json"
    status.write_text("no known broken section\n", encoding="utf-8")
    monkeypatch.setattr(cww, "OUTBOX", outbox)
    monkeypatch.setattr(cww, "STATUS_MD", status)
    monkeypatch.setattr(cww, "WATERMARK", wm_path)
    calls = {"n": 0}
    monkeypatch.setattr(cww, "fire_task", lambda t: (calls.__setitem__("n", calls["n"] + 1), (True, "ok"))[1])

    _write_outbox(outbox, [{"source": "self_check", "message": "SELF-CHECK BROKEN: a"}])
    assert cww.main([]) == 0
    _write_outbox(outbox, [
        {"source": "self_check", "message": "SELF-CHECK BROKEN: a"},
        {"source": "self_check", "message": "SELF-CHECK BROKEN: b"},
    ])
    assert cww.main(["--force"]) == 0
    assert calls["n"] == 2


def test_main_no_event_is_a_quiet_noop(tmp_path, monkeypatch, capsys):
    outbox = tmp_path / "discord-outbox.jsonl"
    status = tmp_path / "STATUS.md"
    wm_path = tmp_path / "wm.json"
    _write_outbox(outbox, [{"source": "prospector", "content": "just an idea, nothing broken"}])
    status.write_text("all green\n", encoding="utf-8")
    monkeypatch.setattr(cww, "OUTBOX", outbox)
    monkeypatch.setattr(cww, "STATUS_MD", status)
    monkeypatch.setattr(cww, "WATERMARK", wm_path)
    fired = {"called": False}
    monkeypatch.setattr(cww, "fire_task", lambda t: fired.__setitem__("called", True) or (True, "ok"))

    assert cww.main([]) == 0
    assert fired["called"] is False


def test_main_never_raises_on_totally_broken_state(tmp_path, monkeypatch):
    """Fail-open contract: even if every file is unreadable/corrupted, main() returns 0."""
    monkeypatch.setattr(cww, "OUTBOX", tmp_path / "nonexistent" / "outbox.jsonl")
    monkeypatch.setattr(cww, "STATUS_MD", tmp_path / "nonexistent" / "STATUS.md")
    monkeypatch.setattr(cww, "WATERMARK", tmp_path / "nonexistent" / "wm.json")
    assert cww.main([]) == 0
