# Trendline-Structure Conviction-Override -- Result

**Generated:** 2026-07-14T14:40:50.909895  
**Pre-registration:** `analysis/recommendations/trendline-structure-conviction-preregistration.json` (version 1, frozen status `FROZEN_PENDING_RUN`)

## Overall verdict: KILL

TL-C mechanically clears the frozen pass_bar's condition_1 threshold ($23.57/tr > $0) but the robustness diagnostic shows this is a single-trade artifact (one $1949.8 signal is 318.2% of the rescued population's net P&L; excluding it alone flips the mean to $-53.48/tr). TL-A breakeven at $-0.28/tr (n=18); TL-B breakeven at $-0.28/tr (n=18) cleanly FAIL condition_1. No candidate clears the evidence bar the mission requires ('ship nothing that fails the evidence bar no matter the pressure') -- block_elite_bull's VIX[15,17.5) band stands as correctly calibrated for ELITE bull level_reclaim signals; the trendline-as-veto/entry-wire remains correctly shadow-only/NEEDS-REVIEW. Today's (2026-07-14) VIX-deadzone block was NOT a mistake this study can overturn.

## Population

n=93 (IS n=85, OOS n=8) ELITE bull level_reclaim signals in VIX [15.0,17.5) reconstructed from the BASE (unblocked) run -- the exact population block_elite_bull would block. Reference: elite-bull-block-vix-01.json reported n_is_blocked=79, n_oos_blocked=4 (83 total) for the same predicate.

Baseline (what a rescue is measured against): elite-bull-block-vix-01.json IS VIX-15-17 bucket avg=$-100.0/tr, n=73.

## Candidate scorecard

| Candidate | Rescued n (IS/OOS) | Rescued mean $/tr | Rescued WR | Remainder n | Remainder mean $/tr | Verdict |
|---|---|---|---|---|---|---|
| TL-A | 18 (16/2) | $-0.28 | 0.222 | 75 | $-87.67 | **FAIL** |
| TL-B | 18 (16/2) | $-0.28 | 0.222 | 75 | $-87.67 | **FAIL** |
| TL-C | 26 (22/4) | $23.57 | 0.192 | 67 | $-107.36 | **PASS** |

## Pass-bar conditions (per candidate)

| Candidate | 1. rescued>0 | 2. no regression on remainder | 3. evidence floor n>=15 | 4. no-lookahead | Overall |
|---|---|---|---|---|---|
| TL-A | FAIL | PASS | met | PASS | **FAIL** |
| TL-B | FAIL | PASS | met | PASS | **FAIL** |
| TL-C | PASS | PASS | met | PASS | **PASS** |

## Robustness diagnostic (disclosure only -- not a pass_bar condition)

Leave-largest-winner-out sensitivity on the rescued subset's condition_1 mean:

| Candidate | Largest single trade | Share of rescued net P&L | Mean excl. largest winner | Condition_1 outlier-dependent? |
|---|---|---|---|---|
| TL-A | $1028.6 | n/a | $-60.8 | no |
| TL-B | $1028.6 | n/a | $-60.8 | no |
| TL-C | $1949.8 | 318.2% | $-53.48 | **YES** |

## Key findings

- Population: n=93 (IS n=85, OOS n=8) ELITE bull level_reclaim signals in VIX [15.0,17.5) reconstructed from the BASE (unblocked) run -- for comparison, elite-bull-block-vix-01.json's own ratification reported n_is_blocked=79, n_oos_blocked=4 (79+4=83) for the SAME predicate; this study finds n=93.
- Baseline (what the override is measured against): elite-bull-block-vix-01.json IS VIX-15-17 bucket avg=$-100.0/tr, n=73.
- TL-A: rescued n=18 (IS=16/OOS=2) mean=$-0.28 WR=0.222, remainder n=75 mean=$-87.67 -> FAIL.
- TL-B: rescued n=18 (IS=16/OOS=2) mean=$-0.28 WR=0.222, remainder n=75 mean=$-87.67 -> FAIL.
- TL-C: rescued n=26 (IS=22/OOS=4) mean=$23.57 WR=0.192, remainder n=67 mean=$-107.36 -> PASS.
-   ROBUSTNESS FLAG on TL-C: condition_1 (rescued subset positive) is NOT robust -- the single largest rescued trade ($1949.8, 318.2% of the rescued population's total P&L) is doing all the work. Excluding it alone, mean drops to $-53.48/tr (would FAIL condition_1). This is a disclosure-only diagnostic (no candidate/threshold/population was touched or re-picked) -- TL-C's mechanical PASS above should be read as OUTLIER-DEPENDENT, not a robust edge, until it accrues more evidence.

## Disclosures

- COUNTERFACTUAL BY CONSTRUCTION: nearly the entire population never received a real fill (that is what block_elite_bull prevents) -- every dollar_pnl in this study is a BS/cached-OPRA SIMULATED replay via orchestrator.run_backtest(use_real_fills=True), NOT a broker-verified fill. Per OP-16/C1, this can inform a SHIP/HOLD decision on the override but any resulting override must accrue its own real-fills track record (evidence_n>=15) before being trusted the way block_elite_bull itself now is.
- PNL engine convention: reused BYTE-IDENTICAL to elite_bull_vix_range_ab.py's own BASE dict (same strike_offset/account_equity defaults that produced elite-bull-block-vix-01.json's ratified avg=-$100/n=73 number) -- NOT necessarily the current live V15_SAFE_TIERS ATM strike convention (see CLAUDE.md C29 + analysis/deep-research/2026-07-11-strike-tier-reconciliation.md). This is a pre-existing, disclosed gap in the gate's OWN evidence base, not something this study introduces -- reusing it keeps the override measured on an apples-to-apples footing against the gate it modifies.
- Structure-state reconstruction is CPU-only and deterministic: trendline_engine.detect() on a trailing N_DAYS=5 trading-day window of the SAME cached spy_5m_2025-01-01_2026-06-16.csv used for signal reconstruction, truncated to timestamp_et <= signal's entry_time_et (C6). No OPRA or live network calls in this layer.
- Timestamp frame: wall-v1 (default et_frame.py convention, matches orchestrator.py's own pd.to_datetime(timestamp_et) parse with no utc=True normalization) -- consistent with the population reconstruction's own frame, not independently re-derived.
- Early-dataset signals (near 2025-01-02) may see a SHORTER-than-5-day lookback window (cold start, clamped to whatever trading days exist before them) -- matches production behavior for a real cold start, not a bug.
- The 2026-07-14 11:06 ET exhibit signal plays NO role in any pass/fail verdict above (excluded by the pre-registration's own ground rule) -- see hypothesis_provenance.today_exhibit in the pre-registration file for the narrative context that motivated this study.

## No-repick clause

Per the frozen pre-registration: no candidate rule, threshold, distance band, or data-layer convention was edited in light of results. The robustness diagnostic above is an ADDITIONAL disclosure computed on the already-frozen rescued sets -- it does not alter, threshold-shop, or re-run any candidate.
