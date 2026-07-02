# FABLE JUDGMENT SUITE — think like this, then act

> Reverse-engineered from Claude Fable 5's 2026-06-30 → 07-02 sessions (the pipeline audit → first trades → gate purge arc), at J's direction. This is not a summary — it is the PROCEDURE LIBRARY. A Sonnet/Opus session that follows these procedures produces Fable-quality work.
>
> **Loading rule:** any substantive Gamma session (conductor fire, evening session, audit, research run) reads THIS index + the one chapter matching its task TYPE before starting. CLAUDE.md and conductor.md point here. FABLE-HANDOFF.md (../FABLE-HANDOFF.md) is the compact state-map + roadmap; these chapters are the HOW.

| Chapter | Read when your task is… | Core skill |
|---|---|---|
| [01-INVESTIGATION.md](01-INVESTIGATION.md) | "why is X broken / not trading / behaving oddly" | evidence-first diagnosis; the money-path walk; the stale-clock hunt |
| [02-VALIDATION.md](02-VALIDATION.md) | "is this strategy/signal/change worth shipping" | not fooling yourself: pre-registration, nulls, FDR, kill ladders |
| [03-EXECUTION.md](03-EXECUTION.md) | "implement/apply/wire a change" | stage-then-apply, guard patterns, agent orchestration, commit discipline |
| [04-JUDGMENT-CALLS.md](04-JUDGMENT-CALLS.md) | any decision point: ship/kill/park/ask-J/trust-which-number | the decision trees, with this week's real calls |

**The one-sentence version of the whole suite:** never trust a claim you didn't verify this session, never ship a result that didn't survive an attempt to kill it, never leave a fix without a guard that REDs on regression, and never end a turn telling J something you haven't quoted evidence for.

**Why this exists:** in 3 days these procedures took the project from "never filled an order, every pipeline handoff broken, instruments lying green" to "16 fills/16 managed exits in one honest session, +$240 day, 6 armed setups, 4 same-day bug fixes, ~20 honest kills." None of that required a smarter model — it required not skipping steps. The steps are below. Don't skip them.
