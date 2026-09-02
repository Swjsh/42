"""The level-memory wire's recorded verdict is unreproducible -- pin that it stays retired.

THE SCAR (2026-09-02). `analysis/recommendations/level-memory-wire.json` carries a complete,
official-looking scorecard: CONTROL 28 trades / TREATMENT 26, n_effect=3, delta -$489.50,
verdict NEGATIVE_INSUFFICIENT_N, "flag_recommendation: leave level_memory_live_merge ON".
`automation/state/params.json` duly carries `level_memory_live_merge: true` to this day, and
`refresh_levels_intraday.py:700` really does merge multi-day memory levels into the live feed
on every intraday refresh.

**No code in this repository, at any commit, can produce that TREATMENT arm.**

`git show --stat e84c062f` -- the commit whose own message reads "levels.py's new additive
memory_levels_by_day hook unions the SAME spot-band+cap formula the live wire uses into real
production trigger logic" -- touches SIX files, and not one of them is engine code. And
`git log -S memory_levels_by_day -- backtest/lib/levels.py backtest/lib/orchestrator.py`
returns nothing across all history: the kwarg has never existed. The runner still dies on it
today, but only AFTER completing a full CONTROL backtest, which is why the import-level smoke
test that cleared all 11 frozen runners could not see it.

WHY A GENERIC "does the claimed build exist?" MONITOR WOULD NOT HAVE CAUGHT THIS, and so why
this file is narrow on purpose: the prereg's `build_step_complete` names
`backtest/lib/levels.py#_detect_from_history`, and that function does exist. What is missing
is the *kwarg*, one level below the granularity of the claim. The claim was unfalsifiable as
written, not merely false.

WHAT THIS FILE PINS -- three properties, none of them the hypothesis:

  1. The prereg stays RETIRED. A frozen prereg quietly flipped back to a runnable status is
     how an unreproducible number re-enters the record as evidence.
  2. If the hook is ever built, the study cannot be revived against the DEAD formula. The
     frozen treatment is side-blind "nearest 6"; the live wire changed 2026-07-27 to cap each
     side independently at 3, precisely because side-blind selection "produced an
     all-resistance set with ZERO supports" (J live-flagged). Measuring the superseded rule
     would answer a question production stopped asking six weeks earlier.
  3. The scorecard is never silently promoted to a verdict -- its own file must keep saying
     the n it rests on is below the evidence floor.

DELIBERATELY NOT ASSERTED: that `level_memory_live_merge` should be false. That is a live
params change inside the config freeze, and the honest state is UNMEASURED, not refuted --
turning "we cannot reproduce the evidence" into "therefore turn it off" would be inventing a
verdict in the other direction. Filed for the 10-30 window instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "analysis" / "recommendations" / "prereg-level-memory-wire-2026-07-15.json"
SCORECARD = REPO / "analysis" / "recommendations" / "level-memory-wire.json"
LEVELS = REPO / "backtest" / "lib" / "levels.py"
LIVE_MERGE = REPO / "setup" / "scripts" / "refresh_levels_intraday.py"
RUNNER = REPO / "backtest" / "tools" / "level_memory_wire_ab.py"

EVIDENCE_FLOOR = 15  # OP-16 advisory floor the recorded n=3 sits far below


def _json(p: Path) -> dict:
    if not p.exists():
        pytest.skip(f"{p.name} absent")
    return json.loads(p.read_text(encoding="utf-8"))


def test_the_prereg_stays_retired_not_runnable():
    """Property 1. A status flip back to FROZEN/ready re-admits an unreproducible number."""
    status = str(_json(PREREG).get("status", ""))
    assert "RETIRED" in status.upper(), (
        f"prereg status is {status!r}. It was retired 2026-09-02 as UNRUNNABLE AS FROZEN: "
        f"the hook its runner calls has never existed in any commit, so its recorded "
        f"CONTROL 28 / TREATMENT 26 scorecard cannot be regenerated. Re-freezing it as "
        f"runnable would put that number back in play as evidence."
    )


def test_the_correction_record_survives():
    """The forensics must travel with the file. A retired status with no reason attached is
    re-litigated by the next session that finds it."""
    rec = _json(PREREG).get("reopened_and_corrected_2026_09_02")
    assert isinstance(rec, dict), "the 2026-09-02 correction record was dropped from the prereg"
    for key in ("correction", "evidence", "what_this_means_for_the_recorded_verdict",
                "second_independent_reason_it_is_dead", "disposition", "live_exposure_this_leaves"):
        assert rec.get(key), f"correction record lost '{key}'"


def test_the_hook_is_still_absent_so_the_runner_still_cannot_run():
    """Property 2, first half. This is the FACT the retirement rests on, re-checked against
    the tree rather than trusted from the write-up. If someone builds the hook, this test
    fails LOUDLY and points at the sibling test below -- that is the intended handoff, not a
    false alarm."""
    if not LEVELS.exists():
        pytest.skip("levels.py absent")
    src = LEVELS.read_text(encoding="utf-8")
    assert "memory_levels_by_day" not in src, (
        "backtest/lib/levels.py now references memory_levels_by_day -- the hook has been "
        "built. Good, but the frozen prereg must NOT simply be re-run: its treatment is the "
        "side-blind 'nearest 6' rule that production replaced on 2026-07-27. Write a NEW "
        "prereg against the current per-side formula (see "
        "test_a_revival_must_target_the_live_formula_not_the_dead_one) rather than reviving "
        "this one, whose no_repick_clause forbids exactly that substitution."
    )


def test_a_revival_must_target_the_live_formula_not_the_dead_one():
    """Property 2, second half. Pins the DIVERGENCE that makes the frozen treatment obsolete,
    read from both real files -- so if production ever reverts to side-blind selection, this
    stops being true and the test says so."""
    if not (LIVE_MERGE.exists() and RUNNER.exists()):
        pytest.skip("live merge or runner absent")
    live = LIVE_MERGE.read_text(encoding="utf-8")
    assert "MEMORY_MERGE_CAP_PER_SIDE" in live, (
        "the live wire no longer caps per side. The 2026-07-27 directional-balance fix (J "
        "live-flagged: side-blind selection gave an all-resistance set with zero supports) "
        "appears to have been reverted -- if so the frozen prereg's treatment may match "
        "production again, and this retirement needs re-reading."
    )
    runner = RUNNER.read_text(encoding="utf-8")
    assert "MEMORY_CAP = 6" in runner, (
        "the frozen runner's constant changed. This file's whole argument is that the runner "
        "encodes the PRE-2026-07-27 rule (nearest 6, side-blind) while production caps 3 per "
        "side; editing the frozen runner in place is how a study silently becomes a different "
        "study."
    )


def test_the_scorecard_never_reads_as_a_usable_verdict():
    """Property 3. n=3 against an evidence floor of 15 was never a verdict even when it was
    believed reproducible; the file must keep saying so."""
    sc = _json(SCORECARD)
    verdict = str(sc.get("verdict", ""))
    assert "INSUFFICIENT" in verdict.upper(), (
        f"scorecard verdict is now {verdict!r}. It was NEGATIVE_INSUFFICIENT_N on n_effect=3 "
        f"against an OP-16 evidence floor of {EVIDENCE_FLOOR}. Promoting it to a decisive "
        f"verdict would rest a live flag on three trades from a run nobody can reproduce."
    )
