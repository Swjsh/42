import json, collections
import numpy as np

with open("scratch_day_arm_pnl.json", encoding="utf-8") as f:
    day_arm = json.load(f)  # keys "date|arm"

arms = ["bold-2", "risky-1", "risky-3", "safe-2", "safe-3"]
dates_all = sorted(set(k.split("|")[0] for k in day_arm))

def corr_stats(dates):
    mat = np.array([[day_arm.get(f"{d}|{a}", 0.0) for a in arms] for d in dates])
    corr = np.corrcoef(mat.T)
    n = len(arms)
    off = [corr[i,j] for i in range(n) for j in range(n) if i != j]
    rho = float(np.mean(off))
    effN_formula = n / (1 + (n-1)*rho)
    eig = np.clip(np.linalg.eigvalsh(corr), 0, None)
    effN_pr = (eig.sum()**2) / (eig**2).sum()
    return corr, rho, effN_formula, effN_pr, mat

print("=== Including today (partial session), n_days=", len(dates_all), "===")
corr, rho, effN_f, effN_pr, mat = corr_stats(dates_all)
print("avg pairwise rho:", round(rho,3), "effN(formula):", round(effN_f,3), "effN(participation ratio):", round(effN_pr,3))

print("\n=== Excluding today (full sessions only), n_days=", len(dates_all)-1, "===")
dates_ex = [d for d in dates_all if d != "2026-09-03"]
corr2, rho2, effN_f2, effN_pr2, mat2 = corr_stats(dates_ex)
print("avg pairwise rho:", round(rho2,3), "effN(formula):", round(effN_f2,3), "effN(participation ratio):", round(effN_pr2,3))

# bootstrap CI on avg pairwise rho (resample days with replacement), excl-today version (cleaner: full sessions only)
rng = np.random.default_rng(20260903)
boot_rhos = []
boot_effn = []
n_days = len(dates_ex)
for _ in range(3000):
    sample = [dates_ex[i] for i in rng.integers(0, n_days, n_days)]
    try:
        c, r, ef, epr, _ = corr_stats(sample)
        if not np.isnan(r):
            boot_rhos.append(r)
            boot_effn.append(ef)
    except Exception:
        pass
boot_rhos = np.array(boot_rhos)
boot_effn = np.array(boot_effn)
print(f"\nBootstrap (3000 resamples, days w/ replacement, excl-today, n={n_days}):")
print(f"  avg pairwise rho: {np.mean(boot_rhos):.3f}  95% CI [{np.percentile(boot_rhos,2.5):.3f}, {np.percentile(boot_rhos,97.5):.3f}]")
print(f"  effN (formula):   {np.mean(boot_effn):.3f}  95% CI [{np.percentile(boot_effn,2.5):.3f}, {np.percentile(boot_effn,97.5):.3f}]")

print("\nFull correlation matrix (excl-today, full sessions n={}):".format(len(dates_ex)))
print("           " + " ".join(f"{a:>8s}" for a in arms))
for i,a in enumerate(arms):
    print(f"{a:10s} " + " ".join(f"{corr2[i,j]:+8.3f}" for j in range(len(arms))))
