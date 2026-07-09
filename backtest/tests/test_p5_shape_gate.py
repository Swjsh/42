"""P5-HARD-GATE guard (ground rule 10, HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX).

Graduates "no exit shape ships unless it PASSES P5 (is a mass-grind-phase5 survivor) or carries
an explicit waiver" into code. RED-PROOFED per the ground rule: the gate MUST red on the shipped
-20/+150 shape when it is not waived (that is the T5 scar), and MUST green on a real survivor.

Pure -- reads local files only, no network / no backtest.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "p5_shape_gate", REPO / "setup" / "scripts" / "p5_shape_gate.py")
g = importlib.util.module_from_spec(_SPEC)
sys.modules["p5_shape_gate"] = g
_SPEC.loader.exec_module(g)

# The live ribbon_ride shape (the T5 scar) and a KNOWN phase5 survivor shape.
RIBBON_RIDE_SIG = g.ShapeSig(-0.20, 1.5, 0.8, "fixed")
KNOWN_SURVIVOR_SIG = g.ShapeSig(-0.08, 1.5, 0.8, "fixed")  # OTM-1:...:stop-8:tp+150%:sell80%:fixed


def test_survivors_actually_loaded():
    """Guard is only meaningful if it reads real survivors. Assert the known -8/+150/0.8/fixed
    survivor is present (so a pass is never vacuous)."""
    survivors = g.load_survivor_sigs()
    assert survivors, "phase5 outputs produced no survivor sigs -- gate would vacuously pass"
    assert any(g._sig_eq(s, KNOWN_SURVIVOR_SIG) for s in survivors)


def test_survivors_read_full_set_not_truncated_summary():
    """Fable review 2026-07-08: the gate originally read the summary's top_survivors (15 rows)
    while the full phase5 JSONL holds 86 survivors -- 71 legitimate survivors were invisible
    (wrongly-RED direction). Lock the fix: the gate must see WELL more than the 15-row summary."""
    survivors = g.load_survivor_sigs()
    assert len(survivors) >= 50, (
        f"gate sees only {len(survivors)} survivor sigs -- it is reading the truncated summary, "
        "not mass-grind-phase5.jsonl (regenerate via python -m autoresearch.mass_grind_phase5)")


def test_scar_shape_absent_from_FULL_survivor_set():
    """The T5-scar claim re-verified against the COMPLETE survivor set (not the top-15): the
    shipped -20/+150/sell80 shape appears in NEITHER lock mode among all 86 survivors. NOTE the
    old grind's lock axis was a dead knob (orchestrator never translated profit_lock_mode --
    181/181 fixed-vs-trailing P4 pairs byte-identical), so fixed and trailing are the same claim."""
    survivors = g.load_survivor_sigs()
    for lock in ("fixed", "trailing"):
        sig = g.ShapeSig(-0.20, 1.5, 0.8, lock)
        assert not any(g._sig_eq(sig, s) for s in survivors), (
            f"-20/+150/sell80/{lock} IS in the full survivor set -- the waiver justification "
            "and the T5-scar narrative need rewriting")


def test_redproof_shipped_shape_reds_without_waiver():
    """THE red-proof ground rule 10 demands: -20/+150 must RED when not waived (the scar)."""
    survivors = g.load_survivor_sigs()
    status = g.shape_p5_status(RIBBON_RIDE_SIG, survivors, waivers=[])
    assert status["ok"] is False, "the -20/+150 shape should FAIL P5 with no waiver (T5 scar)"
    assert status["is_survivor"] is False


def test_greenproof_real_survivor_passes_without_waiver():
    """A genuine survivor passes with NO waiver -- proves the gate isn't just 'always waive'."""
    survivors = g.load_survivor_sigs()
    status = g.shape_p5_status(KNOWN_SURVIVOR_SIG, survivors, waivers=[])
    assert status["ok"] is True and status["is_survivor"] is True


def test_novel_unvetted_shape_reds():
    """The gate's core purpose: a NEW un-searched shape (not survivor, not waived) cannot ship."""
    survivors = g.load_survivor_sigs()
    waivers = g.load_waivers()
    novel = g.ShapeSig(-0.33, 0.15, 1.0, "fixed")
    assert g.shape_p5_status(novel, survivors, waivers)["ok"] is False


def test_live_shapes_all_gated_green():
    """Committed state is GREEN: every live strategy shape is a survivor OR waived. (The two
    current shapes are on PROVISIONAL waivers -- see p5-shape-waivers.json.)"""
    rows = g.audit_live_shapes()
    names = {r["strategy"] for r in rows}
    assert {"ribbon_ride", "vwap_continuation"} <= names, "live registry shapes missing from audit"
    for r in rows:
        assert r["ok"] is True, f"live shape {r['strategy']} is neither survivor nor waived: {r}"


def test_waiver_signature_state_matches_ratification_record():
    """Honesty lock, updated DELIBERATELY 2026-07-09 (this test IS the ratification record):

    * ribbon_ride must REMAIN provisional/unsigned -- its -20/+150 shape is still the T5 scar,
      never validated, kept only because every tested replacement was worse in the current
      regime (STOP-B 2026-07-09). Anyone flipping it to j_signed=true without a real J call
      is repeating the scar.
    * vwap_continuation must be j_signed=true -- the T-W6 option (a) port of the FULL
      validated core cell (-0.06/+0.40/0.8/fixed), signed under J's 2026-07-09 directive
      ('if it improves the engine it ships') + the 2026-07-07 all-5-OP-22-gates-PASS scorecard
      (analysis/recommendations/vwapcont-exit-ab-ship-gate.json) + T-W6 provenance
      (markdown/audits/T-W6-VWAP-TWO-LANE-PROVENANCE-2026-07-08.md). A regression to
      j_signed=false (or to the stale -0.08/+0.30/0.667/trailing shape) reopens two-lane drift."""
    rows = {r["strategy"]: r for r in g.audit_live_shapes()}
    rr = rows["ribbon_ride"]["waiver"]
    assert rr is not None and rr.get("j_signed") is False, (
        "ribbon_ride must remain a PROVISIONAL (unsigned) waiver until a validated shape "
        "replaces it or J signs it for real")
    vw = rows["vwap_continuation"]["waiver"]
    assert vw is not None and vw.get("j_signed") is True, (
        "vwap_continuation's waiver must stay SIGNED (J directive 2026-07-09 + "
        "vwapcont-exit-ab-ship-gate.json all-gates-PASS + T-W6 provenance)")
    sig = rows["vwap_continuation"]["sig"]
    assert (sig["stop"], sig["tp1"], sig["qty"], sig["lock"]) == (-0.06, 0.40, 0.8, "fixed"), (
        f"vwap_continuation live shape drifted from the ratified full core cell: {sig}")


def test_check_cli_returns_zero_when_gated():
    """`--check` exits 0 in the committed (all-waived) state; it exits 1 only on an unwaived shape."""
    rows = g.audit_live_shapes()
    assert all(r["ok"] for r in rows)
