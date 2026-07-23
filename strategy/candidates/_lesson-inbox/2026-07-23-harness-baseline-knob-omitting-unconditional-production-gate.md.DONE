## Candidate lesson: a disclosed harness-baseline knob that omits a gate which is UNCONDITIONAL in production is not the production number -- quote the refinement cell, not the baseline

**Symptom:** The 2026-07-23 kitchen extra-lanes full-history harness measured
`double_bottom_base_quiet`'s BASELINE cell (NOT_NEAR_NAMED proximity gate omitted, matching the
detector's own earlier published "simplified scan" precedent) at -\$2,564 tuning / -\$940
held-out (-\$3,504 combined, 1/4 gates) over 386 days. This number got quoted in
`automation/overnight/queue.md` as "a live-armed lane with a deeply negative pattern" and used to
motivate considering a DISARM of a real live-paper-armed setup. But `double_bottom_base_quiet_
watcher.py`'s Gate 6 (the same NOT_NEAR_NAMED \$0.50 proximity check) is hardcoded and
UNCONDITIONAL in the live watcher -- every real signal passes through it, no enable flag. The
harness's own pre-reg had already disclosed the baseline omits it, AND had already run the
correctly-gated refinement cell (`not_near_named=True`) in the same results file -- it just wasn't
the number that got quoted downstream. The correctly-gated cell tells a completely different
story: n=21 (the gate alone kills ~82% of the ungated population), total +\$8.95, gates_passed
2/4, p_raw=0.988 -- near-flat noise, not a deeply negative pattern. A same-night conductor fire
almost acted on the wrong cell's headline number.

**Root cause:** A full-history harness that adds "one refinement knob per lane" to explore whether
a gate helps is, BY DESIGN, running its BASELINE cell without that gate whenever the gate is the
refinement axis -- even when that same gate is not optional in the live/production watcher. The
pre-reg disclosed this precisely and correctly (`levels_caveat` + `detectors_reused_verbatim`
explicitly say the baseline omits it and why) -- the disclosure did its job. The gap is
downstream: nothing forces a READER (human or a future conductor fire) to check whether a grid
axis's baseline value equals production's actual live value before quoting the baseline cell's
P&L as "the live-armed lane's number."

**Fix pattern (for future harness-reading fires, and for kitchen harness authors):** When a
kitchen/edge-matrix harness's grid explores a knob whose baseline is NOT the production/live
value (most commonly: a gate that's mandatory in the live watcher but treated as an optional
refinement axis in the study), any downstream consumer (queue item, STATUS.md line, disarm/arm
decision) MUST quote the cell whose params match the live-armed config, not the cell labeled
`|BASELINE` by convention. Ideally: harness authors should label the grid's "matches current live
config" cell distinctly from "matches this detector's OWN historical simplified-scan precedent"
when the two diverge -- today `|BASELINE` conflated both meanings for `double_bottom_base_quiet`
specifically (baseline = the detector's old published precedent, NOT live config), while for the
other 3 lanes in the same harness `|BASELINE` correctly meant "live config." That naming collision
is the sharpest lever: a harness's own README/results file should never let one cell_id suffix
mean two different things across lanes in the same run.

**Suggested graduation:** a lightweight assertion/lint in future harness result-writers: if a
lane's watcher module hardcodes a gate unconditionally (detectable by grep -- no corresponding
params.json enable key), the harness MUST either (a) apply that gate in its baseline cell too, or
(b) rename the cell that omits it away from the generic `|BASELINE` suffix so a downstream reader
can't mistake it for "the live config." This is a documentation/labeling discipline fix, not a
runtime code-path fix -- low urgency, MED effort, author's call whether to encode as a real test
or just a harness-authoring convention note in `markdown/research/BACKTESTING-PLAYBOOK.md`.

**Evidence:** `analysis/kitchen/prereg-extra-lanes-fullhist-2026-07-23.json` (disclosure),
`analysis/kitchen/extra-lanes-fullhist-results-2026-07-23.json` (both cells, lines ~298-369),
`backtest/lib/watchers/double_bottom_base_quiet_watcher.py` (Gate 6, unconditional), resolved in
`automation/overnight/queue.md` DOUBLE-BOTTOM-DISARM-DECISION 2026-07-23 ~01:55 ET.

**Cross-reference:** closest existing class is C14 (dead/translated-but-unapplied knobs) and C7
(silent success is failure) -- this is the inverse of C14: not a knob that's dead in production,
but a knob that's ALWAYS-ON in production being treated as optional in a study, with the
always-on state hiding behind conventional `|BASELINE` labeling.
