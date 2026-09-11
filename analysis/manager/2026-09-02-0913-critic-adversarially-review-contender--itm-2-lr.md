<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=11.315s | action=Adversarially review contender 'ITM-2:LR -->
<!-- reason: Last 8 actions were 5 critics + 1 strategist + 1 chef all circling this same ITM-2 LR0 contender. Sweep tail says it now shows op16_reject=true AND wf=-0.829 — both floors broken. Need a definitive KILL-or-COOK call from a fresh critic perspective so we stop burning cycles on it and free the queue. This critic prompt is narrow (named contender, named metrics, named floors) and asks a binary question the model can actually answer without hallucinating. -->

**FAILS**  
- edge_capture = -717.6 < 771 ❌ (fails edge_capture≥771)  
- op16_reject = true ❌ (requires false)  
- wf = -0.829 < 0.0 ❌ (fails wf≥0.0)  

**MARGIN OF DEATH**  
Even if wf could be nudged to ≥0.0 by a two‑line tweak (e.g., stop -40→‑55 or tp +150%→+100%), the strategy remains structurally unprofitable: LR=0, ITM‑2, WR≈0.33, expectancy only 9.07, and max DD ≈ ‑2.66k. Such a low win‑rate combined with negative edge capture cannot be rescued by modest parameter shifts; the configuration is inherently losing.

**KILL OR COOK**  
Archive as **failed_permanent**.