---
name: fable-blast-radius
description: Pre-change consequence mapping — before editing anything, enumerate everything that READS, WRITES, or RACES the thing you're changing, and simulate the change through each consumer. Invoke before ANY edit to shared code/config/state (params keys, engine files, state-file schemas, scheduled tasks, prompts other agents read), before deleting "unused" things, and before running agents in parallel. Trigger phrases: "blast radius", "what does this touch", "is this safe to change". The gap this patches: smaller models fix locally and break globally — the correct local edit with an unmapped consumer is this codebase's second-favorite disaster.
---

# FABLE-BLAST-RADIUS — the change is the easy part

> Worked proofs: arming a 4th setup was "one params key" until the consumer walk found two same-tick fires could DOUBLE-FILL through flat-verify (fixed pre-ship because the radius was walked). Deleting the re-entry lock looked like a pure deletion until the walk found the tz-fix living INSIDE the deleted path and loop-state writers with external readers (dashboard, companion). The promoter "worked" for weeks writing a key with ZERO consumers — a blast radius of nothing is also a finding.

## The procedure

**1. Name the surface precisely.** Not "heartbeat_core" but "the `_SETUP_EXIT_OVERRIDES` dict shape" / "params key `X`" / "the schema of loop-state.json" / "rows in conductor-proposals.jsonl". Changes have consumers per-surface, not per-file.

**2. Enumerate READERS (grep, don't recall).** Search the repo for every consumer of the surface: code imports, key reads, file readers (dashboards, companions, prompts, scheduled scripts, tests, OTHER AGENTS' prompts). For state files check LoopStateModel-style contracts and the dashboard/companion libs. List them BY NAME in your response. Zero readers is a finding (dead surface — why are you changing it instead of deleting it?).

**3. Enumerate WRITERS and RACERS.** Who else writes this surface (daemons churn state files; the conductor commits hourly after-hours; J runs parallel sessions)? Will your edit collide with a scheduled fire, a running daemon holding the file, or another agent's staged patch (apply ORDER matters — patches are generated against a specific tree)? During RTH the live engine is a racer on every file it reads: the airlock rule (no edits 09:30–15:55) exists because of this.

**4. Simulate the change through each consumer.** For each reader: what does it see the tick AFTER your change? (New key absent → defaults engaged — are the defaults sane? Key renamed → old readers silently get None — the dead-knob factory. Schema loosened → contract tests red. Deleted path → who catches its exceptions now?) For each writer: does your change survive their next write, or will it be clobbered/regenerate (editing generated files is writing on sand)?

**5. Walk one level of SECOND-order effects for behavior changes.** New entries armed → more positions → exit manager load, PDT day-trade count, risk-cap interactions, kill-switch proximity, funnel expectations. Gate removed → what did that gate incidentally suppress (the re-entry lock's deletion re-exposed the churn pathology — known BEFORE shipping because this walk was run, so the cooldown A/B was queued alongside).

**6. Decide the containment.** Every change ships with: the revert path (one key / git revert hash), the guard that REDs on the failure mode found in steps 4–5, and — if consumers are external (dashboard, J's eyes) — additive changes over breaking ones (add keys, don't rename; the loop-state fix added derived fields precisely so zero readers needed edits).

## Output contract
Before the edit, your response contains: surface → readers (named) → writers/racers (named) → the 2–3 concrete break scenarios you simulated → the containment (guard + revert). If that list is empty, you didn't look — this codebase has ~60 scheduled tasks, 6 accounts, parallel agents, and daemons; something always reads it.

## Tells you're failing this skill
☐ You said "it's just one line/key." ☐ Your consumer list came from memory, not grep. ☐ You're editing a file a daemon regenerates. ☐ You're deleting something because it "looks unused" without the zero-reader grep. ☐ Two agents (or you and J's other session) have the same file in scope right now and you haven't stated the coordination plan.
