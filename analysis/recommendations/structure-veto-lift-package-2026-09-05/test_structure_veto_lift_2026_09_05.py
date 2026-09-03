"""Guard for the B3 structure-veto lift (package: structure-veto-lift-package-2026-09-05).

NOT LIVE YET. This file is stored in the package directory, NOT under backtest/tests/, by
design (task instruction) -- it documents the exact assertions the flip must satisfy, but is
not wired into the pytest collection path until the main session actually ships the flip. Copy
it to backtest/tests/test_structure_veto_lift_2026_09_05.py in the SAME commit as the
params.json edit (never before -- it will correctly RED against today's repo state, where
structure_veto_enabled is still True for safe).

WHAT THIS PINS, and why each assertion exists:

  (a) safe's automation/state/params.json:structure_veto_enabled == False -- the flip itself.
  (b) bold's automation/state/aggressive/params.json:structure_veto_enabled == False -- proves
      the flip did not touch Bold's explicit, independently-decided False (set 2026-08-12,
      guarded separately by test_structure_veto_explicit_2026_08_12.py; this test does not
      duplicate that guard, only confirms this package's own diff has zero Bold blast radius).
  (c) the 2026-08-04 prereg's kill criterion is still ON DISK, still has a non-empty
      `kill_criterion` field, and the re-check machinery it depends on
      (backtest/autoresearch/gate_expiry_check.py's evaluate_gate_pnl/check_gate path, the
      same sound-replay engine that produced automation/state/gate-registry-status.json's
      `structure_veto_enabled` row and the 2026-08-23 extended battery) is still importable
      and still keys its output on the literal string "structure_veto_enabled" -- i.e. flipping
      the switch does not silently orphan the instrument that would catch a bad flip. This is a
      WIRING check (the plumbing exists), not a live re-run (that happens nightly, unattended,
      on its own schedule -- this test does not invoke or replace it).

WHAT THIS DELIBERATELY DOES NOT DO:
  - Does not re-run gate_expiry_check.py or any replay (that is a >5min-risk grind that runs on
    its own schedule; re-running it here would violate this task's own 5-minute python-process
    ceiling and is not this test's job).
  - Does not assert the flip WAS profitable -- that is exactly what the re-check machinery in
    (c) exists to determine AFTER the fact, on live data the flip has not yet generated.
  - Does not invent a new kill-switch/automation. The kill criterion in the 2026-08-04 prereg
    ("n>=10 fills on refused entries OR 10 sessions net<0 -> re-arm") is evaluated by a HUMAN
    (or a future scheduled instrument) reading gate-registry-status.json's post-flip
    `structure_veto_enabled` row -- this test only proves that row will still exist and still
    be computed by the same sound engine.

See analysis/recommendations/structure-veto-lift-package-2026-09-05/README.md for the full
evidence package this guard belongs to, INCLUDING the contested P&L case (a newer, more
rigorous full-battery revalidation --
analysis/recommendations/gate-revalidation-structure_veto-2026-08-23-extended.json -- currently
recommends "DO NOT FLIP", window 2026-06-26..2026-08-21, not yet re-run with today's 5-episode
cluster folded in). Ship this test only alongside a decision that has weighed that contradiction,
not as evidence that resolves it.
"""

from __future__ import annotations

import json
import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
# gate_expiry_check.py lives under backtest/autoresearch and imports sibling backtest/lib
# modules by the bare `lib.` prefix (same resolution trick engine_cli.py uses) -- this file
# is outside backtest/tests/ (deliberately, per the package-dir instruction) so it does not
# inherit backtest/tests/conftest.py's sys.path setup and must do this itself.
for _p in (str(REPO / "backtest"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
SAFE_PARAMS = REPO / "automation" / "state" / "params.json"
BOLD_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"
PREREG_2026_08_04 = (
    REPO / "analysis" / "recommendations" / "structure-veto-lift-prereg-2026-08-04.json"
)
KEY = "structure_veto_enabled"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_safe_structure_veto_flipped_off():
    """(a) The one-line change this package ships: safe now trades through the classifier's
    downtrend read instead of refusing on it. If this is False, the flip did not ship (or was
    reverted) -- check automation/state/params.json:314 directly before assuming a code bug."""
    cfg = _load(SAFE_PARAMS)
    assert KEY in cfg, f"{KEY} went missing from safe's params.json entirely -- that is not a revert, it's data loss."
    assert cfg[KEY] is False, (
        f"safe's {KEY} is {cfg[KEY]!r}, expected False. This guard only passes once the "
        f"structure-veto-lift-package-2026-09-05 patch has actually been applied to "
        f"automation/state/params.json."
    )


def test_bold_structure_veto_still_false_unaffected_by_this_package():
    """(b) Zero blast radius on Bold. Bold's False predates this package (2026-08-12,
    test_structure_veto_explicit_2026_08_12.py) and this package's own patch touches only
    automation/state/params.json -- Bold's file is untouched. If this goes RED, something
    other than this package's patch moved Bold's key."""
    cfg = _load(BOLD_PARAMS)
    assert KEY in cfg
    assert cfg[KEY] is False, (
        f"Bold's {KEY} changed to {cfg[KEY]!r}. This package's patch never touches "
        f"automation/state/aggressive/params.json -- if Bold's value moved, it was a SEPARATE "
        f"edit and needs its own evidence/prereg, not this guard."
    )


def test_2026_08_04_prereg_kill_criterion_still_on_disk_and_nonempty():
    """(c1) The kill criterion this flip was originally scoped under is still readable. A
    silently-deleted or emptied prereg file would mean nobody could re-check the flip against
    the criterion it was proposed with."""
    assert PREREG_2026_08_04.exists(), (
        f"{PREREG_2026_08_04} is missing -- the 2026-08-04 prereg this flip cites for its kill "
        f"criterion no longer exists on disk."
    )
    doc = _load(PREREG_2026_08_04)
    trial_shape = doc.get("trial_shape_frozen") or {}
    kc = trial_shape.get("kill_criterion")
    assert kc, (
        f"{PREREG_2026_08_04}: trial_shape_frozen.kill_criterion is missing/empty -- the flip "
        f"has no stated re-arm condition to be checked against."
    )
    # The prereg's OWN precondition for the kill criterion being countable at all: a shadow-log
    # path so vetoed-if-still-armed entries stay identifiable post-flip. See README "Precondition
    # gap" section -- as of this package's authoring, engine_cli.py's _classify_sameday_5m only
    # ever runs INSIDE the `if gate_params.get("structure_veto_enabled")` block, so flipping the
    # key to False also turns off the shadow computation, not just the block. This assertion does
    # not fail on that fact (fixing it is out of this package's one-line scope) -- it exists so a
    # future session that adds the shadow log can flip this from xfail-documented to enforced.
    assert "shadow_requirement" in trial_shape, (
        f"{PREREG_2026_08_04}: trial_shape_frozen.shadow_requirement is missing -- the prereg's "
        f"own precondition text for keeping the kill criterion countable while lifted was removed."
    )


def test_gate_expiry_reengine_still_wired_to_structure_veto_enabled():
    """(c2) The re-check MACHINERY (not a re-run -- the plumbing) that would evaluate the kill
    criterion post-flip is still importable and still keys its sound-replay output on the exact
    string 'structure_veto_enabled'. This is what automation/state/gate-registry-status.json's
    nightly row and the 2026-08-23 extended battery both depend on; if this import breaks or the
    key string drifts, gate-registry-status.json silently stops being able to report on this gate
    and nobody would notice until asking why the row went stale."""
    gec = importlib.import_module("backtest.autoresearch.gate_expiry_check")
    assert hasattr(gec, "evaluate_gate_pnl") or hasattr(gec, "check_gate"), (
        "backtest/autoresearch/gate_expiry_check.py no longer exposes evaluate_gate_pnl or "
        "check_gate -- the re-check engine this flip's kill criterion depends on has moved or "
        "been removed. Find the new entrypoint and re-point this guard at it before shipping."
    )
    # The registry row this flip must be re-checked against, generated by the SAME engine.
    registry_path = REPO / "automation" / "state" / "gate-registry-status.json"
    assert registry_path.exists(), "gate-registry-status.json does not exist -- no nightly re-check surface for this gate."
    registry = _load(registry_path)
    assert KEY in (registry.get("gates") or {}), (
        f"{KEY} is no longer a row in gate-registry-status.json's gates block -- the nightly "
        f"instrument stopped tracking this gate. A flip with no post-ship monitoring is not "
        f"the package this README describes."
    )


def test_flip_did_not_silently_widen_beyond_the_single_key():
    """Scope guard: this package is ONE key, ONE value, ONE account. If a future edit to
    params.json under this ticket touches any other key, this is no longer 'the exact one-line
    change' the README promises and needs its own review."""
    cfg = _load(SAFE_PARAMS)
    # Sibling doc key changing is fine (expected -- the _doc string should be updated to record
    # the flip); every OTHER structural key on this gate must be untouched.
    assert "structure_veto_enabled" in cfg
    # No new veto-adjacent key should appear as a side effect of this specific package.
    unexpected_new_keys = {
        "structure_veto_enabled_bold_override",
        "structure_veto_v2_enabled",
    }
    assert not unexpected_new_keys & set(cfg.keys()), (
        "This package's scope is a single boolean flip. A new key appeared alongside it -- "
        "that is a different change than the one this README and patch describe."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
