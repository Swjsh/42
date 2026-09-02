## Candidate lesson: a "genuine fork" is often a pre-registered decision nobody re-read

**Symptom.** A 2026-09-02T05:15 ET Opus entry filed `CRITERION-5-WINDOW-HAS-ZERO-SLACK` as an
open fork requiring a written decision: "defend the 09-29 reading... or state that 10-30 was
always the only reading that mattered." It read as genuinely undecided.

**Root cause (one sentence).** The decision had already been made in writing, before any
result existed, in `automation/state/prod-shadow-designation.json` (written 2026-09-01T20:22
ET) -- the fork-filer checked the go-live gate's *output* (`analysis/go-live-gate.md`, which
does correctly render 09-29 as the pass bar and 10-30 as "disclosure only") but did not check
the *designation file that produced that output's window*, so the pre-registration's own
explicit sentence ("the PREREG-TIGHT-LADDER 40-day clock... is tracked as an EXTENDED
disclosure view only -- it never substitutes for or lowers this shorter, harder pass window")
was never quoted before the fork was filed.

**The generalizable pattern.** Before filing (or acting on) a "genuine fork with no doctrine
default" (OP-0 exception #4), check whether a `*-designation.json` / `*-prereg.md` /
`PREREG-*.md` file already pre-registered the answer. A pre-registration written *before* the
evidence it governs existed is the strongest form of "already decided" this project
recognizes (OP-11: never soften a bar after seeing which side it blocks) -- it should always
outrank re-litigating the question from a downstream report or a system-reminder's shorthand.
Two clocks sharing an end date by coincidence (the Sept config-freeze checkpoint and the
prod-shadow window both landing on 09-29) is exactly the kind of surface-level match that
makes a settled question look open.

**Suggested guard/practice.** Not a code assertion (this is a research-judgment habit, not an
invariant a test can check) -- but worth a one-line addition to the FABLE-ESCALATION guidance
in `conductor.md`'s STAGE 1: *before* filing a "DECIDE, in writing" fork item, grep
`automation/state/*designation*.json` and `analysis/recommendations/PREREG-*.md` for the same
subject; if a pre-registration already answers it, that IS the answer, not a fork.

**Resolved by:** `automation/overnight/queue.md` `CRITERION-5-WINDOW-HAS-ZERO-SLACK` item,
2026-09-02 ~05:40 ET conductor fire (SHIPPED note quotes the designation file verbatim).
