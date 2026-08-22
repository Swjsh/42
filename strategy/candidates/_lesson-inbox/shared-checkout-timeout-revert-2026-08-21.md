---
kind: lesson
filed: 2026-08-21
theme: C34 (tree-wide git ops in the shared checkout revert live state BACKWARD)
severity: HIGH
---

# A timed-out baseline comparison reverted 6 live files, and the next commit shipped it

## What happened

Investigating an 18-failure full-suite RED, I needed to know which failures were mine.
The cheap way to answer that is a baseline: check the pre-work revision out over the
changed files, re-run the failing tests, then check HEAD back out.

```bash
git checkout ed8e78bd -- $FILES        # revert to baseline
pytest <the 12 failing tests>          # <-- took >10 min, TOOL TIMEOUT FIRED HERE
git checkout HEAD -- $FILES            # never ran
```

The tests loaded large master CSVs and blew the 10-minute tool timeout. The restore step
never executed. The **shared working tree** was left holding pre-2026-08-21 versions of
six files, plus one new file moved aside to `/tmp`.

Eleven minutes later another session committed `7f8a8caf` — a futures-mirror diagnostics
fix that had nothing to do with any of those files — and swept the reverted state in as
collateral. A third session then committed `01ac90b4` ("restore heartbeat_core.py — undo
an accidental shared-index revert"), correctly identifying the symptom on one file while
the other six stayed reverted in HEAD.

## Why it mattered

Every reverted file was a repair shipped hours earlier:
- the lazy pandas import, without which the mandatory daily trendline section of the EOD
  audit crashes under system python
- the cp1252 fix, without which the nightly audit exits 1 on every successful run
- a corrected stale test pin, a corrected CLAUDE.md tier row, and three
  `revalidation_filed` gate stamps

None of it announced itself. The tests went green again *because the tests had been
reverted too.*

## Root cause

Not the timeout. The timeout is normal. The root cause is **doing a destructive,
two-phase operation on a shared checkout where phase 2 is not guaranteed to run.**
`git checkout <rev> -- <files>` is destructive to the working tree and has no automatic
undo; pairing it with a long-running command makes the undo conditional on that command
finishing inside a timeout you do not control.

## The rule

**Never `git checkout <old-rev> -- <files>` in the shared checkout to run a baseline.**

Use one of these instead:
1. **`git worktree add`** a throwaway tree at the baseline revision and run there. The
   shared tree is never touched, and an interrupted run leaves nothing to clean up.
2. **Copy the files aside** (`cp f f.bak`), overwrite, restore from the copy. Still
   two-phase, but phase 1 is non-destructive — the originals survive independently of
   whether phase 2 runs.
3. Best of all for "is this failure mine?": run the suspect tests and **read the
   assertion messages**. Two of the three files I was chasing were identifiable from the
   assertion text alone in seconds, with no checkout at all.

## Detection gap worth noting

Nothing flagged six live files silently reverting. `git status` looked clean after the
sweep because the revert had been *committed*. The only reason it surfaced was a
content-level check (`grep -c` for a known marker string) rather than a git-level one —
`git status` answers "does the tree match HEAD", which is the wrong question when HEAD
itself moved backward.

Consider: a guard that asserts a handful of known repair markers are present in HEAD
would have caught this within one commit. Same shape as
`test_status_known_broken_section_2026_08_20.py`, which pins that an escalation channel
still exists.
