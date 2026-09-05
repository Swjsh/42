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


@pytest.fixture(autouse=True)
def _redirect_log_to_tmp(tmp_path, monkeypatch):
    """R4c fix (GOAL-SILENT-RIG-2026-09-05): every test in this file exercises
    _flush_daily_summary/_maybe_flush_daily_summary, both of which call the module's
    `_log()` helper -- and `_log()` writes to the module-level `LOG` Path, which defaults
    to the REAL `automation/state/logs/window-leak-hook-<today>.log` file that the LIVE
    hook process also writes to.

    Before this fix, only status_known_broken.upsert() was faked (via
    monkeypatch.setitem(sys.modules, ...)) -- `_log()` was untouched and wrote straight
    through to the real log file on every test run. That is exactly how the two fake
    lines ended up in the real window-leak-hook-2026-09-05.log at 12:08:41 ET ("daily
    summary flushed for 2026-09-05: ... " / "upsert failed: disk full" / "daily summary
    flushed for 2026-09-04: ... leaker.exe x7" -- the literal text this test file's fixture
    data produces). Tests must never write to real files under automation/state.

    Redirecting HOOK.LOG (and HOOK.PID_FILE, defensively, for any future test that
    exercises main()'s singleton-file write) to tmp_path makes every test's file writes
    land in pytest's own tmp_path -- never the live log the orchestrator/hook process
    reads and writes.
    """
    monkeypatch.setattr(HOOK, "LOG", tmp_path / "window-leak-hook-test.log")
    monkeypatch.setattr(HOOK, "PID_FILE", tmp_path / "window-leak-hook-test.pid")


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


# --- R4a: proc_trace.py cross-reference (fixture trace files, no live process/CIM) --------

import json as _json  # noqa: E402


def _write_trace_file(tmp_path, d: dt.date, rows: list) -> "object":
    p = tmp_path / f"proc-trace-{d.isoformat()}.jsonl"
    p.write_text("\n".join(_json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


_TRACE_ROW = {
    "ts_local": 1_757_000_000_000,
    "pid": 4242,
    "ppid": 1,
    "name": "wscript.exe",
    "cmdline": r"wscript.exe //nologo run_exe_hidden.vbs",
    "parent_name": "explorer.exe",
    "parent_cmdline": r"C:\Windows\explorer.exe",
    "session_id": 1,
}


def test_proc_trace_path_for_date_is_daily_rotated(tmp_path):
    p1 = HOOK._proc_trace_path_for_date(dt.date(2026, 9, 5))
    p2 = HOOK._proc_trace_path_for_date(dt.date(2026, 9, 6))
    assert p1 != p2
    assert p1.name == "proc-trace-2026-09-05.jsonl"


def test_bite_read_recent_events_includes_only_within_window(tmp_path, monkeypatch):
    """NON-VACUOUS BITE: a row 0.5s before `now` (inside a 2s window) must be returned; a row
    30s before `now` must not."""
    today = dt.date(2026, 9, 5)
    now_s = 1_757_000_010.0  # seconds
    recent_row = dict(_TRACE_ROW, ts_local=int(now_s * 1000 - 500), pid=1)
    old_row = dict(_TRACE_ROW, ts_local=int(now_s * 1000 - 30_000), pid=2)
    _write_trace_file(tmp_path, today, [recent_row, old_row])

    monkeypatch.setattr(HOOK.dt, "date", type("_D", (dt.date,), {"today": classmethod(lambda cls: today)}))

    events = HOOK._read_recent_proc_trace_events(within_seconds=2.0, now=now_s, log_dir=tmp_path)
    pids = {e["pid"] for e in events}
    assert pids == {1}, f"expected only the recent row, got pids={pids}"


def test_read_recent_events_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(HOOK.dt, "date", type("_D", (dt.date,), {"today": classmethod(lambda cls: dt.date(2026, 9, 5))}))
    assert HOOK._read_recent_proc_trace_events(within_seconds=2.0, now=1_757_000_000.0, log_dir=tmp_path) == []


def test_read_recent_events_skips_malformed_lines(tmp_path, monkeypatch):
    today = dt.date(2026, 9, 5)
    now_s = 1_757_000_010.0
    p = tmp_path / f"proc-trace-{today.isoformat()}.jsonl"
    good_row = dict(_TRACE_ROW, ts_local=int(now_s * 1000 - 100), pid=9)
    p.write_text(_json.dumps(good_row) + "\n{not json}\n\n", encoding="utf-8")
    monkeypatch.setattr(HOOK.dt, "date", type("_D", (dt.date,), {"today": classmethod(lambda cls: today)}))
    events = HOOK._read_recent_proc_trace_events(within_seconds=2.0, now=now_s, log_dir=tmp_path)
    assert len(events) == 1
    assert events[0]["pid"] == 9


def test_read_recent_events_bounded_tail_read_does_not_crash_on_huge_file(tmp_path, monkeypatch):
    """A file far larger than _PROC_TRACE_TAIL_BYTES must still be readable (tail-only) and
    must never raise -- the hide path can never be delayed by a huge trace file."""
    today = dt.date(2026, 9, 5)
    now_s = 1_757_000_010.0
    rows = [dict(_TRACE_ROW, ts_local=int(now_s * 1000 - 100), pid=i) for i in range(2000)]
    _write_trace_file(tmp_path, today, rows)
    monkeypatch.setattr(HOOK, "_PROC_TRACE_TAIL_BYTES", 4096)  # force a small tail window
    monkeypatch.setattr(HOOK.dt, "date", type("_D", (dt.date,), {"today": classmethod(lambda cls: today)}))
    events = HOOK._read_recent_proc_trace_events(within_seconds=2.0, now=now_s, log_dir=tmp_path)
    assert isinstance(events, list)  # must not raise; tail read means not ALL 2000 need appear


def test_format_proc_trace_chain_names_a_dead_parent():
    """THE WHOLE POINT: a process whose parent has already exited by the time the hide log
    is written is still named here, because proc_trace.py looked the parent up at CREATION
    time, not after the fact."""
    events = [dict(_TRACE_ROW, name="pythonw.exe", parent_name="cmd.exe",
                   parent_cmdline=r"C:\Windows\System32\cmd.exe /c foo")]
    chain = HOOK._format_proc_trace_chain(events)
    assert "pythonw.exe" in chain
    assert "cmd.exe" in chain
    assert "C:\\Windows\\System32\\cmd.exe" in chain


def test_format_proc_trace_chain_empty_list_is_none_string():
    assert HOOK._format_proc_trace_chain([]) == "none"


def test_format_proc_trace_chain_bounded_by_limit():
    events = [dict(_TRACE_ROW, pid=i) for i in range(10)]
    chain = HOOK._format_proc_trace_chain(events, limit=3)
    assert chain.count("<- parent") == 3


def test_handle_show_wiring_calls_proc_trace_reader(monkeypatch, tmp_path):
    """Structural: _handle_show must call _read_recent_proc_trace_events and fold its
    output into the HID log line via proc_trace=[...] -- proven by monkeypatching the reader
    to a sentinel and asserting the sentinel text lands in the log file.

    Forces the hide branch by faking _image_name (console host) + _service_rooted (True),
    and by pre-seeding the shared wt.DWORD instance _handle_show constructs so the real
    GetWindowThreadProcessId (also faked, a no-op) doesn't need to write through a live
    ctypes.byref pointer -- the module reads pid.value straight back off that same instance."""
    calls = []

    def _fake_reader(within_seconds=2.0, now=None, log_dir=None):
        calls.append(within_seconds)
        return [dict(_TRACE_ROW, name="SENTINEL_PROC.exe")]

    monkeypatch.setattr(HOOK, "_read_recent_proc_trace_events", _fake_reader)
    monkeypatch.setattr(HOOK, "_parent_map", lambda: {1234: ("windowsterminal.exe", 1), 1: ("services.exe", 0)})
    monkeypatch.setattr(HOOK, "_attribute_recent_processes", lambda pm: [])
    monkeypatch.setattr(HOOK, "ShowWindow", lambda hwnd, cmd: None)
    monkeypatch.setattr(HOOK, "_image_name", lambda pid: "windowsterminal.exe")
    monkeypatch.setattr(HOOK, "_service_rooted", lambda pid, pm: True)

    fake_pid_holder = HOOK.wt.DWORD()
    fake_pid_holder.value = 1234
    monkeypatch.setattr(HOOK.wt, "DWORD", lambda *a, **kw: fake_pid_holder)
    monkeypatch.setattr(HOOK, "GetWindowThreadProcessId", lambda hwnd, ref: None)

    HOOK._handle_show(None, HOOK.EVENT_OBJECT_SHOW, 999, HOOK.OBJID_WINDOW, 0, 0, 0)

    assert calls, "_read_recent_proc_trace_events must be called from _handle_show"
    log_text = HOOK.LOG.read_text(encoding="utf-8") if HOOK.LOG.exists() else ""
    assert "SENTINEL_PROC.exe" in log_text
