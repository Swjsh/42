# Shared-index absorption: another lane's bare `git commit` can swallow YOUR staged files

**Date:** 2026-08-01 (WEEKEND-TWELVE, 12-lane weekend multi-session grind).
**STATUS UPDATE (2026-08-01 evening, Next-Twelve #3):** originally filed off ONE incident
(da18da34/WS12, below). The chief audit (`analysis/deep-research/WEEKEND-TWELVE-2026-08-01.md`
§3) found the SAME mechanism hit **5 times in one night**; this item now covers all 5 with
citations, and the fix (§ "Fix (SHIPPED)" below) has moved from "candidate for a graduated
guard" to actually built + guard-tested. lesson-author: fold the whole item, not just
incident 1 — the pattern-count and the shipped-fix pointer are the load-bearing new content.

**Family:** C34/C35 (shared-checkout git ops; committed != verified) — a NEW mechanism vs
L239 (own multi-path add fails atomically) and L247 (own later commit absorbs a staged
delete): in all 5 incidents below, the absorber was a DIFFERENT concurrent session, not
the same one that did the staging.

**Root cause (one sentence, unchanged since first filed):** in a shared checkout, `git add`
state is GLOBAL — any parallel lane's pathspec-less `git commit` commits YOUR
staged-but-uncommitted files, silently, under ITS message, with no error of any kind.

---

## Incident 1 — `da18da34` absorbs WS12 (the original filing)

WS12 ran `git add <4 files>` at 12:53, but its `git commit -- <paths>` was blocked ~15 min
by an unrelated RED pre-commit gate (WS7's undocumented scheduled task). While blocked,
WS11's lane ran a BARE `git commit` (no pathspec) for its own work — the shared index still
carried WS12's 4 staged files, so WS11's commit `da18da34` ("feat(recency): core-strategy
recency clock") silently absorbed 490 lines of WS12 deliverables (RESET-PLAN-2026-08-01.md,
a guard test, SKILL.md, a STATUS entry). WS12's own commit `75e9acd5` then recorded only a
3-line follow-up edit under the full WS12 message — the message/content mapping across both
commits is misleading forever.

**Detection that worked (keep doing):** the commit summary line said "1 file changed, 3
insertions" against an intended 490 — the L247 post-commit `git show <sha> --stat` habit
caught it within one command.

## Incident 2 — `482a662a` absorbs WS7 AND WS8 (biggest single sweep, 16 files)

WS6's regime-library/regime-stamp lane staged its own ~7 files and ran a bare commit. The
shared index also carried WS7's ENTIRE Live Watch deliverable (`live_watch.py`,
`LiveWatchPanel.tsx`, `install-live-watch.ps1`, `test_live_watch.py`, two dashboard edits)
AND WS8's trendline-context-conditioning study artifacts (JSON + MD + the runner script)
AND an unrelated `.gitignore` edit — **16 files, 7,912 insertions, three different lanes'
work, one commit message.** WS7 had to file a separate correction, `20589740` ("docs(ws7):
attribution note -- WS7 LIVE WATCH landed inside 482a662a"), so a reader of `git log` alone
would never know WS7's deliverable existed under that sha without it.

## Incident 3 — `a363bd5f` absorbs WS8's staged prereg (caused a DOWNSTREAM citation error)

The theta-cockpit lane's bare commit (building `theta_clock.py` etc.) also swept WS8's
already-staged prereg file (`prereg-trendline-context-conditioning-2026-08-01.json`). This
one did more than scramble attribution: WS8's own report then cited a sha (`9d4d242c`) as
its freeze-order proof that is **not an ancestor of HEAD at all** — the prereg actually rode
into mainline inside `a363bd5f`. The chief audit had to trace the real commit by content
match before WS8's freeze-order claim could be verified. Absorption doesn't just cost
attribution — it can silently invalidate a lane's own cited evidence chain.

## Incident 4 — `be9c1b58` absorbs a same-file concurrent edit (NOT fixable by pathspec alone)

Ostensibly a 1-file, 5-line stub commit (adding a `Gamma_ThetaClock` registry row to
`SCHEDULED-TASKS.md` after the safety gate's `test_every_installed_task_is_documented`
went RED). It ALSO silently carried the twin lane's unrelated cadence-value edit to the
SAME file (`Gamma_CryptoTwin` 5min->1min), undisclosed in the commit message or the lane
report. **This is a distinct, harder sub-flavor:** incidents 1/2/3/5 are about OTHER FILES
getting swept in — pathspec-scoped commit (`git commit -- <paths>`) fully solves those,
because git builds a temporary index containing only the named paths. But here BOTH edits
landed in the SAME file's working-tree content before either session staged it — naming
`automation/state/SCHEDULED-TASKS.md` in a pathspec still commits whatever the file
currently contains on disk, which may already be two sessions' edits blended. **Pathspec
discipline does not fully close this sub-case** — the only real mitigations are (a) keep
per-lane edits to shared registry docs as small/localized as possible so a diff is easy to
eyeball before staging, and (b) treat any shared single-file registry (SCHEDULED-TASKS.md,
STATUS.md, queue.md) as a higher-collision-risk surface and diff it immediately before
`git add`. Flagging this honestly rather than claiming the shipped fix (below) covers it —
it doesn't, fully.

## Incident 5 — `90fd1e40` absorbs the deletion of THIS LESSON'S OWN EARLIER DRAFT

The twin-lane's position-snapshot commit (`feat(twin): position snapshot + last_trade on
twin-health.json`) has a 31-line pure deletion in its diff:
`strategy/candidates/_lesson-inbox/2026-08-01-bare-commit-sweeps-concurrent-sessions-staged-files.md`.
That file was an independent EARLIER draft of this exact lesson (a different lane
discovering the same mechanism, describing incident 2 in near-identical terms), superseded
by consolidation into this item — but the cleanup deletion itself got swept into the twin
lane's unrelated commit rather than landing in whichever commit did the consolidation. The
bug ate its own paper trail while this lesson was being written. (Content is not lost —
`git show 90fd1e40^:strategy/candidates/_lesson-inbox/2026-08-01-bare-commit-sweeps-concurrent-sessions-staged-files.md`
still recovers the original text if ever needed — but it is a small, pointed demonstration
of how pervasive a one-night process failure can get.)

---

**Detection habit that caught 4 of 5 (keep doing):** `git show <sha> --stat` immediately
after every commit, checked against the intended file list — a pre-commit `git diff --cached`
is not the same guarantee (L247). Incident 3 additionally required a content-match trace
since the citing lane didn't know which sha to look at.

## Fix (SHIPPED 2026-08-01 evening, Next-Twelve #3)

1. **`setup/scripts/commit_scoped.py "<message>" <path> [<path>...]`** — stages then commits
   with an explicit pathspec on BOTH calls (`git add -- <paths>` then
   `git commit -m <message> -- <paths>`). `git commit -- <paths>` is not a convention, it is
   a git STRUCTURAL guarantee: git builds a temporary, pathspec-scoped index for the
   duration of the commit (verified empirically this fire — git exports `GIT_INDEX_FILE`
   pointing at a `.git/next-index-*.lock` file, and pre-commit hooks inherit it, a mechanism
   this repo had already independently documented in `test_verify_committed.py`'s 2026-07-01
   env-hygiene comment without generalizing it into a fix). A bare `git commit` has no such
   scoping — it snapshots the real `.git/index` as-is. Guard-tested + RED-proofed:
   `backtest/tests/test_commit_scoped.py` (9 tests; temporarily reverting the helper to a
   bare `git commit` internally turns 5 of the 9 RED with the foreign file visibly present
   in the commit — the exact absorption bug, reproduced and pinned).
2. **`setup/git-hooks/pre-commit` extended** (not replaced) with a WARN-ONLY, fail-open
   tripwire: if the staged set at commit time spans more than one top-level directory group,
   print a loud stderr warning pointing at `commit_scoped.py` and append a line to
   `automation/state/commit-scope-warnings.jsonl`. Crude heuristic by design (git cannot know
   "files this session never touched" — that information doesn't exist anywhere) and it will
   also fire on plenty of legitimate multi-directory commits; accepted false-positive rate
   for something that costs one glance and NEVER blocks. It naturally under-fires (in the
   good direction) for a `commit_scoped.py`/pathspec-scoped commit, because of the same
   temp-index mechanism in point 1 — verified across 4 scenarios (bare 1-dir no-warn, bare
   2-dir warn, pathspec-scoped multi-dir warn-but-no-foreign-sweep, and a live absorption
   repro warn). Does NOT catch incident 4's same-file-concurrent-edit sub-case (see above) —
   that one is structurally out of reach for anything working at file-pathspec granularity.
3. **Doctrine: bare `git commit` is discouraged in this shared checkout** — use
   `commit_scoped.py` or `git commit -- <paths>` directly. Pointer added to
   `markdown/doctrine/fable-judgment/03-EXECUTION.md` (E3, which already named the mechanism
   from an earlier collision but pointed at a bare flag with no tooling behind it).
4. Post-commit `git show <sha> --stat` stays mandatory (it caught 4 of 5 here) — the fix
   above reduces how often you need it, it doesn't replace it.

**Impact across all 5 incidents:** content landed correctly at HEAD in every case (verified
per-incident: working tree == HEAD content, nothing lost). Damage is 100% commit-attribution
/ history-readability / (incident 3) downstream-citation-validity — never data loss. No
history rewrites performed on any of the 5 (C34: no tree-wide git ops in the shared
checkout; all 5 shas are pushed-adjacent shared history — rewriting would be strictly worse
than living with the wrong message).
