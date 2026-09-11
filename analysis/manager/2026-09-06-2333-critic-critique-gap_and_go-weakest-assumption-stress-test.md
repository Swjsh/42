<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=12.43s | action=critique-gap_and_go-weakest-assumption-stress-test -->
<!-- reason: Overseer's next-4 list #4 directly assigns this critique; gap_and_go is also the oldest un-critiqued shippable contender per escalation d73e7a5a. Recent log shows 6 critic runs in a row — but this one targets a different file (edgehunt-gap_and_go.json), not the rank/critique variants of nlwb/vwap already covered. -->

**1. Extracted top‑candidate specifications (verbatim from `analysis/recommendations/edgehunt-gap_and_go.json`)**

```
"entry_rules": "Buy when the opening price gaps up ≥0.5% of prior close AND the 5‑minute bar closes above the gap high; sell‑short when the opening price gaps down ≥0.5% AND the 5‑minute bar closes below the gap low.",
"exit_rules": "Exit long at the earlier of (a) 1.5× ATR profit target or (b) close of the same trading day; exit short symmetrically with a 1.5× ATR profit target or end‑of‑day close.",
"n": 212,
"WR": 0.58,
"expectancy": 0.12,
"wf": "walk‑forward: 60‑month in‑sample / 12‑month out‑of‑sample, rolled monthly"
```

**2. Single weakest empirical assumption**

The strategy assumes that the **same look‑back period (n = 212 bars) is optimal for both the long and short arms across all market regimes**. This implicitly treats the volatility‑driven gap‑and‑go process as stationary and symmetric, ignoring empirical evidence that down‑side gaps often exhibit different persistence and mean‑reversion characteristics than up‑side gaps, especially during high‑VIX periods.

**3. Falsifying stress test**

*Restrict the evaluation to **regular‑trading‑hours (RTH) only** (09:30–16:00 EST) and recompute WR, expectancy, and walk‑forward performance.*  
If the edge is primarily driven by pre‑market or after‑hours gaps (which are excluded in RTH), the strategy’s expectancy should drop to non‑significant levels (e.g., ≤0.02) and the walk‑forward out‑of‑sample Sharpe ratio should fall below 0.5, thereby falsifying the claim that the edge is robust to intraday dynamics alone.