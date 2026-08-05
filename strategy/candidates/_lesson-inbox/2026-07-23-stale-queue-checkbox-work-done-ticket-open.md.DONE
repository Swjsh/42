## Stale queue checkbox: work shipped, ticket left open (3rd occurrence — graduate per OP-25)

**Found:** 2026-07-23 conductor (AFTERHOURS) fire, closing `BREAKER-REARM-STALENESS`.

**Pattern:** a queue.md ticket's underlying work ships (sometimes same-day, sometimes days
later) in a commit that does NOT also flip that ticket's `[ ]`->`[x]` / `status:pending`->
`status:done*`. `task_scorer.py --top` (which ranks by `status:pending` + readiness) then
keeps re-surfacing already-solved work as the highest-priority item, burning a conductor fire
re-discovering something that was already fixed instead of doing new work.

**4 confirmed instances (not a one-off):**
1. `T-W8-HEADROOM-RETEST-CANDIDATES` — ran 2026-07-09, checkbox closed 2026-07-11 (2-day lag).
2. `FUTURES-PHASE1-BATTERY` — ran 2026-07-09, checkbox closed 2026-07-14 (5-day lag).
3. `BREAKER-REARM-STALENESS` — fix shipped 2026-07-09 11:34 MT (commit `1b2cfeeb`), same
   session that filed the ticket even, checkbox closed 2026-07-23 (14-day lag) — this one is
   worse: the FIX and the TICKET were filed/fixed in the SAME session and still diverged.
4. `PMH-IS-FABRICATED-IEX-PREMARKET` — filed 2026-07-27, fix shipped THE SAME DAY (commit
   `7b4aa3f4`, ~2h after filing), checkbox closed 2026-08-01 (5-day lag). Worse still: `task_scorer.py`
   kept re-ranking it a top-2 HIGH-priority ready item across multiple intervening conductor
   fires (`score=6.0, ready=true`), and this fire almost re-implemented the already-shipped fix
   before reading the target file's own docstring, which stated plainly the fix already landed.
   Silver lining this time: investigating the "already done?" claim surfaced a SEPARATE real bug
   (see `_lesson-inbox` item filed alongside this update, 2026-08-01, "guard suite rotted
   independent of the code it guards") — so the wasted-rediscovery risk is real, but checking
   git history FIRST before executing a `task_scorer --top` pick paid for itself here.

**Root cause hypothesis:** a fire that does root-cause debugging + a fix in one motion
(diagnose -> patch -> guard-test -> commit) treats the queue.md entry as a SEPARATE
bookkeeping step that's easy to skip once the code is green and committed — especially when
the ticket text was written days/sessions earlier and isn't the literal string being edited.

**Recommended guard (graduate, don't just re-note in prose again):** a lightweight
cross-reference check — for any `queue.md` item whose text names a specific file (e.g.
`engine_health.py`, `daily_loss_guard.py`) that has a commit touching that exact file dated
AFTER the ticket's own filed-date, AND the ticket is still `status:pending` — flag it as
"possibly-already-shipped, re-verify before executing" instead of blindly treating
`task_scorer`'s `--top` pick as untouched work. This doesn't need to be perfect (false
positives are fine, just a "check first" nudge) — it needs to stop a 3rd/4th/5th fire from
repeating this exact waste. Candidate home: `setup/scripts/task_scorer.py` (same module that
already got the section-scope fix earlier today, 2026-07-23) or a small pre-flight helper the
conductor prompt's STAGE 1 calls before trusting `--top` blindly.

**Not actioned as code this fire** (rail 3, one bounded task; the ticket-close was this fire's
task) — filed for `lesson-author` to encode as an `L##` + fold into C14 (dead/stale-knob class,
same family as L245/L246/L248/task-scorer-section-scope) and, if scoped small, for a follow-up
fire to build the pre-flight cross-reference check named above.
