"""Guard: scheduled-task enumeration must not depend on the caller's CWD.

Scar (2026-08-09, J: "too many cmd and windows popups"): while sweeping console-flash
sources, the window-leak compliance audit flipped to RED with a bare
`JSONDecodeError: Expecting value: line 1 column 1`. Root cause was NOT Task Scheduler --
`_registered_tasks()` passed a repo-RELATIVE path to `powershell.exe -File`. Called from
any CWD other than the repo root, PowerShell could not find the script, dropped into
banner mode, and returned "Windows PowerShell\\nCopyright (C) Microsoft Corporation..."
on stdout. That banner is 78 non-empty characters, so the `if not raw.strip()` empty-guard
waved it straight through into json.loads.

Two independent failures, so two independent guards:
  1. C9 -- the helper path is anchored to __file__, so enumeration works from any CWD.
  2. C7 -- non-JSON stdout raises a message that NAMES the problem, instead of surfacing a
     positional parse error that points the reader at Task Scheduler.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import audit_scheduled_tasks as ast_mod  # noqa: E402


def test_helper_path_is_absolute_and_anchored_to_file(monkeypatch, tmp_path):
    """REDs if the helper path ever goes back to being CWD-relative."""
    captured: dict[str, Path] = {}

    def fake_powershell_file(path: Path) -> str:
        captured["path"] = Path(path)
        return "[]"

    monkeypatch.setattr(ast_mod, "_powershell_file", fake_powershell_file)
    # Run from a directory that is definitively NOT the repo root.
    monkeypatch.chdir(tmp_path)

    ast_mod._registered_tasks()

    helper = captured["path"]
    assert helper.is_absolute(), f"helper path must be absolute, got {helper!r}"
    assert helper.is_file(), f"helper must resolve to a real file from any CWD, got {helper!r}"
    assert helper.name == "_list-gamma-tasks-json.ps1"


def test_powershell_banner_raises_a_named_error_not_a_parse_error(monkeypatch):
    """The exact 78-char banner that slipped past the empty-guard must now be loud."""
    banner = (
        "Windows PowerShell\n"
        "Copyright (C) Microsoft Corporation. All rights reserved.\n"
    )
    monkeypatch.setattr(ast_mod, "_powershell_file", lambda _p: banner)

    with pytest.raises(RuntimeError) as exc:
        ast_mod._registered_tasks()

    msg = str(exc.value)
    assert "non-JSON" in msg, f"error must name the real problem, got: {msg}"
    assert "Windows PowerShell" in msg, "error must quote the offending stdout"


def test_genuinely_empty_stdout_still_returns_empty_list(monkeypatch):
    """Empty stdout keeps its existing contract -- the caller flags LIVE_TASK_SCAN_EMPTY."""
    monkeypatch.setattr(ast_mod, "_powershell_file", lambda _p: "   \n  ")
    assert ast_mod._registered_tasks() == []


def test_valid_json_array_still_parses(monkeypatch):
    """Happy path must survive the added guard."""
    monkeypatch.setattr(ast_mod, "_powershell_file", lambda _p: '[{"name":"Gamma_X"}]')
    assert ast_mod._registered_tasks() == [{"name": "Gamma_X"}]
