"""Guard: a console host must never inherit an app's title allowlist (2026-08-13).

THE INCIDENT. J: "STOP THESE FUCKING CMD POPUS BEFORE I KILL MYSELF" (2026-08-13 ~10:40 ET),
while automation/state/window-leak-summary.json read:

    {"polls_total": 3180000, "leaks_total": 0, ...}

and automation/state/window-leaks.jsonl had recorded nothing since 2026-07-14 -- 422 leaks
logged historically, then silence, through a morning of visible console flashes.

ROOT CAUSE. `_is_allowed` matched the title-substring allowlist against EVERY suspect image.
The allowlist carries "Claude Code" so J's own terminal is not reported. A console host spawned
BY a Claude Code session INHERITS that console title, so a transient `powershell.exe` window
carried the title "Claude Code", matched, and was skipped entirely -- never logged, never
counted, never hidden.

The detector was not broken. It was exempting precisely the windows being complained about.
Third instance in one day of a green signal covering a live failure (the others: exit=0 while
an arm went unmanaged, and min_contracts still valid-looking at 2.75x stale equity).

THE FIX. A title match is honoured only for the app's OWN window image (TITLE_ALLOWLIST_IMAGES).
Console hosts are never exempted by an inherited title.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DET = REPO / "setup" / "scripts" / "window-leak-detector.py"

ALLOW = {"image_names": [], "pids": [],
         "title_substrings": ["Claude Code", "Claude in Chrome", "Apex Legends", "Steam", "Discord"]}


@pytest.fixture(scope="module")
def det():
    spec = importlib.util.spec_from_file_location("_wld_probe", DET)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_wld_probe"] = m
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ the incident


@pytest.mark.parametrize("image", ["powershell.exe", "cmd.exe", "conhost.exe", "OpenConsole.exe", "pwsh.exe"])
def test_a_console_host_is_NOT_exempted_by_an_inherited_title(det, image):
    """THE REGRESSION. This is the exact shape of the 2026-08-13 morning popups: a console
    spawned from a Claude Code session, carrying the parent's title."""
    assert det._is_allowed(image, "Claude Code - 42", 4242, ALLOW) is False, (
        f"{image} with an inherited 'Claude Code' title is still allowlisted -- the detector "
        "remains blind to exactly the windows J reported")


@pytest.mark.parametrize("title", ["Claude Code", "Steam", "Apex Legends", "Discord", "Claude in Chrome"])
def test_no_allowlisted_title_can_exempt_a_console_host(det, title):
    """Every entry in the shipped allowlist, not just the one that bit us."""
    assert det._is_allowed("powershell.exe", title, 1, ALLOW) is False


def test_the_apps_OWN_window_is_still_exempted(det):
    """The allowlist must keep doing its actual job -- J's real terminal is not a leak."""
    assert det._is_allowed("WindowsTerminal.exe", "Claude Code - 42", 1, ALLOW) is True
    assert det._is_allowed("WindowsTerminal.exe", "Steam", 1, ALLOW) is True


def test_an_unrelated_console_title_was_never_exempt_and_still_is_not(det):
    """Vary-and-assert: the fix must not have made everything unconditionally allowed."""
    assert det._is_allowed("powershell.exe", "Windows PowerShell", 1, ALLOW) is False


# ------------------------------------------------------------------ the other two doors


def test_explicit_image_and_pid_allowlists_still_work(det):
    """Those are DELIBERATE, operator-set exemptions and must be untouched by this scope fix."""
    assert det._is_allowed("powershell.exe", "anything", 1, dict(ALLOW, image_names=["powershell.exe"])) is True
    assert det._is_allowed("powershell.exe", "anything", 99, dict(ALLOW, pids=[99])) is True


def test_the_scope_set_is_narrow(det):
    """If TITLE_ALLOWLIST_IMAGES grows to include a console host, the bug is back."""
    assert "WindowsTerminal.exe" in det.TITLE_ALLOWLIST_IMAGES
    for banned in ("powershell.exe", "cmd.exe", "conhost.exe", "OpenConsole.exe", "pwsh.exe",
                   "python.exe", "pythonw.exe", "wscript.exe", "cscript.exe"):
        assert banned not in det.TITLE_ALLOWLIST_IMAGES, (
            f"{banned} was added to TITLE_ALLOWLIST_IMAGES -- a console host can once again be "
            "exempted by an inherited title, which is the 2026-08-13 blindness restored")


def test_console_hosts_are_still_scrutinised_at_all(det):
    """The premise. If powershell.exe leaves SUSPECT_IMAGES, none of the above matters."""
    for img in ("powershell.exe", "cmd.exe", "conhost.exe", "OpenConsole.exe"):
        assert img in det.SUSPECT_IMAGES, f"{img} is no longer scrutinised as a leak candidate"


def test_the_shipped_allowlist_still_contains_the_trigger_entry(det):
    """Provenance: if 'Claude Code' is ever removed from the allowlist the incident cannot
    recur by this route, and this guard should be re-derived rather than trusted."""
    p = REPO / "automation" / "state" / "window-leak-allowlist.json"
    if not p.exists():
        pytest.skip("allowlist absent")
    subs = json.loads(p.read_text(encoding="utf-8")).get("title_substrings", [])
    assert "Claude Code" in subs, (
        "'Claude Code' left the allowlist -- this guard's scenario no longer reflects the "
        "shipped config; re-derive it rather than assuming the fix is still load-bearing")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
