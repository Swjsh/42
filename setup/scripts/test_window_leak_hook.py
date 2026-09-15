"""Tests for window_leak_hook.py -- the event-driven console-host auto-hider.

Run: pytest -v setup/scripts/test_window_leak_hook.py

BACKGROUND (2026-09-15): J reported "powershell closes immediately when I open it".
Root cause: _handle_show() hid ANY service-rooted console-host window (including
WindowsTerminal.exe -- what hosts J's interactive PowerShell on Win11) and never
consulted automation/state/window-leak-allowlist.json at all, unlike the sibling poller
window-leak-detector.py. Live investigation (2026-09-15) additionally found the
detector's own title-based safeguard for WindowsTerminal.exe never actually matches in
practice (title reads generically "Terminal", not the hosted shell's name) and that
ancestry/session-id cannot distinguish J's own WindowsTerminal from a Task-Scheduler
leak on this box -- so the real fix is structural: WindowsTerminal.exe/OpenConsole.exe
are never auto-hidden by either script any more (CONSOLE_HOST_HIDE_ELIGIBLE), and the
allowlist is honoured (with mtime-reload + fail-open) for the one image that remains
hide-eligible, legacy conhost.exe.

These tests exercise the pure `_decide()` core (extracted specifically for testability)
plus the allowlist loader's mtime-reload and fail-open behavior -- no real Win32 window
or process is created.
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "window_leak_hook", Path(__file__).parent / "window_leak_hook.py",
)
wlh = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(wlh)  # type: ignore[union-attr]


@pytest.fixture(autouse=True)
def _no_production_log_writes(monkeypatch):
    """_load_allowlist()'s fail-open path calls the module's real _log(), which appends
    to the REAL, dated automation/state/logs/window-leak-hook-<today>.log -- redirect it
    during tests so test noise never lands in the production hook's log file."""
    monkeypatch.setattr(wlh, "_log", lambda msg: None)


# === fixtures mirroring REAL observed rows =============================================

# window-leak-hook-2026-09-14.log HID #40-44 / window-leaks.jsonl 2026-09-11T03:37:41Z:
# a WindowsTerminal.exe window, title "Terminal", service-rooted (svchost->services->
# wininit, no explorer.exe) -- this is the row that hid J's real interactive PowerShell.
REAL_WT_PID = 23376
REAL_WT_PM = {
    23376: ("windowsterminal.exe", 1832),
    1832: ("svchost.exe", 1624),
    1624: ("services.exe", 1528),
    1528: ("wininit.exe", 1172),
    1172: ("dwm.exe", 0),
}
REAL_WT_TITLE = "Terminal"

# A genuine automation leak: bare conhost.exe, service-rooted, spawned by a headless
# pythonw scheduled-task script (matches the shape of real HID rows for conhost-class
# leaks -- see CONSOLE_HOST_HIDE_ELIGIBLE comment in window_leak_hook.py).
AUTOMATION_CONHOST_PID = 9001
AUTOMATION_CONHOST_PM = {
    9001: ("conhost.exe", 8000),
    8000: ("pythonw.exe", 1800),
    1800: ("svchost.exe", 1624),
    1624: ("services.exe", 1528),
    1528: ("wininit.exe", 0),
}
AUTOMATION_CONHOST_TITLE = "C:\\Users\\jackw\\Desktop\\42\\backtest\\.venv\\Scripts\\pythonw.exe"

# J's own legacy console (explorer-rooted -- no DCOM activation involved for conhost.exe).
J_LEGACY_CONHOST_PID = 4242
J_LEGACY_CONHOST_PM = {
    4242: ("conhost.exe", 3000),
    3000: ("cmd.exe", 2000),
    2000: ("explorer.exe", 0),
}


def _allow(**overrides) -> dict:
    base = {"image_names": [], "title_substrings": [], "pids": []}
    base.update(overrides)
    return base


# === CONSOLE_HOST_HIDE_ELIGIBLE structural exclusion ====================================

def test_windowsterminal_never_hidden_even_when_service_rooted_and_no_allowlist():
    """The exact real-world incident row: WT, title 'Terminal', service-rooted, allowlist
    empty. Must NOT be hidden -- WindowsTerminal.exe is structurally excluded."""
    should_hide, reason = wlh._decide(
        "windowsterminal.exe", REAL_WT_TITLE, REAL_WT_PID, REAL_WT_PM, _allow(),
    )
    assert should_hide is False
    assert "not-hide-eligible" in reason


def test_windowsterminal_never_hidden_even_with_allowlist_none():
    """Same real row, but allowlist unavailable (None) -- still never hidden, and for the
    right (structural) reason, not merely because of the fail-open path."""
    should_hide, reason = wlh._decide(
        "windowsterminal.exe", REAL_WT_TITLE, REAL_WT_PID, REAL_WT_PM, None,
    )
    assert should_hide is False
    assert "not-hide-eligible" in reason


def test_openconsole_never_hidden():
    should_hide, _ = wlh._decide(
        "openconsole.exe", "Terminal", 111, {111: ("openconsole.exe", 1832),
                                              1832: ("svchost.exe", 0)}, _allow(),
    )
    assert should_hide is False


# === conhost.exe: the one hide-eligible image ===========================================

def test_automation_conhost_leak_is_hidden():
    """A genuine automation leak (service-rooted conhost.exe, not allowlisted) must still
    be hidden -- the fix must not disable leak suppression entirely."""
    should_hide, reason = wlh._decide(
        "conhost.exe", AUTOMATION_CONHOST_TITLE, AUTOMATION_CONHOST_PID,
        AUTOMATION_CONHOST_PM, _allow(),
    )
    assert should_hide is True
    assert reason == "service-rooted-not-allowlisted"


def test_j_legacy_conhost_explorer_rooted_not_hidden():
    should_hide, reason = wlh._decide(
        "conhost.exe", "Command Prompt", J_LEGACY_CONHOST_PID, J_LEGACY_CONHOST_PM,
        _allow(),
    )
    assert should_hide is False
    assert reason == "explorer-rooted"


def test_conhost_allowlisted_by_pid_not_hidden():
    allow = _allow(pids=[AUTOMATION_CONHOST_PID])
    should_hide, reason = wlh._decide(
        "conhost.exe", AUTOMATION_CONHOST_TITLE, AUTOMATION_CONHOST_PID,
        AUTOMATION_CONHOST_PM, allow,
    )
    assert should_hide is False
    assert reason == "allowlisted"


def test_conhost_allowlisted_by_image_name_not_hidden():
    allow = _allow(image_names=["conhost.exe"])
    should_hide, reason = wlh._decide(
        "conhost.exe", AUTOMATION_CONHOST_TITLE, AUTOMATION_CONHOST_PID,
        AUTOMATION_CONHOST_PM, allow,
    )
    assert should_hide is False
    assert reason == "allowlisted"


def test_conhost_title_substring_does_not_exempt_it():
    """conhost.exe is NOT in TITLE_ALLOWLIST_IMAGES -- a title match alone (without an
    image_names/pids entry) must NOT exempt a console host. This is the exact scope fix
    the detector shipped 2026-08-13 (inherited titles must not create a blind spot)."""
    allow = _allow(title_substrings=["pythonw.exe"])
    should_hide, reason = wlh._decide(
        "conhost.exe", AUTOMATION_CONHOST_TITLE, AUTOMATION_CONHOST_PID,
        AUTOMATION_CONHOST_PM, allow,
    )
    assert should_hide is True


# === fail-open =========================================================================

def test_conhost_not_hidden_when_allowlist_unavailable():
    """allow=None (missing/corrupt allowlist file) must fail OPEN -- never hide."""
    should_hide, reason = wlh._decide(
        "conhost.exe", AUTOMATION_CONHOST_TITLE, AUTOMATION_CONHOST_PID,
        AUTOMATION_CONHOST_PM, None,
    )
    assert should_hide is False
    assert reason == "allowlist-unavailable-fail-open"


def test_load_allowlist_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(wlh, "ALLOWLIST_FILE", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(wlh, "_allow_cache", None)
    monkeypatch.setattr(wlh, "_allow_mtime", None)
    monkeypatch.setattr(wlh, "_allow_load_failed_logged", False)
    assert wlh._load_allowlist() is None


def test_load_allowlist_corrupt_json_returns_none(tmp_path, monkeypatch):
    p = tmp_path / "allow.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(wlh, "ALLOWLIST_FILE", p)
    monkeypatch.setattr(wlh, "_allow_cache", None)
    monkeypatch.setattr(wlh, "_allow_mtime", None)
    monkeypatch.setattr(wlh, "_allow_load_failed_logged", False)
    assert wlh._load_allowlist() is None


def test_load_allowlist_non_object_json_returns_none(tmp_path, monkeypatch):
    p = tmp_path / "allow.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(wlh, "ALLOWLIST_FILE", p)
    monkeypatch.setattr(wlh, "_allow_cache", None)
    monkeypatch.setattr(wlh, "_allow_mtime", None)
    monkeypatch.setattr(wlh, "_allow_load_failed_logged", False)
    assert wlh._load_allowlist() is None


# === mtime reload =======================================================================

def test_load_allowlist_reloads_on_mtime_change(tmp_path, monkeypatch):
    p = tmp_path / "allow.json"
    p.write_text(json.dumps({"image_names": [], "title_substrings": [], "pids": []}),
                 encoding="utf-8")
    monkeypatch.setattr(wlh, "ALLOWLIST_FILE", p)
    monkeypatch.setattr(wlh, "_allow_cache", None)
    monkeypatch.setattr(wlh, "_allow_mtime", None)
    monkeypatch.setattr(wlh, "_allow_load_failed_logged", False)

    first = wlh._load_allowlist()
    assert first is not None
    assert first["pids"] == []

    # Bump mtime forward so the change is unambiguous even on coarse filesystem clocks.
    p.write_text(json.dumps({"image_names": [], "title_substrings": [], "pids": [9999]}),
                 encoding="utf-8")
    new_time = time.time() + 5
    os.utime(p, (new_time, new_time))

    second = wlh._load_allowlist()
    assert second is not None
    assert second["pids"] == [9999], "allowlist must reload when the file's mtime changes"


def test_load_allowlist_caches_when_mtime_unchanged(tmp_path, monkeypatch):
    p = tmp_path / "allow.json"
    p.write_text(json.dumps({"image_names": [], "title_substrings": [], "pids": []}),
                 encoding="utf-8")
    monkeypatch.setattr(wlh, "ALLOWLIST_FILE", p)
    monkeypatch.setattr(wlh, "_allow_cache", None)
    monkeypatch.setattr(wlh, "_allow_mtime", None)
    monkeypatch.setattr(wlh, "_allow_load_failed_logged", False)

    first = wlh._load_allowlist()
    # Mutate the cached dict object directly to prove the SECOND call returns the same
    # cached object rather than re-reading (mtime unchanged).
    first["_marker"] = "cached"
    second = wlh._load_allowlist()
    assert second.get("_marker") == "cached"


# === _is_allowed parity with window-leak-detector.py's _is_allowed ======================

def test_is_allowed_parity_with_detector():
    """Both scripts independently implement _is_allowed (the hook cannot import the
    hyphenated detector module cleanly for a long-running process -- see the module
    docstring). Pin them to identical behavior across a representative case matrix so a
    future edit to one cannot silently diverge from the other."""
    det_spec = importlib.util.spec_from_file_location(
        "window_leak_detector_for_test",
        Path(__file__).parent / "window-leak-detector.py",
    )
    det = importlib.util.module_from_spec(det_spec)  # type: ignore[arg-type]
    det_spec.loader.exec_module(det)  # type: ignore[union-attr]

    allow = {
        "image_names": ["steam.exe"],
        "title_substrings": ["Claude Code", "Windows PowerShell"],
        "pids": [555],
    }
    cases = [
        # (image_name_lower_for_hook, image_name_mixedcase_for_detector, title, pid)
        ("windowsterminal.exe", "WindowsTerminal.exe", "Claude Code - foo.py", 1),
        ("windowsterminal.exe", "WindowsTerminal.exe", "Terminal", 2),
        ("conhost.exe", "conhost.exe", "Claude Code - foo.py", 3),  # inherited title trap
        ("conhost.exe", "conhost.exe", "anything", 555),  # allowlisted by pid
        ("steam.exe", "steam.exe", "anything", 4),  # allowlisted by image_name
        ("windowsterminal.exe", "WindowsTerminal.exe", "Windows PowerShell v1.0", 5),
    ]
    for hook_image, det_image, title, pid in cases:
        hook_result = wlh._is_allowed(hook_image, title, pid, allow)
        det_result = det._is_allowed(det_image, title, pid, allow)
        assert hook_result == det_result, (
            f"parity break for image={det_image!r} title={title!r} pid={pid}: "
            f"hook={hook_result} detector={det_result}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
