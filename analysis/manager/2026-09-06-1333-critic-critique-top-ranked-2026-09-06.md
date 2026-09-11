<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=7.609s | action=critique-top-ranked-2026-09-06 -->
<!-- reason: Last 8 actions were 5x critic, 1x forager, 1x strategist, 1x chef. Critic is overdue for FRESH target — the 06-29 rank file is the canonical sweep top, and the prior critic actions targeted gap_and_go and other specific contenders, not the current top-ranked. The 8835-row sweep is COMPLETE per the tail note; pivoting from chef/ideation to validate-and-revoke the #1 contender is highest-value right now. No repeated verb (different file/target than prior critic actions). -->

# Adversarial Critique: Top‑Ranked Contender (2026‑06‑29)

- **Combo & edge_capture**: `["EMA_20", "MACD_hist", "vol_regime_filter"]` → **edge_capture = 0.0635** (rank #1 in contender-rank-2026-06-29.json).  
- **(a) Weakest assumption**: The edge claim assumes that the volatility‑regime filter (VIX < 15) persistently isolates low‑slippage, mean‑reverting periods; in reality, regime shifts can occur intraday, making the filter’s look‑ahead bias a hidden source of over‑fit.  
- **(b) Concrete stress‑test**: Shift all entry signals forward by **+1 bar** (i.e., enter one period after the original signal) while keeping exits unchanged; this tests sensitivity to the assumed perfect timing of the regime filter.  
- **(c) Pre‑registered kill criterion**: If the shifted‑entry backtest yields an edge_capture **≤ 0.020** (a > 68 % drop), the edge is considered spurious and the contender is revoked.