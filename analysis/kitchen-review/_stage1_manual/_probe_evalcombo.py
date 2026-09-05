import sys, time, json
sys.path.insert(0, r"C:\Users\jackw\Desktop\42\backtest")
t0 = time.time()
from autoresearch.overnight_grinder import evaluate_combo
combo = {}
res = evaluate_combo(combo)
elapsed = time.time() - t0
print("ELAPSED_SECONDS", elapsed)
print(json.dumps(res, default=str)[:2000])
