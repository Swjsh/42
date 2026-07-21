# DOJO × EOD pipeline — the nightly film room (Fable brainstorm, 2026-07-21, J-directed)

> J: "brainstorm running the EOD pipeline in line with the dojo now that we have candle replays."
> Extends DOJO-REPLAY-TRAINING-SPEC.md. Build owner: Sonnet (queue item EOD-DOJO-EXHIBIT-MANIFEST).

## The idea in one line

The EOD pipeline stops being a text report and becomes a **pre-loaded film-room session**: every
close, the day's misses/blocks/wins are auto-extracted as EXHIBITS (bar timestamps + engine state),
and a dojo session manifest is written so J + Sonnet can sit down, hit replay, and jump straight
to the 4-6 moments that mattered — engine's mind on screen, J's judgment captured as directives.

## Why this composes from parts that already exist

- **TradeAutopsy (16:15 ET)** already does learn-from-losses counterfactual replay → hypothesis
  queue. It produces WHAT went wrong; the dojo gives it a WHERE-TO-LOOK surface J will actually use.
- **core-decisions.jsonl** already carries per-minute verdict/scores/triggers/gates/context —
  exhibit extraction is a pure read (zero LLM, $0).
- **The dojo session machinery** (session/step/whisper/directive/harvest) is built; a manifest is
  just a pre-seeded agenda for it.

## Exhibit extraction rules (deterministic, from the day's decision rows)

1. **BLOCKED-TRIGGER exhibits** — verdict SKIP_* while `triggers` is non-empty (the engine FIRED
   and a gate refused). Record: gate name, score, level, and the forward SPY path (did the block
   save or cost money — the OP-33(d) burden-of-proof number). TODAY'S EXAMPLE: 12:21-13:55
   SKIP_ELITE_BULL_LEVEL_RECLAIM ×20, bull=11, level_reclaim+confluence @748.26, SPY 748.47→748.97.
2. **SCORE-HIGH-NO-TRIGGER exhibits** — stretches where bull_score>=9 or bear_score>=9 with
   `triggers=[]` (the engine FELT it but has no vocabulary for the pattern). TODAY: 11:01-11:05
   bull 9-10 at J's double-bottom+engulfing entry; 12:06-12:10 bull 10.
3. **EXTRA-LANE FILL exhibits** — every extra_exec PLACED (win or lose) with its exit.
4. **J-CALLED exhibits** — any j-intent/manual fill that day.
5. Cap at ~6 exhibits/day, ranked: blocked-triggers first (real money attributable), then
   score-high-no-trigger, then fills.

## The manifest (written at EOD, consumed by the session agent)

`automation/state/dojo/session-briefs/YYYY-MM-DD.md` — per exhibit: bar time(s) to replay to,
the engine's exact read (verdict/scores/gate/levels), the question for J ("should this have
traded? which arms? what stop?"), and blank directive stubs. The interactive session then walks
ONLY those bars (10-min film room, not a 78-bar grind), captures J's calls, and the harvest
routes Lane A (vocabulary/capability gaps) vs Lane B (gate/policy hypotheses → pre-reg).

## Wiring (small, after-hours)

- New `setup/scripts/dojo/exhibit_extractor.py` (pure read of the day's rows → manifest md).
- Hook: run from the existing EOD chain (after TradeAutopsy 16:15, so its counterfactuals can be
  cited per exhibit), Task-Scheduler registered, reaper-exempt pattern.
- The runbook gains a "film room" mode: `start --replay-day <today> --brief <manifest>`.

## What this is NOT

Not a new analytics engine, not autonomous policy-changing. It's an AGENDA GENERATOR that turns
the data we already log into the sit-down J actually wants. All ship decisions still flow through
Lane B pre-reg gates.
