---
name: fable-differential
description: Differential diagnosis for root cause — hold MULTIPLE competing hypotheses and kill them with discriminating evidence instead of locking onto the first plausible story. Invoke for any bug/failure/anomaly investigation, especially repeated failures, "we already fixed this", heisenbugs, or when a previous fix didn't hold. Also when J says "root cause this", "differential", "why is this REALLY happening". The #1 gap this patches: premature closure — smaller models grab the first coherent explanation and stop looking; the first coherent explanation in this codebase has usually been wrong.
---

# FABLE-DIFFERENTIAL — never marry your first hypothesis

> Worked proof this matters: the 09:30 rogue entries had an OBVIOUS first story ("the 09:35 gate is mis-configured") that was WRONG — config was perfect. The truth (engine scoring on yesterday's bar; the floor checks bar-time, not wall-clock) was hypothesis #3, and only discriminating evidence found it. A model that stopped at hypothesis #1 would have "fixed" the config and been burned again next open.

## The procedure

**1. Freeze the symptom as observable fact** — one sentence with the exact artifact quoted (error text, ledger row, wrong number). Not "the gate doesn't work" but "ENTER at 09:30:03 carrying spy=746.26."

**2. Enumerate ≥3 mechanistically distinct hypotheses BEFORE gathering more evidence.** Force the divergence: config wrong / code never reads the config / code reads it against the wrong reference / input data is stale / a different actor placed it / the observation itself is wrong. If you can only produce one hypothesis, you don't understand the system enough — go read the path first. Write them down as a numbered ledger.

**3. For each hypothesis, name its DISCRIMINATING evidence** — the observation that would be true under THIS mechanism and false under the others. (H1 config-wrong → params.json shows a value ≠ 09:35. H2 dead-knob → value is right but grep shows no consumer. H3 wrong-clock → value right, consumer exists, but the compared timestamp is not wall-clock.) A test that all hypotheses pass is worthless — spend tool calls only on discriminators.

**4. Kill in cheapness order.** Check the cheapest discriminator first (one grep, one ledger row, one file read). Update the ledger explicitly: `H1 KILLED — params.json:32 = "09:35"`. Never silently abandon a hypothesis; never keep investigating one you've killed because you liked it.

**5. The survivor must earn it twice:** it explains the ORIGINAL symptom mechanically (one sentence, file:line) AND survives a minimal reproduction (unit repro / replay of the exact row). If the survivor can't be reproduced, reopen the ledger — including "the observation is wrong" (LastTaskResult=0 lied; `placed:true` lied; wrappers lie).

**6. Before closing: the second-instance check.** Ask "where ELSE does this mechanism live?" — the same tz-mixing, the same stale-input pattern, the same wrapper-swallows-exit-code. One grep for the class. (Bold's tz crash had a sibling risk in every datetime subtraction on the tick path.)

## Tells you're failing this skill
☐ You wrote a fix before writing the hypothesis ledger. ☐ All your evidence CONFIRMS your favorite (you never sought a discriminator). ☐ Your hypothesis count is 1. ☐ You're explaining away an anomaly that doesn't fit ("probably just flaky") instead of adding it as H_n. ☐ The "root cause" you're about to report contains the word "probably".

## Output contract
Report the LEDGER, not just the winner: every hypothesis, its discriminator, its kill-quote or survival. This makes your reasoning auditable and teaches the next session what was already ruled out — a killed hypothesis with its evidence is half the value of the investigation.
