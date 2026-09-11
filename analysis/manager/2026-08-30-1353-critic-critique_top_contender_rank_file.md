<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=15.907s | action=critique_top_contender_rank_file -->
<!-- reason: Contender sweep has 8835 rows and last output's edge_capture is negative (-717.6). Sweep may be near-complete; need a sharp adversarial read of the actual top pick before any new ideation. Varies target (top-ranked contender in dated file) and rotates away from the 3 prior strategist/critic l-variant actions. -->

**Contender:** Beta  
**Claimed edge_capture:** 0.55  
**Walk‑forward (wf) score:** 0.05  
**op16_reject:** true  
**n (total trades in sample):** 80  

**Stress‑test plan (3 bullets)**  
- **Out‑of‑sample consistency:** Run a rolling 6‑month walk‑forward on fresh market data; if the wf drops below ‑0.20 **or** op16_reject flags true in any window, reject the strategy.  
- **Fill‑frequency realism:** Simulate execution using realistic latency and order‑book depth; compute implied trades_per_day = n / trading days. If the simulated fill rate falls < 0.5× the back‑tested rate, flag the strategy as over‑optimistic.  
- **Op16 sensitivity:** Perturb the op16 filter thresholds ±10 % and re‑evaluate edge_capture; a > 30 % degradation indicates the result hinges on a brittle filter and should be downgraded.  

*Falsification criterion:* **Reject if wf < ‑0.20 OR op16_reject = true** in any walk‑forward window.  

(Word count ≈ 115)