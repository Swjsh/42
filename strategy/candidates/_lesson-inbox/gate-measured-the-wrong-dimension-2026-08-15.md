---
filed: 2026-08-15
filed_by: engine-improvement survey (post handoff-queue)
kind: lesson
status: pending
---

# A precheck that measures SPEND cannot see a failure that costs $0 — the budget gate waved through 100% of a five-day outage

## Symptom

The autonomous conductor produced no outcomes for five days. Every surface said fine:

| surface | what it showed | why it was wrong |
|---|---|---|
| Task Scheduler | `State=Ready, LastTaskResult=0`, NextRunTime advancing | the outer `wscript` hop is fire-and-forget; the real exit code never reaches it |
| rail-0 budget precheck | `PROCEED — $0.00 of $30.00 used, 0/4 fires` | **it measures SPEND**, and the failure mode spends nothing |
| `check_run_ps1_hidden_masked_exit` | `run-conductor-weekend.ps1 (exit=[1], 5x)` | generic non-zero exit, listed beside unrelated `exit=1` noise |
| unattended registry | `Conductor RED [3.4d]` | correct, but generic staleness — days late, no cause, no action |

The actual line, present in every log the whole time:

```
=== START tick (timeout=600s effort=high model=sonnet) ===
Not logged in · Please run /login
=== END tick exit=1 ===
```

Measured: **49 failed fires across 8 tasks** from 2026-08-11; **100% of conductor fires** from 08-12 (3/3, 4/4, 2/2, 11/11) against ~470 clean fires before it.

## Root cause of the BLINDNESS (not of the outage)

The outage itself is mundane — a login expired. What deserves a lesson is that four
independent monitors all watched it happen and none of them said so.

**The budget gate is the sharp one.** It exists to stop fires that waste money. It reads
spend-to-date, sees `$0.00`, concludes there is plenty of headroom, and returns PROCEED —
on a fire that is about to fail for free. *The cheaper the failure, the more confidently
the gate approves it.* A gate whose measured dimension is orthogonal to the failure mode
does not merely miss it; it actively certifies it.

## Generalisations worth keeping

1. **Name the dimension a gate measures, then ask what failure is invisible along it.**
   Spend-gates cannot see free failures. Liveness-gates cannot see wrong answers.
   Exit-code gates cannot see hollow success. Staleness-gates cannot see a producer that
   writes garbage on time.
2. **"Exit 0 / alive / PROCEED" all mean "nothing raised", never "the work happened"** —
   the standing C7 rule, and this is its most expensive instance to date.
3. **A generic detector is not a diagnosis.** `exit=[1], 5x` was TRUE and USELESS. The
   same evidence one level deeper — the log line — named one cause across eight tasks. When
   several monitors each report a fragment, nothing aggregates them into "these are the
   same incident"; build the layer that does.
4. **Distinguish J-ACTION failures from self-heal targets, explicitly and in the message.**
   `claude /login` is interactive OAuth. An automated healer retrying into it burns fires
   forever and never recovers. Any alert for this class must say "no automation can clear
   this" or something will eventually try.
5. **A deterministic backstop silently carrying production reads exactly like a healthy
   primary.** `eod_flatten.py` covered the failed LLM EOD-flatten path and
   `premarket_deterministic_fallback.py` covered premarket — which is why nothing looked
   broken. Backstop engagement is itself a signal and should be surfaced, not just relied on.

## The fix

`self_check.check_llm_auth_outage` — reads the fire logs for the auth signature, aggregates
per-task counts and the outage span, classifies **BROKEN** (its masked-exit siblings say
DEGRADED because they have backstops; this one has none), and routes through the existing
STATUS.md `## Known broken` + single-Discord-ping escalation. Verified live: self-check
flipped DEGRADED → BROKEN and the finding is on STATUS.md.

Guard: `backtest/tests/test_self_check_llm_auth_outage.py` (8 tests, synthetic logs + frozen
clock so they never depend on the rig's current login state).

Fix: `818a1439`.

## Still open for J

The login itself. Nothing in this repo can clear it.
