# H2 — Morning-Shoulder (10:00) Bleed Gate

**Rank:** 2 of 8 · **Score:** 8.5 · **Seam:** OUR real-fills per-hour P&L histogram · **Status:** PROPOSAL (test, do not ship)

---

## The setup / signal

A **data-validated** intraday time gate that raises the entry-score threshold (or suppresses marginal entries) during the **10:00-10:59 ET morning shoulder**, the empirically worst hour in OUR own real-fills population — while leaving 11:00 (the only solidly positive hour) untouched.

Concretely, three test arms:
- **A (suppress):** no entries 10:00-10:59 unless score is elite (confluence/sequence trigger present).
- **B (threshold bump):** +1 to required entry score in 10:00-10:59 (soft modifier, mirrors the macro pre-event tier pattern already in the engine).
- **C (size taper):** enter but at the floor contract count in 10:00-10:59 (interacts with H4).

## The insight (why it should have edge)

L167 (2026-06-19) hands us the per-hour P&L histogram of the real-fills population and explicitly corrects the folklore:

> "the actual per-hour ATM P&L histogram shows our bleed is the **10:00 morning shoulder** (10:00-10:59: n=146, **-$4,937** — the single worst hour), while lunch (12:00-12:59: n=21, -$109) is the LEAST-bad hour ... and 11:00-11:59 is actually the only solidly *positive* hour (**+$1,526**)."

And from J's real fills (`J-WEBULL-EDGE`): the 09:30-10:30 open is a coin-flip-to-bleeding band (51%/-$31 → 45%/-$11 → 45%/-$11), and **the production 09:35 entry gate fires J straight into his weakest band.** Two independent datasets (OUR engine + J's real fills) agree the morning shoulder is where money dies. The 10:00 hour is post-open-drive, pre-trend-establishment chop: the opening imbalance has cleared but the day's structure hasn't set, so directional entries get whipsawed. This is the *opposite* of the failed lunch-trough gate — we are gating the hour that **actually** bleeds in our data, exactly as L167 prescribes.

## EXACT backtest to validate

1. **First, reproduce the histogram** (L167 mandatory pre-step): regenerate the per-hour real-fills P&L/expectancy histogram on the current population (`analysis/recommendations/` style, ATM and ITM2). Confirm 10:00 is still the bleed and 11:00 still positive on the latest data. **If the histogram has shifted, the gate retargets the new bleed hour — do not assume 10:00.**
2. **Grid:** arms A/B/C above x strike {-2,-1,0} x stop {-0.99, -0.08}. Baseline = no time gate.
3. **Data + OOS:** `spy_5m_2025-01-01_2026-06-16.csv` + VIX; IS through Q1, OOS Q2. Critically check OOS-Q2's *own* per-hour histogram to confirm the 10:00 bleed is stable, not an IS artifact (regime-sign-stability, L166).
4. **Anchor (OP-16):** none of 4/29 (710P), 5/01 (721P @13:09/13:36), 5/04 (721P) entered in the 10:00 hour → gate must be a **no-op on all three anchors**. Verify `edge_capture` unchanged. (5/01's 13:09 leg and 13:36 trigger are both post-noon — safe.)
5. **Guards:** L171 truncation, L172 null-MAX, real-fills authority on the top cell.
6. **Scorecard:** `analysis/recommendations/h2-morning-shoulder-gate.json` including the IS and OOS per-hour histograms side-by-side and the per-arm `removed_hour_pnl` / `surviving_avg_delta`.

## Kill criteria (reject if ANY)

- The 10:00 bleed does not reproduce on the latest histogram, or inverts on OOS-Q2 (L166 sign-instability → the hour is regime-conditional, not a stable gate).
- Removing 10:00 fills **lowers** the surviving average (would mean 10:00 fills are near-breakeven, not the bleed — the exact L167 trap; the gate must improve, not just shrink, the book).
- Any arm changes `edge_capture` (would mean it touched an anchor — only acceptable direction is unchanged).
- Truncation or null gate fails on the top cell.

## Expected edge_capture x feasibility

**edge_capture HIGH** (loss-avoidance on the single worst -$4,937 hour; anchor-neutral by construction). **feasibility HIGH** (pure time feature, histogram already exists as the reproducer). Ranked just below H1 only because it is loss-*avoidance* (raises floor) rather than winner-*capture* (raises ceiling), and is more regime-sensitive than VWAP side.

## Disclosure (OP-20)

This is the *correct* form of the L167-failed time gate: justified by OUR per-window expectancy, targeting a genuinely negative window, removing no anchor winner. Must disclose: the gate is regime-sensitive (the bleed hour can move) — ship with the histogram as a standing monitor, not a frozen constant. Per-quarter stability and the 11:00-positive-hour-preserved check are mandatory disclosures.
