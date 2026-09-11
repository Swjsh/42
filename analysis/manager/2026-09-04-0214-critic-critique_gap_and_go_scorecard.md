<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=62.577s | action=critique_gap_and_go_scorecard -->
<!-- reason: Sweep last row is REJECT on its face (edge_capture=-717.6) and I just did three consecutive critic passes on ITM-2-adjacent rows. Continuing on the same ITM-2 axis is wasteful; the freshest NAMED non-ITM-2 candidate from `analysis/recommendations/` is `edgehunt-gap_and_go.json` (the only scorecard the overseer explicitly named). Switching target breaks the recent-action streak and addresses a candidate the overseer already queued. -->

## Verdict: CLEAN_REJECT ##
1. The contender row does not list any sub‑regime (e.g., VIX bucket, time‑of‑day, gap‑day) where the 9.07 expectancy holds; this information is not exposed in the file.  
2. The exit_reason histogram is not exposed in the contender row, so the actual exit distribution cannot be quoted from the file.  
3. In‑sample versus out‑of‑sample expectancy values are not exposed in the contender row.  
4. The op16 threshold that caused the reject and whether the failure is due to magnitude or stability are not exposed in the contender row.