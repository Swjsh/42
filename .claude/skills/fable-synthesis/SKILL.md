---
name: fable-synthesis
description: Ruthless synthesis — turn a pile of findings/results/agent-reports into the 3 things that matter, ranked, with kills stated and a decision at the top. Invoke when holding multiple agent reports, a long investigation's outputs, audit findings, or brainstorm output that must become a plan; when writing any brief/EOD/summary for J; when a session must hand off to the next one. Trigger phrases: "synthesize", "what actually matters", "rank these", "give me the so-what". The gap this patches: smaller models LIST — everything at equal weight, reader does the thinking; Fable RANKS, KILLS, and DECIDES — the summary IS the judgment.
---

# FABLE-SYNTHESIS — a list is an unfinished thought

> Worked proofs: 15 brainstormed alpha ideas → adversarial judge → 7 ranked survivors with a #1 that turned out to be a live bug worth fixing before the open (the ranking WAS the discovery). Seven recon agents' 100+ findings → "the 8 breaks" table → J could act in one read. The gate audit's 30 gates → "one is yours, two are bugs, the veto has never fired once" — three sentences that carried the whole report. Compression under a decision question is where the intelligence shows.

## The procedure

**1. Fix the DECISION QUESTION first.** Synthesis without a question is a book report. Write it: "what do we ship tonight?", "is this edge real?", "why aren't we trading?". Every finding is then ranked by how much it moves THIS question — not by how interesting it was to discover or how hard someone worked on it.

**2. Force-rank, never bucket-dump.** Order findings by decision-weight. The test for the top item: if J reads ONLY the first sentence, does he know the most important thing? (Not the first chronologically, not the biggest artifact — the thing that changes what happens next.) Sunk effort is not weight: a week-long study that changes nothing ranks below a one-line bug that costs money tomorrow.

**3. State the kills as first-class results.** What was ruled OUT, with the nail named, ranks alongside what was found — a clean kill redirects all future effort and prevents zombie resurrection. "Shotgun dies at 2c spread; futures seeds sign-flip on regime; the veto has never vetoed" did more for the roadmap than most positives.

**4. Merge duplicates ACROSS sources; flag conflicts, don't average them.** Three agents reporting the same break = ONE finding (with the strongest evidence cited), not three bullets. Two sources disagreeing = a named CONFLICT with your adjudication (which number wins and why — accounting? window? harness?) or an explicit unresolved flag. Never let a contradiction sit silently in the same summary.

**5. Every synthesis ends in a decision block:** DO-NOW (ranked, with owner: me/agent/conductor/J-only) · KILLED (with nails) · PARKED (with re-open conditions) · OPEN CONFLICTS/UNKNOWNS (with the probe that resolves each). If the decision block is empty, the synthesis failed — go back to step 1.

**6. Compression discipline:** the whole synthesis in ≤1 screen; detail lives in linked files, not inline; complete sentences (no arrow-chain shorthand the reader must decode); numbers carry units and n's; no finding without its evidence pointer. If two findings need the same caveat, the caveat appears once, prominently — not as fine print under each.

**7. Write for the NEXT reader's first 30 seconds** — J catching up, or a fresh session inheriting the work. They didn't watch the process: no internal codenames without definition, no "as mentioned above" across context they don't have, and the state they're inheriting (what's running, what's owed, what's dangerous) stated explicitly at the end.

## Tells you're failing this skill
☐ Your summary has >5 top-level bullets at equal weight. ☐ The first sentence is background, not the verdict. ☐ Two of your bullets are the same finding from different sources. ☐ A contradiction between sources is present but unmentioned. ☐ There's no explicit kill list. ☐ The reader must open another file to know what to DO. ☐ Effort is masquerading as importance anywhere in the ranking.
