# GOAL: DOCTRINE-CODE-PARITY-SWEEP-2026-09-05

> Opened by Fable 2026-09-05 11:xx ET. GOAL-EXIT-SHAPE-PARITY found two doctrine claims the code does
> not honour (runner target 2.5x; TP1 0.8 on Safe "ratified 2026-06-28, pk-2026-06-28-001") and one
> params surface (top-level exit keys) that is vestigial on the live path. Lesson class C14 says
> such knobs are found one at a time, months late. This goal sweeps ALL of them once and leaves a
> guard so the next drift fails a test the same night.

## DONE-WHEN
`markdown/doctrine/DOCTRINE-CODE-PARITY-2026-09-05.md` lists every checkable claim in (1) CLAUDE.md
(the strategy paragraph, the 10 rules' numbers, Account context, Tech stack status lines such as
"free-model veto DISABLED", "09:35 ET entry gate", "chart-stop-primary", "-50 pct catastrophe caps",
"min 3 contracts", "TP1 chart-level OR +30 pct fallback", "hard time-stop 15:50"), (2) params.json and
aggressive/params.json `_doc` strings that assert a consumer, (3) markdown/0dte/playbook.md and
risk-rules.md numbers -- each with: the code line that enforces it (or NONE), the vary-and-assert
result where a key exists (read / not read), the real-fills evidence where behaviour is observable
(fills-ledger / core-decisions since 08-01), and a verdict PARITY / DOC-DRIFT (code is truth, doc
corrected) / DEAD-KNOB (key not read; documented as such, prereg if J wanted it live) / UNAPPLIED-
RATIFICATION (a ratified change never reached code -- re-filed as a 10-30 prereg with its original
A/B evidence, or formally retired with the reason). All DOC-DRIFT rows are corrected in the source
docs (CLAUDE.md edits factual + minimal, context budget quoted). `backtest/tests/test_doctrine_code_
parity_2026_09_05.py` extends the exit-shape parity guard to the rules paragraph numbers and the tech-
stack status lines (kill-switch pct, per-trade cap pct, min contracts, entry gate time, catastrophe
cap pct, veto flag), RED-proofed against a mutated copy of the text.

## OPERATING RULES
- **CONFIG FREEZE**: no params VALUE changes, no code behaviour changes on FROZEN_TRADING_PATH; a
  ratified-but-unapplied change is a PREREG for 10-30 (or 09-29 if it is a pure reduction), never
  applied now.
- CLAUDE.md edits: factual corrections only, minimal, no new rules; quote the context-budget verdict
  after each edit; if RED, move detail to the parity doc and pointer it.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Truth order: real fills / decisions > code > params doc > CLAUDE.md prose > playbook prose.
- Reuse: backtest/tests/test_exit_shape_parity_2026_09_05.py (parser + guard pattern), the Rule-1
  registry parity guard (commit e11c2683), setup/hooks/doctrine.py (frozen list, freeze detector),
  markdown/0dte/EXIT-SHAPE-TRUTH.md (format).

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] P1 (WIP 2026-09-05 11:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain P1-P5 -- other sessions do not pick up) -- Claim inventory: extract every checkable numeric/boolean claim from the three doc groups
  into analysis/doctrine-parity/claims-2026-09-05.json (claim text, source file:line, kind, expected
  value). DONE-WHEN: count quoted; every claim has a source line.
- [~] P2 (WIP 2026-09-05 11:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain P1-P5 -- other sessions do not pick up) -- Code + evidence check per claim (vary-and-assert on keys; grep the enforcing line;
  real-fills/decisions evidence where observable); verdict per claim.
- [~] P3 (WIP 2026-09-05 11:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain P1-P5 -- other sessions do not pick up) -- Corrections: DOC-DRIFT rows fixed in source docs (CLAUDE.md minimal); DEAD-KNOB rows
  documented in the params `_doc` (if the hook allows) or in the parity doc; UNAPPLIED-RATIFICATION
  rows (at least pk-2026-06-28-001 TP1 0.8 Safe) re-filed as preregs with their original evidence
  (find analysis/recommendations/pk-2026-06-28-001* or the ratification log analysis/recommendations-
  log.jsonl) and added to the checkpoint inventory, or retired with the reason.
- [~] P4 (WIP 2026-09-05 11:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain P1-P5 -- other sessions do not pick up) -- Guard: test_doctrine_code_parity_2026_09_05.py; RED-proof quoted; full `-k parity` green.
- [ ] P5 -- Write markdown/doctrine/DOCTRINE-CODE-PARITY-2026-09-05.md (the table + verdict counts),
  link from markdown/README.md and the lessons index if a new L# is warranted (via lesson-author);
  regenerate CHECKPOINT files via the script if the inventory changed.

## J-DECISIONS
- None. Doc corrections revertible; preregs wait for their checkpoint.

## PROGRESS LOG
- 2026-09-05 11:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 05:38 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.
