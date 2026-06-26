# H4 — Post-Loss Size / Entry Throttle

**Rank:** 4 of 8 · **Score:** 7.5 · **Seam:** J real-fills / risk-gate code-gap (L168) · **Status:** PROPOSAL (test, do not ship — propose-only, risk_gate is doctrine-adjacent)

---

## The setup / signal

A **post-adverse-excursion throttle** in the sizing path (a NEW backtest knob, mirrored later into `risk_gate` only on J ratification):

- After a closed losing trade today, the **next** entry is capped at the **floor contract count** (no elite/confluence size-up) for a cooldown window (test {1 trade, 30 min, 60 min}).
- After **two** losses today, suppress all but elite-trigger entries for the rest of the session (softer than the kill switch, harder than nothing).
- It throttles **size-up after a loss** specifically — it never blocks J's session and never adds to an open position (that's already Rule 4 / NOT_FLAT).

## The insight (why it should have edge)

L168 + `J-WEBULL-EDGE` make this the single most-evidenced edge in the project:

> "**1-2 contracts: net +$4,576 (50.8% WR). 3-5: -$13,975 (18.6% WR). Scaled-in: -$327/trade vs +$3.5 single-fill.** The whole account loss lives in the 88 trades sized 3+. He sizes up into his *worst* trades."

And the **code-gap L168 surfaced explicitly**:

> "`risk_gate.check_order` ... does NOT enforce 'no sizing up after a loss' ... there is no equity-trend- or prior-loss-aware size throttle. ... a fresh-but-oversized entry *after* a losing trade closed is not mechanically capped beyond the static % cap."

The behaviour J's account died from — revenge/conviction sizing-up after a loss — is the *one* thing the engine does not yet mechanically prevent. The `J-LOSERS-STOPPED-THEN-PRINTED` study reconfirms it on the loser book: 3+ lots rode to -47% to -58% vs -40% for 1-2 lots. This isn't a speculative edge; it's hard-coding J's documented #1 leak out of the engine.

**Critical scope discipline (L168):** this does NOT touch `min_contracts` / Rule 6 — that's J's confounded open question. It throttles *the size-up after a loss*, which is the **un-confounded** finding (single-fill positive, scaled-in negative, sizes-up-into-losers). Pure loss-avoidance, no edge-direction claim.

## EXACT backtest to validate

1. **Knob:** add `post_loss_size_throttle` {off, floor_next_1, floor_30min, floor_60min} + `two_loss_elite_only` {off,on} to the backtest sizing path (NOT live params).
2. **Measure on the full 16-month population:** total P&L, max drawdown (sequential), worst-day P&L, and specifically the **conditional** stat — expectancy of "the next entry after a loss" with vs without the throttle. This is the load-bearing number.
3. **Anchor (OP-16):** 4/29, 5/01, 5/04 are each the *first* trade of their day (or independent) → throttle must be a **no-op on all three** (no prior-loss to throttle) → `edge_capture` unchanged. 5/07's two losses (734C then 737C) are exactly the case the two-loss arm should suppress the second of → `edge_capture` should *improve* (fewer J-loser-class entries) or hold.
4. **Real-fills:** the throttle changes *size*, not entry timing, so the per-trade real-fills expectancy is unchanged; the win is at the **book** level (drawdown + worst-day). Report book-level real-fills P&L delta.
5. **Guards:** L172 null is N/A (this is a sizing overlay, not an entry signal) — instead the gate is "max-drawdown reduced AND total P&L not materially worse AND edge_capture >= baseline."
6. **Scorecard:** `analysis/recommendations/h4-post-loss-throttle.json` with the conditional next-after-loss expectancy table and the drawdown delta.

## Kill criteria (reject if ANY)

- Total 16-month P&L drops by more than the drawdown improvement is worth (throttle is too aggressive, clips good post-loss setups — verify against C28's "don't over-tune").
- `edge_capture < baseline` (throttle touched an anchor — should be impossible; if it happens, the anchor-day sequencing is mis-modeled).
- Next-after-loss conditional expectancy is **already positive** at baseline (then there's nothing to throttle — the leak is J-specific and didn't transfer to the engine population; C22).
- The cooldown blocks more winners than losers (measure win/loss ratio of throttled-away entries).

## Expected edge_capture x feasibility

**edge_capture HIGH** (encodes J's documented #1 account-killer; anchor-neutral; pure floor-raising). **feasibility HIGH** (a sizing overlay, no new detector, no look-ahead risk). Ranked #4 not #1 because the *engine* population may not exhibit J's revenge-sizing leak (the engine already sizes mechanically) — so the measured benefit could be small even though the principle is bulletproof. The test settles exactly that.

## Disclosure (OP-20)

PROPOSE-ONLY to J: this is a `risk_gate` change (doctrine-adjacent, Rule 9). It does NOT resolve the min-3 open question (L168) — it is orthogonal. Disclose: benefit is conditional on the engine population actually showing post-loss size-up (J's data does; the mechanical engine may not). Ship the conditional-expectancy table so J sees whether the leak transfers before ratifying.
