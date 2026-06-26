# H5 — Calls-vs-Puts Expectancy Asymmetry

**Rank:** 5 of 8 · **Score:** 6.5 · **Seam:** J real-fills / scope-lock interplay · **Status:** PROPOSAL (test, do not ship — interacts with OP-16 setup scope lock)

---

## The setup / signal

A **direction-conditioned quality bar**: require a *higher* trigger-quality / confluence count for **put** (bear) entries than for **call** (bull) entries, reflecting J's documented 5x worse expectancy on puts. NOT a directional ban — a calibrated asymmetry in the entry threshold. Test arms:
- **A:** puts require >=1 extra confluence vs calls (e.g. bear score floor +1).
- **B:** calls eligible in a wider VWAP/structure band, puts only on the strongest fades (pairs with H1/H6).
- **C:** baseline symmetric (control).

## The insight (why it should have edge)

From `J-WEBULL-EDGE` directional-bias table:

> "**bull (calls) n=344 WR 46.8% -$2,070 exp -$6/trade** vs **bear (puts) n=323 WR 47.1% -$10,815 exp -$33/trade.** Near-identical WR, **5x worse expectancy on puts.** J's call timing is close to breakeven; his bleed is concentrated in puts." And: "8 of 10 [top losers] were puts."

This sits in deliberate tension with the engine's **scope lock** (OP-16: BEARISH_REJECTION is the *engine's* proven edge; BULLISH_RECLAIM is DRAFT). The reconciliation, stated in the doc itself: *"The discriminator is timing + VWAP alignment, not direction per se."* J's *manual put timing* bled; the *engine's* mechanical bear entries are the proven edge. So this hypothesis is really: **does the engine's bear edge survive a direction-conditioned quality bar, and do its few call entries actually clear a lower bar?** It also informs whether lifting BULLISH_RECLAIM out of DRAFT is justified — J's calls were his *less-bad* side.

## EXACT backtest to validate

1. **Stratify the existing population by side** on real-fills: confirm whether the engine (not J) also shows put-worse-than-call expectancy, or whether the engine's bear-rejection edge has *inverted* J's manual put bleed (entirely possible — the engine fixes J's timing).
2. **Grid:** arms A/B/C above x existing setups x strike/stop poles for the truncation cross-check.
3. **Anchor (OP-16) — load-bearing:** ALL of 4/29, 5/01, 5/04 are **puts**. A naive "puts need a higher bar" arm risks *dropping the anchors*. The gate must be calibrated so the three anchor puts (all high-confluence) still clear the raised bar → `edge_capture` preserved. If they don't clear it, the arm is too strict → reject that cell, not the hypothesis.
4. **Real-fills + OOS:** top cell OPRA-validated; IS through Q1, OOS Q2; per-quarter >=4/6.
5. **Guards:** L171, L172, L166 (don't trust J's cross-sectional bias as an option gate without OOS sign-stability — his put bleed is SPX 2021-23; verify on SPY-now).
6. **Scorecard:** `analysis/recommendations/h5-calls-vs-puts.json` with side-stratified real-fills expectancy (engine population) next to J's (his population) so the transfer/non-transfer is explicit.

## Kill criteria (reject if ANY)

- The engine population shows **no** put-worse asymmetry (the engine already fixed J's put-timing bleed → nothing to gate; this is the *likely* outcome and a valuable finding either way).
- Any passing arm drops a J-winner put → `edge_capture < baseline` → REJECT (the anchors are puts; this is the dominant risk).
- Sign of the asymmetry flips IS→OOS (L166 — J's directional bias doesn't transfer).
- Truncation/null gate fails.

## Expected edge_capture x feasibility

**edge_capture MED-HIGH** but with real **downside risk** to the anchors (all puts) — the gate must thread a needle. **feasibility MED** (stratification is easy; calibrating a put-bar that doesn't kill the anchor puts is delicate). Ranked #5 because the most probable outcome is "the engine already corrected J's put bleed" — which is a *confirmation* finding, not a new edge. Still worth running: it directly informs the BULLISH_RECLAIM-out-of-DRAFT question and validates the scope lock with data.

## Disclosure (OP-20)

This is the test most likely to *disconfirm* a naive read of J's data — and that's the point (L168: J's findings are hypotheses, not gates). Disclose prominently if the engine population inverts J's asymmetry; that would be strong evidence the engine's mechanical bear edge is real and J's put bleed was pure timing/sizing, not direction.
