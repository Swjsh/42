## Bare `git stash` — 4th confirmed instance (C34 class: L214, L228, L238, this one)

**Filed by:** conductor (AFTERHOURS), 2026-08-01 ~01:15 ET
**Fold target:** C34 (tree-wide git ops in the shared checkout revert live state BACKWARD)

**What happened:** mid-fire, ran a bare `git stash && pytest ... && git stash pop` to compare
baseline vs my in-progress edit on `test_fleet_arm_parity.py` (FLEET-STRIKE-TIER-ATM-EXTENSION
task). Pytest returned non-zero (pre-existing unrelated test failures), so the `&&` chain
short-circuited and `git stash pop` never ran. Between the `git stash` and my manual recovery,
background daemons (Kitchen, gym, twin, prospector, etc.) wrote fresh live state on top of what
had been reverted-to-HEAD by the stash, so the eventual `git stash pop` partially conflicted
(refused to touch ~50 daemon-written files, correctly leaving them at their newer state) and
had to be resolved with `git stash drop` after manually confirming my 4 edited files applied
cleanly and no daemon file regressed. No data was lost, but it cost real time+tokens mid-fire
and easily could have gone worse (e.g., if pytest had returned 0 by coincidence and the `&&`
chain had proceeded to `git stash pop` DURING a daemon write race).

**Root cause:** same as L214/L228/L238 — a bare (non-pathspec'd) `git stash` in this repo always
sweeps up concurrent daemon writes, because multiple background processes (Kitchen, gym runner,
prospector, twin, discord bridge, etc.) continuously write to tracked live-state files even
during an interactive/conductor session. There is no window where the working tree is quiescent.

**Why this keeps recurring despite 3 prior documented instances:** the existing guidance is
prose-only ("never git stash in this repo, rename-and-restore instead") — nothing in the repo
actually prevents a bare `git stash` invocation. An agent under time/token pressure reaching for
the standard "stash, test, pop" pattern will keep doing this unless the SAFE pattern is easier
to reach for than the dangerous one.

**Proposed guard (for skill-author or validator-author to pick up):** a small `setup/scripts/
safe_baseline_diff.py` (or a documented Bash one-liner) that does the backup+checkout+restore
dance in one call: `cp <files> /tmp/backup && git checkout HEAD -- <files> && <test cmd> && cp
/tmp/backup/* <original paths>`. Making the SAFE pattern a single named command (instead of
requiring the agent to remember 4 manual steps) is more likely to actually get used than another
paragraph of prose. Not a pytest-style code guard (git usage isn't something pytest can gate),
but a callable replacement for the dangerous reflex.

**This fire's actual recovery (for reference):** `cp <4 files> /tmp/fleet_backup/`, then
`git checkout HEAD -- <4 files>` to get pristine baseline, ran the test suite, confirmed the
pre-existing failure count, then `cp /tmp/fleet_backup/* <original paths>` to restore edits.
Zero git-stash involvement in the actual working pattern — this IS the safe pattern, just
arrived at only after the mistake.
