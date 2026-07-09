"""Guard for the funnel-v2 pre-trust audit finding (CHECK 5,
analysis/exit-parity/funnel-v2-pretrust-audit.md, 2026-07-09): mass_grind_phase5.py has
NO awareness of whether the underlying grind actually finished before it computes
"deploy-grade" P5 survivors. `_grind_complete()` / `mass-grind-total.json` live ONLY in
mass_grind_funnel.py (gates the FUNNEL WORKER's own poll-loop exit) -- phase5's main()
reads whatever P4 elites exist at call time and writes a summary with NO completeness
signal at all, so a premature run (this exact scenario already happened once tonight,
at 68% grind completion, before the grind was relaunched) produces a
mass-grind-phase5-summary.json that is byte-structurally indistinguishable from a
real, final one. STOP-B has no code-level way to tell "final" from "mid-grind snapshot".

The only automated trigger that would call `mass_grind_phase5` after checking
completion (`setup/scripts/grind-shard-watchdog.ps1` -> `Gamma_Grind_Watchdog`) is
confirmed Disabled tonight, AND is wired to the legacy v1 file globs
(`mass-grind-progress*.jsonl` / `mass-grind-total.json` fallback 3360) so it could not
correctly detect v2 completion even if re-enabled. Tonight's actual safeguard is a
markdown checklist item (automation/overnight/queue.md T-W7C) read by a human/agent --
this test documents the code-level hole that checklist is the ONLY thing covering.

RED-PROOFED per this repo's graduated-guard convention (see test_p5_shape_gate.py,
mass_grind.py's `_vary_and_assert_probe`): asserts the DESIRED behavior, which the
current code does not implement. Both tests below are EXPECTED TO FAIL until
mass_grind_phase5.py threads a real progress-vs-total completeness check (mirroring
mass_grind_funnel.py's own `_grind_complete()`) into its output. A future fix should
turn both green; do not delete or weaken them to make that happen.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import autoresearch.mass_grind_phase5 as m5


def _write_funnel_row(path: Path, label: str, combo: list, phase_reached: int = 4) -> None:
    row = {
        "label": label, "combo": combo, "phase_reached": phase_reached,
        "verdict": "PASS-P4" if phase_reached == 4 else "PASS-P2",
        "edge_capture": 900.0, "expectancy": 10.0, "wr": 0.3, "n": 50, "wf": 1.5,
        "max_dd": -100.0, "qpf": 1.0,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def test_phase5_summary_discloses_grind_completeness(tmp_path, monkeypatch):
    """mass-grind-phase5-summary.json must say whether the grind it summarizes was
    COMPLETE (progress rows >= mass-grind-total.json's total) at generation time -- the
    exact signal mass_grind_funnel.py's own _grind_complete() already computes for
    itself, just never threaded into phase5's output. Without it, a summary generated
    at 68% (today's real mid-death) is INDISTINGUISHABLE on disk from one generated at
    100%, and nothing stops it becoming tonight's STOP-B kill-check input by accident."""
    reco = tmp_path
    monkeypatch.setattr(m5, "RECO", reco)
    monkeypatch.setattr(m5, "OUT", reco / "mass-grind-phase5.jsonl")
    monkeypatch.setattr(m5, "SUMMARY", reco / "mass-grind-phase5-summary.json")

    # A deliberately INCOMPLETE snapshot: total says 7560, only 1 progress row exists
    # (an extreme version of tonight's real ~68%/91% mid-grind states).
    (reco / "mass-grind-total.json").write_text(json.dumps({"total": 7560}), encoding="utf-8")
    (reco / "mass-grind-v2-progress.jsonl").write_text(
        json.dumps({"label": "OTM-2:LR0:mt1:stop-8:tp+30%:sell50%:fixed:ts10"}) + "\n",
        encoding="utf-8",
    )
    combo = ["OTM-2", 2, False, 1, "-8", -0.08, 0.3, 0.5, "fixed", 0.0, 10]
    _write_funnel_row(reco / "mass-grind-funnel-v2-0.jsonl",
                       "OTM-2:LR0:mt1:stop-8:tp+30%:sell50%:fixed:ts10", combo, phase_reached=4)

    rc = m5.main()
    assert rc == 0

    summary = json.loads((reco / "mass-grind-phase5-summary.json").read_text(encoding="utf-8"))
    assert "grind_complete" in summary, (
        "mass-grind-phase5-summary.json has NO completeness field -- a summary generated "
        "mid-grind (1/7560 progress rows here) is byte-structurally identical to one "
        "generated after the real 7560/7560 finish. STOP-B (or any consumer) cannot tell "
        "them apart without re-deriving the check by hand (see funnel-v2-pretrust-audit.md "
        "CHECK 5). Thread mass_grind_funnel._grind_complete()'s progress-vs-total math into "
        "mass_grind_phase5.main() and stamp the result here.")
    assert summary["grind_complete"] is False, (
        "this fixture is 1 progress row against a declared total of 7560 -- grind_complete "
        "must read False, not silently default True")


def test_phase5_main_has_no_completion_gate_today():
    """Static counterpart, no fixture needed: main()'s own source has zero reference to
    a total/progress completeness check. Guards against a future fix that adds a
    'grind_complete' KEY without actually consulting mass-grind-total.json / the
    progress files (a hardcoded/always-true flag would pass the behavioral test above
    only by accident -- e.g. defaulting True -- so this pins the mechanism, not just the
    shape). NOTE: check for the qualified names, not the bare substring 'total' --
    'total' already appears in main() today via the unrelated 'neighbors_total' key, so
    a naive substring-only check would vacuously pass right now for the wrong reason."""
    src = inspect.getsource(m5.main)
    assert "mass-grind-total" in src or "_grind_complete" in src or "grind_complete" in src, (
        "mass_grind_phase5.main() still has zero reference to the grind's own total/"
        "progress completeness -- it will happily certify P5 survivors off a mid-grind "
        "snapshot (this repo's own 2026-07-09 68%-death was a live example) with no "
        "signal to the caller that the input was partial.")
