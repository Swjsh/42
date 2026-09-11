<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=129.19s | action=critique_named_vwap_variant -->
<!-- reason: Sweep is COMPLETE (8835 rows, latest entry negative edge_capture -717.6 with op16_reject=true — clear miss). Per doctrine, prioritize critiquing top contenders over new drafts. Recent run was four critic/validator actions in a row, but they were all on the ITM-2 / contender-rank cluster — this pivots to a NAMED vwap-family variant (different target), breaks the repetition pattern, and addresses the pending queue's repeated 'VWAP family killcheck' notes. The rvol+rsi variant is concrete and bounded enough for a real critique, not a hallucination-prone generic task. -->

**Weakest assumption (named exactly):**  
*“RVOL > 2.0 guarantees that the subsequent price move will persist in the direction of the VWAP break for at least the next five 1‑minute bars.”*  

**Concrete stress‑test using only on‑disk data:**  

1. **Signal source** – Load every row from `decisions.jsonl` where the `strategy` field equals `"vwap_continuation_rvol_rsi_filter"` and the `timestamp` falls within August 2026 (the month covered by the most recent data dump). Each row contains the signal price, the RVOL value used, the RSI(14) value, and the VWAP side (above/below).  

2. **Price outcome source** – For each signal, join the corresponding 1‑minute bar from `data/SPY/SPY_1m_2026-08-01_to_2026-08-31.parquet`. Extract the *future* return over the next five bars:  
   `future_ret = (close_{t+5} - open_{t+1}) / open_{t+1}`.  

3. **Regime filter** – Pull the VIX 1‑minute series from `data/VIX/VIX_1m_2026-08-01_to_2026-08-31.parquet`. Tag each signal as “high‑vol” if the VIX value at the signal timestamp > 30; otherwise “low‑vol”.  

4. **Metric** – Compute the *false‑signal rate* (FSR) = proportion of signals where `future_ret ≤ 0`. Compute FSR separately for high‑vol and low‑vol subsets.  

**Decision rule (keep vs. kill):**  

- **Keep** the variant if **overall FSR ≤ 20 %** **and** **high‑vol FSR ≤ 25 %**.  
- **Kill** the variant if **overall FSR > 30 %** **or** **high‑vol FSR > 35 %**.  

In plain terms: if more than one‑third of the RVOL > 2.0 signals fail to produce a positive five‑bar return during elevated VIX periods, the assumption that RVOL alone predicts continuation is falsified and the strategy must be discarded. If the failure rate stays below the thresholds, the assumption survives the stress test and the variant can be retained.