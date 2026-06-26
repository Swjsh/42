<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=24.888s | action=IDEATE — Produce ONE new variant of vwap -->
<!-- reason:  -->

#Strategy Variant Specification  
**File:** `strategy/candidates/vwap_reclaim_rvol_gate_DRAFT.md`  
**Base Strategy:** `vwap_reclaim_failed_break` (currently dormant, previously blocked by WP‑0)  
**Variant Name:** `vwap_reclaim_rvol_gate`  

## Overview  
This variant introduces an additional entry gate based on **Relative Volume (RVOL)** to the existing VWAP‑reclaim‑after‑failed‑break logic. The core idea remains: enter a long position when price reclaims the VWAP after a prior failed break‑out attempt. The new gate filters entries to only those occurring on bars where the current volume is at least 1.2× the average volume over a defined look‑back window, thereby increasing the probability that the reclaim is supported by genuine participation.

## Parameters  

| Parameter | Description | Default Value | Notes |
|-----------|-------------|---------------|-------|
| `rvollookback` | Number of bars used to calculate the average volume for RVOL | `20` | Can be adjusted to suit timeframe |
| `rvolthreshold` | Minimum RVOL required for entry | `1.2` | Entry allowed only if `current_volume / avg_volume(rvollookback) >= rvolthreshold` |
| `vwaplen` | Look‑back period for VWAP calculation (inherited from base) | unchanged | |
| `breaklen` | Look‑back period to detect a failed break (inherited from base) | unchanged | |
| `reclaim_tolerance` | Price tolerance for considering a reclaim of VWAP (inherited from base) | unchanged | |

## Entry Conditions (Long)  

1. **Failed Break Detection** (as in base):  
   - Within the last `breaklen` bars, price closed **below** the VWAP after having previously closed **above** it (or vice‑versa depending on direction; for long we look for a prior failed upward break).  

2. **VWAP Reclaim Signal** (as in base):  
   - Current bar’s close price crosses **above** the VWAP (within `reclaim_tolerance`).  

3. **RVOL Gate** (new):  
   - Compute average volume over the past `rvollookback` bars: `avg_vol = mean(volume[‑rvollookback … ‑1])`.  
   - Compute current RVOL: `rvol = volume[0] / avg_vol`.  
   - Entry is permitted only if `rvol >= rvolthreshold` (i.e., ≥ 1.2).  

4. **All other base filters** (e.g., volatility, time‑of‑day, max‑position limits) remain unchanged and are applied after the RVOL gate.

## Exit Conditions  

- Unchanged from the base strategy (e.g., stop‑loss, take‑profit, or opposite‑signal exit).  
- The RVOL gate does **not** affect exit logic.

## Rationale  

- A reclaimed VWAP after a failed break can sometimes occur on low‑volume, noisy price action.  
- Requiring RVOL ≥ 1.2 ensures that the reclaim is accompanied by above‑average participation, increasing the likelihood of sustained momentum.  
- The gate is simple, computationally inexpensive, and can be tuned via `rvollookback` and `rvolthreshold` without altering the core reclamation logic.

## Usage  

- Replace the dormant `vwap_reclaim_failed_break` file with this variant (or keep both and select via configuration).  
- Back‑test using the same data pipeline as the base strategy; adjust `rvollookback` and `rvolthreshold` as needed to optimize for the target instrument and timeframe.  

---  

*End of specification.*