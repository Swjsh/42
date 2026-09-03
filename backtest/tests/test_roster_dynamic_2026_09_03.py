"""Guard: quote_recorder / entry_location_shadow / exit_coverage_check read the LIVE arm
roster (arm_roster.active_arms()) instead of a hardcoded 5-tuple.

Filed by overnight queue item THREE-MODULES-SHOULD-READ-THE-ROSTER-DYNAMICALLY (2026-09-02):
all three hardcoded ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3") including retired
risky-3. exit_coverage_check is the one that matters most -- it reports exit coverage per arm,
so a roster that never learns about a NEW arm silently reads that arm as "fully covered"
(absent, never assessed) rather than flagging it.

Each module now exposes `ARMS` via a PEP 562 module __getattr__ that calls
arm_roster.active_arms() on every access (never a value cached at import), and every internal
usage site calls active_arms() fresh rather than reading a module-level constant. This proves
both halves: the module's own ARMS view matches the roster, and a live roster change (here,
monkeypatching arm_roster.active_arms) is visible without re-importing.

Run: backtest/.venv/Scripts/python.exe -m pytest setup/scripts/test_roster_dynamic_2026_09_03.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
FLEET = REPO / "automation" / "state" / "fleet"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(FLEET))

import arm_roster as ar  # noqa: E402
import quote_recorder as qr  # noqa: E402
import entry_location_shadow as els  # noqa: E402
import exit_coverage_check as ecc  # noqa: E402

MODULES = {"quote_recorder": qr, "entry_location_shadow": els, "exit_coverage_check": ecc}


def test_each_module_arms_equals_the_roster_active_set():
    expected = set(ar.active_arms())
    for name, mod in MODULES.items():
        assert set(mod.ARMS) == expected, f"{name}.ARMS={mod.ARMS!r} != roster {expected!r}"


def test_retired_risky_3_is_excluded():
    for name, mod in MODULES.items():
        assert "risky-3" not in mod.ARMS, f"{name}.ARMS still names retired risky-3"


def test_a_new_roster_arm_is_visible_without_reimport(monkeypatch):
    """The gap this closes: exit_coverage_check reporting full coverage for an arm it never
    knew existed. Monkeypatch arm_roster.active_arms (the shared source every module now
    calls) and confirm all three see safe-9 immediately -- no re-import, no restart."""
    def _fake_active_arms(path=None):
        return ["safe-2", "bold-2", "safe-9"]

    monkeypatch.setattr(ar, "active_arms", _fake_active_arms)
    monkeypatch.setattr(qr, "active_arms", _fake_active_arms)
    monkeypatch.setattr(els, "active_arms", _fake_active_arms)
    monkeypatch.setattr(ecc, "active_arms", _fake_active_arms)

    assert "safe-9" in qr.ARMS
    assert "safe-9" in els.ARMS
    assert "safe-9" in ecc.ARMS


def test_unknown_attribute_still_raises_attributeerror():
    for name, mod in MODULES.items():
        try:
            mod.NOT_A_REAL_ATTRIBUTE  # noqa: B018
        except AttributeError:
            continue
        raise AssertionError(f"{name}.__getattr__ swallowed an unknown attribute")
