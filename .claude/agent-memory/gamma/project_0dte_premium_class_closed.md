---
name: 0dte-premium-class-closed
description: The 0DTE SPY premium axis is exhaustively dead (L182/L183) — do not re-mine premium-selling or premium-buying; climb OFF the premium axis (DTE/instrument/class)
metadata:
  type: project
---

The **0DTE SPY premium CLASS is exhaustively closed** as of 2026-06-22 (encoded L182 + L183 in `markdown/doctrine/LESSONS-LEARNED.md`). All three sub-veins are dead on the real-OPRA data:
- **Long single-leg directional** (~64 families) — theta-killed (bought premium).
- **Short defined-risk** (#6 event iron condor / WP-PS1 randomized condor) — L182 cache-tail-bias: the +$32/tr "edge" was 100% phantom (a narrow ±$5 strike cache truncated the loss tail on big-move days); the real ±$18-band re-price INVERTED it to −$11.38/tr @ the 0th null percentile, tail blows the kill-switch even at min size.
- **Long vol** (#6b event strangle/straddle) — L183: scheduled-event 0DTE IV is two-sided FAIR. Long strangle −$38.82/tr, straddle −$107.09/tr. A positive selection-delta (event days move +$28/tr more) does NOT cover the richer premium paid.

**Why:** scheduled-event 0DTE SPY premium is fairly priced two-sided — you are charged more premium precisely because the realized move is bigger, and the two cancel to within transaction costs. This is the default expectation for a liquid, heavily-arbitraged underlying.

**How to apply:** if a future fire surfaces ANY 0DTE SPY premium-selling or premium-buying idea, treat it as presumptively dead and demand it beat L182 (band must reach the day's intraday extreme — no truncated tail) AND L183 (positive net-of-FULL-premium FIRST + a non-degenerate null where pool > sample). The productive frontier is OFF the premium axis: compound the one live affordable edge (#1 `vwap_continuation`, ATM/0DTE/−8%/qty3 on Safe-2, recency-gated) and climb the search-space ladder to **DTE-expansion / instrument (futures-options premium-selling, calendar/inter-product spreads, untested) / class**. See [[autonomy-blueprint]] and the STRATEGY-DIRECTION-BACKLOG. Related guards: L172 (random-day null), L173 (drop-top-N concentration), L177 (null must trade production's strike universe).
