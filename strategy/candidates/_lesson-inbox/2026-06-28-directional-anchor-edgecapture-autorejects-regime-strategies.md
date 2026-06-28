# Lesson candidate: a directional-anchor `edge_capture` metric auto-rejects any regime-specific (range / mean-reversion) strategy

**Filed:** 2026-06-28 (conductor, while validating the range-scalp regime-appropriate edge)
**Best-fit fold:** C4 (disclose concentration / per-trade expectancy not WR) or C24 (anchor trades are one-off exceptional setups — general population may differ). Related: L16 (J-edge source of truth), L24/L140, L166/L178 (cross-sectional anomaly != per-trade option edge).

## Symptom
The range-scalp R&D cook task (`cook-queue.jsonl` task `2fd24b35`) and the chef candidate both carry the OP-16 J-edge gate verbatim: **"Reject if edge_capture < 771."** Applying that gate would have **auto-rejected the regime-appropriate edge before it was ever tested** — a range/mean-reversion strategy *cannot* capture J's source-of-truth winners, because those winners (5/14 +$1,208, 5/15 +$1,400, 5/04 +$730) are **directional trend days**, not range days. `edge_capture` is anchored on a directional-trend population.

## Root cause
`edge_capture = winners_capture(J trend days) − losers_added`. The J anchor set is a *directional* source-of-truth (trendline rejections that ran). When the candidate strategy's CLASS differs from the anchor's CLASS (mean-reversion fade vs directional continuation), the anchor measures the WRONG population:
- A range strategy is FLAT or slightly negative on big trend days (it fades into a trend = small stop-out) → near-zero `winners_capture` → `edge_capture << 771` by construction.
- This is the same family as C24/L140: "anchor trades are one-off exceptional setups; the general population of a *different* pattern class may behave oppositely."

## Fix / principle
- **Match the yardstick to the strategy class.** A regime-specific strategy must be evaluated against a **regime-matched anchor set** (range days for a range strategy) AND by **per-trade expectancy / WR / concentration**, NOT by `edge_capture` against J's directional trend days.
- `edge_capture` (OP-16) remains correct for *directional* candidates competing to replicate J's edge — it is NOT a universal pre-merge gate.
- Concretely validated this fire: `range_scalp_probe.py` evaluated shotgun_scalper Tier-2 LEVEL_REJECT by per-trade expectancy over the recent range regime → VEIN_CONCENTRATED (+$12.46/tr, 66.7% WR, but top-3 days = 224% of net). Under the `edge_capture < 771` gate it would have been rejected outright (0 trend-day capture), losing a real lead.

## Watch-out / detection
When a cook task or candidate names a new strategy CLASS (mean-reversion, range, scalp, overnight) AND carries the `edge_capture < 771` / OP-16 50%-floor gate, the gate is mis-applied. Flag it: the regime-appropriate edge needs a regime-matched yardstick. The tell: a candidate whose mechanism structurally can't fire on the J anchor days but is still gated on capturing them.

## Reusable corollary (don't rebuild)
The range-scalp "mean-reversion level fade" mechanism is **already implemented** as shotgun_scalper Tier-2 `LEVEL_REJECT_LIVE` — the regime-appropriate R&D should REUSE it (now via `run_shotgun_day(..., tier_filter=2)`), not build a duplicate `range_scalp_grind.py` from scratch (L17/L36).
