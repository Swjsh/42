# Gamma Autonomy — The Next Level (Closing the Last Mile)

> **Date:** 2026-06-21 · **Author:** Gamma (25-agent grounded gap analysis, adversarially verified)
> **Premise:** Gamma is already ~80% autonomous. This plan closes the four specific gaps that stop it from *truly* working on the project itself — unattended, safely, and measurably improving.
> **Companion read:** [GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md](GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md) (the prior audit — much of it now shipped).

---

## What's ALREADY autonomous (verified, do not rebuild)

The recon confirmed — with citations — that the core loop exists and runs:

- **The conductor fires hourly** (`Gamma_Conductor`, 18:00–07:00 ET, Opus, ~$1.50/fire). Enabled 2026-06-20; **12 consecutive successful fires** on 2026-06-21, each picking one bounded task, fanning out specialist agents, validating, and updating STATUS/queue. *(This was "the never-running conductor" — it now runs. The gap of "J was the conductor by hand" is closed.)*
- **It ships engine-benefit work autonomously** — validators, skills, lessons, backtests — via the OP-11/OP-22 auto-ratify gate (OOS+ · WF≥0.70 · stable · no-regression · scorecard filed). No J gate. Proven: 8 engine-benefit items shipped across the 06-21 fires, zero doctrine touches.
- **37 autonomous scheduled tasks** run the live engine, the kitchen R&D loop (4,226 cook items), health beacons, and the Discord decision bus.
- **A guard exists** (`gamma-companion/lib/guard.js`): spawned sessions cannot touch CLAUDE.md / params / heartbeat / live orders.
- **Params already have shadow mode** (OP-11 Karpathy: prod + candidate run in parallel for days before auto-ratify).
- **Lessons graduate to code** (`backtest/tests/test_graduated_guards.py`), and contract tests exist.

**So the engine of autonomy turns.** What's missing is the *last mile of the loop*, its *safety rails*, *sharper direction*, and a *learning metric*. Four phases, in dependency order.

---

## The four gaps (each verified as a real, not-already-built gap)

### Phase 1 — The Actuator: close the approval → apply → commit → rollback loop  ★ highest leverage

**The single biggest unlock.** Today the loop runs right up to the last step and then *stops*: the conductor PROPOSES a doctrine/params/heartbeat change → pings J on Discord → J taps **Approve** → the approval is *recorded* in `conductor-approvals.jsonl` / `companion-decisions.jsonl` … **and then nothing reads it.** J still has to hand-edit the file. The approval just sits there. (Verified gaps #2, #3, #10, #11, #12 — all the same broken link.)

Build the missing **Actuator** — a small scheduled responder (sibling to `Gamma_DiscordResponder`) that closes the chain:

1. **AutoApplyResponder** — reads newly-`approved` proposals, executes each proposal's structured `apply` field (the file edit it was always meant to encode), and marks it `applied`. *Approval becomes fire-and-forget, as designed.*
2. **Snapshot-before-apply** — copy the target file(s) into `automation/state/.autonomy-snapshots/{proposal_id}/` before editing. This is the rollback substrate.
3. **Auto-commit** — stage the changed files and commit with a message built from `proposal_id + title + "(autonomous, J-approved)"`. (Today nothing commits autonomously — changes sit unstaged.)
4. **Change-audit log** — append a `before/after` diff + who/when/why to `automation/state/autonomy-changelog.jsonl`. This is J's "what changed while I was away" forensic trail.
5. **One-tap rollback** — a Discord/companion command `revert <proposal_id>` that restores the snapshot and commits the revert. The off-switch for any single change.

**Why it's the keystone:** it converts every doctrine/params proposal from "Gamma drafts, J hand-edits" into "Gamma drafts, J taps approve, Gamma applies+commits+can-revert." It's also what makes the *rest* of the plan safe to turn on. **Effort: M. Leverage: HIGH.**

> **Structured `apply` field:** proposals must carry a machine-applicable change (target file, anchor, old→new, or a patch), not just prose. Part of this phase is upgrading the proposal schema so every proposal is *actuatable*.

### Phase 2 — The Safety Gate: make autonomous commits unable to break `main`  ★ must ship WITH Phase 1

The pieces of a safety net exist but are **orphaned** — not wired as gates. The conductor validates tests *in-band* during a fire, but there is **no VCS-level gate**: if the gym harness has a latent bug or a test is bypassed, a broken commit reaches `main`. (Verified gaps #4, #7, #8, #9.)

Wire the existing checks into real gates:

1. **Pre-commit hook** (`.git/hooks/pre-commit` via a tracked installer) that runs, and *blocks the commit on failure of*: `test_verify_committed` (today post-hoc, test-only — wire it pre-commit so untracked-but-referenced files can't ship), the **graduated-guards** suite, and the **params↔code contract tests** (today orphaned from build-time — gap #7). Nothing the Actuator commits can violate a graduated lesson or a contract.
2. **A CI gate** (GitHub Actions) on push: re-run the gym + guard + contract suites as a second, independent line of defense (the pre-commit hook is local and bypassable; CI is the backstop). Gap #4.
3. **Staged rollout for *code*** — validators/skills/lessons currently ship to production on a single test pass (params already get shadow mode; *code* does not — gap #9). Add a `strategy/staging/` holding area + one conductor fire of soak before promotion, mirroring the param shadow pattern.

**Hard sequencing rule:** **Phase 2 lands before Phase 1 is switched on.** You do not give Gamma the power to edit + commit its own doctrine until the commit gate provably can't ship breakage. Build the gate, then open the actuator. **Effort: M. Leverage: HIGH (safety-critical).**

### Phase 3 — Sharper Direction: ROI-ranked picking + real idle-drive

The conductor picks the next task by **fixed tier labels**, not value. A $10 Opus spec-write competes with a $0 "verify-now" Python fix on tier alone — no ROI. And when the backlog empties, it *seeds* candidates but **doesn't execute the best one** — it just adds to the pile. (Verified gaps #0, #1, #6 — the documented "find direction autonomously" pain point.)

1. **`task_scorer.py`** — score every ready queue item by a real vector: `leverage × (blocking_count, path-to-money?, engine_benefit_class) ÷ cost_usd`, with staleness and "verify-now ≤60min" boosts. STAGE 1 of the conductor picks the **max-score** item, not the top tier label. (Gap #6's true remaining: this module doesn't exist; the tiebreak is qualitative.)
2. **Idle-drive executes** — when the backlog is genuinely empty, after brainstorming candidates the conductor immediately **scores and executes the single highest-EV one** rather than stopping. Climb the search-space ladder (signal → structure → DTE → instrument) per the strategy-direction backlog when a vein is dry. (Gap #0.)

**Effort: S–M. Leverage: MED** (but this is the difference between "does assigned work" and "self-directs toward the highest-value work").

### Phase 4 — The Learning Metric: prove each cycle is net-better (OP-22, measured not asserted)

The system learns (graduates lessons) but **doesn't measure whether it's improving.** Per-fire outcome data is scattered in prose across three logs; there's no net-improvement number and no "did a graduated lesson regress" audit. "Always-on = always-improving" is currently an *assertion*. (Verified gaps #5, #13, #14.)

1. **`conductor-outcomes.jsonl`** — one structured row per fire: `{fired_at, cost_usd, task_id, items_drained, items_added, lessons_shipped, tests_delta, regressions}`. A unified outcome schema replacing the prose scatter (gap #13).
2. **Net-improvement metric** — a rolling score (work drained − regressions − thrash) the conductor reads each fire and STATUS surfaces. Anti-thrash: penalize re-opening recently-closed items.
3. **Lesson-regression audit** — a loop that runs the graduated-guard suite as a *"did any lesson re-violate since graduation"* check and, on a hit, **auto-files a `LESSON-REGRESSION` queue item** (today the suite fails only at aggregate level, with no per-lesson queue item — gap #14). Plus the lesson→code map for drift audits (gap #5).

**Effort: M. Leverage: HIGH** (this is what makes the loop *converge* instead of churn — and gives J a single "is it getting better?" number).

---

## Sequencing & the one rule

```
Phase 2 (safety gate)  ──►  Phase 1 (actuator)  ──►  Phase 3 (direction)  ──►  Phase 4 (metric)
   build the gate          open the loop            aim it better            prove it improves
```

**The rule:** the safety gate (Phase 2) ships *before* the actuator (Phase 1) is switched live. Everything else can proceed in parallel once the actuator is safe. Phases 3 and 4 are independent of 1–2 and can be built alongside.

**All four stay inside the existing rails:** after-hours only (no heartbeat starvation), fail-open (never lock J out — OP-32 scar), one bounded task per fire, and J keeps the off-switch (now a *real* one-tap `revert`, not a hope).

## Recommended first move

**Build Phase 2 + Phase 1 together as one unit** — the safety gate and the actuator it protects. That single unit is the keystone: it turns "Gamma proposes, J hand-edits" into "Gamma proposes, J taps approve, Gamma safely applies + commits + can revert." It's the highest-leverage change on the board and unblocks true unattended self-modification. Phases 3 (ROI direction) and 4 (learning metric) follow and can run in parallel.
