<!-- Sonnet overseer 2026-06-26 16:03 ET -->
- **STOP** calling `rank_contenders` again — the top-6 have been identical across 4+ consecutive cycles (edge=1692/1563, same params). The leaderboard is stable; re-ranking it produces zero new information.

- **STOP** any action whose output would be byte-identical to a previous cycle's output. Before picking an action, check the last 3 outputs; if the result would match, skip it and pick differently.

- **Action 1 — Critique the #1 survivor for deployment blockers.** Target: `OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:fixed` (edge=1692, WF=1.98). Ask the free model: does `tp+150%` ever realize on a 0DTE OTM-2 in practice? Is `sell80%` compatible with `min_contracts=3`? Is WR=0.12 operationally viable (8-of-9 losers)? Output: a structured PASS/BLOCK verdict with the blocking reason named.

- **Action 2 — Ideate one new vwap_continuation variant with an rvol-floor gate.** The live vwap_continuation edge (LIVE, ITM-2, exp=+$105/t) has no volume filter. Instruct the free model to propose ONE concrete parameter set: rvol threshold, bar-count lookback, and expected direction of WR change. Output <=200 words, no code.

- **Action 3 — Forage a regime-context series.** Pull one free FRED series (e.g. `VIXCLS` or `SP500`) to check whether the current 10-day recency drawdown aligns with a known macro regime (post-FOMC drift, low-VIX chop). Output: a 3-sentence regime read + recommended hold/deploy stance for the dormant edges (vwap_reclaim_failed_break, vix_regime_dayside).

- **Action 4 — Draft a real-fills A/B scorecard stub for the #1 survivor.** Write the `analysis/recommendations/` JSON scaffold (fields: rule_id, OOS_positive, WF, sub_window_stable, anchor_no_regression, evidence_n) so it is ready to fill when replay data arrives. Output: the JSON, nothing else.

- **Rule:** Every output ≤400 words, structured (headers or bullets), no repeated content from prior cycles. If you cannot produce a non-duplicate output for your chosen action, pick a different action.
