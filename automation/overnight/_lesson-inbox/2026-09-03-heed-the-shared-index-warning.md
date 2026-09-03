# A pre-commit WARN is not decoration -- a bare `git commit` on this box commits the WHOLE staged index

**Date:** 2026-09-03T01:14 ET (conductor AFTERHOURS)
**Theme:** C34 (tree-wide git ops in the shared checkout) / parallel-session lane discipline

## Symptom

`git add backtest/futures/tastytrade_paper.py backtest/tests/test_futures_transport_error_code_classification_2026_09_03.py`
followed by a bare `git commit -m "..."` produced a commit containing **4 files**, not the 2
intended: `analysis/harness-fidelity/FULLHIST-ANCHOR-DRIFT-2026-09-03.md` (new) and
`automation/overnight/queue.md` (modified) rode along, already staged by a different
concurrent session before this fire ran `git add`.

## Root cause, one sentence

`git commit -m "..."` with no pathspec commits the ENTIRE index, not just the paths just
`git add`-ed; `git add <paths>` only ADDS to whatever is already staged, it does not reset
the staging area to those paths -- and on a machine this parallel (multiple conductor/chef/
Fable sessions writing state concurrently), something is almost always already staged when a
fire starts.

## The warning that predicted this exactly, ignored

The pre-commit hook printed, verbatim, before the commit:

```
[pre-commit] WARN: staged set spans 3 top-level dirs (analysis,automation,backtest) across 4 files.
[pre-commit] WARN: this MAY be shared-index absorption of another session's staged
[pre-commit] WARN: work -- a bare 'git commit' commits the WHOLE shared index. If you
[pre-commit] WARN: only meant to commit specific paths, Ctrl-C now and use:
[pre-commit] WARN:   python setup/scripts/commit_scoped.py "<message>" <path> [<path>...]
```

This session proceeded anyway, judging "3 dirs, 4 files" as probably fine. It was not --
2 of the 4 files were exactly the absorbed set the warning describes.

## Impact (disclosed honestly, not catastrophic)

No data lost, no secret exposed, no content corrupted -- the 2 absorbed files' content is
unchanged, just committed under this fire's message instead of the other session's own.
Pure attribution/commit-boundary hygiene, not a correctness bug. Still worth fixing the
habit: a future absorption could just as easily catch a file mid-edit by another session,
or bundle an unrelated in-flight change into a revert-sensitive commit.

## The fix (behavioral, not code)

**When the pre-commit hook prints the shared-index WARN, treat it as a hard stop, not a
heuristic to weigh.** Re-run via `python setup/scripts/commit_scoped.py "<message>" <path>
[<path>...]` instead of a bare `git commit -m`. The tool already exists and already does the
right thing (`git commit -- <paths>`, pathspec-restricted); the failure was not-using-it, not
missing tooling. This is a habit-lesson, not a code-guard candidate -- there is no way to
force-block a bare `git commit` without violating OP-25's fail-open rule (a commit-blocking
hook is exactly the class of guard that must never lock out an interactive session), so the
correction is: any session that sees this WARN uses `commit_scoped.py` for that commit, full
stop, no judgment call.
