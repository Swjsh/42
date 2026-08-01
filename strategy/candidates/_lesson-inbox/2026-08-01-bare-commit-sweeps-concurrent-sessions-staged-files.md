# Bare `git commit` sweeps concurrent sessions' staged files (2026-08-01, WS6)

**Symptom:** WS6's pathspec-scoped `git add` (5 files) + bare `git commit` produced a
16-file commit (`482a662a`) that swallowed WS7's staged live-watch ship (live_watch.py,
dashboard panel, tests, installer, page.tsx/workspace.ts edits), WS8's trendline-context
study artifacts + runner, a STATUS.md entry, and a .gitignore edit — all under WS6's
commit message. The immediately preceding attempt had failed on `index.lock` held by a
concurrent session; that session's staging survived in the SHARED index and the retry's
bare `commit` committed the whole index, not the pathspec that had just been `add`-ed.

**Root cause (one sentence):** in a multi-session shared checkout, `git add <paths>` +
`git commit` is NOT pathspec-scoped at the commit step — `commit` snapshots the entire
shared index, including whatever other sessions staged between (or before) your add and
your commit.

**Fix / rule:** in the shared checkout, commit with an explicit pathspec on the COMMIT
itself — `git commit -- <paths...>` (or `git commit <paths...>`) — which commits ONLY
the named paths regardless of what else is staged. Pathspec discipline must cover BOTH
verbs, not just `add`. An `index.lock` collision immediately before a commit is the
red-flag precondition: another session is mid-staging RIGHT NOW.

**Damage disposition (this instance):** all swept content was coherent, fully-staged
work — committed correctly, wrong grouping/message only. No history surgery performed
(C34: no tree-wide git ops in the hot shared checkout); affected lanes' own post-commit
`git show --stat` verification (L247/C35) finds their files in `482a662a`.

**Graduation candidate:** extend C34/C35 row; possibly a repo helper
`setup/scripts/commit_scoped.ps1` that always passes the pathspec to commit.

Family: C34/C35 (shared-checkout git ops). Related: L239 (multi-path add fails
atomically), L247 (pre-commit --cached check != post-commit verify).
