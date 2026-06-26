# Strategy candidate: UNBLOCK midday_trendline_gate (Safe)

> DRAFT — Chef proposal 2026-06-26 11:37:02 ET. J ratifies.

## Hypothesis
`midday_trendline_gate` (gates.py #10, Safe=true) blocks entries whose ONLY trigger is
`trendline_rejection` in 11:30–14:00 ET. It was ratified on the OLD engine (OTM + premium_stop
−0.08/−0.10, NO chandelier), where these trades theta-bled at **−$8.6/trade** (cited in the
params doc, 307 OOS trades). **Directional claim:** under the CURRENT LIVE engine
(chart-stop-primary −0.50 catastrophe cap + chandelier trailing 0.125 + managed TP1/runner,
real OPRA fills), those same trades now NET POSITIVE, so the block suppresses winners and no
longer earns its keep. The exit structure flipped the setup's P&L sign.

## Backtest evidence
A/B = gate ON (blocked, = live baseline) vs gate OFF (unblocked). BLOCK_DELTA = pnl(ON) − pnl(OFF).
Positive ⇒ block helps; negative ⇒ block hurts. Mirrors live Safe config exactly: real fills,
OTM-2 tier @ $2,000 equity, −0.50 caps, tp1 0.50@0.667, runner 2.5×, chandelier trail 0.125,
30% risk cap, min_trig bear=1/bull=2, block_elite_bull + block_level_rejection ON.

- Train (IS) window: 2025-01-02 .. 2026-05-07 → **BLOCK_DELTA = −$371** (gate OFF +$6,837 / ON +$6,466)
- Test (OOS) window: 2026-05-08 .. 2026-06-16 → **BLOCK_DELTA = −$40**
- Recent window: 2026-05-19 .. 2026-06-25 → BLOCK_DELTA = +$23 (marginal, n=5)
- **Removed trades, full history: n=102, ALL puts (0 calls), net +$849, avg +$8.33/tr, WR 71%.**
  Sign-flip vs the OLD-engine ratification (−$8.6/tr → +$8.33/tr).
- edge_capture (J source-of-truth): UNCHANGED. Gate touches only secondary same-day trendline-only
  re-entries; J's primary anchor trades are level/reclaim entries the gate never fires on.
  Bearish source-of-truth not regressed (unblocking ADDS +$849 bear pnl); zero bull trades in the
  removed set ⇒ no bull-side regression possible.
- aggregate sharpe: not the deciding metric here (block is a per-setup filter); per-trade edge of the
  removed cohort is +$8.33/tr positive.
- positive_quarters of the BLOCK: 1/4 sub-windows help, 3/4 hurt (W1 −$336, W2 −$327, W3 +$376, W4 −$84).
- real_fills_validated: yes (simulate_trade_real via run_backtest --real-fills equivalent path).

## Disclosures (per OP-20)
1. Account-size assumption: $2,000 Safe equity → OTM-2 tier (v15_strike_offset_per_tier), 30% risk cap.
   The original block was tuned on OTM + premium-stop; the sign-flip is driven by the exit-structure
   change, not the strike (strike tier unchanged between OLD and CURRENT Safe ribbon engine).
2. Sample-bias: removed cohort is 102 trades, ALL bearish (trendline_rejection puts). The recent
   window (+$23) is thin (n=5). The decisive evidence is the IS/full-history sign-flip, not the recent slice.
3. Out-of-sample: OOS block_delta = −$40 (block hurts OOS too); recent +$23 (marginal). No OOS window
   shows the block adding meaningful value.
4. Real-fills check: yes — entire A/B run on real OPRA fills with the live managed-exit config.
5. Failure-mode enumeration: (a) single-position cascade — removing a trade frees the slot for a
   later same-day entry, so block_delta ≠ −(removed pnl); IS net −$371 reflects this, still negative.
   (b) +$8.33/tr is a thin edge near theta-noise; this is "stop blocking", not "add an edge". (c) the
   removed cohort is 100% bear, so this is functionally a BEAR-block removal, not a bull unblock —
   it does not advance the bull-direction target by itself, but it removes a stale filter that now
   suppresses bear winners. (d) recent regime (+$23) is the only window where the block marginally
   helps; if a recency-drawdown regime persists, the lift is small either way.
6. Concentration: top5_pct N/A (per-setup filter, not a strategy ranking); removed cohort WR 71% across
   102 trades is broad, not concentrated in a handful of days.

## Knob changes proposed
`automation/state/params.json`:
- `"midday_trendline_gate": true` → `false`
- (the `_midday_trendline_gate_doc` revert note can stay; flip the value only)

NEVER edit params.json myself — J ratifies. No heartbeat.md / CLAUDE.md change required (this gate
is read from params.json by the engine; the live heartbeat_core reads engine_cli gates which read params).

## Pre-merge gate
`python crypto/validators/runner.py` → 97/98 PASS (1 known-flaky excluded, overall_pass=True).
Current status: PASS before AND after (this work added only a read-only A/B script, no production code).

## My confidence (1-10) and why
**7.** The sign-flip is clean and mechanism-explained (OLD −$8.6/tr → CURRENT +$8.33/tr, driven by
chart-stop-primary + chandelier converting theta-bled OTM puts into managed winners), IS+OOS both show
the block hurting, anchors untouched, validator green. Docked points: (a) the per-trade edge is thin
(+$8.33/tr) and the portfolio block_delta is modest (−$371 IS over 16 months) — this is removing a
small drag, not unlocking a big edge; (b) the removed cohort is 100% bear, so this is a stale-BEAR-block
removal rather than a bull-direction win — it advances the "validation is the only scope" target
(nothing-validated-is-blocked) but does not by itself open a bull setup; (c) sub-window stability is
weak (1/4 help). Recommendation is UNBLOCK on the weight of the evidence, but it is a low-magnitude change.
