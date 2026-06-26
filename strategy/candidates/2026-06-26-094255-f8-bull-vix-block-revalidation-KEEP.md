# Strategy candidate: F8 bull-VIX gate (filter 8) re-validation — KEEP

> DRAFT — Chef proposal 2026-06-26 09:42:55. J ratifies.
> Verdict: **KEEP** the block. This is a re-validation that *confirms* an existing block, not a new edge.

## Hypothesis
Re-validate the BULL-direction block **VIX_BULL_LOW_THRESHOLD (filter 8)** — bull entry requires
`VIX < 17.20 OR vix_falling` (filters.py:804/885) — under the **CURRENT** engine (real OPRA fills +
managed exits: chart-stop-primary, −50% cap, chandelier, tp1=0.667 / runner=2.5), not the OLD engine
(OTM + BS-sim + −8%/−10% premium stops) it was ratified on (pre-2026-06-18).

Directional claim being tested: *the new ITM+tight+managed-exit structure may have turned the
formerly-losing OTM bull config into a winner, so F8 may now block winners.* **This is FALSIFIED.**

## Backtest evidence
- A/B tool: `backtest/autoresearch/f8_bull_vix_unblock_ab.py` (monkey-patches `evaluate_bullish_setup`
  to drop blocker 8 on the bull path only; bear-side F8 untouched). `use_real_fills=True` forced (C1).
- Train window: 2025-01-02 → 2025-12-31. Test (OOS): 2026-01-02 → 2026-06-18. Full: 2025-01-02 → 2026-06-18.
- The block suppresses exactly **3 bull trades** across full history (train +2, OOS +1).
- Those 3 admitted-on-unblock trades are **net LOSERS** under real fills + managed exits:
  - **full delta_bull_pnl = −$892** (bull P&L +$3,650 → +$2,759 when unblocked)
  - **OOS delta = −$310** | **train delta = −$582** — sign-stable negative across IS and OOS
  - bull WR **33.3% → 25.0%** when unblocked (the admitted trades are pure losers)
- Quarter stability: **3/3 quarters where the block bites are negative** (2025Q1 −$296, 2025Q3 −$286, 2026Q2 −$310); 0 positive. No quarter rewards unblocking.
- edge_capture (anchor): baseline $780 = unblocked $780 (delta **$0** — see anchor-no-regression).
- aggregate sharpe: unchanged on the anchor window; bull-only block contributes a positive +$892 to full-window P&L by suppression.
- final_score: edge_capture ($780) × sharpe — unchanged by the block decision (block KEEP = status quo).
- real_fills_validated: **yes** (use_real_fills=True; all 12 bull trades resolve to real OPRA exits, P&L non-zero).

## Disclosures (per OP-20)
1. **Account-size assumption:** params.json baseline + V15 j-edge overrides, per-trade qty cap-admitted via the live `cap_allows` authority (Safe-2 $2K tier). Bull trades shown at qty 15–22.
2. **Sample-bias disclosure:** only **3 bull trades** are affected by F8 across 18 months — small N. The signal is the *consistency* (all 3 lose, every biting quarter negative, IS and OOS agree in sign), not magnitude. A 3-trade sample cannot by itself prove a per-trade edge, but it is more than enough to refute the "block-now-suppresses-winners" hypothesis: the suppressed population is uniformly losing.
3. **Out-of-sample test result:** OOS (2026) delta = −$310 — same sign as train (−$582). Unblocking degrades OOS. KEEP holds OOS.
4. **Real-fills check:** done — `use_real_fills=True`, OPRA 0DTE cache covers 2025-01-02 → 2026-06-18 for both C and P. First run read the wrong P&L field (`pnl_dollars`, which does not exist → silent $0) and was corrected to `dollar_pnl`; corrected run is authoritative.
5. **Failure-mode enumeration:**
   - *F8-disabled-globally confound:* avoided — patch removes blocker 8 from the BULL result only; bear-side F8 (VIX>17.30-rising) is untouched, so J's bearish source-of-truth is unaffected by construction.
   - *Engine-score assert mismatch:* `GAMMA_ENGINE_SCORE_ASSERT=0` set so the score-bar oracle doesn't fail on the patched bull path.
   - *Wrong-P&L-field silent zero:* caught and fixed (see L182-class — display field name drift).
6. **Concentration:** top5_pct not meaningful here — the decision rides on a 3-trade suppressed population, fully enumerated above (no hidden concentration; all 3 disclosed).

## Anchor-no-regression (OP-16)
J's source-of-truth trades are all bearish puts. Unblocking a BULL gate leaves them **identical**:
anchor edge_capture **$780 → $780 (delta $0)**, OP-16 floor (≥$771) **PASS**. Confirmed empirically, not just by construction.

## Knob changes proposed
**NONE.** Recommendation is **KEEP** — leave filter 8 exactly as-is in `filters.py:804/885`
(`VIX_BULL_LOW_THRESHOLD = 17.20`; `vix_pass = ctx.vix_now < 17.20 or vd == "falling"`).
No params.json edit. (For the record, the param diff that *would* unblock — and which this analysis
recommends AGAINST — is: remove the F8 VIX gate on the bull path, or expose a `block_bull_vix_low: false`
override. There is no params.json knob today; F8 is hardcoded.)

## Pre-merge gate
`python crypto/validators/runner.py` → **passed=97/98 overall_pass=True** (1 known-flaky excluded).
Status: GREEN before and after (work added only a read-only analysis file; no production code touched).

## My confidence (1-10) and why
**8/10.** The direction of the result is unambiguous and sign-stable across IS/OOS and every biting quarter:
the F8-suppressed bull population loses money under the *new* engine too, so the "stale block now eats
winners" hypothesis is cleanly refuted. The only reason it isn't a 9–10 is the small affected N (3 trades) —
F8 simply doesn't bite often, because upstream gates (ribbon-BULL-stack, buyer-pressure, bull_min_triggers≥2)
already exclude most VIX-elevated bull bars. KEEP earns its keep on the margin, not by volume.
