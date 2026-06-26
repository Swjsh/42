# Strategy candidate: OP-16 BULLISH_RECLAIM setup-scope lock — re-validation under current engine

> DRAFT — Chef proposal 2026-06-26. J ratifies. VERDICT: **KEEP**.

## Hypothesis
The OP-16 setup-scope lock ("BULLISH_RECLAIM stays DRAFT until J has 3 live wins") was a
DOCTRINE policy, not ratified on the current real-fills + managed-exit engine. Claim under test:
under the CURRENT engine (real OPRA fills, production params, OTM-ladder + chart-stop-primary +
chandelier-managed exits), unblocking the ribbon BULLISH_RECLAIM setup either (a) adds a real
per-trade edge → UNBLOCK, or (b) only adds a concentration mirage → KEEP.

## Backtest evidence (real fills, simulator_real path via run_backtest)
- Window: 2025-01-02 .. 2026-06-18 (full OPRA cache coverage; IS + OOS + recent)
- Engine: production params.json translated via `_params_to_kwargs`, account_equity=$2,000 (Safe-2 tier)
- A/B: **KEEP** = `enable_bullish=False` (current dormant scope-lock) vs **UNBLOCK** = `enable_bullish=True`
  (bull allowed; its own validated sub-gates — block_elite_bull, block_bull_1100_1200,
  block_bull_ribbon_flip — stay ON). Same real fills, same params, only the scope toggle differs.

| metric | KEEP (bear-only) | UNBLOCK (bull+bear) | delta |
|---|---|---|---|
| trades | 38 | 63 | +25 bull |
| total P&L | $836 | $6,423 | +$5,586 |
| aggregate sharpe (per-trade) | 0.046 | 0.156 | +0.11 |
| max drawdown | -$3,206 | -$4,117 | **-$910 worse** |
| top5_pct of total | 4.45 | 1.29 | (less concentrated aggregate) |

**Headline aggregate looks bullish (+$5,586), but the OP-22 honesty cuts reverse it:**
- **positive_quarters = 2/6** (bull subset): 2025Q3 +$7,308 (n=9, WR 0.89) is the ENTIRE edge.
  2025Q4 -$1,398 (0/5), 2025Q1 -$285, 2025Q2 -$352, 2026Q2 -$911 (WR 0.40). FAILS ≥4/6 bar.
- **drop-top5 = -$1,573** (mean -$78.7 over remaining 20 trades). Strip 5 trades → bull setup is
  NET NEGATIVE per-trade. Classic C4 concentration artifact (a published anomaly, not an option edge).
- **recent (≥2026-05-19) = -$1,247 over 4 trades, WR 0.25** — actively bleeding in the current regime.
- **OOS (2026+) = +$314 over 9 trades, mean +$35** — barely positive, and itself top-heavy
  (2026Q1 +$1,224 masks 2026Q2 -$911).

## Anchor-no-regression (OP-16 bearish source-of-truth)
**CONFIRMED — zero regression.** All 6 anchor-day engine trades are BEARISH_REJECTION (PUT).
The bull setup fires on NONE of the anchor days. edge_capture is byte-identical between KEEP and
UNBLOCK (delta_edge_capture = 0.0). Unblocking the bull side is structurally orthogonal to the
bearish source-of-truth — it cannot help or hurt those 7 trades.
(NB: the engine's raw edge_capture on these days is polluted by a pre-existing engine↔J entry
divergence on 4/29 — the engine takes -$1,065/-$300 bear trades where J took a +$342 710P. That
divergence is IDENTICAL in both arms and is out of scope for this bull-direction A/B.)

## The decisive distinction (ribbon BULLISH_RECLAIM ≠ vwap bull side)
The OP-16 top-level lock currently governs TWO things; they have opposite verdicts:
1. **Ribbon `enable_bullish` (OTM ladder, this A/B):** FAILS drop-top5 + sub-window + recent-regime.
   The lock correctly suppresses a non-edge. **KEEP.**
2. **VWAP-family bull side (the ITM+tight+managed profile the task points to):** the
   vwap_continuation scorecard (`j-daily-pattern-LIVE.json`) shows `both_dirs_positive=True`,
   **drop_top5_mean = +$24.45** (robust, NOT an artifact), drop_top3 = +$29.05. That IS a genuine
   bull-side edge — and `j_vwap_cont_side` is ALREADY `"both"` in params (NOT put-locked).
   `j_vix_dayside_side` is ALSO already `"both"`. So OP-16 is **no longer suppressing the one bull
   edge that passes** — the validated bull path is already side=both, awaiting only J's enable flip.

The block as it stands already does the right thing: suppresses the failing ribbon bull setup,
does NOT suppress the passing vwap bull side. Removing the scope lock wholesale would re-admit the
ribbon bull non-edge for no benefit.

## Disclosures (per OP-20)
1. **Account-size assumption:** $2,000 Safe-2 tier (v15 ladder → OTM-3 at this equity). Bull edge
   may differ at higher tiers, but the suppressed ribbon bull setup uses the same generic ladder.
2. **Sample-bias:** bull subset n=25 over 17.5 months; the +$5,586 is 9 trades in one quarter
   (2025Q3). Small-n, regime-concentrated — exactly the population OP-22 drop-top5 is designed to catch.
3. **Out-of-sample:** OOS (2026+) bull mean +$35/trade, but not sub-window-stable (2026Q2 negative);
   recent month NEGATIVE. Fails all-cuts-OOS-positive.
4. **Real-fills check:** YES — entire A/B run on real OPRA bars via `simulate_trade_real` (run_backtest
   use_real_fills=True). No BS-sim.
5. **Failure-mode enumeration:** if UNBLOCKED, the ribbon bull setup bleeds in non-2025Q3 regimes
   (2025Q4 0/5, 2026Q2 WR 0.40, recent WR 0.25) and deepens max drawdown by $910.
6. **Concentration:** bull subset top5 carries +$7,159 of the +$5,586 net (drop-top5 = -$1,573).

## Knob changes proposed
**NONE.** Recommendation is KEEP. The OP-16 setup-scope lock stays as-is.
- params.json `j_vwap_cont_side` and `j_vix_dayside_side` are ALREADY `"both"` — no change needed;
  the validated bull edge is not being suppressed by this block.
- Ribbon `enable_bullish` stays effectively dormant under doctrine (CLAUDE.md OP-16 unchanged).
- For the exact-param-diff-to-unblock (NOT recommended): would be CLAUDE.md OP-16 edit removing the
  "BULLISH_RECLAIM stays DRAFT" clause — declined; the ribbon bull setup fails OP-22.

## Pre-merge gate
`python crypto/validators/runner.py` → **passed=97/98, overall_pass=True** (1 known-flaky excluded).
No production files touched (A/B script is research-only in `backtest/autoresearch/`). Gate green before
and after.

## My confidence (1-10) and why
**8.** The drop-top5 reversal is decisive and the anchor-no-regression is structurally clean (delta=0).
The one caveat keeping it off 9: the engine↔J 4/29 entry divergence means I can't fully trust the raw
edge_capture floor on anchor days — but since it's identical in both arms it doesn't affect the
bull-scope verdict. The block earns its keep: it suppresses a concentration-mirage ribbon bull setup
while the genuinely-validated vwap bull edge already runs side=both unobstructed.

Scorecard: `analysis/recommendations/chef-bull-scope-ab-2026-06-26.json`
