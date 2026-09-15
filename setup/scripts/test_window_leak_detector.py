"""Tests for window-leak-detector.py's hide-decision logic.

Run: pytest -v setup/scripts/test_window_leak_detector.py

2026-09-15 companion fix to window_leak_hook.py's incident (see
test_window_leak_hook.py's module docstring for the full story). This detector's own
2026-08-15 title-based safeguard for WindowsTerminal.exe was found to never actually
match in practice against live window-leaks.jsonl data (title reads "Terminal", not
"Windows PowerShell"), so WindowsTerminal.exe/OpenConsole.exe are now structurally
excluded from CONSOLE_HOST_IMAGES (the hide-eligible set) here too -- these tests pin
that.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "window_leak_detector", Path(__file__).parent / "window-leak-detector.py",
)
wld = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(wld)  # type: ignore[union-attr]


# Real observed row, window-leaks.jsonl 2026-09-11T03:37:41Z: WindowsTerminal.exe,
# title "Terminal", service-rooted (svchost->services->wininit->dwm, no explorer.exe).
REAL_WT_ANCESTRY = [
    {"pid": 25088, "image_name": "WindowsTerminal.exe"},
    {"pid": 1832, "image_name": "svchost.exe"},
    {"pid": 1624, "image_name": "services.exe"},
    {"pid": 1528, "image_name": "wininit.exe"},
    {"pid": 1172, "image_name": "dwm.exe"},
]


def test_console_host_images_excludes_windowsterminal_and_openconsole():
    """The structural fix: neither image may ever be hide-eligible again."""
    assert "WindowsTerminal.exe" not in wld.CONSOLE_HOST_IMAGES
    assert "OpenConsole.exe" not in wld.CONSOLE_HOST_IMAGES
    assert "conhost.exe" in wld.CONSOLE_HOST_IMAGES


def test_real_incident_row_would_no_longer_be_hide_eligible():
    """Reproduces the exact real row that used to get ShowWindow'd: WindowsTerminal.exe
    is service-rooted per _is_service_rooted, but is no longer in CONSOLE_HOST_IMAGES so
    main()'s `image in CONSOLE_HOST_IMAGES and _is_service_rooted(...)` gate short-circuits
    False before ever reaching the (broken) title check."""
    assert wld._is_service_rooted(REAL_WT_ANCESTRY) is True  # confirms ancestry IS ambiguous
    assert "WindowsTerminal.exe" not in wld.CONSOLE_HOST_IMAGES  # ...but never reached now


def test_windows_powershell_title_substring_does_not_match_real_titles():
    """Documents the finding that killed the 2026-08-15 fix's premise: real
    WindowsTerminal.exe window titles do not contain 'Windows PowerShell'."""
    real_titles = ["Terminal", "Windows Terminal",
                   "C:\\Users\\jackw\\Desktop\\42\\backtest\\.venv\\Scripts\\pythonw.exe"]
    for title in real_titles:
        assert "windows powershell" not in title.lower()


def test_is_allowed_conhost_not_exempted_by_inherited_title():
    allow = {"image_names": [], "title_substrings": ["Claude Code"], "pids": []}
    assert wld._is_allowed("conhost.exe", "Claude Code - some window", 1, allow) is False


def test_is_allowed_windowsterminal_exempted_by_own_title():
    allow = {"image_names": [], "title_substrings": ["Claude Code"], "pids": []}
    assert wld._is_allowed("WindowsTerminal.exe", "Claude Code - some window", 1, allow) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
