"""Guard: the CCR (claude-code-router) gateway keepalive is RETIRED and must stay dead.

Scar history -- this is the SECOND lockout caused by routing J's interactive surfaces
through the local gateway:
  * 2026-07-14: `~/.claude/settings.json` pointed at 127.0.0.1:3456, whose Router.default
    is `ollama,qwen3.6:35b` with no Anthropic provider. Port was LISTENING (so the
    keepalive's TCP probe read "up") while every request was silently served local
    Ollama. Cost J a full workday. CCR was audited to have ZERO production benefit and
    Gamma_CcrKeepalive was disabled.
  * 2026-08-23: a later session RE-ENABLED Gamma_CcrKeepalive, which resurrected CCR
    every 10 min. Claude Desktop -- which now carries its OWN third-party-inference
    setting (Connection = Gateway) that the old settings.json guard could not see --
    failed on every restart with "Your gateway couldn't serve claude-sonnet-4-5".

Doctrine (memory: interactive-surfaces-never-gatewayed): J's interactive surfaces must
not have our components as dependencies AT ALL. A dead port fails loudly and is fixed in
one click; a live port serving the wrong models fails silently for a day.

These tests RED if anything resurrects the keepalive. The previous behavioural suite for
the live keepalive is in this path's git history (it was replaced in place, not deleted);
a local .bak copy also exists but is gitignored, so history is the durable provenance.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "setup" / "scripts" / "ccr_keepalive.py"
_REGISTRY = REPO / "automation" / "state" / "SCHEDULED-TASKS.md"


def test_keepalive_script_is_tombstoned_and_noops() -> None:
    """Running the script must exit 0 immediately without probing or restarting CCR."""
    assert _SCRIPT.exists(), "ccr_keepalive.py vanished -- keep the tombstone, not the void"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"tombstone must exit 0, got {proc.returncode}: {proc.stderr}"
    assert "RETIRED" in proc.stdout, f"tombstone banner missing; stdout={proc.stdout!r}"


def test_tombstone_marker_present_in_source() -> None:
    """The retirement notice must survive edits -- it is the only thing explaining WHY."""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "TOMBSTONE 2026-08-23" in src
    assert "_tombstone_sys.exit(0)" in src


def test_registry_does_not_claim_the_task_is_enabled() -> None:
    """SCHEDULED-TASKS.md must not advertise Gamma_CcrKeepalive as re-enabled again."""
    text = _REGISTRY.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        # Only the doctrine bullet lines declare state; the running "N registered (+1 ...)"
        # narrative line mentions many tasks in passing and is not a status claim.
        if not stripped.startswith(("- ", "> - ", "| ")):
            continue
        if "Gamma_CcrKeepalive" in stripped and "RE-ENABLED" in stripped:
            pytest.fail(f"registry re-advertises the retired keepalive: {stripped}")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Task Scheduler only")
def test_scheduled_task_is_not_registered() -> None:
    """Gamma_CcrKeepalive must not exist as a Windows scheduled task."""
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", "Gamma_CcrKeepalive"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0, (
        "Gamma_CcrKeepalive is registered again -- it resurrects the CCR gateway and "
        "breaks J's Claude Desktop on every restart. Unregister it."
    )
