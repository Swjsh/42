# GOAL: KITCHEN-INTEGRITY-2026-09-05

> Opened by Fable 2026-09-05. Three independent adjudication workers found Kitchen (free-model)
> `_analysis/` verdicts whose numbers cite artifacts that do not exist. The provenance audit shipped
> tonight (`setup/scripts/kitchen_provenance_audit.py`, commit 11a45e2d) scored 4,193 files:
> 357 PROVENANCE-OK, 440 PROVENANCE-MISSING, 3,396 NO-ARTIFACT-CITED. The reviewer now caps PROMOTE
> on PROVENANCE-MISSING. This goal closes the loop: the corpus is tagged, nothing on the leaderboard
> rests on a fabricated number, the chef prompt cannot produce one again, and the rate is rendered.

## DONE-WHEN
(a) Every PROVENANCE-MISSING file carries a machine-readable `PROVENANCE-MISSING` tag (appended
block, never a rewrite) and every leaderboard row whose only evidence is such a file reads
`UNSUPPORTED (provenance)` in its Status column; (b) the chef/Nemotron prompt template requires a
`provenance:` block (runner command + artifact path) and the reviewer rejects a verdict without one
(guard test); (c) `kitchen_fabricated_artifact_rate` (30d) renders on the cockpit and is a gate in
`free_model_audit.py` (>= 0.05 -> the touchpoint is DEGRADED per the OP-32 trust gate); (d) the
NO-ARTIFACT-CITED class (81% of the corpus) has a stated policy: verdict files with numbers but no
artifact are `UNVERIFIED-BY-CONSTRUCTION` and are never counted as evidence by any adjudicator
(kitchen_reviewer, prereg adjudication, leaderboard).

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
- [~] I1 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Retro-tag: `kitchen_provenance_audit.py --tag` appends a `<!-- PROVENANCE-MISSING: <missing paths> -->`
  block (and `<!-- UNVERIFIED-BY-CONSTRUCTION -->` for NO-ARTIFACT-CITED) to each classified file;
  idempotent; dry-run first, quote counts, then apply. DONE-WHEN: re-run audit shows tag counts ==
  class counts.
- [~] I2 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Leaderboard sweep: for every row, find its evidence files; if ALL are MISSING/NO-ARTIFACT
  the Status cell becomes `UNSUPPORTED (provenance)`; write the row list to
  analysis/kitchen-review/leaderboard-provenance-sweep-2026-09-05.json. DONE-WHEN: quoted count.
- [~] I3 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Prompt + reviewer: add the `provenance:` requirement to the chef/Nemotron prompt template
  (find it via markdown/infra/KITCHEN-SPEC.md and setup/scripts/kitchen_*), reviewer rejects a
  verdict without it; guard test RED-proofed.
- [~] I4 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Gate + render: `free_model_audit.py` marks the Kitchen touchpoint DEGRADED when the 30d
  rate >= 0.05; the rate + class counts render on the cockpit Autonomy tile (headless screenshot
  quoted); STATUS Known-broken line auto-managed by the audit (upsert/clear).
- [~] I5 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Lesson: fold `_lesson-inbox/2026-09-05-kitchen-nemotron-fabricated-analysis-numbers.md`
  into LESSONS-LEARNED.md (L310+) via the lesson-author path; add the L# to the CLAUDE.md OP-25 C7
  row (lesson-author is the only writer).

## J-DECISIONS
- None. Revert = `git revert <sha>`; the tags are append-only comments.

## PROGRESS LOG
- 2026-09-05 04:2x ET -- authored by Fable (EOD-audit session); queued on the ladder.
## HONEST STATE
Queued. Nothing started.
