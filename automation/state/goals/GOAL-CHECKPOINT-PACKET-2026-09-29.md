# GOAL: CHECKPOINT-PACKET-2026-09-29

> Opened by Fable 2026-09-05. The September freeze has one safety checkpoint (2026-09-29, kill-type
> risk reductions only) and one full checkpoint (2026-10-30). Tonight's adjudications produced a
> dozen decisions that must be read THEN, with their evidence attached. Left in scattered prereg
> files they will be re-derived by hand on the day (the 2026-08-20 STATUS scar). This goal makes the
> checkpoint a mechanical read.

## DONE-WHEN
`markdown/planning/CHECKPOINT-2026-09-29.md` is GENERATED (not hand-written) by
`setup/scripts/checkpoint_packet.py` from the prereg JSON/MD files, one row per decision with:
prereg path, frozen hypothesis, the decision rule verbatim, the forward-window numbers as of the
generation date (pulled from the ledger each prereg names), the reversible one-line action, and a
mechanical verdict column (RULE MET / RULE NOT MET / INSUFFICIENT N) -- regenerated nightly by
`Gamma_CheckpointPacket` (23:30 ET) so the 09-29 read is the last night's file. Every decision below
appears with a non-null verdict on 2026-09-28's generation.

Decisions in scope (all filed tonight or earlier): TIGHT-LADDER control #4 max_same_day_roundtrips
4->5 (kill-type? no -- it is an expansion; the packet must say so and route it to 10-30 unless the
prereg's own rule classifies otherwise); control #5 -$400 stop (keep); SCORE-LADDER-V2 shadow
retirement (KILLED tonight: extras -$13.8K/arm over 28 sessions -> retire `Gamma_BoldTierRail` /
ladder-rung shadow = a reduction, eligible 09-29); f10 vol_baseline session reset
(prereg-f10-vol-baseline-session-reset-10-30); VIX bull hard-cap unblock shadow read;
SPY signal at 1-2 DTE via weekly-1; FILL-MODEL-UNIFICATION step 2 rescore prerequisites;
tickers theta_budget cadence; catastrophe-cap + day-throttle forward shadows (already accruing).

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: read-only instruments, preregs and shadow work only.
  Nothing in `setup/hooks/doctrine.py` FROZEN_TRADING_PATH is edited; any knob change the evidence
  indicts is filed as a prereg for the 09-29 (kill-type reduction) / 10-30 checkpoint, never shipped.
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. Fable/Opus = spec + adjudication only.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation are the only
  sanctioned continuation paths.
- Reuse before rebuilding: name the existing script/ledger each item composes; never a parallel
  instrument for a question an existing organ already answers.
- Every number reported is quoted from a command run in the same fire (OP-33); UNVERIFIED stays labeled.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] C1 (WIP 2026-09-05 05:5x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Inventory the decisions: `analysis/recommendations/checkpoint-2026-09-29-inventory.json`
  listing every prereg whose status/text names the 09-29 or 10-30 checkpoint (grep both tokens
  across analysis/recommendations/), each tagged reduction | expansion | shadow-read | tooling, with
  the ledger file its rule reads. DONE-WHEN: the nine decisions above are all present; any extra
  ones found are listed too.
- [~] C2 (WIP 2026-09-05 05:5x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- `checkpoint_packet.py`: for each inventory row read the named ledger, compute the rule's
  numbers as of today (reuse each prereg's own scorer where one exists -- stop_mode_shadow_ledger,
  day_throttle_shadow, right_tail_capture once R4 lands, etc.), emit verdict RULE MET / NOT MET /
  INSUFFICIENT N with the n. Fail-open per row (a broken scorer = one UNKNOWN row, never a crash).
  Tests with two fixture preregs, RED-proofed.
- [~] C3 (WIP 2026-09-05 05:5x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Generate `markdown/planning/CHECKPOINT-2026-09-29.md` (and a `-2026-10-30.md` twin for
  the expansion rows); link both from markdown/planning/ROADMAP.md and markdown/README.md index;
  MAP.md routing entry via the generator, never by hand.
- [~] C4 (WIP 2026-09-05 05:5x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Register `Gamma_CheckpointPacket` 23:30 ET daily (installer pattern, registry row,
  guards green, State=Ready). DONE-WHEN quoted.
- [~] C5 (WIP 2026-09-05 05:5x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Cockpit: the packet's verdict counts (met / not met / insufficient) render on the
  Autonomy tile with a link to the file (headless screenshot quoted).

## J-DECISIONS
- None now. On 09-29 J reads the packet; reductions ship under Gamma-decides with revert lines,
  expansions wait for 10-30 regardless.

## PROGRESS LOG
- 2026-09-05 04:2x ET -- authored by Fable (EOD-audit session); queued on the ladder.
## HONEST STATE
Queued. Nothing started.
