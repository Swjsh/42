# Lesson candidate: git stash/checkout on tracked-but-live-written state files reverts them BACKWARD, not just loses history

> Queued by conductor (AFTERHOURS) 2026-07-20 ~19:55 ET. lesson-author picks up at next wake fire.
> **This is a RECURRENCE of the same mechanism as the (never-L-numbered) 2026-07-14 stash-drop
> incident** (`backtest/tests/test_ledger_gitignore_guard.py`'s original docstring, commit
> `41889a0`) — flagging both the original and the recurrence together so lesson-author can
> assign ONE L# covering the general class, not two.

## Symptom

2026-07-20, TWICE the same day: (1) Monday premarket preflight found `circuit-breaker.json`
(both core accounts) + `today-bias.json` carrying **2026-07-14 content** despite file mtimes
showing writes at 04:27/05:58 ET that same morning — i.e. the content **regressed backward**,
not just went stale. (2) At ~18:40 ET, mid-session, an agent's `git stash && ... && git stash pop`
in the shared checkout collided with the running heartbeat's live writes to the same files —
the evening verify found BOTH breakers + `today-bias.json` reverted to 2026-07-14 content again.
Re-armed both times (08:02 ET and 18:42 ET); no trading impact because both are read at
session-start/entry-time and self-heal via re-arm, but a less-monitored file could have caused
a stale kill-switch state to persist silently.

## Root cause

`circuit-breaker*.json` (6 files: core Safe/Bold + 4 fleet arms) and `today-bias.json` (2 files:
main + futures) are **overwritten-in-place JSON state**, continuously written by live automation,
but were **tracked-but-rarely-committed** (last real commit 2026-07-14, same commit that
happened to gitignore the *decision ledgers* for the unrelated 07-14 stash-drop incident — these
files were just along for the ride in that snapshot, not deliberately protected). Any
`git stash` / `git checkout` / `git reset` touching them in the shared checkout reverts the
**working-tree file content** to whatever was last committed — for an overwritten-in-place file
this means state jumps BACKWARD (stale kill-switch armed/tripped flags, stale bias), which is a
more dangerous failure mode than the original 07-14 incident's lost-history symptom (append-only
ledgers losing recent rows) because it can silently misrepresent CURRENT state, not just history.

**Class-level insight for lesson-author:** the 07-14 fix (gitignore + untrack the 4 decision
ledgers) treated the symptom (this specific file set) rather than the mechanism (ANY
tracked-but-continuously-written file in `automation/state/` is vulnerable to ANY tree-wide git
operation in the shared checkout). The mechanism recurred on a *different* file class within a
week because nothing generalized the fix.

## Fix (this fire, 2026-07-20 ~19:55 ET)

Same pattern as `41889a0`: gitignored + `git rm --cached` the 8 confirmed-reproduced files
(`circuit-breaker.json` x6, `today-bias.json` x2). Extended the existing guard
(`backtest/tests/test_ledger_gitignore_guard.py`) with a `STATE_SNAPSHOTS` list + 2 new tests
(`test_state_snapshots_are_gitignored`, `test_state_snapshots_are_untracked`); RED-proofed via
`git stash` on `.gitignore` alone (new test failed with the exact expected assertion, stash pop
restored cleanly, re-verified 4/4 green). Commit: see `automation/overnight/STATUS.md` for hash.

**NOT done this fire (scoped out, follow-up filed):** a broader audit found **~279 tracked
JSON/JSONL files** under `automation/state/` last-committed 2026-07-14 — most are dated
one-time snapshots or append-only historical logs (e.g. `level-quality/outcomes-YYYY-MM-DD.jsonl`,
`atomic-bracket-guard-*.jsonl`) that don't regress in place and are lower risk; a handful may
share the exact overwritten-in-place hazard of the 8 fixed here and were not individually
triaged. Follow-up: `STATE-FILE-REVERSION-AUDIT-FOLLOWUP` in `automation/overnight/queue.md`.

**Also NOT done (interim rule, prose only, not yet code-enforced):** "no `git stash`/
`checkout`/`clean` touching `automation/state/` by any session or fire in the shared checkout"
is the standing discipline that would have prevented BOTH reproductions today. This is exactly
the class of prose-rule the OP-25 mandate says should graduate to a guard — candidate mechanism:
a pre-commit or pytest check that fails if ANY file under `automation/state/` that is NOT in an
explicit tracked-config allowlist (`params.json`, `aggressive/params.json`, `fleet/accounts.json`,
`SCHEDULED-TASKS.md`, `README.md`) is present in `git diff HEAD --name-only` after any stash/
checkout operation — hard to enforce generically without hooking every git invocation; flagging
for lesson-author/skill-author judgment rather than guessing an implementation here.

## Encoded in

`backtest/tests/test_ledger_gitignore_guard.py` (extended guard, 4/4 green, RED-proofed) +
`.gitignore` (the actual fix). Zero trading-path files touched (state-file tracking is
infra/ops, not `params.json`/`heartbeat_core.py`/`filters.py`/placement/exit code) — ships as
engine-benefit per OP-22/OP-26.

## L## (optional)

Not suggested — let lesson-author grep for max and assign next (index currently through L202
per CLAUDE.md OP-25 as of this fire). Suggest folding into class **C7** (silent-success-is-
failure / audit outputs) or a new class if lesson-author judges the git-ops-on-live-state
mechanism distinct enough to warrant its own category — this is the SECOND lesson in this
exact mechanism (07-14 ledgers, 07-20 state snapshots), so a re-violation-class flag is
warranted regardless of which C-number it lands under.
