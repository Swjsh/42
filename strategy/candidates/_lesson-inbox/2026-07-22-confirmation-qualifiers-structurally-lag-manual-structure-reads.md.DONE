# Lesson candidate: A confirmation qualifier built to fix a late trigger can itself be too late

> Queued by conductor (AFTERHOURS) 2026-07-22. lesson-author picks up at next wake fire.

## Symptom

`PULLBACK-HOLD-BULL-TRIGGER` Lane-B (`automation/overnight/queue.md`, full detail
`analysis/recommendations/pullback-hold-bull-stage-summary-2026-07-22.md`): a new bull trigger
was built specifically to fire EARLIER than the engine's late `level_reclaim` trigger. Its
frozen 36-cell pre-reg grid tested two candidate "is this an emerging uptrend yet" confirmation
qualifiers (session-VWAP-crossing, 60-bar market-structure trend). **0/36 cells could reproduce
J's own named live exhibit** (2026-07-22 10:44-10:53 ET pullback low) — because BOTH
confirmation candidates read False at the exact bar (10:40 ET) where J's own discretionary read
called the pullback low. PRICE_VWAP recovered True 15 minutes later; MARKET_STRUCTURE recovered
True 45 minutes later. The new trigger's geometry (pullback + hold + reclaim-above-hold-window)
was itself fine and fired at the right bars on synthetic fixtures — it was blocked entirely by
its OWN confirmation gate, which was slower than the disease it was meant to cure.

## Root cause

Any "is this an uptrend" confirmation built from session-VWAP-crossing or N-bar
trend/swing-structure is, by construction, a LAGGING signal — it needs some number of bars of
evidence to accumulate before it flips True. When such a qualifier is bolted onto a trigger
designed specifically to fire EARLIER than an existing late trigger, the qualifier's own lag can
silently reintroduce the exact lateness the new trigger was built to eliminate — and because the
qualifier gates entry entirely (AND-logic), the new trigger fires 0 times on the case that
mattered, not merely later than hoped. This generalizes: C28 already names "ribbon flip is a
lagging EXIT" — this is the same failure mode on the ENTRY confirmation side, and it is easy to
miss because the new trigger's core geometry can pass every synthetic unit test (it fires
correctly on an isolated fixture) while the compound (geometry AND confirmation) still never
fires on the real case, because the confirmation term is the one silently vetoing it.

## Fix

No code fix needed for the shadow-only Lane-A build (`detect_pullback_hold_bullish` in
`backtest/lib/filters.py`) — it stays correctly shadow-logged pending a future iteration with a
different, less-lagging confirmation primitive. The fix here is a NAMING of the generalizable
anti-pattern so future "build an earlier trigger" work checks the confirmation qualifier's own
lag BEFORE spending a full pre-reg+grid cycle: **when designing a new EARLY entry trigger, audit
any "trend/regime confirmed" qualifier's typical time-to-flip-True against the trigger's own
target entry bar BEFORE registering the grid** — a cheap sanity check (does the qualifier read
True at the anchor bar on the known named exhibits?) would have surfaced this in minutes instead
of after a full 36-cell real-fills grid run.

## Encoded in

Documented in `analysis/recommendations/pullback-hold-bull-stage-summary-2026-07-22.md` (root
cause diagnostic section) and the queue.md closing block for `PULLBACK-HOLD-BULL-TRIGGER`. No
code assertion yet — this is a design-discipline lesson (check confirmation-qualifier lag against
named anchors BEFORE registering a grid), not (yet) a re-violated pattern; if a future early-entry
build repeats this exact mistake (registers a grid with a lagging confirmation qualifier without
first checking it against known anchor bars), graduate to a pre-reg-authoring checklist item /
lint in whatever tooling builds these pre-regs.

## L## (optional)
Related to C28 (ribbon flip is a lagging EXIT) — this is the entry-side sibling; lesson-author's
call whether to fold as a C28 addendum or a new standalone L##.
