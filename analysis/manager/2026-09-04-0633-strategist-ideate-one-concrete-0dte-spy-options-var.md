<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=25.226s | action=Ideate ONE concrete 0DTE SPY options var -->
<!-- reason: Today's session is a scheduled catalyst day (NFP 08:30 ET, 2 hours away) and the firm has a live shadow (RELEASE-BLACKOUT-FORWARD) already accruing per-release-day adverse-move data. Ideating a post-10:00 ET fade variant is the natural R&D next step that complements — and stress-tests — that shadow. Rotates role (last 3 cycles were all critic/chef/forager variants); strategist hasn't fired in this window. Concrete params (not boilerplate) per overseer rule. -->

entry_trigger: if |SPY_09:31 - SPY_09:30| / SPY_09:30 > 0.0025 then after 10:00 ET enter opposite‑direction 0DTE SPY option (puts for an up‑spike, calls for a down‑spike)  
option_selection: choose the 0DTE SPY contract whose absolute delta is between 0.40 and 0.55 at 10:00 ET (nearest ATM)  
stop: 50% loss of option premium (or 0.5 % underlying‑point move against the position, whichever occurs first)  
target: 100% gain of premium (or 0.5 % underlying‑point move in favor, whichever occurs first)  
time‑stop: hard exit at 11:30 ET regardless of P/L  
hypothesis: On NFP days the first‑minute spike is often an over‑reaction driven by liquidity‑seeking algos; after the 08:25‑10:00 ET blackout the market mean‑reverts, as shown by the ISM‑day worst‑1‑min option moves of –12.5% on 2026‑08‑05 and 2026‑09‑03, which were followed by a quick fade back toward the pre‑release level, providing a statistical edge for a post‑10:00 fade trade.