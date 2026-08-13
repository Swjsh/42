"""Guard: every arm STATES its structure-veto setting; none of them inherits it (2026-08-12).

WHAT WAS FOUND. structure_veto_enabled was True in Safe's params.json and ABSENT ENTIRELY from
Bold's (automation/state/aggressive/params.json). engine_cli.decide_payload reads it as
`gate_params.get("structure_veto_enabled", False)`, so Bold resolved to False -- it has been
trading with the structure veto OFF by OMISSION, never by a recorded decision.

The live ledger proves the asymmetry was real, not theoretical: across 25,821 rows of
automation/state/core-decisions.jsonl, SKIP_STRUCTURE_VETO fired 116 times for account=safe and
ZERO times for bold. For Safe it is ~11% of armed ticks where a setup passed scoring.

WHY ONLY EXPLICITNESS WAS SHIPPED, NOT A FLIP. Writing `false` into Bold's config is a behavioural
NO-OP (false == the old default). Turning it ON would change Bold's trade population and needs
evidence, not a 2am config guess -- especially with the arm's whole purpose being a risk-profile
A/B. What this fixes is that the setting was never a DECISION. Absence-as-configuration is the C14
class: nobody chose it, nobody can see it, and it cannot be reviewed.

THE GENERAL RULE PINNED HERE: a gate that materially changes what an arm trades must be STATED by
every arm, so a diff shows it and a reviewer can question it. Defaults are for things nobody needs
to think about; this is not one of them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SAFE = REPO / "automation" / "state" / "params.json"
BOLD = REPO / "automation" / "state" / "aggressive" / "params.json"
KEY = "structure_veto_enabled"


def _cfg(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,path", [("safe", SAFE), ("bold", BOLD)])
def test_every_arm_states_its_structure_veto_setting(name, path):
    """THE REGRESSION. If an arm's key goes missing again it silently inherits False and nobody
    sees it -- which is exactly how Bold ended up veto-less for its whole life."""
    cfg = _cfg(path)
    assert KEY in cfg, (
        f"{name} does not state {KEY}; it would silently inherit engine_cli's False default. "
        "State it explicitly even when the value matches the default.")
    assert isinstance(cfg[KEY], bool), f"{name}: {KEY} must be a bool, got {cfg[KEY]!r}"


def test_bold_stays_a_deliberate_false_until_evidence_says_otherwise():
    """Not a claim that False is CORRECT -- a claim that it is CHOSEN. Flipping Bold to True
    changes its trade population and needs its own A/B, so if this ever goes RED the flip must
    arrive with evidence attached rather than as a quiet config edit."""
    assert _cfg(BOLD)[KEY] is False, (
        "Bold's structure_veto_enabled changed. That alters which trades Bold takes -- it needs a "
        "pre-registered A/B and a scorecard, not a config edit. If the evidence exists, re-point "
        "this test at it.")


def test_safe_still_runs_the_veto():
    assert _cfg(SAFE)[KEY] is True, (
        "Safe's structure veto was turned off -- it refused 116 live entries over the ledger's "
        "38 days; removing it needs evidence")


def test_the_absence_default_is_still_what_we_think_it_is():
    """The whole finding rests on engine_cli defaulting a MISSING key to False. If that default
    ever changes to True, an arm that omits the key silently GAINS a veto instead of losing one,
    and this guard's reasoning inverts."""
    src = (REPO / "backtest" / "lib" / "engine" / "engine_cli.py").read_text(encoding="utf-8")
    assert f'"{KEY}", False' in src or f"'{KEY}', False" in src or f'get("{KEY}", False)' in src, (
        "engine_cli no longer defaults structure_veto_enabled to False on absence -- re-derive "
        "this guard's premise before trusting it")


def test_the_bold_setting_carries_its_reasoning():
    """A bare `false` is indistinguishable from the default it replaced. The doc key is what makes
    it reviewable."""
    cfg = _cfg(BOLD)
    doc = str(cfg.get(f"_{KEY}_doc", ""))
    assert len(doc) > 100, "Bold's structure_veto_enabled has no explanatory _doc key"
    assert "no-op" in doc.lower() or "default" in doc.lower()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
