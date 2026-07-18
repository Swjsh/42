# Lesson candidate: the instrument built to count J's friction was counting its own

> Queued by conductor fire 2026-07-18, ~13:53 ET. lesson-author picks up at next wake fire.

## Symptom
`automation/state/j-question-ledger.jsonl` (the OP-33(e) J-MIND-CHECK harvest, written by
`setup/hook-detect-correction.ps1`, consumed by `friction_distiller.py`'s
`recurring_user_question` FAST_ESCALATE class) claimed J asked an "is it running / is it
trading" state-question **43-49 times over 18 days**. That number was cited verbatim in
`automation/overnight/queue.md`'s `J-ONLY-COMPANION-PUSH-ACTIVATION` item and in a
same-day lesson-inbox item (`2026-07-18-visibility-tool-built-but-inert.md`).

## Root cause
Traced by replaying the hook's own regexes against the actual submitted prompt text
instead of trusting the ledger count. **Every scheduled `conductor` / `conductor-weekend`
/ `conductor-rth` / `weekly-review` fire submits the wrapper's injected
`# RUNTIME CONTEXT (injected by wrapper, ...)` header + STATE DIGEST, followed by the full
`automation/prompts/conductor.md` doctrine text, as the literal UserPromptSubmit `prompt`.**
That doctrine prose itself contains ordinary phrases that trip the hook's `is_running` /
`is_trading` interrogative regexes with zero J involvement:
- `"...the success bar is **daily paper trading** + an honest digest..."` matches
  `is .{0,25}trading`
- `"the rig's function is trading; a fire that ships..."` matches `is .{0,25}trading`
- `"...the forward path is mirror-shadow, never a live futures order..."` matches
  `is .{0,25}live`

Direct regex replay against the file confirmed exactly these 3 self-matches. Auditing the
actual 49-line ledger showed **15 lines (31%) were self-inflicted wrapper fires**, not J
typing anything — the header text `# RUNTIME CONTEXT (injected by wrapper` was present
verbatim at the start of every one of those 15 `prompt` fields.

The existing `$qIsSystem` exclusion (built 2026-06-29 after task-notification events
phantom-fired the same way) filtered `task-notification|system-reminder|</result>|...` —
markers for *tool/agent* messages — but had no marker for *the wrapper's own scheduled-task
prompt*, which is neither a tool result nor a J message but was being counted as the latter.

The general lesson: **an instrument built to measure human friction must be audited for
whether it can hear itself talking.** A self-referential counting loop (the conductor's own
prompt, submitted through the same UserPromptSubmit channel J's real messages arrive on)
will silently inflate any keyword-based friction/question detector unless every automated,
non-interactive prompt source is positively excluded — not just other classes of noise that
were caught before. "We already added a system-message filter" is not the same claim as
"we filtered every non-J prompt source."

## Fix
`setup/hook-detect-correction.ps1`: added `# runtime context \(injected by wrapper|state
digest \(auto-injected` to the `$qIsSystem` exclusion regex (same line the
task-notification filter lives on, not a bolted-on separate check). Verified via direct
PowerShell invocation with (a) a full simulated wrapper prompt (conductor.md content) —
ledger unchanged, confirms non-capture; (b) a real J-style prompt ("is it still running
today?") — ledger grew by 1, confirms no regression. Pruned the 15 confirmed
self-inflicted lines from the live ledger (34 real entries remain) and regenerated
`friction-ledger.jsonl` (`recurring_user_question` now `occ=34`, still
STEP-BACK-ELIGIBLE — the underlying J friction is real, it was just over-counted).
Corrected the "40+/43 times" citations in `queue.md`. Guard:
`backtest/tests/test_graduated_guards.py::test_operator_friction_excludes_wrapper_self_fire`
(RED without the fix — asserts the wrapper marker lives inside the `$qIsSystem` line).

## Encoded in
`setup/hook-detect-correction.ps1` (`$qIsSystem` line),
`backtest/tests/test_graduated_guards.py::test_operator_friction_excludes_wrapper_self_fire`.
Suggests a durable pattern: any future harvest source added to `friction_distiller.py` that
reads from a channel automated fires ALSO write to (Discord outbox, decisions ledger, any
UserPromptSubmit-adjacent capture) needs the same self-exclusion audit before its counts are
trusted for an escalation threshold.

## L## (optional)
Next available L# (lesson-author greps LESSONS-LEARNED.md for current max; CLAUDE.md OP-25
index runs through L201-ish as of this writing). Suggested class: fold into C7 (silent
success is failure — here the failure mode is "silent OVER-success", the ledger looked
alive and correctly counting while quietly counting itself) or open as a sibling to the
"built != delivered" lesson filed the same day
(`2026-07-18-visibility-tool-built-but-inert.md`) under a shared "instrumentation integrity"
theme — both are about an OP-33(e) visibility instrument that looked correct from inside the
codebase but wasn't actually measuring what it claimed.
