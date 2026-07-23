# DRAFT: False-Break (L75) + Close-Ceiling (L59) Pattern Detectors

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** See per-pattern analysis below
**Auto-ship gate:** FAIL (requires J ratification, Rule 9 — heartbeat.md change)

## Summary

Two pattern detectors ported from lessons-learned and measured over 219 days.

| Pattern | Events | Days w/ event | Per-day avg | Fires on losers | Fires on winners |
|---|---|---|---|---|---|
| L75 (false-break bear trap) | 1230 | 211 (96%) | 5.62 | 3/3 | 3/3 |
| L59 (ceiling distribution) | 247 | 133 (61%) | 1.13 | 2/3 | n/a |

## L75 — False-Break Bear Trap

**Rule (from CLAUDE.md L75):** If the opening 09:35 bar's low dips $0.25+ below a level
AND the bar closes back above that level -> suspend bear entries for 30 minutes. The level
acted as a bear trap; price is more likely to squeeze upward.

**Finding:** L75 fired on **211/219** days (96%).
Average 5.62 events/day.

- Fires on anchor LOSERS: 3/3 days
- Fires on anchor WINNERS: 3/3 days

**Anchor loser detail:**
  - 2026-05-05: L75=3 events (would have suspended bear entries)
  - 2026-05-06: L75=6 events (would have suspended bear entries)
  - 2026-05-07: L75=9 events (would have suspended bear entries)

**Recommendation:** DRAFT for implementation. L75 adds $0 if it fires on winners (would block
valid bear setups on those days). Critical question before shipping: on the 3
winner day(s) where L75 fired, DID it fire early enough to block J's actual entry? If the 09:35
bar triggered L75 but J entered at 10:25 (after the 30-min suspend expired) — no conflict.
Needs intraday entry-time cross-reference before ratification.

## L59 — Close-Ceiling Distribution

**Rule (from CLAUDE.md L59):** N>=3 consecutive bars where high >= level but close < level ->
distribution zone (bears defending). Price tests resistance repeatedly but can't close through.
Adds conviction to bear entries AT that level.

**Finding:** L59 fired on **133/219** days (61%).

- Fires on anchor LOSERS: 2/3 days

**Recommendation:** DRAFT. L59 is a CONVICTION signal (adds to bear bias), not a FILTER
(doesn't block entries on its own). Useful for sizing UP on confirmed distribution setups.
Low-risk to implement as an optional signal; would not change entry decisions but could
justify increased size on bear setups with confirmed ceiling. Ships WITHOUT heartbeat.md edit
as an observability-only signal logged to decisions.jsonl.

## OP-20 Disclosure

- N: 219 days, 219-day benchmark window
- No IS/OOS split (detector characterization)
- P&L estimates are illustrative SPY-price-space only (L74)
- Real-fills required for option P&L claim
