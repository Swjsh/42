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
- [x] P1 (DONE 2026-09-05 05:58 ET, Sonnet session a16e320c) -- Claim inventory: 20 claims extracted
  into analysis/doctrine-parity/claims-2026-09-05.json (claim text, source file:line, kind, expected
  value). Every claim has a source line + enforcing_code field.
- [x] P2 (DONE 2026-09-05 05:58 ET, same session) -- Code + evidence check per claim (vary-and-assert
  reused from EXIT-SHAPE-TRUTH for exit-shape keys, fresh grep/read for rules/tech-stack keys);
  verdict per claim: 14 PARITY, 4 DOC-DRIFT, 1 UNAPPLIED-RATIFICATION, 1 UNVERIFIED (playbook.md/
  risk-rules.md numeric cross-check, C15, not completed this pass -- flagged not asserted).
- [x] P3 (DONE 2026-09-05 05:58 ET, same session) -- Corrections: 4 DOC-DRIFT rows fixed in CLAUDE.md
  (Rule 6 min-contracts per-account split, Management-line time-stop 15:50->15:40, TP1 fallback
  reworded off the stale +30%, EOD-flatten row). UNAPPLIED-RATIFICATION (pk-2026-06-28-001 TP1 0.8
  Safe) re-filed as analysis/recommendations/prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json
  with the original scorecard's evidence quoted verbatim; added to checkpoint-2026-09-29-inventory.json
  (count 9->10, classified reduction per its actual direction -- selling MORE at TP1 reduces runner
  exposure, correcting the goal brief's generic expansion-direction template).
- [x] P4 (DONE 2026-09-05 06:02 ET, same session) -- Guard: backtest/tests/test_doctrine_code_parity_
  2026_09_05.py, 9 tests incl. 2 dedicated RED-proofs, all pass. Combined with the sibling exit-shape
  guard: `pytest test_doctrine_code_parity_2026_09_05.py test_exit_shape_parity_2026_09_05.py -q` ->
  15 passed. Full repo-wide `-k parity` (400 tests across unrelated watcher/scorer suites) finished
  in background after goal-close: `396 passed, 4 skipped, 13147 deselected in 749.88s (0:12:29)` --
  0 failed. Full `-k parity` is GREEN.
- [x] P5 (DONE 2026-09-05 06:05 ET, same session) -- markdown/doctrine/DOCTRINE-CODE-PARITY-2026-09-05.md
  written (table + verdict counts + context-budget trace), linked from markdown/README.md doctrine/
  row. No new L# warranted -- the drift class (doc prose vs. registry/params, C14) is already covered
  by existing lesson C14; not a new failure mode. CHECKPOINT files regenerated via checkpoint_packet.py
  (13 rows, new row correctly reads UNKNOWN/n=None pending a fresh scored A/B).

## J-DECISIONS
- None. Doc corrections revertible; preregs wait for their checkpoint.

## PROGRESS LOG
- 2026-09-05 11:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 05:38 ET — opened by goal_autopilot
- 2026-09-05 05:38-06:05 ET -- Sonnet session a16e320c ran P1-P5 end to end. CLAUDE.md context
  budget: pre-edit not re-measured; first-draft edits pushed it to RED (9111/9000 tiktoken), trimmed
  to YELLOW (8995/9000) with integrity=ok. Found the tiktoken-vs-byte-estimate discrepancy between
  `python` (has tiktoken, accurate) and `backtest/.venv/Scripts/python.exe` (falls back to a
  byte/3.6 estimate, under-reports) -- noted in the parity doc so future budget checks use the
  right interpreter.
## HONEST STATE
P1-P5 complete. 4 DOC-DRIFT rows corrected in CLAUDE.md (context budget YELLOW, not RED, after
trim). 1 UNAPPLIED-RATIFICATION re-filed as a 09-29 prereg (pure reduction) and folded into the
checkpoint inventory + regenerated CHECKPOINT files. Guard test green (15/15 doctrine-scoped tests;
full repo `-k parity` also confirmed green post-close: 396 passed/4 skipped/0 failed). One open
item: C15 (playbook.md/risk-rules.md numeric cross-check) was not completed -- flagged UNVERIFIED
in the parity doc rather than claimed done.
