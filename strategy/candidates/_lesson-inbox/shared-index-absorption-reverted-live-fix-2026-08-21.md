## Shared-index absorption silently reverted a live-engine fix onto `main`

**Date:** 2026-08-21 (conductor AFTERHOURS fire, 20:30 ET)

**Symptom:** A pathspec `git add <4 files>` followed by a bare `git commit` (correct
per doctrine -- specific files, not `-A`) still swept 9 OTHER already-staged files into
the same commit, because `git add <paths>` only ADDS to whatever the index already
contains; it does not scope the following `git commit` to just those paths. The
pre-commit hook's own heuristic WARN ("staged set spans 4 top-level dirs... this MAY be
shared-index absorption of another session's staged work") fired and named the exact
risk -- but is non-blocking by design, and the warning was read and discounted instead
of acted on.

**Root cause:** the repo is a SINGLE shared checkout used by multiple concurrent Claude
sessions (conductor fires, interactive sessions, possibly other automation), all of whom
can `git add` into the SAME index. Whoever commits next inherits everyone else's staged
state, good or bad. One of those absorbed files, `setup/scripts/heartbeat_core.py`, was
mid-refactor from another session investigating the deferred T-OPEN-TICK-STALE-QUOTE-
2026-08-20 decision -- its staged content was a hybrid that reverted 97af7375's tested
`_trigger_bar_stale` key-order fix back to an earlier, already-superseded state. That
reverted heartbeat_core.py -- THE LIVE TRADING ENGINE -- briefly landed on `main`
(commit 7f8a8caf) before being caught and restored (01ac90b4) in the same fire.

**How it was caught:** OP-33 discipline -- before moving on, the fire re-read its own
commit's diff (`git show --stat`) instead of trusting the commit message it had just
written, noticed the diff touched files it never edited, and diffed each absorbed file
against the last known-good commit (`git diff 3cdad8f8 -- <file>`) to check for silent
regressions rather than assuming "already staged = already correct."

**Fix shipped this fire:** none to the tooling itself -- `commit_scoped.py` already
exists and does the right thing (pathspec-scoped commit that leaves other staged paths
untouched for their own owner to commit). The gap is behavioral: `git add <paths> &&
git commit` was used instead of `commit_scoped.py "<msg>" <paths>` for the FIRST commit
this fire, despite the hook naming the exact risk. `commit_scoped.py` was used correctly
for the restoration commit.

**Suggested guard (for whoever picks this up):** make `commit_scoped.py` the ONLY
sanctioned commit path in this repo's conductor/automation docs (not just "consider
it if the hook warns") -- i.e. flip the WARN's own wording from "if you only meant to
commit specific paths" (conditional) to an unconditional "use commit_scoped.py; a bare
`git commit` after `git add <paths>` commits the WHOLE shared index, not just what you
added." Possibly also: teach the pre-commit hook to REFUSE (not just warn) when the
about-to-be-committed diff touches a file the current `git add` invocation never named,
UNLESS the caller explicitly opts in (e.g. via `commit_scoped.py --i-know-what-im-doing`
for the rare legitimate multi-file scoped commit). Fail-open still applies -- never
block J's interactive session -- but a conductor fire's own automated commit is fair
game to gate harder than it currently is.

**Also surfaced, out of scope for this fire:** `backtest/tests/
test_trigger_bar_freshness_2026_08_20.py::test_a_prior_session_bar_makes_the_tick_blind`
is ALREADY failing at the last officially-shipped commit (3cdad8f8), confirmed via
git-stash-isolated repro -- pre-dates this fire, not caused or fixed here. It asserts
025a29d4's original gated-`_is_blind` behavior; 97af7375 deliberately walked that back
(documented inline in the function's own comment: broke 10 other tests, would silently
disable the entire backtest/replay lane) but never updated this one test to match the
new deliberate design. Whoever owns T-OPEN-TICK-STALE-QUOTE-2026-08-20 should either fix
the test's expectation to match the documented ungated design, or actually implement the
gating properly (with an injected clock + OP-11 evidence, per the function's own TODO).
`setup/scripts/trendline_tier_rail.py` is also currently DELETED in the working tree
(unstaged, not committed) -- looks like in-progress WIP from the same or another
session; left untouched by this fire on purpose (ambiguous ownership, not my lane).
