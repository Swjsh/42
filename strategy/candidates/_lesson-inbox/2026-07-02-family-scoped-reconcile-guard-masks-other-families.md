# Lesson candidate: a family-scoped reconciliation guard gives false "fully covered" confidence

**Date:** 2026-07-02
**Fire:** conductor (commit 95a603b)
**Class:** corollary to C14 (dead knobs) + C7 (silent success — audit outputs, not exit codes)

## Symptom
`test_params_filters_drift.py` (2026-06-18) reconciled params.json against consumers but scoped
itself to ONE key family: the GATE/threshold knobs (`block_*` / `*_gate` / `*_min` / `*_hard_cap`
/ `*_required`) vs the HEARTBEAT PROSE. Its docstring concluded "there is no clean NEW hard parity
to add" — reading as if params↔consumer coverage were complete. It was not: **24 of 114 ratified
knobs** (exit flags, sizing tiers, entry-window, liquidity thresholds, macro-bias, session-timing)
had ZERO live reader and were entirely outside that guard's scope. One of them
(`entry_no_trade_after_et`) directly caused 10 PLACE_FAIL late ENTER_BEARs on 2026-07-01.

## Root cause
A reconciliation guard that binds a NAMED SUBSET (one name-family, one consumer file) is easily
mistaken for full coverage of the config→consumer contract. The knobs OUTSIDE the family are
invisible to it and accrue silently as dead knobs (C14). The narrow scope is not wrong — it is
incomplete, and its confident docstring hid the incompleteness.

## Fix (shipped this fire)
`test_params_consumer_reconciliation.py` — a BROAD ratchet over EVERY ratified key vs the whole
live consumer surface (code + prompts + installers), shrinks-only `KNOWN_DEAD` allowlist. New dead
knob → RED; a dead knob gaining a consumer → forced allowlist shrink.

## Generalizable rule
When a guard reconciles config↔consumer, its scope of coverage must be MEASURED and stated as a
fraction of the whole (e.g. "covers the gate family = N of M keys"), never implied as total.
A subset-scoped guard should name what it does NOT cover, or a broad guard should sit above it.
Corollary: "no new parity to add" is a claim about the guard's OWN family, not about the config.
