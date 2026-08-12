---
filed: 2026-08-11
filed_by: goal fire (unlock-more-trades, ~21:00-01:30 ET)
kind: lesson
status: pending
---

# Two DIFFERENT sizing clamps emit near-identical `qty clamped N->M: ...` log lines — reading the ledger instead of the source attributed a $921 protection to the wrong mechanism

## Symptom

Classifying August fleet entries by their `reason` field produced this apparent finding:

> "risky-3 was NEVER clamped all month; safe-3 flipped to unclamped on exactly 08-07 — the two
> arms that took the biggest hits. risky-1 stayed clamped and was protected +$921. Why is
> risky-3's recency state permanently GREEN?"

**Every clause of that except the dollar amount is wrong**, and the closing question is
malformed — it cannot be answered because it presumes something impossible.

## Root cause

`fleet_executor.py` has **two** clamps writing nearly the same string:

| function | log line | trigger |
|---|---|---|
| `_apply_full_send_min_sizing` (L302) | `qty clamped N->M: FULL_SEND min size` | EVERY entry of a full-send arm, unconditional |
| `_apply_recency_min_sizing` (L333) | `qty clamped N->M: recency RED` | global ribbon_ride recency verdict == RED |

A classifier that matched the substring `clamped` merged the two into one bucket.

1. **risky-1 is the FULL-SEND arm** (`gate_override: {"full_send": true}`, cell
   `risky x FULL-SEND`). Its clamps are unconditional min-sizing working as designed — its
   08-07 protection had **nothing to do with recency**.
2. **The recency verdict is GLOBAL, not per-arm.** `_recency_verdict()` reads ONE shared file
   (`automation/state/recency-confirmation.json`) live per tick, so it cannot differ between
   arms — "risky-3 is permanently GREEN" is impossible by construction. risky-3 DID clamp
   (12->5) on 08-04 from 11:27 onward; `recency_min_size_enabled=True` in BOTH params files.

The real mechanism: the global verdict was **not RED on the morning of 08-07** (it had been RED
through 08-04 and returned to RED by 08-10), so safe-3 and risky-3 entered at full tier size
into the month's worst day. risky-1 escaped only because FULL_SEND ignores recency entirely.

## Rule to carry forward

1. **Never infer a mechanism from a log string when the source is one grep away.** Log lines
   are written for humans and collide; functions do not. Attribute to the function.
2. **When two code paths can produce the same observable, a classifier over that observable
   must disambiguate** — match the distinguishing suffix (`FULL_SEND min size` vs
   `recency RED`), or better, log a machine-readable `clamp_source` field.
3. **Check the SCOPE of a gate's state before writing a per-entity question.** A global signal
   cannot explain per-arm divergence; if arms differ, the difference is in their flags, not in
   the shared signal.

## Follow-up work order (not a defect — a real open question this exposed)

The recency verdict flips **intraday and mid-week**. Should the clamp's RELEASE require
hysteresis (N consecutive non-RED sessions) rather than tracking a signal that went non-RED for
a single morning and cost the book its worst day of the month? Needs a frozen prereg.

Suggested cheap hardening regardless of that verdict: emit `clamp_source` as a structured field
on the placement row so no future classifier has to parse prose.

Kin: C14 (dead/mistranslated knobs), C7 (audit outputs, not exit codes).
