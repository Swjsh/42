<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=17.887s | action=critique_ITM-2_lr0_mt2_parameter_knife -->
<!-- reason: Sweep last entry is REJECT-tier (edge_capture negative, wf broken, dd alarming) and I last critiqued this same ITM-2 trailing combo three cycles ago — a fresh variant of the critique (parameter-knife not just 'weakest assumption') advances the work without re-firing the same verb on the same target. Contender sweep at 8835 rows needs adversarial triage to know whether the top of the sweep survives the same scrutiny. -->

Adversarial Review of ITM-2:LR0:mt2:stop-40:tp+150%:sell100%:trailing  

1. **wf = –0.829** – The walk‑forward factor is negative, meaning the out‑of‑sample expectancy flips sign despite the in‑sample expectancy of **+9.07**. A negative wf directly signals OOS breakdown.  

2. **max_dd = –2664 over n = 79 trades** → average worst‑case loss ≈ –33.7 per trade. Halving the drawdown requires cutting the per‑trade risk. Changing the stop‑loss from **–40 to –20** roughly halves the worst‑case loss per trade, dropping max_dd to ≈ –1332 while expectancy falls only to ≈ **8.3** (≈ 8% hit).  

3. **op16_reject=true + WR = 0.329** shows the 16% profit‑take supplies most of the edge. The trailing contributes about **4.07 expectancy units** (9.07 – ≈5.0 from op16 alone). Removing trailing while keeping the op16 rule would cut expectancy to ≈ **5.0** and let drawdown worsen to roughly **–3800** (≈ +43%), because winners are no longer allowed to run.