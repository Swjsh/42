# Lesson candidate: EOD pre-fire context read stale decisions.jsonl instead of core-decisions.jsonl

> Queued by Analyst 2026-08-31. lesson-author picks up at next wake fire.

## Symptom
The 2026-08-31 16:00 ET EOD-reflection fire was handed pre-flight context citing "12:10 SKIP_TV_DATA_STALE | 12:25 SKIP_TV_DATA_STALE | 12:30 SKIP_LIQUIDITY" as today's last 3 heartbeat actions. Cross-checked against the live ledger (`automation/state/core-decisions.jsonl`, 772 rows for 2026-08-31): zero `SKIP_*` verdicts exist for today; all 772 ticks graded `HOLD`. The exact (action, timestamp) triples cited in the context are a byte-for-byte match to the tail of `automation/state/decisions.jsonl`, a file last modified 2026-06-25 (`date` field on those rows literally reads `"2026-06-25"`).

## Root cause
`automation/state/decisions.jsonl` is a legacy single-file decision ledger that stopped being written to when the system migrated to per-account/core ledgers (`automation/state/core-decisions.jsonl`, plus `automation/state/aggressive/decisions.jsonl`). The file was never deleted or marked stale, so it still sits at the canonical path a naive `tail decisions.jsonl` or context-assembly step would read. Something upstream of this Analyst fire (unclear which script/prompt — not identified this session, budget-capped) read that dead file and presented its June tail as "today's last 3 actions" without checking the `date` field or file mtime against today's date.

## Fix
Not applied this session (identifying and patching the exact upstream context-assembly step is out of scope for a $0.40/20-turn Analyst fire — needs a repo-wide grep for `decisions.jsonl` read sites, cross-referenced against `core-decisions.jsonl` migration commit). Proposed fix: whatever composes pre-fire/pre-flight context should either (a) read `core-decisions.jsonl` exclusively and treat `decisions.jsonl` as deprecated/delete-candidate, or (b) validate the `date` field of any row it surfaces against the fire's actual trading date before quoting it as "today's" activity, and fail loudly (not silently) if the file's freshest row predates today.

## Encoded in
Not yet encoded — this item needs a code fix (identify + patch the context-assembly read site, and/or archive/delete the dead `decisions.jsonl` file) before it can be folded into `LESSONS-LEARNED.md` as a closed loop. Until fixed, add an L## noting "stale ledger files at canonical paths silently mislead context assemblers — verify `date`/mtime freshness before trusting any decisions-ledger read as 'today'."

## L## (optional)
Suggested: next available L### (lesson-author greps for max and assigns).
