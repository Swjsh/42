<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=29.245s | action=Adversarially critique the candidate fil -->
<!-- reason: Recent actions are critic-heavy on older files (gap_and_go, edgehunt, contender-rank) but the newest chef output has NOT been critiqued yet. It is the highest-priority fresh artifact: an unvetted level-rejection variant that may collide with the twice-killed structure-shift family. Per queue.md, ANY new level variant must explain its difference or be DOA — this is the exact gate to apply now. Avoids the two retired failure modes (backtest-config-JSON hallucination and decision-agreement validator no-op). -->

**Weakest assumption (1 sentence):** The analysis assumes the named level + volume dry-up + reversal pattern is a distinct edge without providing any evidence to support that claim.  
**Why it fails (2 bullets):**  
- The file presents no statistical comparison or performance metrics that differentiate this pattern from the killed level+structure-shift family.  
- No concrete parameter values are disclosed; the configuration section contains only comments or placeholders, preventing verification of any settings.  
**Concrete stress test (1 numeric check):** Because the sample size N and effect size δ are not reported, the required N to survive a 5% Bonferroni correction across 8835 candidates cannot be calculated, indicating insufficient data to assess significance.  
**Verdict: KILL**