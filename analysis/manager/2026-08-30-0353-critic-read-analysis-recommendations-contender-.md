<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=14.914s | action=Read analysis/recommendations/contender- -->
<!-- reason: Sweep is at 8835 rows; last entry has edge_capture -717.6 (REJECT). Per overseer rule #1 next-action list, rank/critique top-5 contenders is the highest-value move now. I haven't critiqued the rank file specifically — only the sweep math. Different verb, different target, no hallucination risk. -->

- **#1 (edge_capture 0.42)** – Weakest assumption: **150 % TP unrealistic given 0DTE gamma** (the take‑profit is set far above typical 0‑day‑to‑expiry premium swings).  
- **#2 (edge_capture 0.38)** – Weakest assumption: **Trailing‑exit dependency on intrabar fill timing** (a 0.3 trailing exit assumes fills occur at the bar close, which often slips in fast‑moving 0DTE markets).  
- **#3 (edge_capture 0.35)** – Weakest assumption: **LR0 meaning‑zero regime filter** (setting the LR0 filter to zero removes any regime‑based protection, leaving the strategy exposed to choppy periods).  
- **#4 (edge_capture 0.33)** – Weakest assumption: **Sell‑100 % meaning flat sizing** (a sell‑size of 1.0 assumes constant contract count regardless of volatility, causing over‑exposure when IV spikes).  
- **#5 (edge_capture 0.30)** – Weakest assumption: **Stop‑40 being wider than typical 0DTE premium** (a 40‑point stop exceeds the average 0DTE premium, so the stop is rarely hit and risk is effectively uncapped).  

**Stress test for #1 contender:**  
Use the **2024‑08‑05 to 2024‑08‑09 carry‑event slice** (a period of sharp VIX‑driven gap moves and heavy 0DTE gamma squeezes).  
*Kill metric:* if the **maximum adverse excursion (MAE) exceeds 120 % of the collected premium** (i.e., the trade would have to lose more than the premium to hit the 150 % TP) **or** the rolling edge_capture over the slice falls below **0.10**, the strategy is deemed invalidated.