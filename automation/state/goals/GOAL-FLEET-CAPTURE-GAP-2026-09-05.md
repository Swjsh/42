# GOAL: FLEET-CAPTURE-GAP-2026-09-05

> Opened by Fable 2026-09-05 from the right-tail capture backfill (commit 915c057d,
> analysis/right-tail/SUMMARY.md): over 36 real waves 2026-08-01..09-04, safe-2 captured 80.6%,
> risky-1 72.2%, bold-2 61.1%, safe-3 58.3%. The arms consume ONE shared signal seconds apart; a 22-point
> capture spread between safe-2 and safe-3 is not market noise, it is a gate or a race. The dominant
> refusal bucket was "no matching fleet decision" (30) -- the fleet arm never fired near the wave --
> then NOT_FLAT (4). This goal names the mechanism per missed wave and files the fix as a prereg.

## DONE-WHEN
`analysis/right-tail/CAPTURE-GAP-2026-09-05.md` (+ .json) attributes EVERY missed wave per arm
(36 waves x 4 arms, from `analysis/right-tail/ledger.jsonl`) to exactly one mechanism with the
quoted evidence row: (1) fleet gate_override refused it (`min_triggers 2` / `require_confluence_or_
sequence`) -- quote the fleet decisions row at that tick; (2) settlement / same-day-entries cap;
(3) NOT_FLAT (still holding a prior position -- name the position and its exit stage); (4) risk_gate
deny (which code); (5) the arm's fleet tick did not run within 2 min of the core ENTER (scheduler
cadence / outage -- cross-check engine_gaps); (6) sizing SIZE_BELOW_MIN / affordability; (7) took it
late (>2 ticks) and it no longer cleared 1.3x from the late entry. Each mechanism gets a dollar
figure = the wave's realized multiple on the arm that DID take it x the missing arm's standard size.
Any mechanism whose dollar figure exceeds $1,000 over the window gets a prereg for the 10-30 checkpoint
(a gate loosening is an EXPANSION) or, if it is a defect (a race, a stale read, a cadence hole), a
fix filed as a normal engine bug with a RED-proofed guard -- defects are not frozen.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: read-only instruments, preregs and packaged-but-unapplied
  changes only. Nothing in `setup/hooks/doctrine.py` FROZEN_TRADING_PATH is edited by this goal; a
  package is applied ONLY on its checkpoint day, by the conductor, with GAMMA_FREEZE_OVERRIDE in the
  invocation, after the packet reads RULE MET.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. Fable/Opus = spec + adjudication only.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation are the only
  sanctioned continuation paths.
- Reuse before rebuilding; every number reported is quoted from a command run in the same fire (OP-33).

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] F1 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Join: for each (wave, arm) in `analysis/right-tail/ledger.jsonl` with taken=false, pull
  the arm's `automation/state/fleet/<arm>/decisions.jsonl` rows within +/-3 min of the wave anchor
  (bold-2 is a core account: use core-decisions.jsonl `account=="bold"`), the fills-ledger state
  (open position?), and `automation/state/engine-gaps` findings for that window. Write the join to
  `analysis/right-tail/capture-gap-join-2026-09-05.json`. DONE-WHEN: row count == number of missed
  (wave, arm) pairs; zero rows without evidence.
- [~] F2 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Attribute: classify every row into mechanisms 1-7 with the quoted row; compute the dollar
  figure per mechanism per arm. DONE-WHEN: the .md table sums to the missed-wave count per arm.
- [~] F3 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Defects: any mechanism-5 (cadence/race) or stale-read finding is a bug -- root cause in one
  sentence, fix in the fleet executor's NON-frozen periphery or the scheduler, RED-proofed guard.
  If the fix touches a FROZEN file, file it as a kill-type prereg for 09-29 instead and say so.
- [~] F4 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Preregs: for each mechanism 1/2/4/6 above the $1,000 line, write
  `analysis/recommendations/prereg-fleet-capture-<mechanism>-10-30-2026-09-05.json` (frozen hypothesis,
  the exact knob, kill criteria on the right-tail ledger's forward window, revert line). Add each to
  `setup/scripts/checkpoint_packet.py`'s inventory so the 10-30 packet reads it.
- [~] F5 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Render: capture rate per arm + top mechanism per arm on the cockpit right-tail tile
  (payload via gamma_home.py; DOM read quoted).

## J-DECISIONS
- None. Preregs wait for 10-30; defects ship with revert lines.

## PROGRESS LOG
- 2026-09-05 06:5x ET -- authored by Fable (EOD-audit session); queued on the ladder.
## HONEST STATE
Queued. Nothing started.
