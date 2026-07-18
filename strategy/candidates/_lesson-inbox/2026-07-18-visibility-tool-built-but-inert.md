# Lesson candidate: a built visibility tool that never reaches J is still invisible

> Queued by conductor-weekend fire 2026-07-18, ~11:30 ET. lesson-author picks up at next wake fire.

## Symptom
`automation/state/j-question-ledger.jsonl` shows J asking a state-question variant
("is it running" / "is it trading" / "whats the status") 40+ times across
2026-06-30..2026-07-18 (18 days) despite `friction_distiller.py`'s own
`recurring_user_question` pattern class existing specifically to catch this
(FAST_ESCALATE=2, action=BUILD_ELIMINATING_INSTRUMENT) and despite J already
having TWO purpose-built pull instruments (`setup/scripts/gamma_glance.py`,
`setup/scripts/gamma_status.py`, both from the 2026-06-29/30 visibility push)
and a phone/watch companion app (`gamma-companion/`) with a full push-notification
stack (VAPID, wrist-approve HMAC tokens, obligations registry) built 2026-06-21.

## Root cause
Two compounding gaps, found only by tracing the actual delivery path end to end
instead of trusting that "a script exists" means "J sees it":
1. **Pull instruments require J to run a command.** `gamma_glance.py`/`gamma_status.py`
   answer the question perfectly but only when actively invoked -- J was asking in
   conversation instead of running them, so their existence never reduced the ask rate.
2. **The push instrument's OWN state proves it never fired.** `automation/state/.vapid.json`
   has existed since 2026-06-21 (so `push.js#sendPush()`, wired into
   `approvals.js`/`escalate.js`/`server.js`, is NOT the silent VAPID-absent no-op the
   first hypothesis assumed) -- but `automation/state/push-subscriptions.json` is `[]`,
   27 days later. Zero devices have ever subscribed. Per
   `gamma-companion/MOBILE_PWA_DESIGN.md` (written 2026-06-21, never actioned), Android
   Chrome refuses push/voice over plain `http://192.168.x.x`; the companion needs an
   HTTPS front-door (Tailscale Serve, documented step-by-step in that file) before J's
   phone can ever complete a push subscription. That is a one-time, J-only, physical
   device+network step -- no autonomous Claude session can complete it.

The general lesson: **"I built the instrument" and "J stopped having to ask" are two
different claims, and only the second one retires OP-33(e) friction.** A tool that
exists but is never invoked, or a push pipe that is wired end-to-end in code but has
zero live subscribers, is architecturally complete and operationally inert -- and
looks identical to "done" from inside the codebase. The only way to catch this is to
trace the FULL path to the human's actual device/attention, not stop at "the function
is called correctly."

## Fix
This fire (2026-07-18): `gamma_glance.py` (`_push_status()`) and `gamma_status.py`
(`_push_glance()`) now report the REAL two-layer state (VAPID present? subscriber
count?) with the exact remaining J-only step, instead of the tools staying silent
on this gap. Guard: `backtest/tests/test_push_visibility_guard.py` (6/6, RED-proofed).
Flagged to J directly (`automation/overnight/queue.md`, `STATUS.md`) as the one
concrete remaining action: run Tailscale Serve + open the companion PWA on his phone
once. Deliberately did NOT touch `.vapid.json`/`push-subscriptions.json` themselves
(gamma-companion's own `guard.js` DENY_WRITE denylists them for any automated Claude,
by design -- this is a J-only physical/consent step, not a code gap).

## Encoded in
`setup/scripts/gamma_glance.py::_push_status`, `setup/scripts/gamma_status.py::_push_glance`,
`backtest/tests/test_push_visibility_guard.py`. Suggests a durable pattern for
`friction_distiller.py`'s `recurring_user_question` class: when the eliminating
instrument is judged "BUILD_ELIMINATING_INSTRUMENT" and a candidate already exists in
code, the FIRST check must be "does it actually reach J's device today" (grep the
real subscriber/session state), not "does the code path exist."

## L## (optional)
Next available L# (lesson-author greps LESSONS-LEARNED.md for current max; as of this
writing the index runs through L201-ish per CLAUDE.md OP-25). Suggested class: fold
into C7 (silent success is failure) or C18 (status-format discipline) as a new row,
or open a new class if lesson-author judges it distinct enough
("built != delivered" / instrument-reach-verification).
