"""Guard for GOAL-SILENT-RIG-2026-09-05 S3: window_leak_hook.py must attribute each hide
to the processes created just before it, and must flush ONE daily Known-broken summary
line via the shared status_known_broken.upsert helper once hides > 0 for a day -- "a leak
can never again be silent for days" (S3 spec).

window_leak_hook.py's own callback (_handle_show) takes a live HWND from a real
SetWinEventHook and cannot be driven from a test without a real Win32 window -- so this
guard drives its PURE-PYTHON surface directly with a fake hide event (a fabricated
process-map + fabricated creation-time/image-path lookups), which is exactly what
_handle_show calls after ShowWindow(SW_HIDE) fires. That is the seam the module was
written to expose: attribution and the daily-summary flush never touch a live HWND.

Does NOT restart or import-execute the live hook process (pid tracked in
automation/state/window-leak-hook.pid) -- per GOAL-SILENT-RIG's operating rules, only the
orchestrator restarts it. Loading the module for these tests is safe: import-time work is
limited to WinDLL binding + constant/function-pointer setup, no hook install and no message
loop (those only run inside main()).
"""
from __future__ import annotations

import collections
import datetime as dt
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO / "setup" / "scripts" / "window_leak_hook.py"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ctypes WinDLL, Windows-only")


def _load_module():
    spec = importlib.util.spec_from_file_location("window_leak_hook_s3", HOOK_PATH)
    assert spec and spec.loader, f"cannot load {HOOK_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HOOK = _load_module()


# --- attribution: a fake hide event + a fake process list ---------------------------------

def test_bite_attribute_recent_processes_flags_only_the_just_created(monkeypatch):
    """NON-VACUOUS BITE: a fabricated process map with one process created 0.5s ago (the
    likely leak source) and one created 30s ago (unrelated, pre-existing) -- attribution
    must name only the recent one."""
    now = 1_000_000.0
    pm = {
        # pid: (image_name_lower, ppid)
        4242: ("wscript.exe", 1),
        9999: ("notepad.exe", 1),
    }
    create_times = {4242: now - 0.5, 9999: now - 30.0}
    image_paths = {4242: r"C:\Windows\System32\wscript.exe", 9999: r"C:\Windows\System32\notepad.exe"}

    monkeypatch.setattr(HOOK.time, "time", lambda: now)
    monkeypatch.setattr(HOOK, "_process_create_time", lambda pid: create_times.get(pid))
    monkeypatch.setattr(HOOK, "_full_image_path", lambda pid: image_paths.get(pid, ""))

    result = HOOK._attribute_recent_processes(pm, within_seconds=3.0)
    pids = {r["pid"] for r in result}
    assert pids == {4242}, (
        f"attribution should name only the process created within the window, got pids={pids}"
    )
    assert result[0]["image"] == r"C:\Windows\System32\wscript.exe"
    assert result[0]["parent"] == "?"  # ppid 1 not itself in the fixture pm


def test_attribute_recent_processes_empty_when_nothing_recent(monkeypatch):
    now = 2_000_000.0
    pm = {111: ("old.exe", 0)}
    monkeypatch.setattr(HOOK.time, "time", lambda: now)
    monkeypatch.setattr(HOOK, "_process_create_time", lambda pid: now - 60.0)
    monkeypatch.setattr(HOOK, "_full_image_path", lambda pid: r"C:\old.exe")
    assert HOOK._attribute_recent_processes(pm) == []


def test_attribute_recent_processes_skips_unreadable_process(monkeypatch):
    """A process whose creation time can't be read (access denied / already exited) must be
    skipped, not crash the attribution pass -- this runs AFTER the hide, so it can never be
    allowed to raise back into _handle_show."""
    pm = {1: ("gone.exe", 0)}
    monkeypatch.setattr(HOOK, "_process_create_time", lambda pid: None)
    assert HOOK._attribute_recent_processes(pm) == []


# --- daily summary: fake hide events accumulate, ONE line flushes via the shared upsert ---

def _fake_skb_module(calls: list):
    fake = types.ModuleType("status_known_broken")

    def upsert(marker, line, *, status_path=None):
        calls.append((marker, line))
        return True

    fake.upsert = upsert
    return fake


def test_bite_flush_daily_summary_writes_one_line_via_upsert(monkeypatch):
    """NON-VACUOUS BITE: a fake day with 3 hides across 2 sources must produce exactly ONE
    upsert() call whose line matches 'WINDOW-LEAK: N windows hidden, top sources: ...'."""
    calls: list = []
    monkeypatch.setitem(sys.modules, "status_known_broken", _fake_skb_module(calls))

    sources = collections.Counter()
    sources[r"C:\Windows\System32\wscript.exe"] = 2
    sources[r"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe"] = 1

    HOOK._flush_daily_summary(dt.date(2026, 9, 5), 3, sources)

    assert len(calls) == 1, f"expected exactly one upsert() call, got {len(calls)}: {calls}"
    marker, line = calls[0]
    assert marker == "WINDOW-LEAK:"
    assert "3 windows hidden" in line
    assert "top sources:" in line
    assert r"C:\Windows\System32\wscript.exe x2" in line


def test_flush_daily_summary_noop_when_zero_hides(monkeypatch):
    """A quiet day (0 hides) must NOT write a Known-broken line -- upsert() is never called."""
    calls: list = []
    monkeypatch.setitem(sys.modules, "status_known_broken", _fake_skb_module(calls))
    HOOK._flush_daily_summary(dt.date(2026, 9, 5), 0, collections.Counter())
    assert calls == [], "a 0-hide day must never write a WINDOW-LEAK Known-broken line"


def test_flush_daily_summary_fails_open_on_upsert_exception(monkeypatch):
    """status_known_broken.upsert() raising must never propagate into the hider -- fail-open
    per OP-25 (the hook's job is hiding windows; a broken STATUS.md write is not fatal)."""
    def _raise(marker, line, *, status_path=None):
        raise RuntimeError("disk full")
    fake = types.ModuleType("status_known_broken")
    fake.upsert = _raise
    monkeypatch.setitem(sys.modules, "status_known_broken", fake)

    HOOK._flush_daily_summary(dt.date(2026, 9, 5), 1, collections.Counter({"x": 1}))
    # no exception raised == pass


def test_bite_maybe_flush_rolls_the_day_and_resets_state(monkeypatch):
    """NON-VACUOUS BITE end-to-end: simulate a fake hide event that bumped _hidden_today
    and _leak_sources on 'yesterday', then a day rollover -- exactly one flush fires for
    yesterday's totals, and today's counters start clean."""
    calls: list = []
    monkeypatch.setitem(sys.modules, "status_known_broken", _fake_skb_module(calls))

    monkeypatch.setattr(HOOK, "_flush_date", dt.date(2026, 9, 4))
    monkeypatch.setattr(HOOK, "_hidden_today", 7)
    monkeypatch.setattr(HOOK, "_leak_sources", collections.Counter({"leaker.exe": 7}))

    class _FakeDate(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2026, 9, 5)

    monkeypatch.setattr(HOOK.dt, "date", _FakeDate)

    HOOK._maybe_flush_daily_summary()

    assert len(calls) == 1
    assert "7 windows hidden" in calls[0][1]
    assert "leaker.exe x7" in calls[0][1]
    assert HOOK._flush_date == dt.date(2026, 9, 5)
    assert HOOK._hidden_today == 0
    assert sum(HOOK._leak_sources.values()) == 0


def test_maybe_flush_is_noop_within_the_same_day(monkeypatch):
    calls: list = []
    monkeypatch.setitem(sys.modules, "status_known_broken", _fake_skb_module(calls))
    monkeypatch.setattr(HOOK, "_flush_date", dt.date.today())
    monkeypatch.setattr(HOOK, "_hidden_today", 5)
    HOOK._maybe_flush_daily_summary()
    assert calls == [], "same-day call must not flush (only a day rollover flushes)"
