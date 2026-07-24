---
name: project-twin-doctrine-first-deploy-drafted-2026-07-23
description: TWIN-DOCTRINE-FIRST-DEPLOY drafted 2026-07-23 (conductor) — CLAUDE.md one-liner folding twin-first-deploy pending J ratification, not yet shipped
metadata:
  type: project
---

TWIN-PROGRAM.md's last open "Build order" item ("Doctrine: CLAUDE.md one-liner proposal")
was drafted 2026-07-23 by a conductor (AFTERHOURS) fire — the queue item
`TWIN-DOCTRINE-FIRST-DEPLOY` (MED, doctrine, propose-only). It is a DRAFT, not shipped:
CLAUDE.md doctrine edits stay J-first per rail-4 (the paper-trading-path carve-out does
not cover CLAUDE.md itself).

**What was proposed:** one sentence appended to existing OP-31 (folds into the Kitchen
bullet rather than a new numbered OP, to avoid extra context-budget cost): "any new
watcher/detector/exit-lifecycle feature runs 24-48h on the 24/7 crypto twin (paper,
mechanism-validation only — twin P&L is never SPY evidence) before touching a SPY
execution path." This formalizes practice the `twin_gauntlet_conductor_hook.py` has
already been advisory-enforcing since B2 (2026-07-11) — not a new behavior, a doctrine
anchor for an existing one.

**Where the full draft lives:** `markdown/planning/TWIN-PROGRAM.md` → "Doctrine proposal"
section (bottom of file). Proposal filed at `automation/state/conductor-proposals.jsonl`
id `gp-2026-07-23-twin-doctrine-001` (apply_ops targets the exact OP-31 string, no
`eval_bar_cleared` since this is doctrine not a validated edge — it will NOT auto-apply).
Discord ping + companion wrist-card both queued same id.

**Why: [[project_crypto_twin_requirement_2026_07_10]]'s standing rule (twin=mechanism,
never SPY evidence) plus the observed practice already running via the gauntlet hook —
this closes the gap between "we do this" and "it's written down."

**How to apply:** if J approves (`ship gp-2026-07-23-twin-doctrine-001` on Discord, or
wrist tap), the AutoApply actuator performs the edit + safety gate + commit — check
`conductor-proposals.jsonl` status field before assuming it's still pending, and check
CLAUDE.md's own OP-31 text directly rather than trusting this memory once ratified (this
memory is a snapshot of the DRAFT state, not living truth). Context-budget note carried in
the proposal: CLAUDE.md was YELLOW 8848/9000 (98%) at draft time; the fold is ~60 tokens
so lands ~8923/9000 — still YELLOW, near-zero headroom left for the next addition. A
context-leanness trim pass is due again soon (last one 2026-07-21), independent of this.
