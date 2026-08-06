# LESSON CANDIDATE: a per-fire USD budget cap that's mis-sized AT BIRTH can fail silently forever -- masked exits hide it, and nobody ever compares it to sibling tasks

**Date:** 2026-08-06 (conductor AFTERHOURS fire, ~05:30 ET)

**Symptom:** `self_check.py`'s RUN-PS1-HIDDEN masked-exit detector (shipped 2026-08-05/06,
itself following the VBS-WRAPPER-EXIT-CODE-BLIND-SPOT theme) flagged
`run-scout-premarket.ps1 (exit=[1], 1x)` for today. Pulling the actual dated log
(`automation/state/logs/scout-2026-08-06.log`) showed the real `claude` CLI error:
`Error: Exceeded USD budget (0.5)`. Checking EVERY dated scout log on disk
(2026-07-20, 07-21, 07-22, 07-23, 07-27, 07-28, 07-31, 08-03, 08-04, 08-05, 08-06) found the
IDENTICAL error -> exit=1 on every single one. `git log` on the script showed exactly ONE
commit ever (2026-06-15, its creation) -- the `-MaxBudgetUsd 0.50` value had never been
touched since birth. `automation/scout/state/scout_output.json` (which Premarket at 08:30 ET
reads for macro/news bias context) had gone stale for 2+ consecutive sessions (08-05, 08-06)
before this was caught, because most fires never reached a clean write before hitting the cap.

**Root cause named in one sentence:** the budget was set too low for the job at design time
(a WebSearch-driven macro/news scan), and Task Scheduler's `LastTaskResult` + the vbs
launcher's fire-and-forget hop meant the daily failure produced ZERO visible signal for
~7-8 weeks -- this was never a regression, it was broken from the first day and nobody had
an instrument that could see it.

**Why it matters (C7/C14 class, new angle):** existing C14 lessons are about dead/translated
knobs that get silently ignored; this is the sibling failure mode for a knob that IS being
read and enforced correctly -- the config VALUE itself was simply wrong, and because the
enforcement mechanism (`claude --max-budget-usd`) fails by aborting the whole session rather
than degrading gracefully, "wrong value" and "no output at all" become nearly indistinguishable
without reading the raw stderr. A same-purpose sibling task check would have caught this in
minutes: `futures-premarket` (a comparable WebSearch/calendar scan) budgets $2.00,
`premarket` itself $3.00 -- `scout-premarket` at $0.50 was a visible outlier the whole time,
just nobody diffed the roster.

**Fix shipped:** `run-scout-premarket.ps1` `-MaxBudgetUsd` raised 0.50 -> 1.00 (still the
2nd-cheapest premarket-class task on the roster, comment left in-line explaining why).
Guard: `backtest/tests/test_scout_premarket_budget.py` (`test_..._is_not_the_known_broken_value`
pins the exact regression value so a future edit can't silently drift back to 0.50;
`test_..._at_least_1_dollar` pins a floor). RED-proofed live (reverted to 0.50 in the real
file, confirmed both assertions fail with the exact evidence string, restored, re-confirmed
green) rather than trusting a synthetic fixture.

**Generalizable pattern -- worth a standing check, not just this one fix:** any
`-MaxBudgetUsd` value should be sanity-checked against sibling tasks doing a similar-shaped
job (WebSearch-scan tier vs. heartbeat-tier vs. deep-review tier) at the time it's FIRST set,
not just when it's edited later -- a drift ratchet catches future edits but not a
wrong-from-day-one value. Consider a one-time audit pass across ALL `run-*.ps1`
`-MaxBudgetUsd` values grouped by task shape (heartbeat / premarket-class / EOD / weekly)
to catch any other outliers of this same class before they cost another 7-8 weeks of silent
staleness. Not attempted this fire (scoped, single-item pick) -- flagged as a candidate
follow-up, not a blocker.
