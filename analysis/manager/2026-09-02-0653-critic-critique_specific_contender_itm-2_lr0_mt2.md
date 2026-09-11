<!-- gamma_manager (FREE) | role=critic lane=ollama::qwen3:14b elapsed=22.469s | action=critique_specific_contender_ITM-2_LR0_mt2 -->
<!-- reason: Most recent contender is a worst-case sweep hit (negative edge_capture, op16 reject, n=79 only) — need a tight adversarial read to decide whether to file as NOISE-REJECT or send to a sibling variant; also satisfies rotation rule (last action was 'critic: ITM-' which was truncated — finishing it cleanly). -->

metric | value | verdict_flag  
edge_capture | -717.6 | pure noise  
expectancy | 9.07 | survivable edge  
wr | 0.3291 | pure noise  
max_dd | -2664.49 | pure noise  
wf | -0.829 | pure noise  
n | 79 | pure noise  

metric | value | verdict_flag  
fragile_assumption | price volatility asymmetry | high risk  
tp_stop_asymmetry | +150% TP vs -40% SL | fragile  

metric | value | verdict_flag  
stress_test | stop parameter | -20  
impact | reduces drawdown risk | critical