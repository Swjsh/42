# Ribbon-flip-back is a dead-frequency knob on the current book + a stop-rule save (2026-08-08)

**What happened:** The pre-registered ribbon-flip-back buffer A/B (preregs
`prereg-ribbon-flipback-buffer{,-v2}-2026-08-08.json`, scorecard
`ribbon-flipback-buffer-ab-v2-2026-08-08.json`) replayed all 219 pain-ledger engine
positions (2026-06-26..2026-08-07) through the production exit manager with historical
ribbon state properly reconstructed (production `compute_ribbon` over cached SPY 5m —
first study ever to model it; every prior exit study hardcoded `ribbon_flip_back=False`).
Control parity PASSED 7/8. Result: only **13 opposing-stack flip reads across the entire
population** — max 9 changed trades per candidate vs the ≥15 power floor → UNDERPOWERED,
lane closed.

**Lesson 1 (doctrine correction):** `EXIT-DISCIPLINE-SPEC.md` (2026-06-20) claims the
chart-stop/ribbon-flip-back family does "92/100 of binding exits" — that described a
DIFFERENT population/era. On the current engine's real fills, raw opposing-stack flips are
nearly absent before other exits fire. Do not cite the 92/100 figure for today's book;
the flip-back buffer axis is a dead-frequency knob (C30-adjacent) until entry behavior
changes materially.

**Lesson 2 (positive pattern worth encoding):** the v1 prereg froze a candidate mechanism
("SPY $ beyond the flip boundary") that did NOT exist in code — the prereg's own
`stop_rule` ("if the surface doesn't exist, STOP, no improvised grid") caught it and the
builder stopped cleanly instead of inventing semantics. Rule of thumb: **read the
mechanism's actual code surface BEFORE freezing a grid, and always include a stop_rule so
a wrong freeze dies cheap.** Bonus catch: `exit_manager.py`'s "(caller already applied
spread+buffer rule)" comment was aspirational — no caller implements one (comment
corrected 2026-08-08).

**Follow-on:** the pain-ledger's 77% loss rate with exits now exhaustively litigated
(widen-stop SETTLED, TP1 27/28 refuted + clocked near-miss, trail CONTROL_HOLDS, pre-TP1
lock CLOSED, structure-ref NO-SHIP, catastrophe cap DECIDED n=13 DO_NOT_WIDEN, flip-back
dead-frequency) points the money question at ENTRY quality, not exits.
