<!-- gamma_manager (FREE) | role=critic lane=ollama::qwen3:14b elapsed=11.912s | action=critique-named-candidate-liquidity_sweep-wick-reversal-short -->
<!-- reason: Critique queue is the highest-leverage action: contender sweep is 8835 rows, gap_and_go already flagged for un-critiqued status, and we have a fresh short-bias candidate from today's chef batch that has never been adversarially reviewed. Recent logs show repeated critic actions but none on this specific file — fills a known gap and de-risks a live-trade candidate before any SHIP signal fires. -->

**Single weakest assumption:** The strategy assumes liquidity sweeps followed by wick reversals reliably signal short-term exhaustion in illiquid markets, ignoring regime-specific slippage dynamics.  
**Why it could fail live:**  
- *Low-volatility mean-reversion regimes*: Wick reversals may be noise, not exhaustion, leading to false signals.  
- *High-liquidity, fast-acting markets* (e.g., crypto spot): Sweeps may be absorbed by institutional orders, negating price impact.  
- *Earnings-driven volatility*: Liquidity distortions during earnings announcements could mask genuine reversals.  
**Cheapest falsification test:** Restrict backtests to assets with 30-day average volume < 10th percentile and re-measure win rate during wick-reversal triggers; if WR efficacy drops >20%, the assumption is invalidated.  
**Verdict:** DOWNGRADE — the strategy’s reliance on illiquidity as both a trigger and a protective factor is fragile in regimes where liquidity depth or speed-of-trading undermines sweep efficacy.