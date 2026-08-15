---
filed: 2026-08-15
filed_by: handoff-queue fire (HANDOFF-2026-08-15-ENGINE-REVIEW items 1-5)
kind: lesson
status: pending
---

# A timezone offset derived by differencing an INJECTED clock against `datetime.now()` is not an offset — it is "how stale the caller's clock is", and it rounds into your measurements

## Symptom

Two unrelated monitors, two different-looking failures, one defect.

**`unattended_health.py`** — 5 guard tests failed with gaps that changed daily:

> `HAS NOT FIRED in 5.9d -- daily trigger, budget 2.0d`

on a fixture whose `last_run` is **2 hours** before its frozen `SUNDAY` clock. 5.9d was the
distance from that fixture to *the day the suite happened to run*.

**`state_freshness_audit.py`** — a guard that **passed in isolation and failed in-batch**:

> `key-levels.json STALE BY AGE: 20.9m > 20m budget while its window 24/7 is OPEN`

The test name pointed at the date axis; the failure was the age axis. Re-measured 20 minutes
later it read 16.6m. It drifts continuously and crosses the 20m budget for part of every hour.

## Root cause

Both files computed the ET-minus-LOCAL offset the same way:

```python
offset_h = round((now_et - datetime.now()).total_seconds() / 3600.0)
```

This is only an offset when `now_et` **is** now. Hand it an injected/frozen clock and it
silently redefines "timezone offset" as "distance from today":

| clock passed in | intended | actual |
|---|---:|---:|
| real `et_now()` | +2 | +2 ✅ |
| frozen `2026-08-09 15:00` | +2 | **−140** |
| frozen `2026-07-30 07:00` | +2 | **−389** |

Then the two files express the damage differently, which is why they did not look related:

- `unattended_health` **adds** the offset to timestamps → every stamp shifts ~5.8 days → fresh
  tasks read as chronic outages.
- `state_freshness_audit` **rounds to whole hours** → the sub-hour remainder survives into
  `age_min` as a phantom age. −388.69h rounds to −389; the leftover 0.31h **is** the 18.5
  minutes. It walks minute by minute, so the guard is flaky by the clock, not by the code.

**Live was correct in both cases** — production passes the real `now_et`, so the expression
returns +2 and nothing misbehaves. That is precisely why it survived: the monitors looked
healthy while their own guard suites sat red, and the red was dismissed as stale pins.

## The fix

Derive the offset from the **date**, via the two zones' own UTC offsets, never by differencing
against the wall clock:

```python
et_from_utc = et_offset_hours(now_et.replace(tzinfo=timezone.utc))   # canonical et_clock
local       = now_et.astimezone().utcoffset()
return et_from_utc - round(local.total_seconds() / 3600.0)
```

Correct for any clock, DST-aware, and it makes `evaluate_task`'s advertised contract ("pure
apart from its inputs, so the guard can drive it with a frozen clock") actually true.

## Why this is a CLASS, not two bugs

Second occurrence = missing guardrail, not bad luck. The repo already had the right primitive
(`et_clock.et_offset_hours`) and doctrine already says *"NEVER again hardcode -4 or -5. Never
derive ET from local time."* — this pattern obeys the letter (nothing hardcoded) while
violating the intent (it derives ET from local time, by subtraction).

Repo swept at fix time: those two were the only instances.

## Generalisation worth keeping

**Any function that accepts an injectable "now" must not consult the real clock anywhere in
its body.** Mixing the two makes the function's output a property of *when it runs*, and the
symptom appears in whatever unit the value is later used for — days here, minutes there. A
useful smell: a "purity" claim in a docstring alongside a bare `datetime.now()` in the body.

**Bounded-value guard shape** (both files now carry it): assert the derived offset stays in a
sane range for arbitrary clocks. It RED-proofs instantly (−140h, −389h) and needs no knowledge
of the local timezone, so it survives the box moving.

## Guards

- `backtest/tests/test_unattended_health.py::test_et_offset_does_not_drift_with_the_wall_clock`
- `...::test_task_verdict_depends_only_on_its_frozen_clock`
- `backtest/tests/test_state_freshness_audit.py::test_et_minus_local_offset_is_a_property_of_the_date_not_of_now`
- `...::test_age_axis_reports_no_phantom_age_under_a_frozen_clock` (SIGN is the discriminator —
  a file written now, scored against a past clock, must have a NEGATIVE age; the broken form
  masks that with a small positive remainder)

Fixes: `c23d6b77` (unattended_health), `692161d0` (state_freshness_audit).
