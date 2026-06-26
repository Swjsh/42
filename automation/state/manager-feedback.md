<!-- Sonnet overseer 2026-06-26 18:03 ET -->
- **STOP repeating validate-top-contender** — it ran at least twice this week; skip any action whose title contains "validate", "top contender", or "survivor" until a new candidate clears the grinder.
- **STOP pulling VIXCLS** — it was foraged twice today (1633 + 1713). If foraging again, pick a different series (e.g. `T10Y2Y` yield-curve spread, `DPCREDIT` Fed credit, or `SOFR`).
- **STOP accepting degenerate output** — the grinder-analysis cook hallucinated a culinary report ("500 kg of ingredients", "Chef Nemo culinary expert"). Any output that does not mention SPY, 0DTE, bars, strikes, or P&L within the first 100 words is **VOID**; log it as `LOW_QUALITY` and re-dispatch to a different lane.

**Next 4 actions (pick in order, skip if already done this session):**

1. **Rank** — read `analysis/recommendations/contender-rank-2026-06-26.json` and rank the listed candidates by `edge_capture` against the 771 J-edge floor; output a 5-row table with pass/fail.
2. **Critique** — send `vwap_reclaim_failed_break` (dormant WP edge) to the critic lane: "Does its stop at −8% still realize before theta kills the position given current VIX ~14.8 regime?"
3. **Ideate** — chef proposes ONE `vwap_continuation` variant gated on `rvol_floor ≥ 1.2` (relative volume at trigger bar); write backtest hypothesis card only, no code.
4. **Forage** — pull `T10Y2Y` (yield curve) from FRED; one paragraph: does the current inversion/steepening favour momentum or mean-reversion 0DTE bias?

**Output rule:** every response ≤ 400 words, must contain at least one concrete SPY/options data point, no repeated headers, no hallucinated domain content.
