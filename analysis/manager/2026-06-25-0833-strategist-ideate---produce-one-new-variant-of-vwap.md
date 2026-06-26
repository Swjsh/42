<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=8.012s | action=IDEATE — Produce ONE new variant of vwap -->
<!-- reason:  -->

# Strategy Variant: `vwap_reclaim_rvol_gate`

**Base Strategy:** `vwap_reclaim_failed_break`  
**Variant Name:** `vwap_reclaim_rvol_gate`  
**Status:** DRAFT  
**Target File:** `strategy/candidates/vwap_reclaim_rvol_gate_DRAFT.md`  

---

## Overview
This variant adds an **RVOL (Relative Volume) ≥ 1.2** entry gate to the original `vwap_reclaim_failed_break` logic. The gate ensures that a trade is only considered when the volume on the reclamation bar is at least 20 % above the average volume of the look‑back period, thereby filtering for stronger participation.

---

## Entry Conditions (in addition to base conditions)

| Condition | Description |
|-----------|-------------|
| **Price Reclaim** | The close price must cross back above the VWAP after having previously broken below it (failed break). |
| **RVOL Gate** | `RVOL_current_bar ≥ 1.2` where `RVOL = (Current Bar Volume) / (Average Volume over N periods)`. |
| **Volume Look‑back (N)** | Default `N = 20` bars (configurable). |
| **Other Base Filters** | All original filters of `vwap_reclaim_failed_break` remain unchanged (e.g., trend context, time‑of‑day, stop‑loss placement, etc.). |

### RVOL Calculation
1. Compute the simple moving average (SMA) of volume over the look‑back window `N`.  
2. Divide the volume of the current bar by this SMA.  
3. The resulting ratio is the RVOL value used for the gate.

*If the RVOL threshold is not met, the entry is suppressed even if the price reclaim condition is satisfied.*

---

## Parameters (exposed for tuning)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rvollength` | `20` | Number of bars used for the volume average in RVOL calculation. |
| `rvolthreshold` | `1.2` | Minimum RVOL required to allow an entry. |
| (All base strategy parameters) | — | Inherited from `vwap_reclaim_failed_break` (e.g., VWAP length, failed‑break look‑back, etc.). |

---

## Exit Logic
Unchanged from the base strategy: exit on the first of the following:
- Price closes below VWAP again (re‑break).  
- Pre‑defined profit target or stop‑loss is hit.  
- Time‑based exit (if applicable).

---

## Notes
- The RVOL gate is intended to increase the probability that the reclamation is supported by genuine market interest rather than low‑volume noise.  
- Adjust `rvollength` and `rvolthreshold` based on instrument characteristics and timeframe.  
- Back‑test validation should compare performance metrics (win rate, profit factor, drawdown) against the base `vwap_reclaim_failed_break` to confirm the gate’s efficacy.  

--- 

*End of variant specification.*