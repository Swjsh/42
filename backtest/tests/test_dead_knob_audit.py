"""Guard: dead_knob_audit -- the config must not silently advertise numbers the engine ignores.

THE INCIDENT (2026-08-17). J watched the day's one winning trade take TP1 and asked a simple
question: is TP1 static or dynamic? The answer turned out to be worse than either.

  * `automation/state/aggressive/params.json` says `tp1_premium_pct: 0.75`.
  * The engine took TP1 at **+100%**.

Proven arithmetically on the real fill, not inferred: entry 0.72, so +75% = 1.26 and
+100% = 1.44. At 13:24 `best_premium` was 1.40 -- which clears 1.26 and would have fired a
+75% TP1. It did not fire. It fired at 13:26 when best reached 1.55, clearing 1.44. The live
value is the literal `tp1_premium_pct=1.0` at `automation/state/fleet/strategies.py:131`,
inside RIBBON_RIDE's ExitShape.

The hardcode is DEFENSIBLE -- it is the SS-B validated cell, ported whole per C29 ("don't mix
fields across cells"). What is not defensible is that params.json advertises a different
number to anyone reading the config, including a future session tuning it.

The same session found `ribbon_min_spread_cents` had been a known dead knob since
`fleet_gate_sweetspot.py:505` wrote it down -- and was still sitting in params.json.

TWO CLASSES, and the distinction is the whole point:
  UNREFERENCED -- name appears in no .py. A grep finds these.
  SHADOWED     -- name IS referenced, but a hardcoded literal wins downstream. A grep calls
                  these HEALTHY. This is the class that produced the TP1 lie.

Pure static analysis over source; no network, no live state, no clock.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "setup" / "scripts" / "dead_knob_audit.py"

_spec = importlib.util.spec_from_file_location("dead_knob_audit", MOD)
dka = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dka)


def test_audit_runs_and_reports_both_classes():
    res = dka.audit()
    assert "unreferenced" in res and "shadowed" in res
    assert res["live_count"] > 50, "most params keys ARE consumed; a tiny count means the " \
                                    "source scan broke, not that the config is dead"


def test_the_tp1_lie_is_still_detected():
    """RED-PROOF for the 2026-08-17 finding. If someone re-points params at the engine (or
    the engine at params) this test SHOULD fail -- and that failure is the signal to re-read
    the exit shape, not to delete the assertion."""
    res = dka.audit()
    shadowed = {(r["file"].split("/")[-2] + "/" + r["file"].split("/")[-1], r["key"])
                for r in res["shadowed"]}
    assert ("aggressive/params.json", "tp1_premium_pct") in shadowed, (
        "aggressive params tp1_premium_pct is no longer flagged SHADOWED -- either the "
        "strategy hardcode was removed (good, verify the engine now honours params) or the "
        "detector regressed (bad)")
    assert ("state/params.json", "tp1_premium_pct") in shadowed


def test_whole_exit_shape_is_shadowed_not_just_tp1():
    """The scope of the lie: it is not one key, it is the ENTIRE exit shape in BOTH files.
    Anyone tuning stop/target/size from params is tuning nothing."""
    res = dka.audit()
    keys = {r["key"] for r in res["shadowed"]}
    for k in ("tp1_premium_pct", "tp1_qty_fraction", "premium_stop_pct"):
        assert k in keys, f"{k} should be flagged as shadowed by strategies.py ExitShape"


def test_doc_and_prose_keys_are_not_reported_as_dead():
    """params.json carries ~29 `_doc` / `_*_section` prose keys BY DESIGN (they ride along via
    the contract's extra='allow'). Reporting those as dead knobs would bury the real six in
    noise -- an audit nobody can read is an audit nobody reads."""
    res = dka.audit()
    for row in res["unreferenced"] + res["shadowed"]:
        assert not row["key"].startswith("_"), f"prose key leaked into the report: {row['key']}"


def test_audit_is_wired_into_the_nightly_fold():
    """A hand-run audit found this weeks late. It only stays found if something runs it."""
    import ast
    src = (REPO / "setup" / "scripts" / "winner_autopsy.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "dead_knob_audit" in imported, (
        "nothing runs the dead-knob audit -- the next lying knob will again be found by hand")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
