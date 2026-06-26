<!-- gamma_manager (FREE) | role=validator lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=4.312s | action=Validate the contender sweep: run OTM-2: -->
<!-- reason:  -->

I’m ready to run the validation, but I need the actual trade data that makes up the **J‑source‑of‑truth** (the 7 trades you’d like to compare against). Could you please provide:

1. The entry/exit prices, timestamps, and direction (long/short) for each of the 7 trades, **or** a CSV/JSON snippet containing that information.  
2. Any additional context the strategy uses (e.g., the underlying instrument, timeframe, or any filters that aren’t captured in the OTM‑2:LR0:mt1:stop‑8:tp+150%:sell80% string).

Once I have those details, I can simulate the OTM‑2:LR0:mt1:stop‑8:tp+150%:sell80% rules on those trades and report the validation metrics (win‑rate, P&L, max‑drawdown, etc.) you’re looking for.